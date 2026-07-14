from pathlib import Path

import pytest

from aidrama_desktop.browser.chrome import ChromeController
from aidrama_desktop.platforms.base import PlatformPublishPaused
from aidrama_desktop.platforms.tiktok import TikTokPublisher
from aidrama_desktop.platforms.wechat_video import remote_debugging_port_for_profile


def test_tiktok_publisher_connects_to_draft_page_and_pauses_before_submit(tmp_path: Path, monkeypatch):
    opened = []
    connected = []
    filled = []

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
        TikTokPublisher,
        "_fill_draft",
        lambda self, page, media_files, title, summary, metadata, timeout_error: filled.append(
            (page, media_files, title, summary, metadata)
        ),
    )

    chrome = ChromeController("chrome", tmp_path)
    publisher = TikTokPublisher(chrome, account_id="media-tk")
    media_file = tmp_path / "001.mp4"
    media_file.write_bytes(b"video")

    with pytest.raises(PlatformPublishPaused, match="TK 表单已填写"):
        publisher.publish([media_file], "English Title", summary="English summary", metadata={"episodeCount": 1})

    profile_dir = tmp_path / "tiktok" / "media-tk"
    assert opened == [(profile_dir, "about:blank", remote_debugging_port_for_profile(profile_dir))]
    assert connected == [f"http://127.0.0.1:{remote_debugging_port_for_profile(profile_dir)}"]
    assert filled == [(fallback_context.pages[0], [media_file], "English Title", "English summary", {"episodeCount": 1})]
    assert fallback_context.pages[0].url == TikTokPublisher.draft_url


def test_tiktok_publisher_fill_draft_uses_expected_field_steps(tmp_path: Path, monkeypatch):
    calls = []
    video = tmp_path / "001.mp4"
    cover = tmp_path / "cover.jpg"
    cover_en = tmp_path / "cover-en.jpg"
    tiktok_cover_en = tmp_path / "tiktok-cover-en.jpg"
    agreement = tmp_path / "agreement.png"
    for path in (video, cover, cover_en, tiktok_cover_en, agreement):
        path.write_bytes(b"file")

    publisher = TikTokPublisher(ChromeController("chrome", tmp_path), account_id="media-tk")

    monkeypatch.setattr(
        publisher,
        "_fill_text_input",
        lambda page, field_id, value, timeout_error, field_label, required=True: calls.append(
            ("fill", field_id, value, field_label, required)
        )
        or True,
    )
    monkeypatch.setattr(
        publisher,
        "_select_first_dropdown_option",
        lambda page, field_id, timeout_error, field_label, required=True: calls.append(
            ("first", field_id, field_label, required)
        )
        or True,
    )
    monkeypatch.setattr(
        publisher,
        "_select_dropdown_option",
        lambda page, field_id, option_texts, timeout_error, field_label, required=True: calls.append(
            ("select", field_id, tuple(option_texts), field_label, required)
        )
        or True,
    )
    monkeypatch.setattr(
        publisher,
        "_set_file_input_by_field",
        lambda page, field_id, files, timeout_error, field_label: calls.append(
            ("file", field_id, files, field_label)
        )
        or True,
    )
    monkeypatch.setattr(
        publisher,
        "_upload_video_files",
        lambda page, media_files, timeout_error: calls.append(("videos", media_files)),
    )
    monkeypatch.setattr(
        publisher,
        "_click_radio_text",
        lambda page, texts, timeout_error, field_label, field_id=None, required=True: calls.append(
            ("radio", tuple(texts), field_label, field_id, required)
        )
        or True,
    )
    monkeypatch.setattr(
        publisher,
        "_click_first_radio_by_field",
        lambda page, field_id, timeout_error, field_label, required=True: calls.append(
            ("first-radio", field_id, field_label, required)
        )
        or True,
    )
    monkeypatch.setattr(
        publisher,
        "_check_checkbox_by_field",
        lambda page, field_id, timeout_error, field_label: calls.append(("check", field_id, field_label)) or True,
    )
    monkeypatch.setattr(publisher, "_wait_for_page", lambda page, milliseconds: None)

    publisher._fill_draft(
        object(),
        [video],
        "English Title",
        "English summary",
        {
            "publishTitle": "AI English Title",
            "publishSummary": "AI English summary",
            "episodeCount": 8,
            "freeEpisodeCount": 4,
            "tiktokCoverEnFile": tiktok_cover_en,
            "coverEnFile": cover_en,
            "coverFile": cover,
            "purchaseContractImages": [agreement],
        },
        TimeoutError,
    )

    assert ("fill", "title", "AI English Title", "TK剧集名", True) in calls
    assert ("fill", "description", "AI English summary", "TK剧集描述", True) in calls
    assert ("first", "contract", "TK关联合同", True) in calls
    assert ("file", "coverStruct", tiktok_cover_en, "TK封面图") in calls
    assert ("videos", [video]) in calls
    assert ("first", "targetAudienceTag", "TK目标观众", True) in calls
    assert ("first", "themeTag", "TK题材类型", True) in calls
    assert ("first", "sourceLanguage", "TK源语言", True) in calls
    assert ("fill", "totalVideoNum", "8", "TK总集数", True) in calls
    assert ("first", "isAiSeries", "TK是否AI短剧", True) in calls
    assert ("radio", ("过审后自动发布",), "TK发布方式", None, False) in calls
    assert ("first-radio", "copyrightProof.isOriginalRightsHolder", "TK是否原始权利人", True) in calls
    assert ("first-radio", "copyrightProof.isAdaptation", "TK内容原创类型", True) in calls
    assert ("first", "copyrightProof.selectedMaterialTypes", "TK上传材料类型", True) in calls
    assert ("file", "copyrightProof.selectedMaterialTypes", [agreement], "TK合作协议") in calls
    assert ("check", "signed", "TK版权内容自查承诺") in calls
    assert ("fill", "previewVideoNumOnProfile", "4", "TK个人页剧集展示集数", False) in calls
    assert ("fill", "previewVideoNum", "4", "TK免费预览集数", False) in calls
    assert ("first", "priceInUsd", "TK预期全集价格设置", True) in calls
    assert not any(call[0] == "select" for call in calls)


def test_tiktok_select_open_dropdown_falls_back_to_keyboard(tmp_path: Path, monkeypatch):
    calls = []
    publisher = TikTokPublisher(ChromeController("chrome", tmp_path), account_id="media-tk")

    class FakeKeyboard:
        def __init__(self, page):
            self.page = page

        def press(self, key):
            calls.append(("press", key))
            if key == "Enter":
                self.page.selected = True

    class FakePage:
        def __init__(self):
            self.selected = False
            self.keyboard = FakeKeyboard(self)

        def wait_for_timeout(self, timeout):
            calls.append(("wait", timeout))

    page = FakePage()
    monkeypatch.setattr(
        publisher,
        "_field_has_non_placeholder_value",
        lambda current_page, field_id: current_page.selected,
    )

    assert publisher._select_open_dropdown_by_keyboard(page, "targetAudienceTag", TimeoutError) is True
    assert ("press", "ArrowDown") in calls
    assert ("press", "Enter") in calls


def test_tiktok_publisher_uploads_videos_with_local_upload_button(tmp_path: Path):
    calls = []
    video = tmp_path / "001.mp4"
    video.write_bytes(b"video")
    publisher = TikTokPublisher(ChromeController("chrome", tmp_path), account_id="media-tk")

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

        def filter(self, has_text=None):
            calls.append(("filter", str(has_text)))
            return self

        def count(self):
            return 1

        def click(self, timeout=None, force=False):
            calls.append(("button.click", timeout, force))

    class FakePage:
        def locator(self, selector):
            calls.append(("locator", selector))
            return FakeLocator()

        def expect_file_chooser(self, timeout=None):
            calls.append(("expect_file_chooser", timeout))
            return FakeChooserContext()

        def evaluate(self, script, payload):
            calls.append(("evaluate", payload))
            return {"complete": True, "errorText": ""}

        def wait_for_timeout(self, timeout):
            calls.append(("wait_for_timeout", timeout))

    publisher._upload_video_files(FakePage(), [video], TimeoutError)

    assert ("locator", "#video-upload-section button") in calls
    assert ("button.click", 5000, True) in calls
    assert ("chooser.set_files", [str(video)]) in calls


def test_tiktok_publisher_scripts_target_stable_form_ids(tmp_path: Path):
    publisher = TikTokPublisher(ChromeController("chrome", tmp_path), account_id="media-tk")

    field_trigger_script = publisher._click_tiktok_field_trigger_script()
    upload_state_script = publisher._tiktok_video_upload_state_script()

    assert 'x-field-id="${fieldId}"' in field_trigger_script
    assert "__aidramaTikTokDropdown" in field_trigger_script
    assert ".Select__trigger" in field_trigger_script
    assert ".semi-cascader" in field_trigger_script
    assert ".Select__item" in publisher._click_dropdown_option_script()
    assert ".Select__placeholder" in publisher._field_has_non_placeholder_value_script()
    assert "选择内容主要面向" in publisher._field_has_non_placeholder_value_script()
    assert "copyrightProof.selectedMaterialTypes" not in field_trigger_script
    assert 'input[type="file"]' in publisher._mark_tiktok_field_file_input_script()
    assert "#video-upload-section" in publisher._mark_tiktok_video_input_script()
    assert "#video-upload-section" in upload_state_script
    assert "document.body ? document.body.innerText" not in upload_state_script
    assert "最大10MB" not in upload_state_script
    assert "|超过|" not in upload_state_script
    assert "低于" not in upload_state_script
    assert "sectionDisabled" in upload_state_script
    assert "visibleNames >= files.length" not in upload_state_script
    assert "__aidramaTikTokSubmitGuardInstalled" in publisher._install_tiktok_submit_guard_script()
    assert "no-enabled-radio" in publisher._click_first_tiktok_radio_script()
