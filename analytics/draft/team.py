"""Transparent, session-roster-dependent Draft HQ team analytics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd

from analytics.draft.presentation import normalize_fantrax_positions
from fantrax.analytics.core.league_rules import (
    MAX_INJURED_RESERVE_PLAYERS,
    MAX_RESERVE_PLAYERS,
    MIN_ACTIVE,
    TOTAL_ACTIVE_SLOTS,
    TOTAL_ROSTER_SIZE,
)


@dataclass(frozen=True)
class RosterSlot:
    name: str
    eligible: tuple[str, ...]
    group: str


def league_roster_slots() -> tuple[RosterSlot, ...]:
    slots: list[RosterSlot] = []
    for position, count in MIN_ACTIVE.items():
        slots.extend(RosterSlot(f"{position}{i + 1}", (position,), position) for i in range(count))
    flex_count = TOTAL_ACTIVE_SLOTS - sum(MIN_ACTIVE.values())
    slots.extend(RosterSlot(f"FLEX{i + 1}", ("D", "M", "F"), "Flex") for i in range(flex_count))
    bench_count = TOTAL_ROSTER_SIZE - TOTAL_ACTIVE_SLOTS
    slots.extend(
        RosterSlot(
            f"BENCH{i + 1}", ("G", "D", "M", "F"),
            "IR" if i >= MAX_RESERVE_PLAYERS else "Bench",
        )
        for i in range(bench_count)
    )
    assert bench_count == MAX_RESERVE_PLAYERS + MAX_INJURED_RESERVE_PLAYERS
    return tuple(slots)


def assign_roster_slots(players: pd.DataFrame, slots: Iterable[RosterSlot] | None = None) -> pd.DataFrame:
    """Maximum-cardinality bipartite assignment, restrictive slots first."""
    roster_slots = list(slots or league_roster_slots())
    player_rows = list(players.iterrows())
    eligible = {
        index: set(normalize_fantrax_positions(row.get("Position", "")).split("/")) - {""}
        for index, row in player_rows
    }
    order = sorted(
        roster_slots,
        key=lambda slot: (len(slot.eligible), slot.group in {"Bench", "IR"}, slot.name),
    )
    match: dict[int, RosterSlot] = {}

    def place(slot: RosterSlot, seen: set[int]) -> bool:
        candidates = sorted(
            (index for index, _ in player_rows if eligible[index].intersection(slot.eligible)),
            key=lambda index: (len(eligible[index]), str(index)),
        )
        for index in candidates:
            if index in seen:
                continue
            seen.add(index)
            if index not in match or place(match[index], seen):
                match[index] = slot
                return True
        return False

    for slot in order:
        place(slot, set())
    records = []
    for index, row in player_rows:
        slot = match.get(index)
        records.append({
            "player_index": index,
            "Player": row.get("Player"),
            "Slot": slot.name if slot else pd.NA,
            "Slot Group": slot.group if slot else "Unassigned",
        })
    return pd.DataFrame(records)


def positional_coverage(players: pd.DataFrame) -> pd.DataFrame:
    assignment = assign_roster_slots(players)
    slots = league_roster_slots()
    records = []
    for group in ("G", "D", "M", "F", "Flex", "Bench", "IR"):
        needed = sum(slot.group == group for slot in slots)
        filled = int(assignment["Slot Group"].eq(group).sum()) if not assignment.empty else 0
        missing = max(0, needed - filled)
        ratio = missing / needed if needed else 0
        level = "Complete" if missing == 0 else "Critical Need" if ratio >= .67 else "High Need" if ratio >= .5 else "Medium Need" if ratio >= .25 else "Low Need"
        records.append({"Position": group, "Filled": filled, "Needed": needed, "Unfilled": missing, "Need": level})
    total_filled = int(assignment["Slot"].notna().sum()) if not assignment.empty else 0
    records.append({"Position": "Total", "Filled": total_filled, "Needed": TOTAL_ROSTER_SIZE, "Unfilled": TOTAL_ROSTER_SIZE-total_filled, "Need": "Complete" if total_filled == TOTAL_ROSTER_SIZE else "Open"})
    return pd.DataFrame(records)


def _mean(frame: pd.DataFrame, field: str) -> float:
    values = pd.to_numeric(frame.get(field), errors="coerce") if field in frame else pd.Series(dtype=float)
    return float(values.mean()) if values.notna().any() else np.nan


def _sum(frame: pd.DataFrame, field: str) -> float:
    values = pd.to_numeric(frame.get(field), errors="coerce") if field in frame else pd.Series(dtype=float)
    return float(values.sum(min_count=1)) if values.notna().any() else np.nan


def minute_weighted_rate(frame: pd.DataFrame, total_field: str, minutes_field: str = "understat_minutes_2526") -> float:
    totals = pd.to_numeric(frame.get(total_field), errors="coerce") if total_field in frame else pd.Series(dtype=float)
    minutes = pd.to_numeric(frame.get(minutes_field), errors="coerce") if minutes_field in frame else pd.Series(dtype=float)
    valid = totals.notna() & minutes.gt(0)
    return float(totals[valid].sum() * 90 / minutes[valid].sum()) if valid.any() else np.nan


def team_summary(team: pd.DataFrame) -> dict[str, float]:
    """Central team totals and historical minute-weighted rates."""
    return {
        "Players Drafted": float(len(team)),
        "Average Draft Score": _mean(team, "Draft Score"),
        "Total Fantrax Projected Points": _sum(team, "fantrax_projected_points"),
        "Average ADP Value": _mean(team, "Value vs ADP"),
        "Average Projected Minutes %": _mean(team, "projected_minutes_share"),
        "Ghost / 90": minute_weighted_rate(team, "ghost_points_2526", "minutes_2526"),
        "Total xG": _sum(team, "xg_2526"),
        "Total xA": _sum(team, "xa_2526"),
        "Total xGI": _sum(team, "xgi_2526"),
        "xG / 90": minute_weighted_rate(team, "xg_2526"),
        "xA / 90": minute_weighted_rate(team, "xa_2526"),
        "xGI / 90": minute_weighted_rate(team, "xgi_2526"),
        "Average Attacking Score": _mean(team, "attacking_score"),
        "Team Strength Percentile": _mean(team, "team_strength_percentile"),
        "Fixture Ease Percentile": _mean(team, "fixture_ease_percentile"),
    }


def team_floor(team: pd.DataFrame) -> dict[str, float]:
    """Transparent floor summary; not a weekly-points prediction.

    Score = 40% ghost-score mean + 35% minutes-score mean + 25% minutes
    confidence. Inputs are existing bounded model/confidence fields.
    """
    components = {
        "Ghost floor": _mean(team, "ghost_score"),
        "Projected minutes": _mean(team, "minutes_score"),
        "Minutes confidence": _mean(team, "minutes_confidence"),
    }
    if any(pd.isna(value) for value in components.values()):
        score = np.nan
    else:
        score = .40 * components["Ghost floor"] + .35 * components["Projected minutes"] + .25 * components["Minutes confidence"]
    return {"Team Floor Score": float(np.clip(score, 0, 100)) if pd.notna(score) else np.nan, **components}


POSITION_PRIORITY = {"F": 100.0, "M": 95.0, "D": 40.0, "G": 0.0}
GOALKEEPER_WARNING_SLOTS = 2


def snake_pick_sequence(league_size: int = 12, draft_slot: int = 2, rounds: int = 16) -> list[int]:
    """Return the user's overall picks for a configurable snake draft."""
    if not 1 <= draft_slot <= league_size:
        raise ValueError("draft_slot must be within league_size")
    return [
        round_index * league_size + (
            draft_slot if round_index % 2 == 0 else league_size - draft_slot + 1
        )
        for round_index in range(rounds)
    ]


def draft_turn_context(
    completed_overall_picks: int,
    league_size: int = 12,
    draft_slot: int = 2,
    rounds: int = 16,
) -> dict[str, int]:
    sequence = snake_pick_sequence(league_size, draft_slot, rounds)
    current = completed_overall_picks + 1
    future = [pick for pick in sequence if pick >= current]
    next_user = future[0] if future else sequence[-1]
    following = next((pick for pick in sequence if pick > next_user), next_user)
    return {"Current Pick": current, "Next User Pick": next_user, "Following User Pick": following, "Picks Until Next Turn": max(0, following - next_user - 1)}


def next_pick_availability_score(row: pd.Series, current_pick: int, next_pick: int, scarcity: float = 0) -> tuple[float, str]:
    """Non-probabilistic survival score from ADP/rank, gap, and scarcity."""
    adp = pd.to_numeric(pd.Series([row.get("ADP")]), errors="coerce").iloc[0]
    rank = pd.to_numeric(pd.Series([row.get("Rank")]), errors="coerce").iloc[0]
    market = adp if pd.notna(adp) else rank
    if pd.isna(market):
        return np.nan, "Unknown"
    cushion = float(market) - float(next_pick)
    score = float(np.clip(50 + cushion * 3 - scarcity * .25, 0, 100))
    label = "Likely to survive" if score >= 75 else "Could survive" if score >= 50 else "At risk before next pick" if score >= 25 else "Unlikely to survive"
    return round(score, 1), label


def position_scarcity(available: pd.DataFrame) -> pd.DataFrame:
    """Scarcity from fractional availability, top-tier depth, and tier cliffs.

    Multi-position players contribute 1 / eligibility-count to each position.
    Scarcity is 45% inverse depth, 30% inverse Tier 1/2 depth, and 25% the
    bounded Draft Score gap between the best current and next tier.
    """
    records = []
    parsed = []
    for _, row in available.iterrows():
        positions = set(normalize_fantrax_positions(row.get("Position", "")).split("/")) - {""}
        for position in positions:
            parsed.append((position, 1 / len(positions), row))
    max_depth = max((sum(weight for pos, weight, _ in parsed if pos == p) for p in ("G", "D", "M", "F")), default=1) or 1
    for position in ("G", "D", "M", "F"):
        items = [(weight, row) for pos, weight, row in parsed if pos == position]
        depth = sum(weight for weight, _ in items)
        top_depth = sum(weight for weight, row in items if str(row.get("tier", "")) in {"Tier 1", "Tier 2"})
        tiers = sorted({str(row.get("tier")) for _, row in items if pd.notna(row.get("tier"))})
        current = tiers[0] if tiers else ""
        current_scores = [float(row.get("Draft Score")) for _, row in items if str(row.get("tier")) == current and pd.notna(row.get("Draft Score"))]
        later_scores = [float(row.get("Draft Score")) for _, row in items if str(row.get("tier")) != current and pd.notna(row.get("Draft Score"))]
        gap = max(0.0, (min(current_scores) - max(later_scores))) if current_scores and later_scores else 0.0
        cliff = min(100.0, gap * 10 + max(0.0, 3 - len(current_scores)) * 15)
        score = .45 * (100 * (1 - depth / max_depth)) + .30 * (100 / (1 + top_depth)) + .25 * cliff
        label = "Critical Scarcity" if score >= 75 else "High Scarcity" if score >= 55 else "Moderate Scarcity" if score >= 35 else "Low Scarcity"
        records.append({"Position": position, "Available Depth": round(depth, 1), "Top-Tier Depth": round(top_depth, 1), "Tier Cliff": round(cliff, 1), "Scarcity Score": round(float(np.clip(score, 0, 100)), 1), "Scarcity": label})
    return pd.DataFrame(records)


def draft_strategy_priorities(team: pd.DataFrame, available: pd.DataFrame) -> pd.DataFrame:
    coverage = positional_coverage(team).set_index("Position")
    scarcity = position_scarcity(available).set_index("Position")
    remaining = max(0, TOTAL_ROSTER_SIZE - len(team))
    records = []
    for position in ("G", "D", "M", "F"):
        legal = 100.0 if coverage.at[position, "Unfilled"] else 0.0
        baseline = POSITION_PRIORITY[position]
        goalkeeper_status = ""
        if position == "G":
            if legal and remaining == 1:
                baseline = 100.0
                goalkeeper_status = "Goalkeeper now required — final roster slot"
            elif legal and (remaining <= GOALKEEPER_WARNING_SLOTS or scarcity.at[position, "Scarcity Score"] >= 85):
                baseline = 65.0
                goalkeeper_status = f"Goalkeeper warning — {remaining} roster spots remain"
            elif legal:
                legal = 0.0
                goalkeeper_status = "Goalkeeper deferred — plan final round"
        priority = .35 * baseline + .35 * legal + .30 * scarcity.at[position, "Scarcity Score"]
        records.append({"Position": position, "Roster Requirement": coverage.at[position, "Need"], "Baseline": baseline, "Scarcity Score": scarcity.at[position, "Scarcity Score"], "Tier Cliff": scarcity.at[position, "Tier Cliff"], "Strategy Priority": round(float(np.clip(priority, 0, 100)), 1), "Goalkeeper Timing": goalkeeper_status})
    return pd.DataFrame(records).sort_values("Strategy Priority", ascending=False).reset_index(drop=True)


FIT_FIELDS = ("Draft Score", "Legal Need", "Strategy Priority", "Scarcity", "Tier Cliff", "Next-Pick Urgency", "ADP Value", "Floor", "Attacking", "Fixtures", "Team Context")
STRATEGY_WEIGHTS = {
    "Balanced": (.25, .08, .16, .09, .07, .10, .07, .05, .05, .04, .04),
    "Best Player Available": (.55, .03, .07, .03, .03, .10, .07, .03, .03, .03, .03),
    "Fill Positional Needs": (.18, .25, .20, .07, .05, .08, .05, .04, .03, .03, .02),
    "Safer Floor": (.20, .07, .12, .06, .04, .08, .05, .25, .04, .05, .04),
    "Attacking Upside": (.20, .07, .15, .07, .05, .08, .05, .04, .23, .03, .03),
    "Favorable Fixtures": (.20, .07, .12, .06, .04, .08, .05, .05, .04, .25, .04),
    "Scarcity Aware": (.18, .07, .16, .22, .12, .12, .04, .02, .03, .02, .02),
}


def best_available_fits(frame: pd.DataFrame, team: pd.DataFrame, strategy: str = "Balanced", limit: int = 5, *, current_pick: int = 1, next_pick: int = 2) -> pd.DataFrame:
    available = frame[frame["Draft Status"].eq("Available")].copy()
    coverage = positional_coverage(team).set_index("Position")
    priorities = draft_strategy_priorities(team, available).set_index("Position")
    need_points = {"Critical Need": 100, "High Need": 80, "Medium Need": 60, "Low Need": 35, "Complete": 0}
    def need(row: pd.Series) -> float:
        positions = set(normalize_fantrax_positions(row.get("Position", "")).split("/"))
        return max((need_points.get(coverage.at[p, "Need"], 0) for p in positions if p in coverage.index), default=0)
    available["Legal Need"] = available.apply(need, axis=1)
    if TOTAL_ROSTER_SIZE - len(team) > GOALKEEPER_WARNING_SLOTS:
        goalkeeper_rows = available["Position"].map(
            lambda value: "G" in normalize_fantrax_positions(value).split("/")
        )
        available.loc[goalkeeper_rows, "Legal Need"] = 0.0
    def positional_metric(row: pd.Series, field: str) -> float:
        positions = set(normalize_fantrax_positions(row.get("Position", "")).split("/")) - {""}
        return max((float(priorities.at[p, field]) for p in positions if p in priorities.index), default=0)
    available["Strategy Priority"] = available.apply(lambda row: positional_metric(row, "Strategy Priority"), axis=1)
    available["Scarcity"] = available.apply(lambda row: positional_metric(row, "Scarcity Score"), axis=1)
    available["Tier Cliff"] = available.apply(lambda row: positional_metric(row, "Tier Cliff"), axis=1)
    survival = available.apply(lambda row: next_pick_availability_score(row, current_pick, next_pick, row["Scarcity"]), axis=1)
    available["Next-Pick Availability Score"] = [item[0] for item in survival]
    available["Next-Pick Survival"] = [item[1] for item in survival]
    available["Next-Pick Urgency"] = 100 - available["Next-Pick Availability Score"]
    value = pd.to_numeric(available.get("Value vs ADP"), errors="coerce").clip(-25, 25).add(25).mul(2)
    available["ADP Value"] = value
    elite_defender = (
        available["Position"].map(lambda value: "D" in normalize_fantrax_positions(value).split("/"))
        & available["Tier Cliff"].ge(60)
        & pd.to_numeric(available["Draft Score"], errors="coerce").ge(85)
        & available["ADP Value"].ge(50)
    )
    available.loc[elite_defender, "Strategy Priority"] = (
        available.loc[elite_defender, "Strategy Priority"] + 15
    ).clip(upper=100)
    available["Floor"] = pd.to_numeric(available.get("ghost_score"), errors="coerce")
    available["Attacking"] = pd.to_numeric(available.get("attacking_score"), errors="coerce")
    available["Fixtures"] = pd.to_numeric(available.get("fixture_ease_percentile"), errors="coerce")
    available["Team Context"] = pd.to_numeric(available.get("team_strength_percentile"), errors="coerce")
    weights = STRATEGY_WEIGHTS.get(strategy, STRATEGY_WEIGHTS["Balanced"])
    components = available[list(FIT_FIELDS)].apply(pd.to_numeric, errors="coerce")
    weighted = components.mul(weights)
    available["Fit Score"] = weighted.sum(axis=1).div(components.notna().mul(weights).sum(axis=1)).clip(0, 100)
    def reasons(row: pd.Series) -> str:
        items = []
        positions = normalize_fantrax_positions(row.get("Position", ""))
        if row["Strategy Priority"] >= 70: items.append(f"fills high-priority {positions} need")
        if row["Scarcity"] >= 55: items.append(f"{positions} scarcity is high")
        if row["Tier Cliff"] >= 45: items.append(f"approaching a {positions} tier cliff")
        if row["Next-Pick Urgency"] >= 65: items.append(f"unlikely to survive the {max(0, next_pick-current_pick-1)}-pick gap")
        if "D" in positions and row["Tier Cliff"] >= 60 and row["Draft Score"] >= 85: items.append("elite defender tier break creates value")
        if row.get("ADP Value", 0) >= 60: items.append("positive ADP value")
        if row.get("Floor", 0) >= 75: items.append("strong fantasy floor")
        if row.get("Attacking", 0) >= 75: items.append("strong attacking profile")
        if row.get("Fixtures", 0) >= 75: items.append("favorable early fixtures")
        if "G" in positions and row["Strategy Priority"] < 50: items.append("goalkeeper intentionally deferred")
        return "; ".join(items[:3]) or "strongest available weighted fit"
    available["Reasons"] = available.apply(reasons, axis=1)
    columns = [c for c in ("Player", "Position", "Team", "Draft Score", "Fit Score", "Next-Pick Survival", "Reasons") if c in available]
    return available.sort_values(["Fit Score", "Draft Score"], ascending=False, na_position="last")[columns].head(limit).reset_index(drop=True)


def team_strengths_and_risks(team: pd.DataFrame) -> tuple[list[str], list[str]]:
    summary, coverage = team_summary(team), positional_coverage(team)
    strengths, risks = [], []
    if summary["Ghost / 90"] >= 6: strengths.append("Strong historical ghost-point floor")
    if summary["Average Projected Minutes %"] >= 80: strengths.append("Strong projected minutes")
    if summary["Average ADP Value"] >= 3: strengths.append("Positive average ADP value")
    if summary["Team Strength Percentile"] >= 70: strengths.append("Strong club context")
    if summary["Fixture Ease Percentile"] >= 70: strengths.append("Favorable fixture profile")
    if coverage.loc[coverage["Position"].isin(["G", "D", "M", "F"]), "Unfilled"].sum() == 0: strengths.append("Required positional coverage filled")
    if coverage.loc[coverage["Position"].isin(["G", "D", "M", "F"]), "Unfilled"].sum() > 0: risks.append("Unfilled required starting positions")
    if summary["Average Projected Minutes %"] < 65: risks.append("Minutes uncertainty")
    if summary["Average ADP Value"] < -3: risks.append("Negative average ADP value")
    if summary["Fixture Ease Percentile"] < 35: risks.append("Difficult fixture profile")
    club_counts = team.get("Team", pd.Series(dtype=str)).value_counts()
    if not club_counts.empty and club_counts.max() >= 4: risks.append("Heavy exposure to one club")
    return strengths, risks
