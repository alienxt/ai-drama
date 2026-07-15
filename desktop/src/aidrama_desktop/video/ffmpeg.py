from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

WECHAT_VIDEO_MIN_BITRATE_BPS = 4_000_000
WECHAT_VIDEO_MIN_WIDTH = 720
WECHAT_VIDEO_MIN_HEIGHT = 1280
WECHAT_VIDEO_TARGET_BITRATE = "5000k"
WECHAT_VIDEO_COVER_FRAME_SECONDS = 1
WECHAT_VIDEO_TRANSCODE_VERSION = "wechat-video-transcode-v7"
WECHAT_VIDEO_COVER_FRAME_VERSION = WECHAT_VIDEO_TRANSCODE_VERSION


class FfmpegError(RuntimeError):
    pass


@dataclass
class FfmpegProcessor:
    ffmpeg_path: str

    def transcode_for_wechat_video(self, source: Path, target: Path, cover_path: Path | None = None) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        command = self._transcode_with_cover_command(source, target, cover_path) if cover_path else self._transcode_command(source, target)
        return self._run_ffmpeg(command, target)

    def merge_videos_for_tiktok(self, sources: list[Path], target: Path) -> Path:
        if len(sources) < 2:
            raise ValueError("TK 剧集合并至少需要 2 个视频")
        target.parent.mkdir(parents=True, exist_ok=True)
        concat_file = target.with_name(f"{target.name}.concat.txt")
        concat_file.write_text(self._concat_file_content(sources), encoding="utf-8")
        command = [
            self.ffmpeg_path,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            *self._wechat_video_output_args(),
            str(target),
        ]
        try:
            return self._run_ffmpeg(command, target)
        finally:
            try:
                concat_file.unlink()
            except OSError:
                pass

    def _run_ffmpeg(self, command: list[str], target: Path) -> Path:
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except FileNotFoundError as exception:
            self._cleanup_failed_target(target)
            raise FfmpegError(f"找不到 FFmpeg 可执行文件：{self.ffmpeg_path}") from exception
        except subprocess.CalledProcessError as exception:
            self._cleanup_failed_target(target)
            detail = self._process_output_tail(exception.stdout, exception.stderr)
            raise FfmpegError(f"FFmpeg 转码退出码 {exception.returncode}：{detail}") from exception
        except OSError as exception:
            self._cleanup_failed_target(target)
            raise FfmpegError(f"FFmpeg 无法启动：{exception}") from exception
        return target

    def _transcode_command(self, source: Path, target: Path) -> list[str]:
        command = [
            self.ffmpeg_path,
            "-y",
            "-i",
            str(source),
        ]
        output_dimensions = self._wechat_video_output_dimensions(source)
        if output_dimensions:
            command.extend(["-vf", self._wechat_video_frame_filter(*output_dimensions)])
        command.extend([*self._wechat_video_output_args(), str(target)])
        return command

    def _transcode_with_cover_command(self, source: Path, target: Path, cover_path: Path | None) -> list[str]:
        dimensions = self.video_dimensions(source)
        if not cover_path or not cover_path.exists() or not dimensions:
            return self._transcode_command(source, target)
        width, height = self._wechat_video_output_dimensions(source) or dimensions
        main_filter = self._wechat_video_frame_filter(width, height)
        filter_complex = (
            f"[0:v]{main_filter},setpts=PTS-STARTPTS[mainv];"
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

    def _wechat_video_output_dimensions(self, source: Path) -> tuple[int, int] | None:
        dimensions = self.video_dimensions(source)
        if not dimensions:
            return None
        width, height = dimensions
        if self._is_below_wechat_video_minimum(width, height):
            return WECHAT_VIDEO_MIN_WIDTH, WECHAT_VIDEO_MIN_HEIGHT
        return width, height

    @staticmethod
    def _wechat_video_frame_filter(width: int, height: int) -> str:
        return (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
            "setsar=1,format=yuv420p"
        )

    @classmethod
    def _concat_file_content(cls, sources: list[Path]) -> str:
        lines = [f"file '{cls._escape_concat_file_path(source)}'" for source in sources]
        return "\n".join(lines) + "\n"

    @staticmethod
    def _escape_concat_file_path(source: Path) -> str:
        return str(source.resolve()).replace("\\", "\\\\").replace("'", "\\'")

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

    def needs_wechat_video_resolution_transcode(
        self,
        source: Path,
        min_width: int = WECHAT_VIDEO_MIN_WIDTH,
        min_height: int = WECHAT_VIDEO_MIN_HEIGHT,
    ) -> bool:
        dimensions = self.video_dimensions(source)
        if not dimensions:
            return False
        width, height = dimensions
        return width < min_width or height < min_height

    def needs_wechat_video_transcode(self, source: Path) -> bool:
        return self.needs_wechat_video_bitrate_transcode(source) or self.needs_wechat_video_resolution_transcode(source)

    @staticmethod
    def _is_below_wechat_video_minimum(width: int, height: int) -> bool:
        return width < WECHAT_VIDEO_MIN_WIDTH or height < WECHAT_VIDEO_MIN_HEIGHT

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

    def video_duration_seconds(self, source: Path) -> float | None:
        command = [
            self.ffprobe_path(),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(source),
        ]
        try:
            result = subprocess.run(command, check=True, capture_output=True, text=True)
            payload = json.loads(result.stdout or "{}")
        except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
            return None
        return self._positive_float((payload.get("format") or {}).get("duration"))

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
    def _positive_float(value: object) -> float | None:
        try:
            parsed = float(str(value))
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _positive_even_int(value: object) -> int | None:
        parsed = FfmpegProcessor._positive_int(value)
        if not parsed:
            return None
        return parsed if parsed % 2 == 0 else parsed - 1

    @staticmethod
    def _process_output_tail(stdout: str | None, stderr: str | None, max_lines: int = 8, max_chars: int = 1000) -> str:
        text = "\n".join(part for part in (stderr, stdout) if part)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return "没有返回错误详情"
        tail = "\n".join(lines[-max_lines:])
        return tail[-max_chars:]

    @staticmethod
    def _cleanup_failed_target(target: Path) -> None:
        try:
            if target.exists():
                target.unlink()
        except OSError:
            pass
