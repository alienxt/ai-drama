from pathlib import Path

from aidrama_desktop.browser.chrome import ChromeController
from aidrama_desktop.platforms.registry import get_publisher
from aidrama_desktop.platforms.wechat_video import WeChatVideoPublisher


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


def test_wechat_video_publisher_opens_playlet_management_for_drama_publish(tmp_path: Path, monkeypatch):
    visited_urls = []
    uploaded = []

    class FakePage:
        def goto(self, url, wait_until=None):
            visited_urls.append((url, wait_until))

        def wait_for_timeout(self, _timeout):
            return None

    class FakeContext:
        def __init__(self):
            self.pages = [FakePage()]

        def new_page(self):
            page = FakePage()
            self.pages.append(page)
            return page

        def close(self):
            return None

    class FakeChromium:
        def launch_persistent_context(self, user_data_dir, executable_path=None, headless=False, args=None):
            assert user_data_dir == str(tmp_path / "wechat_video" / "media-1")
            assert executable_path == "chrome"
            assert headless is False
            return FakeContext()

    class FakePlaywright:
        chromium = FakeChromium()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: FakePlaywright())
    monkeypatch.setattr(
        WeChatVideoPublisher,
        "_upload_playlet",
        lambda self, page, media_files, title, summary, metadata, timeout_error: uploaded.append(
            (media_files, title, summary, metadata)
        ),
    )
    publisher = get_publisher("WECHAT_VIDEO", ChromeController("chrome", tmp_path), account_id="media-1")
    media_file = tmp_path / "001.mp4"

    result = publisher.publish([media_file], "神医归来", summary="简介", metadata={"coverFile": tmp_path / "cover.jpg"})

    assert result == "wechat-playlet:神医归来:1"
    assert visited_urls == [(WeChatVideoPublisher.playlet_url, "domcontentloaded")]
    assert uploaded == [([media_file], "神医归来", "简介", {"coverFile": tmp_path / "cover.jpg"})]


def test_wechat_video_publisher_sets_playlet_monetization_and_free_episode_count(tmp_path: Path, monkeypatch):
    fills = []
    monetization = []
    files = []
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    class FakeLocator:
        def click(self, timeout=None):
            return None

    class FakePage:
        def get_by_text(self, pattern):
            return self

        @property
        def first(self):
            return FakeLocator()

        def wait_for_timeout(self, _timeout):
            return None

    monkeypatch.setattr(
        publisher,
        "_fill_first",
        lambda page, labels, value: fills.append((labels, value)),
    )
    monkeypatch.setattr(
        publisher,
        "_set_file_input",
        lambda page, target_files, button_pattern, timeout_error: files.append(target_files),
    )
    monkeypatch.setattr(
        publisher,
        "_set_monetization_type",
        lambda page, value, timeout_error: monetization.append(value),
    )

    publisher._upload_playlet(
        FakePage(),
        [tmp_path / "001.mp4"],
        "神医归来",
        "简介",
        {
            "publishTitle": "神医归来AI",
            "summary": "简介",
            "coverFile": tmp_path / "cover.jpg",
            "episodes": [{"episodeNo": 1, "file": tmp_path / "001.mp4"}],
            "monetizationLabel": "IAA广告变现",
            "freeEpisodeCount": 6,
        },
        TimeoutError,
    )

    assert monetization == ["IAA广告变现"]
    assert any(value == "6" and "免费集数" in labels for labels, value in fills)
    assert files == [tmp_path / "cover.jpg", [tmp_path / "001.mp4"]]


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
