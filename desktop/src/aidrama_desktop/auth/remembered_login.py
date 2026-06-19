from __future__ import annotations

import json
import time
from pathlib import Path


class RememberedLoginStore:
    ttl_seconds = 24 * 60 * 60

    def __init__(self, path: Path):
        self.path = path

    def get(self, now: float | None = None) -> tuple[str, str] | None:
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.clear()
            return None
        if (now or time.time()) >= float(data.get("expires_at", 0)):
            self.clear()
            return None
        username = str(data.get("username") or "")
        password = str(data.get("password") or "")
        if not username or not password:
            self.clear()
            return None
        return username, password

    def set(self, username: str, password: str, now: float | None = None) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "username": username,
                    "password": password,
                    "expires_at": (now or time.time()) + self.ttl_seconds,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
