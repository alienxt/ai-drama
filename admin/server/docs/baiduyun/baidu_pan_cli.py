#!/usr/bin/env python3
"""Small Baidu Netdisk CLI with token auto-refresh and download helpers."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_CONFIG_PATH = Path(__file__).resolve().with_name("baidu_pan_cli_config.json")
TOKEN_URL = "https://openapi.baidu.com/oauth/2.0/token"
XPAN_FILE_URL = "https://pan.baidu.com/rest/2.0/xpan/file"
XPAN_MEDIA_URL = "https://pan.baidu.com/rest/2.0/xpan/multimedia"
DEFAULT_USER_AGENT = "pan.baidu.com"
DEFAULT_REFERER = "https://pan.baidu.com/"


class BaiduPanError(RuntimeError):
    """Raised when the Baidu Pan API returns a user-facing error."""


def load_config(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path).expanduser()
    if not path.exists():
        raise BaiduPanError(
            f"Config not found: {path}. Run `python baidu_pan_cli.py init ...` first."
        )

    config = json.loads(path.read_text(encoding="utf-8"))
    config["config_path"] = str(path)
    return config


def save_config(config: dict[str, Any]) -> Path:
    path = Path(config.get("config_path", DEFAULT_CONFIG_PATH)).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    payload = dict(config)
    payload.pop("config_path", None)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def token_is_expired(config: dict[str, Any], now: float | None = None) -> bool:
    now = now if now is not None else time.time()
    obtained_at = float(config.get("token_obtained_at", 0))
    expires_in = int(config.get("expires_in", 0))
    return now >= obtained_at + max(expires_in - 60, 0)


def _decode_json_response(response: Any) -> dict[str, Any]:
    raw = response.read()
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _urlopen_json(request: Request) -> dict[str, Any]:
    try:
        with urlopen(request) as response:
            return _decode_json_response(response)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise BaiduPanError(f"HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise BaiduPanError(f"Network error: {exc}") from exc


def _make_request(url: str, method: str = "GET", data: bytes | None = None) -> Request:
    request = Request(url, data=data, method=method)
    request.add_header("User-Agent", DEFAULT_USER_AGENT)
    request.add_header("Referer", DEFAULT_REFERER)
    if data is not None:
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
    return request


def refresh_access_token(config: dict[str, Any]) -> dict[str, Any]:
    payload = urlencode(
        {
            "grant_type": "refresh_token",
            "refresh_token": config["refresh_token"],
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
        }
    ).encode("utf-8")
    response = _urlopen_json(_make_request(TOKEN_URL, method="POST", data=payload))

    if "access_token" not in response:
        raise BaiduPanError(f"Token refresh failed: {response}")

    config["access_token"] = response["access_token"]
    config["refresh_token"] = response.get("refresh_token", config["refresh_token"])
    config["expires_in"] = int(response.get("expires_in", config.get("expires_in", 0)))
    config["token_obtained_at"] = int(time.time())
    save_config(config)
    return config


def ensure_access_token(config: dict[str, Any], force_refresh: bool = False) -> str:
    required_keys = ["client_id", "client_secret", "refresh_token"]
    missing = [key for key in required_keys if not config.get(key)]
    if missing:
        raise BaiduPanError(f"Config is missing required keys: {', '.join(missing)}")

    if force_refresh or not config.get("access_token") or token_is_expired(config):
        refresh_access_token(config)

    return str(config["access_token"])


def api_get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    query = urlencode(params, doseq=True)
    response = _urlopen_json(_make_request(f"{url}?{query}"))

    errno = response.get("errno")
    if errno not in (None, 0):
        raise BaiduPanError(f"API error {errno}: {response}")

    return response


def list_directory(access_token: str, remote_dir: str) -> list[dict[str, Any]]:
    data = api_get_json(
        XPAN_FILE_URL,
        {
            "method": "list",
            "access_token": access_token,
            "dir": remote_dir,
        },
    )
    return list(data.get("list", []))


def get_entry_by_path(access_token: str, remote_path: str) -> dict[str, Any]:
    path = Path(remote_path)
    parent = str(path.parent)
    if parent == ".":
        parent = "/"

    items = list_directory(access_token, parent)
    for item in items:
        if item.get("path") == remote_path:
            return item

    raise BaiduPanError(f"Remote path not found: {remote_path}")


def get_file_dlink(access_token: str, fs_id: int) -> str:
    data = api_get_json(
        XPAN_MEDIA_URL,
        {
            "method": "filemetas",
            "access_token": access_token,
            "fsids": json.dumps([fs_id]),
            "dlink": 1,
        },
    )

    items = data.get("list", [])
    if not items or "dlink" not in items[0]:
        raise BaiduPanError(f"Missing dlink in file metadata response: {data}")

    return str(items[0]["dlink"])


def with_access_token(url: str, access_token: str) -> str:
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}access_token={access_token}"


def download_stream(url: str, local_path: str | Path, access_token: str) -> Path:
    target = Path(local_path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)

    request = _make_request(with_access_token(url, access_token))
    try:
        with urlopen(request) as response:
            target.write_bytes(response.read())
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise BaiduPanError(f"Download failed with HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise BaiduPanError(f"Download failed: {exc}") from exc

    return target


def download_file(config: dict[str, Any], remote_path: str, local_path: str | Path) -> Path:
    access_token = ensure_access_token(config)
    entry = get_entry_by_path(access_token, remote_path)
    if int(entry.get("isdir", 0)) == 1:
        raise BaiduPanError("download only supports files, not directories")

    dlink = get_file_dlink(access_token, int(entry["fs_id"]))
    return download_stream(dlink, local_path, access_token)


def print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Baidu Netdisk helper with auto token refresh.")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help=f"Path to config json (default: {DEFAULT_CONFIG_PATH})",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Save client credentials and tokens.")
    init_parser.add_argument("--client-id", required=True)
    init_parser.add_argument("--client-secret", required=True)
    init_parser.add_argument("--access-token", required=True)
    init_parser.add_argument("--refresh-token", required=True)
    init_parser.add_argument("--expires-in", type=int, default=2592000)
    init_parser.add_argument("--app-name", default="")

    subparsers.add_parser("refresh", help="Force refresh the access token.")

    ls_parser = subparsers.add_parser("ls", help="List files in a remote directory.")
    ls_parser.add_argument("remote_dir", nargs="?", default="/")

    download_parser = subparsers.add_parser("download", help="Download a remote file.")
    download_parser.add_argument("remote_path")
    download_parser.add_argument("local_path", nargs="?")

    subparsers.add_parser("show-config", help="Print the stored config without secrets.")
    return parser


def cmd_init(args: argparse.Namespace) -> int:
    config = {
        "client_id": args.client_id,
        "client_secret": args.client_secret,
        "access_token": args.access_token,
        "refresh_token": args.refresh_token,
        "expires_in": args.expires_in,
        "token_obtained_at": int(time.time()),
        "app_name": args.app_name,
        "config_path": args.config,
    }
    path = save_config(config)
    print(f"Saved config to {path}")
    return 0


def cmd_refresh(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    refresh_access_token(config)
    print("Access token refreshed.")
    return 0


def cmd_ls(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    token = ensure_access_token(config)
    items = list_directory(token, args.remote_dir)
    print_json(items)
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    local_path = args.local_path
    if not local_path:
        local_path = str(Path.cwd() / Path(args.remote_path).name)
    target = download_file(config, args.remote_path, local_path)
    print(f"Downloaded to {target}")
    return 0


def cmd_show_config(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    safe_config = dict(config)
    for key in ("client_secret", "access_token", "refresh_token"):
        if safe_config.get(key):
            safe_config[key] = "***"
    print_json(safe_config)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "init":
            return cmd_init(args)
        if args.command == "refresh":
            return cmd_refresh(args)
        if args.command == "ls":
            return cmd_ls(args)
        if args.command == "download":
            return cmd_download(args)
        if args.command == "show-config":
            return cmd_show_config(args)
        parser.error(f"Unsupported command: {args.command}")
    except BaiduPanError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
