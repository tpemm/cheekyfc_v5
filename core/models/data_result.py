"""Structured data-access results and provenance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Generic, TypeVar


class DataStatus(str, Enum):
    AVAILABLE = "available"
    MISSING = "missing"
    EMPTY = "empty"
    INVALID = "invalid"
    STALE = "stale"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class DataProvenance:
    dataset_key: str
    requested_key: str
    season_id: str
    namespace: str
    resolved_path: Path
    format: str
    modified_time: datetime | None
    size_bytes: int | None
    alias_used: bool = False
    fallback_used: bool = False


DataType = TypeVar("DataType")


@dataclass(frozen=True, slots=True)
class DataResult(Generic[DataType]):
    status: DataStatus
    data: DataType | None
    provenance: DataProvenance
    validation_errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

