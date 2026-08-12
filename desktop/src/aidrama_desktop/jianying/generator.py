from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aidrama_desktop.config.settings import ffprobe_path_for_ffmpeg
from aidrama_desktop.subprocess_utils import hidden_subprocess_kwargs


DEFAULT_CLIP_COUNT = 24
DEFAULT_TIMEOUT_SECONDS = 8 * 60
TOOL_ENV_KEY = "AIDRAMA_JIANYING_TOOL_PATH"
NODE_ENV_KEY = "AIDRAMA_NODE_PATH"


class JianyingGenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class JianyingProjectGenerationResult:
    screenshot_path: Path
    draft_dir: Path | None = None
    result_path: Path | None = None
    strategy_id: str | None = None
    strategy_label: str | None = None
    warnings: tuple[str, ...] = ()


@dataclass
class JianyingProjectGenerator:
    ffmpeg_path: str = "ffmpeg"
    node_path: str | None = None
    tool_path: Path | None = None
    draft_root: Path | None = None
    jianying_app: Path | None = None
    clip_count: int = DEFAULT_CLIP_COUNT
    close_existing: bool = True
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS

    def generate_project_screenshot(
        self,
        *,
        video: Path,
        draft_name: str,
        output_dir: Path,
        screenshot_path: Path,
        srt: Path | None = None,
        bgm_files: list[Path] | None = None,
        strategy: str | None = None,
    ) -> JianyingProjectGenerationResult:
        video = Path(video)
        if not video.exists() or not video.is_file():
            raise JianyingGenerationError(f"剪映工程视频不存在：{video}")

        tool_path = self._resolve_tool_path()
        node_path = self._resolve_node_path()
        output_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)

        command = [
            node_path,
            str(tool_path),
            "--video",
            str(video),
            "--name",
            draft_name,
            "--output-dir",
            str(output_dir),
            "--clip-count",
            str(max(1, int(self.clip_count or DEFAULT_CLIP_COUNT))),
            "--overwrite",
            "--open",
            "--open-draft",
            "--capture",
            "--screenshot",
            str(screenshot_path),
            "--ffmpeg",
            self.ffmpeg_path,
            "--ffprobe",
            ffprobe_path_for_ffmpeg(self.ffmpeg_path),
        ]
        if self.close_existing:
            command.append("--close-existing")
        if sys.platform in {"darwin", "win32"}:
            command.append("--close-after-capture")
        if srt and srt.exists():
            command.extend(["--srt", str(srt)])
        if strategy:
            command.extend(["--strategy", str(strategy)])
        for bgm in bgm_files or []:
            if bgm.exists():
                command.extend(["--bgm", str(bgm)])
        if self.draft_root:
            command.extend(["--draft-root", str(self.draft_root)])
        if self.jianying_app:
            command.extend(["--jianying-app", str(self.jianying_app)])
        helper_command = _windows_uia_helper_command()
        if helper_command:
            command.extend(
                ["--windows-uia-helper-command", json.dumps(helper_command, ensure_ascii=False)]
            )

        try:
            completed = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                **hidden_subprocess_kwargs(),
            )
        except FileNotFoundError as exception:
            raise JianyingGenerationError(f"找不到剪映工程生成依赖：{command[0]}") from exception
        except subprocess.TimeoutExpired as exception:
            raise JianyingGenerationError("剪映工程截图生成超时，请确认剪映已安装并允许辅助功能权限。") from exception
        except subprocess.CalledProcessError as exception:
            detail = (exception.stderr or exception.stdout or "").strip()
            raise JianyingGenerationError(
                f"剪映工程截图生成失败：{detail or exception.returncode}"
            ) from exception

        fallback_result_path = output_dir / "jianying_project_result.json"
        payload = self._parse_tool_output(completed.stdout, fallback_result_path=fallback_result_path)
        warnings = tuple(str(item) for item in payload.get("warnings") or [])
        if warnings:
            raise JianyingGenerationError("剪映工程截图生成失败：" + "；".join(warnings))
        screenshot = Path(str(payload.get("screenshot_path") or screenshot_path))
        if not screenshot.exists() or not screenshot.is_file() or screenshot.stat().st_size <= 0:
            raise JianyingGenerationError(f"剪映工程截图未生成：{screenshot}")
        return JianyingProjectGenerationResult(
            screenshot_path=screenshot,
            draft_dir=Path(str(payload["draft_dir"])) if payload.get("draft_dir") else None,
            result_path=Path(str(payload["result_path"])) if payload.get("result_path") else None,
            strategy_id=str(payload.get("strategy_id") or "") or None,
            strategy_label=str(payload.get("strategy_label") or "") or None,
            warnings=warnings,
        )

    def _resolve_node_path(self) -> str:
        explicit = self.node_path or os.environ.get(NODE_ENV_KEY)
        candidates = [explicit, shutil.which("node"), "node"]
        for candidate in candidates:
            if not candidate:
                continue
            if Path(candidate).is_file():
                return str(Path(candidate))
            resolved = shutil.which(str(candidate))
            if resolved:
                return resolved
        raise JianyingGenerationError("找不到 Node.js，无法运行剪映工程生成工具。")

    def _resolve_tool_path(self) -> Path:
        candidates = [
            self.tool_path,
            Path(os.environ[TOOL_ENV_KEY]) if os.environ.get(TOOL_ENV_KEY) else None,
            *_packaged_tool_candidates(),
            *_source_tree_tool_candidates(),
        ]
        for candidate in candidates:
            if candidate and candidate.exists() and candidate.is_file():
                return candidate
        raise JianyingGenerationError(
            "找不到剪映工程生成脚本，请确认 scripts/jianying/create-jianying-project.js 已随客户端发布。"
        )

    @staticmethod
    def _parse_tool_output(stdout: str, *, fallback_result_path: Path | None = None) -> dict[str, Any]:
        text = str(stdout or "").strip()
        if not text:
            if fallback_result_path and fallback_result_path.exists():
                try:
                    return json.loads(fallback_result_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    pass
            raise JianyingGenerationError("剪映工程生成工具没有返回结果。")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    pass
            if fallback_result_path and fallback_result_path.exists():
                try:
                    return json.loads(fallback_result_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    pass
            raise JianyingGenerationError(f"无法解析剪映工程生成结果：{text[-500:]}")


def _packaged_tool_candidates() -> list[Path]:
    root = getattr(sys, "_MEIPASS", None)
    if not root:
        return []
    return [Path(root) / "aidrama_desktop" / "tools" / "jianying" / "create-jianying-project.js"]


def _source_tree_tool_candidates() -> list[Path]:
    current = Path(__file__).resolve()
    candidates: list[Path] = []
    for parent in current.parents:
        candidates.append(parent / "scripts" / "jianying" / "create-jianying-project.js")
        candidates.append(parent.parent / "scripts" / "jianying" / "create-jianying-project.js")
    return candidates


def _windows_uia_helper_command() -> list[str] | None:
    if sys.platform != "win32":
        return None
    if getattr(sys, "frozen", False):
        return [sys.executable, "--jianying-uia-helper"]
    return [sys.executable, "-m", "aidrama_desktop.gui.app", "--jianying-uia-helper"]
