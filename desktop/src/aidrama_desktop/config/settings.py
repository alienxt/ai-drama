from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path

from platformdirs import user_config_dir, user_data_dir
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

API_BASE_URL = "http://ai-drama-admin-1807108618.ap-southeast-1.elb.amazonaws.com/api"
COMMON_FFMPEG_PATHS = (
    "/opt/homebrew/bin/ffmpeg",
    "/usr/local/bin/ffmpeg",
    "/usr/bin/ffmpeg",
    r"C:\ffmpeg\bin\ffmpeg.exe",
    r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
)


def default_device_id() -> str:
    mac = uuid.getnode()
    octets = [f"{(mac >> shift) & 0xFF:02x}" for shift in range(40, -1, -8)]
    return "mac-" + "-".join(octets)


def ffprobe_path_for_ffmpeg(ffmpeg_path: str) -> str:
    ffmpeg = Path(ffmpeg_path)
    name_lower = ffmpeg.name.lower()
    if name_lower in {"ffmpeg", "ffmpeg.exe"}:
        ffprobe_name = "ffprobe.exe" if name_lower.endswith(".exe") else "ffprobe"
        return str(ffmpeg.with_name(ffprobe_name)) if ffmpeg.parent != Path(".") else ffprobe_name
    if name_lower.startswith("ffmpeg"):
        return str(ffmpeg.with_name(ffmpeg.name.replace("ffmpeg", "ffprobe", 1)))
    return "ffprobe"


def resolve_ffmpeg_path(ffmpeg_path: str) -> str:
    if ffmpeg_path != "ffmpeg":
        return ffmpeg_path
    candidates = [path for path in (shutil.which("ffmpeg"), *COMMON_FFMPEG_PATHS) if path]
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if Path(candidate).is_file() and Path(ffprobe_path_for_ffmpeg(candidate)).is_file():
            return candidate
    return ffmpeg_path


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
    settings.ffmpeg_path = resolve_ffmpeg_path(settings.ffmpeg_path)
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
