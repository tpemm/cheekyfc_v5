"""Canonical Cheeky FC Fantrax league rules.

This module is the single source of truth for roster and starting-lineup rules.
Scoring uses position-sensitive deltas because Fantrax exports complete event
statistics only for rostered players. The exported Fantrax point total remains
canonical for each player's actual position.
"""
from __future__ import annotations

TOTAL_ROSTER_SIZE = 16
TOTAL_ACTIVE_SLOTS = 11
MAX_RESERVE_PLAYERS = 4
MAX_INJURED_RESERVE_PLAYERS = 1

POSITIONS = ("G", "D", "M", "F")
MIN_ACTIVE = {"G": 1, "D": 3, "M": 2, "F": 1}
MAX_ACTIVE = {"G": 1, "D": 5, "M": 5, "F": 3}

# Position-sensitive scoring currently used by the historical analytics layer.
# Non-position-sensitive scoring is preserved through a residual anchored to
# the official exported Fantrax score, so the engine does not need to recreate
# every category to optimize a rostered lineup.
GOAL_POINTS_BASE = {"G": 12.0, "D": 9.0, "M": 9.0, "F": 9.0}
GOAL_POINTS_THIRD_PLUS = {"D": 12.0, "M": 12.0, "F": 12.0}
ASSIST_POINTS = {"G": 7.0, "D": 7.0, "M": 6.0, "F": 6.0}
CLEAN_SHEET_POINTS = {"G": 6.0, "D": 6.0, "M": 1.0, "F": 0.0}
GOALS_AGAINST_AFTER_FIRST_POINTS = {"G": -2.0, "D": -2.0, "M": 0.0, "F": 0.0}

# A player's official weekly score can be rescored at another eligible position
# only when these event stats and the actual scoring position are available.
POSITION_RESCORE_REQUIRED_FIELDS = (
    "fantasy_points",
    "actual_position",
    "goals",
    "assists",
    "clean_sheets",
    "goals_against",
)
