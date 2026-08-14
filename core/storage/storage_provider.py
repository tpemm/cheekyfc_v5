"""Minimal read-only storage interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from os import stat_result
from pathlib import Path


class ArtifactAccessError(OSError):
    """Raised when a storage provider cannot safely access an artifact."""


class StorageProvider(ABC):
    """Read-only operations required by DataManager."""

    @abstractmethod
    def normalize(self, path: str | Path) -> Path:
        """Return a normalized absolute path."""

    @abstractmethod
    def exists(self, path: str | Path) -> bool:
        """Return whether an artifact exists."""

    @abstractmethod
    def stat(self, path: str | Path) -> stat_result:
        """Return artifact metadata."""

    @abstractmethod
    def read_bytes(self, path: str | Path) -> bytes:
        """Read an artifact as bytes."""

    @abstractmethod
    def read_text(self, path: str | Path, encoding: str = "utf-8") -> str:
        """Read an artifact as text."""

    @abstractmethod
    def list_files(
        self,
        root: str | Path,
        pattern: str | None = None,
        *,
        recursive: bool = False,
    ) -> tuple[Path, ...]:
        """List files deterministically below a root."""

