from __future__ import annotations

from pathlib import Path

from aidrama_desktop.browser.chrome import ChromeController
from aidrama_desktop.platforms.base import PlatformPublisher
from aidrama_desktop.platforms.wechat_video import WeChatVideoPublisher


def platform_login_url(platform: str) -> str:
    if platform == "WECHAT_VIDEO":
        return WeChatVideoPublisher.login_url
    if platform == "DOUYIN":
        return "https://creator.douyin.com/"
    if platform == "TIKTOK":
        return "https://www.tiktok.com/upload"
    raise NotImplementedError(f"{platform} publisher is reserved for a later adapter")


def get_publisher(
    platform: str,
    chrome: ChromeController,
    account_id: str | None = None,
    profile_dir: str | Path | None = None,
) -> PlatformPublisher:
    if platform == "WECHAT_VIDEO":
        return WeChatVideoPublisher(chrome, account_id=account_id, profile_dir=profile_dir)
    raise NotImplementedError(f"{platform} publisher is reserved for a later adapter")
