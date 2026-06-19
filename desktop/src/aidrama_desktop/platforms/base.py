from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class PlatformPublisher(ABC):
    @abstractmethod
    def open_login(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def export_login_state(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def publish(self, media_files: list[Path], title: str, summary: str | None = None) -> str:
        raise NotImplementedError

