from pathlib import Path

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
