from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from aidrama_desktop.config.settings import COMMON_WHISPER_PATHS as SETTINGS_COMMON_WHISPER_PATHS
from aidrama_desktop.config.settings import resolve_whisper_path
from aidrama_desktop.subprocess_utils import hidden_subprocess_kwargs


WHISPER_PATH_ENV_KEY = "AIDRAMA_WHISPER_PATH"
WHISPER_MODEL_ENV_KEY = "AIDRAMA_WHISPER_MODEL"
WHISPER_LANGUAGE_ENV_KEY = "AIDRAMA_WHISPER_LANGUAGE"
WHISPER_TIMEOUT_ENV_KEY = "AIDRAMA_WHISPER_TIMEOUT_SECONDS"
WHISPER_INITIAL_PROMPT_ENV_KEY = "AIDRAMA_WHISPER_INITIAL_PROMPT"
DEFAULT_WHISPER_MODEL = "small"
DEFAULT_WHISPER_LANGUAGE = "zh"
DEFAULT_WHISPER_TIMEOUT_SECONDS = 30 * 60
DEFAULT_WHISPER_INITIAL_PROMPT = (
    "以下是普通话短剧对白，请使用简体中文和中文标点输出。"
)
COMMON_WHISPER_PATHS = SETTINGS_COMMON_WHISPER_PATHS
class WhisperSrtGenerationError(RuntimeError):
    pass


@dataclass(frozen=True)
class WhisperSrtGenerationResult:
    srt_path: Path
    created: bool
    provider: str = "openaiWhisper"


@dataclass
class WhisperSrtGenerator:
    command_path: str | None = None
    model: str | None = None
    language: str | None = None
    initial_prompt: str | None = None
    timeout_seconds: int | None = None
    ffmpeg_path: str | None = None

    def generate_srt(self, video: Path, target: Path) -> WhisperSrtGenerationResult:
        video = Path(video)
        target = Path(target)
        if not video.exists() or not video.is_file():
            raise WhisperSrtGenerationError(f"字幕源视频不存在：{video}")
        if target.exists() and target.is_file() and target.stat().st_size > 0:
            return WhisperSrtGenerationResult(srt_path=target, created=False)

        command_path = self._resolve_command_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        generated = target.parent / f"{video.stem}.srt"
        if generated.exists() and generated != target:
            generated.unlink()

        command = [
            command_path,
            str(video),
            "--model",
            self._model(),
            "--language",
            self._language(),
            "--output_format",
            "srt",
            "--output_dir",
            str(target.parent),
            "--verbose",
            "False",
            "--fp16",
            "False",
        ]
        initial_prompt = self._initial_prompt()
        if initial_prompt:
            command.extend(["--initial_prompt", initial_prompt])
        try:
            completed = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds(),
                env=self._subprocess_env(command_path),
                **hidden_subprocess_kwargs(),
            )
        except FileNotFoundError as exception:
            raise WhisperSrtGenerationError(
                f"找不到 whisper 命令：{command_path}"
            ) from exception
        except subprocess.TimeoutExpired as exception:
            raise WhisperSrtGenerationError("whisper 字幕识别超时") from exception
        except subprocess.CalledProcessError as exception:
            detail = (exception.stderr or exception.stdout or "").strip()
            raise WhisperSrtGenerationError(
                f"whisper 字幕识别失败：{detail[-500:] or exception.returncode}"
            ) from exception

        if generated.exists() and generated.is_file() and generated.stat().st_size > 0:
            if generated != target:
                generated.replace(target)
        if not target.exists() or not target.is_file() or target.stat().st_size <= 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise WhisperSrtGenerationError(f"whisper 未生成 SRT：{detail[-500:]}")
        return WhisperSrtGenerationResult(srt_path=target, created=True)

    def _resolve_command_path(self) -> str:
        resolved = resolve_whisper_path(self.command_path or os.environ.get(WHISPER_PATH_ENV_KEY))
        if resolved:
            return resolved
        raise WhisperSrtGenerationError("找不到本机 whisper 命令")

    def _subprocess_env(self, command_path: str) -> dict[str, str]:
        env = dict(os.environ)
        path_dirs = [
            Path(command_path).expanduser().parent,
            Path(self.ffmpeg_path).expanduser().parent if self.ffmpeg_path else None,
            Path("/opt/homebrew/bin"),
            Path("/usr/local/bin"),
            Path("/usr/bin"),
            Path("/bin"),
            Path("/usr/sbin"),
            Path("/sbin"),
        ]
        existing_path = env.get("PATH") or ""
        merged: list[str] = []
        seen: set[str] = set()
        for directory in [*path_dirs, *(Path(part) for part in existing_path.split(os.pathsep) if part)]:
            if not directory:
                continue
            text = str(directory)
            if text == "." or text in seen:
                continue
            seen.add(text)
            merged.append(text)
        env["PATH"] = os.pathsep.join(merged)
        return env

    def _model(self) -> str:
        return str(self.model or os.environ.get(WHISPER_MODEL_ENV_KEY) or DEFAULT_WHISPER_MODEL)

    def _language(self) -> str:
        return str(
            self.language
            or os.environ.get(WHISPER_LANGUAGE_ENV_KEY)
            or DEFAULT_WHISPER_LANGUAGE
        )

    def _initial_prompt(self) -> str:
        return str(
            self.initial_prompt
            if self.initial_prompt is not None
            else os.environ.get(WHISPER_INITIAL_PROMPT_ENV_KEY, DEFAULT_WHISPER_INITIAL_PROMPT)
        ).strip()

    def _timeout_seconds(self) -> int:
        raw = self.timeout_seconds or os.environ.get(WHISPER_TIMEOUT_ENV_KEY)
        try:
            return max(60, int(raw)) if raw else DEFAULT_WHISPER_TIMEOUT_SECONDS
        except (TypeError, ValueError):
            return DEFAULT_WHISPER_TIMEOUT_SECONDS
