"""Position-aware Fantrax scoring helpers.

The full event line exists for rostered players but not for every available
waiver player. To stay exact, the engine anchors to the official Fantrax score
at the player's actual position, removes only the known position-sensitive
components, and adds those components back for a candidate position.

Therefore:
* actual-position score always equals the official Fantrax export;
* multi-position rostered players can be compared correctly;
* waiver rows without full stats are retained but explicitly marked as not
  position-rescorable instead of being silently guessed.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Iterable, Mapping

from fantrax.analytics.core.league_rules import (
    ASSIST_POINTS,
    CLEAN_SHEET_POINTS,
    GOALS_AGAINST_AFTER_FIRST_POINTS,
    GOAL_POINTS_BASE,
    GOAL_POINTS_THIRD_PLUS,
    POSITIONS,
)


def _finite(value: object, default: float = 0.0) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else default
    except (TypeError, ValueError):
        return default


def normalize_position(value: object) -> str:
    text = "" if value is None else str(value).strip().upper()
    aliases = {
        "GK": "G", "GOALKEEPER": "G",
        "DEF": "D", "DEFENDER": "D",
        "MID": "M", "MIDFIELDER": "M",
        "FWD": "F", "FORWARD": "F", "ST": "F",
    }
    text = aliases.get(text, text)
    return text if text in POSITIONS else ""


def parse_eligible_positions(value: object, fallback: object = "") -> tuple[str, ...]:
    text = "" if value is None else str(value).upper().strip()
    positions: list[str] = []
    for raw in re.split(r"[,/|;\s]+", text):
        pos = normalize_position(raw)
        if pos and pos not in positions:
            positions.append(pos)
    fallback_pos = normalize_position(fallback)
    if not positions and fallback_pos:
        positions.append(fallback_pos)
    return tuple(positions)


def goal_points(position: str, goals: object) -> float:
    pos = normalize_position(position)
    count = max(_finite(goals), 0.0)
    if pos in GOAL_POINTS_THIRD_PLUS:
        return min(count, 2.0) * GOAL_POINTS_BASE[pos] + max(count - 2.0, 0.0) * GOAL_POINTS_THIRD_PLUS[pos]
    return count * GOAL_POINTS_BASE.get(pos, 0.0)


def position_sensitive_points(
    position: str,
    *,
    goals: object = 0,
    assists: object = 0,
    clean_sheets: object = 0,
    goals_against: object = 0,
) -> float:
    pos = normalize_position(position)
    if not pos:
        raise ValueError(f"Unknown scoring position: {position!r}")
    return (
        goal_points(pos, goals)
        + ASSIST_POINTS[pos] * max(_finite(assists), 0.0)
        + CLEAN_SHEET_POINTS[pos] * max(_finite(clean_sheets), 0.0)
        + GOALS_AGAINST_AFTER_FIRST_POINTS[pos] * max(_finite(goals_against) - 1.0, 0.0)
    )


@dataclass(frozen=True)
class PositionScoreResult:
    official_points: float
    actual_position: str
    eligible_positions: tuple[str, ...]
    scores_by_position: Mapping[str, float]
    rescore_available: bool
    scoring_source: str
    warning: str = ""


def score_player_positions(
    *,
    official_points: object,
    actual_position: object,
    eligible_positions: object,
    goals: object | None,
    assists: object | None,
    clean_sheets: object | None,
    goals_against: object | None,
    full_stats_available: bool = True,
) -> PositionScoreResult:
    official = _finite(official_points)
    actual = normalize_position(actual_position)
    eligible = parse_eligible_positions(eligible_positions, actual)

    if not eligible:
        return PositionScoreResult(official, actual, tuple(), {}, False, "official_export", "No valid eligible position.")

    required_values = (goals, assists, clean_sheets, goals_against)
    can_rescore = bool(full_stats_available and actual and all(v is not None for v in required_values))

    if not can_rescore:
        # Official points are usable for rankings and waiver analysis, but a
        # cross-position comparison would be fabricated. Keep only the actual
        # position when known; otherwise expose the same official total with an
        # explicit non-rescorable flag for display-only use.
        positions = (actual,) if actual else eligible
        scores = {pos: official for pos in positions}
        return PositionScoreResult(
            official, actual, eligible, scores, False, "official_export_only",
            "Complete rostered event stats are unavailable; position-dependent rescoring was not attempted.",
        )

    actual_component = position_sensitive_points(
        actual,
        goals=goals,
        assists=assists,
        clean_sheets=clean_sheets,
        goals_against=goals_against,
    )
    invariant_residual = official - actual_component
    scores = {
        pos: invariant_residual + position_sensitive_points(
            pos,
            goals=goals,
            assists=assists,
            clean_sheets=clean_sheets,
            goals_against=goals_against,
        )
        for pos in eligible
    }
    # Guarantee exact identity at the exported scoring position despite any
    # floating-point arithmetic or future scoring-rule changes.
    if actual in scores:
        scores[actual] = official

    return PositionScoreResult(official, actual, eligible, scores, True, "official_export_plus_position_delta")
