from __future__ import annotations

import random
import json
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from aidrama_desktop import __version__
from aidrama_desktop.api.client import ApiClient
from aidrama_desktop.contracts import (
    ContractRenderInput,
    render_contract_material_bundle,
)
from aidrama_desktop.platforms.base import PlatformPublisher
from aidrama_desktop.video.ffmpeg import FfmpegProcessor


DOWNLOAD_CHUNK_SIZE = 1024 * 1024
EPISODE_DOWNLOAD_RETRIES = 3
EPISODE_DOWNLOAD_RETRY_DELAY_SECONDS = 2.0
RETRYABLE_HTTP_STATUS_CODES = {401, 403, 408, 425, 429, 500, 502, 503, 504}
DOWNLOAD_PROGRESS_REPORT_INTERVAL_SECONDS = 10.0
BAIDU_DOWNLOAD_HEADERS = {
    "User-Agent": "pan.baidu.com",
    "Referer": "https://pan.baidu.com/",
}


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
    progress_callback: Callable[..., None] | None = None
    cancel_checker: Callable[[], bool] | None = None
    pause_checker: Callable[[], bool] | None = None
    skip_checker: Callable[[], bool] | None = None
    download_concurrency: int = 6
    contract_templates: dict[str, Path | str | None] | None = None
    contracts_dir: Path | None = None
    contract_platform: str = "WECHAT_VIDEO"
    contract_buyer: str = "甲方公司"
    contract_seller: str = "乙方公司"
    contract_image_converter: Callable[[Path, Path, str | None], list[Path]] | None = None

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

    def execute_task(self, task: dict | None) -> str:
        return self._execute_task(task)

    def _execute_task(self, task: dict | None) -> str:
        if not task:
            self._notify("空闲", None)
            return "no-task"
        task_id = task["id"]
        self._notify("任务已领取", task_id, task)
        try:
            self._progress(task_id, "DOWNLOADING", 10)
            download_plan = self.api.get(f"/desktop/dramas/{task['dramaId']}/download-plan")
            drama_title = self._drama_title(download_plan, task)
            task_with_title = {**task, "dramaTitle": drama_title}
            self._notify(f"当前短剧：{drama_title}", task_id, task_with_title)
            contract_metadata = self._prepare_contract_materials(download_plan, task_id, drama_title)
            source_files = self._download(download_plan, task_id, drama_title)
            raise_if_task_interrupted(self.cancel_checker, self.pause_checker, self.skip_checker)
            self._progress(task_id, "UPLOADING", 75)
            self._notify(f"发布：{drama_title}", task_id)
            metadata = self._publish_metadata(download_plan, source_files)
            metadata.update(contract_metadata)
            publish_id = self._publisher_for(task).publish(
                source_files,
                title=drama_title,
                summary=download_plan.get("summary"),
                metadata=metadata,
            )
            self.api.put(
                f"/desktop/tasks/{task_id}/result",
                {"success": True, "platformPublishId": publish_id, "failureReason": None},
            )
            self._notify("任务完成", task_id)
            return "succeeded"
        except Exception as exception:  # noqa: BLE001
            if isinstance(exception, TaskPaused):
                self.api.post(f"/desktop/tasks/{task_id}/pause", {"deviceId": self.device_id})
                self._notify("任务已暂停，可恢复执行", task_id, task)
                return "paused"
            if isinstance(exception, TaskSkipped):
                self.api.post(f"/desktop/tasks/{task_id}/skip", {"deviceId": self.device_id})
                self._notify("任务已跳过，已放回池里", task_id, task)
                return "skipped"
            if isinstance(exception, TaskCancelled):
                self.api.put(f"/desktop/tasks/{task_id}/progress", {"status": "CANCELLED", "progress": 0})
                self._notify("任务已停止，可重新分发", task_id, task)
                return "cancelled"
            self.api.put(
                f"/desktop/tasks/{task_id}/result",
                {"success": False, "platformPublishId": None, "failureReason": str(exception)},
            )
            self._notify(f"任务失败：{exception}", task_id, task)
            return "failed"

    def _progress(self, task_id: str, status: str, progress: int) -> None:
        self._notify(status, task_id)
        self.api.put(f"/desktop/tasks/{task_id}/progress", {"status": status, "progress": progress})

    def _publisher_for(self, task: dict) -> PlatformPublisher:
        media_account_id = task.get("mediaAccountId")
        if self.publisher_factory and media_account_id:
            return self.publisher_factory(str(media_account_id))
        return self.publisher

    def _prepare_contract_materials(self, download_plan: dict, task_id: str, drama_title: str) -> dict[str, object]:
        if self.contract_templates is None:
            return {}
        self._notify(f"生成合同材料：{drama_title}", task_id)
        output_dir = (self.contracts_dir or self.work_dir / "contracts") / "generated" / str(task_id)

        def data_factory(contract_type: str, label: str) -> ContractRenderInput:
            return self._contract_render_input(download_plan, drama_title, contract_type, label)

        bundle = render_contract_material_bundle(
            self.contract_templates,
            self.contract_platform,
            output_dir,
            data_factory,
            image_converter=self.contract_image_converter,
        )
        self._notify(f"合同材料已生成：{drama_title}", task_id)
        return bundle.metadata()

    def _contract_render_input(
        self,
        download_plan: dict,
        drama_title: str,
        contract_type: str,
        label: str,
    ) -> ContractRenderInput:
        episodes = download_plan.get("episodes") or []
        episode_count = self._int_value(download_plan.get("episodeCount"), len(episodes))
        episode_minutes = self._int_value(download_plan.get("totalMinutes"), episode_count)
        cost_amount_wan = self._int_value(download_plan.get("costAmountWan"), 0)
        return ContractRenderInput(
            contract_type=label,
            drama_title=drama_title,
            episode_count=str(episode_count),
            episode_minutes=str(episode_minutes),
            price=str(cost_amount_wan),
            buyer=self.contract_buyer or "甲方公司",
            seller=self.contract_seller or "乙方公司",
            sign_date=date.today().isoformat(),
        )

    @staticmethod
    def _int_value(value: object, default: int = 0) -> int:
        try:
            return max(int(float(str(value))), 0)
        except (TypeError, ValueError):
            return default

    def _notify(self, stage: str, task_id: str | None, task: dict | None = None) -> None:
        if self.progress_callback:
            self.progress_callback(stage, task_id, task)

    @staticmethod
    def _drama_title(download_plan: dict, task: dict) -> str:
        return str(download_plan.get("title") or task["dramaId"])

    def _download(self, download_plan: dict, task_id: str, drama_title: str) -> list[Path]:
        target_dir = self.input_dir() / download_plan["dramaId"]
        progress_lock = threading.Lock()
        downloaded_by_episode: dict[int, int] = {}
        total_by_episode = {
            index: episode_size(episode) or 0
            for index, episode in enumerate(download_plan.get("episodes") or [], start=1)
        }
        last_reported_at = 0.0
        last_reported_progress = 10

        def report_progress(index: int, total: int, episode: dict, downloaded: int, total_bytes: int | None) -> None:
            nonlocal last_reported_at, last_reported_progress
            self._notify(self._download_stage(drama_title, index, total, downloaded, total_bytes), task_id)
            now = time.monotonic()
            should_report = False
            progress = 10
            with progress_lock:
                downloaded_by_episode[index] = max(downloaded_by_episode.get(index, 0), downloaded)
                if total_bytes and total_bytes > 0:
                    total_by_episode[index] = max(total_by_episode.get(index, 0), total_bytes)
                known_total = sum(total_by_episode.values())
                if known_total > 0:
                    known_downloaded = sum(
                        min(downloaded_bytes, total_by_episode.get(episode_index, downloaded_bytes) or downloaded_bytes)
                        for episode_index, downloaded_bytes in downloaded_by_episode.items()
                    )
                    progress = min(70, max(10, 10 + int(known_downloaded * 60 / known_total)))
                if progress > last_reported_progress or now - last_reported_at >= DOWNLOAD_PROGRESS_REPORT_INTERVAL_SECONDS:
                    last_reported_progress = max(last_reported_progress, progress)
                    last_reported_at = now
                    should_report = True
            if should_report:
                try:
                    self.api.put(
                        f"/desktop/tasks/{task_id}/progress",
                        {"status": "DOWNLOADING", "progress": last_reported_progress},
                    )
                except Exception:
                    pass

        return download_episodes(
            download_plan,
            target_dir,
            self.api.base_url,
            headers=self.api.download_headers(),
            progress_callback=report_progress,
            should_stop=self.cancel_checker,
            should_pause=self.pause_checker,
            should_skip=self.skip_checker,
            max_concurrent_downloads=self.download_concurrency,
        )

    def _publish_metadata(self, download_plan: dict, processed_files: list[Path]) -> dict[str, Any]:
        episodes = download_plan.get("episodes") or []
        cover_file = self.input_dir() / str(download_plan["dramaId"]) / "fengmian.jpg"
        return {
            "dramaId": download_plan.get("dramaId"),
            "title": download_plan.get("title"),
            "aiTitle": download_plan.get("aiTitle"),
            "publishTitle": download_plan.get("aiTitle") or download_plan.get("title"),
            "summary": download_plan.get("summary"),
            "coverFile": cover_file if cover_file.exists() else None,
            "coverUrl": download_plan.get("effectiveCoverUrl") or download_plan.get("aiCoverUrl") or download_plan.get("coverUrl"),
            "rating": download_plan.get("rating"),
            "categoryIds": download_plan.get("categoryIds") or [],
            "totalMinutes": download_plan.get("totalMinutes"),
            "costAmountWan": download_plan.get("costAmountWan"),
            "monetizationType": "IAA_AD",
            "monetizationLabel": "IAA广告变现",
            "freeEpisodeCount": random.randint(3, 10),
            "episodeCount": len(episodes),
            "episodes": [
                {
                    "episodeNo": episode.get("episodeNo"),
                    "title": episode.get("title"),
                    "file": processed_files[index],
                }
                for index, episode in enumerate(episodes)
                if index < len(processed_files)
            ],
        }

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
    should_pause: Callable[[], bool] | None = None,
    should_skip: Callable[[], bool] | None = None,
    max_concurrent_downloads: int = 6,
    episode_retry_count: int = EPISODE_DOWNLOAD_RETRIES,
    retry_delay_seconds: float = EPISODE_DOWNLOAD_RETRY_DELAY_SECONDS,
) -> list[Path]:
    target_dir.mkdir(parents=True, exist_ok=True)
    cover_file = download_cover(
        download_plan,
        target_dir,
        base_url,
        headers=headers,
        should_stop=should_stop,
        should_pause=should_pause,
        should_skip=should_skip,
    )
    write_drama_metadata(download_plan, target_dir, cover_file)
    episodes = download_plan["episodes"]
    total = len(episodes)
    if not episodes:
        return []

    worker_count = max(1, min(max_concurrent_downloads, total))
    files: list[Path | None] = [None] * total
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                download_episode,
                episode,
                index,
                total,
                target_dir,
                base_url,
                headers,
                progress_callback,
                should_stop,
                should_pause,
                should_skip,
                episode_retry_count,
                retry_delay_seconds,
            ): index
            for index, episode in enumerate(episodes, start=1)
        }
        for future in as_completed(futures):
            index = futures[future]
            files[index - 1] = future.result()
    return [file for file in files if file is not None]


def download_episode(
    episode: dict,
    index: int,
    total: int,
    target_dir: Path,
    base_url: str,
    headers: dict[str, str] | None,
    progress_callback: Callable[[int, int, dict, int, int | None], None] | None,
    should_stop: Callable[[], bool] | None,
    should_pause: Callable[[], bool] | None,
    should_skip: Callable[[], bool] | None,
    retry_count: int = EPISODE_DOWNLOAD_RETRIES,
    retry_delay_seconds: float = EPISODE_DOWNLOAD_RETRY_DELAY_SECONDS,
) -> Path:
    raise_if_task_interrupted(should_stop, should_pause, should_skip)
    target = target_dir / f"{episode['episodeNo']:03d}.mp4"
    if is_complete_episode_file(target, episode):
        if progress_callback:
            downloaded = target.stat().st_size
            progress_callback(index, total, episode, downloaded, episode_size(episode) or downloaded)
        return target

    part_file = target.with_name(f"{target.name}.part")
    attempts = max(1, retry_count)
    last_exception: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            raise_if_task_interrupted(should_stop, should_pause, should_skip)
        except TaskInterrupted:
            cleanup_part_file(part_file)
            raise
        try:
            cleanup_part_file(part_file)
            download_episode_attempt(
                episode,
                index,
                total,
                part_file,
                base_url,
                headers,
                progress_callback,
                should_stop,
                should_pause,
                should_skip,
            )
            if not is_downloaded_file_complete(part_file, episode):
                expected_size = episode_size(episode)
                actual_size = part_file.stat().st_size if part_file.exists() else 0
                raise RuntimeError(f"第 {episode['episodeNo']} 集下载不完整：{actual_size}/{expected_size} bytes")
            part_file.replace(target)
            return target
        except TaskInterrupted:
            cleanup_part_file(part_file)
            raise
        except Exception as exception:  # noqa: BLE001
            last_exception = exception
            cleanup_part_file(part_file)
            if attempt >= attempts or not is_retryable_download_error(exception):
                break
            sleep_before_retry(retry_delay_seconds, should_stop, should_pause, should_skip)
    if last_exception:
        raise last_exception
    raise RuntimeError(f"第 {episode['episodeNo']} 集下载失败")


def download_episode_attempt(
    episode: dict,
    index: int,
    total: int,
    target: Path,
    base_url: str,
    headers: dict[str, str] | None,
    progress_callback: Callable[[int, int, dict, int, int | None], None] | None,
    should_stop: Callable[[], bool] | None,
    should_pause: Callable[[], bool] | None,
    should_skip: Callable[[], bool] | None,
) -> None:
    url = resolve_download_url(str(episode["downloadUrl"]), base_url)
    request = urllib.request.Request(url, headers=episode_download_headers(headers))
    with urllib.request.urlopen(request) as response, target.open("wb") as output:
        total_bytes = _content_length(response) or episode_size(episode)
        downloaded = 0
        while True:
            raise_if_task_interrupted(should_stop, should_pause, should_skip)
            chunk = response.read(DOWNLOAD_CHUNK_SIZE)
            if not chunk:
                break
            output.write(chunk)
            downloaded += len(chunk)
            if progress_callback:
                progress_callback(index, total, episode, downloaded, total_bytes)


def episode_download_headers(headers: dict[str, str] | None) -> dict[str, str]:
    merged = dict(headers or {})
    merged.update(BAIDU_DOWNLOAD_HEADERS)
    return merged


def episode_size(episode: dict) -> int | None:
    try:
        size = int(episode.get("size") or 0)
    except (TypeError, ValueError):
        return None
    return size if size > 0 else None


def is_complete_episode_file(target: Path, episode: dict) -> bool:
    return target.exists() and target.is_file() and is_downloaded_file_complete(target, episode)


def is_downloaded_file_complete(target: Path, episode: dict) -> bool:
    if not target.exists() or not target.is_file():
        return False
    actual_size = target.stat().st_size
    expected_size = episode_size(episode)
    if expected_size:
        return actual_size >= expected_size
    return actual_size > 0


def cleanup_part_file(part_file: Path) -> None:
    try:
        if part_file.exists():
            part_file.unlink()
    except OSError:
        pass


def is_retryable_download_error(exception: BaseException) -> bool:
    if isinstance(exception, urllib.error.HTTPError):
        return exception.code in RETRYABLE_HTTP_STATUS_CODES
    if isinstance(exception, urllib.error.URLError):
        return True
    if isinstance(exception, TimeoutError):
        return True
    return False


def sleep_before_retry(
    delay_seconds: float,
    should_stop: Callable[[], bool] | None,
    should_pause: Callable[[], bool] | None = None,
    should_skip: Callable[[], bool] | None = None,
) -> None:
    deadline = time.monotonic() + max(delay_seconds, 0)
    while time.monotonic() < deadline:
        raise_if_task_interrupted(should_stop, should_pause, should_skip)
        remaining = max(deadline - time.monotonic(), 0)
        time.sleep(min(0.2, remaining))


def download_cover(
    download_plan: dict,
    target_dir: Path,
    base_url: str,
    headers: dict[str, str] | None = None,
    should_stop: Callable[[], bool] | None = None,
    should_pause: Callable[[], bool] | None = None,
    should_skip: Callable[[], bool] | None = None,
) -> Path | None:
    cover_url = download_plan.get("effectiveCoverUrl") or download_plan.get("aiCoverUrl") or download_plan.get("coverUrl")
    if not cover_url:
        return None
    raise_if_task_interrupted(should_stop, should_pause, should_skip)
    target = target_dir / "fengmian.jpg"
    request = urllib.request.Request(resolve_download_url(str(cover_url), base_url), headers=episode_download_headers(headers))
    with urllib.request.urlopen(request) as response, target.open("wb") as output:
        while True:
            raise_if_task_interrupted(should_stop, should_pause, should_skip)
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
        "totalMinutes": download_plan.get("totalMinutes"),
        "costAmountWan": download_plan.get("costAmountWan"),
        "episodeCount": len(episodes),
        "episodes": [
            {
                "episodeNo": episode.get("episodeNo"),
                "title": episode.get("title"),
                "sourcePath": episode.get("sourcePath"),
                "size": episode.get("size"),
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


class TaskInterrupted(RuntimeError):
    pass


class TaskCancelled(TaskInterrupted):
    pass


class TaskPaused(TaskInterrupted):
    pass


class TaskSkipped(TaskInterrupted):
    pass


def raise_if_task_interrupted(
    should_stop: Callable[[], bool] | None,
    should_pause: Callable[[], bool] | None = None,
    should_skip: Callable[[], bool] | None = None,
) -> None:
    if should_skip and should_skip():
        raise TaskSkipped("用户跳过任务")
    if should_pause and should_pause():
        raise TaskPaused("用户暂停任务")
    if should_stop and should_stop():
        raise TaskCancelled("用户停止下载")


def _content_length(response: object) -> int | None:
    headers = getattr(response, "headers", None)
    value = headers.get("Content-Length") if headers is not None else None
    if value is None and hasattr(response, "getheader"):
        value = response.getheader("Content-Length")
    try:
        return int(value) if value else None
    except ValueError:
        return None
