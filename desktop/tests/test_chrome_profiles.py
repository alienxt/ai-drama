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


def test_open_platform_login_can_enable_remote_debugging(tmp_path: Path, monkeypatch):
    calls = []

    class FakeProcess:
        pass

    monkeypatch.setattr("aidrama_desktop.browser.chrome.subprocess.Popen", lambda args: calls.append(args) or FakeProcess())
    chrome = ChromeController("chrome", tmp_path)

    process = chrome.open_platform_login(
        "WECHAT_VIDEO",
        "https://channels.weixin.qq.com/platform",
        "media-1",
        remote_debugging_port=19001,
    )

    assert isinstance(process, FakeProcess)
    assert "--remote-debugging-port=19001" in calls[0]


def test_open_platform_login_reuses_same_profile_for_same_media_account(tmp_path: Path, monkeypatch):
    calls = []

    class FakeProcess:
        pass

    monkeypatch.setattr("aidrama_desktop.browser.chrome.subprocess.Popen", lambda args: calls.append(args) or FakeProcess())
    chrome = ChromeController("chrome", tmp_path)

    chrome.open_platform_login("WECHAT_VIDEO", "https://channels.weixin.qq.com/platform", "media-1")
    chrome.open_platform_login("WECHAT_VIDEO", "https://channels.weixin.qq.com/platform", "media-1")

    user_data_dirs = [
        arg
        for args in calls
        for arg in args
        if arg.startswith("--user-data-dir=")
    ]
    assert user_data_dirs == [
        f"--user-data-dir={tmp_path / 'wechat_video' / 'media-1'}",
        f"--user-data-dir={tmp_path / 'wechat_video' / 'media-1'}",
    ]


def test_open_profile_uses_saved_profile_directory(tmp_path: Path, monkeypatch):
    calls = []

    class FakeProcess:
        pass

    monkeypatch.setattr("aidrama_desktop.browser.chrome.subprocess.Popen", lambda args: calls.append(args) or FakeProcess())
    chrome = ChromeController("chrome", tmp_path)
    saved_profile = tmp_path / "saved-profile"

    chrome.open_profile(saved_profile, "https://channels.weixin.qq.com/platform")

    assert f"--user-data-dir={saved_profile}" in calls[0]
