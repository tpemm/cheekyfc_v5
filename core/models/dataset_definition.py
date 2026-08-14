"""Metadata model for a logical application dataset."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DatasetDefinition:
    """Describe a dataset without loading it or resolving a filesystem path."""

    key: str
    display_name: str
    description: str
    classification: str
    namespace: str
    filename_template: str
    required: bool = True
    producer: str | None = None
    consumers: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    cacheable: bool = True
    mutable: bool = True
    schema_name: str | None = None
    working_subdirectory: str = ""
    snapshot_subdirectory: str = ""
    required_columns: tuple[str, ...] = ()
    family: bool = False
