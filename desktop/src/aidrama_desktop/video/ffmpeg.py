from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

WECHAT_VIDEO_MIN_BITRATE_BPS = 4_000_000
WECHAT_VIDEO_TARGET_BITRATE = "5000k"


@dataclass
class FfmpegProcessor:
    ffmpeg_path: str

    def transcode_for_wechat_video(self, source: Path, target: Path) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        command = [
            self.ffmpeg_path,
            "-y",
            "-i",
            str(source),
            "-c:v",
            "libx264",
            "-b:v",
            WECHAT_VIDEO_TARGET_BITRATE,
            "-minrate",
            WECHAT_VIDEO_TARGET_BITRATE,
            "-maxrate",
            WECHAT_VIDEO_TARGET_BITRATE,
            "-bufsize",
            "10000k",
            "-preset",
            "veryfast",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(target),
        ]
        subprocess.run(command, check=True)
        return target

    def needs_wechat_video_bitrate_transcode(
        self,
        source: Path,
        min_bitrate_bps: int = WECHAT_VIDEO_MIN_BITRATE_BPS,
    ) -> bool:
        bitrate = self.video_bitrate_bps(source)
        return bitrate is not None and bitrate < min_bitrate_bps

    def video_bitrate_bps(self, source: Path) -> int | None:
        command = [
            self.ffprobe_path(),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=bit_rate",
            "-show_entries",
            "format=bit_rate",
            "-of",
            "json",
            str(source),
        ]
        try:
            result = subprocess.run(command, check=True, capture_output=True, text=True)
            payload = json.loads(result.stdout or "{}")
        except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
            return None
        return self._bitrate_from_probe_payload(payload)

    def ffprobe_path(self) -> str:
        ffmpeg = Path(self.ffmpeg_path)
        if ffmpeg.name == "ffmpeg":
            return str(ffmpeg.with_name("ffprobe")) if ffmpeg.parent != Path(".") else "ffprobe"
        if ffmpeg.name.startswith("ffmpeg"):
            return str(ffmpeg.with_name(ffmpeg.name.replace("ffmpeg", "ffprobe", 1)))
        return "ffprobe"

    @staticmethod
    def _bitrate_from_probe_payload(payload: dict) -> int | None:
        for stream in payload.get("streams") or []:
            bitrate = FfmpegProcessor._positive_int(stream.get("bit_rate"))
            if bitrate:
                return bitrate
        return FfmpegProcessor._positive_int((payload.get("format") or {}).get("bit_rate"))

    @staticmethod
    def _positive_int(value: object) -> int | None:
        try:
            parsed = int(str(value))
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None
