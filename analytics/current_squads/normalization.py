"""Shared current-player normalization."""

from analytics.draft.reliability import normalize_team, normalize_text

FPL_POSITION = {1: "G", 2: "D", 3: "M", 4: "F"}

__all__ = ["FPL_POSITION", "normalize_team", "normalize_text"]
