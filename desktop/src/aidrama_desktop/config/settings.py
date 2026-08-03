from __future__ import annotations

import os
import json
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
COMMON_WHISPER_PATHS = (
    Path("~/Library/Python/3.13/bin/whisper"),
    Path("~/Library/Python/3.12/bin/whisper"),
    Path("~/Library/Python/3.11/bin/whisper"),
    Path("~/Library/Python/3.10/bin/whisper"),
    Path("~/Library/Python/3.9/bin/whisper"),
    Path("~/.local/bin/whisper"),
    Path("~/.venvs/whisper/bin/whisper"),
    Path("~/.pyenv/shims/whisper"),
    Path("/opt/homebrew/opt/pyenv/shims/whisper"),
    Path("/opt/homebrew/bin/whisper"),
    Path("/usr/local/bin/whisper"),
)
TOOL_PATHS_CONFIG_FILENAME = "tool-paths.json"


def default_device_id() -> str:
    mac = uuid.getnode()
    octets = [f"{(mac >> shift) & 0xFF:02x}" for shift in range(40, -1, -8)]
    return "mac-" + "-".join(octets)


def ffprobe_path_for_ffmpeg(ffmpeg_path: str) -> str:
    ffmpeg = Path(normalize_executable_path(ffmpeg_path))
    name_lower = ffmpeg.name.lower()
    if name_lower in {"ffmpeg", "ffmpeg.exe"}:
        ffprobe_name = "ffprobe.exe" if name_lower.endswith(".exe") else "ffprobe"
        return str(ffmpeg.with_name(ffprobe_name)) if ffmpeg.parent != Path(".") else ffprobe_name
    if name_lower.startswith("ffmpeg"):
        return str(ffmpeg.with_name(ffmpeg.name.replace("ffmpeg", "ffprobe", 1)))
    return "ffprobe"


def normalize_executable_path(executable_path: str | None, *, default: str = "ffmpeg") -> str:
    value = str(executable_path or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    return value or default


def normalize_optional_executable_path(executable_path: str | None) -> str | None:
    value = str(executable_path or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    return value or None


def _looks_like_filesystem_path(value: str) -> bool:
    return value.startswith(("~", ".", "..")) or "/" in value or "\\" in value or (len(value) >= 2 and value[1] == ":")


def _ffmpeg_executable_name() -> str:
    return "ffmpeg.exe" if os.name == "nt" else "ffmpeg"


def ffmpeg_path_candidates(ffmpeg_path: str | None, *, default: str = "ffmpeg") -> list[str]:
    value = normalize_executable_path(ffmpeg_path, default=default)
    candidates: list[str] = []
    seen: set[str] = set()

    def add(candidate: str) -> None:
        normalized = normalize_executable_path(candidate, default=default)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        candidates.append(normalized)

    add(value)
    if not _looks_like_filesystem_path(value):
        return candidates
    base_path = Path(value).expanduser()
    lower_name = base_path.name.lower()
    is_named_ffmpeg = lower_name in {"ffmpeg", "ffmpeg.exe"}
    if base_path.is_dir() or (not is_named_ffmpeg and base_path.suffix == ""):
        add(str(base_path / _ffmpeg_executable_name()))
        add(str(base_path / "bin" / _ffmpeg_executable_name()))
    return candidates


def find_existing_ffmpeg_path(ffmpeg_path: str | None, *, require_ffprobe: bool = False) -> str | None:
    for candidate in ffmpeg_path_candidates(ffmpeg_path):
        candidate_path = Path(candidate).expanduser()
        if not candidate_path.is_file():
            continue
        if require_ffprobe and not Path(ffprobe_path_for_ffmpeg(str(candidate_path))).is_file():
            continue
        return str(candidate_path)
    return None


def ffmpeg_path_is_usable(ffmpeg_path: str) -> bool:
    return find_existing_ffmpeg_path(ffmpeg_path, require_ffprobe=True) is not None


def find_ffmpeg_fallback_path(*, exclude: str | None = None) -> str | None:
    excluded = normalize_executable_path(exclude) if exclude else None
    candidates = [path for path in (shutil.which("ffmpeg"), *COMMON_FFMPEG_PATHS) if path]
    seen: set[str] = set()
    for candidate in candidates:
        for normalized in ffmpeg_path_candidates(candidate):
            if normalized in seen or normalized == excluded:
                continue
            seen.add(normalized)
            usable = find_existing_ffmpeg_path(normalized, require_ffprobe=True)
            if usable:
                return usable
    return None


def resolve_ffmpeg_path(ffmpeg_path: str) -> str:
    requested_candidates = ffmpeg_path_candidates(ffmpeg_path)
    for candidate in requested_candidates:
        usable = find_existing_ffmpeg_path(candidate, require_ffprobe=True)
        if usable:
            return usable
    requested = requested_candidates[0] if requested_candidates else normalize_executable_path(ffmpeg_path)
    fallback = find_ffmpeg_fallback_path(exclude=requested)
    if fallback:
        return fallback
    existing = find_existing_ffmpeg_path(requested, require_ffprobe=False)
    return existing or requested


def resolve_whisper_path(whisper_path: str | None = None) -> str | None:
    candidates = [
        normalize_optional_executable_path(whisper_path),
        shutil.which("whisper"),
        *COMMON_WHISPER_PATHS,
        "whisper",
    ]
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate:
            continue
        candidate_path = Path(str(candidate)).expanduser()
        normalized = str(candidate_path)
        if normalized in seen:
            continue
        seen.add(normalized)
        if candidate_path.is_file():
            return normalized
        resolved = shutil.which(str(candidate))
        if resolved:
            return resolved
    return normalize_optional_executable_path(whisper_path)


def load_tool_path_config(config_dir: Path) -> dict[str, str]:
    path = config_dir / TOOL_PATHS_CONFIG_FILENAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    result: dict[str, str] = {}
    key_map = {
        "ffmpegPath": "ffmpeg_path",
        "whisperPath": "whisper_path",
        "nodePath": "node_path",
        "jianyingDraftRoot": "jianying_draft_root",
        "jianyingApp": "jianying_app",
        "jianyingMusicDir": "jianying_music_dir",
    }
    for raw_key, settings_key in key_map.items():
        value = normalize_optional_executable_path(data.get(raw_key))
        if value:
            result[settings_key] = value
    return result


def save_tool_path_config(
    config_dir: Path,
    *,
    ffmpeg_path: str | None = None,
    whisper_path: str | None,
    node_path: str | None = None,
    jianying_draft_root: str | None = None,
    jianying_app: str | None = None,
    jianying_music_dir: str | None = None,
) -> None:
    path = config_dir / TOOL_PATHS_CONFIG_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ffmpegPath": normalize_optional_executable_path(ffmpeg_path) or "",
        "whisperPath": normalize_optional_executable_path(whisper_path) or "",
        "nodePath": normalize_optional_executable_path(node_path) or "",
        "jianyingDraftRoot": normalize_optional_executable_path(jianying_draft_root) or "",
        "jianyingApp": normalize_optional_executable_path(jianying_app) or "",
        "jianyingMusicDir": normalize_optional_executable_path(jianying_music_dir) or "",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class Settings(BaseSettings):
    server_url: str = Field(default=API_BASE_URL)
    device_id: str = Field(default_factory=default_device_id)
    chrome_path: str | None = None
    ffmpeg_path: str = "ffmpeg"
    whisper_path: str | None = None
    node_path: str | None = None
    jianying_draft_root: Path | None = None
    jianying_app: Path | None = None
    jianying_music_dir: Path | None = None
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

    @property
    def tool_paths_file(self) -> Path:
        return self.config_dir / TOOL_PATHS_CONFIG_FILENAME


def load_settings() -> Settings:
    settings = Settings()
    settings.work_dir.mkdir(parents=True, exist_ok=True)
    settings.config_dir.mkdir(parents=True, exist_ok=True)
    tool_path_config = load_tool_path_config(settings.config_dir)
    if tool_path_config.get("ffmpeg_path"):
        settings.ffmpeg_path = tool_path_config["ffmpeg_path"]
    settings.ffmpeg_path = resolve_ffmpeg_path(settings.ffmpeg_path)
    if tool_path_config.get("whisper_path"):
        settings.whisper_path = tool_path_config["whisper_path"]
    if tool_path_config.get("node_path"):
        settings.node_path = tool_path_config["node_path"]
    if tool_path_config.get("jianying_draft_root"):
        settings.jianying_draft_root = Path(tool_path_config["jianying_draft_root"]).expanduser()
    elif os.environ.get("JIANYING_DRAFT_ROOT"):
        settings.jianying_draft_root = Path(str(os.environ["JIANYING_DRAFT_ROOT"])).expanduser()
    if tool_path_config.get("jianying_app"):
        settings.jianying_app = Path(tool_path_config["jianying_app"]).expanduser()
    elif os.environ.get("JIANYING_APP"):
        settings.jianying_app = Path(str(os.environ["JIANYING_APP"])).expanduser()
    if tool_path_config.get("jianying_music_dir"):
        settings.jianying_music_dir = Path(tool_path_config["jianying_music_dir"]).expanduser()
    elif os.environ.get("AIDRAMA_JIANYING_MUSIC_DIR"):
        settings.jianying_music_dir = Path(str(os.environ["AIDRAMA_JIANYING_MUSIC_DIR"])).expanduser()
    settings.whisper_path = resolve_whisper_path(settings.whisper_path or os.environ.get("AIDRAMA_WHISPER_PATH"))
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
