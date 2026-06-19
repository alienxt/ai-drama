from __future__ import annotations

from pathlib import Path


class TokenStore:
    def __init__(self, token_file: Path):
        self.token_file = token_file

    def get(self) -> str | None:
        if not self.token_file.exists():
            return None
        token = self.token_file.read_text(encoding="utf-8").strip()
        return token or None

    def set(self, token: str) -> None:
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        self.token_file.write_text(token, encoding="utf-8")

    def clear(self) -> None:
        if self.token_file.exists():
            self.token_file.unlink()

