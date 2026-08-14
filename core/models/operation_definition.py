"""Public metadata for one approved application operation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OperationDefinition:
    key: str
    label: str
    description: str
    capability: str
    parameters: tuple[str, ...] = ()

