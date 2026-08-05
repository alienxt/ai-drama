from __future__ import annotations

import argparse
import importlib
import sys
import time
from pathlib import Path, PureWindowsPath
from typing import Any


class ProgressLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, message: str) -> None:
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(f"{message}\n")


def _load_uiautomation() -> Any:
    return importlib.import_module("uiautomation")


def _basename_lower(path: str) -> str:
    value = str(path or "").strip().strip('"')
    if not value:
        return ""
    return PureWindowsPath(value).name.lower()


def _normalize_windows_path(path: str) -> str:
    value = str(path or "").strip().strip('"')
    if not value:
        return ""
    return str(PureWindowsPath(value)).replace("/", "\\").lower()


def _safe_control_text(control: Any, attr: str) -> str:
    try:
        return str(getattr(control, attr) or "")
    except Exception:
        return ""


def _safe_process_id(control: Any) -> int:
    try:
        return int(getattr(control, "ProcessId") or 0)
    except Exception:
        return 0


def _process_image_path(pid: int) -> str:
    if sys.platform != "win32" or not pid:
        return ""
    try:
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        kernel32 = ctypes.windll.kernel32
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD),
        ]
        kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.OpenProcess(process_query_limited_information, False, int(pid))
        if not handle:
            return ""
        try:
            size = wintypes.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            ok = kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size))
            return buffer.value if ok else ""
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return ""


def _window_status(name: str, class_name: str, draft_name: str) -> str:
    lowered_class = class_name.lower()
    lowered_name = name.lower()
    lowered_draft = draft_name.lower()
    if "homepage" in lowered_class:
        return "home"
    if "mainwindow" in lowered_class:
        return "edit"
    if lowered_draft and lowered_draft in lowered_name:
        return "edit"
    return "unknown"


def _describe_window_candidate(control: Any, process_image: str = "") -> str:
    name = _safe_control_text(control, "Name").replace("\n", " ").strip()
    class_name = _safe_control_text(control, "ClassName").replace("\n", " ").strip()
    pid = _safe_process_id(control)
    image_name = _basename_lower(process_image)
    return (
        f"name={name or '-'} className={class_name or '-'} "
        f"pid={pid or '-'} process={image_name or '-'}"
    )


def _control_exists(control: Any, seconds: float) -> bool:
    try:
        return bool(control.Exists(seconds))
    except TypeError:
        return bool(control.Exists(int(seconds)))


def _find_jianying_window(
    uia: Any,
    progress: ProgressLog,
    *,
    app_path: str = "",
    draft_name: str = "",
    timeout_seconds: float = 20,
) -> tuple[Any, str]:
    state = {"status": "unknown", "match": "none"}
    app_basename = _basename_lower(app_path)
    app_path_normalized = _normalize_windows_path(app_path)
    process_cache: dict[int, str] = {}
    last_observed: list[str] = []

    def legacy_compare(control: Any, _depth: int) -> bool:
        name = _safe_control_text(control, "Name")
        class_name = _safe_control_text(control, "ClassName")
        if name != "剪映专业版":
            return False
        status = _window_status(name, class_name, draft_name)
        if status not in {"home", "edit"}:
            return False
        state["status"] = status
        state["match"] = "legacy"
        return True

    def relaxed_compare(control: Any, _depth: int) -> bool:
        name = _safe_control_text(control, "Name")
        class_name = _safe_control_text(control, "ClassName")
        pid = _safe_process_id(control)
        process_image = ""
        if pid:
            process_image = process_cache.setdefault(pid, _process_image_path(pid))

        observed_text = _describe_window_candidate(control, process_image)
        if observed_text and len(last_observed) < 12 and observed_text not in last_observed:
            last_observed.append(observed_text)

        combined = f"{name} {class_name} {process_image}".lower()
        process_path_normalized = _normalize_windows_path(process_image)
        process_basename = _basename_lower(process_image)
        app_matches = bool(
            (app_path_normalized and process_path_normalized == app_path_normalized)
            or (app_basename and process_basename == app_basename)
        )
        token_matches = any(
            token in combined
            for token in ("剪映", "jianying", "jianyingpro", "capcut", "videofusion")
        )
        draft_matches = bool(draft_name and draft_name.lower() in name.lower())

        if not (app_matches or token_matches or draft_matches):
            return False

        state["status"] = _window_status(name, class_name, draft_name)
        state["match"] = "relaxed"
        return True

    deadline = time.monotonic() + max(0.5, timeout_seconds)
    retry_logged = False
    while True:
        last_observed.clear()
        app = uia.WindowControl(searchDepth=1, Compare=legacy_compare)
        if _control_exists(app, 0):
            break
        app = uia.WindowControl(searchDepth=1, Compare=relaxed_compare)
        if _control_exists(app, 0):
            break
        if time.monotonic() >= deadline:
            observed_text = " | ".join(last_observed) if last_observed else "none"
            raise RuntimeError(f"剪映窗口未找到；已观察窗口: {observed_text}")
        if not retry_logged:
            progress.write("stage=python-uia-window-search-waiting")
            retry_logged = True
        time.sleep(0.5)

    app.SetActive()
    app.SetTopmost()
    progress.write(
        f"stage=python-uia-window-ready status={state['status']} "
        f"match={state['match']} name={app.Name} className={app.ClassName}"
    )
    return app, state["status"]


def _switch_to_home(
    uia: Any,
    app: Any,
    status: str,
    progress: ProgressLog,
    *,
    app_path: str = "",
    draft_name: str = "",
) -> Any:
    if status == "home":
        return app
    if status == "unknown":
        progress.write("stage=python-uia-assume-home status=unknown")
        return app
    if status != "edit":
        raise RuntimeError(f"仅支持从剪映编辑页返回首页，当前状态: {status}")

    close_button = app.GroupControl(searchDepth=1, ClassName="TitleBarButton", foundIndex=3)
    if not close_button.Exists(0):
        raise RuntimeError("未找到剪映编辑页第三个 TitleBarButton")
    progress.write("stage=python-uia-return-home buttonIndex=3")
    close_button.Click(simulateMove=False)
    time.sleep(2)
    app, status = _find_jianying_window(
        uia,
        progress,
        app_path=app_path,
        draft_name=draft_name,
        timeout_seconds=15,
    )
    if status != "home":
        if status == "unknown":
            progress.write("stage=python-uia-assume-home status=unknown")
            return app
        raise RuntimeError("剪映未返回 HomePage")
    return app


def _open_named_draft(uia: Any, app: Any, draft_name: str, progress: ProgressLog) -> None:
    target_description = f"HomePageDraftTitle:{draft_name}"
    observed: set[str] = set()

    def compare(control: Any, depth: int) -> bool:
        if depth != 2:
            return False
        try:
            full_description = str(control.GetPropertyValue(30159) or "")
        except Exception:
            return False
        if full_description.startswith("HomePageDraftTitle:") and full_description not in observed:
            observed.add(full_description)
            progress.write(
                f"stage=python-uia-draft-title-observed fullDescription={full_description}"
            )
        return full_description.lower() == target_description.lower()

    progress.write(f"stage=python-uia-draft-search target={target_description}")
    title = app.TextControl(searchDepth=2, Compare=compare)
    if not title.Exists(20, 0.5):
        observed_text = " | ".join(sorted(observed)) if observed else "none"
        raise RuntimeError(
            f"未找到剪映草稿 FullDescription '{target_description}'。"
            f"实际读取到的草稿: {observed_text}"
        )

    draft_card = title.GetParentControl()
    if draft_card is None:
        raise RuntimeError("精确匹配的草稿标题没有父级草稿卡片")
    bounds = draft_card.BoundingRectangle
    progress.write(
        "stage=python-uia-draft-card-click "
        f"left={bounds.left} top={bounds.top} right={bounds.right} bottom={bounds.bottom}"
    )
    draft_card.Click(simulateMove=False)


def open_jianying_draft(app_path: str, draft_name: str, progress: ProgressLog) -> None:
    if sys.platform != "win32":
        raise RuntimeError("剪映 UI Automation 辅助模式仅支持 Windows")
    if not draft_name:
        raise RuntimeError("草稿名称不能为空")

    uia = _load_uiautomation()
    progress.write(f"stage=python-uia-start appPath={app_path} target={draft_name}")
    app, status = _find_jianying_window(
        uia,
        progress,
        app_path=app_path,
        draft_name=draft_name,
        timeout_seconds=45,
    )
    try:
        app = _switch_to_home(
            uia,
            app,
            status,
            progress,
            app_path=app_path,
            draft_name=draft_name,
        )
        _open_named_draft(uia, app, draft_name, progress)

        time.sleep(10)
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            try:
                app, status = _find_jianying_window(
                    uia,
                    progress,
                    app_path=app_path,
                    draft_name=draft_name,
                    timeout_seconds=2,
                )
                if status == "edit":
                    progress.write("stage=python-uia-main-window-ready")
                    return
            except Exception:
                pass
            time.sleep(1)
        raise RuntimeError(f"点击精确草稿卡片后，剪映未进入 MainWindow: {draft_name}")
    finally:
        try:
            app.SetTopmost(False)
        except Exception:
            pass


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--app-path", default="")
    parser.add_argument("--draft-name", required=True)
    parser.add_argument("--progress-file", type=Path, required=True)
    args = parser.parse_args(argv)
    progress = ProgressLog(args.progress_file)
    try:
        open_jianying_draft(args.app_path, args.draft_name, progress)
    except Exception as exception:
        progress.write(f"stage=python-uia-error message={exception}")
        return 1
    return 0
