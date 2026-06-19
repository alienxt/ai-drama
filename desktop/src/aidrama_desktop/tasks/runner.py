from __future__ import annotations

import urllib.request
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from aidrama_desktop import __version__
from aidrama_desktop.api.client import ApiClient
from aidrama_desktop.platforms.base import PlatformPublisher
from aidrama_desktop.video.ffmpeg import FfmpegProcessor


@dataclass
class TaskRunner:
    api: ApiClient
    processor: FfmpegProcessor
    publisher: PlatformPublisher
    work_dir: Path
    device_id: str
    downloads_dir: Path | None = None
    processed_dir: Path | None = None
    publisher_factory: Callable[[str], PlatformPublisher] | None = None
    progress_callback: Callable[[str, str | None], None] | None = None
    cancel_checker: Callable[[], bool] | None = None

    def heartbeat(self) -> None:
        self.api.post(
            "/desktop/devices/heartbeat",
            {"deviceId": self.device_id, "appVersion": __version__, "osName": "desktop", "idle": True},
        )

    def run_once(self) -> str:
        task = self.api.post("/desktop/tasks/claim", {"deviceId": self.device_id})
        return self._execute_task(task)

    def publish_once(self) -> str:
        task = self.api.post("/desktop/tasks/publish-next", {"deviceId": self.device_id})
        return self._execute_task(task)

    def _execute_task(self, task: dict | None) -> str:
        if not task:
            self._notify("空闲", None)
            return "no-task"
        task_id = task["id"]
        self._notify("任务已领取", task_id)
        try:
            self._progress(task_id, "DOWNLOADING", 10)
            download_plan = self.api.get(f"/desktop/dramas/{task['dramaId']}/download-plan")
            drama_title = self._drama_title(download_plan, task)
            source_files = self._download(download_plan, task_id, drama_title)
            self._progress(task_id, "PROCESSING", 45)
            processed = []
            total_files = len(source_files)
            for index, source in enumerate(source_files, start=1):
                self._notify(f"处理：{drama_title} 第 {index}/{total_files} 集", task_id)
                processed.append(
                    self.processor.transcode_for_wechat_video(
                        source,
                        self.output_dir() / download_plan["dramaId"] / source.with_suffix(".mp4").name,
                    )
                )
            self._progress(task_id, "UPLOADING", 75)
            self._notify(f"发布：{drama_title}", task_id)
            publish_id = self._publisher_for(task).publish(
                processed,
                title=drama_title,
                summary=download_plan.get("summary"),
            )
            self.api.put(
                f"/desktop/tasks/{task_id}/result",
                {"success": True, "platformPublishId": publish_id, "failureReason": None},
            )
            self._notify("任务完成", task_id)
            return "succeeded"
        except Exception as exception:  # noqa: BLE001
            if isinstance(exception, TaskCancelled):
                self.api.put(f"/desktop/tasks/{task_id}/progress", {"status": "CANCELLED", "progress": 0})
                self._notify("任务已停止，可重新分发", task_id)
                return "cancelled"
            self.api.put(
                f"/desktop/tasks/{task_id}/result",
                {"success": False, "platformPublishId": None, "failureReason": str(exception)},
            )
            self._notify(f"任务失败：{exception}", task_id)
            return "failed"

    def _progress(self, task_id: str, status: str, progress: int) -> None:
        self._notify(status, task_id)
        self.api.put(f"/desktop/tasks/{task_id}/progress", {"status": status, "progress": progress})

    def _publisher_for(self, task: dict) -> PlatformPublisher:
        media_account_id = task.get("mediaAccountId")
        if self.publisher_factory and media_account_id:
            return self.publisher_factory(str(media_account_id))
        return self.publisher

    def _notify(self, stage: str, task_id: str | None) -> None:
        if self.progress_callback:
            self.progress_callback(stage, task_id)

    @staticmethod
    def _drama_title(download_plan: dict, task: dict) -> str:
        return str(download_plan.get("title") or task["dramaId"])

    def _download(self, download_plan: dict, task_id: str, drama_title: str) -> list[Path]:
        target_dir = self.input_dir() / download_plan["dramaId"]
        return download_episodes(
            download_plan,
            target_dir,
            self.api.base_url,
            headers=self.api.download_headers(),
            progress_callback=lambda index, total, episode, downloaded, total_bytes: self._notify(
                self._download_stage(drama_title, index, total, downloaded, total_bytes),
                task_id,
            ),
            should_stop=self.cancel_checker,
        )

    def input_dir(self) -> Path:
        return self.downloads_dir or self.work_dir / "dramas" / "downloads"

    def output_dir(self) -> Path:
        return self.processed_dir or self.work_dir / "dramas" / "processed"

    @staticmethod
    def _download_stage(
        drama_title: str,
        index: int,
        total: int,
        downloaded_bytes: int,
        total_bytes: int | None,
    ) -> str:
        downloaded_mb = downloaded_bytes / 1024 / 1024
        if total_bytes and total_bytes > 0:
            total_mb = total_bytes / 1024 / 1024
            percent = min(100, int(downloaded_bytes * 100 / total_bytes))
            return f"下载：{drama_title} 第 {index}/{total} 集 {downloaded_mb:.1f}/{total_mb:.1f} MB（{percent}%）"
        return f"下载：{drama_title} 第 {index}/{total} 集 {downloaded_mb:.1f} MB"


def download_episodes(
    download_plan: dict,
    target_dir: Path,
    base_url: str,
    headers: dict[str, str] | None = None,
    progress_callback: Callable[[int, int, dict, int, int | None], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> list[Path]:
    target_dir.mkdir(parents=True, exist_ok=True)
    cover_file = download_cover(download_plan, target_dir, base_url, headers=headers, should_stop=should_stop)
    write_drama_metadata(download_plan, target_dir, cover_file)
    files: list[Path] = []
    episodes = download_plan["episodes"]
    total = len(episodes)
    for index, episode in enumerate(episodes, start=1):
        target = target_dir / f"{episode['episodeNo']:03d}.mp4"
        url = resolve_download_url(str(episode["downloadUrl"]), base_url)
        request = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(request) as response, target.open("wb") as output:
            total_bytes = _content_length(response)
            downloaded = 0
            while True:
                if should_stop and should_stop():
                    raise TaskCancelled("用户停止下载")
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    progress_callback(index, total, episode, downloaded, total_bytes)
        files.append(target)
    return files


def download_cover(
    download_plan: dict,
    target_dir: Path,
    base_url: str,
    headers: dict[str, str] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> Path | None:
    cover_url = download_plan.get("effectiveCoverUrl") or download_plan.get("aiCoverUrl") or download_plan.get("coverUrl")
    if not cover_url:
        return None
    if should_stop and should_stop():
        raise TaskCancelled("用户停止下载")
    target = target_dir / "fengmian.jpg"
    request = urllib.request.Request(resolve_download_url(str(cover_url), base_url), headers=headers or {})
    with urllib.request.urlopen(request) as response, target.open("wb") as output:
        while True:
            if should_stop and should_stop():
                raise TaskCancelled("用户停止下载")
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
    return target


def write_drama_metadata(download_plan: dict, target_dir: Path, cover_file: Path | None) -> Path:
    episodes = download_plan.get("episodes") or []
    metadata = {
        "dramaId": download_plan.get("dramaId"),
        "title": download_plan.get("title"),
        "aiTitle": download_plan.get("aiTitle"),
        "publishTitle": download_plan.get("aiTitle") or download_plan.get("title"),
        "summary": download_plan.get("summary"),
        "coverFile": cover_file.name if cover_file else None,
        "coverUrl": download_plan.get("effectiveCoverUrl") or download_plan.get("aiCoverUrl") or download_plan.get("coverUrl"),
        "rating": download_plan.get("rating"),
        "categoryIds": download_plan.get("categoryIds") or [],
        "episodeCount": len(episodes),
        "episodes": [
            {
                "episodeNo": episode.get("episodeNo"),
                "title": episode.get("title"),
                "sourcePath": episode.get("sourcePath"),
                "fileName": f"{int(episode['episodeNo']):03d}.mp4",
            }
            for episode in episodes
        ],
    }
    target = target_dir / "meta.json"
    target.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def resolve_download_url(url: str, base_url: str) -> str:
    if url.startswith("/"):
        return base_url.removesuffix("/api") + url
    return url


class TaskCancelled(RuntimeError):
    pass


def _content_length(response: object) -> int | None:
    headers = getattr(response, "headers", None)
    value = headers.get("Content-Length") if headers is not None else None
    if value is None and hasattr(response, "getheader"):
        value = response.getheader("Content-Length")
    try:
        return int(value) if value else None
    except ValueError:
        return None
