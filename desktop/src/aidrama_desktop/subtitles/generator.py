from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from aidrama_desktop.config.settings import (
    SUBTITLE_PROVIDER_OPENAI_WHISPER,
    normalize_subtitle_provider,
)
from aidrama_desktop.subtitles.faster_whisper import FasterWhisperSrtGenerator
from aidrama_desktop.subtitles.whisper import (
    WhisperSrtGenerationError,
    WhisperSrtGenerationResult,
    WhisperSrtGenerator,
)


SUBTITLE_PROVIDER_ENV_KEY = "AIDRAMA_SUBTITLE_PROVIDER"


@dataclass
class SubtitleSrtGenerator:
    provider: str | None = None
    whisper_path: str | None = None
    faster_whisper_python_path: str | None = None
    ffmpeg_path: str | None = None

    def generate_srt(self, video: Path, target: Path) -> WhisperSrtGenerationResult:
        provider = normalize_subtitle_provider(
            self.provider or os.environ.get(SUBTITLE_PROVIDER_ENV_KEY)
        )
        if provider == SUBTITLE_PROVIDER_OPENAI_WHISPER:
            return WhisperSrtGenerator(
                command_path=self.whisper_path,
                ffmpeg_path=self.ffmpeg_path,
            ).generate_srt(video, target)

        errors: list[str] = []
        try:
            return FasterWhisperSrtGenerator(
                python_path=self.faster_whisper_python_path,
            ).generate_srt(video, target)
        except WhisperSrtGenerationError as exception:
            errors.append(f"fasterWhisper: {exception}")

        try:
            return WhisperSrtGenerator(
                command_path=self.whisper_path,
                ffmpeg_path=self.ffmpeg_path,
            ).generate_srt(video, target)
        except WhisperSrtGenerationError as exception:
            errors.append(f"openaiWhisper: {exception}")

        raise WhisperSrtGenerationError("；".join(errors))
