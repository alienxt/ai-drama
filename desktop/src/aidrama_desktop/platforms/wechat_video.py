from __future__ import annotations

import re
from pathlib import Path

from aidrama_desktop.browser.chrome import ChromeController
from aidrama_desktop.platforms.base import PlatformPublisher


class WeChatVideoPublisher(PlatformPublisher):
    login_url = "https://channels.weixin.qq.com/platform"

    def __init__(self, chrome: ChromeController, account_id: str | None = None):
        self.chrome = chrome
        self.account_id = account_id

    def open_login(self) -> str:
        self.chrome.open_platform_login("WECHAT_VIDEO", self.login_url, self.account_id)
        return self.export_login_state()

    def export_login_state(self) -> str:
        return self.chrome.login_state_ref("WECHAT_VIDEO", self.account_id)

    def publish(self, media_files: list[Path], title: str, summary: str | None = None) -> str:
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
            page.goto(self.login_url, wait_until="domcontentloaded")
            page.wait_for_timeout(1000)

            for media_file in media_files:
                self._upload_single(page, media_file, title, summary, PlaywrightTimeoutError)
            context.close()
        return f"wechat-video:{title}:{len(media_files)}"

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
