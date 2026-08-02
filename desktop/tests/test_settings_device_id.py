from pathlib import Path

from aidrama_desktop.config.settings import Settings, load_settings, resolve_whisper_path, save_tool_path_config


def test_settings_default_device_id_uses_mac_address(monkeypatch):
    monkeypatch.delenv("AIDRAMA_DEVICE_ID", raising=False)
    monkeypatch.setattr("aidrama_desktop.config.settings.uuid.getnode", lambda: 0xA1B2C3D4E5F6)

    settings = Settings()

    assert settings.device_id == "mac-a1-b2-c3-d4-e5-f6"


def test_settings_device_id_can_be_overridden_by_env(monkeypatch):
    monkeypatch.setenv("AIDRAMA_DEVICE_ID", "manual-device")

    settings = Settings()

    assert settings.device_id == "manual-device"


def test_settings_download_concurrency_can_be_overridden_by_env(monkeypatch):
    monkeypatch.setenv("AIDRAMA_DOWNLOAD_CONCURRENCY", "8")

    settings = Settings()

    assert settings.download_concurrency == 8


def test_load_settings_creates_planned_directories(monkeypatch, tmp_path):
    monkeypatch.setenv("AIDRAMA_WORK_DIR", str(tmp_path / "data" / "work"))
    monkeypatch.setenv("AIDRAMA_TOKEN_FILE", str(tmp_path / "config" / "token"))
    monkeypatch.setenv("AIDRAMA_BROWSER_PROFILE_DIR", str(tmp_path / "data" / "browser-profiles"))

    settings = load_settings()

    assert settings.config_dir == tmp_path / "config"
    assert settings.remembered_login_file == tmp_path / "config" / "remembered-login.json"
    assert settings.dramas_dir == tmp_path / "data" / "work" / "dramas"
    assert settings.downloads_dir == tmp_path / "data" / "work" / "dramas" / "downloads"
    assert settings.processed_dir == tmp_path / "data" / "work" / "dramas" / "processed"
    assert settings.contracts_dir == tmp_path / "data" / "work" / "contracts"
    assert settings.temp_dir == tmp_path / "data" / "work" / "tmp"

    for directory in [
        settings.config_dir,
        settings.dramas_dir,
        settings.downloads_dir,
        settings.processed_dir,
        settings.contracts_dir,
        settings.temp_dir,
        settings.browser_profile_dir,
    ]:
        assert directory.exists()


def test_load_settings_auto_resolves_ffmpeg_with_ffprobe(monkeypatch, tmp_path):
    fake_bin = tmp_path / "homebrew" / "bin"
    fake_bin.mkdir(parents=True)
    ffmpeg = fake_bin / "ffmpeg"
    ffprobe = fake_bin / "ffprobe"
    ffmpeg.write_text("#!/bin/sh\n")
    ffprobe.write_text("#!/bin/sh\n")
    monkeypatch.delenv("AIDRAMA_FFMPEG_PATH", raising=False)
    monkeypatch.setenv("AIDRAMA_WORK_DIR", str(tmp_path / "data" / "work"))
    monkeypatch.setenv("AIDRAMA_TOKEN_FILE", str(tmp_path / "config" / "token"))
    monkeypatch.setenv("AIDRAMA_BROWSER_PROFILE_DIR", str(tmp_path / "data" / "browser-profiles"))
    monkeypatch.setattr("aidrama_desktop.config.settings.shutil.which", lambda name: None)
    monkeypatch.setattr("aidrama_desktop.config.settings.COMMON_FFMPEG_PATHS", (str(ffmpeg),))

    settings = load_settings()

    assert settings.ffmpeg_path == str(ffmpeg)


def test_load_settings_keeps_valid_explicit_ffmpeg_path(monkeypatch, tmp_path):
    custom_bin = tmp_path / "custom" / "bin"
    custom_bin.mkdir(parents=True)
    ffmpeg = custom_bin / "ffmpeg"
    ffprobe = custom_bin / "ffprobe"
    ffmpeg.write_text("#!/bin/sh\n")
    ffprobe.write_text("#!/bin/sh\n")
    monkeypatch.setenv("AIDRAMA_FFMPEG_PATH", str(ffmpeg))
    monkeypatch.setenv("AIDRAMA_WORK_DIR", str(tmp_path / "data" / "work"))
    monkeypatch.setenv("AIDRAMA_TOKEN_FILE", str(tmp_path / "config" / "token"))
    monkeypatch.setenv("AIDRAMA_BROWSER_PROFILE_DIR", str(tmp_path / "data" / "browser-profiles"))

    settings = load_settings()

    assert settings.ffmpeg_path == str(ffmpeg)


def test_load_settings_falls_back_when_explicit_ffmpeg_path_is_missing(monkeypatch, tmp_path):
    fallback_bin = tmp_path / "fallback" / "bin"
    fallback_bin.mkdir(parents=True)
    ffmpeg = fallback_bin / "ffmpeg"
    ffprobe = fallback_bin / "ffprobe"
    ffmpeg.write_text("#!/bin/sh\n")
    ffprobe.write_text("#!/bin/sh\n")
    monkeypatch.setenv("AIDRAMA_FFMPEG_PATH", str(tmp_path / "missing" / "ffmpeg"))
    monkeypatch.setenv("AIDRAMA_WORK_DIR", str(tmp_path / "data" / "work"))
    monkeypatch.setenv("AIDRAMA_TOKEN_FILE", str(tmp_path / "config" / "token"))
    monkeypatch.setenv("AIDRAMA_BROWSER_PROFILE_DIR", str(tmp_path / "data" / "browser-profiles"))
    monkeypatch.setattr("aidrama_desktop.config.settings.shutil.which", lambda name: str(ffmpeg) if name == "ffmpeg" else None)
    monkeypatch.setattr("aidrama_desktop.config.settings.COMMON_FFMPEG_PATHS", ())

    settings = load_settings()

    assert settings.ffmpeg_path == str(ffmpeg)


def test_load_settings_uses_saved_whisper_path_over_environment(monkeypatch, tmp_path):
    saved_whisper = tmp_path / "tools" / "whisper"
    saved_node = tmp_path / "tools" / "node"
    draft_root = tmp_path / "jianying" / "drafts"
    music_dir = tmp_path / "music"
    saved_whisper.parent.mkdir(parents=True)
    saved_whisper.write_text("#!/bin/sh\n")
    saved_node.write_text("#!/bin/sh\n")
    draft_root.mkdir(parents=True)
    music_dir.mkdir()
    config_dir = tmp_path / "config"
    save_tool_path_config(
        config_dir,
        whisper_path=str(saved_whisper),
        node_path=str(saved_node),
        jianying_draft_root=str(draft_root),
        jianying_music_dir=str(music_dir),
    )
    monkeypatch.setenv("AIDRAMA_WHISPER_PATH", str(tmp_path / "old" / "whisper"))
    monkeypatch.setenv("JIANYING_DRAFT_ROOT", str(tmp_path / "old" / "drafts"))
    monkeypatch.setenv("AIDRAMA_JIANYING_MUSIC_DIR", str(tmp_path / "old" / "music"))
    monkeypatch.setenv("AIDRAMA_WORK_DIR", str(tmp_path / "data" / "work"))
    monkeypatch.setenv("AIDRAMA_TOKEN_FILE", str(config_dir / "token"))
    monkeypatch.setenv("AIDRAMA_BROWSER_PROFILE_DIR", str(tmp_path / "data" / "browser-profiles"))

    settings = load_settings()

    assert settings.whisper_path == str(saved_whisper)
    assert settings.node_path == str(saved_node)
    assert settings.jianying_draft_root == draft_root
    assert settings.jianying_music_dir == music_dir


def test_resolve_whisper_path_detects_user_python_install(monkeypatch, tmp_path):
    user_whisper = tmp_path / "Library" / "Python" / "3.9" / "bin" / "whisper"
    user_whisper.parent.mkdir(parents=True)
    user_whisper.write_text("#!/bin/sh\n")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("aidrama_desktop.config.settings.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "aidrama_desktop.config.settings.COMMON_WHISPER_PATHS",
        (Path("~/Library/Python/3.9/bin/whisper"),),
    )

    assert resolve_whisper_path() == str(user_whisper)


def test_load_settings_persists_generated_device_id(monkeypatch, tmp_path):
    monkeypatch.delenv("AIDRAMA_DEVICE_ID", raising=False)
    monkeypatch.setenv("AIDRAMA_WORK_DIR", str(tmp_path / "data" / "work"))
    monkeypatch.setenv("AIDRAMA_TOKEN_FILE", str(tmp_path / "config" / "token"))
    monkeypatch.setenv("AIDRAMA_BROWSER_PROFILE_DIR", str(tmp_path / "data" / "browser-profiles"))
    mac_addresses = iter([0xA1B2C3D4E5F6, 0x102030405060])
    monkeypatch.setattr("aidrama_desktop.config.settings.uuid.getnode", lambda: next(mac_addresses))

    first = load_settings()
    second = load_settings()

    assert first.device_id == "mac-a1-b2-c3-d4-e5-f6"
    assert second.device_id == first.device_id
    assert (tmp_path / "config" / "device-id").read_text() == first.device_id
