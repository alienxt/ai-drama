from __future__ import annotations

import json
import random
import re
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
DRAMA_STRATEGY1_TRIM_HEAD_SECONDS = 1.0
DRAMA_STRATEGY1_TRIM_TAIL_SECONDS = 1.0
DRAMA_STRATEGY1_MIN_SEGMENT_SECONDS = 50
DRAMA_STRATEGY1_MAX_SEGMENT_SECONDS = 60
DRAMA_STRATEGY1_MIN_LAST_SEGMENT_SECONDS = 30.0
DRAMA_STRATEGY1_MIN_SPEED = 1.02
DRAMA_STRATEGY1_MAX_SPEED = 1.05


class FfmpegError(RuntimeError):
    pass


@dataclass(frozen=True)
class DramaStrategySegment:
    file: Path
    source_episode_indexes: tuple[int, ...]


@dataclass(frozen=True)
class _TimelineSource:
    file: Path
    source_episode_index: int
    start_seconds: float
    end_seconds: float
    output_start_seconds: float
    output_end_seconds: float


@dataclass(frozen=True)
class VideoReassemblySourceClip:
    path: Path
    start_seconds: float
    duration_seconds: float


@dataclass(frozen=True)
class VideoReassemblySegment:
    index: int
    start_seconds: float
    duration_seconds: float
    target: Path


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

    def process_drama_with_strategy1(
        self,
        sources: list[Path],
        target_dir: Path,
        drama_title: str,
        *,
        speed: float | None = None,
        segment_seconds: tuple[int, int] = (
            DRAMA_STRATEGY1_MIN_SEGMENT_SECONDS,
            DRAMA_STRATEGY1_MAX_SEGMENT_SECONDS,
        ),
        trim_head_seconds: float = DRAMA_STRATEGY1_TRIM_HEAD_SECONDS,
        trim_tail_seconds: float = DRAMA_STRATEGY1_TRIM_TAIL_SECONDS,
        min_last_segment_seconds: float = DRAMA_STRATEGY1_MIN_LAST_SEGMENT_SECONDS,
    ) -> list[DramaStrategySegment]:
        if not sources:
            return []
        target_dir.mkdir(parents=True, exist_ok=True)
        effective_speed = speed or self._strategy1_speed(sources)
        timeline_sources = self._strategy1_timeline_sources(sources, effective_speed, trim_head_seconds, trim_tail_seconds)
        if not timeline_sources:
            return []
        total_seconds = timeline_sources[-1].output_end_seconds
        segment_lengths = self._strategy1_segment_lengths(sources, total_seconds, segment_seconds, min_last_segment_seconds)
        if not segment_lengths:
            return []
        boundaries = self._strategy1_segment_boundaries(segment_lengths)
        timeline_file = target_dir / ".strategy1-timeline.mp4"
        self._run_ffmpeg(
            self._strategy1_timeline_command(timeline_sources, timeline_file, effective_speed, boundaries),
            timeline_file,
        )
        generated_dir = target_dir / ".strategy1-segments"
        generated_dir.mkdir(parents=True, exist_ok=True)
        for existing in generated_dir.glob("*.mp4"):
            existing.unlink()
        split_pattern = generated_dir / "%03d.mp4"
        self._run_ffmpeg(
            self._strategy1_split_command(timeline_file, split_pattern, boundaries),
            split_pattern,
        )
        segments: list[DramaStrategySegment] = []
        for index, length in enumerate(segment_lengths, start=1):
            generated = generated_dir / f"{index - 1:03d}.mp4"
            target = target_dir / f"{self._safe_strategy1_title(drama_title)}-策略1第{index:03d}集.mp4"
            if not generated.exists():
                raise FfmpegError(f"策略1切分未生成第 {index} 段：{generated}")
            if target.exists():
                target.unlink()
            generated.replace(target)
            start = sum(segment_lengths[: index - 1])
            end = start + length
            source_indexes = self._strategy1_source_indexes_for_range(timeline_sources, start, end)
            segments.append(DramaStrategySegment(target, source_indexes))
        self._cleanup_failed_target(timeline_file)
        try:
            generated_dir.rmdir()
        except OSError:
            pass
        return segments

    def reassemble_videos(
        self,
        clips: list[VideoReassemblySourceClip],
        segments: list[VideoReassemblySegment],
        timeline: Path,
        *,
        speed_factor: float = 1.0,
        swap_orientation: bool = False,
    ) -> list[Path]:
        if not clips:
            raise ValueError("重组分集至少需要 1 个视频")
        if not segments:
            raise ValueError("重组分集没有可输出的切片")
        timeline.parent.mkdir(parents=True, exist_ok=True)
        for segment in segments:
            segment.target.parent.mkdir(parents=True, exist_ok=True)
        concat_file = timeline.with_name(f"{timeline.name}.concat.txt")
        concat_file.write_text(self._concat_clip_file_content(clips), encoding="utf-8")
        try:
            self._run_ffmpeg(
                self._reassembly_timeline_command(
                    concat_file,
                    timeline,
                    clips[0].path,
                    speed_factor=speed_factor,
                    swap_orientation=swap_orientation,
                ),
                timeline,
            )
            for segment in segments:
                self._run_ffmpeg(
                    self._reassembly_segment_command(timeline, segment),
                    segment.target,
                )
        finally:
            try:
                concat_file.unlink()
            except OSError:
                pass
        return [segment.target for segment in segments]

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

    def _strategy1_timeline_command(
        self,
        timeline_sources: list[_TimelineSource],
        target: Path,
        speed: float,
        boundaries: list[float] | None = None,
    ) -> list[str]:
        command = [self.ffmpeg_path, "-y"]
        for source in timeline_sources:
            command.extend(["-i", str(source.file)])
        filters: list[str] = []
        concat_inputs: list[str] = []
        atempo = self._audio_atempo_filter(speed)
        for input_index, source in enumerate(timeline_sources):
            filters.append(
                f"[{input_index}:v]trim=start={self._format_seconds(source.start_seconds)}:"
                f"end={self._format_seconds(source.end_seconds)},"
                f"setpts=(PTS-STARTPTS)/{self._format_float(speed)},format=yuv420p[v{input_index}]"
            )
            if self.video_has_audio(source.file):
                filters.append(
                    f"[{input_index}:a]atrim=start={self._format_seconds(source.start_seconds)}:"
                    f"end={self._format_seconds(source.end_seconds)},"
                    f"asetpts=PTS-STARTPTS,{atempo}[a{input_index}]"
                )
            else:
                duration = (source.end_seconds - source.start_seconds) / speed
                filters.append(
                    "anullsrc=r=48000:cl=stereo,"
                    f"atrim=duration={self._format_seconds(duration)},"
                    f"asetpts=PTS-STARTPTS[a{input_index}]"
                )
            concat_inputs.append(f"[v{input_index}][a{input_index}]")
        concat_filter = "".join(concat_inputs)
        concat_filter += f"concat=n={len(timeline_sources)}:v=1:a=1[outv][outa]"
        filter_complex = ";".join([*filters, concat_filter])
        command.extend(
            [
                "-filter_complex",
                filter_complex,
                "-map",
                "[outv]",
                "-map",
                "[outa]",
                *self._strategy1_force_keyframe_args(boundaries or []),
                *self._wechat_video_output_args(),
                str(target),
            ]
        )
        return command

    @staticmethod
    def _strategy1_force_keyframe_args(boundaries: list[float]) -> list[str]:
        if not boundaries:
            return []
        return ["-force_key_frames", ",".join(f"{boundary:.3f}" for boundary in boundaries)]

    def _strategy1_split_command(self, timeline_file: Path, split_pattern: Path, boundaries: list[float]) -> list[str]:
        command = [
            self.ffmpeg_path,
            "-y",
            "-i",
            str(timeline_file),
            "-c",
            "copy",
            "-f",
            "segment",
            "-reset_timestamps",
            "1",
        ]
        if boundaries:
            command.extend(["-segment_times", ",".join(f"{boundary:.3f}" for boundary in boundaries)])
        command.append(str(split_pattern))
        return command

    def _strategy1_timeline_sources(
        self,
        sources: list[Path],
        speed: float,
        trim_head_seconds: float,
        trim_tail_seconds: float,
    ) -> list[_TimelineSource]:
        timeline_sources: list[_TimelineSource] = []
        output_cursor = 0.0
        for index, source in enumerate(sources, start=1):
            duration = self.video_duration_seconds(source)
            if duration is None:
                raise FfmpegError(f"无法读取策略1源视频时长：{source}")
            start = min(max(trim_head_seconds, 0.0), duration)
            end = max(start, duration - max(trim_tail_seconds, 0.0))
            usable = end - start
            if usable <= 0:
                continue
            output_duration = usable / speed
            timeline_sources.append(
                _TimelineSource(
                    file=source,
                    source_episode_index=index,
                    start_seconds=start,
                    end_seconds=end,
                    output_start_seconds=output_cursor,
                    output_end_seconds=output_cursor + output_duration,
                )
            )
            output_cursor += output_duration
        return timeline_sources

    def _strategy1_segment_lengths(
        self,
        sources: list[Path],
        total_seconds: float,
        segment_seconds: tuple[int, int],
        min_last_segment_seconds: float,
    ) -> list[float]:
        min_seconds, max_seconds = sorted(segment_seconds)
        if total_seconds <= 0:
            return []
        if total_seconds <= max_seconds:
            return [total_seconds]
        rng = random.Random(self._strategy1_seed(sources))
        lengths: list[float] = []
        remaining = total_seconds
        while remaining > max_seconds:
            length = float(rng.randint(min_seconds, max_seconds))
            lengths.append(length)
            remaining -= length
        if remaining < min_last_segment_seconds and lengths:
            lengths[-1] += remaining
        else:
            lengths.append(remaining)
        return lengths

    @staticmethod
    def _strategy1_segment_boundaries(segment_lengths: list[float]) -> list[float]:
        boundaries: list[float] = []
        cursor = 0.0
        for length in segment_lengths[:-1]:
            cursor += length
            boundaries.append(cursor)
        return boundaries

    @staticmethod
    def _strategy1_source_indexes_for_range(
        timeline_sources: list[_TimelineSource],
        start_seconds: float,
        end_seconds: float,
    ) -> tuple[int, ...]:
        indexes = [
            source.source_episode_index
            for source in timeline_sources
            if source.output_start_seconds < end_seconds and source.output_end_seconds > start_seconds
        ]
        return tuple(dict.fromkeys(indexes))

    def _strategy1_speed(self, sources: list[Path]) -> float:
        rng = random.Random(self._strategy1_seed(sources))
        return round(rng.uniform(DRAMA_STRATEGY1_MIN_SPEED, DRAMA_STRATEGY1_MAX_SPEED), 3)

    @staticmethod
    def _strategy1_seed(sources: list[Path]) -> str:
        parts = []
        for source in sources:
            try:
                stat = source.stat()
                parts.append(f"{source.name}:{stat.st_size}:{stat.st_mtime_ns}")
            except OSError:
                parts.append(source.name)
        return "|".join(parts)

    @staticmethod
    def _audio_atempo_filter(speed: float) -> str:
        if 0.5 <= speed <= 2.0:
            return f"atempo={FfmpegProcessor._format_float(speed)}"
        filters: list[str] = []
        remaining = speed
        while remaining > 2.0:
            filters.append("atempo=2.0")
            remaining /= 2.0
        while remaining < 0.5:
            filters.append("atempo=0.5")
            remaining /= 0.5
        filters.append(f"atempo={FfmpegProcessor._format_float(remaining)}")
        return ",".join(filters)

    @staticmethod
    def _safe_strategy1_title(value: object) -> str:
        clean = re.sub(r'[\\/:*?"<>|\r\n\t]+', "", str(value or "").strip())
        clean = re.sub(r"\s+", "", clean).strip(" ._-")
        return clean or "短剧"

    @staticmethod
    def _format_seconds(value: float) -> str:
        text = f"{value:.3f}"
        return text.rstrip("0").rstrip(".") if "." in text else text

    @staticmethod
    def _format_float(value: float) -> str:
        text = f"{value:.6f}"
        return text.rstrip("0").rstrip(".") if "." in text else text

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

    def _reassembly_timeline_command(
        self,
        concat_file: Path,
        timeline: Path,
        first_source: Path,
        *,
        speed_factor: float,
        swap_orientation: bool,
    ) -> list[str]:
        command = [
            self.ffmpeg_path,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
        ]
        video_filters = self._reassembly_video_filters(first_source, speed_factor, swap_orientation)
        if video_filters:
            command.extend(["-vf", ",".join(video_filters)])
        if self.has_audio_stream(first_source) and self._has_effective_speed_change(speed_factor):
            command.extend(["-af", self._atempo_filter(speed_factor)])
        command.extend([*self._wechat_video_output_args(), str(timeline)])
        return command

    def _reassembly_segment_command(
        self,
        timeline: Path,
        segment: VideoReassemblySegment,
    ) -> list[str]:
        return [
            self.ffmpeg_path,
            "-y",
            "-ss",
            self._format_seconds(segment.start_seconds),
            "-i",
            str(timeline),
            "-t",
            self._format_seconds(segment.duration_seconds),
            *self._wechat_video_output_args(),
            str(segment.target),
        ]

    def _reassembly_video_filters(
        self,
        first_source: Path,
        speed_factor: float,
        swap_orientation: bool,
    ) -> list[str]:
        filters: list[str] = []
        if swap_orientation:
            dimensions = self.video_dimensions(first_source)
            if dimensions:
                width, height = dimensions
                filters.append(self._wechat_video_frame_filter(height, width))
        if self._has_effective_speed_change(speed_factor):
            filters.append(f"setpts=PTS/{self._format_filter_number(speed_factor)}")
        return filters

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
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
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

    def video_has_audio(self, source: Path) -> bool:
        return self.has_audio_stream(source)

    def has_audio_stream(self, source: Path) -> bool:
        command = [
            self.ffprobe_path(),
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=index",
            "-of",
            "json",
            str(source),
        ]
        try:
            result = subprocess.run(command, check=True, capture_output=True, text=True)
            payload = json.loads(result.stdout or "{}")
        except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
            return False
        return bool(payload.get("streams"))

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

    @classmethod
    def _concat_clip_file_content(cls, clips: list[VideoReassemblySourceClip]) -> str:
        lines: list[str] = []
        for clip in clips:
            start = max(0.0, clip.start_seconds)
            duration = max(0.001, clip.duration_seconds)
            lines.append(f"file '{cls._escape_concat_file_path(clip.path)}'")
            if start > 0:
                lines.append(f"inpoint {cls._format_seconds(start)}")
            lines.append(f"outpoint {cls._format_seconds(start + duration)}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _format_seconds(value: float) -> str:
        return f"{max(value, 0.0):.3f}".rstrip("0").rstrip(".") or "0"

    @staticmethod
    def _format_filter_number(value: float) -> str:
        return f"{value:.6f}".rstrip("0").rstrip(".")

    @staticmethod
    def _has_effective_speed_change(speed_factor: float) -> bool:
        return abs(speed_factor - 1.0) >= 0.0001

    @classmethod
    def _atempo_filter(cls, speed_factor: float) -> str:
        factor = max(speed_factor, 0.01)
        parts: list[float] = []
        while factor > 2.0:
            parts.append(2.0)
            factor /= 2.0
        while factor < 0.5:
            parts.append(0.5)
            factor /= 0.5
        parts.append(factor)
        return ",".join(f"atempo={cls._format_filter_number(part)}" for part in parts)

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
