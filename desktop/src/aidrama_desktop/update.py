from __future__ import annotations

import os
import platform as platform_module
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence
from urllib.parse import urljoin, urlparse

import httpx


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    release_notes: str | None
    mandatory: bool
    file_name: str | None
    file_size: int
    download_url: str

    @classmethod
    def from_api(cls, data: dict) -> "UpdateInfo | None":
        if not data.get("updateAvailable"):
            return None
        download_url = str(data.get("downloadUrl") or "")
        if not download_url:
            return None
        return cls(
            version=str(data.get("version") or ""),
            release_notes=data.get("releaseNotes"),
            mandatory=bool(data.get("mandatory")),
            file_name=data.get("fileName"),
            file_size=int(data.get("fileSize") or 0),
            download_url=download_url,
        )


def detect_platform(system_name: str | None = None) -> str | None:
    system = system_name or platform_module.system()
    if system == "Darwin":
        return "MAC"
    if system == "Windows":
        return "WINDOWS"
    return None


def installer_file_name(update: UpdateInfo) -> str:
    if update.file_name:
        return Path(update.file_name).name
    parsed = urlparse(update.download_url)
    return Path(parsed.path).name or f"ai-drama-desktop-{update.version}"


def download_installer(
    update: UpdateInfo,
    target_dir: Path,
    base_url: str,
    headers: Mapping[str, str] | None = None,
) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / installer_file_name(update)
    url = resolve_download_url(update.download_url, base_url)
    with httpx.Client(timeout=300) as client:
        stream_kwargs = {"headers": dict(headers)} if headers else {}
        with client.stream("GET", url, **stream_kwargs) as response:
            response.raise_for_status()
            with target.open("wb") as output:
                for chunk in response.iter_bytes():
                    output.write(chunk)
    return target


def resolve_download_url(download_url: str, base_url: str) -> str:
    if download_url.startswith("http://") or download_url.startswith("https://"):
        return download_url
    server_root = base_url.rstrip("/")
    if server_root.endswith("/api"):
        server_root = server_root[:-4]
    return urljoin(server_root + "/", download_url.lstrip("/"))


def open_installer(
    path: Path,
    platform: str,
    opener: Callable[[Sequence[str]], object] | None = None,
) -> None:
    if platform == "MAC":
        command = ["open", str(path)]
        if opener:
            opener(command)
        else:
            subprocess.Popen(command)
        return
    if platform == "WINDOWS":
        if opener:
            opener([str(path)])
        else:
            os.startfile(path)  # type: ignore[attr-defined]
        return
    raise ValueError(f"Unsupported desktop platform: {platform}")
