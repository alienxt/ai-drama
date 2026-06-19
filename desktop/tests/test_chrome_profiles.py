from pathlib import Path

from aidrama_desktop.browser.chrome import ChromeController
from aidrama_desktop.platforms.registry import get_publisher


def test_chrome_profile_can_be_scoped_to_media_account(tmp_path: Path):
    chrome = ChromeController("chrome", tmp_path)

    profile = chrome.platform_profile_dir("WECHAT_VIDEO", "media-1")

    assert profile == tmp_path / "wechat_video" / "media-1"
    assert profile.exists()
    assert chrome.login_state_ref("WECHAT_VIDEO", "media-1") == str(profile)


def test_wechat_video_publisher_uses_media_account_profile(tmp_path: Path):
    chrome = ChromeController("chrome", tmp_path)
    publisher = get_publisher("WECHAT_VIDEO", chrome, account_id="media-1")

    assert publisher.export_login_state() == str(tmp_path / "wechat_video" / "media-1")
