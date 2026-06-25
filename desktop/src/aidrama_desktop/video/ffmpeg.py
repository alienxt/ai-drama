from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

WECHAT_VIDEO_MIN_BITRATE_BPS = 4_000_000
WECHAT_VIDEO_TARGET_BITRATE = "5000k"
WECHAT_VIDEO_COVER_FRAME_SECONDS = 1
WECHAT_VIDEO_COVER_FRAME_VERSION = "wechat-video-cover-frame-v5"


@dataclass
class FfmpegProcessor:
    ffmpeg_path: str

    def transcode_for_wechat_video(self, source: Path, target: Path, cover_path: Path | None = None) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        command = self._transcode_with_cover_command(source, target, cover_path) if cover_path else self._transcode_command(source, target)
        subprocess.run(command, check=True)
        return target

    def _transcode_command(self, source: Path, target: Path) -> list[str]:
        return [
            self.ffmpeg_path,
            "-y",
            "-i",
            str(source),
            *self._wechat_video_output_args(),
            str(target),
        ]

    def _transcode_with_cover_command(self, source: Path, target: Path, cover_path: Path | None) -> list[str]:
        dimensions = self.video_dimensions(source)
        if not cover_path or not cover_path.exists() or not dimensions:
            return self._transcode_command(source, target)
        width, height = dimensions
        filter_complex = (
            f"[0:v]scale={width}:{height},setsar=1,format=yuv420p,setpts=PTS-STARTPTS[mainv];"
            "[1:v]split=2[coverbgsrc][coverfgsrc];"
            f"[coverbgsrc]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},boxblur=24:2,eq=brightness=-0.08:saturation=0.85,"
            "setsar=1,format=rgba[coverbg];"
            f"[coverfgsrc]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            "setsar=1,format=rgba[coverfg];"
            "[coverbg][coverfg]overlay=(W-w)/2:(H-h)/2,format=yuv420p,split=2[coverv][picv];"
            f"[mainv][coverv]overlay=0:0:enable='lt(t,{WECHAT_VIDEO_COVER_FRAME_SECONDS})',format=yuv420p[outv]"
        )
        return [
            self.ffmpeg_path,
            "-y",
            "-i",
            str(source),
            "-i",
            str(cover_path),
            "-filter_complex",
            filter_complex,
            "-map",
            "[outv]",
            "-map",
            "0:a?",
            "-map",
            "[picv]",
            *self._wechat_video_output_args(),
            "-c:v:1",
            "mjpeg",
            "-disposition:v:1",
            "attached_pic",
            str(target),
        ]

    @staticmethod
    def _wechat_video_output_args() -> list[str]:
        return [
            "-c:v:0",
            "libx264",
            "-b:v:0",
            WECHAT_VIDEO_TARGET_BITRATE,
            "-minrate:v:0",
            WECHAT_VIDEO_TARGET_BITRATE,
            "-maxrate:v:0",
            WECHAT_VIDEO_TARGET_BITRATE,
            "-bufsize:v:0",
            "10000k",
            "-x264-params",
            "nal-hrd=cbr:filler=1",
            "-preset",
            "veryfast",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-pix_fmt:v:0",
            "yuv420p",
            "-movflags",
            "+faststart",
        ]

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

    def video_dimensions(self, source: Path) -> tuple[int, int] | None:
        command = [
            self.ffprobe_path(),
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(source),
        ]
        try:
            result = subprocess.run(command, check=True, capture_output=True, text=True)
            payload = json.loads(result.stdout or "{}")
        except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
            return None
        for stream in payload.get("streams") or []:
            width = self._positive_even_int(stream.get("width"))
            height = self._positive_even_int(stream.get("height"))
            if width and height:
                return width, height
        return None

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

    @staticmethod
    def _positive_even_int(value: object) -> int | None:
        parsed = FfmpegProcessor._positive_int(value)
        if not parsed:
            return None
        return parsed if parsed % 2 == 0 else parsed - 1
