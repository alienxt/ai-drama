import inspect
import re
from pathlib import Path

import pytest

from aidrama_desktop.browser.chrome import ChromeController
from aidrama_desktop.platforms.registry import get_publisher
from aidrama_desktop.platforms.wechat_video import (
    PLAYLET_EPISODE_UPLOAD_MAX_WAIT_SECONDS,
    WeChatVideoPublisher,
    remote_debugging_port_for_profile,
)


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
    assert opened == [(profile_dir, "about:blank", port)]
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
    assert opened == [(profile_dir, "about:blank", port)]
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


def test_wechat_video_publisher_limits_playlet_summary_to_100_chars(tmp_path: Path):
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")
    long_summary = "命运反转" * 30

    summary = publisher._playlet_summary("穆家有女镇山河", long_summary, {})

    assert len(summary) == 100
    assert summary == long_summary[:94] + "......"


def test_wechat_video_publisher_extracts_structured_playlet_summary_body(tmp_path: Path):
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")
    raw_summary = (
        "标题：穆家有女初封将\n\n"
        "简介：\n"
        "镇国大将军之女穆倾凰倾心辅佐夫君沈南辰仕途登顶，安稳相守十载。"
        "偶然间她发现府中少年身具穆家独有的火焰血脉印记，知晓这才是自己失散多年的亲生儿子穆野。"
        "穆倾凰静心筹谋，悉心教导培养亲子。秋猎盛会之上，她当众厘清血脉渊源，以实情证身份，"
        "平定朝堂风波，肃清朝堂与府中纷乱。\n\n"
        "集数：49集"
    )

    summary = publisher._playlet_summary("穆家有女镇山河", None, {"summary": raw_summary})

    assert len(summary) == 100
    assert summary.startswith("镇国大将军之女穆倾凰")
    assert summary.endswith("......")
    assert "标题：" not in summary
    assert "简介：" not in summary
    assert "集数：" not in summary


def test_wechat_video_publisher_uses_fallback_playlet_summary(tmp_path: Path):
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    summary = publisher._playlet_summary("穆家有女镇山河", None, {})

    assert summary == "《穆家有女镇山河》讲述人物在命运转折中的情感与成长故事。"
    assert len(summary) <= 100


def test_wechat_video_publisher_fills_text_field_near_summary_label(tmp_path: Path):
    calls = []
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    class FakePage:
        def evaluate(self, script, payload):
            calls.append((script, payload))
            return {"filled": True, "tagName": "TEXTAREA", "value": "一段简介"}

    assert publisher._fill_text_field_near_text(
        FakePage(),
        [re.compile("剧目简介")],
        "一段简介",
        TimeoutError,
        "剧目简介",
    )
    assert calls[0][1] == {"patterns": ["剧目简介"], "value": "一段简介"}
    assert "HTMLTextAreaElement.prototype" in calls[0][0]


def test_wechat_video_publisher_fills_weui_textarea_by_exact_label(tmp_path: Path):
    calls = []
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    class FakePage:
        def evaluate(self, script, payload):
            calls.append((script, payload))
            return {"filled": True, "label": "剧目简介", "value": "一段简介"}

    assert publisher._fill_weui_textarea_by_label(FakePage(), "剧目简介", "一段简介", TimeoutError)
    script, payload = calls[0]
    assert payload == {"label": "剧目简介", "value": "一段简介"}
    assert ".weui-desktop-form__control-group" in script
    assert "label.weui-desktop-form__label" in script
    assert "textarea.weui-desktop-form__textarea" in script
    assert "async ({ label, value })" in script
    assert "textarea.value === value" in script


def test_wechat_video_publisher_fills_weui_input_by_label_and_verifies_value(tmp_path: Path):
    calls = []
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    class FakePage:
        def evaluate(self, script, payload):
            calls.append((script, payload))
            return {"filled": True, "value": "27"}

    assert publisher._fill_weui_input_by_label(FakePage(), ["总集数"], "27", TimeoutError, "总集数")
    script, payload = calls[0]
    assert payload == {"labels": ["总集数"], "value": "27"}
    assert ".weui-desktop-form__control-group" in script
    assert ".cost_title" in script
    assert "input[type=\"text\"]" in script


def test_wechat_video_publisher_finally_ensures_playlet_form_fields(tmp_path: Path):
    calls = []
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    class FakePage:
        def evaluate(self, script, payload):
            calls.append((script, payload))
            return {"missing": []}

    publisher._ensure_playlet_form_fields(FakePage(), "剧名", "简介", 27, 6, "乙方公司", "3", TimeoutError)
    script, payload = calls[0]
    names = [field["name"] for field in payload["fields"]]
    assert names == ["剧目名称", "剧目简介", "总集数", "试看集数", "制作方名称", "剧目制作成本"]
    assert "document.execCommand('insertText'" in script
    assert "missing" in script


def test_wechat_video_publisher_advances_to_file_step_after_uploads(tmp_path: Path):
    calls = []
    cover = tmp_path / "fengmian.jpg"
    purchase = tmp_path / "purchase.png"
    rights = tmp_path / "rights.png"
    cost = tmp_path / "cost.png"
    for path in (cover, purchase, rights, cost):
        path.write_bytes(b"image")
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    class FakePage:
        def evaluate(self, script, payload=None):
            calls.append((script, payload))
            if isinstance(payload, list):
                return {"missing": []}
            if ".weui-desktop-icon-checkbox" in script:
                return {"accepted": True, "nextClicked": True}
            if "剧集文件选取" in script:
                return True
            return {}

        def wait_for_timeout(self, timeout):
            calls.append(("wait", timeout))

    publisher._advance_playlet_to_file_step(
        FakePage(),
        {
            "coverFile": cover,
            "buyDramaContractImages": [purchase],
            "rightsStatementImages": [rights],
            "costConfigReportImages": [cost],
        },
        TimeoutError,
    )

    upload_payload = next(payload for script, payload in calls if isinstance(payload, list))
    assert [item["name"] for item in upload_payload] == ["fengmian.jpg", "purchase.png", "rights.png", "cost.png"]
    assert any(".weui-desktop-icon-checkbox" in script for script, payload in calls if isinstance(script, str))
    assert any("剧集文件选取" in script for script, payload in calls if isinstance(script, str))


def test_wechat_video_publisher_notice_script_uses_footer_and_next_button(tmp_path: Path):
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")
    script = publisher._accept_playlet_notice_and_click_next_script()

    assert ".form_footer" in script
    assert ".weui-desktop-icon-checkbox" in script
    assert ".next_btn button.weui-desktop-btn_primary" in script
    assert "mouseClick(notice)" not in script


def test_wechat_video_publisher_accepts_notice_with_footer_locators(tmp_path: Path):
    calls = []
    accepted = {"value": False}
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    class FakeLocator:
        def __init__(self, kind):
            self.kind = kind

        @property
        def first(self):
            return self

        def filter(self, has_text=None):
            calls.append((f"{self.kind}.filter", has_text.pattern if hasattr(has_text, "pattern") else has_text))
            return self

        def count(self):
            if self.kind == "next":
                return 1 if accepted["value"] else 0
            return 1 if self.kind == "icon" else 0

        def click(self, timeout=None, force=None):
            calls.append((f"{self.kind}.click", timeout, force))
            if self.kind == "icon":
                accepted["value"] = True

    class FakePage:
        def locator(self, selector):
            calls.append(("locator", selector))
            if selector == ".next_btn button.weui-desktop-btn_primary":
                return FakeLocator("next")
            if selector == ".form_footer .weui-desktop-icon-checkbox":
                return FakeLocator("icon")
            return FakeLocator("other")

        def wait_for_timeout(self, timeout):
            calls.append(("wait", timeout))

    assert publisher._accept_playlet_notice_and_click_next_with_locators(FakePage(), TimeoutError) == {
        "accepted": True,
        "nextClicked": True,
    }
    assert ("icon.click", 3000, True) in calls
    assert ("next.click", 5000, True) in calls
    assert not any(call[0] == "label.click" for call in calls)


def test_wechat_video_publisher_file_name_wait_is_soft(tmp_path: Path):
    image = tmp_path / "purchase.png"
    image.write_bytes(b"image")
    calls = []
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    class FakePage:
        def evaluate(self, script, payload):
            calls.append((script, payload))
            return {"missing": ["purchase.png"]}

        def wait_for_timeout(self, timeout):
            calls.append(("wait", timeout))

    publisher._wait_for_playlet_upload_file_names(FakePage(), [image], TimeoutError, attempts=2)

    assert len([call for call in calls if isinstance(call[1], list)]) == 2


def test_wechat_video_publisher_uploads_playlet_episode_files_with_video_input(tmp_path: Path):
    calls = []
    videos = []
    for index in range(1, 4):
        path = tmp_path / f"短剧-第{index}集.mp4"
        path.write_bytes(b"video")
        videos.append(path)
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    class FakeLocator:
        @property
        def first(self):
            return self

        def count(self):
            return 1

        def set_input_files(self, paths):
            calls.append(("set_input_files", paths))

    class FakePage:
        def locator(self, selector):
            calls.append(("locator", selector))
            return FakeLocator()

        def evaluate(self, script, payload):
            calls.append(("evaluate", payload))
            if isinstance(payload, dict) and "expectedCount" in payload:
                return {"complete": True, "uploaded": 3, "total": 3}
            return {}

        def wait_for_timeout(self, timeout):
            calls.append(("wait", timeout))

    publisher._upload_playlet_episode_files(FakePage(), videos, 3, TimeoutError)

    assert ("set_input_files", [str(path) for path in videos]) in calls
    assert any(call[0] == "evaluate" and call[1]["expectedCount"] == 3 for call in calls)


def test_wechat_video_publisher_waits_for_episode_upload_progress(tmp_path: Path):
    video = tmp_path / "短剧-第1集.mp4"
    video.write_bytes(b"video")
    calls = []
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    class FakePage:
        def evaluate(self, script, payload):
            calls.append((script, payload))
            return {"complete": len(calls) >= 2, "uploaded": len(calls), "total": 1}

        def wait_for_timeout(self, timeout):
            calls.append(("wait", timeout))

    publisher._wait_for_playlet_episode_uploads(
        FakePage(),
        1,
        [video],
        TimeoutError,
        max_wait_seconds=30,
        check_interval_ms=10_000,
    )

    assert len([call for call in calls if isinstance(call[1], dict)]) == 2


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
    assert opened == [(profile_dir, "about:blank", port)]
    assert connected == [f"http://127.0.0.1:{port}"]
    assert uploaded_pages == [fallback_context.pages[0]]


def test_wechat_video_publisher_sets_playlet_monetization_and_free_episode_count(tmp_path: Path, monkeypatch):
    fills = []
    monetization = []
    files = []
    material_uploads = []
    weui_summary_fields = []
    summary_fields = []
    field_fills = []
    final_ensures = []
    advances = []
    video_uploads = []
    review_steps = []
    submit_steps = []
    events = []
    agreement_clicks = []
    entry_clicks = []
    option_clicks = []
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")
    purchase_image = tmp_path / "purchase.png"
    rights_image = tmp_path / "rights.png"
    cost_image = tmp_path / "cost.png"
    purchase_image.write_bytes(b"purchase")
    rights_image.write_bytes(b"rights")
    cost_image.write_bytes(b"cost")

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
                events.append(f"option:{self.pattern.pattern}")
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
        lambda page, labels, value: fills.append((labels, value)) or True,
    )
    monkeypatch.setattr(
        publisher,
        "_fill_playlet_field",
        lambda page, labels, value, timeout_error, field_label, required=False: (
            events.append(f"field:{field_label}"),
            field_fills.append((field_label, labels, value, required)),
            True,
        )[-1],
    )
    monkeypatch.setattr(
        publisher,
        "_fill_weui_textarea_by_label",
        lambda page, label, value, timeout_error: (
            events.append("summary"),
            weui_summary_fields.append((label, value)),
            True,
        )[-1],
    )
    monkeypatch.setattr(
        publisher,
        "_fill_text_field_near_text",
        lambda page, label_patterns, value, timeout_error, field_label: summary_fields.append(
            (field_label, value, [pattern.pattern for pattern in label_patterns])
        )
        or True,
    )
    monkeypatch.setattr(
        publisher,
        "_set_file_input",
        lambda page, target_files, button_pattern, timeout_error: files.append(target_files),
    )
    monkeypatch.setattr(
        publisher,
        "_set_file_input_near_text",
        lambda page, target_files, label_patterns, timeout_error, field_label: material_uploads.append(
            (field_label, target_files, [pattern.pattern for pattern in label_patterns])
        ),
    )
    monkeypatch.setattr(
        publisher,
        "_set_monetization_type",
        lambda page, value, timeout_error: events.append("monetization") or monetization.append(value),
    )
    monkeypatch.setattr(
        publisher,
        "_ensure_playlet_form_fields",
        lambda page, title, summary, episode_count, free_episode_count, producer_name, production_cost, timeout_error: final_ensures.append(
            (title, summary, episode_count, free_episode_count, producer_name, production_cost)
        ),
    )
    monkeypatch.setattr(
        publisher,
        "_advance_playlet_to_file_step",
        lambda page, metadata, timeout_error: advances.append(metadata),
    )
    monkeypatch.setattr(
        publisher,
        "_upload_playlet_episode_files",
        lambda page, media_files, episode_count, timeout_error: video_uploads.append((media_files, episode_count)),
    )
    monkeypatch.setattr(
        publisher,
        "_advance_playlet_to_confirmation_review",
        lambda page, timeout_error: review_steps.append(page),
    )
    monkeypatch.setattr(
        publisher,
        "_submit_playlet_and_wait_for_success",
        lambda page, timeout_error: submit_steps.append(page),
    )
    page = FakePage()
    publisher._upload_playlet(
        page,
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
            "producerName": "乙方公司",
            "productionCostWan": 3,
            "buyDramaContractImages": [purchase_image],
            "rightsStatementImages": [rights_image],
            "costConfigReportImages": [cost_image],
        },
        TimeoutError,
    )

    assert monetization == ["IAA广告变现"]
    assert agreement_clicks == [3000]
    assert entry_clicks == [5000]
    assert any(value == "神医归来AI" and "剧目名称" in labels for field, labels, value, required in field_fills)
    assert weui_summary_fields == [("剧目简介", "简介")]
    assert summary_fields == []
    assert not any(value == "简介" and "剧目简介" in labels for labels, value in fills)
    assert any(field == "总集数" and value == "27" for field, labels, value, required in field_fills)
    assert any(field == "试看集数" and value == "6" for field, labels, value, required in field_fills)
    assert any(field == "制作方名称" and value == "乙方公司" for field, labels, value, required in field_fills)
    assert any(field == "剧目制作成本" and value == "3" for field, labels, value, required in field_fills)
    assert final_ensures == [("神医归来AI", "简介", 27, 6, "乙方公司", "3")]
    assert len(advances) == 1
    assert video_uploads == [([tmp_path / "001.mp4"], 27)]
    assert review_steps == [page]
    assert submit_steps == [page]
    assert "^数字真人$" in option_clicks
    assert "AI内容声明|AI\\s*内容声明|AI生成|AI\\s*生成" in option_clicks
    assert any("版权方/授权播出方" in pattern for pattern in option_clicks)
    assert "^其他微短剧$" in option_clicks
    assert events.index("monetization") > events.index("option:^其他微短剧$")
    assert events.index("field:剧目名称") > events.index("monetization")
    assert events.index("field:剧目名称") > events.index("option:^其他微短剧$")
    assert events.index("summary") > events.index("option:^其他微短剧$")
    assert material_uploads == [
        ("剧目海报", tmp_path / "cover.jpg", ["剧目海报", "海报", "封面"]),
        (
            "剧目制作证明材料",
            [purchase_image, rights_image],
            ["剧目制作证明材料", "制作证明材料", "剧目制作合同"],
        ),
        ("成本配置比例情况报告", [cost_image], ["成本配置比例情况报告", "成本配置比例", "成本配置报告"]),
    ]
    assert files == []


def test_wechat_video_publisher_clicks_ai_statement_switch_control(tmp_path: Path):
    clicked = []
    checked = {"value": False}
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    class FakeLocator:
        def __init__(self, selector):
            self.selector = selector

        @property
        def first(self):
            return self

        def count(self):
            return 1

        def is_checked(self):
            return checked["value"]

        def click(self, timeout=None, force=False):
            clicked.append((self.selector, timeout, force))
            if "switch" in self.selector:
                checked["value"] = True

    class FakePage:
        def locator(self, selector):
            return FakeLocator(selector)

        def wait_for_timeout(self, _timeout):
            return None

        def evaluate(self, _script, _payload):
            raise AssertionError("should not use DOM helper after real switch click succeeds")

        def get_by_text(self, pattern):
            raise AssertionError(f"unexpected text fallback: {pattern.pattern}")

    publisher._set_ai_content_statement(FakePage(), TimeoutError)

    assert checked["value"]
    assert clicked == [(".speedupaudit_box label.switch_speedupaudit", 2500, True)]


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
    assert "speedupaudit_box" in evaluated[0][0]
    assert "switch_speedupaudit input.weui-desktop-switch__input" in evaluated[0][0]


def test_wechat_video_publisher_retries_failed_playlet_episode_uploads(tmp_path: Path):
    video = tmp_path / "穆家有女镇山河-第16集.mp4"
    video.write_text("fake-video")
    states = [
        {"uploaded": 46, "total": 49, "failedCount": 3, "failedNames": [video.name], "errorText": ""},
        {"uploaded": 49, "total": 49, "failedCount": 0, "complete": True, "errorText": ""},
    ]
    calls = []
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    class FakePage:
        def evaluate(self, script, payload=None):
            calls.append(("evaluate", payload, script))
            if "retry.click" in script:
                return {"clicked": 3, "names": [video.name]}
            state = states.pop(0)
            state.setdefault("visibleNames", 49)
            state.setdefault("complete", False)
            return state

        def wait_for_timeout(self, timeout):
            calls.append(("wait", timeout, ""))

    publisher._wait_for_playlet_episode_uploads(
        FakePage(),
        49,
        [video],
        TimeoutError,
        max_wait_seconds=50,
        check_interval_ms=10_000,
    )

    assert any(call[0] == "evaluate" and call[1] is None and "retry.click" in call[2] for call in calls)
    assert ("wait", 10000, "") in calls
    assert states == []


def test_wechat_video_publisher_retries_failed_playlet_episode_uploads_inside_frame(tmp_path: Path):
    video = tmp_path / "穆家有女镇山河-第17集.mp4"
    video.write_text("fake-video")
    frame_states = [
        {
            "uploaded": 36,
            "total": 49,
            "hasProgress": True,
            "rowCount": 50,
            "failedCount": 13,
            "retryableCount": 13,
            "failedNames": [video.name],
            "errorText": "",
        },
        {
            "uploaded": 49,
            "total": 49,
            "hasProgress": True,
            "rowCount": 50,
            "failedCount": 0,
            "successCount": 49,
            "complete": True,
            "errorText": "",
        },
    ]
    calls = []
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    class FakeFrame:
        def __init__(self, name):
            self.name = name

        def evaluate(self, script, payload=None):
            calls.append((self.name, "evaluate", payload, script))
            if "retry.click" in script:
                return {"clicked": 13 if self.name == "upload-frame" else 0, "names": [video.name]}
            if self.name == "top-frame":
                return {"uploaded": 0, "total": 49, "hasProgress": False, "rowCount": 0, "failedCount": 0}
            return frame_states.pop(0)

    class FakePage:
        frames = [FakeFrame("top-frame"), FakeFrame("upload-frame")]

        def wait_for_timeout(self, timeout):
            calls.append(("page", "wait", timeout, ""))

    publisher._wait_for_playlet_episode_uploads(
        FakePage(),
        49,
        [video],
        TimeoutError,
        max_wait_seconds=50,
        check_interval_ms=10_000,
    )

    assert any(call[0] == "upload-frame" and "retry.click" in call[3] for call in calls)
    assert ("page", "wait", 10000, "") in calls
    assert frame_states == []


def test_wechat_video_publisher_does_not_complete_playlet_video_upload_by_visible_names():
    script = WeChatVideoPublisher._playlet_episode_upload_state_script()

    assert "visibleNames >= expectedCount" not in script
    assert "successRows.length >= expectedCount" in script


def test_wechat_video_publisher_fails_fast_for_playlet_video_quality_error(tmp_path: Path):
    video = tmp_path / "穆家有女镇山河-第16集.mp4"
    video.write_text("fake-video")
    calls = []
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    class FakePage:
        def evaluate(self, script, payload=None):
            calls.append(("evaluate", script))
            return {"uploaded": 46, "total": 49, "failedCount": 3, "errorText": "文件码率低于4Mbps"}

        def wait_for_timeout(self, timeout):
            calls.append(("wait", timeout))

    with pytest.raises(RuntimeError, match="文件码率低于4Mbps"):
        publisher._wait_for_playlet_episode_uploads(
            FakePage(),
            49,
            [video],
            TimeoutError,
            max_wait_seconds=50,
            check_interval_ms=10_000,
        )

    assert not any(call[0] == "evaluate" and "retry.click" in call[1] for call in calls)


def test_wechat_video_publisher_times_out_after_waiting_for_playlet_episode_uploads(tmp_path: Path):
    video = tmp_path / "穆家有女镇山河-第17集.mp4"
    video.write_text("fake-video")
    waits = []
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    class FakePage:
        def evaluate(self, script, payload=None):
            return {
                "uploaded": 36,
                "total": 49,
                "hasProgress": True,
                "rowCount": 50,
                "failedCount": 0,
                "successCount": 36,
                "complete": False,
                "errorText": "",
            }

        def wait_for_timeout(self, timeout):
            waits.append(timeout)

    with pytest.raises(RuntimeError, match="超过 1 分钟仍未完成：36/49"):
        publisher._wait_for_playlet_episode_uploads(
            FakePage(),
            49,
            [video],
            TimeoutError,
            max_wait_seconds=20,
            check_interval_ms=10_000,
        )

    assert waits == [10_000, 10_000]


def test_wechat_video_publisher_waits_30_minutes_by_default_for_playlet_episode_uploads():
    kwdefaults = WeChatVideoPublisher._wait_for_playlet_episode_uploads.__kwdefaults__ or {}

    assert kwdefaults["max_wait_seconds"] == PLAYLET_EPISODE_UPLOAD_MAX_WAIT_SECONDS
    assert PLAYLET_EPISODE_UPLOAD_MAX_WAIT_SECONDS == 30 * 60


def test_wechat_video_publisher_does_not_treat_video_requirement_text_as_upload_error():
    script = WeChatVideoPublisher._playlet_episode_upload_state_script()

    assert "分辨率不低于" not in script
    assert "码率不低于" not in script
    assert "文件码率低于" in script


def test_wechat_video_publisher_does_not_complete_without_submit_confirmation(tmp_path: Path):
    clicks = []
    waits = []
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    class FakeLocator:
        def __init__(self, pattern):
            self.pattern = pattern

        def click(self, timeout=None):
            clicks.append((self.pattern.pattern, timeout))

        def wait_for(self, timeout=None):
            waits.append((self.pattern.pattern, timeout))
            raise TimeoutError("no success")

        def count(self):
            return 0

    class FakePage:
        def get_by_text(self, pattern):
            self.pattern = pattern
            return self

        @property
        def first(self):
            return FakeLocator(self.pattern)

        def wait_for_timeout(self, _timeout):
            return None

    with pytest.raises(RuntimeError, match="未确认提交成功"):
        publisher._submit_playlet_and_wait_for_success(FakePage(), TimeoutError, success_timeout_seconds=0)

    assert any("确认提审" in pattern for pattern, _timeout in clicks)


def test_wechat_video_publisher_clicks_second_review_submit_button(tmp_path: Path, monkeypatch):
    clicks = []
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    checks = iter([False, True])
    monkeypatch.setattr(
        publisher,
        "_page_has_text",
        lambda page, pattern: next(checks, True),
    )
    monkeypatch.setattr(
        publisher,
        "_click_playlet_submit_button",
        lambda page, timeout_error: clicks.append("确认提审") or True,
    )

    publisher._advance_playlet_to_confirmation_review(object(), TimeoutError)

    assert clicks == ["确认提审"]


def test_wechat_video_publisher_submit_clicks_until_success(tmp_path: Path, monkeypatch):
    clicks = []
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    monkeypatch.setattr(
        publisher,
        "_page_has_text",
        lambda page, pattern: len(clicks) >= 2,
    )
    monkeypatch.setattr(
        publisher,
        "_click_playlet_submit_button",
        lambda page, timeout_error: clicks.append("确认提审") or True,
    )
    monkeypatch.setattr(publisher, "_click_confirm_if_available", lambda page, timeout_error: None)

    publisher._submit_playlet_and_wait_for_success(object(), TimeoutError, success_timeout_seconds=1)

    assert clicks == ["确认提审", "确认提审"]


def test_wechat_video_publisher_treats_closed_page_after_final_submit_as_success(tmp_path: Path, monkeypatch):
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    monkeypatch.setattr(publisher, "_page_has_text", lambda page, pattern: False)

    def close_after_submit(page, timeout_error):
        raise RuntimeError("浏览器页面已关闭，无法点击视频号确认提审按钮")

    monkeypatch.setattr(publisher, "_click_playlet_submit_button", close_after_submit)

    publisher._submit_playlet_and_wait_for_success(object(), TimeoutError, success_timeout_seconds=1)


def test_wechat_video_publisher_treats_blank_page_after_final_submit_as_success(tmp_path: Path, monkeypatch):
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    class FakePage:
        url = "https://channels.weixin.qq.com/platform/native-drama-post"

    page = FakePage()

    monkeypatch.setattr(publisher, "_page_has_text", lambda page, pattern: False)

    def submit_and_open_blank(page, timeout_error):
        page.url = "about:blank"
        return True

    monkeypatch.setattr(publisher, "_click_playlet_submit_button", submit_and_open_blank)
    monkeypatch.setattr(publisher, "_click_confirm_if_available", lambda page, timeout_error: None)

    publisher._submit_playlet_and_wait_for_success(page, TimeoutError, success_timeout_seconds=1)


def test_wechat_video_publisher_success_text_can_be_inside_frame(tmp_path: Path):
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    class FakeLocator:
        def __init__(self, count):
            self._count = count

        def count(self):
            return self._count

    class FakeTarget:
        def __init__(self, count):
            self.count = count

        def get_by_text(self, _pattern):
            return self

        @property
        def first(self):
            return FakeLocator(self.count)

    class FakePage:
        frames = [FakeTarget(0), FakeTarget(1)]

    assert publisher._page_has_text(FakePage(), re.compile("提审成功"))


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


def test_wechat_video_publisher_sets_material_file_input_near_target_label(tmp_path: Path):
    calls = []
    purchase_image = tmp_path / "purchase.png"
    cost_image = tmp_path / "cost.png"
    purchase_image.write_bytes(b"purchase")
    cost_image.write_bytes(b"cost")
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    class FakeSession:
        def send(self, method, payload):
            calls.append((method, payload))
            if method == "DOM.getDocument":
                return {"root": {"nodeId": 1}}
            if method == "DOM.querySelector":
                return {"nodeId": 12}
            return {}

    class FakeContext:
        def new_cdp_session(self, page):
            calls.append(("new_cdp_session", page))
            return FakeSession()

    class FakePage:
        context = FakeContext()

        def evaluate(self, script, payload):
            calls.append(("evaluate", payload))
            if isinstance(payload, dict) and "inputMarker" in payload:
                return {
                    "inputMarked": True,
                    "inputMarker": payload["inputMarker"],
                    "buttonMarker": payload["buttonMarker"],
                    "fieldMarker": payload["fieldMarker"],
                }
            if isinstance(payload, dict) and "files" in payload:
                return {"visibleAccepted": True}
            return True

    page = FakePage()

    publisher._set_file_input_near_text(
        page,
        [purchase_image, cost_image],
        [re.compile("剧目制作证明材料")],
        TimeoutError,
        "剧目制作证明材料",
    )

    marker_payloads = [
        payload
        for method, payload in calls
        if method == "evaluate" and isinstance(payload, dict) and "inputMarker" in payload
    ]
    marker_payload = marker_payloads[-1]
    marker = marker_payload["inputMarker"]
    assert marker_payload["patterns"] == ["剧目制作证明材料"]
    assert ("DOM.querySelector", {"nodeId": 1, "selector": f'input[type="file"][data-aidrama-file-input="{marker}"]'}) in calls
    assert (
        "DOM.setFileInputFiles",
        {"nodeId": 12, "files": [str(purchase_image.resolve()), str(cost_image.resolve())]},
    ) in calls


def test_wechat_video_publisher_sets_hidden_input_before_clicking_upload_button(tmp_path: Path):
    calls = []
    purchase_image = tmp_path / "purchase.png"
    purchase_image.write_bytes(b"purchase")
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    class FakeSession:
        def send(self, method, payload):
            calls.append((method, payload))
            if method == "DOM.getDocument":
                return {"root": {"nodeId": 1}}
            if method == "DOM.querySelector":
                return {"nodeId": 12}
            return {}

    class FakeContext:
        def new_cdp_session(self, page):
            return FakeSession()

    class FakePage:
        context = FakeContext()

        def evaluate(self, script, payload):
            calls.append(("evaluate", payload))
            if isinstance(payload, dict) and "inputMarker" in payload:
                return {
                    "inputMarked": True,
                    "inputMarker": payload["inputMarker"],
                    "buttonMarker": payload["buttonMarker"],
                    "fieldMarker": payload["fieldMarker"],
                }
            if isinstance(payload, dict) and "files" in payload:
                return {"visibleAccepted": True, "explicitFileName": True}
            return True

    publisher._set_file_input_near_text(
        FakePage(),
        [purchase_image],
        [re.compile("剧目制作证明材料")],
        TimeoutError,
        "剧目制作证明材料",
    )

    set_file_index = next(index for index, call in enumerate(calls) if call[0] == "DOM.setFileInputFiles")
    acceptance_index = next(
        index
        for index, call in enumerate(calls)
        if call[0] == "evaluate" and isinstance(call[1], dict) and "files" in call[1]
    )
    assert set_file_index < acceptance_index
    assert not any(call[0] == "wait_for_timeout" for call in calls)


def test_wechat_video_publisher_prefers_material_file_chooser_button(tmp_path: Path):
    calls = []
    purchase_image = tmp_path / "purchase.png"
    purchase_image.write_bytes(b"purchase")
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    class FakeFileChooser:
        def set_files(self, paths):
            calls.append(("chooser.set_files", paths))

    class FakeChooserContext:
        value = FakeFileChooser()

        def __enter__(self):
            calls.append(("expect_file_chooser.enter", None))
            return self

        def __exit__(self, exc_type, exc, traceback):
            calls.append(("expect_file_chooser.exit", exc_type))
            return False

    class FakeLocator:
        @property
        def first(self):
            return self

        def click(self, timeout=None):
            calls.append(("button.click", timeout))

    class FakePage:
        def evaluate(self, script, payload):
            calls.append(("evaluate", payload))
            if isinstance(payload, dict) and "inputMarker" in payload:
                return {
                    "inputMarked": True,
                    "inputMarker": payload["inputMarker"],
                    "buttonMarker": payload["buttonMarker"],
                    "fieldMarker": payload["fieldMarker"],
                }
            if isinstance(payload, dict) and "files" in payload:
                return {"visibleAccepted": True, "nameVisible": True}
            return True

        def locator(self, selector):
            calls.append(("locator", selector))
            return FakeLocator()

        def expect_file_chooser(self, timeout=None):
            calls.append(("expect_file_chooser", timeout))
            return FakeChooserContext()

        def wait_for_timeout(self, timeout):
            calls.append(("wait_for_timeout", timeout))

    publisher._set_file_input_near_text(
        FakePage(),
        [purchase_image],
        [re.compile("剧目制作证明材料")],
        TimeoutError,
        "剧目制作证明材料",
    )

    assert ("chooser.set_files", [str(purchase_image)]) in calls
    assert not any(call[0] == "DOM.setFileInputFiles" for call in calls)


def test_wechat_video_publisher_uploads_material_with_visible_button_without_input(tmp_path: Path):
    calls = []
    purchase_image = tmp_path / "purchase.png"
    purchase_image.write_bytes(b"purchase")
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    class FakeFileChooser:
        def set_files(self, paths):
            calls.append(("chooser.set_files", paths))

    class FakeChooserContext:
        value = FakeFileChooser()

        def __enter__(self):
            calls.append(("expect_file_chooser.enter", None))
            return self

        def __exit__(self, exc_type, exc, traceback):
            calls.append(("expect_file_chooser.exit", exc_type))
            return False

    class FakeLocator:
        @property
        def first(self):
            return self

        def click(self, timeout=None):
            calls.append(("button.click", timeout))

    class FakePage:
        def evaluate(self, script, payload):
            calls.append(("evaluate", payload))
            if isinstance(payload, dict) and "buttonMarker" in payload and "inputMarker" not in payload:
                return {
                    "buttonMarked": True,
                    "buttonMarker": payload["buttonMarker"],
                    "fieldMarker": payload["fieldMarker"],
                }
            if isinstance(payload, dict) and "files" in payload:
                return {"visibleAccepted": True, "nameVisible": True}
            raise AssertionError("hidden input fallback should not be used")

        def locator(self, selector):
            calls.append(("locator", selector))
            return FakeLocator()

        def expect_file_chooser(self, timeout=None):
            calls.append(("expect_file_chooser", timeout))
            return FakeChooserContext()

        def wait_for_timeout(self, timeout):
            calls.append(("wait_for_timeout", timeout))

    publisher._set_file_input_near_text(
        FakePage(),
        [purchase_image],
        [re.compile("剧目制作证明材料")],
        TimeoutError,
        "剧目制作证明材料",
    )

    assert ("chooser.set_files", [str(purchase_image)]) in calls
    assert not any(isinstance(call[1], dict) and "inputMarker" in call[1] for call in calls if call[0] == "evaluate")


def test_wechat_video_publisher_uploads_material_by_labelled_form_group_button(tmp_path: Path):
    calls = []
    purchase_image = tmp_path / "purchase.png"
    purchase_image.write_bytes(b"purchase")
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    class FakeFileChooser:
        def set_files(self, paths):
            calls.append(("chooser.set_files", paths))

    class FakeChooserContext:
        value = FakeFileChooser()

        def __enter__(self):
            calls.append(("expect_file_chooser.enter", None))
            return self

        def __exit__(self, exc_type, exc, traceback):
            calls.append(("expect_file_chooser.exit", exc_type))
            return False

    class FakeLocator:
        def __init__(self, kind):
            self.kind = kind

        def filter(self, has_text=None):
            calls.append((f"{self.kind}.filter", has_text.pattern if hasattr(has_text, "pattern") else has_text))
            return self

        def count(self):
            calls.append((f"{self.kind}.count", None))
            return 1

        def nth(self, index):
            calls.append((f"{self.kind}.nth", index))
            return FakeLocator("group" if self.kind == "groups" else "button")

        def locator(self, selector):
            calls.append((f"{self.kind}.locator", selector))
            return FakeLocator("buttons")

        def evaluate(self, script, marker):
            calls.append((f"{self.kind}.evaluate", marker))

        def click(self, timeout=None):
            calls.append((f"{self.kind}.click", timeout))

    class FakePage:
        def locator(self, selector):
            calls.append(("page.locator", selector))
            return FakeLocator("groups")

        def expect_file_chooser(self, timeout=None):
            calls.append(("expect_file_chooser", timeout))
            return FakeChooserContext()

        def evaluate(self, script, payload):
            calls.append(("page.evaluate", payload))
            if isinstance(payload, dict) and "files" in payload:
                return {"visibleAccepted": True, "nameVisible": True}
            raise AssertionError("hidden upload scripts should not be used")

        def wait_for_timeout(self, timeout):
            calls.append(("wait_for_timeout", timeout))

    publisher._set_file_input_near_text(
        FakePage(),
        [purchase_image],
        [re.compile("剧目制作证明材料")],
        TimeoutError,
        "剧目制作证明材料",
    )

    assert ("chooser.set_files", [str(purchase_image)]) in calls
    assert any(call[0] == "group.evaluate" for call in calls)
    assert not any(isinstance(call[1], dict) and "inputMarker" in call[1] for call in calls if call[0] == "page.evaluate")


def test_wechat_video_publisher_reveals_material_upload_then_sets_hidden_input(tmp_path: Path):
    calls = []
    purchase_image = tmp_path / "purchase.png"
    purchase_image.write_bytes(b"purchase")
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    class FakeSession:
        def send(self, method, payload):
            calls.append((method, payload))
            if method == "DOM.getDocument":
                return {"root": {"nodeId": 1}}
            if method == "DOM.querySelector":
                return {"nodeId": 12}
            return {}

    class FakeContext:
        def new_cdp_session(self, page):
            calls.append(("new_cdp_session", page))
            return FakeSession()

    class FakePage:
        context = FakeContext()

        def evaluate(self, script, payload):
            calls.append(("evaluate", payload))
            if isinstance(payload, dict) and "inputMarker" in payload:
                return {
                    "inputMarked": True,
                    "inputMarker": payload["inputMarker"],
                    "buttonMarker": payload["buttonMarker"],
                    "fieldMarker": payload["fieldMarker"],
                }
            if isinstance(payload, dict) and "files" in payload:
                return {"visibleAccepted": True}
            return True

        def wait_for_timeout(self, timeout):
            calls.append(("wait_for_timeout", timeout))

    publisher._set_file_input_near_text(
        FakePage(),
        [purchase_image],
        [re.compile("剧目制作证明材料")],
        TimeoutError,
        "剧目制作证明材料",
    )

    evaluate_payloads = [payload for method, payload in calls if method == "evaluate"]
    marker_payloads = [payload for payload in evaluate_payloads if isinstance(payload, dict) and "inputMarker" in payload]
    assert len(marker_payloads) == 2
    marker_payload = marker_payloads[-1]
    assert marker_payload["patterns"] == ["剧目制作证明材料"]
    input_marker = marker_payload["inputMarker"]
    assert (
        "DOM.setFileInputFiles",
        {"nodeId": 12, "files": [str(purchase_image.resolve())]},
    ) in calls
    assert input_marker in evaluate_payloads
    assert any(
        isinstance(payload, dict) and payload.get("marker") == marker_payload["fieldMarker"]
        for payload in evaluate_payloads
    )


def test_wechat_video_publisher_rejects_material_upload_without_visible_acceptance(tmp_path: Path):
    calls = []
    purchase_image = tmp_path / "purchase.png"
    purchase_image.write_bytes(b"purchase")
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    class FakeSession:
        def send(self, method, payload):
            calls.append((method, payload))
            if method == "DOM.getDocument":
                return {"root": {"nodeId": 1}}
            if method == "DOM.querySelector":
                return {"nodeId": 12}
            return {}

    class FakeContext:
        def new_cdp_session(self, page):
            return FakeSession()

    class FakePage:
        context = FakeContext()

        def evaluate(self, script, payload):
            calls.append(("evaluate", payload))
            if isinstance(payload, dict) and "inputMarker" in payload:
                return {
                    "inputMarked": True,
                    "inputMarker": payload["inputMarker"],
                    "buttonMarker": payload["buttonMarker"],
                    "fieldMarker": payload["fieldMarker"],
                }
            if isinstance(payload, dict) and "files" in payload:
                return {"visibleAccepted": False}
            return True

        def wait_for_timeout(self, timeout):
            calls.append(("wait_for_timeout", timeout))

    try:
        publisher._set_file_input_near_text(
            FakePage(),
            [purchase_image],
            [re.compile("剧目制作证明材料")],
            TimeoutError,
            "剧目制作证明材料",
        )
    except RuntimeError as exception:
        assert "文件未被页面接收" in str(exception)
    else:
        raise AssertionError("expected material upload rejection")


def test_wechat_video_publisher_rejects_too_many_cost_report_files(tmp_path: Path):
    cost_first = tmp_path / "cost-1.png"
    cost_second = tmp_path / "cost-2.png"
    cost_first.write_bytes(b"cost")
    cost_second.write_bytes(b"cost")
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    try:
        publisher._set_file_input_near_text(
            object(),
            [cost_first, cost_second],
            [re.compile("成本配置比例情况报告")],
            TimeoutError,
            "成本配置比例情况报告",
        )
    except RuntimeError as exception:
        assert "最多支持上传 1 个文件" in str(exception)
    else:
        raise AssertionError("expected cost report upload count rejection")


def test_wechat_video_material_upload_script_matches_wechat_hidden_upload_dom(tmp_path: Path):
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    script = publisher._mark_material_upload_controls_script()
    state_source = inspect.getsource(WeChatVideoPublisher._material_upload_field_state)

    assert ".audit-form-upload" in script
    assert ".custom-file-upload" in script
    assert ".custom-image-upload" in script
    assert "file-input-hidden" in script or "input[type=\"file\"]" in script
    assert "重新选择" in script
    assert ".img_text" in state_source


def test_wechat_video_material_upload_button_script_ignores_download_links(tmp_path: Path):
    publisher = WeChatVideoPublisher(ChromeController("chrome", tmp_path), account_id="media-1")

    script = publisher._reveal_material_upload_script()

    assert '"a"' not in script
    assert "DOCUMENT_POSITION_FOLLOWING" in script
    assert "下载模版" not in script
    assert "MouseEvent('mousedown'" in script


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
