from __future__ import annotations

import re
import time
import zlib
from pathlib import Path
from typing import Any

from aidrama_desktop.browser.chrome import ChromeController
from aidrama_desktop.platforms.base import PlatformPublisher


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
        process = self.chrome.open_profile(profile_dir, target_url, remote_debugging_port=port)
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
        publish_summary = str(metadata.get("summary") or summary or "")
        self._enter_playlet_plan(page, timeout_error)
        create_button = page.get_by_text(re.compile("创建剧集|新建剧集|新增剧集|上传剧集|添加剧集")).first
        try:
            create_button.click(timeout=8000)
            page.wait_for_timeout(1000)
        except timeout_error:
            pass

        self._fill_first(
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
        )
        if publish_summary:
            self._fill_first(
                page,
                [
                    "剧目简介",
                    "简介",
                    "剧情简介",
                    "描述",
                    "请介绍相关剧情概要",
                    "请输入简介",
                    "请输入剧情简介",
                ],
                publish_summary,
            )

        episode_count = metadata.get("episodeCount") or len(metadata.get("episodes", []) or media_files)
        if episode_count:
            self._fill_first(
                page,
                [
                    "总集数",
                    "剧集总数",
                    "总剧集数量",
                    "请填写待提审剧目的总剧集数量",
                    "请输入总集数",
                ],
                str(episode_count),
            )

        self._set_monetization_type(page, str(metadata.get("monetizationLabel") or "IAA广告变现"), timeout_error)
        free_episode_count = metadata.get("freeEpisodeCount")
        if free_episode_count is not None:
            self._fill_first(
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
            )

        self._set_default_playlet_options(page, timeout_error)

        cover_file = metadata.get("coverFile")
        if cover_file:
            self._set_file_input(page, Path(cover_file), re.compile("剧目海报|海报|封面|上传封面|添加封面|选择文件"), timeout_error)

        self._click_next_if_available(page, timeout_error)

        episode_files = [
            Path(episode.get("file"))
            for episode in metadata.get("episodes", [])
            if episode.get("file")
        ] or media_files
        self._set_file_input(page, episode_files, re.compile("上传视频|上传剧集|添加视频|添加剧集|选择文件"), timeout_error)
        self._click_next_if_available(page, timeout_error)

        try:
            page.get_by_text(re.compile("保存|提交审核|发布|上架")).first.click(timeout=15000)
        except timeout_error as exception:
            raise RuntimeError("短剧文件已选择，但未找到剧集保存/提交按钮，请检查视频号剧集管理页面") from exception

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

    def _fill_first(self, page, labels: list[str], value: str) -> None:
        for label in labels:
            for query in (label, re.compile(re.escape(label))):
                locator = page.get_by_placeholder(query).first
                if locator.count() == 0:
                    locator = page.get_by_label(query).first
                if locator.count() > 0:
                    locator.fill(value)
                    return

    def _set_default_playlet_options(self, page, timeout_error) -> None:
        self._click_text_option(page, [re.compile("^漫剧$")], timeout_error)
        self._set_ai_content_statement(page, timeout_error)
        self._set_submit_identity(page, timeout_error)
        self._click_text_option(page, [re.compile("^其他微短剧$")], timeout_error)

    def _set_ai_content_statement(self, page, timeout_error) -> None:
        label_pattern = re.compile("AI内容声明|AI\\s*内容声明|AI生成|AI\\s*生成")
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
                    return /checked|active|selected|open|on/.test(className);
                };
                const controlsIn = (container) => Array.from(container.querySelectorAll([
                    'input[type="checkbox"]',
                    '[role="switch"]',
                    'button[aria-checked]',
                    '[aria-checked]',
                    '[class*="switch"]',
                    '[class*="Switch"]'
                ].join(','))).filter(visible);
                const labels = Array.from(document.querySelectorAll('body *'))
                    .filter(visible)
                    .filter((el) => re.test(normalized(el.innerText || el.textContent)));
                for (const label of labels) {
                    let container = label;
                    for (let depth = 0; container && depth < 6; depth += 1, container = container.parentElement) {
                        const controls = controlsIn(container);
                        if (!controls.length) continue;
                        const labelRect = label.getBoundingClientRect();
                        const control = controls
                            .map((item) => {
                                const rect = item.getBoundingClientRect();
                                const dx = Math.max(0, rect.left - labelRect.right);
                                const dy = Math.abs((rect.top + rect.bottom) / 2 - (labelRect.top + labelRect.bottom) / 2);
                                return { item, score: dx + dy * 2 };
                            })
                            .sort((a, b) => a.score - b.score)[0].item;
                        if (!isOn(control)) control.click();
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
