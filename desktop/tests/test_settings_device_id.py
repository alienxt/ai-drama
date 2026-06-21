from aidrama_desktop.config.settings import Settings, load_settings


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
