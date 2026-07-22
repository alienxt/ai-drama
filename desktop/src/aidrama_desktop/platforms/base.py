from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from pathlib import Path


class PlatformPublishPaused(RuntimeError):
    pass


class PlatformPublishSubmittedError(RuntimeError):
    pass


class PlatformPublisher(ABC):
    @abstractmethod
    def open_login(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def export_login_state(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def publish(
        self,
        media_files: list[Path],
        title: str,
        summary: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        raise NotImplementedError
