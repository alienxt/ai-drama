from pathlib import Path

from aidrama_desktop.browser.chrome import ChromeController
from aidrama_desktop.platforms.registry import get_publisher
from aidrama_desktop.platforms.wechat_video import WeChatVideoPublisher, remote_debugging_port_for_profile


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


def test_wechat_video_publisher_uses_native_drama_post_url():
    assert WeChatVideoPublisher.playlet_url == "https://channels.weixin.qq.com/platform/native-drama-post"


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


def test_wechat_video_publisher_open_login_uses_reusable_debug_port(tmp_path: Path, monkeypatch):
    opened = []
    chrome = ChromeController("chrome", tmp_path)
    publisher = get_publisher("WECHAT_VIDEO", chrome, account_id="media-1")

    monkeypatch.setattr(
        ChromeController,
        "open_profile",
        lambda self, profile_dir, url, remote_debugging_port=None: opened.append(
            (profile_dir, url, remote_debugging_port)
        ),
    )

    login_state_ref = publisher.open_login()

    profile_dir = tmp_path / "wechat_video" / "media-1"
    assert login_state_ref == str(profile_dir)
    assert opened == [(profile_dir, WeChatVideoPublisher.login_url, remote_debugging_port_for_profile(profile_dir))]


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

    class FakeBrowser:
        def __init__(self):
            self.contexts = [FakeContext()]

    class FakeChromium:
        def connect_over_cdp(self, endpoint):
            connected.append(endpoint)
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: FakePlaywright())
    monkeypatch.setattr(
        ChromeController,
        "open_profile",
        lambda self, profile_dir, url, remote_debugging_port=None: opened.append(
            (profile_dir, url, remote_debugging_port)
        ),
    )
    monkeypatch.setattr(
        WeChatVideoPublisher,
        "_upload_playlet",
        lambda self, page, media_files, title, summary, metadata, timeout_error: uploaded.append(
            (media_files, title, summary, metadata)
        ),
    )
    chrome = ChromeController("chrome", tmp_path)
    publisher = get_publisher("WECHAT_VIDEO", chrome, account_id="media-1")
    media_file = tmp_path / "001.mp4"

    result = publisher.publish([media_file], "神医归来", summary="简介", metadata={"coverFile": tmp_path / "cover.jpg"})

    assert result == "wechat-playlet:神医归来:1"
    profile_dir = tmp_path / "wechat_video" / "media-1"
    port = remote_debugging_port_for_profile(profile_dir)
    assert opened == [(profile_dir, WeChatVideoPublisher.playlet_url, port)]
    assert connected == [f"http://127.0.0.1:{port}"]
    assert visited_urls == [(WeChatVideoPublisher.playlet_url, "domcontentloaded")]
    assert uploaded == [([media_file], "神医归来", "简介", {"coverFile": tmp_path / "cover.jpg"})]


def test_wechat_video_publisher_reuses_startup_blank_page_for_playlet_publish(tmp_path: Path, monkeypatch):
    uploaded_pages = []
    opened = []
    connected = []

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

        def new_page(self):
            self.pages.append(unexpected_page)
            return unexpected_page

    context = FakeContext()

    class FakeBrowser:
        contexts = [context]

    class FakeChromium:
        def connect_over_cdp(self, endpoint):
            connected.append(endpoint)
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: FakePlaywright())
    monkeypatch.setattr(
        ChromeController,
        "open_profile",
        lambda self, profile_dir, url, remote_debugging_port=None: opened.append(
            (profile_dir, url, remote_debugging_port)
        ),
    )
    monkeypatch.setattr(
        WeChatVideoPublisher,
        "_upload_playlet",
        lambda self, page, media_files, title, summary, metadata, timeout_error: uploaded_pages.append(page),
    )
    chrome = ChromeController("chrome", tmp_path)
    publisher = get_publisher("WECHAT_VIDEO", chrome, account_id="media-1")
    media_file = tmp_path / "001.mp4"

    publisher.publish([media_file], "神医归来", metadata={"coverFile": tmp_path / "cover.jpg"})

    assert blank_page.closed is False
    assert uploaded_pages == [blank_page]
    profile_dir = tmp_path / "wechat_video" / "media-1"
    port = remote_debugging_port_for_profile(profile_dir)
    assert opened == [(profile_dir, WeChatVideoPublisher.playlet_url, port)]
    assert connected == [f"http://127.0.0.1:{port}"]
    assert blank_page.visited == [(WeChatVideoPublisher.playlet_url, "domcontentloaded")]
    assert unexpected_page.visited == []


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


def test_wechat_video_publisher_connects_to_open_profile_for_publishing(tmp_path: Path, monkeypatch):
    uploaded_pages = []
    opened = []
    connected = []

    class FakePage:
        url = "about:blank"

        def goto(self, url, wait_until=None):
            self.url = url

        def wait_for_timeout(self, _timeout):
            return None

    class FakeContext:
        def __init__(self):
            self.pages = [FakePage()]

        def new_page(self):
            page = FakePage()
            self.pages.append(page)
            return page

    fallback_context = FakeContext()

    class FakeBrowser:
        contexts = [fallback_context]

    class FakeChromium:
        def connect_over_cdp(self, endpoint):
            connected.append(endpoint)
            return FakeBrowser()

    class FakePlaywright:
        chromium = FakeChromium()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr("playwright.sync_api.sync_playwright", lambda: FakePlaywright())
    monkeypatch.setattr(
        ChromeController,
        "open_profile",
        lambda self, profile_dir, url, remote_debugging_port=None: opened.append(
            (profile_dir, url, remote_debugging_port)
        ),
    )
    monkeypatch.setattr(
        WeChatVideoPublisher,
        "_upload_playlet",
        lambda self, page, media_files, title, summary, metadata, timeout_error: uploaded_pages.append(page),
    )
    chrome = ChromeController("chrome", tmp_path)
    publisher = get_publisher("WECHAT_VIDEO", chrome, account_id="media-1")

    result = publisher.publish([tmp_path / "001.mp4"], "神医归来", metadata={"coverFile": tmp_path / "cover.jpg"})

    assert result == "wechat-playlet:神医归来:1"
    profile_dir = tmp_path / "wechat_video" / "media-1"
    port = remote_debugging_port_for_profile(profile_dir)
    assert opened == [(profile_dir, WeChatVideoPublisher.playlet_url, port)]
    assert connected == [f"http://127.0.0.1:{port}"]
    assert uploaded_pages == [fallback_context.pages[0]]


def test_wechat_video_publisher_sets_playlet_monetization_and_free_episode_count(tmp_path: Path, monkeypatch):
    fills = []
    monetization = []
    files = []
    agreement_clicks = []
    entry_clicks = []
    option_clicks = []
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    class FakeLocator:
        def __init__(self, kind="other", pattern=None):
            self.kind = kind
            self.pattern = pattern

        def click(self, timeout=None):
            if self.kind == "agreement":
                agreement_clicks.append(timeout)
            if self.kind == "entry":
                entry_clicks.append(timeout)
            if self.kind == "option":
                option_clicks.append(self.pattern.pattern)
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
            return FakeLocator("option", self.pattern)

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
            "episodeCount": 27,
        },
        TimeoutError,
    )

    assert monetization == ["IAA广告变现"]
    assert agreement_clicks == [3000]
    assert entry_clicks == [5000]
    assert any(value == "神医归来AI" and "剧目名称" in labels for labels, value in fills)
    assert any(value == "简介" and "剧目简介" in labels for labels, value in fills)
    assert any(value == "27" and "总集数" in labels for labels, value in fills)
    assert any(value == "6" and "免费集数" in labels for labels, value in fills)
    assert "^漫剧$" in option_clicks
    assert "AI内容声明|AI\\s*内容声明|AI生成|AI\\s*生成" in option_clicks
    assert any("版权方/授权播出方" in pattern for pattern in option_clicks)
    assert "^其他微短剧$" in option_clicks
    assert files == [tmp_path / "cover.jpg", [tmp_path / "001.mp4"]]


def test_wechat_video_publisher_uses_dom_helper_for_ai_statement(tmp_path: Path):
    evaluated = []
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    class FakePage:
        def evaluate(self, script, payload):
            evaluated.append((script, payload))
            return True

        def get_by_text(self, pattern):
            raise AssertionError(f"unexpected text fallback: {pattern.pattern}")

    publisher._set_ai_content_statement(FakePage(), TimeoutError)

    assert [payload for _script, payload in evaluated] == ["AI内容声明|AI\\s*内容声明|AI生成|AI\\s*生成"]


def test_wechat_video_publisher_prefers_authorized_submit_identity(tmp_path: Path):
    evaluated = []
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    combined = ["剧目制作方版权方/授权播出方", "剧目制作方/版权方/授权播出方", "剧目制作方.*版权方/授权播出方"]
    authorized = ["^版权方/授权播出方$", "版权方/授权播出方", "授权播出方"]

    class FakePage:
        def evaluate(self, script, payload):
            evaluated.append((script, payload))
            return payload != combined

        def get_by_text(self, pattern):
            raise AssertionError(f"unexpected text fallback: {pattern.pattern}")

    publisher._set_submit_identity(FakePage(), TimeoutError)

    assert [payload for _script, payload in evaluated] == [combined, authorized]


def test_wechat_video_publisher_uses_cdp_when_file_is_too_large_for_playwright(tmp_path: Path):
    calls = []
    video = tmp_path / "001.mp4"
    video.write_text("fake-video")
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    class FakeFileInput:
        def evaluate(self, script, marker):
            calls.append(("evaluate", script, marker))

    class FakeFileChooser:
        element = FakeFileInput()

        def set_files(self, _paths):
            raise RuntimeError("Cannot transfer files larger than 50Mb to a browser not co-located with the server")

    class FakeSession:
        def send(self, method, payload):
            calls.append((method, payload))
            if method == "DOM.getDocument":
                return {"root": {"nodeId": 1}}
            if method == "DOM.querySelector":
                return {"nodeId": 7}
            return {}

    class FakeContext:
        def new_cdp_session(self, page):
            calls.append(("new_cdp_session", page))
            return FakeSession()

    class FakePage:
        context = FakeContext()

    page = FakePage()

    publisher._set_file_chooser_files(page, FakeFileChooser(), str(video))

    assert ("new_cdp_session", page) in calls
    assert any(call[0] == "DOM.querySelector" for call in calls)
    assert ("DOM.setFileInputFiles", {"nodeId": 7, "files": [str(video.resolve())]}) in calls


def test_wechat_video_publisher_finds_marked_file_input_in_flattened_dom(tmp_path: Path):
    calls = []
    video = tmp_path / "001.mp4"
    video.write_text("fake-video")
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    class FakeFileInput:
        def evaluate(self, script, marker):
            calls.append(("evaluate", script, marker))

    class FakeFileChooser:
        element = FakeFileInput()

        def set_files(self, _paths):
            raise RuntimeError("Cannot transfer files larger than 50Mb to a browser not co-located with the server")

    class FakeSession:
        def send(self, method, payload):
            calls.append((method, payload))
            if method == "DOM.getDocument":
                return {"root": {"nodeId": 1}}
            if method == "DOM.querySelector":
                return {"nodeId": 0}
            if method == "DOM.getFlattenedDocument":
                marker = next(call[2] for call in calls if call[0] == "evaluate")
                return {"nodes": [{"nodeId": 9, "attributes": ["data-aidrama-file-input", marker]}]}
            return {}

    class FakeContext:
        def new_cdp_session(self, page):
            return FakeSession()

    class FakePage:
        context = FakeContext()

    publisher._set_file_chooser_files(FakePage(), FakeFileChooser(), str(video))

    assert ("DOM.setFileInputFiles", {"nodeId": 9, "files": [str(video.resolve())]}) in calls


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
