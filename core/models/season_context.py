"""Immutable resolved season state."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SeasonContext:
    """Resolved configuration and capabilities for one season."""

    season_id: str
    display_name: str
    status: str
    enabled: bool
    data_ready: bool
    namespace: str
    working_root: Path
    snapshot_root: Path
    finalized: bool
    mutable: bool
    supported_pages: tuple[str, ...] = ()
    supported_operations: tuple[str, ...] = ()

