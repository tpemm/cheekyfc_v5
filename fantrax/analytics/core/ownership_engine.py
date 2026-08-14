"""Shared ownership-period helpers for manager, player, and explorer views."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class OwnershipPeriod:
    manager_id: str
    player_id: str
    start_gameweek: int
    end_gameweek: int

    @property
    def weeks_owned(self) -> int:
        return max(self.end_gameweek - self.start_gameweek + 1, 0)
