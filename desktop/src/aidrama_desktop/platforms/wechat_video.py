from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from aidrama_desktop.browser.chrome import ChromeController
from aidrama_desktop.platforms.base import PlatformPublisher


class WeChatVideoPublisher(PlatformPublisher):
    login_url = "https://channels.weixin.qq.com/platform"
    playlet_url = "https://channels.weixin.qq.com/platform/playlet"

    def __init__(
        self,
        chrome: ChromeController,
        account_id: str | None = None,
        profile_dir: str | Path | None = None,
    ):
        self.chrome = chrome
        self.account_id = account_id
        self.profile_dir = Path(profile_dir) if profile_dir else None

    def open_login(self) -> str:
        if self.profile_dir:
            self.chrome.open_profile(self._profile_dir(), self.login_url)
        else:
            self.chrome.open_platform_login("WECHAT_VIDEO", self.login_url, self.account_id)
        return self.export_login_state()

    def export_login_state(self) -> str:
        return str(self._profile_dir())

    def _profile_dir(self) -> Path:
        if self.profile_dir:
            self.profile_dir.mkdir(parents=True, exist_ok=True)
            return self.profile_dir
        return self.chrome.platform_profile_dir("WECHAT_VIDEO", self.account_id)

    def publish(
        self,
        media_files: list[Path],
        title: str,
        summary: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if not media_files:
            raise ValueError("media_files cannot be empty")
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exception:
            raise RuntimeError("Playwright is required for real WeChat Video publishing") from exception

        profile_dir = self._profile_dir()
        with sync_playwright() as playwright:
            try:
                context = playwright.chromium.launch_persistent_context(
                    str(profile_dir),
                    executable_path=self.chrome.chrome_path,
                    headless=False,
                    args=[
                        "--no-first-run",
                        "--disable-default-apps",
                        "--disable-session-crashed-bubble",
                    ],
                )
            except Exception as exception:  # noqa: BLE001
                raise RuntimeError("无法启动视频号发布浏览器，请关闭该媒体号已打开的 Chrome 窗口后重试") from exception
            try:
                page = self._open_publish_page(context, self.playlet_url if metadata else self.login_url)
                if metadata:
                    self._upload_playlet(page, media_files, title, summary, metadata, PlaywrightTimeoutError)
                else:
                    for media_file in media_files:
                        self._upload_single(page, media_file, title, summary, PlaywrightTimeoutError)
            finally:
                self._close_context(context)
        prefix = "wechat-playlet" if metadata else "wechat-video"
        return f"{prefix}:{title}:{len(media_files)}"

    def _open_publish_page(self, context, target_url: str):
        startup_pages = list(getattr(context, "pages", []) or [])
        page = context.new_page()
        try:
            page.goto(target_url, wait_until="domcontentloaded")
            page.wait_for_timeout(1000)
        except Exception as exception:  # noqa: BLE001
            if self._is_page_closed_error(exception):
                raise RuntimeError("浏览器页面已关闭，无法打开视频号发布页面") from exception
            raise RuntimeError("无法打开视频号发布页面，请确认网络正常并已登录视频号助手") from exception
        self._close_startup_blank_pages(startup_pages, active_page=page)
        return page

    def _close_startup_blank_pages(self, pages, active_page) -> None:
        for page in pages:
            if page is active_page:
                continue
            url = str(getattr(page, "url", "") or "")
            close = getattr(page, "close", None)
            if callable(close) and url in {"", "about:blank"}:
                try:
                    close()
                except Exception:
                    pass

    @staticmethod
    def _close_context(context) -> None:
        try:
            context.close()
        except Exception:
            pass

    def _upload_playlet(
        self,
        page,
        media_files: list[Path],
        title: str,
        summary: str | None,
        metadata: dict[str, Any],
        timeout_error,
    ) -> None:
        publish_title = str(metadata.get("publishTitle") or title)
        publish_summary = str(metadata.get("summary") or summary or "")
        create_button = page.get_by_text(re.compile("创建剧集|新建剧集|新增剧集|上传剧集|添加剧集")).first
        try:
            create_button.click(timeout=8000)
            page.wait_for_timeout(1000)
        except timeout_error:
            pass

        self._fill_first(page, ["剧集名称", "短剧名称", "标题", "请输入剧集名称", "请输入标题"], publish_title)
        if publish_summary:
            self._fill_first(page, ["简介", "剧情简介", "描述", "请输入简介", "请输入剧情简介"], publish_summary)

        self._set_monetization_type(page, str(metadata.get("monetizationLabel") or "IAA广告变现"), timeout_error)
        free_episode_count = metadata.get("freeEpisodeCount")
        if free_episode_count is not None:
            self._fill_first(
                page,
                ["免费集数", "免费试看集数", "免费观看集数", "请输入免费集数", "请输入免费试看集数"],
                str(free_episode_count),
            )

        cover_file = metadata.get("coverFile")
        if cover_file:
            self._set_file_input(page, Path(cover_file), re.compile("封面|上传封面|添加封面"), timeout_error)

        episode_files = [
            Path(episode.get("file"))
            for episode in metadata.get("episodes", [])
            if episode.get("file")
        ] or media_files
        self._set_file_input(page, episode_files, re.compile("上传视频|上传剧集|添加视频|添加剧集|选择文件"), timeout_error)

        try:
            page.get_by_text(re.compile("保存|提交审核|发布|上架")).first.click(timeout=15000)
        except timeout_error as exception:
            raise RuntimeError("短剧文件已选择，但未找到剧集保存/提交按钮，请检查视频号剧集管理页面") from exception

    def _upload_single(self, page, media_file: Path, title: str, summary: str | None, timeout_error) -> None:
        upload_button = page.get_by_text(re.compile("发表视频|发布视频|上传视频|创建")).first
        file_input = page.locator('input[type="file"]').first
        if file_input.count() > 0:
            file_input.set_input_files(str(media_file))
        else:
            try:
                with page.expect_file_chooser(timeout=5000) as chooser:
                    upload_button.click(timeout=5000)
                chooser.value.set_files(str(media_file))
            except timeout_error as exception:
                raise RuntimeError("未找到视频号上传入口，请确认已登录并停留在视频号助手后台") from exception

        self._fill_first(page, ["标题", "请输入标题"], title)
        if summary:
            self._fill_first(page, ["描述", "简介", "请输入描述", "请输入简介"], summary)

        try:
            page.get_by_text(re.compile("发表|发布|上架")).first.click(timeout=15000)
        except timeout_error as exception:
            raise RuntimeError("视频已选择，但未找到发布按钮，请检查视频号后台页面") from exception

    def _fill_first(self, page, labels: list[str], value: str) -> None:
        for label in labels:
            locator = page.get_by_placeholder(label).first
            if locator.count() == 0:
                locator = page.get_by_label(label).first
            if locator.count() > 0:
                locator.fill(value)
                return

    def _set_monetization_type(self, page, label: str, timeout_error) -> None:
        try:
            page.get_by_text(re.compile("变现类型|收益类型|付费类型")).first.click(timeout=3000)
        except timeout_error:
            pass
        except Exception as exception:  # noqa: BLE001
            if self._is_page_closed_error(exception):
                raise RuntimeError("浏览器页面已关闭，等待视频号剧集变现类型控件失败") from exception
            raise RuntimeError("等待视频号剧集变现类型控件失败") from exception
        try:
            page.get_by_text(re.compile(re.escape(label))).first.click(timeout=5000)
        except timeout_error as exception:
            raise RuntimeError(f"未找到视频号剧集变现类型选项：{label}") from exception
        except Exception as exception:  # noqa: BLE001
            if self._is_page_closed_error(exception):
                raise RuntimeError(f"浏览器页面已关闭，选择视频号剧集变现类型失败：{label}") from exception
            raise RuntimeError(f"选择视频号剧集变现类型失败：{label}") from exception

    @staticmethod
    def _is_page_closed_error(exception: Exception) -> bool:
        message = str(exception)
        return "Target page, context or browser has been closed" in message

    def _set_file_input(self, page, files: Path | list[Path], button_pattern, timeout_error) -> None:
        paths = [str(item) for item in files] if isinstance(files, list) else str(files)
        file_input = page.locator('input[type="file"]').first
        if file_input.count() > 0:
            file_input.set_input_files(paths)
            return
        try:
            with page.expect_file_chooser(timeout=5000) as chooser:
                page.get_by_text(button_pattern).first.click(timeout=5000)
            chooser.value.set_files(paths)
        except timeout_error as exception:
            raise RuntimeError("未找到视频号剧集管理上传入口，请确认已登录并停留在剧集管理页面") from exception
