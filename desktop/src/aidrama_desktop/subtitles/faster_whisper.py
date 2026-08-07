from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from aidrama_desktop.config.settings import (
    COMMON_FASTER_WHISPER_PYTHON_PATHS as SETTINGS_COMMON_FASTER_WHISPER_PYTHON_PATHS,
)
from aidrama_desktop.config.settings import (
    SUBTITLE_PROVIDER_FASTER_WHISPER,
    resolve_faster_whisper_python_path,
)
from aidrama_desktop.subprocess_utils import hidden_subprocess_kwargs
from aidrama_desktop.subtitles.whisper import (
    DEFAULT_WHISPER_INITIAL_PROMPT,
    DEFAULT_WHISPER_LANGUAGE,
    WHISPER_INITIAL_PROMPT_ENV_KEY,
    WHISPER_LANGUAGE_ENV_KEY,
    WHISPER_MODEL_ENV_KEY,
    WHISPER_TIMEOUT_ENV_KEY,
    WhisperSrtGenerationError,
    WhisperSrtGenerationResult,
)


FASTER_WHISPER_PYTHON_PATH_ENV_KEY = "AIDRAMA_FASTER_WHISPER_PYTHON_PATH"
FASTER_WHISPER_DEVICE_ENV_KEY = "AIDRAMA_FASTER_WHISPER_DEVICE"
FASTER_WHISPER_COMPUTE_TYPE_ENV_KEY = "AIDRAMA_FASTER_WHISPER_COMPUTE_TYPE"
DEFAULT_FASTER_WHISPER_MODEL = "base"
DEFAULT_FASTER_WHISPER_DEVICE = "auto"
DEFAULT_FASTER_WHISPER_COMPUTE_TYPE = "int8"
COMMON_FASTER_WHISPER_PYTHON_PATHS = SETTINGS_COMMON_FASTER_WHISPER_PYTHON_PATHS


@dataclass
class FasterWhisperSrtGenerator:
    python_path: str | None = None
    model: str | None = None
    language: str | None = None
    initial_prompt: str | None = None
    timeout_seconds: int | None = None
    device: str | None = None
    compute_type: str | None = None

    def generate_srt(self, video: Path, target: Path) -> WhisperSrtGenerationResult:
        video = Path(video)
        target = Path(target)
        if not video.exists() or not video.is_file():
            raise WhisperSrtGenerationError(f"字幕源视频不存在：{video}")
        if target.exists() and target.is_file() and target.stat().st_size > 0:
            return WhisperSrtGenerationResult(
                srt_path=target,
                created=False,
                provider=SUBTITLE_PROVIDER_FASTER_WHISPER,
            )

        python_path = self._resolve_python_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_target = target.with_name(f".{target.name}.tmp")
        if temp_target.exists():
            temp_target.unlink()

        command = [
            python_path,
            "-c",
            _FASTER_WHISPER_RUNNER,
            "--video",
            str(video),
            "--target",
            str(temp_target),
            "--model",
            self._model(),
            "--language",
            self._language(),
            "--device",
            self._device(),
            "--compute-type",
            self._compute_type(),
        ]
        initial_prompt = self._initial_prompt()
        if initial_prompt:
            command.extend(["--initial-prompt", initial_prompt])
        try:
            completed = subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds(),
                env=self._subprocess_env(),
                **hidden_subprocess_kwargs(),
            )
        except FileNotFoundError as exception:
            raise WhisperSrtGenerationError(
                f"找不到 faster-whisper Python：{python_path}"
            ) from exception
        except subprocess.TimeoutExpired as exception:
            raise WhisperSrtGenerationError("faster-whisper 字幕识别超时") from exception
        except subprocess.CalledProcessError as exception:
            detail = (exception.stderr or exception.stdout or "").strip()
            raise WhisperSrtGenerationError(
                f"faster-whisper 字幕识别失败：{detail[-500:] or exception.returncode}"
            ) from exception

        if temp_target.exists() and temp_target.is_file() and temp_target.stat().st_size > 0:
            temp_target.replace(target)
        if not target.exists() or not target.is_file() or target.stat().st_size <= 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise WhisperSrtGenerationError(f"faster-whisper 未生成 SRT：{detail[-500:]}")
        return WhisperSrtGenerationResult(
            srt_path=target,
            created=True,
            provider=SUBTITLE_PROVIDER_FASTER_WHISPER,
        )

    def _resolve_python_path(self) -> str:
        resolved = resolve_faster_whisper_python_path(
            self.python_path or os.environ.get(FASTER_WHISPER_PYTHON_PATH_ENV_KEY)
        )
        if resolved:
            return resolved
        raise WhisperSrtGenerationError("找不到 faster-whisper Python")

    @staticmethod
    def _subprocess_env() -> dict[str, str]:
        env = dict(os.environ)
        env.setdefault("PYTHONIOENCODING", "utf-8")
        return env

    def _model(self) -> str:
        return str(self.model or os.environ.get(WHISPER_MODEL_ENV_KEY) or DEFAULT_FASTER_WHISPER_MODEL)

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
            return max(60, int(raw)) if raw else 30 * 60
        except (TypeError, ValueError):
            return 30 * 60

    def _device(self) -> str:
        return str(
            self.device
            or os.environ.get(FASTER_WHISPER_DEVICE_ENV_KEY)
            or DEFAULT_FASTER_WHISPER_DEVICE
        )

    def _compute_type(self) -> str:
        return str(
            self.compute_type
            or os.environ.get(FASTER_WHISPER_COMPUTE_TYPE_ENV_KEY)
            or DEFAULT_FASTER_WHISPER_COMPUTE_TYPE
        )


_FASTER_WHISPER_RUNNER = r"""
from __future__ import annotations

import argparse
from pathlib import Path

from faster_whisper import WhisperModel


def format_timestamp(seconds: float) -> str:
    milliseconds = max(0, int(round(float(seconds) * 1000.0)))
    hours, milliseconds = divmod(milliseconds, 60 * 60 * 1000)
    minutes, milliseconds = divmod(milliseconds, 60 * 1000)
    seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def clean_text(text: object) -> str:
    return " ".join(str(text or "").strip().split())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--language", required=True)
    parser.add_argument("--device", required=True)
    parser.add_argument("--compute-type", required=True)
    parser.add_argument("--initial-prompt", default="")
    args = parser.parse_args()

    model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)
    segments, _ = model.transcribe(
        args.video,
        language=args.language or None,
        initial_prompt=args.initial_prompt or None,
        beam_size=1,
        vad_filter=True,
        word_timestamps=False,
        condition_on_previous_text=False,
    )

    target = Path(args.target)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        index = 1
        for segment in segments:
            text = clean_text(segment.text)
            if not text:
                continue
            handle.write(f"{index}\n")
            handle.write(f"{format_timestamp(segment.start)} --> {format_timestamp(segment.end)}\n")
            handle.write(f"{text}\n\n")
            index += 1


if __name__ == "__main__":
    main()
"""
