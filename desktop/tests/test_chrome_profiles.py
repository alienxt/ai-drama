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


def test_wechat_video_publisher_prefers_saved_profile_dir(tmp_path: Path):
    chrome = ChromeController("chrome", tmp_path)
    saved_profile = tmp_path / "wechat_video" / "external-account"
    publisher = get_publisher(
        "WECHAT_VIDEO",
        chrome,
        account_id="media-1",
        profile_dir=saved_profile,
    )

    assert publisher.export_login_state() == str(saved_profile)
    assert saved_profile.exists()


def test_wechat_video_publisher_opens_playlet_management_for_drama_publish(tmp_path: Path, monkeypatch):
    visited_urls = []
    uploaded = []
    opened = []
    connected = []

    class FakePage:
        url = "about:blank"

        def goto(self, url, wait_until=None):
            self.url = url
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
        def connect_over_cdp(self, endpoint_url):
            connected.append(endpoint_url)
            return FakeBrowser()

    class FakeBrowser:
        contexts = [FakeContext()]

        def close(self):
            return None

    class FakePlaywright:
        chromium = FakeChromium()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr(
        "aidrama_desktop.platforms.wechat_video.available_remote_debugging_port",
        lambda: 9333,
    )
    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: FakePlaywright())
    monkeypatch.setattr(
        WeChatVideoPublisher,
        "_upload_playlet",
        lambda self, page, media_files, title, summary, metadata, timeout_error: uploaded.append(
            (media_files, title, summary, metadata)
        ),
    )
    chrome = ChromeController("chrome", tmp_path)
    monkeypatch.setattr(chrome, "open_profile", lambda profile_dir, url, remote_debugging_port=None: opened.append((profile_dir, url, remote_debugging_port)))
    publisher = get_publisher("WECHAT_VIDEO", chrome, account_id="media-1")
    media_file = tmp_path / "001.mp4"

    result = publisher.publish([media_file], "神医归来", summary="简介", metadata={"coverFile": tmp_path / "cover.jpg"})

    assert result == "wechat-playlet:神医归来:1"
    assert opened == [(tmp_path / "wechat_video" / "media-1", WeChatVideoPublisher.playlet_url, 9333)]
    assert connected == ["http://127.0.0.1:9333"]
    assert visited_urls == [(WeChatVideoPublisher.playlet_url, "domcontentloaded")]
    assert uploaded == [([media_file], "神医归来", "简介", {"coverFile": tmp_path / "cover.jpg"})]


def test_wechat_video_publisher_reuses_startup_blank_page_for_playlet_publish(tmp_path: Path, monkeypatch):
    uploaded_pages = []
    opened = []

    class FakePage:
        def __init__(self, url="about:blank"):
            self.url = url
            self.closed = False
            self.visited = []

        def goto(self, url, wait_until=None):
            self.url = url
            self.visited.append((url, wait_until))

        def wait_for_timeout(self, _timeout):
            return None

        def close(self):
            self.closed = True

    blank_page = FakePage()
    unexpected_page = FakePage()

    class FakeContext:
        def __init__(self):
            self.pages = [blank_page]
            self.closed = False

        def new_page(self):
            self.pages.append(unexpected_page)
            return unexpected_page

        def close(self):
            self.closed = True

    context = FakeContext()

    class FakeBrowser:
        contexts = [context]

        def close(self):
            context.close()

    class FakeChromium:
        def connect_over_cdp(self, _endpoint_url):
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr(
        "aidrama_desktop.platforms.wechat_video.available_remote_debugging_port",
        lambda: 9333,
    )
    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: FakePlaywright())
    monkeypatch.setattr(
        WeChatVideoPublisher,
        "_upload_playlet",
        lambda self, page, media_files, title, summary, metadata, timeout_error: uploaded_pages.append(page),
    )
    chrome = ChromeController("chrome", tmp_path)
    monkeypatch.setattr(chrome, "open_profile", lambda profile_dir, url, remote_debugging_port=None: opened.append((profile_dir, url, remote_debugging_port)))
    publisher = get_publisher("WECHAT_VIDEO", chrome, account_id="media-1")
    media_file = tmp_path / "001.mp4"

    publisher.publish([media_file], "神医归来", metadata={"coverFile": tmp_path / "cover.jpg"})

    assert blank_page.closed is False
    assert uploaded_pages == [blank_page]
    assert opened == [(tmp_path / "wechat_video" / "media-1", WeChatVideoPublisher.playlet_url, 9333)]
    assert blank_page.visited == [(WeChatVideoPublisher.playlet_url, "domcontentloaded")]
    assert unexpected_page.visited == []
    assert context.closed is True


def test_wechat_video_publisher_reuses_existing_playlet_tab(tmp_path: Path, monkeypatch):
    uploaded_pages = []

    class FakePage:
        def __init__(self, url):
            self.url = url
            self.visited = []

        def goto(self, url, wait_until=None):
            self.visited.append((url, wait_until))

        def wait_for_timeout(self, _timeout):
            return None

    playlet_page = FakePage(WeChatVideoPublisher.playlet_url)
    unexpected_page = FakePage("about:blank")

    class FakeContext:
        pages = [playlet_page]

        def new_page(self):
            self.pages.append(unexpected_page)
            return unexpected_page

    monkeypatch.setattr(
        WeChatVideoPublisher,
        "_upload_playlet",
        lambda self, page, media_files, title, summary, metadata, timeout_error: uploaded_pages.append(page),
    )
    publisher = get_publisher("WECHAT_VIDEO", ChromeController("chrome", tmp_path), account_id="media-1")

    page = publisher._open_publish_page(FakeContext(), WeChatVideoPublisher.playlet_url)
    publisher._upload_playlet(page, [tmp_path / "001.mp4"], "神医归来", None, {}, TimeoutError)

    assert page is playlet_page
    assert uploaded_pages == [playlet_page]
    assert playlet_page.visited == []
    assert unexpected_page not in FakeContext.pages


def test_wechat_video_publisher_falls_back_when_cdp_attach_fails(tmp_path: Path, monkeypatch):
    uploaded_pages = []
    launched = []
    terminated = []

    class FakeProcess:
        def poll(self):
            return None

        def terminate(self):
            terminated.append(True)

    class FakePage:
        url = "about:blank"

        def goto(self, url, wait_until=None):
            self.url = url

        def wait_for_timeout(self, _timeout):
            return None

    class FakeContext:
        def __init__(self):
            self.pages = [FakePage()]
            self.closed = False

        def new_page(self):
            page = FakePage()
            self.pages.append(page)
            return page

        def close(self):
            self.closed = True

    fallback_context = FakeContext()

    class FakeChromium:
        def connect_over_cdp(self, _endpoint_url):
            raise RuntimeError("cdp unavailable")

        def launch_persistent_context(self, user_data_dir, executable_path=None, headless=False, args=None):
            launched.append((user_data_dir, executable_path, headless, args))
            return fallback_context

    class FakePlaywright:
        chromium = FakeChromium()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr(
        "aidrama_desktop.platforms.wechat_video.available_remote_debugging_port",
        lambda: 9333,
    )
    monkeypatch.setattr("aidrama_desktop.platforms.wechat_video.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: FakePlaywright())
    monkeypatch.setattr(
        WeChatVideoPublisher,
        "_upload_playlet",
        lambda self, page, media_files, title, summary, metadata, timeout_error: uploaded_pages.append(page),
    )
    chrome = ChromeController("chrome", tmp_path)
    monkeypatch.setattr(chrome, "open_profile", lambda profile_dir, url, remote_debugging_port=None: FakeProcess())
    publisher = get_publisher("WECHAT_VIDEO", chrome, account_id="media-1")

    result = publisher.publish([tmp_path / "001.mp4"], "神医归来", metadata={"coverFile": tmp_path / "cover.jpg"})

    assert result == "wechat-playlet:神医归来:1"
    assert terminated == [True]
    assert launched == [
        (
            str(tmp_path / "wechat_video" / "media-1"),
            "chrome",
            False,
            ["--no-first-run", "--disable-default-apps", "--disable-session-crashed-bubble"],
        )
    ]
    assert uploaded_pages == [fallback_context.pages[0]]
    assert fallback_context.closed is True


def test_wechat_video_publisher_sets_playlet_monetization_and_free_episode_count(tmp_path: Path, monkeypatch):
    fills = []
    monetization = []
    files = []
    agreement_clicks = []
    entry_clicks = []
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    class FakeLocator:
        def __init__(self, kind="other"):
            self.kind = kind

        def click(self, timeout=None):
            if self.kind == "agreement":
                agreement_clicks.append(timeout)
            if self.kind == "entry":
                entry_clicks.append(timeout)
            return None

    class FakePage:
        def get_by_text(self, pattern):
            self.pattern = pattern
            return self

        @property
        def first(self):
            if "已阅读并同意" in self.pattern.pattern:
                return FakeLocator("agreement")
            if "上架剧目" in self.pattern.pattern:
                return FakeLocator("entry")
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
    assert agreement_clicks == [3000]
    assert entry_clicks == [5000]
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
    assert "--remote-debugging-address=127.0.0.1" in calls[0]
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
