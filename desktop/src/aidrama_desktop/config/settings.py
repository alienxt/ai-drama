from __future__ import annotations

import os
import uuid
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

API_BASE_URL = "https://ad.ai-drama.uk/api"


def default_device_id() -> str:
    mac = uuid.getnode()
    octets = [f"{(mac >> shift) & 0xFF:02x}" for shift in range(40, -1, -8)]
    return "mac-" + "-".join(octets)


class Settings(BaseSettings):
    server_url: str = Field(default=API_BASE_URL)
    device_id: str = Field(default_factory=default_device_id)
    chrome_path: str | None = None
    ffmpeg_path: str = "ffmpeg"
    soffice_path: str = "soffice"
    local_agent_port: int = 17888
    download_concurrency: int = 6
    work_dir: Path = Field(default_factory=lambda: Path(user_data_dir("ai-drama-desktop")) / "work")
    browser_profile_dir: Path = Field(
        default_factory=lambda: Path(user_data_dir("ai-drama-desktop")) / "chrome-profiles"
    )
    token_file: Path = Field(
        default_factory=lambda: Path(user_config_dir("ai-drama-desktop")) / "token"
    )

    model_config = SettingsConfigDict(env_prefix="AIDRAMA_", env_file=".env", extra="ignore")

    @property
    def config_dir(self) -> Path:
        return self.token_file.parent

    @property
    def remembered_login_file(self) -> Path:
        return self.config_dir / "remembered-login.json"

    @property
    def device_id_file(self) -> Path:
        return self.config_dir / "device-id"

    @property
    def dramas_dir(self) -> Path:
        return self.work_dir / "dramas"

    @property
    def downloads_dir(self) -> Path:
        return self.dramas_dir / "downloads"

    @property
    def processed_dir(self) -> Path:
        return self.dramas_dir / "processed"

    @property
    def temp_dir(self) -> Path:
        return self.work_dir / "tmp"

    @property
    def updates_dir(self) -> Path:
        return self.work_dir / "updates"

    @property
    def contracts_dir(self) -> Path:
        return self.work_dir / "contracts"


def load_settings() -> Settings:
    settings = Settings()
    settings.work_dir.mkdir(parents=True, exist_ok=True)
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    if "AIDRAMA_DEVICE_ID" not in os.environ:
        if settings.device_id_file.exists():
            stored_device_id = settings.device_id_file.read_text(encoding="utf-8").strip()
            if stored_device_id:
                settings.device_id = stored_device_id
        else:
            settings.device_id_file.write_text(settings.device_id, encoding="utf-8")
    settings.dramas_dir.mkdir(parents=True, exist_ok=True)
    settings.downloads_dir.mkdir(parents=True, exist_ok=True)
    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    settings.temp_dir.mkdir(parents=True, exist_ok=True)
    settings.updates_dir.mkdir(parents=True, exist_ok=True)
    settings.contracts_dir.mkdir(parents=True, exist_ok=True)
    settings.browser_profile_dir.mkdir(parents=True, exist_ok=True)
    return settings
