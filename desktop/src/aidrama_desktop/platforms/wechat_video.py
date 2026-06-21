from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from aidrama_desktop.browser.chrome import ChromeController
from aidrama_desktop.platforms.base import PlatformPublisher


class WeChatVideoPublisher(PlatformPublisher):
    login_url = "https://channels.weixin.qq.com/platform"
    playlet_url = "https://channels.weixin.qq.com/platform/playlet"

    def __init__(self, chrome: ChromeController, account_id: str | None = None):
        self.chrome = chrome
        self.account_id = account_id

    def open_login(self) -> str:
        self.chrome.open_platform_login("WECHAT_VIDEO", self.login_url, self.account_id)
        return self.export_login_state()

    def export_login_state(self) -> str:
        return self.chrome.login_state_ref("WECHAT_VIDEO", self.account_id)

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

        profile_dir = self.chrome.platform_profile_dir("WECHAT_VIDEO", self.account_id)
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(profile_dir),
                executable_path=self.chrome.chrome_path,
                headless=False,
                args=["--no-first-run", "--disable-default-apps"],
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(self.playlet_url if metadata else self.login_url, wait_until="domcontentloaded")
            page.wait_for_timeout(1000)

            if metadata:
                self._upload_playlet(page, media_files, title, summary, metadata, PlaywrightTimeoutError)
            else:
                for media_file in media_files:
                    self._upload_single(page, media_file, title, summary, PlaywrightTimeoutError)
            context.close()
        prefix = "wechat-playlet" if metadata else "wechat-video"
        return f"{prefix}:{title}:{len(media_files)}"

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
        try:
            page.get_by_text(re.compile(re.escape(label))).first.click(timeout=5000)
        except timeout_error as exception:
            raise RuntimeError(f"未找到视频号剧集变现类型选项：{label}") from exception

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
