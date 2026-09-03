"""Prepared, descriptive models for the Teams research experience.

The helpers in this module are deliberately UI-free.  They consume canonical
products and preserve the distinction between an observed zero and no sample.
Percentiles are neutral volume percentiles: a larger number means *more* of the
named characteristic, never automatically better.
"""
from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

from analytics.advanced_descriptive import add_plot_coordinates
from analytics.players.role_tactical import event_activity_by_zone
from core.services.historical_advanced import historical_club_id

PROFILE_GROUPS = {
    "Attacking Profile": (
        ("xG / Match", "xg_per_match"), ("Shots / Match", "shots_per_match"),
        ("SOT / Match", "shots_on_target_per_match"), ("KP / Match", "key_passes_per_match"),
        ("Box Entries / Match", "box_entries_per_match"),
    ),
    "Creation / Ball Progression": (
        ("Pass Completion %", "pass_completion_pct"), ("Final-Third Entries / Match", "final_third_entries_per_match"),
        ("Cross Attempts / Match", "crosses_per_match"), ("Successful Crosses / Match", "successful_crosses_per_match"),
        ("Successful TakeOns / Match", "successful_take_ons_per_match"),
    ),
    "Defensive Profile": (
        ("xGA / Match", "xga_per_match"), ("Tackles Won / Match", "successful_tackles_per_match"),
        ("Interceptions / Match", "interceptions_per_match"), ("Aerial Win %", "aerial_win_pct"),
        ("Defensive Event Depth", "defensive_event_activity_depth"),
    ),
}

EVENT_LAYERS = {
    "Activity Density": None,
    "Passes": {"Pass"}, "Key Passes": {"KeyPass"}, "Crosses": {"Cross"},
    "TakeOns": {"TakeOn"}, "Shots": {"Goal", "SavedShot", "MissedShots", "ShotOnPost"},
    "Defensive Actions": {"Tackle", "Interception", "Clearance", "BlockedPass", "BlockedShot"},
    "Recoveries": {"BallRecovery"}, "Aerials": {"Aerial"},
}


def _number(series: pd.Series | object) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _club(frame: pd.DataFrame, club_id: str, column: str = "club_id") -> pd.DataFrame:
    return frame[frame.get(column, pd.Series(index=frame.index, dtype=object)).astype(str).eq(str(club_id))].copy()


def _aggregate_matches(matches: pd.DataFrame) -> pd.Series:
    if matches.empty:
        return pd.Series(dtype=object)
    row = {
        "club_id": matches.club_id.iloc[0], "club_name": matches.get("club_name", pd.Series([pd.NA])).iloc[0],
        "matches": matches.canonical_match_id.nunique(), "wins": matches.result.eq("W").sum(),
        "draws": matches.result.eq("D").sum(), "losses": matches.result.eq("L").sum(),
        "goals_for": _number(matches.get("team_goals")).sum(min_count=1),
        "goals_against": _number(matches.get("opponent_goals")).sum(min_count=1),
        "xg": _number(matches.get("xg")).sum(min_count=1), "xga": _number(matches.get("xga")).sum(min_count=1),
    }
    row["xg_diff"] = row["xg"] - row["xga"] if pd.notna(row["xg"]) and pd.notna(row["xga"]) else np.nan
    for field in ("event_count", "passes", "successful_passes", "key_passes", "crosses", "successful_crosses",
                  "take_ons", "successful_take_ons", "shots", "shots_on_target", "successful_tackles",
                  "interceptions", "clearances", "blocks", "recoveries", "aerials", "aerial_wins",
                  "final_third_entries", "box_entries", "defensive_event_activity_depth"):
        if field in matches:
            row[f"{field}_per_match"] = _number(matches[field]).mean()
    for field in ("pass_completion_pct", "cross_success_pct", "take_on_success_pct", "aerial_win_pct", "final_third_event_share", "box_event_share"):
        if field in matches:
            row[field] = _number(matches[field]).mean()
    return pd.Series(row)


def prepare_team_profile_percentiles(profiles: pd.DataFrame, club_id: str) -> dict[str, pd.DataFrame]:
    """Return fixed league-relative panels using neutral, non-inverted percentiles."""
    league = profiles.copy()
    if league.empty:
        return {group: pd.DataFrame() for group in PROFILE_GROUPS}
    if "xg_per_match" not in league and {"xg", "matches"} <= set(league):
        league["xg_per_match"] = _number(league.xg) / _number(league.matches).replace(0, np.nan)
        league["xga_per_match"] = _number(league.xga) / _number(league.matches).replace(0, np.nan)
    selected = _club(league, club_id)
    panels: dict[str, pd.DataFrame] = {}
    for group, axes in PROFILE_GROUPS.items():
        rows = []
        for label, field in axes:
            values = _number(league[field]) if field in league else pd.Series(dtype=float)
            value = np.nan if selected.empty or field not in selected else _number(selected[field]).iloc[0]
            rows.append({"Metric": label, "Value": value, "League Average": values.mean(),
                         "Volume Percentile": np.nan if pd.isna(value) else 100 * values.rank(pct=True).loc[selected.index[0]],
                         "Volume Rank": np.nan if pd.isna(value) else values.rank(method="min", ascending=False).loc[selected.index[0]]})
        panels[group] = pd.DataFrame(rows)
    return panels


def prepare_team_overview(club_id: str, matches: pd.DataFrame, profiles: pd.DataFrame,
                          fantasy: pd.DataFrame, fixtures: pd.DataFrame) -> dict[str, object]:
    own = _club(matches, club_id).sort_values(["match_date", "canonical_match_id"])
    profile = _club(profiles, club_id)
    summary = profile.iloc[0].copy() if not profile.empty else _aggregate_matches(own)
    if pd.notna(summary.get("matches")):
        summary["record"] = f"{int(summary.get('wins', 0))}-{int(summary.get('draws', 0))}-{int(summary.get('losses', 0))}"
    allowed = _club(fantasy, club_id)
    summary["opponent_fpts_observed"] = _number(allowed.get("fantasy_points_allowed")).sum(min_count=1)
    future = _club(fixtures, club_id)
    if not future.empty:
        future = future[~future.get("completed", False).fillna(False).astype(bool)].sort_values("kickoff_time").head(5)
    return {"summary": summary, "matches": own, "trend": own[[c for c in ("match_date", "opponent_name", "team_goals", "xg", "xga") if c in own]],
            "fixtures": future, "profiles": prepare_team_profile_percentiles(profiles, club_id)}


def prepare_team_match_analysis(matches: pd.DataFrame, club_id: str, *, venue: str = "All") -> dict[str, object]:
    rows = _club(matches, club_id)
    if venue in {"Home", "Away"}:
        rows = rows[rows.get("home_away", pd.Series(index=rows.index, dtype=object)).astype(str).eq(venue[0])]
    rows = rows.sort_values(["match_date", "canonical_match_id"])
    return {"rows": rows, "summary": _aggregate_matches(rows)}


def filter_tactical_scope(matches: pd.DataFrame, club_id: str, *, scope: str = "Season", venue: str = "All",
                          formation: str = "All", manager: str = "All", match_id: str | None = None) -> pd.DataFrame:
    rows = _club(matches, club_id).sort_values(["match_date", "canonical_match_id"])
    if venue in {"Home", "Away"}: rows = rows[rows.home_away.astype(str).eq(venue[0])]
    if formation != "All": rows = rows[rows.formation.astype(str).eq(str(formation))]
    if manager != "All": rows = rows[rows.manager_name.astype(str).eq(str(manager))]
    if scope == "Last 10": rows = rows.tail(10)
    elif scope == "Last 5": rows = rows.tail(5)
    elif scope == "Individual Match" and match_id is not None: rows = rows[rows.canonical_match_id.astype(str).eq(str(match_id))]
    return rows


def prepare_team_events(events: pd.DataFrame, matches: pd.DataFrame, club_id: str, layer: str = "Activity Density") -> pd.DataFrame:
    ids = set(matches.get("canonical_match_id", pd.Series(dtype=object)).astype(str))
    selected = events[events.get("club_id", pd.Series(index=events.index, dtype=object)).astype(str).eq(str(club_id)) &
                      events.get("canonical_match_id", pd.Series(index=events.index, dtype=object)).astype(str).isin(ids)].copy()
    selected = add_plot_coordinates(selected)
    types = EVENT_LAYERS.get(layer)
    if layer == "Key Passes": selected = selected[selected.get("is_key_pass", False).fillna(False).astype(bool)]
    elif layer == "Crosses": selected = selected[selected.get("qualifiers", "").astype(str).str.contains("Cross", case=False, na=False)]
    elif types is not None: selected = selected[selected.event_type.astype(str).isin(types)]
    return selected


def prepare_team_tactical_profile(matches: pd.DataFrame, events: pd.DataFrame, club_id: str, **filters: object) -> dict[str, object]:
    selected = filter_tactical_scope(matches, club_id, **filters)
    activity = prepare_team_events(events, selected, club_id)
    empty_zones = {"events": 0, "center_x": np.nan, "center_y": np.nan, "defensive_third_share": np.nan,
                   "middle_third_share": np.nan, "final_third_share": np.nan, "left_share": np.nan,
                   "center_share": np.nan, "right_share": np.nan, "box_count": 0, "box_share": np.nan}
    return {"matches": selected, "summary": _aggregate_matches(selected), "events": activity,
            "zones": event_activity_by_zone(activity) if not activity.empty else empty_zones}


def prepare_team_fantasy_matchups(total: pd.DataFrame, position: pd.DataFrame, club_id: str) -> dict[str, object]:
    observed = _club(total, club_id)
    rows = _club(position, club_id)
    metrics = [c for c in ("fantasy_points_allowed", "ghost_allowed", "goals_allowed", "assists_allowed", "key_passes_allowed",
                            "tackles_won_allowed", "accurate_crosses_allowed", "interceptions_allowed", "clearances_allowed", "aerial_wins_allowed") if c in rows]
    grouped = rows.groupby("position_group", as_index=True).agg(matches_observed=("canonical_match_id", "nunique"), **{c: (c, "sum") for c in metrics}) if not rows.empty else pd.DataFrame()
    grouped = grouped.reindex(["GK", "DEF", "MID", "FWD"])
    if "fantasy_points_allowed" in grouped:
        grouped["fpts_per_match"] = grouped.fantasy_points_allowed / grouped.matches_observed
        grouped["ghost_per_match"] = grouped.ghost_allowed / grouped.matches_observed
    grouped.index.name = "position_group"
    return {"matches": observed.canonical_match_id.nunique() if not observed.empty else 0,
            "summary": observed[metrics].sum(min_count=1) if metrics else pd.Series(dtype=float), "positions": grouped.reset_index()}


def prepare_team_historical_comparison(current_club_id: str, historical_matches: pd.DataFrame) -> dict[str, object]:
    historical_id = historical_club_id(current_club_id)
    rows = _club(historical_matches, historical_id)
    return {"historical_club_id": historical_id, "available": not rows.empty, "matches": rows,
            "summary": _aggregate_matches(rows) if not rows.empty else pd.Series(dtype=object)}
