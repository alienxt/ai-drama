from __future__ import annotations

import re
import time
import zlib
from pathlib import Path
from typing import Any

from aidrama_desktop.browser.chrome import ChromeController
from aidrama_desktop.platforms.base import PlatformPublisher, PlatformPublishPaused


PLAYLET_SUMMARY_MAX_CHARS = 100
PLAYLET_SUMMARY_ELLIPSIS = "......"


class WeChatVideoPublisher(PlatformPublisher):
    login_url = "https://channels.weixin.qq.com/platform"
    playlet_url = "https://channels.weixin.qq.com/platform/native-drama-post"

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

    def _profile_dir(self) -> Path:
        if self.profile_dir:
            self.profile_dir.mkdir(parents=True, exist_ok=True)
            return self.profile_dir
        return self.chrome.platform_profile_dir("WECHAT_VIDEO", self.account_id)

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
            raise RuntimeError("Playwright is required for real WeChat Video publishing") from exception

        profile_dir = self._profile_dir()
        with sync_playwright() as playwright:
            browser = None
            context = None
            try:
                target_url = self.playlet_url if metadata else self.login_url
                browser = self._connect_to_chrome(playwright, profile_dir, target_url)
                context = self._browser_context(browser)
            except Exception as exception:  # noqa: BLE001
                raise RuntimeError("无法接管视频号发布浏览器，请先通过客户端打开媒体号后台并完成扫码登录") from exception
            page = self._open_publish_page(context, target_url)
            if metadata:
                self._upload_playlet(page, media_files, title, summary, metadata, PlaywrightTimeoutError)
            else:
                for media_file in media_files:
                    self._upload_single(page, media_file, title, summary, PlaywrightTimeoutError)
        prefix = "wechat-playlet" if metadata else "wechat-video"
        return f"{prefix}:{title}:{len(media_files)}"

    def _connect_to_chrome(self, playwright, profile_dir: Path, target_url: str):
        port = remote_debugging_port_for_profile(profile_dir)
        process = self.chrome.open_profile(profile_dir, "about:blank", remote_debugging_port=port)
        endpoint = f"http://127.0.0.1:{port}"
        last_exception: Exception | None = None
        for _ in range(30):
            try:
                return playwright.chromium.connect_over_cdp(endpoint)
            except Exception as exception:  # noqa: BLE001
                last_exception = exception
                time.sleep(0.2)
        self._terminate_process(process)
        if last_exception:
            raise last_exception
        raise RuntimeError("Chrome remote debugging endpoint did not become ready")

    @staticmethod
    def _browser_context(browser):
        contexts = list(getattr(browser, "contexts", []) or [])
        if contexts:
            return contexts[0]
        return browser.new_context()

    def _open_publish_page(self, context, target_url: str):
        startup_pages = list(getattr(context, "pages", []) or [])
        page = self._target_page(startup_pages, target_url) or self._startup_blank_page(startup_pages) or context.new_page()
        try:
            if not self._is_target_url(getattr(page, "url", ""), target_url):
                page.goto(target_url, wait_until="domcontentloaded")
            page.wait_for_timeout(1000)
        except Exception as exception:  # noqa: BLE001
            if self._is_page_closed_error(exception):
                raise RuntimeError("浏览器页面已关闭，无法打开视频号发布页面") from exception
            raise RuntimeError("无法打开视频号发布页面，请确认网络正常并已登录视频号助手") from exception
        self._close_startup_blank_pages(startup_pages, active_page=page)
        return page

    @staticmethod
    def _target_page(pages, target_url: str):
        for page in pages:
            if WeChatVideoPublisher._is_target_url(getattr(page, "url", ""), target_url):
                return page
        return None

    @staticmethod
    def _is_target_url(url: str, target_url: str) -> bool:
        return str(url or "").rstrip("/") == target_url.rstrip("/")

    @staticmethod
    def _startup_blank_page(pages):
        for page in pages:
            url = str(getattr(page, "url", "") or "")
            if url in {"", "about:blank"}:
                return page
        return None

    def _close_startup_blank_pages(self, pages, active_page) -> None:
        for page in pages:
            if page is active_page:
                continue
            url = str(getattr(page, "url", "") or "")
            close = getattr(page, "close", None)
            if callable(close) and url in {"", "about:blank"}:
                try:
                    close()
                except Exception:
                    pass

    @staticmethod
    def _terminate_process(process) -> None:
        poll = getattr(process, "poll", None)
        terminate = getattr(process, "terminate", None)
        if callable(poll) and poll() is not None:
            return
        if callable(terminate):
            try:
                terminate()
            except Exception:
                pass

    def _upload_playlet(
        self,
        page,
        media_files: list[Path],
        title: str,
        summary: str | None,
        metadata: dict[str, Any],
        timeout_error,
    ) -> None:
        publish_title = str(metadata.get("publishTitle") or title)
        publish_summary = self._playlet_summary(publish_title, summary, metadata)
        episode_count = metadata.get("episodeCount") or len(metadata.get("episodes", []) or media_files)
        free_episode_count = metadata.get("freeEpisodeCount")
        producer_name = self._metadata_text(metadata, "producerName", "seller", "contractSeller")
        production_cost = self._production_cost_wan(metadata)
        self._enter_playlet_plan(page, timeout_error)
        create_button = page.get_by_text(re.compile("创建剧集|新建剧集|新增剧集|上传剧集|添加剧集")).first
        try:
            create_button.click(timeout=8000)
            page.wait_for_timeout(1000)
        except timeout_error:
            pass

        self._set_default_playlet_options(page, timeout_error)
        self._set_monetization_type(page, str(metadata.get("monetizationLabel") or "IAA广告变现"), timeout_error)
        self._wait_for_page(page, 800)

        self._fill_playlet_field(
            page,
            [
                "剧目名称",
                "剧集名称",
                "短剧名称",
                "标题",
                "请填写待提审剧目的名称",
                "请输入剧目名称",
                "请输入剧集名称",
                "请输入标题",
            ],
            publish_title,
            timeout_error,
            "剧目名称",
        )
        if publish_summary:
            summary_labels = [
                re.compile("剧目简介"),
                re.compile("剧情简介"),
                re.compile("请介绍相关剧情概要"),
            ]
            summary_filled = self._fill_weui_textarea_by_label(
                page,
                "剧目简介",
                publish_summary,
                timeout_error,
            )
            if not summary_filled:
                summary_filled = self._fill_text_field_near_text(
                    page,
                    summary_labels,
                    publish_summary,
                    timeout_error,
                    "剧目简介",
                )
            if not summary_filled:
                summary_filled = self._fill_first(
                    page,
                    [
                        "剧目简介",
                        "简介",
                        "剧情简介",
                        "描述",
                        "请介绍相关剧情概要，便于用户更好地了解作品内容",
                        "请介绍相关剧情概要",
                        "请输入简介",
                        "请输入剧情简介",
                    ],
                    publish_summary,
                )

        if episode_count:
            self._fill_playlet_field(
                page,
                [
                    "总集数",
                    "剧集总数",
                    "总剧集数量",
                    "请填写待提审剧目的总剧集数量",
                    "请输入总集数",
                ],
                str(episode_count),
                timeout_error,
                "总集数",
            )

        if free_episode_count is not None:
            self._fill_playlet_field(
                page,
                [
                    "试看集数",
                    "免费集数",
                    "免费试看集数",
                    "免费观看集数",
                    "请填写试看集数",
                    "请输入免费集数",
                    "请输入免费试看集数",
                ],
                str(free_episode_count),
                timeout_error,
                "试看集数",
            )

        if producer_name:
            self._fill_playlet_field(
                page,
                [
                    "制作方名称",
                    "制作方主体名称",
                    "剧目制作方名称",
                    "剧目制作方",
                    "请填写待提审剧目的制作方主体名称",
                    "请输入制作方名称",
                    "请输入制作方主体名称",
                ],
                producer_name,
                timeout_error,
                "制作方名称",
            )
        if production_cost:
            self._fill_playlet_field(
                page,
                [
                    "剧目制作成本",
                    "剧目制作成本（单位：万元）",
                    "制作成本",
                    "剧目成本",
                    "请填写剧目制作成本，该金额需与《成本配置比例情况报告》内容一致",
                    "请输入剧目制作成本",
                ],
                production_cost,
                timeout_error,
                "剧目制作成本",
            )

        cover_file = metadata.get("coverFile")
        if cover_file:
            self._set_file_input_near_text(
                page,
                Path(cover_file),
                [
                    re.compile("剧目海报"),
                    re.compile("海报"),
                    re.compile("封面"),
                ],
                timeout_error,
                "剧目海报",
            )

        self._upload_playlet_contract_materials(page, metadata, timeout_error)

        self._ensure_playlet_form_fields(
            page,
            publish_title,
            publish_summary,
            episode_count,
            free_episode_count,
            producer_name,
            production_cost,
            timeout_error,
        )

        self._advance_playlet_to_file_step(page, metadata, timeout_error)

        raise PlatformPublishPaused("剧目提审第一步已完成，已停留在第二步剧集文件选取。")

    def _enter_playlet_plan(self, page, timeout_error) -> None:
        self._accept_playlet_agreement(page, timeout_error)
        try:
            page.get_by_text(re.compile("上架剧目并参与计划|上架剧目|参与计划")).first.click(timeout=5000)
            page.wait_for_timeout(1000)
        except timeout_error:
            pass

    def _accept_playlet_agreement(self, page, timeout_error) -> None:
        try:
            page.get_by_text(re.compile("我已阅读并同意|已阅读并同意|同意.*协议")).first.click(timeout=3000)
            page.wait_for_timeout(300)
            return
        except timeout_error:
            pass
        checkbox = page.locator('input[type="checkbox"]').first
        try:
            if checkbox.count() > 0 and not checkbox.is_checked():
                checkbox.check(timeout=3000)
                page.wait_for_timeout(300)
        except timeout_error:
            pass

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

    def _fill_first(self, page, labels: list[str], value: str) -> bool:
        for label in labels:
            for query in (label, re.compile(re.escape(label))):
                locator = page.get_by_placeholder(query).first
                if locator.count() == 0:
                    locator = page.get_by_label(query).first
                if locator.count() > 0:
                    locator.fill(value)
                    return True
        return False

    def _ensure_playlet_form_fields(
        self,
        page,
        title: str,
        summary: str,
        episode_count: object,
        free_episode_count: object,
        producer_name: str,
        production_cost: str,
        timeout_error,
    ) -> None:
        fields: list[dict[str, object]] = [
            {
                "name": "剧目名称",
                "value": title,
                "labels": ["剧目名称", "剧集名称", "短剧名称"],
                "placeholders": ["待提审剧目的名称", "请输入剧目名称", "请输入剧集名称", "请输入标题"],
                "textarea": False,
            },
            {
                "name": "剧目简介",
                "value": summary,
                "labels": ["剧目简介", "剧情简介"],
                "placeholders": ["剧情概要", "了解作品内容", "请输入简介", "请输入剧情简介"],
                "textarea": True,
            },
        ]
        if episode_count:
            fields.append(
                {
                    "name": "总集数",
                    "value": str(episode_count),
                    "labels": ["总集数", "剧集总数", "总剧集数量"],
                    "placeholders": ["总剧集数量", "总集数"],
                    "textarea": False,
                }
            )
        if free_episode_count is not None:
            fields.append(
                {
                    "name": "试看集数",
                    "value": str(free_episode_count),
                    "labels": ["试看集数", "免费集数", "免费试看集数", "免费观看集数"],
                    "placeholders": ["试看集数", "免费集数", "免费试看集数"],
                    "textarea": False,
                }
            )
        if producer_name:
            fields.append(
                {
                    "name": "制作方名称",
                    "value": producer_name,
                    "labels": ["制作方名称", "制作方主体名称", "剧目制作方名称", "剧目制作方"],
                    "placeholders": ["制作方主体名称", "制作方名称"],
                    "textarea": False,
                }
            )
        if production_cost:
            fields.append(
                {
                    "name": "剧目制作成本",
                    "value": production_cost,
                    "labels": ["剧目制作成本", "制作成本", "剧目成本"],
                    "placeholders": ["剧目制作成本", "成本配置比例情况报告"],
                    "textarea": False,
                }
            )
        missing = self._ensure_playlet_fields_by_dom(page, fields, timeout_error)
        if missing:
            self._wait_for_page(page, 500)

    def _ensure_playlet_fields_by_dom(
        self,
        page,
        fields: list[dict[str, object]],
        timeout_error,
    ) -> list[str]:
        evaluate = getattr(page, "evaluate", None)
        if not callable(evaluate):
            return [str(field.get("name") or "") for field in fields]
        try:
            result = evaluate(self._ensure_playlet_fields_by_dom_script(), {"fields": fields})
        except timeout_error as exception:
            raise RuntimeError("校验视频号表单字段失败，请重新打开发布页面后重试") from exception
        except Exception as exception:  # noqa: BLE001
            if self._is_page_closed_error(exception):
                raise RuntimeError("浏览器页面已关闭，无法校验视频号表单字段") from exception
            return [str(field.get("name") or "") for field in fields]
        if not isinstance(result, dict):
            return [str(field.get("name") or "") for field in fields]
        missing = result.get("missing")
        if isinstance(missing, list):
            return [str(item) for item in missing if str(item).strip()]
        return []

    def _fill_playlet_field(
        self,
        page,
        labels: list[str],
        value: str,
        timeout_error,
        field_label: str,
        *,
        required: bool = False,
    ) -> bool:
        text_value = str(value)
        if self._fill_playlet_field_with_locator(page, labels, text_value, timeout_error, field_label):
            return True
        if self._fill_weui_input_by_label(page, labels, text_value, timeout_error, field_label):
            return True
        patterns = [re.compile(re.escape(label)) for label in labels]
        if self._fill_text_field_near_text(page, patterns, text_value, timeout_error, field_label):
            return True
        if self._fill_first_verified(page, labels, text_value, timeout_error, field_label):
            return True
        if required:
            raise RuntimeError(f"未能填写视频号{field_label}，请重新打开发布页面后重试")
        return False

    def _fill_playlet_field_with_locator(
        self,
        page,
        labels: list[str],
        value: str,
        timeout_error,
        field_label: str,
        *,
        textarea_only: bool = False,
    ) -> bool:
        locator_getter = getattr(page, "locator", None)
        if not callable(locator_getter):
            return False
        input_selector = (
            "textarea.weui-desktop-form__textarea, textarea"
            if textarea_only
            else (
                "input.weui-desktop-form__input, input[type='text'], input[type='number'], "
                "input:not([type]), textarea.weui-desktop-form__textarea, textarea"
            )
        )
        group_selectors = [
            ".weui-desktop-form__control-group",
            ".cost_form",
            ".ant-form-item",
            ".form-item",
            ".form-row",
        ]
        for label in labels:
            for group_selector in group_selectors:
                try:
                    groups = locator_getter(group_selector).filter(has_text=label)
                    if groups.count() == 0:
                        continue
                    fields = groups.first.locator(input_selector)
                    if fields.count() == 0:
                        continue
                    if self._fill_locator_and_verify(fields.first, value, timeout_error, field_label):
                        return True
                except timeout_error:
                    continue
                except Exception as exception:  # noqa: BLE001
                    if self._is_page_closed_error(exception):
                        raise RuntimeError(f"浏览器页面已关闭，无法填写视频号{field_label}") from exception
                    continue
        return False

    def _fill_first_verified(self, page, labels: list[str], value: str, timeout_error, field_label: str) -> bool:
        for label in labels:
            for query in (label, re.compile(re.escape(label))):
                try:
                    locator = page.get_by_placeholder(query).first
                    if locator.count() == 0:
                        locator = page.get_by_label(query).first
                    if locator.count() > 0 and self._fill_locator_and_verify(locator, value, timeout_error, field_label):
                        return True
                except timeout_error:
                    continue
                except Exception as exception:  # noqa: BLE001
                    if self._is_page_closed_error(exception):
                        raise RuntimeError(f"浏览器页面已关闭，无法填写视频号{field_label}") from exception
                    continue
        return False

    def _fill_locator_and_verify(self, locator, value: str, timeout_error, field_label: str) -> bool:
        try:
            scroll = getattr(locator, "scroll_into_view_if_needed", None)
            if callable(scroll):
                scroll(timeout=3000)
            locator.fill(value, timeout=5000)
            self._dispatch_locator_input_events(locator, value)
            actual = self._locator_input_value(locator)
        except timeout_error:
            return False
        except Exception as exception:  # noqa: BLE001
            if self._is_page_closed_error(exception):
                raise RuntimeError(f"浏览器页面已关闭，无法填写视频号{field_label}") from exception
            return False
        return actual == value

    @staticmethod
    def _dispatch_locator_input_events(locator, value: str) -> None:
        evaluate = getattr(locator, "evaluate", None)
        if not callable(evaluate):
            return
        try:
            evaluate(
                """
                (element, value) => {
                    const proto = element instanceof HTMLTextAreaElement
                        ? HTMLTextAreaElement.prototype
                        : HTMLInputElement.prototype;
                    const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                    if (setter && element.value !== value) setter.call(element, value);
                    element.dispatchEvent(new Event('input', { bubbles: true }));
                    element.dispatchEvent(new Event('change', { bubbles: true }));
                    element.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: 'Process' }));
                }
                """,
                value,
            )
        except Exception:  # noqa: BLE001
            return

    @staticmethod
    def _locator_input_value(locator) -> str:
        input_value = getattr(locator, "input_value", None)
        if callable(input_value):
            try:
                return str(input_value(timeout=1000) or "")
            except Exception:  # noqa: BLE001
                pass
        evaluate = getattr(locator, "evaluate", None)
        if callable(evaluate):
            try:
                return str(evaluate("(element) => element.value || element.textContent || ''") or "")
            except Exception:  # noqa: BLE001
                pass
        return ""

    def _fill_weui_input_by_label(
        self,
        page,
        labels: list[str],
        value: str,
        timeout_error,
        field_label: str,
    ) -> bool:
        evaluate = getattr(page, "evaluate", None)
        if not callable(evaluate):
            return False
        try:
            result = evaluate(
                self._fill_weui_input_by_label_script(),
                {"labels": labels, "value": value},
            )
        except timeout_error as exception:
            raise RuntimeError(f"填写视频号{field_label}失败，请重新打开发布页面后重试") from exception
        except Exception as exception:  # noqa: BLE001
            if self._is_page_closed_error(exception):
                raise RuntimeError(f"浏览器页面已关闭，无法填写视频号{field_label}") from exception
            return False
        if not (isinstance(result, dict) and result.get("filled")):
            return False
        return str(result.get("value") or "") == value

    def _fill_weui_textarea_by_label(self, page, label: str, value: str, timeout_error) -> bool:
        if self._fill_playlet_field_with_locator(page, [label], value, timeout_error, label, textarea_only=True):
            return True
        evaluate = getattr(page, "evaluate", None)
        if not callable(evaluate):
            return False
        try:
            result = evaluate(self._fill_weui_textarea_by_label_script(), {"label": label, "value": value})
        except timeout_error as exception:
            raise RuntimeError(f"填写视频号{label}失败，请重新打开发布页面后重试") from exception
        except Exception as exception:  # noqa: BLE001
            if self._is_page_closed_error(exception):
                raise RuntimeError(f"浏览器页面已关闭，无法填写视频号{label}") from exception
            return False
        if not (isinstance(result, dict) and result.get("filled")):
            return False
        return str(result.get("value") or "") == value

    def _fill_text_field_near_text(
        self,
        page,
        label_patterns: list[re.Pattern[str]],
        value: str,
        timeout_error,
        field_label: str,
    ) -> bool:
        evaluate = getattr(page, "evaluate", None)
        if not callable(evaluate):
            return False
        try:
            result = evaluate(
                self._fill_text_field_near_text_script(),
                {"patterns": [pattern.pattern for pattern in label_patterns], "value": value},
            )
        except timeout_error as exception:
            raise RuntimeError(f"填写视频号{field_label}失败，请重新打开发布页面后重试") from exception
        except Exception as exception:  # noqa: BLE001
            if self._is_page_closed_error(exception):
                raise RuntimeError(f"浏览器页面已关闭，无法填写视频号{field_label}") from exception
            return False
        if not (isinstance(result, dict) and result.get("filled")):
            return False
        return str(result.get("value") or "") == value

    @staticmethod
    def _metadata_text(metadata: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = metadata.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return ""

    @classmethod
    def _playlet_summary(cls, title: str, summary: str | None, metadata: dict[str, Any]) -> str:
        raw_summary = cls._metadata_text(metadata, "summary", "description", "intro", "brief") or str(summary or "")
        normalized = cls._normalize_playlet_summary(raw_summary)
        if not normalized:
            normalized = f"《{title}》讲述人物在命运转折中的情感与成长故事。"
        return cls._limit_playlet_summary(normalized)

    @classmethod
    def _normalize_playlet_summary(cls, value: str) -> str:
        text = str(value or "").strip()
        summary_match = re.search(r"(?:剧目简介|剧情简介|简介)\s*[:：]\s*(.+)", text, flags=re.S)
        if summary_match:
            text = summary_match.group(1)
        else:
            text = re.sub(r"^\s*标题\s*[:：]\s*[^\r\n]*(?:\r?\n)+", "", text)
        text = re.sub(r"\s*(?:总集数|集数)\s*[:：]\s*\d+\s*集?\s*$", "", text.strip())
        text = re.sub(r"\s+", " ", text).strip()
        return text.strip(" ，,。；;、")

    @classmethod
    def _limit_playlet_summary(cls, value: str) -> str:
        if len(value) <= PLAYLET_SUMMARY_MAX_CHARS:
            return value
        keep = PLAYLET_SUMMARY_MAX_CHARS - len(PLAYLET_SUMMARY_ELLIPSIS)
        return value[:keep].rstrip(" ，,。；;、") + PLAYLET_SUMMARY_ELLIPSIS

    @staticmethod
    def _production_cost_wan(metadata: dict[str, Any]) -> str:
        value = metadata.get("productionCostWan")
        if value is None:
            value = metadata.get("costAmountWan")
        try:
            amount = int(float(str(value)))
        except (TypeError, ValueError):
            return ""
        return str(amount) if amount > 0 else ""

    def _upload_playlet_contract_materials(self, page, metadata: dict[str, Any], timeout_error) -> None:
        purchase_images = self._metadata_paths(metadata, "buyDramaContractImages", "purchaseContractImages")
        if purchase_images:
            self._set_file_input_near_text(
                page,
                purchase_images,
                [
                    re.compile("剧目制作证明材料"),
                    re.compile("制作证明材料"),
                    re.compile("剧目制作合同"),
                ],
                timeout_error,
                "剧目制作证明材料",
            )

        cost_images = self._metadata_paths(metadata, "costConfigReportImages", "costContractImages")
        if cost_images:
            self._set_file_input_near_text(
                page,
                cost_images,
                [
                    re.compile("成本配置比例情况报告"),
                    re.compile("成本配置比例"),
                    re.compile("成本配置报告"),
                ],
                timeout_error,
                "成本配置比例情况报告",
            )

    def _advance_playlet_to_file_step(self, page, metadata: dict[str, Any], timeout_error) -> None:
        self._wait_for_playlet_upload_file_names(page, self._expected_playlet_upload_paths(metadata), timeout_error)
        result = self._accept_playlet_notice_and_click_next(page, timeout_error)
        if not result.get("accepted"):
            raise RuntimeError("未找到视频号剧目审核服务使用须知勾选框，请手动勾选后重试")
        if not result.get("nextClicked"):
            raise RuntimeError("未找到视频号剧目提审“下一步”按钮，请确认第一步表单已完整填写")
        self._wait_for_playlet_file_step(page)

    def _expected_playlet_upload_paths(self, metadata: dict[str, Any]) -> list[Path]:
        paths: list[Path] = []
        cover_file = metadata.get("coverFile")
        if cover_file:
            cover_path = Path(cover_file)
            if cover_path.exists():
                paths.append(cover_path)
        paths.extend(self._metadata_paths(metadata, "buyDramaContractImages", "purchaseContractImages"))
        paths.extend(self._metadata_paths(metadata, "costConfigReportImages", "costContractImages"))
        return paths

    def _wait_for_playlet_upload_file_names(
        self,
        page,
        paths: list[Path],
        timeout_error,
        *,
        attempts: int = 12,
    ) -> None:
        if not paths:
            return
        evaluate = getattr(page, "evaluate", None)
        if not callable(evaluate):
            return
        payload = [{"name": path.name, "stem": path.stem} for path in paths]
        missing: list[str] = []
        for _attempt in range(attempts):
            try:
                result = evaluate(self._playlet_upload_file_names_state_script(), payload)
            except timeout_error:
                result = {}
            except Exception as exception:  # noqa: BLE001
                if self._is_page_closed_error(exception):
                    raise RuntimeError("浏览器页面已关闭，无法等待视频号文件上传完成") from exception
                return
            if isinstance(result, dict):
                missing = [str(item) for item in result.get("missing", [])]
                if not missing:
                    return
            self._wait_for_page(page, 500)
        return

    @staticmethod
    def _playlet_upload_file_names_state_script() -> str:
        return """
            (files) => {
                const normalized = (value) => String(value || '').replace(/\\s+/g, '');
                const text = normalized(document.body ? document.body.innerText || document.body.textContent : '');
                const missing = files
                    .filter((file) => {
                        const names = [normalized(file.name), normalized(file.stem)].filter(Boolean);
                        return !names.some((name) => text.includes(name));
                    })
                    .map((file) => file.name);
                return { missing };
            }
        """

    def _accept_playlet_notice_and_click_next(self, page, timeout_error) -> dict[str, bool]:
        locator_result = self._accept_playlet_notice_and_click_next_with_locators(page, timeout_error)
        if locator_result.get("nextClicked"):
            return locator_result
        evaluate = getattr(page, "evaluate", None)
        if not callable(evaluate):
            return locator_result
        last_result = locator_result
        for _attempt in range(10):
            try:
                result = evaluate(self._accept_playlet_notice_and_click_next_script())
            except timeout_error:
                result = {}
            except Exception as exception:  # noqa: BLE001
                if self._is_page_closed_error(exception):
                    raise RuntimeError("浏览器页面已关闭，无法进入视频号剧目提审第二步") from exception
                result = {}
            if isinstance(result, dict):
                last_result = {
                    "accepted": bool(result.get("accepted")),
                    "nextClicked": bool(result.get("nextClicked")),
                }
            if isinstance(result, dict) and result.get("nextClicked"):
                self._wait_for_page(page, 1200)
                return {"accepted": bool(result.get("accepted")), "nextClicked": True}
            locator_result = self._accept_playlet_notice_and_click_next_with_locators(page, timeout_error)
            if locator_result.get("nextClicked"):
                return locator_result
            if locator_result.get("accepted"):
                last_result = locator_result
            self._wait_for_page(page, 500)
        return last_result

    def _accept_playlet_notice_and_click_next_with_locators(self, page, timeout_error) -> dict[str, bool]:
        locator_getter = getattr(page, "locator", None)
        if not callable(locator_getter):
            return {"accepted": False, "nextClicked": False}
        accepted = False
        for _attempt in range(10):
            try:
                primary_next = page.locator(".next_btn button.weui-desktop-btn_primary").filter(
                    has_text=re.compile("^下一步$")
                ).first
                if primary_next.count() > 0:
                    primary_next.click(timeout=5000, force=True)
                    self._wait_for_page(page, 1200)
                    return {"accepted": True, "nextClicked": True}

                icon = page.locator(".form_footer .weui-desktop-icon-checkbox").first
                checkbox = page.locator(".form_footer input[type='checkbox']").first
                if icon.count() > 0:
                    icon.click(timeout=3000, force=True)
                    accepted = True
                elif checkbox.count() > 0:
                    checkbox.click(timeout=3000, force=True)
                    accepted = True
                else:
                    return {"accepted": False, "nextClicked": False}
            except timeout_error:
                return {"accepted": accepted, "nextClicked": False}
            except Exception as exception:  # noqa: BLE001
                if self._is_page_closed_error(exception):
                    raise RuntimeError("浏览器页面已关闭，无法勾选视频号剧目审核服务使用须知") from exception
                return {"accepted": accepted, "nextClicked": False}
            self._wait_for_page(page, 300)
        try:
            primary_next = page.locator(".next_btn button.weui-desktop-btn_primary").filter(
                has_text=re.compile("^下一步$")
            ).first
            if primary_next.count() > 0:
                primary_next.click(timeout=5000, force=True)
                self._wait_for_page(page, 1200)
                return {"accepted": True, "nextClicked": True}
        except timeout_error:
            pass
        except Exception as exception:  # noqa: BLE001
            if self._is_page_closed_error(exception):
                raise RuntimeError("浏览器页面已关闭，无法点击视频号剧目提审下一步") from exception
        return {"accepted": accepted, "nextClicked": False}

    @staticmethod
    def _accept_playlet_notice_and_click_next_script() -> str:
        return """
            () => {
                const normalized = (value) => String(value || '').replace(/\\s+/g, '');
                const mouseClick = (element) => {
                    if (!element) return;
                    element.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                    element.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                    element.click();
                };
                const visible = (el) => {
                    if (!el || !(el instanceof HTMLElement)) return false;
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                };
                const textOf = (el) => normalized(el.innerText || el.textContent || '');
                const footer = document.querySelector('.form_footer');
                let accepted = false;
                if (footer) {
                    try { footer.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (_) {}
                    const icon = footer.querySelector('.weui-desktop-icon-checkbox');
                    const input = footer.querySelector('input[type="checkbox"]');
                    if (icon) {
                        mouseClick(icon);
                        accepted = true;
                    }
                    if (input) {
                        if (!accepted) mouseClick(input);
                        if (!input.checked) {
                            input.checked = true;
                        }
                        input.setAttribute('checking', '');
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                        accepted = true;
                    }
                }
                const next = [
                    ...Array.from(document.querySelectorAll('.next_btn button.weui-desktop-btn_primary')),
                    ...Array.from(document.querySelectorAll('button.weui-desktop-btn_primary, [role="button"].weui-desktop-btn_primary, .weui-desktop-btn_primary'))
                ]
                    .filter(visible)
                    .filter((button) => /^(下一步|继续)$/.test(textOf(button)))
                    .filter((button) => {
                        const disabled = button.disabled
                            || button.getAttribute('aria-disabled') === 'true'
                            || /disabled/.test(String(button.className || ''));
                        return !disabled;
                    })[0] || null;
                let nextClicked = false;
                if (accepted && next) {
                    try { next.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (_) {}
                    mouseClick(next);
                    nextClicked = true;
                }
                return { accepted, nextClicked };
            }
        """

    def _wait_for_playlet_file_step(self, page, *, attempts: int = 20) -> bool:
        evaluate = getattr(page, "evaluate", None)
        if not callable(evaluate):
            return True
        for _attempt in range(attempts):
            try:
                result = evaluate(
                    """
                    () => {
                        const text = String(document.body ? document.body.innerText || document.body.textContent : '').replace(/\\s+/g, '');
                        return /剧集文件选取|视频文件|上传剧集|提审信息确认/.test(text);
                    }
                    """
                )
            except Exception as exception:  # noqa: BLE001
                if self._is_page_closed_error(exception):
                    raise RuntimeError("浏览器页面已关闭，无法确认视频号剧目提审第二步") from exception
                return True
            if result:
                return True
            self._wait_for_page(page, 500)
        return False

    @staticmethod
    def _metadata_paths(metadata: dict[str, Any], *keys: str) -> list[Path]:
        paths: list[Path] = []
        seen: set[str] = set()
        for key in keys:
            value = metadata.get(key)
            if not value:
                continue
            values = value if isinstance(value, (list, tuple)) else [value]
            for item in values:
                if not item:
                    continue
                path = Path(item)
                resolved = str(path)
                if resolved in seen or not path.exists():
                    continue
                paths.append(path)
                seen.add(resolved)
        return paths

    def _submit_playlet_and_wait_for_success(self, page, timeout_error) -> None:
        try:
            page.get_by_text(re.compile("提交审核|提交|发布|上架")).first.click(timeout=15000)
            page.wait_for_timeout(1000)
        except timeout_error as exception:
            raise RuntimeError("短剧表单已唤起，但未找到提交审核/发布按钮，任务不会标记完成。") from exception
        self._click_confirm_if_available(page, timeout_error)
        success_pattern = re.compile("提交成功|发布成功|上架成功|已提交|待审核|审核中")
        try:
            page.get_by_text(success_pattern).first.wait_for(timeout=15000)
            return
        except timeout_error:
            pass
        if self._page_has_text(page, success_pattern):
            return
        raise RuntimeError("短剧表单已唤起，但未确认提交成功，任务不会标记完成。")

    def _click_confirm_if_available(self, page, timeout_error) -> None:
        try:
            page.get_by_text(re.compile("确认提交|确定提交|确认|确定")).first.click(timeout=3000)
            page.wait_for_timeout(500)
        except timeout_error:
            pass

    @staticmethod
    def _page_has_text(page, pattern: re.Pattern[str]) -> bool:
        try:
            return page.get_by_text(pattern).first.count() > 0
        except Exception:  # noqa: BLE001
            return False

    def _set_default_playlet_options(self, page, timeout_error) -> None:
        self._click_text_option(page, [re.compile("^漫剧$")], timeout_error)
        self._set_ai_content_statement(page, timeout_error)
        self._set_submit_identity(page, timeout_error)
        self._click_text_option(page, [re.compile("^其他微短剧$")], timeout_error)

    def _set_ai_content_statement(self, page, timeout_error) -> None:
        label_pattern = re.compile("AI内容声明|AI\\s*内容声明|AI生成|AI\\s*生成")
        if self._click_ai_content_switch(page, timeout_error):
            return
        if self._enable_switch_near_text(page, label_pattern):
            return
        role_getter = getattr(page, "get_by_role", None)
        if callable(role_getter):
            try:
                switch = role_getter("switch", name=label_pattern).first
                if switch.count() > 0:
                    self._check_or_click(switch, timeout_error)
                    return
            except timeout_error:
                pass
            try:
                checkbox = role_getter("checkbox", name=label_pattern).first
                if checkbox.count() > 0:
                    self._check_or_click(checkbox, timeout_error)
                    return
            except timeout_error:
                pass
        label_getter = getattr(page, "get_by_label", None)
        if callable(label_getter):
            try:
                labelled = label_getter(label_pattern).first
                if labelled.count() > 0:
                    self._check_or_click(labelled, timeout_error)
                    return
            except timeout_error:
                pass
        self._click_text_option(page, [label_pattern], timeout_error)

    @staticmethod
    def _click_ai_content_switch(page, timeout_error) -> bool:
        locator_getter = getattr(page, "locator", None)
        if not callable(locator_getter):
            return False
        selectors = [
            ".speedupaudit_box label.switch_speedupaudit",
            ".speedupaudit_box label.weui-desktop-switch",
            ".speedupaudit_box .weui-desktop-switch__box",
        ]
        for _attempt in range(8):
            if WeChatVideoPublisher._is_ai_content_switch_checked(page):
                return True
            clicked = False
            for selector in selectors:
                try:
                    locator = locator_getter(selector).first
                    if locator.count() == 0:
                        continue
                    WeChatVideoPublisher._click_locator(locator, timeout_error, timeout=2500, force=True)
                    clicked = True
                    wait_for_timeout = getattr(page, "wait_for_timeout", None)
                    if callable(wait_for_timeout):
                        wait_for_timeout(400)
                    if WeChatVideoPublisher._is_ai_content_switch_checked(page):
                        return True
                except timeout_error:
                    continue
                except Exception:  # noqa: BLE001
                    continue
            wait_for_timeout = getattr(page, "wait_for_timeout", None)
            if callable(wait_for_timeout):
                wait_for_timeout(500)
        return WeChatVideoPublisher._is_ai_content_switch_checked(page)

    @staticmethod
    def _is_ai_content_switch_checked(page) -> bool:
        locator_getter = getattr(page, "locator", None)
        if not callable(locator_getter):
            return False
        selectors = [
            ".speedupaudit_box input.weui-desktop-switch__input[type='checkbox']",
            ".speedupaudit_box input[type='checkbox']",
        ]
        for selector in selectors:
            try:
                locator = locator_getter(selector).first
                if locator.count() > 0 and locator.is_checked():
                    return True
            except Exception:  # noqa: BLE001
                continue
        return False

    @staticmethod
    def _click_locator(locator, timeout_error, *, timeout: int, force: bool = False) -> None:
        click = getattr(locator, "click", None)
        if not callable(click):
            return
        try:
            click(timeout=timeout, force=force)
        except TypeError:
            click(timeout=timeout)
        except timeout_error:
            raise

    def _set_submit_identity(self, page, timeout_error) -> None:
        combined_patterns = [
            re.compile("剧目制作方版权方/授权播出方"),
            re.compile("剧目制作方/版权方/授权播出方"),
            re.compile("剧目制作方.*版权方/授权播出方"),
        ]
        target_patterns = [
            re.compile("^版权方/授权播出方$"),
            re.compile("版权方/授权播出方"),
            re.compile("授权播出方"),
        ]
        if self._click_radio_near_text(page, combined_patterns):
            return
        if self._click_radio_near_text(page, target_patterns):
            return
        if self._click_text_option(page, target_patterns, timeout_error):
            return
        self._click_text_option(page, [re.compile("^剧目制作方$")], timeout_error)

    @staticmethod
    def _enable_switch_near_text(page, pattern: re.Pattern[str]) -> bool:
        evaluate = getattr(page, "evaluate", None)
        if not callable(evaluate):
            return False
        script = """
            (pattern) => {
                const re = new RegExp(pattern);
                const normalized = (value) => String(value || '').replace(/\\s+/g, '');
                const visible = (el) => {
                    if (!el || !(el instanceof HTMLElement)) return false;
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                };
                const isOn = (control) => {
                    if (control.matches('input[type="checkbox"]')) return control.checked;
                    const aria = control.getAttribute('aria-checked');
                    if (aria === 'true') return true;
                    if (aria === 'false') return false;
                    const className = String(control.className || '').toLowerCase();
                    if (/checked|active|selected|open|on/.test(className)) return true;
                    const style = window.getComputedStyle(control);
                    const rgb = String(style.backgroundColor || '').match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
                    if (!rgb) return false;
                    const red = Number(rgb[1]);
                    const green = Number(rgb[2]);
                    const blue = Number(rgb[3]);
                    return (green > 120 && red < 140) || (blue > 150 && red < 150);
                };
                const controlsIn = (container) => Array.from(container.querySelectorAll([
                    'input[type="checkbox"]',
                    '[role="switch"]',
                    'button[aria-checked]',
                    '[aria-checked]',
                    '[class*="toggle"]',
                    '[class*="Toggle"]',
                    '[class*="switch"]',
                    '[class*="Switch"]'
                ].join(','))).filter(visible);
                const switchLikeIn = (container) => Array.from(container.querySelectorAll('*'))
                    .filter(visible)
                    .filter((item) => container === document.body || container.contains(item))
                    .filter((item) => {
                        const rect = item.getBoundingClientRect();
                        if (rect.width < 36 || rect.width > 110 || rect.height < 18 || rect.height > 54) return false;
                        if (rect.width / rect.height < 1.35) return false;
                        const style = window.getComputedStyle(item);
                        const radius = Number.parseFloat(style.borderRadius || '0');
                        const className = String(item.className || '').toLowerCase();
                        return radius >= rect.height / 3
                            || /switch|toggle|checkbox/.test(className)
                            || item.getAttribute('role') === 'switch';
                    });
                const checkNativeInput = (input) => {
                    if (!input) return false;
                    if (input.checked) return true;
                    const descriptor = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'checked');
                    if (descriptor && descriptor.set) descriptor.set.call(input, true);
                    else input.checked = true;
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    return input.checked;
                };
                const exactGroups = Array.from(document.querySelectorAll([
                    '.speedupaudit_box',
                    '.weui-desktop-form__control-group'
                ].join(',')))
                    .filter(visible)
                    .filter((el) => re.test(normalized(el.innerText || el.textContent)))
                    .sort((a, b) => normalized(a.innerText || a.textContent).length - normalized(b.innerText || b.textContent).length);
                for (const group of exactGroups) {
                    const input = group.querySelector([
                        'label.switch_speedupaudit input.weui-desktop-switch__input[type="checkbox"]',
                        'label.weui-desktop-switch input.weui-desktop-switch__input[type="checkbox"]',
                        'input.weui-desktop-switch__input[type="checkbox"]',
                        'input[type="checkbox"]'
                    ].join(','));
                    if (input && input.checked) return true;
                    const switchLabel = group.querySelector('label.switch_speedupaudit, label.weui-desktop-switch');
                    const switchBox = group.querySelector('.weui-desktop-switch__box');
                    const clickables = [switchBox, switchLabel, input].filter(Boolean);
                    for (const clickable of clickables) {
                        if (isOn(clickable) || (input && input.checked)) return true;
                        clickable.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                        clickable.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                        clickable.click();
                        const checkedInput = group.querySelector('input.weui-desktop-switch__input[type="checkbox"], input[type="checkbox"]');
                        if ((checkedInput && checkedInput.checked) || isOn(clickable) || (switchBox && isOn(switchBox))) return true;
                    }
                    if (checkNativeInput(input) && (switchBox ? isOn(switchBox) : true)) return true;
                }
                const rankedCandidates = (container, labelRect) => [
                    ...controlsIn(container),
                    ...switchLikeIn(container)
                ]
                    .filter((item, index, array) => array.indexOf(item) === index)
                    .map((item) => {
                        const rect = item.getBoundingClientRect();
                        const centerX = (rect.left + rect.right) / 2;
                        const centerY = (rect.top + rect.bottom) / 2;
                        const labelCenterY = (labelRect.top + labelRect.bottom) / 2;
                        const dx = Math.max(0, centerX - labelRect.right);
                        const dy = Math.abs(centerY - labelCenterY);
                        const leftPenalty = centerX < labelRect.right ? 500 : 0;
                        return { item, score: dx + dy * 5 + leftPenalty, dx, dy };
                    })
                    .filter((candidate) => candidate.dx < 460 && candidate.dy < 80)
                    .sort((a, b) => a.score - b.score);
                const labels = Array.from(document.querySelectorAll('body *'))
                    .filter(visible)
                    .filter((el) => re.test(normalized(el.innerText || el.textContent)))
                    .sort((a, b) => normalized(a.innerText || a.textContent).length - normalized(b.innerText || b.textContent).length);
                for (const label of labels) {
                    let container = label;
                    for (let depth = 0; container && depth < 6; depth += 1, container = container.parentElement) {
                        const labelRect = label.getBoundingClientRect();
                        const candidates = rankedCandidates(container, labelRect);
                        if (!candidates.length) continue;
                        const control = candidates[0].item;
                        if (!isOn(control)) control.click();
                        return true;
                    }
                    const labelRect = label.getBoundingClientRect();
                    const nearby = rankedCandidates(document.body, labelRect)[0];
                    if (nearby && nearby.score < 600) {
                        if (!isOn(nearby.item)) nearby.item.click();
                        return true;
                    }
                }
                return false;
            }
        """
        try:
            return bool(evaluate(script, pattern.pattern))
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def _click_radio_near_text(page, patterns: list[re.Pattern[str]]) -> bool:
        evaluate = getattr(page, "evaluate", None)
        if not callable(evaluate):
            return False
        script = """
            (patterns) => {
                const regexps = patterns.map((pattern) => new RegExp(pattern));
                const normalized = (value) => String(value || '').replace(/\\s+/g, '');
                const visible = (el) => {
                    if (!el || !(el instanceof HTMLElement)) return false;
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                };
                const isChecked = (control) => {
                    if (control.matches('input[type="radio"]')) return control.checked;
                    const aria = control.getAttribute('aria-checked');
                    if (aria === 'true') return true;
                    const className = String(control.className || '').toLowerCase();
                    return /checked|active|selected/.test(className);
                };
                const controlsIn = (container) => Array.from(container.querySelectorAll([
                    'input[type="radio"]',
                    '[role="radio"]',
                    '[class*="radio"]',
                    '[class*="Radio"]'
                ].join(','))).filter(visible);
                const labels = Array.from(document.querySelectorAll('body *'))
                    .filter(visible)
                    .filter((el) => {
                        const text = normalized(el.innerText || el.textContent);
                        return text && regexps.some((re) => re.test(text));
                    })
                    .sort((a, b) => normalized(a.innerText || a.textContent).length - normalized(b.innerText || b.textContent).length);
                for (const label of labels) {
                    let container = label;
                    for (let depth = 0; container && depth < 5; depth += 1, container = container.parentElement) {
                        const controls = controlsIn(container);
                        if (!controls.length) continue;
                        const labelRect = label.getBoundingClientRect();
                        const control = controls
                            .map((item) => {
                                const rect = item.getBoundingClientRect();
                                const dx = Math.abs((rect.left + rect.right) / 2 - labelRect.left);
                                const dy = Math.abs((rect.top + rect.bottom) / 2 - (labelRect.top + labelRect.bottom) / 2);
                                return { item, score: dx + dy * 4 };
                            })
                            .sort((a, b) => a.score - b.score)[0].item;
                        if (!isChecked(control)) control.click();
                        return true;
                    }
                    label.click();
                    return true;
                }
                return false;
            }
        """
        try:
            return bool(evaluate(script, [pattern.pattern for pattern in patterns]))
        except Exception:  # noqa: BLE001
            return False

    def _check_or_click(self, locator, timeout_error) -> None:
        try:
            is_checked = getattr(locator, "is_checked", None)
            if callable(is_checked) and is_checked():
                return
        except Exception:  # noqa: BLE001
            pass
        try:
            check = getattr(locator, "check", None)
            if callable(check):
                check(timeout=3000)
                return
        except Exception:  # noqa: BLE001
            pass
        try:
            click = getattr(locator, "click", None)
            if callable(click):
                click(timeout=3000)
        except timeout_error:
            pass

    def _click_text_option(self, page, patterns: list[re.Pattern[str]], timeout_error) -> bool:
        for pattern in patterns:
            try:
                page.get_by_text(pattern).first.click(timeout=3000)
                page.wait_for_timeout(200)
                return True
            except timeout_error:
                continue
            except Exception as exception:  # noqa: BLE001
                if self._is_page_closed_error(exception):
                    raise RuntimeError(f"浏览器页面已关闭，选择视频号表单选项失败：{pattern.pattern}") from exception
        return False

    def _set_monetization_type(self, page, label: str, timeout_error) -> None:
        try:
            page.get_by_text(re.compile("变现类型|收益类型|付费类型")).first.click(timeout=3000)
        except timeout_error:
            pass
        except Exception as exception:  # noqa: BLE001
            if self._is_page_closed_error(exception):
                raise RuntimeError("浏览器页面已关闭，等待视频号剧集变现类型控件失败") from exception
            raise RuntimeError("等待视频号剧集变现类型控件失败") from exception
        try:
            page.get_by_text(re.compile(re.escape(label))).first.click(timeout=5000)
        except timeout_error as exception:
            raise RuntimeError(f"未找到视频号剧集变现类型选项：{label}") from exception
        except Exception as exception:  # noqa: BLE001
            if self._is_page_closed_error(exception):
                raise RuntimeError(f"浏览器页面已关闭，选择视频号剧集变现类型失败：{label}") from exception
            raise RuntimeError(f"选择视频号剧集变现类型失败：{label}") from exception

    @staticmethod
    def _is_page_closed_error(exception: Exception) -> bool:
        message = str(exception)
        return "Target page, context or browser has been closed" in message

    def _set_file_input(self, page, files: Path | list[Path], button_pattern, timeout_error) -> None:
        paths = [str(item) for item in files] if isinstance(files, list) else str(files)
        try:
            with page.expect_file_chooser(timeout=5000) as chooser:
                page.get_by_text(button_pattern).first.click(timeout=5000)
            self._set_file_chooser_files(page, chooser.value, paths)
            return
        except timeout_error:
            pass
        file_input = page.locator('input[type="file"]').first
        if file_input.count() > 0:
            self._set_locator_files(page, file_input, paths)
            return
        try:
            with page.expect_file_chooser(timeout=5000) as chooser:
                page.get_by_text(button_pattern).first.click(timeout=5000)
            self._set_file_chooser_files(page, chooser.value, paths)
        except timeout_error as exception:
            raise RuntimeError("未找到视频号剧集管理上传入口，请确认已登录并停留在剧集管理页面") from exception

    def _set_file_input_near_text(
        self,
        page,
        files: Path | list[Path],
        label_patterns: list[re.Pattern[str]],
        timeout_error,
        field_label: str,
    ) -> None:
        paths = [str(item) for item in files] if isinstance(files, list) else str(files)
        path_list = [Path(path) for path in paths] if isinstance(paths, list) else [Path(paths)]
        self._validate_material_upload_files(path_list, field_label)
        self._validate_material_upload_file_count(path_list, field_label)
        if self._try_set_material_files_by_labelled_button(page, paths, label_patterns, timeout_error, field_label, path_list):
            return
        button_controls = self._mark_material_upload_button(page, label_patterns, timeout_error, field_label)
        if button_controls:
            button_marker = str(button_controls.get("buttonMarker") or "")
            if button_marker and self._try_set_material_files_by_marked_button(page, paths, button_marker, timeout_error, field_label):
                return

        try:
            controls = self._mark_material_upload_controls(page, label_patterns, timeout_error, field_label)
        except RuntimeError as exception:
            raise RuntimeError(
                f"视频号{field_label}上传失败：已尝试点击该字段的“选择文件”按钮，但没有触发文件选择器；"
                "同时也没有找到隐藏上传控件。请确认发布页停留在第 1 步且该字段已显示。"
            ) from exception
        input_marker = str(controls["inputMarker"])
        button_marker = str(controls.get("buttonMarker") or "")
        field_marker = str(controls.get("fieldMarker") or "")
        if button_marker:
            if self._try_set_material_files_by_marked_button(page, paths, button_marker, timeout_error, field_label):
                return
            controls = self._mark_material_upload_controls(page, label_patterns, timeout_error, field_label)
            input_marker = str(controls["inputMarker"])
            button_marker = str(controls.get("buttonMarker") or "")
            field_marker = str(controls.get("fieldMarker") or "")
        self._set_marked_file_input_files(page, input_marker, paths, field_label)
        self._dispatch_marked_file_input_events(page, input_marker)
        if self._material_upload_field_accepted_files(page, field_marker, path_list):
            return
        if button_marker:
            controls = self._mark_material_upload_controls(page, label_patterns, timeout_error, field_label)
            button_marker = str(controls.get("buttonMarker") or "")
            field_marker = str(controls.get("fieldMarker") or "")
            if button_marker and self._try_set_material_files_by_marked_button(page, paths, button_marker, timeout_error, field_label):
                return
        controls = self._mark_material_upload_controls(page, label_patterns, timeout_error, field_label)
        input_marker = str(controls["inputMarker"])
        field_marker = str(controls.get("fieldMarker") or "")
        self._set_marked_file_input_files(page, input_marker, paths, field_label)
        self._dispatch_marked_file_input_events(page, input_marker)
        if self._material_upload_field_accepted_files(page, field_marker, path_list):
            return
        state = self._material_upload_field_state(page, field_marker, path_list)
        detail = self._material_upload_failure_detail(state)
        names = "、".join(path.name for path in path_list)
        raise RuntimeError(f"视频号{field_label}文件未被页面接收：{names}{detail}，请重新打开发布页面后重试")

    def _try_set_material_files_by_labelled_button(
        self,
        page,
        paths: str | list[str],
        label_patterns: list[re.Pattern[str]],
        timeout_error,
        field_label: str,
        path_list: list[Path],
    ) -> bool:
        locator_getter = getattr(page, "locator", None)
        expect_file_chooser = getattr(page, "expect_file_chooser", None)
        if not callable(locator_getter) or not callable(expect_file_chooser):
            return False
        upload_button_text = re.compile("选择文件|重新选择|上传文件|添加文件")
        group_selectors = [
            ".weui-desktop-form__control-group",
            ".audit-form-upload",
            ".weui-desktop-form__controls",
            ".ant-form-item",
            ".form-item",
            ".form-row",
        ]
        for pattern in label_patterns:
            for group_selector in group_selectors:
                try:
                    groups = page.locator(group_selector).filter(has_text=pattern)
                    group_count = min(groups.count(), 5)
                except Exception as exception:  # noqa: BLE001
                    if self._is_page_closed_error(exception):
                        raise RuntimeError(f"浏览器页面已关闭，无法上传视频号{field_label}") from exception
                    continue
                for index in range(group_count):
                    try:
                        group = groups.nth(index)
                        field_marker = f"aidramaMaterialField{time.time_ns()}"
                        self._mark_locator_as_upload_field(group, field_marker)
                        buttons = group.locator("button, [role='button'], label, .weui-desktop-btn").filter(
                            has_text=upload_button_text
                        )
                        button_count = min(buttons.count(), 3)
                    except Exception as exception:  # noqa: BLE001
                        if self._is_page_closed_error(exception):
                            raise RuntimeError(f"浏览器页面已关闭，无法上传视频号{field_label}") from exception
                        continue
                    for button_index in range(button_count):
                        try:
                            with page.expect_file_chooser(timeout=3500) as chooser:
                                buttons.nth(button_index).click(timeout=5000)
                            self._set_file_chooser_files(page, chooser.value, paths)
                            self._wait_for_page(page, 1000)
                            return True
                        except timeout_error:
                            self._wait_for_page(page, 500)
                            continue
                        except Exception as exception:  # noqa: BLE001
                            if self._is_page_closed_error(exception):
                                raise RuntimeError(f"浏览器页面已关闭，无法上传视频号{field_label}") from exception
                            self._wait_for_page(page, 500)
                            continue
        return False

    @staticmethod
    def _mark_locator_as_upload_field(locator, field_marker: str) -> None:
        evaluate = getattr(locator, "evaluate", None)
        if not callable(evaluate):
            return
        try:
            evaluate("(element, marker) => element.setAttribute('data-aidrama-upload-field', marker)", field_marker)
        except Exception:  # noqa: BLE001
            return

    @staticmethod
    def _validate_material_upload_files(files: list[Path], field_label: str) -> None:
        max_size = 10 * 1024 * 1024
        for path in files:
            if not path.exists():
                raise RuntimeError(f"视频号{field_label}文件不存在：{path}")
            if path.stat().st_size > max_size:
                raise RuntimeError(f"视频号{field_label}文件超过 10MB，无法上传：{path.name}")

    @staticmethod
    def _validate_material_upload_file_count(files: list[Path], field_label: str) -> None:
        limits = {
            "剧目海报": 1,
            "成本配置比例情况报告": 1,
            "剧目制作证明材料": 4,
        }
        limit = limits.get(field_label)
        if limit is not None and len(files) > limit:
            raise RuntimeError(f"视频号{field_label}最多支持上传 {limit} 个文件。")

    @staticmethod
    def _material_upload_failure_detail(state: dict[str, Any]) -> str:
        if not isinstance(state, dict) or not state:
            return ""
        reason = str(state.get("reason") or "").strip()
        text = re.sub(r"\s+", " ", str(state.get("text") or "")).strip()
        if reason:
            return f"（页面状态：{reason}）"
        if text:
            return f"（页面显示：{text[:120]}）"
        return ""

    def _mark_material_upload_button(
        self,
        page,
        label_patterns: list[re.Pattern[str]],
        timeout_error,
        field_label: str,
    ) -> dict[str, Any] | None:
        button_marker = f"aidramaMaterialButton{time.time_ns()}"
        field_marker = f"aidramaMaterialField{time.time_ns()}"
        evaluate = getattr(page, "evaluate", None)
        if not callable(evaluate):
            return None
        payload = {
            "patterns": [pattern.pattern for pattern in label_patterns],
            "buttonMarker": button_marker,
            "fieldMarker": field_marker,
        }
        for _attempt in range(10):
            try:
                result = evaluate(self._mark_material_upload_button_script(), payload)
            except timeout_error:
                return None
            except Exception as exception:  # noqa: BLE001
                if self._is_page_closed_error(exception):
                    raise RuntimeError(f"浏览器页面已关闭，无法上传视频号{field_label}") from exception
                return None
            if isinstance(result, dict) and result.get("buttonMarked"):
                return result
            self._wait_for_page(page, 300)
        return None

    def _mark_material_upload_controls(
        self,
        page,
        label_patterns: list[re.Pattern[str]],
        timeout_error,
        field_label: str,
    ) -> dict[str, Any]:
        input_marker = f"aidramaMaterialInput{time.time_ns()}"
        button_marker = f"aidramaMaterialButton{time.time_ns()}"
        field_marker = f"aidramaMaterialField{time.time_ns()}"
        evaluate = getattr(page, "evaluate", None)
        if not callable(evaluate):
            raise RuntimeError(f"未找到视频号{field_label}上传控件，请重新打开发布页面后重试")
        payload = {
            "patterns": [pattern.pattern for pattern in label_patterns],
            "inputMarker": input_marker,
            "buttonMarker": button_marker,
            "fieldMarker": field_marker,
        }
        for _attempt in range(10):
            try:
                result = evaluate(self._mark_material_upload_controls_script(), payload)
            except timeout_error as exception:
                raise RuntimeError(f"未找到视频号{field_label}上传控件，请重新打开发布页面后重试") from exception
            except Exception as exception:  # noqa: BLE001
                if self._is_page_closed_error(exception):
                    raise RuntimeError(f"浏览器页面已关闭，无法上传视频号{field_label}") from exception
                raise RuntimeError(f"定位视频号{field_label}上传控件失败") from exception
            if isinstance(result, dict) and result.get("inputMarked"):
                return result
            if result is True:
                return {"inputMarker": input_marker, "buttonMarker": None}
            self._wait_for_page(page, 300)
        raise RuntimeError(f"未找到视频号{field_label}上传控件，请重新打开发布页面后重试")

    def _try_set_material_files_by_marked_button(
        self,
        page,
        paths: str | list[str],
        button_marker: str,
        timeout_error,
        field_label: str,
    ) -> bool:
        selector = f'[data-aidrama-upload-button="{button_marker}"]'
        locator_getter = getattr(page, "locator", None)
        expect_file_chooser = getattr(page, "expect_file_chooser", None)
        if not callable(locator_getter) or not callable(expect_file_chooser):
            return False
        try:
            with page.expect_file_chooser(timeout=3500) as chooser:
                page.locator(selector).first.click(timeout=5000)
            self._set_file_chooser_files(page, chooser.value, paths)
            self._wait_for_page(page, 1000)
            return True
        except timeout_error:
            self._wait_for_page(page, 600)
            return False
        except Exception as exception:  # noqa: BLE001
            if self._is_page_closed_error(exception):
                raise RuntimeError(f"浏览器页面已关闭，无法上传视频号{field_label}") from exception
            self._wait_for_page(page, 600)
            return False

    def _set_marked_file_input_files(
        self,
        page,
        marker: str,
        paths: str | list[str],
        field_label: str,
    ) -> None:
        selector = f'input[type="file"][data-aidrama-file-input="{marker}"]'
        locator_getter = getattr(page, "locator", None)
        if callable(locator_getter):
            try:
                locator = page.locator(selector).first
                if locator.count() > 0:
                    self._set_locator_files(page, locator, paths)
                    return
            except Exception as exception:  # noqa: BLE001
                if self._is_page_closed_error(exception):
                    raise RuntimeError(f"浏览器页面已关闭，无法上传视频号{field_label}") from exception
        self._set_marked_file_input_files_with_cdp(page, marker, paths)

    @staticmethod
    def _marked_file_input_has_files(page, marker: str, expected_count: int) -> bool:
        evaluate = getattr(page, "evaluate", None)
        if not callable(evaluate):
            return False
        try:
            return bool(
                evaluate(
                    """
                    ({ marker, expectedCount }) => {
                        const input = document.querySelector(`input[type="file"][data-aidrama-file-input="${marker}"]`);
                        return Boolean(input && input.files && input.files.length >= expectedCount);
                    }
                    """,
                    {"marker": marker, "expectedCount": expected_count},
                )
            )
        except Exception:  # noqa: BLE001
            return False

    def _material_upload_field_accepted_files(self, page, field_marker: str, files: list[Path]) -> bool:
        if not field_marker:
            return False
        for _attempt in range(60):
            result = self._material_upload_field_state(page, field_marker, files)
            if isinstance(result, dict) and result.get("visibleAccepted"):
                return True
            self._wait_for_page(page, 500)
        return False

    @staticmethod
    def _material_upload_field_state(page, field_marker: str, files: list[Path]) -> dict[str, Any]:
        evaluate = getattr(page, "evaluate", None)
        if not callable(evaluate):
            return {}
        try:
            return evaluate(
                """
                ({ marker, files }) => {
                    const field = document.querySelector(`[data-aidrama-upload-field="${marker}"]`);
                    if (!field) return { visibleAccepted: false, reason: 'field-missing' };
                    const normalized = (value) => String(value || '').replace(/\\s+/g, '');
                    const visible = (el) => {
                        if (!el || !(el instanceof HTMLElement)) return false;
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                    };
                    const text = normalized(field.innerText || field.textContent);
                    const expectedNames = files.flatMap((file) => {
                        const name = normalized(file.name);
                        const stem = normalized(file.stem);
                        return [name, stem].filter(Boolean);
                    });
                    const nameVisible = expectedNames.some((name) => name && text.includes(name));
                    const successTextVisible = /上传成功|已上传/.test(text);
                    const explicitFileName = Array.from(field.querySelectorAll('.img_text'))
                        .some((item) => expectedNames.some((name) => name && normalized(item.textContent).includes(name)));
                    const visiblePreview = Array.from(field.querySelectorAll([
                        'img[src]',
                        '.img_text',
                        '.previewimg_container',
                        '.file-delete-icon',
                        '[class*="preview"]',
                        '[class*="Preview"]',
                        '[class*="file-list"]',
                        '[class*="FileList"]',
                        '[class*="upload-list"]',
                        '[class*="UploadList"]'
                    ].join(','))).some(visible);
                    return {
                        visibleAccepted: Boolean(nameVisible || explicitFileName || successTextVisible || visiblePreview),
                        nameVisible: Boolean(nameVisible),
                        explicitFileName: Boolean(explicitFileName),
                        successTextVisible: Boolean(successTextVisible),
                        visiblePreview: Boolean(visiblePreview),
                        text: text.slice(0, 300),
                    };
                }
                """,
                {
                    "marker": field_marker,
                    "files": [{"name": path.name, "stem": path.stem} for path in files],
                },
            )
        except Exception:  # noqa: BLE001
            return {}

    def _try_set_material_files_by_button(
        self,
        page,
        paths: str | list[str],
        label_patterns: list[re.Pattern[str]],
        timeout_error,
        field_label: str,
    ) -> bool:
        marker = f"aidramaMaterialButton{time.time_ns()}"
        selector = f'[data-aidrama-upload-button="{marker}"]'
        try:
            marked = bool(page.evaluate(
                self._reveal_material_upload_script(),
                {"patterns": [pattern.pattern for pattern in label_patterns], "marker": marker},
            ))
        except Exception as exception:  # noqa: BLE001
            if self._is_page_closed_error(exception):
                raise RuntimeError(f"浏览器页面已关闭，无法展开视频号{field_label}上传控件") from exception
            # Some pages expose the file input directly; failing to click the visible
            # wrapper should not prevent the lower-level input fallback.
            return False
        if not marked:
            return False
        try:
            with page.expect_file_chooser(timeout=2500) as chooser:
                page.locator(selector).first.click(timeout=5000)
            self._set_file_chooser_files(page, chooser.value, paths)
            return True
        except timeout_error:
            self._wait_for_page(page, 600)
            return False
        except Exception as exception:  # noqa: BLE001
            if self._is_page_closed_error(exception):
                raise RuntimeError(f"浏览器页面已关闭，无法上传视频号{field_label}") from exception
            self._wait_for_page(page, 600)
            return False

    def _mark_file_input_near_text(
        self,
        page,
        label_patterns: list[re.Pattern[str]],
        timeout_error,
        field_label: str,
    ) -> str:
        marker = f"aidramaMaterialInput{time.time_ns()}"
        evaluate = getattr(page, "evaluate", None)
        if not callable(evaluate):
            raise RuntimeError(f"未找到视频号{field_label}上传控件，请重新打开发布页面后重试")
        for _attempt in range(10):
            try:
                marked = bool(evaluate(self._mark_file_input_script(), {"patterns": [pattern.pattern for pattern in label_patterns], "marker": marker}))
            except timeout_error as exception:
                raise RuntimeError(f"未找到视频号{field_label}上传控件，请重新打开发布页面后重试") from exception
            except Exception as exception:  # noqa: BLE001
                if self._is_page_closed_error(exception):
                    raise RuntimeError(f"浏览器页面已关闭，无法上传视频号{field_label}") from exception
                raise RuntimeError(f"定位视频号{field_label}上传控件失败") from exception
            if marked:
                return marker
            self._wait_for_page(page, 300)
        raise RuntimeError(f"未找到视频号{field_label}上传控件，请重新打开发布页面后重试")

    @staticmethod
    def _wait_for_page(page, milliseconds: int) -> None:
        wait_for_timeout = getattr(page, "wait_for_timeout", None)
        if callable(wait_for_timeout):
            try:
                wait_for_timeout(milliseconds)
            except Exception:
                pass

    @staticmethod
    def _mark_material_upload_button_script() -> str:
        return """
            ({ patterns, buttonMarker, fieldMarker }) => {
                const regexps = patterns.map((pattern) => new RegExp(pattern));
                const normalized = (value) => String(value || '').replace(/\\s+/g, '');
                const textOf = (el) => {
                    if (!el) return '';
                    const clone = el.cloneNode(true);
                    if (clone instanceof HTMLElement) {
                        clone.querySelectorAll([
                            '.weui-desktop-popover__wrp',
                            '.weui-desktop-popover',
                            '.tips_icon',
                            'svg'
                        ].join(',')).forEach((node) => node.remove());
                    }
                    return normalized(clone.innerText || clone.textContent || el.innerText || el.textContent);
                };
                const visible = (el) => {
                    if (!el || !(el instanceof HTMLElement)) return false;
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                };
                const matchesLabel = (el) => {
                    const text = textOf(el);
                    return text && regexps.some((re) => re.test(text));
                };
                const uploadButtonsIn = (region) => Array.from(region.querySelectorAll([
                    'button',
                    '[role="button"]',
                    'label',
                    '.webuploader-pick',
                    '.weui-desktop-upload',
                    '.weui-desktop-upload__btn',
                    '.weui-desktop-upload__img__btn',
                    '.weui-desktop-upload__input-box',
                    '.upload-button-wrapper',
                    '.upload-box',
                    '.upload',
                    '.Upload',
                    '[class*="upload"]',
                    '[class*="Upload"]'
                ].join(',')))
                    .filter(visible)
                    .filter((button) => !/下载|模版|模板/.test(textOf(button)));
                const uploadRegionsIn = (container) => Array.from(container.querySelectorAll([
                    '.weui-desktop-form__control-group',
                    '.audit-form-upload',
                    '.custom-file-upload',
                    '.custom-image-upload',
                    '.weui-desktop-form__controls',
                    '.ant-form-item',
                    '.semi-form-field',
                    '.t-form__item',
                    '.form-item',
                    '.form-row',
                    '.field-row'
                ].join(','))).filter((region) => uploadButtonsIn(region).length > 0);
                const elementRect = (el) => {
                    let current = el;
                    for (let depth = 0; current && depth < 8; depth += 1, current = current.parentElement) {
                        const rect = current.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) return rect;
                    }
                    return el.getBoundingClientRect();
                };
                const relationScore = (anchor, region) => {
                    if (region.contains(anchor)) return 0;
                    const relation = anchor.compareDocumentPosition(region);
                    if (!(relation & Node.DOCUMENT_POSITION_FOLLOWING)) return Number.POSITIVE_INFINITY;
                    const anchorRect = anchor.getBoundingClientRect();
                    const regionRect = elementRect(region);
                    const verticalDistance = regionRect.top - anchorRect.bottom;
                    if (verticalDistance < -120 || verticalDistance > 1000) return Number.POSITIVE_INFINITY;
                    const horizontalDistance = Math.abs(regionRect.left - anchorRect.left);
                    if (horizontalDistance > 1300) return Number.POSITIVE_INFINITY;
                    return verticalDistance + horizontalDistance * 0.05;
                };
                const bestButtonIn = (region) => uploadButtonsIn(region)
                    .sort((a, b) => {
                        const aText = textOf(a);
                        const bText = textOf(b);
                        const aBonus = /选择文件|重新选择|上传文件|添加文件/.test(aText) ? -100 : 0;
                        const bBonus = /选择文件|重新选择|上传文件|添加文件/.test(bText) ? -100 : 0;
                        return aBonus - bBonus;
                    })[0] || null;
                const markRegion = (region) => {
                    const button = bestButtonIn(region);
                    if (!button) return null;
                    region.setAttribute('data-aidrama-upload-field', fieldMarker);
                    button.setAttribute('data-aidrama-upload-button', buttonMarker);
                    return {
                        buttonMarked: true,
                        buttonMarker,
                        fieldMarker,
                        fieldText: textOf(region).slice(0, 200),
                        buttonText: textOf(button).slice(0, 80),
                    };
                };
                const anchors = Array.from(document.querySelectorAll('body *'))
                    .filter(visible)
                    .filter(matchesLabel)
                    .sort((a, b) => textOf(a).length - textOf(b).length);
                for (const anchor of anchors) {
                    try { anchor.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (_) {}
                    const directRegion = anchor.closest('.weui-desktop-form__control-group');
                    if (directRegion) {
                        const result = markRegion(directRegion);
                        if (result) return result;
                    }
                    const regions = [];
                    let container = anchor.parentElement;
                    for (let depth = 0; container && depth < 8; depth += 1, container = container.parentElement) {
                        regions.push(...uploadRegionsIn(container));
                    }
                    const uniqueRegions = regions
                        .filter((region, index, array) => array.indexOf(region) === index)
                        .map((region) => ({ region, score: relationScore(anchor, region) }))
                        .filter((candidate) => Number.isFinite(candidate.score))
                        .sort((a, b) => a.score - b.score);
                    for (const candidate of uniqueRegions) {
                        const result = markRegion(candidate.region);
                        if (result) return result;
                    }
                }
                return null;
            }
        """

    @staticmethod
    def _mark_material_upload_controls_script() -> str:
        return """
            ({ patterns, inputMarker, buttonMarker, fieldMarker }) => {
                const regexps = patterns.map((pattern) => new RegExp(pattern));
                const normalized = (value) => String(value || '').replace(/\\s+/g, '');
                const textOf = (el) => {
                    if (!el) return '';
                    const clone = el.cloneNode(true);
                    if (clone instanceof HTMLElement) {
                        clone.querySelectorAll([
                            '.weui-desktop-popover__wrp',
                            '.weui-desktop-popover',
                            '.tips_icon',
                            'svg'
                        ].join(',')).forEach((node) => node.remove());
                    }
                    return normalized(clone.innerText || clone.textContent || el.innerText || el.textContent);
                };
                const visible = (el) => {
                    if (!el || !(el instanceof HTMLElement)) return false;
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                };
                const matchesLabel = (el) => {
                    const text = textOf(el);
                    return text && regexps.some((re) => re.test(text));
                };
                const uploadRegionsIn = (container) => Array.from(container.querySelectorAll([
                    '.weui-desktop-form__control-group',
                    '.audit-form-upload',
                    '.custom-file-upload',
                    '.custom-image-upload',
                    '.upload-button-wrapper',
                    '.ant-form-item',
                    '.semi-form-field',
                    '.t-form__item',
                    '.form-item',
                    '.form-row',
                    '.field-row'
                ].join(','))).filter((region) => region.querySelector('input[type="file"]'));
                const uploadButtonsIn = (region) => Array.from(region.querySelectorAll([
                    'button',
                    '[role="button"]',
                    'label',
                    '.webuploader-pick',
                    '.weui-desktop-upload',
                    '.weui-desktop-upload__btn',
                    '.weui-desktop-upload__img__btn',
                    '.weui-desktop-upload__input-box',
                    '.upload-button-wrapper',
                    '.upload-box',
                    '.upload',
                    '.Upload',
                    '[class*="upload"]',
                    '[class*="Upload"]'
                ].join(',')))
                    .filter(visible)
                    .filter((button) => !/下载|模版|模板/.test(textOf(button)));
                const elementRect = (el) => {
                    let current = el;
                    for (let depth = 0; current && depth < 8; depth += 1, current = current.parentElement) {
                        const rect = current.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) return rect;
                    }
                    return el.getBoundingClientRect();
                };
                const relationScore = (anchor, region) => {
                    if (region.contains(anchor)) return 0;
                    const relation = anchor.compareDocumentPosition(region);
                    if (!(relation & Node.DOCUMENT_POSITION_FOLLOWING)) return Number.POSITIVE_INFINITY;
                    const anchorRect = anchor.getBoundingClientRect();
                    const regionRect = elementRect(region);
                    const verticalDistance = regionRect.top - anchorRect.bottom;
                    if (verticalDistance < -80 || verticalDistance > 900) return Number.POSITIVE_INFINITY;
                    const horizontalDistance = Math.abs(regionRect.left - anchorRect.left);
                    if (horizontalDistance > 1200) return Number.POSITIVE_INFINITY;
                    return verticalDistance + horizontalDistance * 0.05;
                };
                const markRegion = (region) => {
                    const inputs = Array.from(region.querySelectorAll('input[type="file"]'));
                    const input = inputs.find((item) => item.classList.contains('file-input-hidden'))
                        || inputs.find((item) => item.classList.contains('upload-input'))
                        || inputs.find((item) => {
                        const accept = String(item.getAttribute('accept') || '').toLowerCase();
                        return /image|jpg|jpeg|png|bmp/.test(accept) && !/video/.test(accept);
                    }) || inputs[0];
                    if (!input) return null;
                    region.setAttribute('data-aidrama-upload-field', fieldMarker);
                    input.setAttribute('data-aidrama-file-input', inputMarker);
                    const button = uploadButtonsIn(region)
                        .sort((a, b) => {
                            const aText = textOf(a);
                            const bText = textOf(b);
                            const aBonus = /选择文件|重新选择|上传文件|添加文件/.test(aText) ? -100 : 0;
                            const bBonus = /选择文件|重新选择|上传文件|添加文件/.test(bText) ? -100 : 0;
                            return aBonus - bBonus;
                        })[0];
                    if (button) button.setAttribute('data-aidrama-upload-button', buttonMarker);
                    return {
                        inputMarked: true,
                        inputMarker,
                        fieldMarker,
                        buttonMarked: Boolean(button),
                        buttonMarker: button ? buttonMarker : null,
                        inputAccept: input.getAttribute('accept') || '',
                        inputMultiple: Boolean(input.multiple),
                        fieldText: textOf(region).slice(0, 200)
                    };
                };
                const anchors = Array.from(document.querySelectorAll('body *'))
                    .filter(visible)
                    .filter(matchesLabel)
                    .sort((a, b) => textOf(a).length - textOf(b).length);
                for (const anchor of anchors) {
                    try { anchor.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (_) {}
                    const directRegion = anchor.closest('.weui-desktop-form__control-group');
                    if (directRegion && directRegion.querySelector('input[type="file"]')) {
                        const result = markRegion(directRegion);
                        if (result) return result;
                    }
                    const regions = [];
                    let container = anchor.parentElement;
                    for (let depth = 0; container && depth < 8; depth += 1, container = container.parentElement) {
                        regions.push(...uploadRegionsIn(container));
                    }
                    const uniqueRegions = regions
                        .filter((region, index, array) => array.indexOf(region) === index)
                        .map((region) => ({ region, score: relationScore(anchor, region) }))
                        .filter((candidate) => Number.isFinite(candidate.score))
                        .sort((a, b) => a.score - b.score);
                    for (const candidate of uniqueRegions) {
                        const result = markRegion(candidate.region);
                        if (result) return result;
                    }
                }
                return null;
            }
        """

    @staticmethod
    def _material_field_matcher_script(candidate_selector: str, mark_body: str, *, require_visible_candidate: bool = True) -> str:
        candidate_filter = ".filter(visible)" if require_visible_candidate else ""
        return f"""
            ({{ patterns, marker }}) => {{
                const regexps = patterns.map((pattern) => new RegExp(pattern));
                const normalized = (value) => String(value || '').replace(/\\s+/g, '');
                const visible = (el) => {{
                    if (!el || !(el instanceof HTMLElement)) return false;
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                }};
                const textOf = (el) => normalized(el.innerText || el.textContent);
                const matchesLabel = (el) => {{
                    const text = textOf(el);
                    return text && regexps.some((re) => re.test(text));
                }};
                const candidatesIn = (container) => Array.from(container.querySelectorAll({candidate_selector!r})){candidate_filter};
                const elementRect = (el) => {{
                    let current = el;
                    for (let depth = 0; current && depth < 6; depth += 1, current = current.parentElement) {{
                        const rect = current.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) return rect;
                    }}
                    return el.getBoundingClientRect();
                }};
                const preferredContainer = (label) => label.closest([
                    '.weui-desktop-form__control-group',
                    '.weui-desktop-form__control',
                    '.weui-desktop-form__item',
                    '.weui-desktop-form__frm-control',
                    '.ant-form-item',
                    '.semi-form-field',
                    '.t-form__item',
                    '.form-item',
                    '.form-row',
                    '.field-row'
                ].join(','));
                const scoreCandidate = (label, candidate) => {{
                    const labelRect = label.getBoundingClientRect();
                    const rect = elementRect(candidate);
                    const centerX = (rect.left + rect.right) / 2;
                    const centerY = (rect.top + rect.bottom) / 2;
                    const labelCenterY = (labelRect.top + labelRect.bottom) / 2;
                    const belowPenalty = centerY < labelRect.top ? 300 : 0;
                    const dx = Math.max(0, centerX - labelRect.left);
                    const dy = Math.abs(centerY - labelCenterY);
                    const text = textOf(candidate);
                    const textBonus = /选择文件|上传|添加|材料|\\+/.test(text) ? -100 : 0;
                    return dx * 0.2 + dy * 4 + belowPenalty + textBonus;
                }};
                const markBest = (label, candidates) => {{
                    const best = candidates
                        {candidate_filter}
                        .sort((a, b) => scoreCandidate(label, a) - scoreCandidate(label, b))[0];
                    if (!best) return false;
                    {mark_body}
                    return true;
                }};
                const labels = Array.from(document.querySelectorAll('body *'))
                    .filter(visible)
                    .filter(matchesLabel)
                    .sort((a, b) => textOf(a).length - textOf(b).length);
                for (const label of labels) {{
                    try {{ label.scrollIntoView({{ block: 'center', inline: 'nearest' }}); }} catch (_) {{}}
                    const preferred = preferredContainer(label);
                    const preferredCandidates = preferred ? candidatesIn(preferred) : [];
                    if (preferredCandidates.length && markBest(label, preferredCandidates)) return true;
                    let container = label;
                    for (let depth = 0; container && depth < 8; depth += 1, container = container.parentElement) {{
                        const candidates = candidatesIn(container);
                        if (candidates.length && markBest(label, candidates)) return true;
                    }}
                    const labelRect = label.getBoundingClientRect();
                    const followingCandidates = candidatesIn(document.body)
                        .filter((candidate) => Boolean(label.compareDocumentPosition(candidate) & Node.DOCUMENT_POSITION_FOLLOWING))
                        .filter((candidate) => {{
                            const rect = elementRect(candidate);
                            if (rect.width <= 0 || rect.height <= 0) return false;
                            const verticalDistance = rect.top - labelRect.top;
                            const horizontalDistance = Math.abs(rect.left - labelRect.left);
                            return verticalDistance >= -20 && verticalDistance <= 900 && horizontalDistance <= 1200;
                        }});
                    if (followingCandidates.length && markBest(label, followingCandidates)) return true;
                }}
                return false;
            }}
        """

    @staticmethod
    def _fill_text_field_near_text_script() -> str:
        return """
            ({ patterns, value }) => {
                const regexps = patterns.map((pattern) => new RegExp(pattern));
                const normalized = (text) => String(text || '').replace(/\\s+/g, '');
                const textOf = (element) => normalized(element.innerText || element.textContent);
                const visible = (element) => {
                    if (!element || !(element instanceof HTMLElement)) return false;
                    const rect = element.getBoundingClientRect();
                    const style = window.getComputedStyle(element);
                    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                };
                const matchesLabel = (element) => {
                    const text = textOf(element);
                    return text && regexps.some((regexp) => regexp.test(text));
                };
                const fieldContainers = [
                    '.weui-desktop-form__control-group',
                    '.weui-desktop-form__control',
                    '.weui-desktop-form__item',
                    '.weui-desktop-form__frm-control',
                    '.ant-form-item',
                    '.semi-form-field',
                    '.t-form__item',
                    '.form-item',
                    '.form-row',
                    '.field-row'
                ].join(',');
                const inputSelector = [
                    'textarea',
                    'input:not([type])',
                    'input[type="text"]',
                    '[contenteditable="true"]',
                    '[role="textbox"]'
                ].join(',');
                const candidatesIn = (container) => Array.from(container.querySelectorAll(inputSelector))
                    .filter((candidate) => {
                        if (!visible(candidate)) return false;
                        if (candidate.disabled || candidate.readOnly) return false;
                        const type = String(candidate.getAttribute('type') || '').toLowerCase();
                        return !['file', 'checkbox', 'radio', 'hidden', 'button', 'submit'].includes(type);
                    });
                const elementRect = (element) => {
                    let current = element;
                    for (let depth = 0; current && depth < 6; depth += 1, current = current.parentElement) {
                        const rect = current.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0) return rect;
                    }
                    return element.getBoundingClientRect();
                };
                const scoreCandidate = (label, candidate) => {
                    const labelRect = label.getBoundingClientRect();
                    const rect = elementRect(candidate);
                    const vertical = Math.abs(((rect.top + rect.bottom) / 2) - ((labelRect.top + labelRect.bottom) / 2));
                    const horizontal = Math.max(0, rect.left - labelRect.left);
                    const belowPenalty = rect.bottom < labelRect.top ? 300 : 0;
                    const tagBonus = candidate.tagName === 'TEXTAREA' ? -120 : 0;
                    const placeholder = normalized(candidate.getAttribute('placeholder'));
                    const placeholderBonus = /剧情概要|剧目简介|简介/.test(placeholder) ? -150 : 0;
                    return vertical * 4 + horizontal * 0.15 + belowPenalty + tagBonus + placeholderBonus;
                };
                const setValue = (candidate) => {
                    try { candidate.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (_) {}
                    candidate.focus();
                    if (candidate.isContentEditable || candidate.getAttribute('role') === 'textbox') {
                        candidate.textContent = value;
                    } else {
                        const proto = candidate instanceof HTMLTextAreaElement
                            ? HTMLTextAreaElement.prototype
                            : HTMLInputElement.prototype;
                        const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                        if (setter) setter.call(candidate, value);
                        else candidate.value = value;
                    }
                    candidate.dispatchEvent(new Event('input', { bubbles: true }));
                    candidate.dispatchEvent(new Event('change', { bubbles: true }));
                    candidate.blur();
                    return true;
                };
                const fillBest = (label, candidates) => {
                    const best = candidates.sort((a, b) => scoreCandidate(label, a) - scoreCandidate(label, b))[0];
                    if (!best) return null;
                    setValue(best);
                    return {
                        filled: (best.value || best.textContent || '') === value,
                        tagName: best.tagName,
                        placeholder: best.getAttribute('placeholder') || '',
                        value: best.value || best.textContent || '',
                    };
                };
                const labels = Array.from(document.querySelectorAll('body *'))
                    .filter(visible)
                    .filter(matchesLabel)
                    .sort((a, b) => textOf(a).length - textOf(b).length);
                for (const label of labels) {
                    try { label.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (_) {}
                    const direct = label.closest(fieldContainers);
                    const directCandidates = direct ? candidatesIn(direct) : [];
                    if (directCandidates.length) {
                        const result = fillBest(label, directCandidates);
                        if (result) return result;
                    }
                    let container = label.parentElement;
                    for (let depth = 0; container && depth < 8; depth += 1, container = container.parentElement) {
                        const candidates = candidatesIn(container);
                        if (candidates.length) {
                            const result = fillBest(label, candidates);
                            if (result) return result;
                        }
                    }
                    const labelRect = label.getBoundingClientRect();
                    const followingCandidates = candidatesIn(document.body).filter((candidate) => {
                        if (!(label.compareDocumentPosition(candidate) & Node.DOCUMENT_POSITION_FOLLOWING)) return false;
                        const rect = elementRect(candidate);
                        const verticalDistance = rect.top - labelRect.top;
                        const horizontalDistance = Math.abs(rect.left - labelRect.left);
                        return verticalDistance >= -20 && verticalDistance <= 700 && horizontalDistance <= 1200;
                    });
                    if (followingCandidates.length) {
                        const result = fillBest(label, followingCandidates);
                        if (result) return result;
                    }
                }
                return { filled: false };
            }
        """

    @staticmethod
    def _ensure_playlet_fields_by_dom_script() -> str:
        return """
            async ({ fields }) => {
                const normalized = (text) => String(text || '').replace(/\\s+/g, '');
                const visible = (element) => {
                    if (!element || !(element instanceof HTMLElement)) return false;
                    const rect = element.getBoundingClientRect();
                    const style = window.getComputedStyle(element);
                    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                };
                const inputSelector = [
                    'input.weui-desktop-form__input',
                    'input[type="text"]',
                    'input[type="number"]',
                    'input:not([type])',
                    'textarea.weui-desktop-form__textarea',
                    'textarea'
                ].join(',');
                const groupSelector = [
                    '.weui-desktop-form__control-group',
                    '.cost_form',
                    '.ant-form-item',
                    '.form-item',
                    '.form-row'
                ].join(',');
                const candidatesIn = (container, textareaOnly) => Array.from(container.querySelectorAll(inputSelector))
                    .filter(visible)
                    .filter((candidate) => {
                        if (candidate.disabled || candidate.readOnly) return false;
                        if (textareaOnly && candidate.tagName !== 'TEXTAREA') return false;
                        const type = String(candidate.getAttribute('type') || '').toLowerCase();
                        return !['file', 'checkbox', 'radio', 'hidden', 'button', 'submit'].includes(type);
                    });
                const groupTextParts = (group) => {
                    const labelText = Array.from(group.querySelectorAll([
                        'label.weui-desktop-form__label',
                        '.weui-desktop-form__label',
                        '.cost_title',
                        '[class*="label"]',
                        '[class*="Label"]'
                    ].join(','))).filter(visible).map((element) => element.textContent || '');
                    const placeholderText = candidatesIn(group, false).map((element) => element.getAttribute('placeholder') || '');
                    return [...labelText, ...placeholderText, group.getAttribute('data-test') || ''];
                };
                const elementScore = (group, field, index) => {
                    const wanted = [
                        ...(field.labels || []),
                        ...(field.placeholders || [])
                    ].map(normalized).filter(Boolean);
                    const parts = groupTextParts(group).map(normalized).filter(Boolean);
                    if (!parts.length) return null;
                    const exact = parts.some((part) => wanted.some((item) => part === item));
                    const fuzzy = parts.some((part) => wanted.some((item) => part.includes(item) || item.includes(part)));
                    if (!exact && !fuzzy) return null;
                    const rect = group.getBoundingClientRect();
                    const sizePenalty = Math.min(normalized(group.innerText || group.textContent).length, 2000);
                    return (exact ? 0 : 500) + sizePenalty + Math.max(0, rect.top) * 0.01 + index;
                };
                const setNativeValue = (element, nextValue) => {
                    const proto = element instanceof HTMLTextAreaElement
                        ? HTMLTextAreaElement.prototype
                        : HTMLInputElement.prototype;
                    const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                    if (setter) setter.call(element, nextValue);
                    else element.value = nextValue;
                    try {
                        element.dispatchEvent(new InputEvent('input', {
                            bubbles: true,
                            cancelable: true,
                            inputType: 'insertText',
                            data: nextValue,
                        }));
                    } catch (_) {
                        element.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                    element.dispatchEvent(new Event('input', { bubbles: true }));
                    element.dispatchEvent(new Event('change', { bubbles: true }));
                    element.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: 'Process' }));
                };
                const fillElement = async (element, value) => {
                    try { element.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (_) {}
                    element.focus();
                    if (typeof element.select === 'function') {
                        try { element.select(); } catch (_) {}
                    }
                    try { document.execCommand('insertText', false, value); } catch (_) {}
                    if (element.value !== value) {
                        setNativeValue(element, value);
                    } else {
                        element.dispatchEvent(new Event('input', { bubbles: true }));
                        element.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                    await new Promise((resolve) => window.setTimeout(resolve, 80));
                    if (element.value !== value) {
                        setNativeValue(element, value);
                    }
                    element.blur();
                    await new Promise((resolve) => window.setTimeout(resolve, 80));
                    return element.value || '';
                };
                const groups = Array.from(document.querySelectorAll(groupSelector)).filter(visible);
                const outcomes = [];
                for (const field of fields) {
                    const value = String(field.value ?? '');
                    if (!value) continue;
                    const ranked = groups
                        .map((group, index) => ({ group, score: elementScore(group, field, index) }))
                        .filter((item) => item.score !== null)
                        .sort((a, b) => a.score - b.score);
                    let actual = '';
                    let found = false;
                    for (const item of ranked) {
                        const candidates = candidatesIn(item.group, Boolean(field.textarea));
                        if (!candidates.length) continue;
                        actual = await fillElement(candidates[0], value);
                        found = true;
                        if (actual === value) break;
                    }
                    outcomes.push({
                        name: field.name,
                        expected: value,
                        actual,
                        found,
                        ok: found && actual === value,
                    });
                }
                return {
                    outcomes,
                    missing: outcomes.filter((item) => !item.ok).map((item) => item.name),
                };
            }
        """

    @staticmethod
    def _fill_weui_input_by_label_script() -> str:
        return """
            async ({ labels, value }) => {
                const normalized = (text) => String(text || '').replace(/\\s+/g, '');
                const wanted = labels.map(normalized).filter(Boolean);
                const visible = (element) => {
                    if (!element || !(element instanceof HTMLElement)) return false;
                    const rect = element.getBoundingClientRect();
                    const style = window.getComputedStyle(element);
                    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                };
                const matches = (text) => {
                    const candidate = normalized(text);
                    if (!candidate) return false;
                    return wanted.some((item) => candidate === item || candidate.includes(item) || item.includes(candidate));
                };
                const candidateSelector = [
                    'input:not([type])',
                    'input[type="text"]',
                    'input[type="number"]',
                    'textarea.weui-desktop-form__textarea',
                    'textarea'
                ].join(',');
                const fieldCandidates = (group) => Array.from(group.querySelectorAll(candidateSelector))
                    .filter(visible)
                    .filter((candidate) => {
                        if (candidate.disabled || candidate.readOnly) return false;
                        const type = String(candidate.getAttribute('type') || '').toLowerCase();
                        return !['file', 'checkbox', 'radio', 'hidden', 'button', 'submit'].includes(type);
                    });
                const groupTexts = (group) => [
                    ...Array.from(group.querySelectorAll([
                        'label.weui-desktop-form__label',
                        '.weui-desktop-form__label',
                        '.cost_title',
                        '[class*="label"]',
                        '[class*="Label"]'
                    ].join(','))).filter(visible).map((element) => element.textContent || ''),
                    ...fieldCandidates(group).map((element) => element.getAttribute('placeholder') || '')
                ];
                const setNativeValue = (element, nextValue) => {
                    const proto = element instanceof HTMLTextAreaElement
                        ? HTMLTextAreaElement.prototype
                        : HTMLInputElement.prototype;
                    const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                    if (setter) setter.call(element, nextValue);
                    else element.value = nextValue;
                    try {
                        element.dispatchEvent(new InputEvent('input', {
                            bubbles: true,
                            cancelable: true,
                            inputType: 'insertText',
                            data: nextValue,
                        }));
                    } catch (_) {
                        element.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                    element.dispatchEvent(new Event('change', { bubbles: true }));
                    element.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: 'Process' }));
                };
                const fillCandidate = async (candidate) => {
                    try { candidate.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (_) {}
                    candidate.focus();
                    setNativeValue(candidate, value);
                    await new Promise((resolve) => window.setTimeout(resolve, 50));
                    setNativeValue(candidate, value);
                    candidate.blur();
                    await new Promise((resolve) => window.setTimeout(resolve, 50));
                    return {
                        filled: candidate.value === value,
                        value: candidate.value,
                        placeholder: candidate.getAttribute('placeholder') || '',
                    };
                };
                const groups = Array.from(document.querySelectorAll([
                    '.weui-desktop-form__control-group',
                    '.ant-form-item',
                    '.form-item',
                    '.form-row'
                ].join(','))).filter(visible);
                const matchedGroups = groups
                    .map((group) => {
                        const texts = groupTexts(group);
                        const exact = texts.some((text) => wanted.includes(normalized(text)));
                        const fuzzy = texts.some(matches);
                        const hasPlaceholder = fieldCandidates(group).some((field) => matches(field.getAttribute('placeholder') || ''));
                        const textLength = normalized(texts.join('')).length;
                        const score = (exact ? 0 : 1000) + (hasPlaceholder ? -100 : 0) + textLength;
                        return { group, matched: exact || fuzzy || hasPlaceholder, score };
                    })
                    .filter((item) => item.matched)
                    .sort((a, b) => a.score - b.score);
                for (const item of matchedGroups) {
                    const candidates = fieldCandidates(item.group);
                    if (!candidates.length) continue;
                    const result = await fillCandidate(candidates[0]);
                    if (result.filled) return result;
                }
                return { filled: false, reason: 'field-not-found' };
            }
        """

    @staticmethod
    def _fill_weui_textarea_by_label_script() -> str:
        return """
            async ({ label, value }) => {
                const normalized = (text) => String(text || '').replace(/\\s+/g, '');
                const visible = (element) => {
                    if (!element || !(element instanceof HTMLElement)) return false;
                    const rect = element.getBoundingClientRect();
                    const style = window.getComputedStyle(element);
                    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                };
                const setNativeValue = (element, nextValue) => {
                    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
                    if (setter) setter.call(element, nextValue);
                    else element.value = nextValue;
                    try {
                        element.dispatchEvent(new InputEvent('input', {
                            bubbles: true,
                            cancelable: true,
                            inputType: 'insertText',
                            data: nextValue,
                        }));
                    } catch (_) {
                        element.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                    element.dispatchEvent(new Event('input', { bubbles: true }));
                    element.dispatchEvent(new Event('change', { bubbles: true }));
                    element.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: 'Process' }));
                };
                const groups = Array.from(document.querySelectorAll('.weui-desktop-form__control-group'));
                for (const group of groups) {
                    const formLabel = group.querySelector('label.weui-desktop-form__label');
                    if (!formLabel || normalized(formLabel.textContent) !== normalized(label)) continue;
                    const textarea = group.querySelector('textarea.weui-desktop-form__textarea, textarea');
                    if (!textarea || !visible(textarea) || textarea.disabled || textarea.readOnly) {
                        return { filled: false, reason: 'textarea-missing-or-disabled' };
                    }
                    try { textarea.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (_) {}
                    textarea.focus();
                    setNativeValue(textarea, value);
                    await new Promise((resolve) => window.setTimeout(resolve, 50));
                    setNativeValue(textarea, value);
                    textarea.blur();
                    await new Promise((resolve) => window.setTimeout(resolve, 50));
                    return {
                        filled: textarea.value === value,
                        label: normalized(formLabel.textContent),
                        placeholder: textarea.getAttribute('placeholder') || '',
                        value: textarea.value,
                        valueLength: String(value || '').length,
                    };
                }
                return { filled: false, reason: 'label-not-found' };
            }
        """

    @classmethod
    def _reveal_material_upload_script(cls) -> str:
        selector = ",".join(
            [
                "button",
                "[role='button']",
                "label",
                ".weui-desktop-upload",
                ".weui-desktop-upload__btn",
                ".weui-desktop-upload__input-box",
                ".upload",
                ".Upload",
                "[class*='upload']",
                "[class*='Upload']",
            ]
        )
        return cls._material_field_matcher_script(
            selector,
            """
                    best.setAttribute('data-aidrama-upload-button', marker);
                    best.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
                    best.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true, view: window }));
                    best.click();
            """,
        )

    @classmethod
    def _mark_file_input_script(cls) -> str:
        return cls._material_field_matcher_script(
            "input[type='file']",
            "best.setAttribute('data-aidrama-file-input', marker);",
            require_visible_candidate=False,
        )

    def _set_file_chooser_files(self, page, file_chooser, paths: str | list[str]) -> None:
        try:
            file_chooser.set_files(paths)
        except Exception as exception:  # noqa: BLE001
            if not self._is_file_transfer_limit_error(exception):
                raise
            self._set_file_input_files_with_cdp(page, file_chooser.element, paths)

    def _set_locator_files(self, page, file_input, paths: str | list[str]) -> None:
        try:
            file_input.set_input_files(paths)
        except Exception as exception:  # noqa: BLE001
            if not self._is_file_transfer_limit_error(exception):
                raise
            self._set_file_input_files_with_cdp(page, file_input, paths)

    @staticmethod
    def _is_file_transfer_limit_error(exception: Exception) -> bool:
        return "Cannot transfer files larger than 50Mb" in str(exception)

    @staticmethod
    def _set_file_input_files_with_cdp(page, file_input, paths: str | list[str]) -> None:
        marker = f"aidramaFileInput{time.time_ns()}"
        file_input.evaluate("(element, marker) => element.setAttribute('data-aidrama-file-input', marker)", marker)
        WeChatVideoPublisher._set_marked_file_input_files_with_cdp(page, marker, paths)

    @staticmethod
    def _set_marked_file_input_files_with_cdp(page, marker: str, paths: str | list[str]) -> None:
        session = page.context.new_cdp_session(page)
        document = session.send("DOM.getDocument", {"pierce": True})
        root_node_id = document["root"]["nodeId"]
        node = session.send(
            "DOM.querySelector",
            {"nodeId": root_node_id, "selector": f'input[type="file"][data-aidrama-file-input="{marker}"]'},
        )
        node_id = node.get("nodeId") or WeChatVideoPublisher._find_marked_file_input_node(session, marker)
        if not node_id:
            raise RuntimeError("未能定位视频号文件选择控件，请重新打开发布页面后重试")
        path_list = [str(Path(path).resolve()) for path in paths] if isinstance(paths, list) else [str(Path(paths).resolve())]
        session.send("DOM.setFileInputFiles", {"nodeId": node_id, "files": path_list})

    @staticmethod
    def _dispatch_marked_file_input_events(page, marker: str) -> None:
        evaluate = getattr(page, "evaluate", None)
        if not callable(evaluate):
            return
        try:
            evaluate(
                """
                (marker) => {
                    const input = document.querySelector(`input[type="file"][data-aidrama-file-input="${marker}"]`);
                    if (!input) return false;
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                }
                """,
                marker,
            )
        except Exception:
            pass

    @staticmethod
    def _find_marked_file_input_node(session, marker: str) -> int | None:
        try:
            document = session.send("DOM.getFlattenedDocument", {"depth": -1, "pierce": True})
        except Exception:  # noqa: BLE001
            return None
        for node in document.get("nodes", []) or []:
            attributes = node.get("attributes", []) or []
            pairs = zip(attributes[0::2], attributes[1::2])
            if any(name == "data-aidrama-file-input" and value == marker for name, value in pairs):
                return node.get("nodeId")
        return None

    @staticmethod
    def _click_next_if_available(page, timeout_error) -> None:
        try:
            page.get_by_text(re.compile("下一步|继续")).first.click(timeout=5000)
            page.wait_for_timeout(1000)
        except timeout_error:
            pass

def remote_debugging_port_for_profile(profile_dir: Path) -> int:
    return 20000 + zlib.crc32(str(profile_dir).encode("utf-8")) % 10000
