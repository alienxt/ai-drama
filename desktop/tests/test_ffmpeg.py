import json
import subprocess
from pathlib import Path

import pytest

from aidrama_desktop.video.ffmpeg import (
    FfmpegError,
    FfmpegProcessor,
    VideoReassemblySegment,
    VideoReassemblySourceClip,
)
from aidrama_desktop import subprocess_utils


def test_hidden_subprocess_kwargs_are_empty_off_windows(monkeypatch):
    monkeypatch.setattr(subprocess_utils.os, "name", "posix", raising=False)

    assert subprocess_utils.hidden_subprocess_kwargs() == {}


def test_hidden_subprocess_kwargs_hide_windows_console(monkeypatch):
    class StartupInfo:
        def __init__(self):
            self.dwFlags = 0
            self.wShowWindow = None

    monkeypatch.setattr(subprocess_utils.os, "name", "nt", raising=False)
    monkeypatch.setattr(subprocess_utils.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(subprocess_utils.subprocess, "STARTUPINFO", StartupInfo, raising=False)
    monkeypatch.setattr(subprocess_utils.subprocess, "STARTF_USESHOWWINDOW", 1, raising=False)
    monkeypatch.setattr(subprocess_utils.subprocess, "SW_HIDE", 0, raising=False)

    kwargs = subprocess_utils.hidden_subprocess_kwargs()

    assert kwargs["creationflags"] == 0x08000000
    assert kwargs["startupinfo"].dwFlags == 1
    assert kwargs["startupinfo"].wShowWindow == 0


def test_ffmpeg_processor_reads_video_bitrate(monkeypatch, tmp_path):
    source = tmp_path / "video.mp4"
    source.write_text("video")

    def fake_run(command, check=False, capture_output=False, text=False):
        assert command[0] == "ffprobe"
        assert str(source) in command
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"streams": [{"bit_rate": "3500000"}], "format": {"bit_rate": "3600000"}}),
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    processor = FfmpegProcessor("ffmpeg")

    assert processor.video_bitrate_bps(source) == 3_500_000
    assert processor.needs_wechat_video_bitrate_transcode(source) is True


def test_ffmpeg_processor_uses_sibling_ffprobe_for_absolute_ffmpeg():
    processor = FfmpegProcessor("/opt/homebrew/bin/ffmpeg")

    assert processor.ffprobe_path() == "/opt/homebrew/bin/ffprobe"


def test_ffmpeg_processor_falls_back_to_format_bitrate(monkeypatch, tmp_path):
    source = tmp_path / "video.mp4"
    source.write_text("video")

    def fake_run(command, check=False, capture_output=False, text=False):
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"format": {"bit_rate": "4500000"}}))

    monkeypatch.setattr("subprocess.run", fake_run)

    processor = FfmpegProcessor("ffmpeg")

    assert processor.video_bitrate_bps(source) == 4_500_000
    assert processor.needs_wechat_video_bitrate_transcode(source) is False


def test_ffmpeg_processor_transcodes_unreadable_bitrate(monkeypatch, tmp_path):
    source = tmp_path / "video.mp4"
    source.write_text("video")

    def fake_run(command, check=False, capture_output=False, text=False):
        raise OSError("ffprobe missing")

    monkeypatch.setattr("subprocess.run", fake_run)

    processor = FfmpegProcessor("ffmpeg")

    assert processor.video_bitrate_bps(source) is None
    assert processor.needs_wechat_video_bitrate_transcode(source) is True


def test_ffmpeg_processor_detects_low_wechat_video_resolution(monkeypatch, tmp_path):
    source = tmp_path / "video.mp4"
    source.write_text("video")

    def fake_run(command, check=False, capture_output=False, text=False):
        if "stream=width,height" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"streams": [{"width": 540, "height": 960}]}),
            )
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"streams": [{"bit_rate": "4500000"}]}),
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    processor = FfmpegProcessor("ffmpeg")

    assert processor.video_dimensions(source) == (540, 960)
    assert processor.needs_wechat_video_resolution_transcode(source) is True
    assert processor.needs_wechat_video_transcode(source) is True


def test_ffmpeg_processor_keeps_compliant_wechat_video_resolution(monkeypatch, tmp_path):
    source = tmp_path / "video.mp4"
    source.write_text("video")

    def fake_run(command, check=False, capture_output=False, text=False):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"streams": [{"width": 720, "height": 1280}]}),
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    processor = FfmpegProcessor("ffmpeg")

    assert processor.needs_wechat_video_resolution_transcode(source) is False


def test_ffmpeg_processor_keeps_compliant_landscape_wechat_video_resolution(monkeypatch, tmp_path):
    source = tmp_path / "video.mp4"
    source.write_text("video")

    def fake_run(command, check=False, capture_output=False, text=False):
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"streams": [{"width": 1280, "height": 720}]}),
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    processor = FfmpegProcessor("ffmpeg")

    assert processor.needs_wechat_video_resolution_transcode(source) is False


def test_ffmpeg_processor_treats_unknown_resolution_as_needing_transcode(monkeypatch, tmp_path):
    source = tmp_path / "video.mp4"
    source.write_text("not-a-video")

    def fake_run(command, check=False, capture_output=False, text=False):
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"streams": []}))

    monkeypatch.setattr("subprocess.run", fake_run)

    processor = FfmpegProcessor("ffmpeg")

    assert processor.video_dimensions(source) is None
    assert processor.needs_wechat_video_resolution_transcode(source) is True


def test_ffmpeg_processor_reads_video_duration(monkeypatch, tmp_path):
    source = tmp_path / "video.mp4"
    source.write_text("video")

    def fake_run(command, check=False, capture_output=False, text=False):
        assert command[0] == "ffprobe"
        assert "format=duration:stream=duration" in command
        assert str(source) in command
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"format": {"duration": "29.42"}}))

    monkeypatch.setattr("subprocess.run", fake_run)

    processor = FfmpegProcessor("ffmpeg")

    assert processor.video_duration_seconds(source) == 29.42


def test_ffmpeg_processor_reads_stream_duration_when_format_duration_missing(monkeypatch, tmp_path):
    source = tmp_path / "video.mp4"
    source.write_text("video")

    def fake_run(command, check=False, capture_output=False, text=False):
        assert command[0] == "ffprobe"
        assert "format=duration:stream=duration" in command
        assert str(source) in command
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"streams": [{"duration": "31.25"}]}))

    monkeypatch.setattr("subprocess.run", fake_run)

    processor = FfmpegProcessor("ffmpeg")

    assert processor.video_duration_seconds(source) == 31.25


def test_ffmpeg_processor_reports_missing_ffprobe(monkeypatch):
    def fake_run(command, check=False, capture_output=False, text=False):
        raise FileNotFoundError(command[0])

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("aidrama_desktop.config.settings.shutil.which", lambda name: None)
    monkeypatch.setattr("aidrama_desktop.config.settings.COMMON_FFMPEG_PATHS", ())

    processor = FfmpegProcessor("/opt/ffmpeg/bin/ffmpeg")

    with pytest.raises(FfmpegError) as error:
        processor.ensure_ffprobe_available()

    assert "找不到 FFprobe 可执行文件：/opt/ffmpeg/bin/ffprobe" in str(error.value)
    assert "AIDRAMA_FFMPEG_PATH" in str(error.value)


def test_ffmpeg_processor_retries_missing_ffmpeg_with_path_fallback(monkeypatch, tmp_path):
    stale_ffmpeg = tmp_path / "missing" / "ffmpeg"
    fallback_bin = tmp_path / "fallback" / "bin"
    fallback_bin.mkdir(parents=True)
    fallback_ffmpeg = fallback_bin / "ffmpeg"
    fallback_ffprobe = fallback_bin / "ffprobe"
    fallback_ffmpeg.write_text("#!/bin/sh\n")
    fallback_ffprobe.write_text("#!/bin/sh\n")
    source = tmp_path / "source.mp4"
    target = tmp_path / "target.mp4"
    source.write_text("video")
    commands: list[list[str]] = []

    def fake_run(command, check=False, capture_output=False, text=False):
        commands.append(command)
        if command[0] in {str(stale_ffmpeg), str(stale_ffmpeg.with_name("ffprobe"))}:
            raise FileNotFoundError(command[0])
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr(
        "aidrama_desktop.config.settings.shutil.which",
        lambda name: str(fallback_ffmpeg) if name == "ffmpeg" else None,
    )
    monkeypatch.setattr("aidrama_desktop.config.settings.COMMON_FFMPEG_PATHS", ())

    processor = FfmpegProcessor(str(stale_ffmpeg))

    assert processor.transcode_for_wechat_video(source, target) == target
    stale_ffmpeg_index = next(index for index, command in enumerate(commands) if command[0] == str(stale_ffmpeg))
    fallback_ffmpeg_index = next(index for index, command in enumerate(commands) if command[0] == str(fallback_ffmpeg))
    assert stale_ffmpeg_index < fallback_ffmpeg_index
    assert processor.ffmpeg_path == str(fallback_ffmpeg)


def test_ffmpeg_processor_transcodes_low_resolution_to_wechat_video_minimum(monkeypatch, tmp_path):
    source = tmp_path / "video.mp4"
    target = tmp_path / "processed.mp4"
    source.write_text("video")
    commands = []

    def fake_run(command, check=False, capture_output=False, text=False):
        commands.append(command)
        if command[0] == "ffprobe":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"streams": [{"width": 540, "height": 960}]}),
            )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("subprocess.run", fake_run)

    processor = FfmpegProcessor("ffmpeg")

    assert processor.transcode_for_wechat_video(source, target) == target

    ffmpeg_command = commands[-1]
    assert "-vf" in ffmpeg_command
    video_filter = ffmpeg_command[ffmpeg_command.index("-vf") + 1]
    assert "scale=720:1280:force_original_aspect_ratio=decrease" in video_filter
    assert "pad=720:1280:(ow-iw)/2:(oh-ih)/2" in video_filter
    assert "setsar=1,format=yuv420p" in video_filter
    assert ffmpeg_command[-1] == str(target)


def test_ffmpeg_processor_transcodes_low_resolution_landscape_to_landscape_minimum(monkeypatch, tmp_path):
    source = tmp_path / "video.mp4"
    target = tmp_path / "processed.mp4"
    source.write_text("video")
    commands = []

    def fake_run(command, check=False, capture_output=False, text=False):
        commands.append(command)
        if command[0] == "ffprobe":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"streams": [{"width": 960, "height": 540}]}),
            )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("subprocess.run", fake_run)

    processor = FfmpegProcessor("ffmpeg")

    assert processor.transcode_for_wechat_video(source, target) == target

    ffmpeg_command = commands[-1]
    assert "-vf" in ffmpeg_command
    video_filter = ffmpeg_command[ffmpeg_command.index("-vf") + 1]
    assert "scale=1280:720:force_original_aspect_ratio=decrease" in video_filter
    assert "pad=1280:720:(ow-iw)/2:(oh-ih)/2" in video_filter
    assert ffmpeg_command[-1] == str(target)


def test_ffmpeg_processor_transcodes_with_cover_opening_second(monkeypatch, tmp_path):
    source = tmp_path / "video.mp4"
    target = tmp_path / "processed.mp4"
    cover = tmp_path / "fengmian.jpg"
    source.write_text("video")
    cover.write_text("cover")
    commands = []

    def fake_run(command, check=False, capture_output=False, text=False):
        commands.append(command)
        if command[0] == "ffprobe":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"streams": [{"width": 721, "height": 1281}]}),
            )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("subprocess.run", fake_run)

    processor = FfmpegProcessor("ffmpeg")

    assert processor.transcode_for_wechat_video(source, target, cover_path=cover) == target

    ffmpeg_command = commands[-1]
    assert ffmpeg_command[0] == "ffmpeg"
    assert str(source) in ffmpeg_command
    assert str(cover) in ffmpeg_command
    assert "-filter_complex" in ffmpeg_command
    assert ffmpeg_command[ffmpeg_command.index("-x264-params") + 1] == "nal-hrd=cbr:filler=1"
    filter_complex = ffmpeg_command[ffmpeg_command.index("-filter_complex") + 1]
    assert "scale=720:1280:force_original_aspect_ratio=decrease" in filter_complex
    assert "pad=720:1280:(ow-iw)/2:(oh-ih)/2" in filter_complex
    assert "boxblur=24:2" in filter_complex
    assert "force_original_aspect_ratio=decrease" in filter_complex
    assert "overlay=(W-w)/2:(H-h)/2" in filter_complex
    assert "split=2[coverv][picv]" in filter_complex
    assert "overlay=0:0:enable='lt(t,1)'" in filter_complex
    assert ffmpeg_command[ffmpeg_command.index("-map") + 1] == "[outv]"
    assert "0:a?" in ffmpeg_command
    assert "[picv]" in ffmpeg_command
    assert ffmpeg_command[ffmpeg_command.index("-c:v:1") + 1] == "mjpeg"
    assert ffmpeg_command[ffmpeg_command.index("-disposition:v:1") + 1] == "attached_pic"


def test_ffmpeg_processor_merges_tiktok_videos_with_concat_file(monkeypatch, tmp_path):
    source_1 = tmp_path / "001.mp4"
    source_2 = tmp_path / "002.mp4"
    target = tmp_path / "TK" / "merged.mp4"
    source_1.write_text("video-1")
    source_2.write_text("video-2")
    commands = []
    concat_files = []

    def fake_run(command, check=False, capture_output=False, text=False):
        commands.append(command)
        concat_path = Path(command[command.index("-i") + 1])
        concat_files.append(concat_path)
        content = concat_path.read_text(encoding="utf-8")
        assert f"file '{source_1}'" in content
        assert f"file '{source_2}'" in content
        target.write_text("merged")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("subprocess.run", fake_run)

    processor = FfmpegProcessor("ffmpeg")

    assert processor.merge_videos_for_tiktok([source_1, source_2], target) == target

    assert target.read_text() == "merged"
    ffmpeg_command = commands[-1]
    assert ffmpeg_command[:7] == ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i"]
    assert ffmpeg_command[-1] == str(target)
    assert ffmpeg_command[ffmpeg_command.index("-x264-params") + 1] == "nal-hrd=cbr:filler=1"
    assert not concat_files[0].exists()


def test_ffmpeg_processor_strategy1_resegments_whole_drama_without_orientation_conversion(monkeypatch, tmp_path):
    source_1 = tmp_path / "001.mp4"
    source_2 = tmp_path / "002.mp4"
    target_dir = tmp_path / "strategy1"
    source_1.write_text("video-1")
    source_2.write_text("video-2")
    commands = []

    def fake_run(command, check=False, capture_output=False, text=False):
        commands.append(command)
        if command[0] == "ffprobe":
            source = Path(command[-1])
            duration = "62.0" if source == source_1 else "63.0"
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"format": {"duration": duration}}))
        if "-f" in command and "segment" in command:
            pattern = Path(command[-1])
            pattern.parent.mkdir(parents=True, exist_ok=True)
            for index in range(2):
                Path(str(pattern).replace("%03d", f"{index:03d}")).write_text(f"segment-{index}")
            return subprocess.CompletedProcess(command, 0)
        Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
        Path(command[-1]).write_text("timeline")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("subprocess.run", fake_run)

    processor = FfmpegProcessor("ffmpeg")

    segments = processor.process_drama_with_strategy1(
        [source_1, source_2],
        target_dir,
        drama_title="神医归来",
        speed=1.0,
        segment_seconds=(60, 60),
    )

    assert [segment.file.name for segment in segments] == ["神医归来-策略1第001集.mp4", "神医归来-策略1第002集.mp4"]
    assert [segment.source_episode_indexes for segment in segments] == [(1,), (2,)]
    timeline_command = commands[-2]
    assert "-filter_complex" in timeline_command
    timeline_filter = timeline_command[timeline_command.index("-filter_complex") + 1]
    assert "trim=start=1:end=61" in timeline_filter
    assert "trim=start=1:end=62" in timeline_filter
    assert "concat=n=2:v=1:a=1" in timeline_filter
    assert "scale=" not in timeline_filter
    assert "pad=" not in timeline_filter
    split_command = commands[-1]
    assert split_command[split_command.index("-segment_times") + 1] == "60.000"


def test_ffmpeg_processor_strategy1_adds_silent_audio_for_sources_without_audio(monkeypatch, tmp_path):
    source = tmp_path / "001.mp4"
    target_dir = tmp_path / "strategy1"
    source.write_text("video")
    commands = []

    def fake_run(command, check=False, capture_output=False, text=False):
        commands.append(command)
        if command[0] == "ffprobe" and "format=duration:stream=duration" in command:
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"format": {"duration": "62.0"}}))
        if command[0] == "ffprobe" and ("stream=codec_type" in command or "stream=index" in command):
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"streams": []}))
        if "-f" in command and "segment" in command:
            pattern = Path(command[-1])
            pattern.parent.mkdir(parents=True, exist_ok=True)
            Path(str(pattern).replace("%03d", "000")).write_text("segment")
            return subprocess.CompletedProcess(command, 0)
        Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
        Path(command[-1]).write_text("timeline")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("subprocess.run", fake_run)

    processor = FfmpegProcessor("ffmpeg")

    processor.process_drama_with_strategy1([source], target_dir, drama_title="无声剧", speed=1.0)

    timeline_command = commands[-2]
    timeline_filter = timeline_command[timeline_command.index("-filter_complex") + 1]
    assert "anullsrc=r=48000:cl=stereo" in timeline_filter
    assert "[0:a]atrim" not in timeline_filter


def test_ffmpeg_processor_strategy1_forces_keyframes_at_segment_boundaries(monkeypatch, tmp_path):
    source_1 = tmp_path / "001.mp4"
    source_2 = tmp_path / "002.mp4"
    source_1.write_text("video-1")
    source_2.write_text("video-2")
    commands = []

    def fake_run(command, check=False, capture_output=False, text=False):
        commands.append(command)
        if command[0] == "ffprobe" and "format=duration:stream=duration" in command:
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"format": {"duration": "62.0"}}))
        if command[0] == "ffprobe" and ("stream=codec_type" in command or "stream=index" in command):
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"streams": [{"index": 0}]}))
        if "-f" in command and "segment" in command:
            pattern = Path(command[-1])
            pattern.parent.mkdir(parents=True, exist_ok=True)
            for index in range(2):
                Path(str(pattern).replace("%03d", f"{index:03d}")).write_text("segment")
            return subprocess.CompletedProcess(command, 0)
        Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
        Path(command[-1]).write_text("timeline")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("subprocess.run", fake_run)

    processor = FfmpegProcessor("ffmpeg")

    processor.process_drama_with_strategy1(
        [source_1, source_2],
        tmp_path / "strategy1",
        drama_title="神医归来",
        speed=1.0,
        segment_seconds=(60, 60),
    )

    timeline_command = commands[-2]
    assert timeline_command[timeline_command.index("-force_key_frames") + 1] == "60.000"


def test_ffmpeg_processor_reassembles_videos_with_trim_speed_and_segments(monkeypatch, tmp_path):
    source_1 = tmp_path / "001.mp4"
    source_2 = tmp_path / "002.mp4"
    timeline = tmp_path / "reassembled" / ".full.mp4"
    first_segment = tmp_path / "reassembled" / "001.mp4"
    second_segment = tmp_path / "reassembled" / "002.mp4"
    source_1.write_text("video-1")
    source_2.write_text("video-2")
    commands = []

    def fake_run(command, check=False, capture_output=False, text=False):
        if command[0] == "ffprobe":
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"streams": [{"index": 0}]}))
        commands.append(command)
        if Path(command[-1]).name == "timeline.mp4":
            Path(command[-1]).write_text("timeline")
        else:
            Path(command[-1]).write_text("segment")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("subprocess.run", fake_run)

    processor = FfmpegProcessor("ffmpeg")
    result = processor.reassemble_videos(
        [
            VideoReassemblySourceClip(source_1, 1.0, 60.0),
            VideoReassemblySourceClip(source_2, 1.0, 60.0),
        ],
        [
            VideoReassemblySegment(1, 0.0, 50.0, first_segment),
            VideoReassemblySegment(2, 50.0, 67.647, second_segment),
        ],
        timeline,
        speed_factor=1.02,
        swap_orientation=False,
    )

    assert result == [first_segment, second_segment]
    timeline_command = commands[0]
    assert timeline_command[:2] == ["ffmpeg", "-y"]
    assert timeline_command.count("-i") == 2
    assert Path(timeline_command[-1]).name == "timeline.mp4"
    filter_complex = timeline_command[timeline_command.index("-filter_complex") + 1]
    assert "[0:v]setpts=PTS-STARTPTS,trim=start=1:duration=60,setpts=(PTS-STARTPTS)/1.02" in filter_complex
    assert "setsar=1,fps=30,format=yuv420p[v0]" in filter_complex
    assert "[0:a]asetpts=PTS-STARTPTS,atrim=start=1:duration=60,asetpts=PTS-STARTPTS" in filter_complex
    assert "aresample=async=1:first_pts=0" in filter_complex
    assert "aformat=sample_rates=48000:channel_layouts=stereo,atempo=1.02" in filter_complex
    assert "apad,atrim=duration=58.824,asetpts=PTS-STARTPTS[a0]" in filter_complex
    assert "concat=n=2:v=1:a=1[outv][maina]" in filter_complex
    assert "[maina]anull[outa]" in filter_complex
    assert timeline_command[timeline_command.index("-map") + 1] == "[outv]"
    assert timeline_command[timeline_command.index("-map", timeline_command.index("-map") + 1) + 1] == "[outa]"
    assert commands[1][commands[1].index("-ss") + 1] == "0"
    assert Path(commands[1][-1]).name == "segment-001.mp4"
    assert commands[2][commands[2].index("-ss") + 1] == "50"
    assert commands[2][commands[2].index("-t") + 1] == "67.647"
    assert first_segment.read_text() == "segment"
    assert second_segment.read_text() == "segment"


def test_ffmpeg_processor_reassembly_retries_without_audio_on_bad_aac(monkeypatch, tmp_path):
    source = tmp_path / "001.mp4"
    timeline = tmp_path / "reassembled" / ".full.mp4"
    segment = tmp_path / "reassembled" / "001.mp4"
    source.write_text("video")
    commands = []
    timeline_attempts = 0

    def fake_run(command, check=False, capture_output=False, text=False):
        nonlocal timeline_attempts
        if command[0] == "ffprobe":
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"streams": [{"index": 0}]}))
        commands.append(command)
        if Path(command[-1]).name == "timeline.mp4":
            timeline_attempts += 1
            if timeline_attempts == 1:
                Path(command[-1]).write_text("partial")
                raise subprocess.CalledProcessError(
                    3221225477,
                    command,
                    output="",
                    stderr="[aac @ 000002d2b2d1b4c0] Number of bands (43) exceeds limit (38).",
                )
            Path(command[-1]).write_text("timeline")
        else:
            Path(command[-1]).write_text("segment")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("subprocess.run", fake_run)

    processor = FfmpegProcessor("ffmpeg")
    result = processor.reassemble_videos(
        [VideoReassemblySourceClip(source, 1.0, 60.0)],
        [VideoReassemblySegment(1, 0.0, 60.0, segment)],
        timeline,
        speed_factor=1.02,
    )

    timeline_commands = [
        command
        for command in commands
        if Path(command[-1]).name == "timeline.mp4"
    ]
    assert result == [segment]
    assert len(timeline_commands) == 2
    assert "[outa]" in timeline_commands[0][timeline_commands[0].index("-filter_complex") + 1]
    assert "-an" in timeline_commands[1]
    assert "[outa]" not in timeline_commands[1][timeline_commands[1].index("-filter_complex") + 1]
    assert segment.read_text() == "segment"


def test_ffmpeg_processor_reassembly_swaps_orientation_with_black_padding(monkeypatch, tmp_path):
    source = tmp_path / "001.mp4"
    timeline = tmp_path / "reassembled" / ".full.mp4"
    segment = tmp_path / "reassembled" / "001.mp4"
    source.write_text("video")
    commands = []

    def fake_run(command, check=False, capture_output=False, text=False):
        if command[0] == "ffprobe" and "stream=width,height" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"streams": [{"width": 720, "height": 1280}]}),
            )
        if command[0] == "ffprobe":
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"streams": [{"index": 0}]}))
        commands.append(command)
        Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
        Path(command[-1]).write_text("video")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("subprocess.run", fake_run)

    processor = FfmpegProcessor("ffmpeg")
    processor.reassemble_videos(
        [VideoReassemblySourceClip(source, 1.0, 60.0)],
        [VideoReassemblySegment(1, 0.0, 60.0, segment)],
        timeline,
        speed_factor=1.0,
        swap_orientation=True,
    )

    timeline_command = commands[0]
    filter_complex = timeline_command[timeline_command.index("-filter_complex") + 1]
    assert (
        "scale=1280:720:force_original_aspect_ratio=decrease,"
        "pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,"
        "setsar=1,fps=30,format=yuv420p"
    ) in filter_complex


def test_ffmpeg_processor_reassembly_effects_reset_sar_before_concat(monkeypatch, tmp_path):
    source = tmp_path / "001.mp4"
    timeline = tmp_path / "reassembled" / ".full.mp4"
    segment = tmp_path / "reassembled" / "001.mp4"
    source.write_text("video")
    commands = []

    def fake_run(command, check=False, capture_output=False, text=False):
        if command[0] == "ffprobe" and "stream=width,height" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"streams": [{"width": 1280, "height": 720}]}),
            )
        if command[0] == "ffprobe":
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"streams": [{"index": 0}]}))
        commands.append(command)
        Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
        Path(command[-1]).write_text("video")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("subprocess.run", fake_run)

    processor = FfmpegProcessor("ffmpeg")
    processor.reassemble_videos(
        [VideoReassemblySourceClip(source, 1.0, 60.0)],
        [VideoReassemblySegment(1, 0.0, 60.0, segment)],
        timeline,
        speed_factor=1.0,
        border_percent=1.0,
        rotate_degrees=0.4,
    )

    timeline_command = commands[0]
    filter_complex = timeline_command[timeline_command.index("-filter_complex") + 1]
    assert (
        "rotate=0.4*PI/180:fillcolor=black,"
        "scale=trunc(iw*0.98/2)*2:trunc(ih*0.98/2)*2,"
        "pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,"
        "setsar=1,fps=30,format=yuv420p"
    ) in filter_complex


def test_ffmpeg_processor_uses_filter_complex_script_for_long_reassembly(monkeypatch, tmp_path):
    source_1 = tmp_path / "001.mp4"
    source_2 = tmp_path / "002.mp4"
    timeline = tmp_path / "reassembled" / ".full.mp4"
    segment = tmp_path / "reassembled" / "001.mp4"
    source_1.write_text("video-1")
    source_2.write_text("video-2")
    timeline_commands = []
    script_paths = []

    def fake_run(command, check=False, capture_output=False, text=False):
        if command[0] == "ffprobe":
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"streams": [{"index": 0}]}))
        if Path(command[-1]).name == "timeline.mp4":
            timeline_commands.append(command)
            script_path = Path(command[command.index("-filter_complex_script") + 1])
            script_paths.append(script_path)
            assert script_path.exists()
            assert "concat=n=2:v=1:a=1[outv][maina]" in script_path.read_text(encoding="utf-8")
            Path(command[-1]).write_text("timeline")
        else:
            Path(command[-1]).write_text("segment")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("aidrama_desktop.video.ffmpeg.FFMPEG_FILTER_SCRIPT_MIN_CHARS", 20)

    processor = FfmpegProcessor("ffmpeg")
    processor.reassemble_videos(
        [
            VideoReassemblySourceClip(source_1, 1.0, 60.0),
            VideoReassemblySourceClip(source_2, 1.0, 60.0),
        ],
        [VideoReassemblySegment(1, 0.0, 60.0, segment)],
        timeline,
    )

    assert timeline_commands
    assert "-filter_complex" not in timeline_commands[0]
    assert "-filter_complex_script" in timeline_commands[0]
    assert all(not path.exists() for path in script_paths)


def test_ffmpeg_processor_logs_filter_complex_script_content_on_failure(monkeypatch, tmp_path):
    source = tmp_path / "001.mp4"
    timeline = tmp_path / "reassembled" / ".full.mp4"
    segment = tmp_path / "reassembled" / "001.mp4"
    source.write_text("video")

    def fake_run(command, check=False, capture_output=False, text=False):
        if command[0] == "ffprobe":
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"streams": [{"index": 0}]}))
        raise subprocess.CalledProcessError(
            1,
            command,
            output="",
            stderr="Conversion failed!",
        )

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("aidrama_desktop.video.ffmpeg.FFMPEG_FILTER_SCRIPT_MIN_CHARS", 20)

    processor = FfmpegProcessor("ffmpeg")

    with pytest.raises(FfmpegError) as error:
        processor.reassemble_videos(
            [VideoReassemblySourceClip(source, 1.0, 60.0)],
            [VideoReassemblySegment(1, 0.0, 60.0, segment)],
            timeline,
        )

    message = str(error.value)
    assert "FFmpeg filter_complex_script：" in message
    assert "FFmpeg filter_complex 内容：" in message
    assert "concat=n=1:v=1:a=1[outv][maina]" in message
    assert "Conversion failed!" in message


def test_ffmpeg_processor_labels_windows_long_command_error(monkeypatch, tmp_path):
    source = tmp_path / "001.mp4"
    timeline = tmp_path / "reassembled" / ".full.mp4"
    segment = tmp_path / "reassembled" / "001.mp4"
    source.write_text("video")

    def fake_run(command, check=False, capture_output=False, text=False):
        if command[0] == "ffprobe":
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"streams": [{"index": 0}]}))
        error = FileNotFoundError("[WinError 206] 文件名或扩展名太长。")
        error.winerror = 206
        raise error

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("aidrama_desktop.video.ffmpeg.FFMPEG_FILTER_SCRIPT_MIN_CHARS", 20)
    monkeypatch.setattr("aidrama_desktop.config.settings.shutil.which", lambda name: None)
    monkeypatch.setattr("aidrama_desktop.config.settings.COMMON_FFMPEG_PATHS", ())

    processor = FfmpegProcessor("ffmpeg")

    with pytest.raises(FfmpegError) as error:
        processor.reassemble_videos(
            [VideoReassemblySourceClip(source, 1.0, 60.0)],
            [VideoReassemblySegment(1, 0.0, 60.0, segment)],
            timeline,
        )

    message = str(error.value)
    assert "FFmpeg 启动失败：Windows 命令行过长（WinError 206）" in message
    assert "找不到 FFmpeg 可执行文件" not in message
    assert "FFmpeg filter_complex_script：" in message
    assert "FFmpeg filter_complex 内容：" in message


def test_ffmpeg_processor_reassembly_segments_include_cover_frame(monkeypatch, tmp_path):
    source = tmp_path / "001.mp4"
    cover = tmp_path / "fengmian.jpg"
    timeline = tmp_path / "reassembled" / ".full.mp4"
    segment = tmp_path / "reassembled" / "001.mp4"
    source.write_text("video")
    cover.write_text("cover")
    commands = []

    def fake_run(command, check=False, capture_output=False, text=False):
        if command[0] == "ffprobe" and "stream=width,height" in command:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"streams": [{"width": 1280, "height": 720}]}),
            )
        if command[0] == "ffprobe":
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"streams": [{"index": 0}]}))
        commands.append(command)
        Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
        Path(command[-1]).write_text("video")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("subprocess.run", fake_run)

    processor = FfmpegProcessor("ffmpeg")
    processor.reassemble_videos(
        [VideoReassemblySourceClip(source, 1.0, 60.0)],
        [VideoReassemblySegment(1, 0.0, 60.0, segment)],
        timeline,
        cover_path=cover,
    )

    segment_command = commands[1]
    assert Path(segment_command[segment_command.index("-i") + 1]).name == "timeline.mp4"
    assert any(Path(part).name == "cover.jpg" for part in segment_command)
    assert "-filter_complex" in segment_command
    assert "[mainv][coverv]overlay=0:0:enable='lt(t,1)'" in segment_command[segment_command.index("-filter_complex") + 1]
    assert "[picv]" in segment_command
    assert "attached_pic" in segment_command


def test_ffmpeg_processor_reports_transcode_stderr(monkeypatch, tmp_path):
    source = tmp_path / "video.mp4"
    target = tmp_path / "processed.mp4"
    source.write_text("video")

    def fake_run(command, check=False, capture_output=False, text=False):
        assert capture_output is True
        assert text is True
        Path(command[-1]).write_text("partial")
        raise subprocess.CalledProcessError(
            1,
            command,
            output="",
            stderr="Invalid data found when processing input\nConversion failed!",
        )

    monkeypatch.setattr("subprocess.run", fake_run)

    processor = FfmpegProcessor("ffmpeg")

    with pytest.raises(FfmpegError) as error:
        processor.transcode_for_wechat_video(source, target)

    message = str(error.value)
    assert "FFmpeg 转码退出码 1" in message
    assert "Conversion failed!" in message
    assert "FFmpeg 命令：" in message
    assert "FFmpeg stderr：" in message
    assert "Invalid data found when processing input" in message
    assert "FFmpeg stdout：" in message
    assert not target.exists()


def test_ffmpeg_processor_reports_windows_signed_returncode_without_stderr(monkeypatch, tmp_path):
    source = tmp_path / "video.mp4"
    target = tmp_path / "processed.mp4"
    source.write_text("video")

    def fake_run(command, check=False, capture_output=False, text=False):
        target.write_text("partial")
        raise subprocess.CalledProcessError(4294967274, command, output="", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)

    processor = FfmpegProcessor("ffmpeg")

    with pytest.raises(FfmpegError) as error:
        processor.transcode_for_wechat_video(source, target)

    message = str(error.value)
    assert "FFmpeg 转码退出码 -22（Windows 原始码 4294967274）" in message
    assert "没有返回错误详情" in message
    assert "目标文件：" in message
    assert "FFmpeg 命令：" in message
    assert "FFmpeg stderr：" in message
    assert "（空）" in message
    assert not target.exists()


def test_ffmpeg_processor_reports_existing_binary_when_launch_still_fails(monkeypatch, tmp_path):
    ffmpeg_bin = tmp_path / "ffmpeg" / "bin"
    ffmpeg_bin.mkdir(parents=True)
    configured_ffmpeg = ffmpeg_bin / "ffmpeg"
    configured_ffprobe = ffmpeg_bin / "ffprobe"
    configured_ffmpeg.write_text("#!/bin/sh\n")
    configured_ffprobe.write_text("#!/bin/sh\n")
    source = tmp_path / "video.mp4"
    target = tmp_path / "processed.mp4"
    source.write_text("video")

    def fake_run(command, check=False, capture_output=False, text=False):
        raise FileNotFoundError("missing runtime dependency")

    monkeypatch.setattr("subprocess.run", fake_run)
    monkeypatch.setattr("aidrama_desktop.config.settings.shutil.which", lambda name: None)
    monkeypatch.setattr("aidrama_desktop.config.settings.COMMON_FFMPEG_PATHS", ())

    processor = FfmpegProcessor(str(configured_ffmpeg))

    with pytest.raises(FfmpegError) as error:
        processor.transcode_for_wechat_video(source, target)

    message = str(error.value)
    assert f"找不到 FFmpeg 可执行文件：{configured_ffmpeg}" in message
    assert "FFmpeg 文件存在：是" in message
    assert "同目录 FFprobe 存在：是" in message
    assert "系统错误：missing runtime dependency" in message
    assert "DLL 缺失" in message
