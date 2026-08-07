import subprocess
from pathlib import Path

from aidrama_desktop.config.settings import SUBTITLE_PROVIDER_OPENAI_WHISPER
from aidrama_desktop.subtitles.faster_whisper import (
    COMMON_FASTER_WHISPER_PYTHON_PATHS,
    FasterWhisperSrtGenerator,
)
from aidrama_desktop.subtitles.generator import SubtitleSrtGenerator
from aidrama_desktop.subtitles.whisper import COMMON_WHISPER_PATHS, WhisperSrtGenerator


def test_whisper_generator_resolves_common_venv_path(monkeypatch, tmp_path):
    venv_whisper = tmp_path / ".venvs" / "whisper" / "bin" / "whisper"
    venv_whisper.parent.mkdir(parents=True)
    venv_whisper.write_text("#!/bin/sh\n")
    monkeypatch.delenv("AIDRAMA_WHISPER_PATH", raising=False)
    monkeypatch.setattr("aidrama_desktop.config.settings.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "aidrama_desktop.config.settings.COMMON_WHISPER_PATHS",
        (Path("~/.venvs/whisper/bin/whisper"),),
    )
    monkeypatch.setenv("HOME", str(tmp_path))

    assert WhisperSrtGenerator()._resolve_command_path() == str(venv_whisper)


def test_common_whisper_paths_include_user_venv():
    assert Path("~/.venvs/whisper/bin/whisper") in COMMON_WHISPER_PATHS
    assert Path("~/Library/Python/3.9/bin/whisper") in COMMON_WHISPER_PATHS


def test_common_faster_whisper_paths_include_ai_drama_venv():
    assert Path("~/AI-Drama/faster-whisper-venv/bin/python") in COMMON_FASTER_WHISPER_PYTHON_PATHS
    assert Path(r"C:\AI-Drama\faster-whisper-venv\Scripts\python.exe") in COMMON_FASTER_WHISPER_PYTHON_PATHS


def test_faster_whisper_generator_runs_external_python(monkeypatch, tmp_path):
    python = tmp_path / "python"
    video = tmp_path / "video.mp4"
    target = tmp_path / "subtitle.srt"
    python.write_text("#!/bin/sh\n")
    video.write_bytes(b"video")
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        generated = Path(command[command.index("--target") + 1])
        generated.write_text("1\n00:00:00,000 --> 00:00:01,000\n测试字幕\n", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("aidrama_desktop.subtitles.faster_whisper.subprocess.run", fake_run)

    result = FasterWhisperSrtGenerator(python_path=str(python)).generate_srt(video, target)

    assert result.created is True
    assert result.provider == "fasterWhisper"
    assert target.read_text(encoding="utf-8").startswith("1\n")
    assert commands[0][0] == str(python)
    assert commands[0][commands[0].index("--model") + 1] == "base"
    assert commands[0][commands[0].index("--compute-type") + 1] == "int8"


def test_subtitle_generator_uses_openai_whisper_when_selected(monkeypatch, tmp_path):
    video = tmp_path / "video.mp4"
    target = tmp_path / "subtitle.srt"
    video.write_bytes(b"video")
    calls = []

    class FakeWhisper:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def generate_srt(self, video_path, target_path):
            target_path.write_text("srt", encoding="utf-8")
            return type(
                "Result",
                (),
                {"srt_path": target_path, "created": True, "provider": "openaiWhisper"},
            )()

    monkeypatch.setattr("aidrama_desktop.subtitles.generator.WhisperSrtGenerator", FakeWhisper)

    result = SubtitleSrtGenerator(
        provider=SUBTITLE_PROVIDER_OPENAI_WHISPER,
        whisper_path="whisper",
        ffmpeg_path="ffmpeg",
    ).generate_srt(video, target)

    assert result.provider == "openaiWhisper"
    assert calls == [{"command_path": "whisper", "ffmpeg_path": "ffmpeg"}]
