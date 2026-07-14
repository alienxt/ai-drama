from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from aidrama_desktop.browser.chrome import ChromeController
from aidrama_desktop.platforms.base import PlatformPublishPaused
from aidrama_desktop.platforms.wechat_video import WeChatVideoPublisher, remote_debugging_port_for_profile


TIKTOK_EPISODE_UPLOAD_MAX_WAIT_SECONDS = 45 * 60


class TikTokPublisher(WeChatVideoPublisher):
    login_url = "https://drama.tiktok.com/series/draft"
    draft_url = "https://drama.tiktok.com/series/draft"

    def __init__(
        self,
        chrome: ChromeController,
        account_id: str | None = None,
        profile_dir: str | Path | None = None,
    ):
        self.chrome = chrome
        self.account_id = account_id
        self.profile_dir = Path(profile_dir) if profile_dir else None

    def open_login(self) -> str:
        profile_dir = self._profile_dir()
        self.chrome.open_profile(
            profile_dir,
            self.login_url,
            remote_debugging_port=remote_debugging_port_for_profile(profile_dir),
        )
        return self.export_login_state()

    def export_login_state(self) -> str:
        return str(self._profile_dir())

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
            raise RuntimeError("Playwright is required for real TikTok Drama publishing") from exception

        metadata = metadata or {}
        profile_dir = self._profile_dir()
        with sync_playwright() as playwright:
            try:
                browser = self._connect_to_chrome(playwright, profile_dir, self.draft_url)
                context = self._browser_context(browser)
            except Exception as exception:  # noqa: BLE001
                raise RuntimeError("无法接管 TK 发布浏览器，请先通过客户端打开 TK 后台并完成登录") from exception
            page = self._open_publish_page(context, self.draft_url)
            self._fill_draft(page, media_files, title, summary, metadata, PlaywrightTimeoutError)
        raise PlatformPublishPaused("TK 表单已填写并停留在提交前，等待人工核验后手动提交。")

    def _profile_dir(self) -> Path:
        if self.profile_dir:
            self.profile_dir.mkdir(parents=True, exist_ok=True)
            return self.profile_dir
        return self.chrome.platform_profile_dir("TIKTOK", self.account_id)

    def _fill_draft(
        self,
        page,
        media_files: list[Path],
        title: str,
        summary: str | None,
        metadata: dict[str, Any],
        timeout_error,
    ) -> None:
        publish_title = str(metadata.get("publishTitle") or title).strip()
        publish_summary = str(metadata.get("publishSummary") or summary or metadata.get("summary") or "").strip()
        episode_count = self._metadata_int(metadata, "episodeCount", default=len(media_files))
        free_episode_count = self._metadata_int(metadata, "freeEpisodeCount", default=max(1, min(episode_count, 3)))

        self._install_tiktok_submit_guard(page, timeout_error)
        self._fill_text_input(page, "title", publish_title, timeout_error, "TK剧集名")
        if publish_summary:
            self._fill_text_input(page, "description", publish_summary, timeout_error, "TK剧集描述")
        self._select_first_dropdown_option(page, "contract", timeout_error, "TK关联合同")

        cover_file = self._tiktok_cover_file(metadata)
        if cover_file:
            self._set_file_input_by_field(page, "coverStruct", cover_file, timeout_error, "TK封面图")

        self._wait_for_tiktok_section_unlocked(page, "#video-upload-section", "TK内容上传", timeout_error)
        self._upload_video_files(page, media_files, timeout_error)
        self._wait_for_tiktok_section_unlocked(page, "#details-section", "TK剧集详情", timeout_error)
        self._fill_details_section(page, episode_count, timeout_error)
        self._wait_for_tiktok_section_unlocked(page, "#copyright-proof-section", "TK版权证明", timeout_error)
        self._fill_copyright_section(page, metadata, timeout_error)
        self._wait_for_tiktok_section_unlocked(page, "#business-mode-section", "TK商业模式", timeout_error)
        self._fill_business_section(page, free_episode_count, timeout_error)
        self._wait_for_page(page, 1000)

    def _fill_details_section(self, page, episode_count: int, timeout_error) -> None:
        self._select_first_dropdown_option(page, "targetAudienceTag", timeout_error, "TK目标观众")
        self._select_first_dropdown_option(page, "themeTag", timeout_error, "TK题材类型")
        self._select_first_dropdown_option(page, "sourceLanguage", timeout_error, "TK源语言")
        self._fill_text_input(page, "totalVideoNum", str(episode_count), timeout_error, "TK总集数")
        self._select_first_dropdown_option(page, "accountIds", timeout_error, "TK发布账号", required=False)
        self._select_first_dropdown_option(page, "isAiSeries", timeout_error, "TK是否AI短剧")
        self._click_radio_text(page, ["过审后自动发布"], timeout_error, "TK发布方式", required=False)

    def _fill_copyright_section(self, page, metadata: dict[str, Any], timeout_error) -> None:
        self._click_first_radio_by_field(
            page,
            "copyrightProof.isOriginalRightsHolder",
            timeout_error,
            "TK是否原始权利人",
        )
        self._click_first_radio_by_field(
            page,
            "copyrightProof.isAdaptation",
            timeout_error,
            "TK内容原创类型",
        )
        self._select_first_dropdown_option(page, "copyrightProof.selectedMaterialTypes", timeout_error, "TK上传材料类型")
        agreement_images = self._metadata_paths(
            metadata,
            "tiktokCooperationAgreementImages",
            "purchaseContractImages",
            "buyDramaContractImages",
        )
        if agreement_images:
            self._set_file_input_by_field(
                page,
                "copyrightProof.selectedMaterialTypes",
                agreement_images,
                timeout_error,
                "TK合作协议",
            )
        self._check_checkbox_by_field(page, "signed", timeout_error, "TK版权内容自查承诺")

    def _fill_business_section(self, page, free_episode_count: int, timeout_error) -> None:
        count = str(max(1, free_episode_count))
        self._fill_text_input(page, "previewVideoNumOnProfile", count, timeout_error, "TK个人页剧集展示集数", required=False)
        self._fill_text_input(page, "previewVideoNum", count, timeout_error, "TK免费预览集数", required=False)
        self._select_first_dropdown_option(page, "priceInUsd", timeout_error, "TK预期全集价格设置")

    def _upload_video_files(self, page, media_files: list[Path], timeout_error) -> None:
        paths = [str(path) for path in media_files]
        if not paths:
            raise RuntimeError("TK 没有可上传的视频文件")
        if self._set_tiktok_video_files_by_button(page, paths, timeout_error):
            self._wait_for_tiktok_video_uploads(page, media_files, timeout_error)
            return

        locator_getter = getattr(page, "locator", None)
        if callable(locator_getter):
            selectors = [
                "#video-upload-section input[type='file'][multiple]",
                "#video-upload-section input[type='file'][accept*='.mp4']",
                "#video-upload-section input[type='file'][accept*='mov']",
                "input[type='file'][multiple][accept*='.mp4']",
            ]
            for selector in selectors:
                try:
                    file_input = page.locator(selector).first
                    if file_input.count() > 0:
                        self._set_locator_files(page, file_input, paths)
                        self._wait_for_page(page, 1500)
                        self._wait_for_tiktok_video_uploads(page, media_files, timeout_error)
                        return
                except timeout_error:
                    continue
                except Exception as exception:  # noqa: BLE001
                    if self._is_page_closed_error(exception):
                        raise RuntimeError("浏览器页面已关闭，无法上传 TK 视频") from exception
                    continue

        marker = f"aidramaTikTokVideoInput{time.time_ns()}"
        evaluate = getattr(page, "evaluate", None)
        if callable(evaluate):
            try:
                marked = bool(evaluate(self._mark_tiktok_video_input_script(), marker))
            except timeout_error:
                marked = False
            except Exception as exception:  # noqa: BLE001
                if self._is_page_closed_error(exception):
                    raise RuntimeError("浏览器页面已关闭，无法定位 TK 视频上传控件") from exception
                marked = False
            if marked:
                self._set_marked_file_input_files_with_cdp(page, marker, paths)
                self._dispatch_marked_file_input_events(page, marker)
                self._wait_for_page(page, 1500)
                self._wait_for_tiktok_video_uploads(page, media_files, timeout_error)
                return
        raise RuntimeError("未找到 TK 内容上传区的本地上传控件，请确认已登录并停留在 TK 短剧草稿页")

    def _set_tiktok_video_files_by_button(self, page, paths: list[str], timeout_error) -> bool:
        locator_getter = getattr(page, "locator", None)
        expect_file_chooser = getattr(page, "expect_file_chooser", None)
        if not callable(locator_getter) or not callable(expect_file_chooser):
            return False
        try:
            button = page.locator("#video-upload-section button").filter(has_text=re.compile("本地上传")).first
            if button.count() == 0:
                button = page.locator("#video-upload-section [role='button']").filter(has_text=re.compile("本地上传")).first
            with page.expect_file_chooser(timeout=5000) as chooser:
                button.click(timeout=5000, force=True)
            self._set_file_chooser_files(page, chooser.value, paths)
            self._wait_for_page(page, 1500)
            return True
        except timeout_error:
            return False
        except Exception as exception:  # noqa: BLE001
            if self._is_page_closed_error(exception):
                raise RuntimeError("浏览器页面已关闭，无法点击 TK 本地上传按钮") from exception
            return False

    def _wait_for_tiktok_video_uploads(
        self,
        page,
        media_files: list[Path],
        timeout_error,
        *,
        max_wait_seconds: int = TIKTOK_EPISODE_UPLOAD_MAX_WAIT_SECONDS,
        check_interval_ms: int = 10_000,
    ) -> None:
        payload = {"files": [{"name": path.name, "stem": path.stem} for path in media_files]}
        deadline = time.time() + max_wait_seconds
        last_state: dict[str, Any] = {}
        while time.time() < deadline:
            try:
                result = page.evaluate(self._tiktok_video_upload_state_script(), payload)
            except timeout_error:
                result = {}
            except Exception as exception:  # noqa: BLE001
                if self._is_page_closed_error(exception):
                    raise RuntimeError("浏览器页面已关闭，无法等待 TK 视频上传完成") from exception
                return
            if isinstance(result, dict):
                last_state = result
                error_text = str(result.get("errorText") or "").strip()
                if error_text:
                    raise RuntimeError(f"TK 视频上传失败：{error_text}")
                if result.get("complete"):
                    return
            self._wait_for_page(page, check_interval_ms)
        uploaded = last_state.get("uploaded")
        total = last_state.get("total") or len(media_files)
        raise RuntimeError(f"TK 视频上传超过 {max_wait_seconds // 60} 分钟仍未完成：{uploaded or 0}/{total}")

    def _wait_for_tiktok_section_unlocked(
        self,
        page,
        selector: str,
        section_label: str,
        timeout_error,
        *,
        max_wait_seconds: int = 60,
        check_interval_ms: int = 1000,
    ) -> bool:
        evaluate = getattr(page, "evaluate", None)
        if not callable(evaluate):
            return True
        deadline = time.time() + max_wait_seconds
        last_state: dict[str, Any] = {}
        while time.time() < deadline:
            try:
                result = evaluate(self._tiktok_section_unlocked_script(), selector)
            except timeout_error:
                result = {}
            except Exception as exception:  # noqa: BLE001
                if self._is_page_closed_error(exception):
                    raise RuntimeError(f"浏览器页面已关闭，无法等待 {section_label} 解锁") from exception
                return True
            if isinstance(result, dict):
                last_state = result
                if result.get("missing") or result.get("unlocked"):
                    return True
            self._wait_for_page(page, check_interval_ms)
        if last_state.get("disabled"):
            raise RuntimeError(f"{section_label}仍处于不可填写状态，请检查前置步骤是否已完成")
        return False

    def _install_tiktok_submit_guard(self, page, timeout_error) -> bool:
        evaluate = getattr(page, "evaluate", None)
        if not callable(evaluate):
            return False
        try:
            return bool(evaluate(self._install_tiktok_submit_guard_script()))
        except timeout_error:
            return False
        except Exception as exception:  # noqa: BLE001
            if self._is_page_closed_error(exception):
                raise RuntimeError("浏览器页面已关闭，无法安装 TK 提交保护") from exception
            return False

    def _fill_text_input(
        self,
        page,
        field_id: str,
        value: str,
        timeout_error,
        field_label: str,
        *,
        required: bool = True,
    ) -> bool:
        if not str(value).strip():
            if required:
                raise RuntimeError(f"{field_label}为空，无法填写 TK 表单")
            return False
        locator_getter = getattr(page, "locator", None)
        if callable(locator_getter):
            selectors = [
                f"#{self._css_escape(field_id)}",
                f'[x-field-id="{field_id}"] input',
                f'[x-field-id="{field_id}"] textarea',
            ]
            for selector in selectors:
                try:
                    locator = page.locator(selector).first
                    if locator.count() > 0 and self._fill_locator_and_verify(locator, str(value), timeout_error, field_label):
                        return True
                except timeout_error:
                    continue
                except Exception as exception:  # noqa: BLE001
                    if self._is_page_closed_error(exception):
                        raise RuntimeError(f"浏览器页面已关闭，无法填写 {field_label}") from exception
                    continue
        evaluate = getattr(page, "evaluate", None)
        if callable(evaluate):
            try:
                result = evaluate(
                    self._fill_tiktok_text_field_script(),
                    {"fieldId": field_id, "value": str(value)},
                )
            except timeout_error:
                result = {}
            except Exception as exception:  # noqa: BLE001
                if self._is_page_closed_error(exception):
                    raise RuntimeError(f"浏览器页面已关闭，无法填写 {field_label}") from exception
                result = {}
            if isinstance(result, dict) and result.get("filled"):
                return True
        if required:
            raise RuntimeError(f"未找到 {field_label} 输入框，请确认 TK 表单页面结构未变化")
        return False

    def _set_file_input_by_field(
        self,
        page,
        field_id: str,
        files: Path | list[Path],
        timeout_error,
        field_label: str,
    ) -> bool:
        path_list = files if isinstance(files, list) else [files]
        existing = [Path(path) for path in path_list if Path(path).exists()]
        if not existing:
            raise RuntimeError(f"{field_label}文件不存在，无法上传")
        paths: str | list[str] = [str(path) for path in existing] if len(existing) > 1 else str(existing[0])
        locator_getter = getattr(page, "locator", None)
        if callable(locator_getter):
            try:
                file_input = page.locator(f'[x-field-id="{field_id}"] input[type="file"]').first
                if file_input.count() > 0:
                    self._set_locator_files(page, file_input, paths)
                    self._wait_for_page(page, 1000)
                    return True
            except timeout_error:
                pass
            except Exception as exception:  # noqa: BLE001
                if self._is_page_closed_error(exception):
                    raise RuntimeError(f"浏览器页面已关闭，无法上传 {field_label}") from exception
        marker = f"aidramaTikTokFieldInput{time.time_ns()}"
        evaluate = getattr(page, "evaluate", None)
        if not callable(evaluate):
            return False
        try:
            marked = bool(evaluate(self._mark_tiktok_field_file_input_script(), {"fieldId": field_id, "marker": marker}))
        except timeout_error as exception:
            raise RuntimeError(f"未找到 {field_label} 上传控件，请确认 TK 表单已显示该字段") from exception
        except Exception as exception:  # noqa: BLE001
            if self._is_page_closed_error(exception):
                raise RuntimeError(f"浏览器页面已关闭，无法上传 {field_label}") from exception
            marked = False
        if not marked:
            raise RuntimeError(f"未找到 {field_label} 上传控件，请确认 TK 表单已显示该字段")
        self._set_marked_file_input_files_with_cdp(page, marker, paths)
        self._dispatch_marked_file_input_events(page, marker)
        self._wait_for_page(page, 1000)
        return True

    def _select_dropdown_option(
        self,
        page,
        field_id: str,
        option_texts: list[str],
        timeout_error,
        field_label: str,
        *,
        required: bool = True,
    ) -> bool:
        for text in option_texts:
            if self._select_dropdown_option_by_text(page, field_id, text, timeout_error, field_label):
                return True
        if required:
            raise RuntimeError(f"未能选择 {field_label}：{'/'.join(option_texts)}")
        return False

    def _select_dropdown_option_by_text(self, page, field_id: str, option_text: str, timeout_error, field_label: str) -> bool:
        deadline = time.time() + 8
        while time.time() < deadline:
            try:
                opened = bool(page.evaluate(self._click_tiktok_field_trigger_script(), field_id))
                if not opened:
                    self._wait_for_page(page, 500)
                    continue
                self._wait_for_page(page, 300)
                result = page.evaluate(
                    self._click_dropdown_option_script(),
                    {"optionText": option_text, "first": False},
                )
            except timeout_error:
                result = {}
            except Exception as exception:  # noqa: BLE001
                if self._is_page_closed_error(exception):
                    raise RuntimeError(f"浏览器页面已关闭，无法选择 {field_label}") from exception
                result = {}
            if isinstance(result, dict) and result.get("clicked"):
                self._wait_for_page(page, 300)
                return True
            self._wait_for_page(page, 500)
        return False

    def _select_first_dropdown_option(
        self,
        page,
        field_id: str,
        timeout_error,
        field_label: str,
        *,
        required: bool = True,
    ) -> bool:
        if self._field_has_non_placeholder_value(page, field_id):
            return True

        if self._click_tiktok_field_trigger_by_locator(page, field_id, timeout_error):
            self._wait_for_page(page, 500)
            if self._click_first_visible_dropdown_option_by_locator(page, timeout_error):
                self._wait_for_page(page, 500)
                if self._field_has_non_placeholder_value(page, field_id):
                    return True
            if self._select_open_dropdown_by_keyboard(page, field_id, timeout_error):
                return True
            try:
                result = page.evaluate(self._click_dropdown_option_script(), {"optionText": "", "first": True})
            except timeout_error:
                result = {}
            except Exception as exception:  # noqa: BLE001
                if self._is_page_closed_error(exception):
                    raise RuntimeError(f"浏览器页面已关闭，无法选择 {field_label}") from exception
                result = {}
            if isinstance(result, dict) and result.get("clicked"):
                self._wait_for_page(page, 500)
                if self._field_has_non_placeholder_value(page, field_id):
                    return True

        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                opened = bool(page.evaluate(self._click_tiktok_field_trigger_script(), field_id))
                if not opened:
                    if self._field_has_non_placeholder_value(page, field_id):
                        return True
                    if not required:
                        return False
                    self._wait_for_page(page, 500)
                    continue
                self._wait_for_page(page, 500)
                result = page.evaluate(self._click_dropdown_option_script(), {"optionText": "", "first": True})
            except timeout_error:
                result = {}
            except Exception as exception:  # noqa: BLE001
                if self._is_page_closed_error(exception):
                    raise RuntimeError(f"浏览器页面已关闭，无法选择 {field_label}") from exception
                result = {}
            if isinstance(result, dict) and result.get("clicked"):
                self._wait_for_page(page, 500)
                if self._field_has_non_placeholder_value(page, field_id):
                    return True
            if self._select_open_dropdown_by_keyboard(page, field_id, timeout_error):
                return True
            if self._field_has_non_placeholder_value(page, field_id):
                return True
            self._wait_for_page(page, 500)
        if self._field_has_non_placeholder_value(page, field_id):
            return True
        if required:
            raise RuntimeError(f"未能选择 {field_label}下拉列表第一项")
        return False

    def _select_open_dropdown_by_keyboard(self, page, field_id: str, timeout_error) -> bool:
        keyboard = getattr(page, "keyboard", None)
        if keyboard is None:
            return False
        try:
            keyboard.press("ArrowDown")
            self._wait_for_page(page, 120)
            keyboard.press("Enter")
            self._wait_for_page(page, 500)
            if self._field_has_non_placeholder_value(page, field_id):
                return True
            keyboard.press("Enter")
            self._wait_for_page(page, 500)
            return self._field_has_non_placeholder_value(page, field_id)
        except timeout_error:
            return False
        except Exception as exception:  # noqa: BLE001
            if self._is_page_closed_error(exception):
                raise
            return False

    def _click_tiktok_field_trigger_by_locator(self, page, field_id: str, timeout_error) -> bool:
        locator_getter = getattr(page, "locator", None)
        if not callable(locator_getter):
            return False
        selector = (
            f'[x-field-id="{field_id}"] [role="combobox"], '
            f'[x-field-id="{field_id}"] button[aria-haspopup], '
            f'[x-field-id="{field_id}"] .semi-select, '
            f'[x-field-id="{field_id}"] .Select__trigger, '
            f'[x-field-id="{field_id}"] .semi-cascader, '
            f'[x-field-id="{field_id}"] .trigger-iF4aJp, '
            f'[x-field-id="{field_id}"] [aria-haspopup="dialog"], '
            f'[x-field-id="{field_id}"] [aria-haspopup="listbox"]'
        )
        try:
            trigger = page.locator(selector).first
            if trigger.count() == 0:
                return False
            trigger.click(timeout=5000, force=True)
            return True
        except timeout_error:
            return False
        except Exception as exception:  # noqa: BLE001
            if self._is_page_closed_error(exception):
                raise
            return False

    def _click_first_visible_dropdown_option_by_locator(self, page, timeout_error) -> bool:
        locator_getter = getattr(page, "locator", None)
        if not callable(locator_getter):
            return False
        selectors = [
            '[role="dialog"] [role="option"]:not([aria-disabled="true"])',
            '[role="listbox"] [role="option"]:not([aria-disabled="true"])',
            '.Select__contentWrapper [role="option"]:not([aria-disabled="true"])',
            '.Select__item:not(.Select__item--disabled-true)',
            '.semi-select-option:not(.semi-select-option-disabled)',
            '.semi-cascader-option:not(.semi-cascader-option-disabled)',
        ]
        for selector in selectors:
            try:
                option = page.locator(selector).first
                if option.count() == 0:
                    continue
                option.click(timeout=5000, force=True)
                return True
            except timeout_error:
                continue
            except Exception as exception:  # noqa: BLE001
                if self._is_page_closed_error(exception):
                    raise
                continue
        return False

    def _click_first_radio_by_field(
        self,
        page,
        field_id: str,
        timeout_error,
        field_label: str,
        *,
        required: bool = True,
    ) -> bool:
        if self._click_first_radio_by_locator(page, field_id, timeout_error):
            self._wait_for_page(page, 500)
            return True

        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                result = page.evaluate(self._click_first_tiktok_radio_script(), field_id)
            except timeout_error:
                result = {}
            except Exception as exception:  # noqa: BLE001
                if self._is_page_closed_error(exception):
                    raise RuntimeError(f"浏览器页面已关闭，无法选择 {field_label}") from exception
                result = {}
            if isinstance(result, dict) and result.get("clicked"):
                self._wait_for_page(page, 500)
                return True
            if not required:
                return False
            self._wait_for_page(page, 500)
        if required:
            raise RuntimeError(f"未能选择 {field_label}第一项")
        return False

    def _click_first_radio_by_locator(self, page, field_id: str, timeout_error) -> bool:
        locator_getter = getattr(page, "locator", None)
        if not callable(locator_getter):
            return False
        selectors = [
            f'[x-field-id="{field_id}"] label.semi-radio:not(.semi-radio-disabled)',
            f'[x-field-id="{field_id}"] [role="radio"]:not([aria-disabled="true"])',
            f'[x-field-id="{field_id}"] label',
        ]
        for selector in selectors:
            try:
                option = page.locator(selector).first
                if option.count() == 0:
                    continue
                option.click(timeout=5000, force=True)
                return True
            except timeout_error:
                continue
            except Exception as exception:  # noqa: BLE001
                if self._is_page_closed_error(exception):
                    raise
                continue
        return False

    def _click_radio_text(
        self,
        page,
        texts: list[str],
        timeout_error,
        field_label: str,
        *,
        field_id: str | None = None,
        required: bool = True,
    ) -> bool:
        try:
            result = page.evaluate(
                self._click_tiktok_radio_script(),
                {"texts": texts, "fieldId": field_id},
            )
        except timeout_error:
            result = {}
        except Exception as exception:  # noqa: BLE001
            if self._is_page_closed_error(exception):
                raise RuntimeError(f"浏览器页面已关闭，无法选择 {field_label}") from exception
            result = {}
        if isinstance(result, dict) and result.get("clicked"):
            self._wait_for_page(page, 300)
            return True
        if required:
            raise RuntimeError(f"未能选择 {field_label}：{'/'.join(texts)}")
        return False

    def _check_checkbox_by_field(self, page, field_id: str, timeout_error, field_label: str) -> bool:
        try:
            result = page.evaluate(self._check_tiktok_checkbox_script(), field_id)
        except timeout_error:
            result = {}
        except Exception as exception:  # noqa: BLE001
            if self._is_page_closed_error(exception):
                raise RuntimeError(f"浏览器页面已关闭，无法勾选 {field_label}") from exception
            result = {}
        if isinstance(result, dict) and result.get("checked"):
            self._wait_for_page(page, 200)
            return True
        raise RuntimeError(f"未能勾选 {field_label}")

    @staticmethod
    def _tiktok_cover_file(metadata: dict[str, Any]) -> Path | None:
        for key in ("tiktokCoverEnFile", "coverEnFile", "coverFile", "videoCoverEnFile", "videoCoverFile"):
            value = metadata.get(key)
            if value and Path(value).exists():
                return Path(value)
        return None

    @staticmethod
    def _metadata_int(metadata: dict[str, Any], key: str, default: int) -> int:
        try:
            value = int(float(str(metadata.get(key))))
        except (TypeError, ValueError):
            value = default
        return max(1, value)

    @staticmethod
    def _field_has_non_placeholder_value(page, field_id: str) -> bool:
        evaluate = getattr(page, "evaluate", None)
        if not callable(evaluate):
            return False
        try:
            return bool(evaluate(TikTokPublisher._field_has_non_placeholder_value_script(), field_id))
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def _css_escape(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"').replace(".", "\\.")

    @staticmethod
    def _fill_tiktok_text_field_script() -> str:
        return """
            ({ fieldId, value }) => {
                const field = document.querySelector(`[x-field-id="${fieldId}"]`);
                const input = document.getElementById(fieldId)
                    || (field && field.querySelector('input, textarea'));
                if (!input) return { filled: false };
                const proto = input instanceof HTMLTextAreaElement
                    ? HTMLTextAreaElement.prototype
                    : HTMLInputElement.prototype;
                const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                if (setter) setter.call(input, value);
                else input.value = value;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
                input.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: 'Process' }));
                return { filled: input.value === value, value: input.value };
            }
        """

    @staticmethod
    def _click_tiktok_field_trigger_script() -> str:
        return """
            (fieldId) => {
                const field = document.querySelector(`[x-field-id="${fieldId}"]`);
                if (!field) return false;
                const visible = (el) => {
                    if (!el || !(el instanceof HTMLElement)) return false;
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                };
                const candidates = [
                    ...Array.from(field.querySelectorAll('[role="combobox"], button[aria-haspopup], .semi-select, .Select__trigger, .semi-cascader, [aria-haspopup="dialog"], [aria-haspopup="listbox"]')),
                    ...Array.from(field.querySelectorAll('button, [role="button"]'))
                ].filter(visible);
                const target = candidates.find((item) => item.getAttribute('aria-disabled') !== 'true' && !item.disabled);
                if (!target) return false;
                try { target.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (_) {}
                const rect = target.getBoundingClientRect();
                window.__aidramaTikTokDropdown = {
                    fieldId,
                    popupId: target.getAttribute('data-popupid')
                        || target.getAttribute('aria-controls')
                        || target.getAttribute('aria-describedby')
                        || '',
                    rect: {
                        left: rect.left,
                        right: rect.right,
                        top: rect.top,
                        bottom: rect.bottom,
                        width: rect.width,
                        height: rect.height
                    }
                };
                target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                target.click();
                return true;
            }
        """

    @staticmethod
    def _field_has_non_placeholder_value_script() -> str:
        return """
            (fieldId) => {
                const field = document.querySelector(`[x-field-id="${fieldId}"]`);
                if (!field) return false;
                const visible = (el) => {
                    if (!el || !(el instanceof HTMLElement)) return false;
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                };
                const placeholder = field.querySelector([
                    '.Select__placeholder',
                    '.semi-select-selection-placeholder',
                    '.triggerHintText-yBovY0',
                    '[class*="placeholder"]',
                    '[class*="Placeholder"]'
                ].join(','));
                if (placeholder && visible(placeholder)) return false;
                const valuedInput = Array.from(field.querySelectorAll('input, textarea'))
                    .find((input) => String(input.value || '').trim());
                if (valuedInput) return true;
                const normalized = (value) => String(value || '').replace(/\\s+/g, '');
                const text = normalized(field.innerText || field.textContent);
                if (!text) return false;
                return !/(^选择$|请选择|请先|输入价格|输入数字|请选择合同|选择内容主要面向|选择剧集的题材标签|请选择剧集的源语言|请选择是否AI短剧|上传材料类型选择|预期全集价格设置输入价格)/.test(text);
            }
        """

    @staticmethod
    def _click_dropdown_option_script() -> str:
        return """
            ({ optionText, first }) => {
                const normalized = (value) => String(value || '').replace(/\\s+/g, '');
                const desired = normalized(optionText);
                const visible = (el) => {
                    if (!el || !(el instanceof HTMLElement)) return false;
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                };
                const disabled = (el) => el.disabled || el.getAttribute('aria-disabled') === 'true' || /disabled/.test(String(el.className || ''));
                const optionSelectors = [
                    '[role="option"]',
                    '[role="menuitem"]',
                    '.semi-select-option',
                    '.semi-cascader-option',
                    '.Select__option',
                    '.Select__item',
                    '.Select__itemInner',
                    '.Select__itemLabel',
                    '.Option__root',
                    '.Option__item',
                    '[class*="Select__item"]'
                ].join(',');
                const active = window.__aidramaTikTokDropdown || {};
                const popupId = active.popupId || '';
                const triggerRect = active.rect || null;
                const cssEscape = (value) => {
                    if (window.CSS && typeof window.CSS.escape === 'function') return window.CSS.escape(value);
                    return String(value || '').replace(/[^a-zA-Z0-9_-]/g, '\\\\$&');
                };
                const popupRoot = popupId ? document.getElementById(popupId) : null;
                const nearTrigger = (el) => {
                    if (!triggerRect) return false;
                    const rect = el.getBoundingClientRect();
                    const horizontalOverlap = rect.right >= triggerRect.left - 80 && rect.left <= triggerRect.right + 520;
                    const belowTrigger = rect.bottom >= triggerRect.bottom - 8 && rect.top <= triggerRect.bottom + 680;
                    return horizontalOverlap && belowTrigger;
                };
                const inActivePopup = (el) => {
                    if (popupRoot && popupRoot.contains(el)) return true;
                    if (popupId && el.closest && el.closest(`#${cssEscape(popupId)}`)) return true;
                    return nearTrigger(el);
                };
                const optionTextOf = (el) => normalized(el.innerText || el.textContent);
                const looksLikeOption = (el) => {
                    const text = optionTextOf(el);
                    if (
                        !text
                        || /请选择|请先|输入价格|输入数字|选择内容主要面向|选择剧集的题材标签|请选择剧集的源语言|请选择是否AI短剧/.test(text)
                    ) return false;
                    const rect = el.getBoundingClientRect();
                    if (rect.height > 180 || rect.width > 900) return false;
                    if (el.matches('input, textarea, svg, path')) return false;
                    if (el.matches('button') && normalized(el.textContent).includes('提交')) return false;
                    return true;
                };
                const scopedOptions = popupRoot
                    ? Array.from(popupRoot.querySelectorAll(optionSelectors))
                    : [];
                const globalOptions = Array.from(document.querySelectorAll(optionSelectors))
                    .filter(inActivePopup);
                const directOptions = [...scopedOptions, ...globalOptions];
                const geometricOptions = directOptions.length === 0 && triggerRect
                    ? Array.from(document.body.querySelectorAll('div, li, span, p'))
                        .filter(visible)
                        .filter(inActivePopup)
                    : [];
                const seen = new Set();
                const options = [...directOptions, ...geometricOptions]
                    .filter((el) => {
                        if (seen.has(el)) return false;
                        seen.add(el);
                        return true;
                    })
                    .filter(visible)
                    .filter((el) => !disabled(el))
                    .filter(looksLikeOption)
                    .sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
                const target = first
                    ? options[0]
                    : options.find((el) => optionTextOf(el).includes(desired));
                if (!target) return { clicked: false, count: options.length, popupId };
                const clickable = target.closest('[role="option"], [role="menuitem"], .semi-select-option, .semi-cascader-option, .Select__option, .Select__item, .Option__root, .Option__item, [class*="Select__item"]')
                    || target;
                try { clickable.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (_) {}
                clickable.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, view: window }));
                clickable.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                clickable.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, cancelable: true, view: window }));
                clickable.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                clickable.click();
                return { clicked: true, text: clickable.innerText || clickable.textContent || '', popupId };
            }
        """

    @staticmethod
    def _tiktok_section_unlocked_script() -> str:
        return """
            (selector) => {
                const section = document.querySelector(selector);
                if (!section) return { missing: true };
                const disabledContainer = section.querySelector('.sectionDisabled-SdfV1y');
                const disabled = Boolean(disabledContainer);
                return { missing: false, disabled, unlocked: !disabled };
            }
        """

    @staticmethod
    def _install_tiktok_submit_guard_script() -> str:
        return """
            () => {
                if (window.__aidramaTikTokSubmitGuardInstalled) return true;
                window.__aidramaTikTokSubmitGuardInstalled = true;
                document.addEventListener('click', (event) => {
                    if (event.isTrusted) return;
                    const target = event.target && event.target.closest
                        ? event.target.closest('button, [role="button"]')
                        : null;
                    const text = String(target ? (target.innerText || target.textContent || '') : '').replace(/\\s+/g, '');
                    if (target && text.includes('提交')) {
                        event.preventDefault();
                        event.stopImmediatePropagation();
                    }
                }, true);
                return true;
            }
        """

    @staticmethod
    def _click_tiktok_radio_script() -> str:
        return """
            ({ texts, fieldId }) => {
                const normalized = (value) => String(value || '').replace(/\\s+/g, '');
                const desired = texts.map(normalized).filter(Boolean);
                const visible = (el) => {
                    if (!el || !(el instanceof HTMLElement)) return false;
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                };
                const root = fieldId ? document.querySelector(`[x-field-id="${fieldId}"]`) : document;
                if (!root) return { clicked: false };
                const candidates = Array.from(root.querySelectorAll('label, [role="radio"], .semi-radio, button, [role="button"], span, div'))
                    .filter(visible)
                    .filter((el) => desired.some((text) => normalized(el.innerText || el.textContent).includes(text)))
                    .sort((a, b) => normalized(a.innerText || a.textContent).length - normalized(b.innerText || b.textContent).length);
                const target = candidates[0];
                if (!target) return { clicked: false };
                const radio = target.closest('label, .semi-radio, [role="radio"]') || target;
                try { radio.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (_) {}
                radio.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                radio.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                radio.click();
                return { clicked: true, text: radio.innerText || radio.textContent || '' };
            }
        """

    @staticmethod
    def _click_first_tiktok_radio_script() -> str:
        return """
            (fieldId) => {
                const field = document.querySelector(`[x-field-id="${fieldId}"]`) || document.getElementById(fieldId);
                if (!field) return { clicked: false, reason: 'missing-field' };
                const visible = (el) => {
                    if (!el || !(el instanceof HTMLElement)) return false;
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                };
                const disabled = (el) => {
                    const input = el.querySelector && el.querySelector('input[type="radio"]');
                    return Boolean(
                        el.disabled
                        || el.getAttribute('aria-disabled') === 'true'
                        || /disabled/.test(String(el.className || ''))
                        || (input && input.disabled)
                    );
                };
                const options = Array.from(field.querySelectorAll('label, [role="radio"], .semi-radio'))
                    .filter(visible)
                    .filter((el) => !disabled(el));
                const target = options[0];
                if (!target) return { clicked: false, reason: 'no-enabled-radio' };
                const input = target.querySelector('input[type="radio"]');
                if (input && input.checked) return { clicked: true, alreadyChecked: true };
                try { target.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (_) {}
                target.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, cancelable: true, view: window }));
                target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                target.dispatchEvent(new PointerEvent('pointerup', { bubbles: true, cancelable: true, view: window }));
                target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                target.click();
                if (input && !input.checked && !input.disabled) {
                    input.checked = true;
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    input.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
                }
                return { clicked: true, text: target.innerText || target.textContent || '' };
            }
        """

    @staticmethod
    def _check_tiktok_checkbox_script() -> str:
        return """
            (fieldId) => {
                const field = document.querySelector(`[x-field-id="${fieldId}"]`) || document.getElementById(fieldId);
                if (!field) return { checked: false };
                const input = field.querySelector('input[type="checkbox"]');
                if (input && input.checked) return { checked: true };
                const target = field.querySelector('label, [role="checkbox"], .semi-checkbox, input[type="checkbox"]')
                    || field.closest('label')
                    || field;
                try { target.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (_) {}
                target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                target.click();
                if (input && !input.checked) {
                    input.checked = true;
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                }
                return { checked: input ? Boolean(input.checked) : true };
            }
        """

    @staticmethod
    def _mark_tiktok_field_file_input_script() -> str:
        return """
            ({ fieldId, marker }) => {
                const field = document.querySelector(`[x-field-id="${fieldId}"]`);
                if (!field) return false;
                const inputs = Array.from(field.querySelectorAll('input[type="file"]'));
                const input = inputs.find((item) => !item.disabled) || inputs[0];
                if (!input) return false;
                input.setAttribute('data-aidrama-file-input', marker);
                return true;
            }
        """

    @staticmethod
    def _mark_tiktok_video_input_script() -> str:
        return """
            (marker) => {
                const section = document.querySelector('#video-upload-section') || document;
                const inputs = Array.from(section.querySelectorAll('input[type="file"]'));
                const input = inputs.find((item) => {
                    const accept = String(item.getAttribute('accept') || '').toLowerCase();
                    return item.multiple && /mp4|mov|video/.test(accept);
                }) || inputs.find((item) => item.multiple);
                if (!input) return false;
                input.setAttribute('data-aidrama-file-input', marker);
                return true;
            }
        """

    @staticmethod
    def _tiktok_video_upload_state_script() -> str:
        return """
            ({ files }) => {
                const normalized = (value) => String(value || '').replace(/\\s+/g, '');
                const section = document.querySelector('#video-upload-section') || document.body || document;
                const text = normalized(section.innerText || section.textContent || '');
                const names = files.flatMap((file) => [normalized(file.name), normalized(file.stem)].filter(Boolean));
                const visibleNames = names.filter((name) => text.includes(name)).length;
                const successMatches = Array.from(text.matchAll(/上传成功|已上传|处理完成|上传完成/g)).length;
                const progressMatch = text.match(/(\\d+)\\s*\\/\\s*(\\d+)/);
                const uploaded = progressMatch ? Number(progressMatch[1]) : Math.max(visibleNames, successMatches);
                const total = progressMatch ? Number(progressMatch[2]) : files.length;
                const errorMatch = text.match(/(上传失败|校验失败|格式不支持|文件过大|文件太小)[^\\n]{0,100}/);
                const details = document.querySelector('#details-section');
                const detailUnlocked = Boolean(details && !details.querySelector('.sectionDisabled-SdfV1y'));
                const completeBySuccessText = successMatches >= files.length;
                return {
                    uploaded,
                    total,
                    visibleNames,
                    successMatches,
                    complete: detailUnlocked || completeBySuccessText,
                    errorText: errorMatch ? errorMatch[0] : '',
                };
            }
        """
