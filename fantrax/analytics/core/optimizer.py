"""Legal 11-player lineup optimizer with multi-position scoring."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Mapping, Sequence

from fantrax.analytics.core.league_rules import MAX_ACTIVE, MIN_ACTIVE, POSITIONS, TOTAL_ACTIVE_SLOTS


@dataclass(frozen=True)
class LineupPlayer:
    row_id: int
    player_id: str
    player_name: str
    scores_by_position: Mapping[str, float]
    actual_started: bool = False
    actual_position: str = ""
    rescore_available: bool = True


@dataclass(frozen=True)
class OptimizedLineup:
    total_points: float
    assignments: Mapping[int, str]
    legal_solution_found: bool
    warning: str = ""

    @property
    def selected_row_ids(self) -> tuple[int, ...]:
        return tuple(self.assignments.keys())


def _legal(counts: tuple[int, int, int, int], used: int) -> bool:
    if used != TOTAL_ACTIVE_SLOTS:
        return False
    return all(MIN_ACTIVE[p] <= counts[i] <= MAX_ACTIVE[p] for i, p in enumerate(POSITIONS))


def optimize_lineup(players: Sequence[LineupPlayer]) -> OptimizedLineup:
    candidates = [p for p in players if p.scores_by_position]
    if len(candidates) < TOTAL_ACTIVE_SLOTS:
        return OptimizedLineup(0.0, {}, False, f"Only {len(candidates)} usable players; {TOTAL_ACTIVE_SLOTS} required.")

    @lru_cache(maxsize=None)
    def dp(i: int, used: int, g: int, d: int, m: int, f: int):
        counts = (g, d, m, f)
        if used == TOTAL_ACTIVE_SLOTS:
            return (0.0, tuple()) if _legal(counts, used) else (-float("inf"), tuple())
        if i >= len(candidates) or used + (len(candidates) - i) < TOTAL_ACTIVE_SLOTS:
            return -float("inf"), tuple()
        if any(counts[j] > MAX_ACTIVE[p] for j, p in enumerate(POSITIONS)):
            return -float("inf"), tuple()
        minimum_needed = sum(max(MIN_ACTIVE[p] - counts[j], 0) for j, p in enumerate(POSITIONS))
        if minimum_needed > TOTAL_ACTIVE_SLOTS - used:
            return -float("inf"), tuple()

        player = candidates[i]
        best_score, best_assignments = dp(i + 1, used, g, d, m, f)
        for pos, points in player.scores_by_position.items():
            if pos not in POSITIONS:
                continue
            next_counts = list(counts)
            pos_i = POSITIONS.index(pos)
            next_counts[pos_i] += 1
            if next_counts[pos_i] > MAX_ACTIVE[pos]:
                continue
            rest_score, rest_assignments = dp(i + 1, used + 1, *next_counts)
            candidate_score = float(points) + rest_score
            if candidate_score > best_score:
                best_score = candidate_score
                best_assignments = ((player.row_id, pos),) + rest_assignments
        return best_score, best_assignments

    total, assignments = dp(0, 0, 0, 0, 0, 0)
    if total == -float("inf"):
        return OptimizedLineup(0.0, {}, False, "No legal formation could be constructed from the eligible positions.")
    return OptimizedLineup(round(float(total), 6), dict(assignments), True)
