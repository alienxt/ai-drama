from __future__ import annotations

import json
import inspect
import re
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from aidrama_desktop import __version__
from aidrama_desktop.api.client import ApiClient
from aidrama_desktop.contracts import (
    ContractRenderInput,
    generate_contract_start_date,
    generate_agreement_number,
    render_contract_material_bundle,
)
from aidrama_desktop.platforms.base import PlatformPublisher, PlatformPublishPaused
from aidrama_desktop.video.ffmpeg import (
    FfmpegProcessor,
    WECHAT_VIDEO_COVER_FRAME_VERSION,
    WECHAT_VIDEO_MIN_HEIGHT,
    WECHAT_VIDEO_MIN_WIDTH,
)


DOWNLOAD_CHUNK_SIZE = 1024 * 1024
EPISODE_DOWNLOAD_RETRIES = 3
EPISODE_DOWNLOAD_RETRY_DELAY_SECONDS = 2.0
RETRYABLE_HTTP_STATUS_CODES = {401, 403, 408, 425, 429, 500, 502, 503, 504}
NON_RETRYABLE_DOWNLOAD_ERROR_CODES = {"HONGGUO_VIDEO_EMPTY"}
DOWNLOAD_PROGRESS_REPORT_INTERVAL_SECONDS = 10.0
TASK_PREPARATION_POLL_INTERVAL_SECONDS = 3.0
TASK_PREPARATION_TIMEOUT_SECONDS = 10 * 60.0
MAX_SKIPPED_EPISODE_FAILURES = 3
WECHAT_VIDEO_MIN_EPISODE_DURATION_SECONDS = 30.0
TIKTOK_MIN_EPISODE_DURATION_SECONDS = 15.0
TIKTOK_MAX_EPISODE_COUNT = 120
TIKTOK_MIN_VIDEO_SIZE_BYTES = 5 * 1024 * 1024
TIKTOK_MAX_VIDEO_SIZE_BYTES = 4 * 1024 * 1024 * 1024
TIKTOK_EPISODE_MERGE_VERSION = "tiktok-episode-merge-v1"
TIKTOK_COVER_FILENAME = "tiktok-cover-en.jpg"
TIKTOK_COVER_WIDTH = 768
TIKTOK_COVER_HEIGHT = 1024
TIKTOK_COVER_MAX_BYTES = 10 * 1024 * 1024
BAIDU_DOWNLOAD_HEADERS = {
    "User-Agent": "pan.baidu.com",
    "Referer": "https://pan.baidu.com/",
}
FILENAME_EDGE_CHARS = " ._-—–·，,。.!！?？、:：;；《》<>【】[]()（）"
INVALID_FILENAME_CHARS_RE = re.compile(r'[\\/:*?"<>|\r\n\t]+')


class DownloadHttpError(RuntimeError):
    def __init__(
        self,
        episode_no: int,
        status_code: int,
        reason: str,
        error_code: str | None = None,
        error_message: str | None = None,
    ):
        self.episode_no = episode_no
        self.status_code = status_code
        self.reason = reason
        self.error_code = error_code
        self.error_message = error_message
        message = error_message or f"HTTP {status_code}: {reason}"
        if error_code:
            message = f"{message}（{error_code}）"
        super().__init__(f"第 {episode_no} 集下载失败：{message}")


@dataclass
class EpisodeMediaFile:
    episode: dict[str, Any]
    episode_index: int
    file: Path
    source_episode_indexes: tuple[int, ...] | None = None


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
    max_skipped_episode_failures: int = MAX_SKIPPED_EPISODE_FAILURES
    contract_templates: dict[str, Path | str | None] | None = None
    contracts_dir: Path | None = None
    contract_platform: str = "WECHAT_VIDEO"
    contract_buyer: str = "甲方公司"
    contract_seller: str = "乙方公司"
    contract_image_converter: Callable[[Path, Path, str | None], list[Path]] | None = None
    soffice_path: str | None = None

    def heartbeat(self) -> None:
        self.api.post(
            "/desktop/devices/heartbeat",
            {"deviceId": self.device_id, "appVersion": __version__, "osName": "desktop", "idle": True},
        )

    def run_once(self) -> str:
        task = self.api.post("/desktop/tasks/claim", self._claim_payload())
        return self._execute_task(task)

    def publish_once(self) -> str:
        task = self.api.post("/desktop/tasks/publish-next", self._claim_payload())
        return self._execute_task(task)

    def execute_task(self, task: dict | None) -> str:
        return self._execute_task(task)

    def refill_task_form_from_cache(self, task: dict | None) -> str:
        if not task:
            self._notify("重填表单失败：任务为空", None)
            return "no-task"
        task_id = str(task["id"])
        platform = self._task_platform(task)
        if platform != "TIKTOK":
            raise RuntimeError("当前只支持 TK 任务从本地缓存重填表单。")
        download_plan = self.api.get(f"/desktop/dramas/{task['dramaId']}/download-plan")
        drama_title = self._drama_title(download_plan, task)
        task_with_title = {**task, "dramaTitle": drama_title}
        self._notify(f"重填TK表单：{drama_title}", task_id, task_with_title)
        upload_items = self._cached_upload_items(download_plan, platform)
        if not upload_items:
            raise RuntimeError("没有找到本地 TK 上传缓存，请先完整执行一次任务生成 TK 合并视频。")
        effective_download_plan = self._effective_download_plan(download_plan, upload_items)
        contract_metadata = self._prepare_contract_materials(
            effective_download_plan,
            task_id,
            drama_title,
            platform=platform,
        )
        metadata = self._publish_metadata(effective_download_plan, upload_items, platform=platform)
        metadata.update(contract_metadata)
        publish_title = str(metadata.get("publishTitle") or drama_title)
        publish_summary = metadata.get("publishSummary")
        try:
            self._publisher_for(task).publish(
                [item.file for item in upload_items],
                title=publish_title,
                summary=str(publish_summary) if publish_summary else None,
                metadata=metadata,
            )
        except PlatformPublishPaused as exception:
            self._notify(str(exception) or "TK 表单已重填并停留在提交前", task_id, task_with_title)
            return "ready-for-review"
        self._notify("TK 表单重填完成", task_id, task_with_title)
        return "succeeded"

    def _execute_task(self, task: dict | None) -> str:
        if not task:
            self._notify("空闲", None)
            return "no-task"
        task_id = task["id"]
        platform = self._task_platform(task)
        self._notify("任务已领取", task_id, task)
        try:
            self._wait_for_task_preparation(task)
            self._progress(task_id, "DOWNLOADING", 10)
            download_plan = self.api.get(f"/desktop/dramas/{task['dramaId']}/download-plan")
            drama_title = self._drama_title(download_plan, task)
            task_with_title = {**task, "dramaTitle": drama_title}
            self._notify(f"当前短剧：{drama_title}", task_id, task_with_title)
            source_items = self._download(download_plan, task_id, drama_title)
            raise_if_task_interrupted(self.cancel_checker, self.pause_checker, self.skip_checker)
            self._progress(task_id, "PROCESSING", 70)
            source_items = self._prepare_source_items_for_platform(source_items, task_id, drama_title, platform)
            upload_items = self._prepare_media_files_for_upload(
                source_items,
                task_id,
                drama_title,
                original_episode_count=len(download_plan.get("episodes") or []),
                platform=platform,
            )
            upload_items = self._filter_upload_items_for_platform(upload_items, task_id, drama_title, platform)
            raise_if_task_interrupted(self.cancel_checker, self.pause_checker, self.skip_checker)
            if not upload_items:
                raise RuntimeError("没有可上传的剧集，整部剧分发失败。")
            effective_download_plan = self._effective_download_plan(download_plan, upload_items)
            contract_metadata = (
                self._prepare_contract_materials(effective_download_plan, task_id, drama_title, platform=platform)
                if self._requires_contract_materials(platform)
                else {}
            )
            self._progress(task_id, "UPLOADING", 75)
            self._notify(f"发布：{drama_title}", task_id)
            metadata = self._publish_metadata(effective_download_plan, upload_items, platform=platform)
            metadata.update(contract_metadata)
            publish_title = str(metadata.get("publishTitle") or drama_title)
            publish_summary = metadata.get("publishSummary")
            publish_id = self._publisher_for(task).publish(
                [item.file for item in upload_items],
                title=publish_title,
                summary=str(publish_summary) if publish_summary else None,
                metadata=metadata,
            )
            result_task = self.api.put(
                f"/desktop/tasks/{task_id}/result",
                {"success": True, "platformPublishId": publish_id, "failureReason": None},
            )
            if self._is_cancelled_result(result_task):
                self._notify("任务已停止，可重新分发", task_id, task)
                return "cancelled"
            self._notify("任务完成", task_id)
            return "succeeded"
        except Exception as exception:  # noqa: BLE001
            if isinstance(exception, PlatformPublishPaused):
                failure_reason = str(exception) or "剧目提审表单停留在第一页，未完成上传提交。"
                result_task = self.api.put(
                    f"/desktop/tasks/{task_id}/result",
                    {"success": False, "platformPublishId": None, "failureReason": failure_reason},
                )
                if self._is_cancelled_result(result_task):
                    self._notify("任务已停止，可重新分发", task_id, task)
                    return "cancelled"
                self._notify(f"上传失败：{failure_reason}", task_id, task)
                return "failed"
            if isinstance(exception, TaskPaused):
                self.api.post(f"/desktop/tasks/{task_id}/pause", {"deviceId": self.device_id})
                self._notify("任务已暂停，可恢复执行", task_id, task)
                return "paused"
            if isinstance(exception, TaskSkipped):
                self.api.post(f"/desktop/tasks/{task_id}/skip", {"deviceId": self.device_id})
                self._notify("任务已跳过，已放回池里", task_id, task)
                return "skipped"
            if isinstance(exception, TaskCancelled):
                self.api.post(f"/desktop/tasks/{task_id}/force-stop")
                self._notify("任务已停止，可重新分发", task_id, task)
                return "cancelled"
            result_task = self.api.put(
                f"/desktop/tasks/{task_id}/result",
                {"success": False, "platformPublishId": None, "failureReason": str(exception)},
            )
            if self._is_cancelled_result(result_task):
                self._notify("任务已停止，可重新分发", task_id, task)
                return "cancelled"
            self._notify(f"任务失败：{exception}", task_id, task)
            return "failed"

    def _claim_payload(self) -> dict[str, Any]:
        return {"deviceId": self.device_id, "asyncPreparation": True}

    def _wait_for_task_preparation(self, task: dict) -> None:
        task_id = str(task["id"])
        self._notify("准备AI素材", task_id, task)
        deadline = time.monotonic() + TASK_PREPARATION_TIMEOUT_SECONDS
        last_message = ""
        while True:
            raise_if_task_interrupted(self.cancel_checker, self.pause_checker, self.skip_checker)
            response = self.api.post(f"/desktop/tasks/{task_id}/prepare")
            if response.get("prepared"):
                self._notify("AI素材准备完成", task_id, task)
                return
            if response.get("failed"):
                message = str(response.get("message") or "AI 素材准备失败，请稍后重试。")
                raise RuntimeError(message)
            message = str(response.get("message") or "AI 素材准备中，请稍候")
            if message != last_message:
                self._notify(message, task_id, task)
                last_message = message
            if time.monotonic() >= deadline:
                raise RuntimeError("AI 素材准备超时，请稍后刷新任务状态后重试。")
            try:
                retry_after = float(response.get("retryAfterSeconds") or TASK_PREPARATION_POLL_INTERVAL_SECONDS)
            except (TypeError, ValueError):
                retry_after = TASK_PREPARATION_POLL_INTERVAL_SECONDS
            time.sleep(max(1.0, min(retry_after, 10.0)))

    def _progress(self, task_id: str, status: str, progress: int) -> None:
        self._notify(status, task_id)
        self.api.put(f"/desktop/tasks/{task_id}/progress", {"status": status, "progress": progress})

    @staticmethod
    def _is_cancelled_result(task: Any) -> bool:
        return isinstance(task, dict) and task.get("status") == "CANCELLED"

    def _publisher_for(self, task: dict) -> PlatformPublisher:
        media_account_id = task.get("mediaAccountId")
        if self.publisher_factory and media_account_id:
            return self.publisher_factory(str(media_account_id))
        return self.publisher

    @staticmethod
    def _task_platform(task: dict) -> str:
        return str(task.get("platform") or task.get("mediaPlatform") or "WECHAT_VIDEO").strip() or "WECHAT_VIDEO"

    @staticmethod
    def _requires_contract_materials(platform: str) -> bool:
        return platform in {"WECHAT_VIDEO", "TIKTOK"}

    def _prepare_contract_materials(
        self,
        download_plan: dict,
        task_id: str,
        drama_title: str,
        *,
        platform: str,
    ) -> dict[str, object]:
        if self.contract_templates is None:
            return {}
        material_label = "TK合作协议" if platform == "TIKTOK" else "合同材料"
        self._notify(f"生成{material_label}：{drama_title}", task_id)
        output_dir = (self.contracts_dir or self.work_dir / "contracts") / "generated" / str(task_id)
        sign_date = (date.today() - timedelta(days=1)).isoformat()
        start_date = generate_contract_start_date(sign_date)
        agreement_number = generate_agreement_number(sign_date)

        def data_factory(contract_type: str, label: str) -> ContractRenderInput:
            return self._contract_render_input(
                download_plan,
                drama_title,
                contract_type,
                label,
                agreement_number,
                sign_date,
                start_date,
            )

        bundle = render_contract_material_bundle(
            self.contract_templates,
            platform,
            output_dir,
            data_factory,
            image_converter=self.contract_image_converter,
            soffice_path=self.soffice_path,
        )
        self._notify(f"{material_label}已生成：{drama_title}", task_id)
        return bundle.metadata()

    def _contract_render_input(
        self,
        download_plan: dict,
        drama_title: str,
        contract_type: str,
        label: str,
        agreement_number: str,
        sign_date: str,
        start_date: str,
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
            sign_date=sign_date,
            start_date=start_date,
            agreement_number=agreement_number,
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

    def _download(self, download_plan: dict, task_id: str, drama_title: str) -> list[EpisodeMediaFile]:
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

        def report_skipped(index: int, total: int, episode: dict, exception: BaseException) -> None:
            episode_no = episode_number(episode, index)
            self._notify(
                f"跳过：{drama_title} 第 {episode_no} 集下载失败（最多允许 {self.max_skipped_episode_failures} 集）：{exception}",
                task_id,
            )

        kwargs: dict[str, Any] = {
            "headers": self.api.download_headers(),
            "progress_callback": report_progress,
            "should_stop": self.cancel_checker,
            "should_pause": self.pause_checker,
            "should_skip": self.skip_checker,
            "max_concurrent_downloads": self.download_concurrency,
        }
        download_parameters = inspect.signature(download_episodes).parameters
        if "max_skipped_episodes" in download_parameters:
            kwargs["max_skipped_episodes"] = self.max_skipped_episode_failures
            kwargs["skip_callback"] = report_skipped
        source_files = download_episodes(download_plan, target_dir, self.api.base_url, **kwargs)
        media_items = self._episode_media_files_from_paths(download_plan, source_files)
        skipped_count = len(download_plan.get("episodes") or []) - len(media_items)
        if skipped_count > 0:
            self._notify(f"已跳过 {skipped_count} 集下载失败剧集，继续处理 {len(media_items)} 集", task_id)
        return media_items

    def _prepare_source_items_for_platform(
        self,
        source_items: list[EpisodeMediaFile],
        task_id: str,
        drama_title: str,
        platform: str,
    ) -> list[EpisodeMediaFile]:
        if platform == "TIKTOK" and len(source_items) > TIKTOK_MAX_EPISODE_COUNT:
            return self._merge_tiktok_episode_items(source_items, task_id, drama_title)
        return source_items

    def _prepare_media_files_for_upload(
        self,
        source_items: list[EpisodeMediaFile],
        task_id: str,
        drama_title: str,
        original_episode_count: int,
        platform: str = "WECHAT_VIDEO",
    ) -> list[EpisodeMediaFile]:
        single_transcode = getattr(self.processor, "transcode_for_wechat_video", None)
        if not callable(single_transcode):
            return source_items
        cover_file = self._cover_file_for_sources([item.file for item in source_items])
        upload_items: list[EpisodeMediaFile] = []
        processed_count = 0
        skipped_count = self._covered_source_skipped_count(original_episode_count, source_items)
        last_skip_message: str | None = None
        for item in source_items:
            raise_if_task_interrupted(self.cancel_checker, self.pause_checker, self.skip_checker)
            source_file = item.file
            episode_no = episode_number(item.episode, item.episode_index)
            duration_seconds = self._video_duration_seconds(source_file)
            min_duration_seconds = self._platform_min_episode_duration_seconds(platform)
            if duration_seconds is not None and min_duration_seconds and duration_seconds < min_duration_seconds:
                skipped_count += 1
                message = (
                    f"第 {episode_no} 集视频时长 {duration_seconds:.1f} 秒，小于"
                    f"{self._platform_duration_rule_label(platform)}要求的 {min_duration_seconds:.0f} 秒，已跳过该集；"
                    f"已跳过 {skipped_count}/{self.max_skipped_episode_failures} 集"
                )
                last_skip_message = message
                if skipped_count > self.max_skipped_episode_failures:
                    raise RuntimeError(
                        f"剧集失败超过 {self.max_skipped_episode_failures} 集，整部剧分发失败。最后错误：{message}"
                    )
                self._notify(f"跳过：{drama_title} {message}", task_id)
                continue
            source_needs_transcode = self._needs_wechat_video_transcode(source_file)
            source_needs_bitrate_transcode = self._needs_wechat_video_bitrate_transcode(source_file)
            source_needs_resolution_transcode = self._needs_wechat_video_resolution_transcode(source_file)
            should_add_cover_frame = cover_file is not None
            if not source_needs_transcode and not should_add_cover_frame:
                upload_items.append(item)
                continue
            processed_count += 1
            target = self._processed_media_target(source_file)
            signature = self._processed_media_signature(source_file, cover_file)
            target_needs_transcode = self._needs_wechat_video_transcode(target)
            if self._is_ready_upload_file(target) and self._processed_media_signature_matches(target, signature) and not target_needs_transcode:
                upload_items.append(EpisodeMediaFile(item.episode, item.episode_index, target, item.source_episode_indexes))
                continue
            action_parts = []
            if source_needs_bitrate_transcode:
                action_parts.append("提升码率")
            if source_needs_resolution_transcode:
                action_parts.append("提升分辨率")
            elif source_needs_transcode:
                action_parts.append("规范分辨率")
            if should_add_cover_frame:
                action_parts.append("添加封面帧")
            action = "、".join(action_parts) or "统一转码"
            self._notify(f"转码：{drama_title} 第 {episode_no} 集（{action}）", task_id)
            try:
                processed_file = single_transcode(source_file, target, cover_path=cover_file)
                self._write_processed_media_signature(processed_file, signature)
                upload_items.append(EpisodeMediaFile(item.episode, item.episode_index, processed_file, item.source_episode_indexes))
            except Exception as exception:  # noqa: BLE001
                self._cleanup_failed_media_file(target)
                self._cleanup_failed_media_file(self._processed_media_signature_path(target))
                self._cleanup_failed_media_file(source_file)
                skipped_count += 1
                message = (
                    f"第 {episode_no} 集视频转码失败，已跳过该集并清理本地缓存；"
                    f"已跳过 {skipped_count}/{self.max_skipped_episode_failures} 集：{exception}"
                )
                last_skip_message = message
                if skipped_count > self.max_skipped_episode_failures:
                    raise RuntimeError(
                        f"剧集失败超过 {self.max_skipped_episode_failures} 集，整部剧分发失败。最后错误：{message}"
                    ) from exception
                self._notify(f"跳过：{drama_title} {message}", task_id)
        if not upload_items and last_skip_message:
            raise RuntimeError(f"没有可上传的剧集：{last_skip_message}")
        if processed_count:
            label = "视频转码和封面帧处理完成" if cover_file else "视频转码处理完成"
            self._notify(f"{label}：{drama_title}（{processed_count} 集）", task_id)
        return upload_items

    def _needs_wechat_video_transcode(self, source_file: Path) -> bool:
        needs_transcode = getattr(self.processor, "needs_wechat_video_transcode", None)
        if callable(needs_transcode):
            try:
                return bool(needs_transcode(source_file))
            except Exception:  # noqa: BLE001
                return False
        return self._needs_wechat_video_bitrate_transcode(source_file) or self._needs_wechat_video_resolution_transcode(source_file)

    def _needs_wechat_video_bitrate_transcode(self, source_file: Path) -> bool:
        needs_bitrate = getattr(self.processor, "needs_wechat_video_bitrate_transcode", None)
        if not callable(needs_bitrate):
            return False
        try:
            return bool(needs_bitrate(source_file))
        except Exception:  # noqa: BLE001
            return False

    def _needs_wechat_video_resolution_transcode(self, source_file: Path) -> bool:
        needs_resolution = getattr(self.processor, "needs_wechat_video_resolution_transcode", None)
        if callable(needs_resolution):
            try:
                return bool(needs_resolution(source_file))
            except Exception:  # noqa: BLE001
                return False
        dimensions = self._video_dimensions(source_file)
        if not dimensions:
            return False
        width, height = dimensions
        return width < WECHAT_VIDEO_MIN_WIDTH or height < WECHAT_VIDEO_MIN_HEIGHT

    @staticmethod
    def _covered_source_skipped_count(original_episode_count: int, source_items: list[EpisodeMediaFile]) -> int:
        covered_indexes = {
            source_index
            for item in source_items
            for source_index in (item.source_episode_indexes or (item.episode_index,))
        }
        return max(original_episode_count - len(covered_indexes), 0)

    @staticmethod
    def _platform_min_episode_duration_seconds(platform: str) -> float:
        if platform == "TIKTOK":
            return TIKTOK_MIN_EPISODE_DURATION_SECONDS
        return WECHAT_VIDEO_MIN_EPISODE_DURATION_SECONDS

    @staticmethod
    def _platform_duration_rule_label(platform: str) -> str:
        if platform == "TIKTOK":
            return "TK"
        return "视频号"

    def _filter_upload_items_for_platform(
        self,
        media_items: list[EpisodeMediaFile],
        task_id: str,
        drama_title: str,
        platform: str,
    ) -> list[EpisodeMediaFile]:
        if platform != "TIKTOK":
            return media_items
        if len(media_items) > TIKTOK_MAX_EPISODE_COUNT:
            media_items = self._merge_tiktok_episode_items(media_items, task_id, drama_title)
        accepted: list[EpisodeMediaFile] = []
        skipped = 0
        last_reason = ""
        for item in media_items:
            size = item.file.stat().st_size if item.file.exists() else 0
            if size < TIKTOK_MIN_VIDEO_SIZE_BYTES or size > TIKTOK_MAX_VIDEO_SIZE_BYTES:
                skipped += 1
                episode_no = episode_number(item.episode, item.episode_index)
                size_mb = size / 1024 / 1024
                if size < TIKTOK_MIN_VIDEO_SIZE_BYTES:
                    last_reason = f"第 {episode_no} 集文件 {size_mb:.1f} MB，小于 TK 要求的 5 MB"
                else:
                    last_reason = f"第 {episode_no} 集文件 {size_mb:.1f} MB，超过 TK 要求的 4 GB"
                self._notify(f"跳过：{drama_title} {last_reason}", task_id)
                if skipped > self.max_skipped_episode_failures:
                    raise RuntimeError(
                        f"剧集失败超过 {self.max_skipped_episode_failures} 集，整部剧分发失败。最后错误：{last_reason}"
                    )
                continue
            accepted.append(item)
        if not accepted and last_reason:
            raise RuntimeError(f"没有可上传的剧集：{last_reason}")
        return accepted

    def _merge_tiktok_episode_items(
        self,
        media_items: list[EpisodeMediaFile],
        task_id: str,
        drama_title: str,
    ) -> list[EpisodeMediaFile]:
        groups = self._tiktok_episode_merge_groups(media_items)
        if len(groups) > TIKTOK_MAX_EPISODE_COUNT:
            raise RuntimeError(
                f"TK 单部短剧最多上传 {TIKTOK_MAX_EPISODE_COUNT} 个视频；"
                f"当前 {len(media_items)} 集按两集合并后仍有 {len(groups)} 个视频。"
            )
        merge_videos = getattr(self.processor, "merge_videos_for_tiktok", None)
        if not callable(merge_videos):
            raise RuntimeError("当前 FFmpeg 处理器不支持 TK 剧集合并，请升级客户端后重试。")
        source_dir = media_items[0].file.parent
        target_dir = source_dir if source_dir.name == "TK" else source_dir / "TK"
        target_dir.mkdir(parents=True, exist_ok=True)
        total_groups = len(groups)
        merged_items: list[EpisodeMediaFile] = []
        for output_index, group in enumerate(groups, start=1):
            raise_if_task_interrupted(self.cancel_checker, self.pause_checker, self.skip_checker)
            target = target_dir / self._tiktok_merged_episode_filename(drama_title, output_index)
            signature = self._tiktok_episode_merge_signature(group)
            if self._is_ready_upload_file(target) and self._processed_media_signature_matches(target, signature):
                merged_file = target
            else:
                range_label = self._episode_range_label(group)
                self._notify(f"合并TK剧集：{drama_title} 原第 {range_label} 集 -> 第 {output_index}/{total_groups} 集", task_id)
                try:
                    merged_file = merge_videos([item.file for item in group], target)
                    self._write_processed_media_signature(merged_file, signature)
                except Exception as exception:  # noqa: BLE001
                    self._cleanup_failed_media_file(target)
                    self._cleanup_failed_media_file(self._processed_media_signature_path(target))
                    raise RuntimeError(f"TK 剧集合并失败：原第 {range_label} 集：{exception}") from exception
            source_indexes = tuple(
                source_index
                for item in group
                for source_index in (item.source_episode_indexes or (item.episode_index,))
            )
            merged_items.append(
                EpisodeMediaFile(
                    self._tiktok_merged_episode_metadata(group, output_index),
                    group[0].episode_index,
                    merged_file,
                    source_indexes,
                )
            )
        self._notify(f"TK剧集合并完成：{drama_title}（{len(media_items)} 集 -> {len(merged_items)} 集）", task_id)
        return merged_items

    @staticmethod
    def _tiktok_episode_merge_groups(media_items: list[EpisodeMediaFile]) -> list[list[EpisodeMediaFile]]:
        if len(media_items) <= TIKTOK_MAX_EPISODE_COUNT:
            return [[item] for item in media_items]
        groups: list[list[EpisodeMediaFile]] = []
        pair_limit = len(media_items) - 3 if len(media_items) % 2 == 1 else len(media_items)
        for index in range(0, pair_limit, 2):
            groups.append(media_items[index : index + 2])
        if len(media_items) % 2 == 1:
            groups.append(media_items[-3:])
        return groups

    @staticmethod
    def _tiktok_episode_merge_signature(group: list[EpisodeMediaFile]) -> dict[str, Any]:
        sources = []
        for item in group:
            stat = item.file.stat()
            sources.append(
                {
                    "path": str(item.file),
                    "size": stat.st_size,
                    "mtimeNs": stat.st_mtime_ns,
                    "episodeIndex": item.episode_index,
                    "sourceEpisodeIndexes": list(item.source_episode_indexes or (item.episode_index,)),
                }
            )
        return {"version": TIKTOK_EPISODE_MERGE_VERSION, "sources": sources}

    @staticmethod
    def _tiktok_merged_episode_filename(drama_title: str, output_index: int) -> str:
        drama_name = safe_episode_drama_name(drama_title) or "短剧"
        return f"{drama_name}-TK第{output_index:03d}集.mp4"

    @staticmethod
    def _tiktok_merged_episode_metadata(group: list[EpisodeMediaFile], output_index: int) -> dict[str, Any]:
        source_episode_numbers = [episode_number(item.episode, item.episode_index) for item in group]
        source_range = TaskRunner._episode_range_label(group)
        return {
            **group[0].episode,
            "episodeNo": output_index,
            "title": f"第{source_range}集",
            "sourceEpisodeNumbers": source_episode_numbers,
            "sourceEpisodeRange": source_range,
        }

    @staticmethod
    def _episode_range_label(group: list[EpisodeMediaFile]) -> str:
        episode_numbers = [episode_number(item.episode, item.episode_index) for item in group]
        if not episode_numbers:
            return ""
        if len(episode_numbers) == 1 or episode_numbers[0] == episode_numbers[-1]:
            return str(episode_numbers[0])
        return f"{episode_numbers[0]}-{episode_numbers[-1]}"

    @staticmethod
    def _is_ready_upload_file(target: Path) -> bool:
        return target.exists() and target.is_file() and target.stat().st_size > 0

    def _processed_media_target(self, source_file: Path) -> Path:
        try:
            source_parent = source_file.parent.relative_to(self.input_dir())
        except ValueError:
            source_parent = Path(source_file.parent.name)
        return self.output_dir() / source_parent / source_file.name

    def _cover_file_for_sources(self, source_files: list[Path]) -> Path | None:
        if not source_files:
            return None
        asset_dir = self._source_asset_dir(source_files[0])
        poster_cover = asset_dir / "fengmian.jpg"
        video_cover = asset_dir / "video-cover.jpg"
        first_source = source_files[0]
        dimensions = self._video_dimensions(first_source)
        if dimensions:
            width, height = dimensions
            if width > height:
                return video_cover if video_cover.exists() and video_cover.is_file() else self._existing_file(poster_cover)
            return self._existing_file(poster_cover)
        return self._existing_file(poster_cover) or self._existing_file(video_cover)

    @staticmethod
    def _source_asset_dir(source_file: Path) -> Path:
        parent = source_file.parent
        if parent.name == "TK" and parent.parent != parent:
            return parent.parent
        return parent

    def _video_dimensions(self, source_file: Path) -> tuple[int, int] | None:
        video_dimensions = getattr(self.processor, "video_dimensions", None)
        if not callable(video_dimensions):
            return None
        try:
            dimensions = video_dimensions(source_file)
        except Exception:  # noqa: BLE001
            return None
        if not dimensions:
            return None
        width, height = dimensions
        return (int(width), int(height)) if width and height else None

    def _video_duration_seconds(self, source_file: Path) -> float | None:
        video_duration = getattr(self.processor, "video_duration_seconds", None)
        if not callable(video_duration):
            return None
        try:
            duration = video_duration(source_file)
        except Exception:  # noqa: BLE001
            return None
        if duration is None:
            return None
        try:
            parsed = float(duration)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _existing_file(path: Path) -> Path | None:
        return path if path.exists() and path.is_file() else None

    @staticmethod
    def _processed_media_signature(source_file: Path, cover_file: Path | None) -> dict[str, Any]:
        source_stat = source_file.stat()
        signature: dict[str, Any] = {
            "version": WECHAT_VIDEO_COVER_FRAME_VERSION,
            "minWidth": WECHAT_VIDEO_MIN_WIDTH,
            "minHeight": WECHAT_VIDEO_MIN_HEIGHT,
            "source": str(source_file),
            "sourceSize": source_stat.st_size,
            "sourceMtimeNs": source_stat.st_mtime_ns,
            "cover": None,
        }
        if cover_file:
            cover_stat = cover_file.stat()
            signature.update(
                {
                    "cover": str(cover_file),
                    "coverSize": cover_stat.st_size,
                    "coverMtimeNs": cover_stat.st_mtime_ns,
                }
            )
        return signature

    @staticmethod
    def _processed_media_signature_path(target: Path) -> Path:
        return target.with_name(f"{target.name}.aidrama.json")

    def _processed_media_signature_matches(self, target: Path, expected: dict[str, Any]) -> bool:
        signature_file = self._processed_media_signature_path(target)
        if not signature_file.exists():
            return False
        try:
            actual = json.loads(signature_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return actual == expected

    def _write_processed_media_signature(self, target: Path, signature: dict[str, Any]) -> None:
        signature_file = self._processed_media_signature_path(target)
        signature_file.parent.mkdir(parents=True, exist_ok=True)
        signature_file.write_text(json.dumps(signature, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _cleanup_failed_media_file(path: Path) -> None:
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass

    @staticmethod
    def _episode_media_files_from_paths(download_plan: dict, source_files: list[Path]) -> list[EpisodeMediaFile]:
        episodes = download_plan.get("episodes") or []
        by_filename: dict[str, tuple[dict[str, Any], int]] = {}
        for index, episode in enumerate(episodes, start=1):
            by_filename[episode_video_filename(download_plan, episode, index)] = (episode, index)
            by_filename[legacy_episode_video_filename(episode, index)] = (episode, index)

        items: list[EpisodeMediaFile] = []
        used_indexes: set[int] = set()
        for position, source_file in enumerate(source_files):
            matched = by_filename.get(source_file.name)
            if matched is None and len(source_files) == len(episodes) and position < len(episodes):
                matched = (episodes[position], position + 1)
            if matched is None:
                continue
            episode, episode_index = matched
            if episode_index in used_indexes:
                continue
            used_indexes.add(episode_index)
            items.append(EpisodeMediaFile(episode, episode_index, source_file))
        return sorted(items, key=lambda item: item.episode_index)

    def _cached_upload_items(self, download_plan: dict, platform: str) -> list[EpisodeMediaFile]:
        drama_id = str(download_plan["dramaId"])
        if platform == "TIKTOK":
            directories = [
                self.output_dir() / drama_id / "TK",
                self.input_dir() / drama_id / "TK",
                self.output_dir() / drama_id,
                self.input_dir() / drama_id,
            ]
        else:
            directories = [self.output_dir() / drama_id, self.input_dir() / drama_id]
        for directory in directories:
            files = self._cached_video_files(directory)
            if not files:
                continue
            if platform == "TIKTOK" and len(files) > TIKTOK_MAX_EPISODE_COUNT:
                continue
            return self._cached_episode_media_files(download_plan, files, platform)
        return []

    @staticmethod
    def _cached_video_files(directory: Path) -> list[Path]:
        if not directory.exists() or not directory.is_dir():
            return []
        files = [
            path
            for path in directory.iterdir()
            if path.is_file()
            and path.suffix.lower() in {".mp4", ".mov", ".m4v"}
            and not path.name.endswith(".part")
        ]
        return sorted(files, key=lambda path: path.name)

    def _cached_episode_media_files(
        self,
        download_plan: dict,
        files: list[Path],
        platform: str,
    ) -> list[EpisodeMediaFile]:
        original_episodes = download_plan.get("episodes") or []
        if platform == "TIKTOK" and len(original_episodes) > TIKTOK_MAX_EPISODE_COUNT:
            source_items = [
                EpisodeMediaFile(episode, index, files[0])
                for index, episode in enumerate(original_episodes, start=1)
            ]
            groups = self._tiktok_episode_merge_groups(source_items)
            if len(groups) == len(files):
                return [
                    EpisodeMediaFile(
                        self._tiktok_merged_episode_metadata(group, output_index),
                        group[0].episode_index,
                        file,
                        tuple(item.episode_index for item in group),
                    )
                    for output_index, (file, group) in enumerate(zip(files, groups, strict=False), start=1)
                ]
        items: list[EpisodeMediaFile] = []
        for index, file in enumerate(files, start=1):
            episode = original_episodes[index - 1] if index <= len(original_episodes) else {"episodeNo": index}
            items.append(EpisodeMediaFile(episode, index, file))
        return items

    @classmethod
    def _effective_download_plan(cls, download_plan: dict, media_items: list[EpisodeMediaFile]) -> dict:
        original_episodes = download_plan.get("episodes") or []
        effective_count = len(media_items)
        original_count = len(original_episodes)
        downloaded_indexes = {
            source_index
            for item in media_items
            for source_index in (item.source_episode_indexes or (item.episode_index,))
        }
        skipped_episode_numbers = [
            episode_number(episode, index)
            for index, episode in enumerate(original_episodes, start=1)
            if index not in downloaded_indexes
        ]
        effective_plan = {
            **download_plan,
            "episodes": [item.episode for item in media_items],
            "episodeCount": effective_count,
            "totalMinutes": cls._scaled_total_minutes(download_plan, original_count, effective_count),
            "originalEpisodeCount": cls._int_value(download_plan.get("episodeCount"), original_count),
            "skippedEpisodeCount": len(skipped_episode_numbers),
            "skippedEpisodeNumbers": skipped_episode_numbers,
        }
        return effective_plan

    @classmethod
    def _scaled_total_minutes(cls, download_plan: dict, original_count: int, effective_count: int) -> int:
        original_total_minutes = cls._int_value(download_plan.get("totalMinutes"), 0)
        if effective_count <= 0:
            return 0
        if original_total_minutes <= 0:
            return effective_count
        if original_count <= 0 or original_count == effective_count:
            return original_total_minutes
        return max(effective_count, round(original_total_minutes * effective_count / original_count))

    def _publish_metadata(
        self,
        download_plan: dict,
        media_items: list[EpisodeMediaFile],
        platform: str = "WECHAT_VIDEO",
    ) -> dict[str, Any]:
        episodes = download_plan.get("episodes") or []
        cover_file = self.input_dir() / str(download_plan["dramaId"]) / "fengmian.jpg"
        cover_en_file = self.input_dir() / str(download_plan["dramaId"]) / "fengmian-en.jpg"
        tiktok_cover_en_file = self.input_dir() / str(download_plan["dramaId"]) / TIKTOK_COVER_FILENAME
        video_cover_file = self.input_dir() / str(download_plan["dramaId"]) / "video-cover.jpg"
        video_cover_en_file = self.input_dir() / str(download_plan["dramaId"]) / "video-cover-en.jpg"
        publish_title = self._platform_publish_title(download_plan, platform)
        publish_summary = self._platform_publish_summary(download_plan, platform)
        return {
            "dramaId": download_plan.get("dramaId"),
            "platform": platform,
            "title": download_plan.get("title"),
            "aiTitle": download_plan.get("aiTitle"),
            "aiTitleEn": download_plan.get("aiTitleEn"),
            "publishTitle": publish_title,
            "publishSummary": publish_summary,
            "summary": publish_summary,
            "aiSummary": download_plan.get("aiSummary"),
            "aiSummaryEn": download_plan.get("aiSummaryEn"),
            "originalSummary": download_plan.get("summary"),
            "coverFile": cover_file if cover_file.exists() else None,
            "coverEnFile": cover_en_file if cover_en_file.exists() else None,
            "tiktokCoverEnFile": tiktok_cover_en_file if tiktok_cover_en_file.exists() else None,
            "videoCoverFile": video_cover_file if video_cover_file.exists() else None,
            "videoCoverEnFile": video_cover_en_file if video_cover_en_file.exists() else None,
            "coverUrl": download_plan.get("effectiveCoverUrl") or download_plan.get("aiCoverUrl") or download_plan.get("coverUrl"),
            "videoCoverUrl": download_plan.get("aiVideoCoverUrl"),
            "coverEnUrl": download_plan.get("aiCoverEnUrl"),
            "videoCoverEnUrl": download_plan.get("aiVideoCoverEnUrl"),
            "rating": download_plan.get("rating"),
            "categoryIds": download_plan.get("categoryIds") or [],
            "totalMinutes": download_plan.get("totalMinutes"),
            "costAmountWan": download_plan.get("costAmountWan"),
            "productionCostWan": download_plan.get("costAmountWan"),
            "producerName": self.contract_seller or self.contract_buyer,
            "aiContentDeclaration": True,
            "monetizationType": "IAA_AD",
            "monetizationLabel": "IAA广告变现",
            "freeEpisodeCount": self._free_episode_count(download_plan, len(episodes)),
            "episodeCount": len(episodes),
            "originalEpisodeCount": download_plan.get("originalEpisodeCount"),
            "skippedEpisodeCount": download_plan.get("skippedEpisodeCount") or 0,
            "skippedEpisodeNumbers": download_plan.get("skippedEpisodeNumbers") or [],
            "episodes": [
                self._episode_publish_metadata(item)
                for item in media_items
            ],
        }

    @staticmethod
    def _episode_publish_metadata(item: EpisodeMediaFile) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "episodeNo": item.episode.get("episodeNo"),
            "title": item.episode.get("title"),
            "file": item.file,
        }
        source_numbers = item.episode.get("sourceEpisodeNumbers")
        source_range = item.episode.get("sourceEpisodeRange")
        if source_numbers:
            payload["sourceEpisodeNumbers"] = source_numbers
        if source_range:
            payload["sourceEpisodeRange"] = source_range
        return payload

    @staticmethod
    def _platform_publish_title(download_plan: dict[str, Any], platform: str) -> str:
        if platform == "TIKTOK":
            return str(
                download_plan.get("aiTitleEn")
                or download_plan.get("aiTitle")
                or download_plan.get("title")
                or download_plan.get("dramaId")
                or ""
            )
        return str(download_plan.get("aiTitle") or download_plan.get("title") or download_plan.get("dramaId") or "")

    @staticmethod
    def _platform_publish_summary(download_plan: dict[str, Any], platform: str) -> str | None:
        if platform == "TIKTOK":
            value = download_plan.get("aiSummaryEn") or download_plan.get("aiSummary") or download_plan.get("summary")
        else:
            value = download_plan.get("aiSummary") or download_plan.get("summary")
        return str(value) if value else None

    @classmethod
    def _free_episode_count(cls, download_plan: dict[str, Any], episode_count: int) -> int:
        for key in ("freeEpisodeCount", "trialEpisodeCount", "previewEpisodeCount", "sampleEpisodeCount"):
            value = cls._int_value(download_plan.get(key), 0)
            if value > 0:
                return min(value, episode_count) if episode_count > 0 else value
        if episode_count <= 0:
            return 3
        calculated = max(3, min(20, round(episode_count * 0.2)))
        return min(calculated, episode_count)

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
    max_skipped_episodes: int = 0,
    skip_callback: Callable[[int, int, dict, BaseException], None] | None = None,
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
    video_cover_file = download_video_cover(
        download_plan,
        target_dir,
        base_url,
        headers=headers,
        should_stop=should_stop,
        should_pause=should_pause,
        should_skip=should_skip,
    )
    cover_en_file = download_english_cover(
        download_plan,
        target_dir,
        base_url,
        headers=headers,
        should_stop=should_stop,
        should_pause=should_pause,
        should_skip=should_skip,
    )
    tiktok_cover_en_file = prepare_tiktok_cover(cover_en_file, target_dir)
    video_cover_en_file = download_english_video_cover(
        download_plan,
        target_dir,
        base_url,
        headers=headers,
        should_stop=should_stop,
        should_pause=should_pause,
        should_skip=should_skip,
    )
    write_drama_metadata(
        download_plan,
        target_dir,
        cover_file,
        video_cover_file,
        cover_en_file,
        video_cover_en_file,
        tiktok_cover_en_file,
    )
    episodes = download_plan["episodes"]
    total = len(episodes)
    if not episodes:
        return []

    worker_count = max(1, min(max_concurrent_downloads, total))
    files: list[Path | None] = [None] * total
    skipped_indexes: set[int] = set()
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                download_episode,
                episode,
                index,
                total,
                target_dir,
                episode_video_filename(download_plan, episode, index),
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
            try:
                files[index - 1] = future.result()
            except TaskInterrupted:
                raise
            except Exception as exception:  # noqa: BLE001
                if max_skipped_episodes <= 0:
                    raise
                episode = episodes[index - 1]
                if skip_callback:
                    skip_callback(index, total, episode, exception)
                files[index - 1] = None
                skipped_indexes.add(index)
                if len(skipped_indexes) > max_skipped_episodes:
                    raise RuntimeError(
                        f"剧集下载失败超过 {max_skipped_episodes} 集，整部剧分发失败。"
                        f"最近失败：{exception}"
                    ) from exception
    return [file for file in files if file is not None]


def download_episode(
    episode: dict,
    index: int,
    total: int,
    target_dir: Path,
    filename: str,
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
    target = target_dir / filename
    legacy_target = target_dir / legacy_episode_video_filename(episode, index)
    if target != legacy_target and is_complete_episode_file(legacy_target, episode) and not target.exists():
        legacy_target.replace(target)
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
    try:
        response_context = urllib.request.urlopen(request)
    except urllib.error.HTTPError as exception:
        raise download_http_error(exception, episode_number(episode, index)) from exception
    with response_context as response, target.open("wb") as output:
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


def episode_video_filename(download_plan: dict, episode: dict, index: int) -> str:
    drama_name = safe_episode_drama_name(
        download_plan.get("aiTitle")
        or download_plan.get("publishTitle")
        or download_plan.get("title")
        or download_plan.get("name")
    )
    episode_no = episode_number(episode, index)
    return f"{drama_name}-第{episode_no}集.mp4"


def legacy_episode_video_filename(episode: dict, index: int) -> str:
    return f"{episode_number(episode, index):03d}.mp4"


def episode_number(episode: dict, index: int) -> int:
    try:
        value = int(episode.get("episodeNo") or index)
    except (TypeError, ValueError):
        value = index
    return max(value, 1)


def safe_episode_drama_name(value: object) -> str:
    clean = INVALID_FILENAME_CHARS_RE.sub("", str(value or "").strip())
    clean = re.sub(r"\s+", "", clean).strip(FILENAME_EDGE_CHARS)
    return clean or "短剧"


def cleanup_part_file(part_file: Path) -> None:
    try:
        if part_file.exists():
            part_file.unlink()
    except OSError:
        pass


def is_retryable_download_error(exception: BaseException) -> bool:
    if isinstance(exception, DownloadHttpError):
        if exception.error_code in NON_RETRYABLE_DOWNLOAD_ERROR_CODES:
            return False
        return exception.status_code in RETRYABLE_HTTP_STATUS_CODES
    if isinstance(exception, urllib.error.HTTPError):
        return exception.code in RETRYABLE_HTTP_STATUS_CODES
    if isinstance(exception, urllib.error.URLError):
        return True
    if isinstance(exception, TimeoutError):
        return True
    return False


def download_http_error(exception: urllib.error.HTTPError, episode_no: int) -> DownloadHttpError:
    body = _read_http_error_body(exception)
    error_code: str | None = None
    error_message: str | None = None
    if body:
        try:
            payload = json.loads(body)
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                error_code = str(error.get("code") or "") or None
                error_message = str(error.get("message") or "") or None
    reason = str(getattr(exception, "reason", None) or getattr(exception, "msg", None) or "")
    return DownloadHttpError(
        episode_no=episode_no,
        status_code=exception.code,
        reason=reason or "HTTP Error",
        error_code=error_code,
        error_message=error_message,
    )


def _read_http_error_body(exception: urllib.error.HTTPError) -> str:
    try:
        raw = exception.read(64 * 1024)
    except Exception:  # noqa: BLE001
        return ""
    if not raw:
        return ""
    return raw.decode("utf-8", errors="replace")


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
    return download_plan_asset(
        cover_url,
        target_dir / "fengmian.jpg",
        base_url,
        headers=headers,
        should_stop=should_stop,
        should_pause=should_pause,
        should_skip=should_skip,
    )


def download_video_cover(
    download_plan: dict,
    target_dir: Path,
    base_url: str,
    headers: dict[str, str] | None = None,
    should_stop: Callable[[], bool] | None = None,
    should_pause: Callable[[], bool] | None = None,
    should_skip: Callable[[], bool] | None = None,
) -> Path | None:
    return download_plan_asset(
        download_plan.get("aiVideoCoverUrl"),
        target_dir / "video-cover.jpg",
        base_url,
        headers=headers,
        should_stop=should_stop,
        should_pause=should_pause,
        should_skip=should_skip,
    )


def download_english_cover(
    download_plan: dict,
    target_dir: Path,
    base_url: str,
    headers: dict[str, str] | None = None,
    should_stop: Callable[[], bool] | None = None,
    should_pause: Callable[[], bool] | None = None,
    should_skip: Callable[[], bool] | None = None,
) -> Path | None:
    return download_plan_asset(
        download_plan.get("aiCoverEnUrl"),
        target_dir / "fengmian-en.jpg",
        base_url,
        headers=headers,
        should_stop=should_stop,
        should_pause=should_pause,
        should_skip=should_skip,
    )


def download_english_video_cover(
    download_plan: dict,
    target_dir: Path,
    base_url: str,
    headers: dict[str, str] | None = None,
    should_stop: Callable[[], bool] | None = None,
    should_pause: Callable[[], bool] | None = None,
    should_skip: Callable[[], bool] | None = None,
) -> Path | None:
    return download_plan_asset(
        download_plan.get("aiVideoCoverEnUrl"),
        target_dir / "video-cover-en.jpg",
        base_url,
        headers=headers,
        should_stop=should_stop,
        should_pause=should_pause,
        should_skip=should_skip,
    )


def prepare_tiktok_cover(cover_file: Path | None, target_dir: Path) -> Path | None:
    if not cover_file or not cover_file.exists() or not cover_file.is_file():
        return None
    target = target_dir / TIKTOK_COVER_FILENAME
    if is_ready_tiktok_cover(target, cover_file):
        return target
    try:
        from PySide6.QtCore import QRect, Qt
        from PySide6.QtGui import QImage
    except ImportError:
        return None
    source = QImage(str(cover_file))
    if source.isNull() or source.width() <= 0 or source.height() <= 0:
        return None
    crop_rect = tiktok_cover_crop_rect(source.width(), source.height(), QRect)
    cropped = source.copy(crop_rect)
    scaled = cropped.scaled(
        TIKTOK_COVER_WIDTH,
        TIKTOK_COVER_HEIGHT,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    output = scaled.convertToFormat(QImage.Format.Format_RGB888)
    target.parent.mkdir(parents=True, exist_ok=True)
    for quality in (92, 86, 80, 74, 68):
        if output.save(str(target), "JPEG", quality) and target.stat().st_size <= TIKTOK_COVER_MAX_BYTES:
            return target
    return target if target.exists() and target.is_file() else None


def is_ready_tiktok_cover(target: Path, source: Path) -> bool:
    if not target.exists() or not target.is_file() or target.stat().st_size <= 0:
        return False
    if target.stat().st_size > TIKTOK_COVER_MAX_BYTES or target.stat().st_mtime_ns < source.stat().st_mtime_ns:
        return False
    try:
        from PySide6.QtGui import QImage
    except ImportError:
        return True
    image = QImage(str(target))
    return not image.isNull() and image.width() == TIKTOK_COVER_WIDTH and image.height() == TIKTOK_COVER_HEIGHT


def tiktok_cover_crop_rect(width: int, height: int, rect_factory):
    target_ratio = TIKTOK_COVER_WIDTH / TIKTOK_COVER_HEIGHT
    source_ratio = width / height
    if source_ratio > target_ratio:
        crop_width = max(1, round(height * target_ratio))
        x = max((width - crop_width) // 2, 0)
        return rect_factory(x, 0, crop_width, height)
    crop_height = max(1, round(width / target_ratio))
    y = max((height - crop_height) // 2, 0)
    return rect_factory(0, y, width, crop_height)


def download_plan_asset(
    asset_url: object,
    target: Path,
    base_url: str,
    headers: dict[str, str] | None = None,
    should_stop: Callable[[], bool] | None = None,
    should_pause: Callable[[], bool] | None = None,
    should_skip: Callable[[], bool] | None = None,
) -> Path | None:
    if not asset_url:
        return None
    raise_if_task_interrupted(should_stop, should_pause, should_skip)
    request = urllib.request.Request(resolve_download_url(str(asset_url), base_url), headers=episode_download_headers(headers))
    with urllib.request.urlopen(request) as response, target.open("wb") as output:
        while True:
            raise_if_task_interrupted(should_stop, should_pause, should_skip)
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
    return target


def write_drama_metadata(
    download_plan: dict,
    target_dir: Path,
    cover_file: Path | None,
    video_cover_file: Path | None = None,
    cover_en_file: Path | None = None,
    video_cover_en_file: Path | None = None,
    tiktok_cover_en_file: Path | None = None,
) -> Path:
    episodes = download_plan.get("episodes") or []
    publish_summary = download_plan.get("aiSummary") or download_plan.get("summary")
    metadata = {
        "dramaId": download_plan.get("dramaId"),
        "title": download_plan.get("title"),
        "aiTitle": download_plan.get("aiTitle"),
        "aiTitleEn": download_plan.get("aiTitleEn"),
        "publishTitle": download_plan.get("aiTitle") or download_plan.get("title"),
        "summary": publish_summary,
        "aiSummary": download_plan.get("aiSummary"),
        "aiSummaryEn": download_plan.get("aiSummaryEn"),
        "originalSummary": download_plan.get("summary"),
        "coverFile": cover_file.name if cover_file else None,
        "coverEnFile": cover_en_file.name if cover_en_file else None,
        "tiktokCoverEnFile": tiktok_cover_en_file.name if tiktok_cover_en_file else None,
        "videoCoverFile": video_cover_file.name if video_cover_file else None,
        "videoCoverEnFile": video_cover_en_file.name if video_cover_en_file else None,
        "coverUrl": download_plan.get("effectiveCoverUrl") or download_plan.get("aiCoverUrl") or download_plan.get("coverUrl"),
        "videoCoverUrl": download_plan.get("aiVideoCoverUrl"),
        "coverEnUrl": download_plan.get("aiCoverEnUrl"),
        "videoCoverEnUrl": download_plan.get("aiVideoCoverEnUrl"),
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
                "fileName": episode_video_filename(download_plan, episode, index),
            }
            for index, episode in enumerate(episodes, start=1)
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
