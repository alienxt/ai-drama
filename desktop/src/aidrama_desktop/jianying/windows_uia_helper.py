from __future__ import annotations

import argparse
import importlib
import sys
import time
from pathlib import Path
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


def _find_jianying_window(uia: Any, progress: ProgressLog) -> tuple[Any, str]:
    state = {"status": "unknown"}

    def compare(control: Any, _depth: int) -> bool:
        if control.Name != "剪映专业版":
            return False
        class_name = str(control.ClassName or "").lower()
        if "homepage" in class_name:
            state["status"] = "home"
            return True
        if "mainwindow" in class_name:
            state["status"] = "edit"
            return True
        return False

    app = uia.WindowControl(searchDepth=1, Compare=compare)
    if not app.Exists(0):
        raise RuntimeError("剪映窗口未找到")
    app.SetActive()
    app.SetTopmost()
    progress.write(
        f"stage=python-uia-window-ready status={state['status']} "
        f"name={app.Name} className={app.ClassName}"
    )
    return app, state["status"]


def _switch_to_home(uia: Any, app: Any, status: str, progress: ProgressLog) -> Any:
    if status == "home":
        return app
    if status != "edit":
        raise RuntimeError(f"仅支持从剪映编辑页返回首页，当前状态: {status}")

    close_button = app.GroupControl(searchDepth=1, ClassName="TitleBarButton", foundIndex=3)
    if not close_button.Exists(0):
        raise RuntimeError("未找到剪映编辑页第三个 TitleBarButton")
    progress.write("stage=python-uia-return-home buttonIndex=3")
    close_button.Click(simulateMove=False)
    time.sleep(2)
    app, status = _find_jianying_window(uia, progress)
    if status != "home":
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
    app, status = _find_jianying_window(uia, progress)
    try:
        app = _switch_to_home(uia, app, status, progress)
        _open_named_draft(uia, app, draft_name, progress)

        time.sleep(10)
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            try:
                app, status = _find_jianying_window(uia, progress)
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
