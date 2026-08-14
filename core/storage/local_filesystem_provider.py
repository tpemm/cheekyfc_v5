"""Read-only local filesystem storage provider."""

from __future__ import annotations

from os import stat_result
from pathlib import Path

from core.storage.storage_provider import ArtifactAccessError, StorageProvider


class LocalFilesystemProvider(StorageProvider):
    """Provide normalized, deterministic local artifact access."""

    def normalize(self, path: str | Path) -> Path:
        try:
            return Path(path).expanduser().resolve(strict=False)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            raise ArtifactAccessError(f"Could not normalize path {path!r}") from exc

    def exists(self, path: str | Path) -> bool:
        normalized = self.normalize(path)
        try:
            return normalized.exists()
        except OSError as exc:
            raise ArtifactAccessError(
                f"Could not check artifact existence: {normalized}"
            ) from exc

    def stat(self, path: str | Path) -> stat_result:
        normalized = self.normalize(path)
        try:
            return normalized.stat()
        except OSError as exc:
            raise ArtifactAccessError(
                f"Could not inspect artifact: {normalized}"
            ) from exc

    def read_bytes(self, path: str | Path) -> bytes:
        normalized = self.normalize(path)
        try:
            return normalized.read_bytes()
        except OSError as exc:
            raise ArtifactAccessError(
                f"Could not read artifact bytes: {normalized}"
            ) from exc

    def read_text(self, path: str | Path, encoding: str = "utf-8") -> str:
        normalized = self.normalize(path)
        try:
            return normalized.read_text(encoding=encoding)
        except (OSError, UnicodeError) as exc:
            raise ArtifactAccessError(
                f"Could not read artifact text: {normalized}"
            ) from exc

    def list_files(
        self,
        root: str | Path,
        pattern: str | None = None,
        *,
        recursive: bool = False,
    ) -> tuple[Path, ...]:
        normalized = self.normalize(root)
        if not self.exists(normalized):
            return ()
        if not normalized.is_dir():
            raise ArtifactAccessError(f"Artifact root is not a directory: {normalized}")

        search_pattern = pattern or "*"
        try:
            candidates = (
                normalized.rglob(search_pattern)
                if recursive
                else normalized.glob(search_pattern)
            )
            files = (path.resolve() for path in candidates if path.is_file())
            return tuple(sorted(files, key=lambda path: path.as_posix().casefold()))
        except OSError as exc:
            raise ArtifactAccessError(
                f"Could not list artifacts below: {normalized}"
            ) from exc

