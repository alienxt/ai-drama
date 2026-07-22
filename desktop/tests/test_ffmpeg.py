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


def test_ffmpeg_processor_ignores_unreadable_bitrate(monkeypatch, tmp_path):
    source = tmp_path / "video.mp4"
    source.write_text("video")

    def fake_run(command, check=False, capture_output=False, text=False):
        raise OSError("ffprobe missing")

    monkeypatch.setattr("subprocess.run", fake_run)

    processor = FfmpegProcessor("ffmpeg")

    assert processor.video_bitrate_bps(source) is None
    assert processor.needs_wechat_video_bitrate_transcode(source) is False


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


def test_ffmpeg_processor_reads_video_duration(monkeypatch, tmp_path):
    source = tmp_path / "video.mp4"
    source.write_text("video")

    def fake_run(command, check=False, capture_output=False, text=False):
        assert command[0] == "ffprobe"
        assert "format=duration" in command
        assert str(source) in command
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"format": {"duration": "29.42"}}))

    monkeypatch.setattr("subprocess.run", fake_run)

    processor = FfmpegProcessor("ffmpeg")

    assert processor.video_duration_seconds(source) == 29.42


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
        if command[0] == "ffprobe" and "format=duration" in command:
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
        if command[0] == "ffprobe" and "format=duration" in command:
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
    concat_files = []

    def fake_run(command, check=False, capture_output=False, text=False):
        if command[0] == "ffprobe":
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps({"streams": [{"index": 0}]}))
        commands.append(command)
        if "-f" in command and command[command.index("-f") + 1] == "concat":
            concat_path = Path(command[command.index("-i") + 1])
            concat_files.append(concat_path)
            content = concat_path.read_text(encoding="utf-8")
            assert f"file '{source_1}'" in content
            assert "inpoint 1" in content
            assert "outpoint 61" in content
            timeline.write_text("timeline")
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
    assert timeline_command[:7] == ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i"]
    assert timeline_command[timeline_command.index("-vf") + 1] == "setpts=PTS/1.02"
    assert timeline_command[timeline_command.index("-af") + 1] == "atempo=1.02"
    assert commands[1][commands[1].index("-ss") + 1] == "0"
    assert commands[2][commands[2].index("-ss") + 1] == "50"
    assert commands[2][commands[2].index("-t") + 1] == "67.647"
    assert not concat_files[0].exists()


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
    assert timeline_command[timeline_command.index("-vf") + 1] == (
        "scale=1280:720:force_original_aspect_ratio=decrease,"
        "pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black,"
        "setsar=1,format=yuv420p"
    )


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

    assert "FFmpeg 转码退出码 1" in str(error.value)
    assert "Conversion failed!" in str(error.value)
    assert not target.exists()
