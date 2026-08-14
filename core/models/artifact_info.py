"""Metadata describing one safe, inspectable artifact."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ArtifactInfo:
    """Filesystem metadata without loaded artifact contents."""

    path: Path
    name: str
    suffix: str
    size_bytes: int
    modified_time: datetime
    is_file: bool
    dataset_key: str | None = None
    namespace: str | None = None
    season_id: str | None = None

