from __future__ import annotations

import json
import os
import random
import re
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from aidrama_desktop.config.settings import (
    ffprobe_path_for_ffmpeg,
    find_existing_ffmpeg_path,
    find_ffmpeg_fallback_path,
    normalize_executable_path,
)
from aidrama_desktop.subprocess_utils import hidden_subprocess_kwargs

WECHAT_VIDEO_MIN_BITRATE_BPS = 4_000_000
WECHAT_VIDEO_MIN_WIDTH = 720
WECHAT_VIDEO_MIN_HEIGHT = 1280
WECHAT_VIDEO_TARGET_BITRATE = "5000k"
WECHAT_VIDEO_TARGET_FPS = 30
WECHAT_VIDEO_COVER_FRAME_SECONDS = 1
WECHAT_VIDEO_TRANSCODE_VERSION = "wechat-video-transcode-v9"
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


def minimum_wechat_video_dimensions(width: int, height: int) -> tuple[int, int]:
    if width >= height:
        return WECHAT_VIDEO_MIN_HEIGHT, WECHAT_VIDEO_MIN_WIDTH
    return WECHAT_VIDEO_MIN_WIDTH, WECHAT_VIDEO_MIN_HEIGHT


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

    def transcode_for_wechat_video(
        self,
        source: Path,
        target: Path,
        cover_path: Path | None = None,
        *,
        trim_head_seconds: float = 0.0,
        trim_tail_seconds: float = 0.0,
        speed_factor: float = 1.0,
        swap_orientation: bool = False,
        bgm_files: list[Path] | None = None,
        bgm_volume_percent: float = 0.0,
        audio_pitch_semitones: float = 0.0,
        border_percent: float = 0.0,
        mirror_horizontal: bool = False,
        rotate_degrees: float = 0.0,
    ) -> Path:
        target.parent.mkdir(parents=True, exist_ok=True)
        has_effects = any(
            [
                trim_head_seconds > 0,
                trim_tail_seconds > 0,
                self._has_effective_speed_change(speed_factor),
                swap_orientation,
                bool(bgm_files),
                bgm_volume_percent > 0,
                abs(audio_pitch_semitones) >= 0.001,
                border_percent > 0,
                mirror_horizontal,
                abs(rotate_degrees) >= 0.001,
            ]
        )
        if has_effects:
            command = self._transcode_with_effects_command(
                source,
                target,
                trim_head_seconds=trim_head_seconds,
                trim_tail_seconds=trim_tail_seconds,
                speed_factor=speed_factor,
                swap_orientation=swap_orientation,
                bgm_files=bgm_files or [],
                bgm_volume_percent=bgm_volume_percent,
                audio_pitch_semitones=audio_pitch_semitones,
                border_percent=border_percent,
                mirror_horizontal=mirror_horizontal,
                rotate_degrees=rotate_degrees,
            )
        else:
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
        bgm_files: list[Path] | None = None,
        bgm_volume_percent: float = 0.0,
        audio_pitch_semitones: float = 0.0,
        border_percent: float = 0.0,
        mirror_horizontal: bool = False,
        rotate_degrees: float = 0.0,
        cover_path: Path | None = None,
    ) -> list[Path]:
        if not clips:
            raise ValueError("重组分集至少需要 1 个视频")
        if not segments:
            raise ValueError("重组分集没有可输出的切片")
        timeline.parent.mkdir(parents=True, exist_ok=True)
        for segment in segments:
            segment.target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="aidrama-ffmpeg-") as work_dir_value:
            work_dir = Path(work_dir_value)
            staged_clips = self._stage_reassembly_clips(clips, work_dir)
            staged_cover = self._stage_reassembly_cover(cover_path, work_dir)
            timeline_duration = sum(max(segment.duration_seconds, 0.0) for segment in segments)
            staged_bgm_files = self._stage_reassembly_bgm_files(
                bgm_files or [],
                work_dir,
                timeline_duration=timeline_duration,
            )
            work_timeline = work_dir / "timeline.mp4"
            work_segments = [
                VideoReassemblySegment(
                    segment.index,
                    segment.start_seconds,
                    segment.duration_seconds,
                    work_dir / f"segment-{segment.index:03d}.mp4",
                )
                for segment in segments
            ]
            timeline_command = self._reassembly_timeline_command(
                staged_clips,
                work_timeline,
                speed_factor=speed_factor,
                swap_orientation=swap_orientation,
                bgm_files=staged_bgm_files,
                bgm_volume_percent=bgm_volume_percent,
                audio_pitch_semitones=audio_pitch_semitones,
                border_percent=border_percent,
                mirror_horizontal=mirror_horizontal,
                rotate_degrees=rotate_degrees,
            )
            try:
                self._run_ffmpeg(timeline_command, work_timeline)
            except FfmpegError as exception:
                if not self._is_reassembly_audio_decode_error(exception):
                    raise
                self._run_ffmpeg(
                    self._reassembly_timeline_command(
                        staged_clips,
                        work_timeline,
                        speed_factor=speed_factor,
                        swap_orientation=swap_orientation,
                        bgm_files=staged_bgm_files,
                        bgm_volume_percent=bgm_volume_percent,
                        audio_pitch_semitones=audio_pitch_semitones,
                        border_percent=border_percent,
                        mirror_horizontal=mirror_horizontal,
                        rotate_degrees=rotate_degrees,
                        drop_audio=True,
                    ),
                    work_timeline,
                )
            for segment, work_segment in zip(segments, work_segments, strict=True):
                self._run_ffmpeg(
                    self._reassembly_segment_command(work_timeline, work_segment, cover_path=staged_cover),
                    work_segment.target,
                )
                self._move_generated_output(work_segment.target, segment.target)
        return [segment.target for segment in segments]

    def _run_ffmpeg(self, command: list[str], target: Path) -> Path:
        try:
            subprocess.run(command, check=True, capture_output=True, text=True, **hidden_subprocess_kwargs())
        except FileNotFoundError as exception:
            fallback_command = self._ffmpeg_fallback_command(command)
            if fallback_command:
                try:
                    subprocess.run(
                        fallback_command,
                        check=True,
                        capture_output=True,
                        text=True,
                        **hidden_subprocess_kwargs(),
                    )
                    self.ffmpeg_path = fallback_command[0]
                    return target
                except FileNotFoundError:
                    pass
                except subprocess.CalledProcessError as fallback_exception:
                    self._cleanup_failed_target(target)
                    raise FfmpegError(
                        self._format_ffmpeg_failure_message(
                            fallback_command,
                            fallback_exception.returncode,
                            fallback_exception.stdout,
                            fallback_exception.stderr,
                            target,
                        )
                    ) from fallback_exception
                except OSError as fallback_exception:
                    self._cleanup_failed_target(target)
                    raise FfmpegError(f"FFmpeg 无法启动：{fallback_exception}") from fallback_exception
            self._cleanup_failed_target(target)
            raise FfmpegError(self._format_ffmpeg_missing_message(command, exception, fallback_command)) from exception
        except subprocess.CalledProcessError as exception:
            self._cleanup_failed_target(target)
            raise FfmpegError(
                self._format_ffmpeg_failure_message(
                    command,
                    exception.returncode,
                    exception.stdout,
                    exception.stderr,
                    target,
                )
            ) from exception
        except OSError as exception:
            self._cleanup_failed_target(target)
            raise FfmpegError(f"FFmpeg 无法启动：{exception}") from exception
        return target

    def _stage_reassembly_clips(
        self,
        clips: list[VideoReassemblySourceClip],
        work_dir: Path,
    ) -> list[VideoReassemblySourceClip]:
        staged: list[VideoReassemblySourceClip] = []
        for index, clip in enumerate(clips, start=1):
            suffix = clip.path.suffix if clip.path.suffix else ".mp4"
            staged_path = work_dir / f"source-{index:03d}{suffix}"
            self._stage_reassembly_file(clip.path, staged_path)
            staged.append(
                VideoReassemblySourceClip(
                    staged_path,
                    clip.start_seconds,
                    clip.duration_seconds,
                )
            )
        return staged

    def _stage_reassembly_cover(self, cover_path: Path | None, work_dir: Path) -> Path | None:
        if not cover_path or not cover_path.exists():
            return None
        suffix = cover_path.suffix if cover_path.suffix else ".jpg"
        staged_cover = work_dir / f"cover{suffix}"
        self._stage_reassembly_file(cover_path, staged_cover)
        return staged_cover

    def _stage_reassembly_bgm_files(
        self,
        bgm_files: list[Path],
        work_dir: Path,
        *,
        timeline_duration: float,
    ) -> list[Path]:
        if not bgm_files or timeline_duration <= 0:
            return []
        staged_pool: list[Path] = []
        durations: list[float] = []
        for index, file in enumerate(bgm_files, start=1):
            if not file.exists() or not file.is_file():
                continue
            suffix = file.suffix if file.suffix else ".m4a"
            staged_path = work_dir / f"bgm-{index:03d}{suffix}"
            self._stage_reassembly_file(file, staged_path)
            duration = self.media_duration_seconds(staged_path)
            if duration is None or duration <= 0:
                continue
            staged_pool.append(staged_path)
            durations.append(duration)
        if not staged_pool:
            return []
        playlist: list[Path] = []
        remaining = timeline_duration
        cursor = 0
        while remaining > 0.001 and cursor < 512:
            index = cursor % len(staged_pool)
            playlist.append(staged_pool[index])
            remaining -= durations[index]
            cursor += 1
        return playlist

    def _loop_bgm_files_for_duration(self, bgm_files: list[Path], duration_seconds: float) -> list[Path]:
        if not bgm_files or duration_seconds <= 0:
            return []
        playable: list[tuple[Path, float]] = []
        for file in bgm_files:
            if not file.exists() or not file.is_file():
                continue
            media_duration = self.media_duration_seconds(file)
            if media_duration is None or media_duration <= 0:
                continue
            playable.append((file, media_duration))
        if not playable:
            return []
        playlist: list[Path] = []
        remaining = duration_seconds
        cursor = 0
        while remaining > 0.001 and cursor < 512:
            file, media_duration = playable[cursor % len(playable)]
            playlist.append(file)
            remaining -= media_duration
            cursor += 1
        return playlist

    @staticmethod
    def _stage_reassembly_file(source: Path, target: Path) -> None:
        try:
            os.link(source, target)
        except OSError:
            shutil.copy2(source, target)

    @classmethod
    def _move_generated_output(cls, source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            source.replace(target)
        except OSError:
            try:
                shutil.copy2(source, target)
                source.unlink()
            except OSError as exception:
                cls._cleanup_failed_target(target)
                raise FfmpegError(f"FFmpeg 输出文件移动失败：{exception}") from exception

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

    def _transcode_with_effects_command(
        self,
        source: Path,
        target: Path,
        *,
        trim_head_seconds: float,
        trim_tail_seconds: float,
        speed_factor: float,
        swap_orientation: bool,
        bgm_files: list[Path],
        bgm_volume_percent: float,
        audio_pitch_semitones: float,
        border_percent: float,
        mirror_horizontal: bool,
        rotate_degrees: float,
    ) -> list[str]:
        source_duration = self.video_duration_seconds(source)
        if source_duration is None:
            raise FfmpegError(f"无法读取转码源视频时长：{source}")
        start_seconds = min(max(trim_head_seconds, 0.0), source_duration)
        end_seconds = max(start_seconds, source_duration - max(trim_tail_seconds, 0.0))
        usable_duration = end_seconds - start_seconds
        if usable_duration <= 0:
            raise FfmpegError(f"转码后无可用视频时长：{source}")
        output_duration = usable_duration / max(speed_factor, 0.01)
        playlist = self._loop_bgm_files_for_duration(bgm_files, output_duration)
        command = [self.ffmpeg_path, "-y", "-i", str(source)]
        for bgm_file in playlist:
            command.extend(["-i", str(bgm_file)])
        frame_filter = self._reassembly_frame_filter(
            source,
            swap_orientation,
            border_percent=border_percent,
            mirror_horizontal=mirror_horizontal,
            rotate_degrees=rotate_degrees,
        )
        speed = max(speed_factor, 0.01)
        formatted_speed = self._format_filter_number(speed)
        filters = [
            f"[0:v]trim=start={self._format_seconds(start_seconds)}:end={self._format_seconds(end_seconds)},"
            f"setpts=PTS-STARTPTS,setpts=(PTS-STARTPTS)/{formatted_speed},{frame_filter}[outv]"
        ]
        if self.has_audio_stream(source):
            audio_filter = (
                f"[0:a]atrim=start={self._format_seconds(start_seconds)}:end={self._format_seconds(end_seconds)},"
                "asetpts=PTS-STARTPTS,"
                "aresample=async=1:first_pts=0,"
                "aformat=sample_rates=48000:channel_layouts=stereo"
            )
            if self._has_effective_speed_change(speed):
                audio_filter += f",{self._atempo_filter(speed)}"
            audio_filter += f",apad,atrim=duration={self._format_seconds(output_duration)},asetpts=PTS-STARTPTS[maina]"
            filters.append(audio_filter)
        else:
            filters.append(
                "anullsrc=r=48000:cl=stereo,"
                f"atrim=duration={self._format_seconds(output_duration)},asetpts=PTS-STARTPTS[maina]"
            )
        audio_output_label = "maina"
        if playlist and bgm_volume_percent > 0:
            bgm_inputs: list[str] = []
            for bgm_index, _bgm_file in enumerate(playlist):
                input_index = 1 + bgm_index
                filters.append(
                    f"[{input_index}:a]asetpts=PTS-STARTPTS,"
                    "aresample=async=1:first_pts=0,"
                    "aformat=sample_rates=48000:channel_layouts=stereo"
                    f"[bgm{bgm_index}]"
                )
                bgm_inputs.append(f"[bgm{bgm_index}]")
            filters.append("".join(bgm_inputs) + f"concat=n={len(bgm_inputs)}:v=0:a=1[bgmcat]")
            filters.append(
                f"[bgmcat]atrim=duration={self._format_seconds(output_duration)},"
                "asetpts=PTS-STARTPTS,"
                f"volume={self._format_filter_number(max(0.0, bgm_volume_percent / 100.0))}[bgmmix]"
            )
            filters.append("[maina][bgmmix]amix=inputs=2:duration=first:dropout_transition=0[mixeda]")
            audio_output_label = "mixeda"
        pitch_filter = self._pitch_shift_filter(audio_pitch_semitones)
        if pitch_filter:
            filters.append(f"[{audio_output_label}]{pitch_filter}[outa]")
        else:
            filters.append(f"[{audio_output_label}]anull[outa]")
        command.extend(
            [
                "-filter_complex",
                ";".join(filters),
                "-map",
                "[outv]",
                "-map",
                "[outa]",
                *self._wechat_video_output_args(),
                str(target),
            ]
        )
        return command

    def _reassembly_timeline_command(
        self,
        clips: list[VideoReassemblySourceClip],
        timeline: Path,
        *,
        speed_factor: float,
        swap_orientation: bool,
        bgm_files: list[Path] | None = None,
        bgm_volume_percent: float = 0.0,
        audio_pitch_semitones: float = 0.0,
        border_percent: float = 0.0,
        mirror_horizontal: bool = False,
        rotate_degrees: float = 0.0,
        drop_audio: bool = False,
    ) -> list[str]:
        command = [self.ffmpeg_path, "-y"]
        for clip in clips:
            command.extend(["-i", str(clip.path)])
        for bgm_file in bgm_files or []:
            command.extend(["-i", str(bgm_file)])
        filter_complex = self._reassembly_filter_complex(
            clips,
            speed_factor=speed_factor,
            swap_orientation=swap_orientation,
            bgm_files=bgm_files or [],
            bgm_volume_percent=bgm_volume_percent,
            audio_pitch_semitones=audio_pitch_semitones,
            border_percent=border_percent,
            mirror_horizontal=mirror_horizontal,
            rotate_degrees=rotate_degrees,
            drop_audio=drop_audio,
        )
        command.extend(["-filter_complex", filter_complex, "-map", "[outv]"])
        if not drop_audio:
            command.extend(["-map", "[outa]"])
        if drop_audio:
            command.append("-an")
        command.extend([*self._wechat_video_output_args(include_audio=not drop_audio), str(timeline)])
        return command

    def _reassembly_filter_complex(
        self,
        clips: list[VideoReassemblySourceClip],
        *,
        speed_factor: float,
        swap_orientation: bool,
        bgm_files: list[Path],
        bgm_volume_percent: float,
        audio_pitch_semitones: float,
        border_percent: float,
        mirror_horizontal: bool,
        rotate_degrees: float,
        drop_audio: bool,
    ) -> str:
        filters: list[str] = []
        concat_inputs: list[str] = []
        frame_filter = self._reassembly_frame_filter(
            clips[0].path,
            swap_orientation,
            border_percent=border_percent,
            mirror_horizontal=mirror_horizontal,
            rotate_degrees=rotate_degrees,
        )
        speed = max(speed_factor, 0.01)
        formatted_speed = self._format_filter_number(speed)
        total_output_duration = sum(clip.duration_seconds / speed for clip in clips)
        for input_index, clip in enumerate(clips):
            start = self._format_seconds(clip.start_seconds)
            duration = self._format_seconds(clip.duration_seconds)
            output_duration = self._format_seconds(clip.duration_seconds / speed)
            filters.append(
                f"[{input_index}:v]setpts=PTS-STARTPTS,"
                f"trim=start={start}:duration={duration},"
                f"setpts=(PTS-STARTPTS)/{formatted_speed},"
                f"{frame_filter}[v{input_index}]"
            )
            if drop_audio:
                concat_inputs.append(f"[v{input_index}]")
                continue
            if self.has_audio_stream(clip.path):
                audio_filter = (
                    f"[{input_index}:a]asetpts=PTS-STARTPTS,"
                    f"atrim=start={start}:duration={duration},"
                    "asetpts=PTS-STARTPTS,"
                    "aresample=async=1:first_pts=0,"
                    "aformat=sample_rates=48000:channel_layouts=stereo"
                )
                if self._has_effective_speed_change(speed):
                    audio_filter += f",{self._atempo_filter(speed)}"
                audio_filter += (
                    f",apad,atrim=duration={output_duration},"
                    f"asetpts=PTS-STARTPTS[a{input_index}]"
                )
                filters.append(audio_filter)
            else:
                filters.append(
                    "anullsrc=r=48000:cl=stereo,"
                    f"atrim=duration={output_duration},"
                    f"asetpts=PTS-STARTPTS[a{input_index}]"
                )
            concat_inputs.append(f"[v{input_index}][a{input_index}]")
        if drop_audio:
            concat_filter = "".join(concat_inputs)
            concat_filter += f"concat=n={len(clips)}:v=1:a=0[outv]"
            return ";".join([*filters, concat_filter])
        concat_filter = "".join(concat_inputs)
        concat_filter += f"concat=n={len(clips)}:v=1:a=1[outv][maina]"
        filters.append(concat_filter)
        audio_output_label = "maina"
        if bgm_files and bgm_volume_percent > 0:
            bgm_inputs: list[str] = []
            for bgm_index, _bgm_file in enumerate(bgm_files):
                input_index = len(clips) + bgm_index
                filters.append(
                    f"[{input_index}:a]asetpts=PTS-STARTPTS,"
                    "aresample=async=1:first_pts=0,"
                    "aformat=sample_rates=48000:channel_layouts=stereo"
                    f"[bgm{bgm_index}]"
                )
                bgm_inputs.append(f"[bgm{bgm_index}]")
            filters.append("".join(bgm_inputs) + f"concat=n={len(bgm_inputs)}:v=0:a=1[bgmcat]")
            filters.append(
                f"[bgmcat]atrim=duration={self._format_seconds(total_output_duration)},"
                "asetpts=PTS-STARTPTS,"
                f"volume={self._format_filter_number(max(0.0, bgm_volume_percent / 100.0))}[bgmmix]"
            )
            filters.append(
                "[maina][bgmmix]amix=inputs=2:duration=first:dropout_transition=0[mixeda]"
            )
            audio_output_label = "mixeda"
        pitch_filter = self._pitch_shift_filter(audio_pitch_semitones)
        if pitch_filter:
            filters.append(f"[{audio_output_label}]{pitch_filter}[outa]")
        else:
            filters.append(f"[{audio_output_label}]anull[outa]")
        return ";".join(filters)

    def _reassembly_segment_command(
        self,
        timeline: Path,
        segment: VideoReassemblySegment,
        *,
        cover_path: Path | None = None,
    ) -> list[str]:
        if cover_path and cover_path.exists():
            dimensions = self.video_dimensions(timeline)
            if not dimensions:
                raise FfmpegError(f"无法读取重组时间线尺寸，不能嵌入封面帧：{timeline}")
            width, height = dimensions
            filter_complex = (
                "[0:v]setpts=PTS-STARTPTS[mainv];"
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
                "-ss",
                self._format_seconds(segment.start_seconds),
                "-t",
                self._format_seconds(segment.duration_seconds),
                "-i",
                str(timeline),
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
                str(segment.target),
            ]
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

    def _reassembly_frame_filter(
        self,
        first_source: Path,
        swap_orientation: bool,
        *,
        border_percent: float = 0.0,
        mirror_horizontal: bool = False,
        rotate_degrees: float = 0.0,
    ) -> str:
        filters: list[str] = []
        target_width: int | None = None
        target_height: int | None = None
        dimensions = self.video_dimensions(first_source)
        if dimensions:
            width, height = dimensions
            if swap_orientation:
                target_width = height
                target_height = width
                filters.extend(self._wechat_video_frame_filters(height, width))
            elif self._is_below_wechat_video_minimum(width, height):
                target_width, target_height = minimum_wechat_video_dimensions(width, height)
                filters.extend(self._wechat_video_frame_filters(target_width, target_height))
            else:
                target_width = width
                target_height = height
        if filters and filters[-1] == "format=yuv420p":
            filters.pop()
        if mirror_horizontal:
            filters.append("hflip")
        if rotate_degrees:
            filters.append(
                f"rotate={self._format_filter_number(rotate_degrees)}*PI/180:fillcolor=black"
            )
        if border_percent > 0:
            inset_ratio = max(0.0, min(0.45, border_percent / 100.0))
            scale_ratio = max(0.1, 1.0 - inset_ratio * 2.0)
            filters.append(
                "scale="
                f"trunc(iw*{self._format_filter_number(scale_ratio)}/2)*2:"
                f"trunc(ih*{self._format_filter_number(scale_ratio)}/2)*2"
            )
            if target_width and target_height:
                filters.append(f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:color=black")
        if not filters or filters[-1] != "setsar=1":
            filters.append("setsar=1")
        filters.extend([f"fps={WECHAT_VIDEO_TARGET_FPS}", "format=yuv420p"])
        return ",".join(filters)

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
            return minimum_wechat_video_dimensions(width, height)
        return width, height

    @staticmethod
    def _wechat_video_frame_filter(width: int, height: int) -> str:
        return ",".join(FfmpegProcessor._wechat_video_frame_filters(width, height))

    @staticmethod
    def _wechat_video_frame_filters(width: int, height: int) -> list[str]:
        return [
            f"scale={width}:{height}:force_original_aspect_ratio=decrease",
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black",
            "setsar=1",
            "format=yuv420p",
        ]

    @classmethod
    def _concat_file_content(cls, sources: list[Path]) -> str:
        lines = [f"file '{cls._escape_concat_file_path(source)}'" for source in sources]
        return "\n".join(lines) + "\n"

    @staticmethod
    def _escape_concat_file_path(source: Path) -> str:
        return str(source.resolve()).replace("\\", "\\\\").replace("'", "\\'")

    @staticmethod
    def _wechat_video_output_args(include_audio: bool = True) -> list[str]:
        args = [
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
        ]
        if include_audio:
            args.extend(
                [
                    "-c:a",
                    "aac",
                    "-b:a",
                    "128k",
                ]
            )
        args.extend(
            [
                "-pix_fmt:v:0",
                "yuv420p",
                "-movflags",
                "+faststart",
            ]
        )
        return args

    def needs_wechat_video_bitrate_transcode(
        self,
        source: Path,
        min_bitrate_bps: int = WECHAT_VIDEO_MIN_BITRATE_BPS,
    ) -> bool:
        bitrate = self.video_bitrate_bps(source)
        return bitrate is None or bitrate < min_bitrate_bps

    def needs_wechat_video_resolution_transcode(
        self,
        source: Path,
        min_width: int = WECHAT_VIDEO_MIN_WIDTH,
        min_height: int = WECHAT_VIDEO_MIN_HEIGHT,
    ) -> bool:
        dimensions = self.video_dimensions(source)
        if not dimensions:
            return True
        width, height = dimensions
        required_width, required_height = minimum_wechat_video_dimensions(width, height)
        return width < required_width or height < required_height

    def needs_wechat_video_transcode(self, source: Path) -> bool:
        return self.needs_wechat_video_bitrate_transcode(source) or self.needs_wechat_video_resolution_transcode(source)

    @staticmethod
    def _is_below_wechat_video_minimum(width: int, height: int) -> bool:
        min_width, min_height = minimum_wechat_video_dimensions(width, height)
        return width < min_width or height < min_height

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
            result = subprocess.run(command, check=True, capture_output=True, text=True, **hidden_subprocess_kwargs())
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
            result = subprocess.run(command, check=True, capture_output=True, text=True, **hidden_subprocess_kwargs())
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
            "-select_streams",
            "v:0",
            "-show_entries",
            "format=duration:stream=duration",
            "-of",
            "json",
            str(source),
        ]
        try:
            result = subprocess.run(command, check=True, capture_output=True, text=True, **hidden_subprocess_kwargs())
            payload = json.loads(result.stdout or "{}")
        except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
            return None
        return self._duration_from_probe_payload(payload)

    def media_duration_seconds(self, source: Path) -> float | None:
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
            result = subprocess.run(command, check=True, capture_output=True, text=True, **hidden_subprocess_kwargs())
            payload = json.loads(result.stdout or "{}")
        except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
            return None
        return self._duration_from_probe_payload(payload)

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
            result = subprocess.run(command, check=True, capture_output=True, text=True, **hidden_subprocess_kwargs())
            payload = json.loads(result.stdout or "{}")
        except (OSError, subprocess.CalledProcessError, json.JSONDecodeError):
            return False
        return bool(payload.get("streams"))

    def ensure_ffprobe_available(self) -> None:
        try:
            subprocess.run(
                [self.ffprobe_path(), "-version"],
                check=True,
                capture_output=True,
                text=True,
                **hidden_subprocess_kwargs(),
            )
        except FileNotFoundError as exception:
            fallback_path = find_ffmpeg_fallback_path(exclude=self.ffmpeg_path)
            if fallback_path:
                self.ffmpeg_path = fallback_path
                try:
                    subprocess.run(
                        [self.ffprobe_path(), "-version"],
                        check=True,
                        capture_output=True,
                        text=True,
                        **hidden_subprocess_kwargs(),
                    )
                    return
                except FileNotFoundError:
                    pass
                except subprocess.CalledProcessError as fallback_exception:
                    detail = self._process_output_tail(fallback_exception.stdout, fallback_exception.stderr)
                    raise FfmpegError(f"FFprobe 无法运行：{detail}") from fallback_exception
                except OSError as fallback_exception:
                    raise FfmpegError(f"FFprobe 无法启动：{fallback_exception}") from fallback_exception
            raise FfmpegError(
                f"找不到 FFprobe 可执行文件：{self.ffprobe_path()}。"
                "请安装 FFmpeg/FFprobe，或把 AIDRAMA_FFMPEG_PATH 配置为 ffmpeg 的绝对路径。"
            ) from exception
        except subprocess.CalledProcessError as exception:
            detail = self._process_output_tail(exception.stdout, exception.stderr)
            raise FfmpegError(f"FFprobe 无法运行：{detail}") from exception
        except OSError as exception:
            raise FfmpegError(f"FFprobe 无法启动：{exception}") from exception

    def ffprobe_path(self) -> str:
        return ffprobe_path_for_ffmpeg(self.ffmpeg_path)

    def _ffmpeg_fallback_command(self, command: list[str]) -> list[str] | None:
        if not command:
            return None
        configured_path = normalize_executable_path(command[0])
        fallback_path = find_ffmpeg_fallback_path(exclude=configured_path)
        if not fallback_path:
            return None
        return [fallback_path, *command[1:]]

    @classmethod
    def _format_ffmpeg_missing_message(
        cls,
        command: list[str],
        exception: FileNotFoundError,
        fallback_command: list[str] | None = None,
    ) -> str:
        configured_path = normalize_executable_path(command[0] if command else "")
        resolved_path = find_existing_ffmpeg_path(configured_path, require_ffprobe=False) if configured_path else None
        binary_path = resolved_path or configured_path
        sections = [f"找不到 FFmpeg 可执行文件：{configured_path or 'ffmpeg'}。"]
        if binary_path and cls._looks_like_executable_path(binary_path):
            ffmpeg_exists = Path(binary_path).is_file()
            ffprobe_path = ffprobe_path_for_ffmpeg(binary_path)
            ffprobe_exists = Path(ffprobe_path).is_file()
            sections.append(f"FFmpeg 文件存在：{'是' if ffmpeg_exists else '否'}")
            sections.append(f"同目录 FFprobe 存在：{'是' if ffprobe_exists else '否'}")
            if resolved_path and resolved_path != configured_path:
                sections.append(f"自动识别后的 FFmpeg 路径：{resolved_path}")
            if ffmpeg_exists:
                sections.append(
                    "补充提示：如果 ffmpeg 可执行文件明确存在但仍报 FileNotFoundError，在 Windows 上通常是同目录 DLL 缺失、文件被安全软件隔离，或压缩包未完整解压。"
                )
        sections.append(f"系统错误：{exception}")
        if fallback_command:
            sections.append(f"兜底尝试：{fallback_command[0]}")
        else:
            sections.append("已尝试 PATH 和常见安装目录兜底，仍未找到可用的 FFmpeg/FFprobe。")
        return "\n".join(sections)

    @staticmethod
    def _looks_like_executable_path(value: str) -> bool:
        return value.startswith(("~", ".", "..")) or "/" in value or "\\" in value or (len(value) >= 2 and value[1] == ":")

    @staticmethod
    def _bitrate_from_probe_payload(payload: dict) -> int | None:
        for stream in payload.get("streams") or []:
            bitrate = FfmpegProcessor._positive_int(stream.get("bit_rate"))
            if bitrate:
                return bitrate
        return FfmpegProcessor._positive_int((payload.get("format") or {}).get("bit_rate"))

    @staticmethod
    def _duration_from_probe_payload(payload: dict) -> float | None:
        duration = FfmpegProcessor._positive_float((payload.get("format") or {}).get("duration"))
        if duration:
            return duration
        for stream in payload.get("streams") or []:
            duration = FfmpegProcessor._positive_float(stream.get("duration"))
            if duration:
                return duration
        return None

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

    @classmethod
    def _pitch_shift_filter(cls, semitones: float) -> str:
        if -0.001 < semitones < 0.001:
            return ""
        pitch_factor = max(0.25, min(4.0, 2 ** (semitones / 12.0)))
        preserve_tempo = cls._atempo_filter(1.0 / pitch_factor)
        filters = [
            f"asetrate=48000*{cls._format_filter_number(pitch_factor)}",
            "aresample=48000",
        ]
        if preserve_tempo:
            filters.append(preserve_tempo)
        return ",".join(filters)

    @staticmethod
    def _process_output_tail(stdout: str | None, stderr: str | None, max_lines: int = 8, max_chars: int = 1000) -> str:
        text = "\n".join(part for part in (stderr, stdout) if part)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return "没有返回错误详情"
        tail = "\n".join(lines[-max_lines:])
        return tail[-max_chars:]

    @staticmethod
    def _format_process_returncode(returncode: int) -> str:
        if returncode > 0x7FFFFFFF:
            signed = returncode - 0x100000000
            return f"{signed}（Windows 原始码 {returncode}）"
        return str(returncode)

    @staticmethod
    def _command_summary(command: list[str], max_chars: int = 1000) -> str:
        text = " ".join(shlex.quote(part) for part in command)
        if len(text) <= max_chars:
            return text
        return f"{text[: max_chars - 3]}..."

    @staticmethod
    def _command_text(command: list[str]) -> str:
        return " ".join(shlex.quote(part) for part in command)

    @classmethod
    def _format_ffmpeg_failure_message(
        cls,
        command: list[str],
        returncode: int,
        stdout: str | None,
        stderr: str | None,
        target: Path,
    ) -> str:
        detail = cls._process_output_tail(stdout, stderr)
        sections = [
            f"FFmpeg 转码退出码 {cls._format_process_returncode(returncode)}：{detail}",
            f"目标文件：{target}",
            f"FFmpeg 命令：{cls._command_text(command)}",
            "FFmpeg stderr：",
            (stderr or "").strip() or "（空）",
            "FFmpeg stdout：",
            (stdout or "").strip() or "（空）",
        ]
        return "\n".join(sections)

    @staticmethod
    def _is_reassembly_audio_decode_error(exception: Exception) -> bool:
        message = str(exception).lower()
        if "[aac" not in message:
            return False
        markers = (
            "number of bands",
            "channel element",
            "invalid band type",
            "predictor reset group",
            "pulse tool not allowed",
            "reserved bit set",
        )
        return any(marker in message for marker in markers)

    @staticmethod
    def _cleanup_failed_target(target: Path) -> None:
        try:
            if target.exists():
                target.unlink()
        except OSError:
            pass
