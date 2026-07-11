import json
import subprocess
from pathlib import Path

import pytest

from aidrama_desktop.video.ffmpeg import FfmpegError, FfmpegProcessor


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
                stdout=json.dumps({"streams": [{"width": 1281, "height": 721}]}),
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
    assert "scale=1280:720" in filter_complex
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
