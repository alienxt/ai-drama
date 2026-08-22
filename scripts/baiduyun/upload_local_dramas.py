#!/usr/bin/env python3
"""Upload locally downloaded drama folders to Baidu Netdisk scan layout."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import posixpath
import re
import sys
import tempfile
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DEFAULT_CONFIG_PATH = REPO_ROOT / "admin" / "server" / "docs" / "baiduyun" / "baidu_pan_cli_config.json"
DEFAULT_REMOTE_ROOT = "/drama/真人剧/2026"
TOKEN_URL = "https://openapi.baidu.com/oauth/2.0/token"
XPAN_FILE_URL = "https://pan.baidu.com/rest/2.0/xpan/file"
PCS_UPLOAD_URL = "https://d.pcs.baidu.com/rest/2.0/pcs/superfile2"
DEFAULT_USER_AGENT = "pan.baidu.com"
DEFAULT_REFERER = "https://pan.baidu.com/"
DEFAULT_TIMEOUT_SECONDS = 180
DEFAULT_UPLOAD_RETRIES = 6
CHUNK_SIZE = 4 * 1024 * 1024
SLICE_MD5_SIZE = 256 * 1024
MARKER_NAME = ".baidu-uploaded.json"
OAUTH_REDIRECT_URI = "oob"
OAUTH_SCOPE = "basic,netdisk"
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
INFO_NAMES = ("视频信息.txt", "简介.txt", "summary.txt", "intro.txt", "视频信息.md", "简介.md", "summary.md", "intro.md")
DOWNLOAD_TEMP_EXTENSIONS = {".tmp", ".temp", ".part", ".crdownload", ".download", ".downloading", ".aria2"}
FIELD_RE = re.compile(r"^\s*([^:：]{1,16})\s*[:：]\s*(.*?)\s*$")
EPISODE_PATTERNS = (
    re.compile(r"^.*第\s*0*(\d+)\s*集.*\.(mp4|mov|m4v|mkv)$", re.IGNORECASE),
    re.compile(r"^0*(\d+)(?:\s*集)?.*\.(mp4|mov|m4v|mkv)$", re.IGNORECASE),
    re.compile(r"^(?:ep|episode)\s*0*(\d+).*\.(mp4|mov|m4v|mkv)$", re.IGNORECASE),
)
STOP_SUMMARY_HEADERS = {"演员信息", "演员", "饰演", "演员简介", "角色信息", "角色", "制作信息"}


class UploadError(RuntimeError):
    """Raised when local planning or Baidu upload fails."""


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message: str, *, error: bool = False) -> None:
    print(f"[{now_text()}] {message}", file=sys.stderr if error else sys.stdout)


def format_duration(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remaining = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m{remaining:.1f}s"
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours)}h{int(minutes)}m{remaining:.1f}s"


def format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f}{unit}" if unit != "B" else f"{int(value)}B"
        value /= 1024
    return f"{size}B"


def format_speed(size: int, seconds: float) -> str:
    if seconds <= 0:
        return "n/a"
    return f"{format_size(int(size / seconds))}/s"


@dataclass(frozen=True)
class EpisodeFile:
    episode_no: int
    path: Path
    remote_name: str


@dataclass(frozen=True)
class LocalDramaPlan:
    local_dir: Path
    title: str
    author: str
    category: str
    episode_count: int
    total_minutes: str
    summary: str
    info_path: Path | None
    cover_path: Path | None
    cover_remote_name: str | None
    episodes: list[EpisodeFile]
    remote_dir: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "localDir": str(self.local_dir),
            "title": self.title,
            "author": self.author,
            "category": self.category,
            "episodeCount": self.episode_count,
            "totalMinutes": self.total_minutes,
            "summaryChars": len(self.summary),
            "infoPath": str(self.info_path) if self.info_path else None,
            "coverPath": str(self.cover_path) if self.cover_path else None,
            "coverRemoteName": self.cover_remote_name,
            "episodeFiles": len(self.episodes),
            "remoteDir": self.remote_dir,
        }


@dataclass(frozen=True)
class DownloadReadiness:
    ready: bool
    reason: str
    expected_count: int
    actual_count: int
    missing: list[int]
    used_info_count: bool


def load_config(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path).expanduser()
    if not path.exists():
        raise UploadError(f"Config not found: {path}")
    config = json.loads(path.read_text(encoding="utf-8"))
    config["config_path"] = str(path)
    return config


def save_config(config: dict[str, Any]) -> None:
    path = Path(config.get("config_path", DEFAULT_CONFIG_PATH)).expanduser()
    payload = dict(config)
    payload.pop("config_path", None)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def token_is_expired(config: dict[str, Any], now: float | None = None) -> bool:
    now = time.time() if now is None else now
    obtained_at = float(config.get("token_obtained_at", 0))
    expires_in = int(config.get("expires_in", 0))
    return now >= obtained_at + max(expires_in - 60, 0)


def ensure_access_token(config: dict[str, Any], force_refresh: bool = False, timeout: float = 30) -> str:
    access_token = str(config.get("access_token") or "")
    missing = [key for key in ("client_id", "client_secret", "refresh_token") if not config.get(key)]
    if access_token and not force_refresh and not token_is_expired(config):
        return access_token
    if access_token and not force_refresh and access_token_is_usable(access_token, timeout=min(timeout, 15)):
        log("Existing Baidu access_token is still usable; skip token refresh.")
        return access_token
    if missing:
        raise UploadError(f"Config is missing required keys: {', '.join(missing)}")
    try:
        refresh_access_token(config, timeout=timeout)
    except UploadError as exc:
        if access_token and refresh_token_has_been_used(exc) and access_token_is_usable(access_token, timeout=min(timeout, 15)):
            log("Baidu refresh_token is stale, but existing access_token is still usable; continue.")
            return access_token
        if refresh_token_has_been_used(exc):
            raise UploadError(
                "Baidu refresh_token has already been used/rotated. Copy the newest "
                "baidu_pan_cli_config.json from the machine that refreshed it last, "
                "or re-authorize Baidu Netdisk to generate a fresh refresh_token."
            ) from exc
        raise
    return str(config["access_token"])


def refresh_token_has_been_used(exc: UploadError) -> bool:
    message = str(exc)
    return "expired_token" in message and "refresh token has been used" in message


def access_token_is_usable(access_token: str, timeout: float = 15) -> bool:
    try:
        list_directory(access_token, "/", timeout=timeout)
        return True
    except UploadError:
        return False


def refresh_access_token(config: dict[str, Any], timeout: float = 30) -> None:
    payload = urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": config["refresh_token"],
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
        }
    ).encode("utf-8")
    response = request_json(TOKEN_URL, method="POST", data=payload, timeout=timeout)
    if "access_token" not in response:
        raise UploadError(f"Token refresh failed: {safe_json(response)}")
    config["access_token"] = response["access_token"]
    config["refresh_token"] = response.get("refresh_token", config["refresh_token"])
    config["expires_in"] = int(response.get("expires_in", config.get("expires_in", 0)))
    config["token_obtained_at"] = int(time.time())
    save_config(config)


def authorization_url(client_id: str, *, display: str = "tv") -> str:
    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": OAUTH_REDIRECT_URI,
            "scope": OAUTH_SCOPE,
            "display": display,
            "qrcode": 1,
            "force_login": 1,
        }
    )
    return f"https://openapi.baidu.com/oauth/2.0/authorize?{query}"


def exchange_authorization_code(config: dict[str, Any], code: str, timeout: float = 30) -> None:
    missing = [key for key in ("client_id", "client_secret") if not config.get(key)]
    if missing:
        raise UploadError(f"Config is missing required keys: {', '.join(missing)}")
    payload = urlencode(
        {
            "grant_type": "authorization_code",
            "code": code.strip(),
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "redirect_uri": OAUTH_REDIRECT_URI,
        }
    ).encode("utf-8")
    response = request_json(TOKEN_URL, method="POST", data=payload, timeout=timeout)
    if "access_token" not in response or "refresh_token" not in response:
        raise UploadError(f"Authorization code exchange failed: {safe_json(response)}")
    config["access_token"] = response["access_token"]
    config["refresh_token"] = response["refresh_token"]
    config["expires_in"] = int(response.get("expires_in", config.get("expires_in", 2592000)))
    config["token_obtained_at"] = int(time.time())
    save_config(config)


def request_json(
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 60,
) -> dict[str, Any]:
    request = Request(url, data=data, method=method)
    request.add_header("User-Agent", DEFAULT_USER_AGENT)
    request.add_header("Referer", DEFAULT_REFERER)
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise UploadError(f"HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise UploadError(f"Network error: {exc}") from exc
    except OSError as exc:
        raise UploadError(f"Network error: {exc}") from exc
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise UploadError(f"Invalid JSON response: {raw[:500]!r}") from exc


def api_get_json(url: str, params: dict[str, Any], *, timeout: float = 60) -> dict[str, Any]:
    return checked_api_response(request_json(f"{url}?{urlencode(params, doseq=True)}", timeout=timeout))


def api_post_form_json(
    url: str,
    params: dict[str, Any],
    form: dict[str, Any],
    *,
    timeout: float = 60,
    accept_exists: bool = False,
) -> dict[str, Any]:
    data = urlencode(form, doseq=True).encode("utf-8")
    response = request_json(
        f"{url}?{urlencode(params, doseq=True)}",
        method="POST",
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=timeout,
    )
    return checked_api_response(response, accept_exists=accept_exists)


def checked_api_response(response: dict[str, Any], *, accept_exists: bool = False) -> dict[str, Any]:
    errno = response.get("errno", response.get("error_code"))
    if errno in (None, 0):
        return response
    message = str(response.get("errmsg") or response.get("error_msg") or response.get("msg") or "")
    if accept_exists and (errno in (-8, 31061) or "exist" in message.lower() or "已存在" in message):
        return response
    raise UploadError(f"Baidu API error {errno}: {safe_json(response)}")


def list_directory(access_token: str, remote_dir: str, *, timeout: float = 60) -> list[dict[str, Any]]:
    response = api_get_json(
        XPAN_FILE_URL,
        {
            "method": "list",
            "access_token": access_token,
            "dir": remote_dir,
        },
        timeout=timeout,
    )
    return list(response.get("list", []))


def remote_entry(access_token: str, remote_path: str, *, timeout: float = 60) -> dict[str, Any] | None:
    parent = posixpath.dirname(remote_path.rstrip("/")) or "/"
    name = posixpath.basename(remote_path.rstrip("/"))
    try:
        entries = list_directory(access_token, parent, timeout=timeout)
    except UploadError:
        return None
    for entry in entries:
        if entry.get("path") == remote_path or entry.get("server_filename") == name:
            return entry
    return None


def remote_entries_by_path(access_token: str, remote_dir: str, *, timeout: float = 60) -> dict[str, dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    for entry in list_directory(access_token, remote_dir, timeout=timeout):
        path = entry.get("path")
        if path:
            entries[str(path)] = entry
        name = entry.get("server_filename")
        if name:
            entries[posixpath.join(remote_dir, str(name))] = entry
    return entries


def ensure_remote_dir(access_token: str, remote_dir: str, *, timeout: float = 60) -> None:
    current = ""
    for part in [item for item in remote_dir.strip("/").split("/") if item]:
        current = current + "/" + part
        existing = remote_entry(access_token, current, timeout=timeout)
        if existing and int(existing.get("isdir", 0)) == 1:
            continue
        api_post_form_json(
            XPAN_FILE_URL,
            {"method": "create", "access_token": access_token},
            {"path": current, "isdir": 1, "rtype": 1},
            timeout=timeout,
            accept_exists=True,
        )


def upload_file(
    access_token: str,
    local_path: Path,
    remote_path: str,
    *,
    on_duplicate: str = "skip",
    timeout: float = 120,
    retries: int = 2,
    label: str | None = None,
    existing_entry: dict[str, Any] | None = None,
    skip_remote_check: bool = False,
) -> str:
    local_path = local_path.expanduser()
    if not local_path.is_file():
        raise UploadError(f"Local file not found: {local_path}")
    started_at = time.perf_counter()
    local_size = local_path.stat().st_size
    display = label or local_path.name
    try:
        existing = existing_entry
        if on_duplicate == "skip" and existing is None and not skip_remote_check:
            existing = remote_entry(access_token, remote_path, timeout=timeout)
        if existing and on_duplicate == "skip":
            elapsed = time.perf_counter() - started_at
            remote_size = int(existing.get("size", -1))
            if remote_size == local_size:
                log(f"  skip existing: {display} -> {remote_path} ({format_size(local_size)}, elapsed={format_duration(elapsed)})")
                return remote_path
            raise UploadError(
                f"Remote file exists with different size: {remote_path} "
                f"(remoteSize={format_size(remote_size)}, localSize={format_size(local_size)}, elapsed={format_duration(elapsed)}). "
                "Delete the remote file or rerun with --on-duplicate overwrite."
            )

        md5_info = calculate_md5s(local_path)
        block_list_json = json.dumps(md5_info["block_md5s"], ensure_ascii=False)
        rtype = 3 if on_duplicate == "overwrite" else 1
        precreate = api_post_form_json(
            XPAN_FILE_URL,
            {"method": "precreate", "access_token": access_token, "openapi": "xpansdk"},
            {
                "path": remote_path,
                "size": local_size,
                "isdir": 0,
                "autoinit": 1,
                "rtype": rtype,
                "block_list": block_list_json,
                "content-md5": md5_info["content_md5"],
                "slice-md5": md5_info["slice_md5"],
                "local_ctime": int(local_path.stat().st_ctime),
                "local_mtime": int(local_path.stat().st_mtime),
            },
            timeout=timeout,
        )
        upload_id = str(precreate.get("uploadid") or "")
        requested_blocks = precreate.get("block_list")
        if requested_blocks is None:
            requested_blocks = list(range(len(md5_info["block_md5s"])))
        requested_block_indexes = {int(index) for index in requested_blocks}
        if requested_block_indexes and not upload_id:
            raise UploadError(f"Missing uploadid for {remote_path}: {safe_json(precreate)}")

        log(f"  upload started: {display} -> {remote_path} ({format_size(local_size)})")
        for index, chunk in iter_file_chunks(local_path):
            if index not in requested_block_indexes:
                continue
            retry_call(
                lambda index=index, chunk=chunk: upload_block(
                    access_token,
                    remote_path,
                    upload_id,
                    index,
                    local_path.name,
                    chunk,
                    timeout=timeout,
                ),
                retries=retries,
                label=f"{display} block {index}",
            )

        create = api_post_form_json(
            XPAN_FILE_URL,
            {"method": "create", "access_token": access_token, "openapi": "xpansdk"},
            {
                "path": remote_path,
                "size": local_size,
                "isdir": 0,
                "rtype": rtype,
                "uploadid": upload_id,
                "block_list": block_list_json,
                "local_ctime": int(local_path.stat().st_ctime),
                "local_mtime": int(local_path.stat().st_mtime),
            },
            timeout=timeout,
        )
        result = str(create.get("path") or remote_path)
        elapsed = time.perf_counter() - started_at
        log(
            f"  upload finished: {display} -> {result} "
            f"({format_size(local_size)}, elapsed={format_duration(elapsed)}, speed={format_speed(local_size, elapsed)})"
        )
        return result
    except Exception as exc:
        elapsed = time.perf_counter() - started_at
        log(
            f"  upload failed: {display} -> {remote_path} "
            f"({format_size(local_size)}, elapsed={format_duration(elapsed)}, error={exc})",
            error=True,
        )
        raise


def upload_bytes(
    access_token: str,
    content: bytes,
    remote_path: str,
    *,
    on_duplicate: str = "skip",
    timeout: float = 120,
    retries: int = 2,
    label: str | None = None,
    existing_entry: dict[str, Any] | None = None,
    skip_remote_check: bool = False,
) -> str:
    temp_dir = Path(tempfile.gettempdir())
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / f"aidrama-upload-{hashlib.md5(remote_path.encode('utf-8')).hexdigest()}.tmp"
    temp_path.write_bytes(content)
    try:
        return upload_file(
            access_token,
            temp_path,
            remote_path,
            on_duplicate=on_duplicate,
            timeout=timeout,
            retries=retries,
            label=label,
            existing_entry=existing_entry,
            skip_remote_check=skip_remote_check,
        )
    finally:
        try:
            temp_path.unlink()
        except OSError:
            pass


def upload_block(
    access_token: str,
    remote_path: str,
    upload_id: str,
    partseq: int,
    filename: str,
    chunk: bytes,
    *,
    timeout: float = 120,
) -> dict[str, Any]:
    body, content_type = multipart_body(
        {
            "file": (
                filename,
                chunk,
                mimetypes.guess_type(filename)[0] or "application/octet-stream",
            )
        }
    )
    query = urlencode(
        {
            "method": "upload",
            "type": "tmpfile",
            "access_token": access_token,
            "path": remote_path,
            "uploadid": upload_id,
            "partseq": partseq,
        }
    )
    response = request_json(
        f"{PCS_UPLOAD_URL}?{query}",
        method="POST",
        data=body,
        headers={"Content-Type": content_type},
        timeout=timeout,
    )
    return checked_api_response(response)


def multipart_body(files: dict[str, tuple[str, bytes, str]]) -> tuple[bytes, str]:
    boundary = f"----AiDramaBaiduUpload{int(time.time() * 1000)}"
    chunks: list[bytes] = []
    for field, (filename, content, content_type) in files.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'.encode("utf-8"),
                f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                content,
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def calculate_md5s(path: Path) -> dict[str, Any]:
    content_md5 = hashlib.md5()
    slice_md5 = hashlib.md5()
    slice_remaining = SLICE_MD5_SIZE
    block_md5s: list[str] = []
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            content_md5.update(chunk)
            if slice_remaining > 0:
                slice_part = chunk[:slice_remaining]
                slice_md5.update(slice_part)
                slice_remaining -= len(slice_part)
            block_md5s.append(hashlib.md5(chunk).hexdigest())
    if not block_md5s:
        block_md5s.append(hashlib.md5(b"").hexdigest())
    return {
        "content_md5": content_md5.hexdigest(),
        "slice_md5": slice_md5.hexdigest(),
        "block_md5s": block_md5s,
    }


def iter_file_chunks(path: Path) -> Iterable[tuple[int, bytes]]:
    with path.open("rb") as handle:
        index = 0
        while True:
            chunk = handle.read(CHUNK_SIZE)
            if not chunk:
                break
            yield index, chunk
            index += 1


def retry_call(callback, *, retries: int, label: str) -> Any:
    attempt = 0
    while True:
        try:
            return callback()
        except UploadError as exc:
            attempt += 1
            if attempt > retries:
                raise
            wait = min(2**attempt, 10)
            log(f"  retry {attempt}/{retries}: {label}; wait {wait}s; error={exc}")
            time.sleep(wait)


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def parse_info_text(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        match = FIELD_RE.match(line)
        if match:
            key = normalize_field_key(match.group(1))
            value = match.group(2).strip()
            if key == "summary":
                summary_lines = []
                if value:
                    summary_lines.append(value)
                cursor = index + 1
                while cursor < len(lines):
                    candidate = lines[cursor].strip()
                    if is_summary_stop_line(candidate):
                        break
                    if candidate:
                        summary_lines.append(candidate)
                    cursor += 1
                fields["summary"] = "\n".join(summary_lines).strip()
                index = cursor
                continue
            if key:
                fields[key] = value
        index += 1
    return fields


def normalize_field_key(raw_key: str) -> str | None:
    key = raw_key.strip()
    mapping = {
        "名称": "title",
        "剧名": "title",
        "标题": "title",
        "作者": "author",
        "版权方": "author",
        "分类": "category",
        "类型": "category",
        "集数": "episode_count",
        "时长": "total_minutes",
        "总时长": "total_minutes",
        "简介": "summary",
    }
    return mapping.get(key)


def is_summary_stop_line(line: str) -> bool:
    if not line:
        return False
    match = FIELD_RE.match(line)
    if not match:
        return False
    return match.group(1).strip() in STOP_SUMMARY_HEADERS


def find_info_file(local_dir: Path) -> Path | None:
    for name in INFO_NAMES:
        path = local_dir / name
        if path.is_file():
            return path
    return None


def episode_no(name: str) -> int | None:
    for pattern in EPISODE_PATTERNS:
        match = pattern.match(name)
        if match:
            return int(match.group(1))
    return None


def find_episodes(local_dir: Path) -> list[EpisodeFile]:
    episodes: list[EpisodeFile] = []
    for path in local_dir.iterdir():
        if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        number = episode_no(path.name)
        if number is None:
            continue
        remote_name = f"第{number:02d}集{path.suffix.lower()}"
        episodes.append(EpisodeFile(number, path, remote_name))
    return sorted(episodes, key=lambda item: item.episode_no)


def select_cover(local_dir: Path) -> Path | None:
    candidates = [path for path in local_dir.iterdir() if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS]
    if not candidates:
        return None
    return sorted(candidates, key=cover_priority)[0]


def cover_priority(path: Path) -> tuple[int, str]:
    stem = path.stem.lower()
    name = path.name.lower()
    if stem in {"封面", "cover"}:
        return 0, name
    if "封面" in stem:
        return 1, name
    if stem in {"海报", "poster"} or "海报" in stem or "poster" in stem:
        return 2, name
    if stem == "0":
        return 3, name
    return 9, name


def parse_episode_count(value: str) -> int:
    if not value:
        return 0
    match = re.search(r"\d+", value)
    return int(match.group(0)) if match else 0


def build_summary(fields: dict[str, str], title: str) -> str:
    summary = fields.get("summary", "").strip()
    if summary:
        return summary
    return title


def sanitize_remote_segment(value: str) -> str:
    sanitized = re.sub(r"[\\/:*?\"<>|]+", "_", value.strip())
    sanitized = re.sub(r"\s+", " ", sanitized)
    return sanitized or "未命名短剧"


def normalize_remote_path(path: str) -> str:
    normalized = posixpath.normpath("/" + path.strip("/"))
    return "/" if normalized == "/." else normalized


def default_date_dir(now: datetime | None = None) -> str:
    current = now or datetime.now()
    return f"{current.month}月{current.day}日"


def build_drama_plan(local_dir: Path, remote_root: str, date_dir: str, *, allow_missing_episodes: bool = False) -> LocalDramaPlan:
    local_dir = local_dir.expanduser().resolve()
    episodes = find_episodes(local_dir)
    if not episodes:
        raise UploadError(f"No episode video files found: {local_dir}")
    info_path = find_info_file(local_dir)
    fields = parse_info_text(read_text(info_path)) if info_path else {}
    title = fields.get("title") or local_dir.name
    expected_count = parse_episode_count(fields.get("episode_count", ""))
    episode_count = expected_count or len(episodes)
    missing = missing_episode_numbers(episodes, episode_count)
    if missing and not allow_missing_episodes:
        raise UploadError(
            f"{local_dir.name} missing episode files: {compact_numbers(missing)}. "
            "Use --allow-missing-episodes to upload anyway."
        )
    cover_path = select_cover(local_dir)
    cover_remote_name = f"封面{cover_path.suffix.lower()}" if cover_path else None
    title_segment = sanitize_remote_segment(title)
    remote_dir = normalize_remote_path(
        posixpath.join(remote_root, date_dir, f"{title_segment}（{episode_count}集）")
    )
    return LocalDramaPlan(
        local_dir=local_dir,
        title=title,
        author=fields.get("author", ""),
        category=fields.get("category", ""),
        episode_count=episode_count,
        total_minutes=fields.get("total_minutes", ""),
        summary=build_summary(fields, title),
        info_path=info_path,
        cover_path=cover_path,
        cover_remote_name=cover_remote_name,
        episodes=episodes,
        remote_dir=remote_dir,
    )


def missing_episode_numbers(episodes: list[EpisodeFile], expected_count: int) -> list[int]:
    if expected_count <= 0:
        return []
    present = {episode.episode_no for episode in episodes}
    return [number for number in range(1, expected_count + 1) if number not in present]


def read_expected_episode_count(local_dir: Path) -> int:
    info_path = find_info_file(local_dir)
    if not info_path:
        return 0
    fields = parse_info_text(read_text(info_path))
    return parse_episode_count(fields.get("episode_count", ""))


def download_readiness(local_dir: Path, *, allow_missing_episodes: bool = False) -> DownloadReadiness:
    if directory_has_temp_files(local_dir):
        return DownloadReadiness(False, "temporary download files exist", 0, 0, [], False)
    episodes = find_episodes(local_dir)
    expected_count = read_expected_episode_count(local_dir)
    actual_count = len(episodes)
    if expected_count <= 0:
        return DownloadReadiness(True, "no episode count in info file; fallback stability checks required", 0, actual_count, [], False)
    if actual_count == 0:
        return DownloadReadiness(False, f"episode files 0/{expected_count}", expected_count, actual_count, [], True)
    missing = missing_episode_numbers(episodes, expected_count)
    if allow_missing_episodes:
        return DownloadReadiness(True, f"episode files {actual_count}/{expected_count}, missing allowed", expected_count, actual_count, missing, True)
    if actual_count != expected_count or missing:
        detail = f"episode files {actual_count}/{expected_count}"
        if missing:
            detail += f", missing {compact_numbers(missing)}"
        return DownloadReadiness(False, detail, expected_count, actual_count, missing, True)
    if any(episode.path.stat().st_size <= 0 for episode in episodes):
        return DownloadReadiness(False, f"episode files {actual_count}/{expected_count}, but some files are empty", expected_count, actual_count, [], True)
    return DownloadReadiness(True, f"episode files complete {actual_count}/{expected_count}", expected_count, actual_count, [], True)


def compact_numbers(numbers: list[int], limit: int = 20) -> str:
    shown = ", ".join(str(number) for number in numbers[:limit])
    if len(numbers) > limit:
        return f"{shown}, ... ({len(numbers)} total)"
    return shown


def iter_candidate_dirs(root: Path, *, recursive: bool = False, include_marked: bool = False) -> Iterable[Path]:
    root = root.expanduser().resolve()
    if has_episode_files(root):
        yield root
        return
    if recursive:
        iterator = (path for path in root.rglob("*") if path.is_dir())
    else:
        iterator = (path for path in root.iterdir() if path.is_dir())
    for path in iterator:
        if not include_marked and marker_path(path).exists():
            continue
        if has_episode_files(path):
            yield path


def has_episode_files(path: Path) -> bool:
    if not path.is_dir():
        return False
    return any(item.is_file() and item.suffix.lower() in VIDEO_EXTENSIONS and episode_no(item.name) for item in path.iterdir())


def marker_path(local_dir: Path) -> Path:
    return local_dir / MARKER_NAME


def is_dir_stable(local_dir: Path, settle_seconds: int) -> bool:
    if settle_seconds <= 0:
        return True
    newest_mtime = max((path.stat().st_mtime for path in local_dir.iterdir() if path.is_file()), default=0)
    return time.time() - newest_mtime >= settle_seconds


def directory_snapshot(local_dir: Path) -> tuple[tuple[str, int, int], ...]:
    snapshot: list[tuple[str, int, int]] = []
    for path in sorted(local_dir.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_file():
            continue
        stat = path.stat()
        snapshot.append((path.name, stat.st_size, stat.st_mtime_ns))
    return tuple(snapshot)


def directory_has_temp_files(local_dir: Path) -> bool:
    for path in local_dir.iterdir():
        if path.is_file() and path.suffix.lower() in DOWNLOAD_TEMP_EXTENSIONS:
            return True
    return False


def is_download_complete(local_dir: Path, checks: int, interval_seconds: float) -> bool:
    if checks <= 1:
        return not directory_has_temp_files(local_dir)
    if directory_has_temp_files(local_dir):
        return False
    previous = directory_snapshot(local_dir)
    for _ in range(checks - 1):
        time.sleep(max(interval_seconds, 0))
        if directory_has_temp_files(local_dir):
            return False
        current = directory_snapshot(local_dir)
        if current != previous:
            return False
        previous = current
    return True


def upload_drama_plan(
    access_token: str,
    plan: LocalDramaPlan,
    *,
    on_duplicate: str,
    timeout: float,
    retries: int,
    write_marker: bool,
    upload_workers: int = 1,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    total_bytes = len(summary_file_content(plan).encode("utf-8"))
    if plan.cover_path:
        total_bytes += plan.cover_path.stat().st_size
    total_bytes += sum(episode.path.stat().st_size for episode in plan.episodes)
    log(
        f"Drama upload started: {plan.title} -> {plan.remote_dir} "
        f"(episodes={len(plan.episodes)}/{plan.episode_count}, files={len(plan.episodes) + 1 + (1 if plan.cover_path else 0)}, total={format_size(total_bytes)})"
    )
    uploaded: list[str] = []
    try:
        ensure_remote_dir(access_token, plan.remote_dir, timeout=timeout)
        known_remote_entries: dict[str, dict[str, Any]] | None = None
        if on_duplicate == "skip":
            try:
                known_remote_entries = remote_entries_by_path(access_token, plan.remote_dir, timeout=timeout)
            except UploadError as exc:
                log(f"  remote listing failed; fallback to per-file duplicate checks: {exc}", error=True)

        summary_content = summary_file_content(plan).encode("utf-8")
        summary_remote_path = posixpath.join(plan.remote_dir, "简介.txt")
        uploaded.append(
            upload_bytes(
                access_token,
                summary_content,
                summary_remote_path,
                on_duplicate=on_duplicate,
                timeout=timeout,
                retries=retries,
                label="summary: 简介.txt",
                existing_entry=known_remote_entries.get(summary_remote_path) if known_remote_entries is not None else None,
                skip_remote_check=known_remote_entries is not None,
            )
        )
        if plan.cover_path and plan.cover_remote_name:
            cover_remote_path = posixpath.join(plan.remote_dir, plan.cover_remote_name)
            uploaded.append(
                upload_file(
                    access_token,
                    plan.cover_path,
                    cover_remote_path,
                    on_duplicate=on_duplicate,
                    timeout=timeout,
                    retries=retries,
                    label=f"cover: {plan.cover_remote_name}",
                    existing_entry=known_remote_entries.get(cover_remote_path) if known_remote_entries is not None else None,
                    skip_remote_check=known_remote_entries is not None,
                )
            )
        episode_workers = max(int(upload_workers), 1)
        episode_results: list[str] = []
        if episode_workers > 1 and len(plan.episodes) > 1:
            log(f"  uploading episodes with {min(episode_workers, len(plan.episodes))} workers")
            episode_results = upload_episodes_concurrently(
                access_token,
                plan,
                on_duplicate=on_duplicate,
                timeout=timeout,
                retries=retries,
                upload_workers=episode_workers,
                known_remote_entries=known_remote_entries,
            )
        else:
            for episode in plan.episodes:
                remote_path = posixpath.join(plan.remote_dir, episode.remote_name)
                episode_results.append(
                    upload_file(
                        access_token,
                        episode.path,
                        remote_path,
                        on_duplicate=on_duplicate,
                        timeout=timeout,
                        retries=retries,
                        label=f"episode {episode.episode_no}/{plan.episode_count}: {episode.remote_name}",
                        existing_entry=known_remote_entries.get(remote_path) if known_remote_entries is not None else None,
                        skip_remote_check=known_remote_entries is not None,
                    )
                )
        uploaded.extend(episode_results)

        elapsed = time.perf_counter() - started_at
        marker = {
            "uploadedAt": datetime.now().isoformat(timespec="seconds"),
            "remoteDir": plan.remote_dir,
            "title": plan.title,
            "episodeCount": plan.episode_count,
            "uploadedFiles": uploaded,
            "durationSeconds": round(elapsed, 3),
        }
        if write_marker:
            marker_path(plan.local_dir).write_text(json.dumps(marker, indent=2, ensure_ascii=False), encoding="utf-8")
        log(
            f"Drama upload finished: {plan.title} "
            f"(files={len(uploaded)}, elapsed={format_duration(elapsed)}, avgSpeed={format_speed(total_bytes, elapsed)})"
        )
        return marker
    except Exception as exc:
        elapsed = time.perf_counter() - started_at
        log(f"Drama upload failed: {plan.title} (elapsed={format_duration(elapsed)}, error={exc})", error=True)
        raise


def upload_episodes_concurrently(
    access_token: str,
    plan: LocalDramaPlan,
    *,
    on_duplicate: str,
    timeout: float,
    retries: int,
    upload_workers: int,
    known_remote_entries: dict[str, dict[str, Any]] | None,
) -> list[str]:
    results: list[str | None] = [None] * len(plan.episodes)
    futures: dict[Future[str], int] = {}
    executor = ThreadPoolExecutor(max_workers=min(upload_workers, len(plan.episodes)))
    try:
        for index, episode in enumerate(plan.episodes):
            remote_path = posixpath.join(plan.remote_dir, episode.remote_name)
            future = executor.submit(
                upload_file,
                access_token,
                episode.path,
                remote_path,
                on_duplicate=on_duplicate,
                timeout=timeout,
                retries=retries,
                label=f"episode {episode.episode_no}/{plan.episode_count}: {episode.remote_name}",
                existing_entry=known_remote_entries.get(remote_path) if known_remote_entries is not None else None,
                skip_remote_check=known_remote_entries is not None,
            )
            futures[future] = index
        for future in as_completed(futures):
            try:
                results[futures[future]] = future.result()
            except Exception:
                for pending in futures:
                    pending.cancel()
                raise
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
    return [result for result in results if result is not None]


def summary_file_content(plan: LocalDramaPlan) -> str:
    lines = [
        f"名称：{plan.title}",
    ]
    if plan.author:
        lines.append(f"作者：{plan.author}")
    if plan.category:
        lines.append(f"分类：{plan.category}")
    lines.extend(
        [
            f"集数：{plan.episode_count}",
            "",
            "简介：",
            plan.summary.strip() or plan.title,
            "",
        ]
    )
    if plan.total_minutes:
        lines.append(f"时长：{plan.total_minutes}")
    return "\n".join(lines)


def scan_once(args: argparse.Namespace, access_token: str | None = None) -> int:
    root = Path(args.watch_dir).expanduser()
    if not root.is_dir():
        raise UploadError(f"Watch directory not found: {root}")
    plans: list[LocalDramaPlan] = []
    for local_dir in iter_candidate_dirs(root, recursive=args.recursive, include_marked=args.force):
        if marker_path(local_dir).exists() and not args.force:
            log(f"skip marked: {local_dir}")
            continue
        readiness = download_readiness(local_dir, allow_missing_episodes=args.allow_missing_episodes)
        if not readiness.ready:
            log(f"skip incomplete: {local_dir} ({readiness.reason})")
            continue
        if not readiness.used_info_count:
            if not is_dir_stable(local_dir, args.settle_seconds):
                log(f"skip unstable: {local_dir}")
                continue
            if not is_download_complete(local_dir, args.complete_checks, args.complete_interval_seconds):
                log(f"skip incomplete: {local_dir}")
                continue
        try:
            plans.append(
                build_drama_plan(
                    local_dir,
                    args.remote_root,
                    args.date_dir,
                    allow_missing_episodes=args.allow_missing_episodes,
                )
            )
        except UploadError as exc:
            log(f"skip invalid: {exc}", error=True)

    if args.dry_run:
        print(json.dumps([plan.as_dict() for plan in plans], indent=2, ensure_ascii=False))
        return 0
    if not plans:
        log("No local drama folders ready to upload.")
        return 0
    if access_token is None:
        config = load_config(args.config)
        access_token = ensure_access_token(config, force_refresh=args.refresh_token, timeout=args.timeout)

    failed_count = 0
    for plan in plans:
        try:
            marker = upload_drama_plan(
                access_token,
                plan,
                on_duplicate=args.on_duplicate,
                timeout=args.timeout,
                retries=args.retries,
                write_marker=not args.no_marker,
                upload_workers=args.upload_workers,
            )
            log(f"Uploaded marker ready: {marker['remoteDir']} files={len(marker['uploadedFiles'])}")
        except UploadError as exc:
            failed_count += 1
            log(f"Upload skipped after failure: {plan.title} ({exc})", error=True)
    return 1 if failed_count else 0


def watch(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    access_token = ensure_access_token(config, force_refresh=args.refresh_token, timeout=args.timeout)
    log(f"Watching {Path(args.watch_dir).expanduser()} -> {args.remote_root}/{args.date_dir}")
    while True:
        try:
            scan_once(args, access_token=access_token)
        except UploadError as exc:
            log(f"Scan failed: {exc}", error=True)
        time.sleep(args.interval_seconds)


def safe_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False)[:1000]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Upload local drama folders to Baidu Netdisk for AI Drama scanner.")
    parser.add_argument("watch_dir", nargs="?", help="Local directory to scan, for example /Users/eason/Desktop/IT-Codex/tmp")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help=f"Baidu token config JSON. Default: {DEFAULT_CONFIG_PATH}")
    parser.add_argument("--remote-root", default=DEFAULT_REMOTE_ROOT, help=f"Baidu scan root. Default: {DEFAULT_REMOTE_ROOT}")
    parser.add_argument("--date-dir", default=default_date_dir(), help="Remote date directory, for example 8月18日.")
    parser.add_argument("--print-auth-url", action="store_true", help="Print Baidu OAuth URL for generating a new authorization code.")
    parser.add_argument("--auth-code", help="Exchange a Baidu authorization code and save fresh tokens into --config.")
    parser.add_argument("--watch", action="store_true", help="Keep polling the watch directory.")
    parser.add_argument("--interval-seconds", type=int, default=60, help="Polling interval in watch mode.")
    parser.add_argument("--settle-seconds", type=int, default=60, help="Skip recently changed folders when 视频信息.txt has no usable 集数.")
    parser.add_argument("--complete-checks", type=int, default=3, help="Unchanged snapshots required when 视频信息.txt has no usable 集数.")
    parser.add_argument("--complete-interval-seconds", type=float, default=3, help="Seconds between fallback completion snapshots.")
    parser.add_argument("--recursive", action="store_true", help="Find drama folders recursively under watch_dir.")
    parser.add_argument("--dry-run", action="store_true", help="Only print planned remote layout, do not upload.")
    parser.add_argument("--force", action="store_true", help="Ignore existing local upload marker.")
    parser.add_argument("--allow-missing-episodes", action="store_true", help="Upload even if 视频信息 says some episode files are missing.")
    parser.add_argument("--on-duplicate", choices=("skip", "overwrite", "rename"), default="skip", help="How to handle existing remote files.")
    parser.add_argument("--no-marker", action="store_true", help=f"Do not write {MARKER_NAME} after upload.")
    parser.add_argument("--refresh-token", action="store_true", help="Force refresh Baidu access token before upload.")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS, help="HTTP timeout seconds.")
    parser.add_argument("--retries", type=int, default=DEFAULT_UPLOAD_RETRIES, help="Retry count for each upload block.")
    parser.add_argument("--upload-workers", type=int, default=1, help="Parallel episode upload workers. Use 1 for serial uploads; try 3-4 for faster batches.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.print_auth_url:
            config = load_config(args.config)
            if not config.get("client_id"):
                raise UploadError("Config is missing required key: client_id")
            print(authorization_url(str(config["client_id"])))
            return 0
        if args.auth_code:
            config = load_config(args.config)
            exchange_authorization_code(config, args.auth_code, timeout=args.timeout)
            log(f"Baidu token config refreshed: {Path(args.config).expanduser()}")
            return 0
        if not args.watch_dir:
            parser.error("watch_dir is required unless --print-auth-url or --auth-code is used.")
        if args.watch:
            return watch(args)
        return scan_once(args)
    except KeyboardInterrupt:
        log("Stopped.")
        return 130
    except UploadError as exc:
        log(f"Error: {exc}", error=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
