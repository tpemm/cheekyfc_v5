"""Canonical current-season player-match participation and rate denominators."""
from __future__ import annotations

import numpy as np
import pandas as pd


RATE_DENOMINATORS = {"per_game": "games_played", "per_start": "starts", "per_90": "minutes"}


def add_canonical_rates(frame: pd.DataFrame, metrics: tuple[str, ...]) -> pd.DataFrame:
    """Add rates from the three canonical denominators; never substitute one basis for another."""
    out = frame.copy()
    for metric in metrics:
        if metric not in out:
            continue
        value = pd.to_numeric(out[metric], errors="coerce")
        for suffix, denominator in RATE_DENOMINATORS.items():
            den = pd.to_numeric(out.get(denominator), errors="coerce")
            out[f"{metric}_{suffix}"] = value.div(den.where(den.gt(0)))
            if suffix == "per_90":
                out[f"{metric}_{suffix}"] *= 90
    return out


def _num(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(frame.get(column, pd.Series(index=frame.index, dtype=float)), errors="coerce")


def build_player_match_participation(
    lineups: pd.DataFrame,
    matches: pd.DataFrame,
    weekly: pd.DataFrame,
    understat: pd.DataFrame,
    identity: pd.DataFrame,
    *,
    season: str = "2627",
) -> pd.DataFrame:
    """Build one row per mapped player and acquired match from exact provider evidence."""
    if lineups.empty:
        return pd.DataFrame()
    out = lineups[lineups.get("canonical_player_id").notna()].copy()
    if out.duplicated(["canonical_match_id", "canonical_player_id"]).any():
        raise ValueError("Duplicate canonical player-match lineup rows")
    bridge = identity.dropna(subset=["canonical_player_id", "fantrax_player_id"]).drop_duplicates("canonical_player_id")
    fan_map = dict(zip(bridge.canonical_player_id.astype(str), bridge.fantrax_player_id.astype(str).str.strip("*")))
    us_map = dict(zip(bridge.canonical_player_id.astype(str), bridge.get("understat_player_id", pd.Series(index=bridge.index))))
    out["fantrax_player_id"] = out.canonical_player_id.astype(str).map(fan_map)
    out["understat_player_id"] = out.canonical_player_id.astype(str).map(us_map)
    match_cols = ["canonical_match_id", "date", "home_club_id", "away_club_id", "home_score", "away_score"]
    out = out.merge(matches[match_cols], on="canonical_match_id", how="left", validate="many_to_one")
    out["season"] = season
    period_map=dict(zip(understat.get("canonical_match_id",pd.Series(dtype=object)).astype(str),pd.to_numeric(understat.get("period",pd.Series(dtype=float)),errors="coerce")))
    out["fantrax_period"] = out.canonical_match_id.astype(str).map(period_map).astype("Int64")
    out["venue"] = np.where(out.club_id.eq(out.home_club_id), "H", "A")
    out["opponent_id"] = np.where(out.venue == "H", out.away_club_id, out.home_club_id)
    out["team_goals_for"] = np.where(out.venue == "H", out.home_score, out.away_score)
    out["team_goals_against"] = np.where(out.venue == "H", out.away_score, out.home_score)
    out["team_clean_sheet"] = _num(out, "team_goals_against").eq(0)

    started_ws = out.started.fillna(False).astype(bool)
    sub_on = _num(out, "sub_on_minute")
    sub_off = _num(out, "sub_off_minute")
    out["substitute_used"] = (~started_ws) & sub_on.notna()
    out["unused_substitute"] = (~started_ws) & ~out.substitute_used
    out["appeared"] = started_ws | out.substitute_used
    out["started"] = started_ws
    out["start_source"] = np.where(started_ws | out.bench.fillna(False).astype(bool), "WHOSCORED_LINEUP", "MISSING")
    out["participation_source"] = np.where(out.appeared, "WHOSCORED_LINEUP_SUBSTITUTION", "WHOSCORED_UNUSED_SUBSTITUTE")

    us = understat.copy()
    if not us.empty:
        us["fantrax_player_id"] = us.fantrax_player_id.astype(str).str.strip("*")
        us = us.dropna(subset=["fantrax_player_id"])[["canonical_match_id", "fantrax_player_id", "minutes"]].drop_duplicates(["canonical_match_id", "fantrax_player_id"]).rename(columns={"minutes": "understat_exact_minutes"})
        out = out.merge(us, on=["canonical_match_id", "fantrax_player_id"], how="left", validate="one_to_one")
    else:
        out["understat_exact_minutes"] = np.nan
    ws_minutes = pd.Series(np.nan, index=out.index)
    ws_minutes = ws_minutes.mask(started_ws & sub_off.notna(), sub_off.clip(lower=0, upper=90))
    ws_minutes = ws_minutes.mask(started_ws & sub_off.isna(), 90)
    ws_minutes = ws_minutes.mask(out.substitute_used, (90 - sub_on.clip(lower=0, upper=90)).clip(lower=0))
    out["whoscored_derived_minutes"] = ws_minutes.where(out.appeared)

    weekly_one = weekly.copy()
    weekly_one["fantrax_player_id"] = weekly_one.fantrax_player_id.astype(str).str.strip("*")
    detail = weekly_one.get("current_manager_id", pd.Series(index=weekly_one.index)).notna()
    exact = weekly_one.loc[detail, ["fantrax_player_id", "period", "start", "minutes", "clean_sheets"]].drop_duplicates(["fantrax_player_id", "period"])
    exact = exact.rename(columns={"period": "fantrax_period", "start": "fantrax_exact_start", "minutes": "fantrax_exact_minutes", "clean_sheets": "fantrax_clean_sheets"})
    out = out.merge(exact, on=["fantrax_player_id", "fantrax_period"], how="left", validate="many_to_one")
    # Exact Fantrax period values are match-attributable only when the club has one acquired match.
    club_matches = out.groupby(["club_id", "fantrax_period"])["canonical_match_id"].transform("nunique").eq(1)
    fan_start = _num(out, "fantrax_exact_start").where(club_matches)
    fan_minutes = _num(out, "fantrax_exact_minutes").where(club_matches)
    out["started"] = fan_start.notna().where(fan_start.notna(), started_ws).astype(bool)
    out.loc[fan_start.notna(), "started"] = fan_start[fan_start.notna()].gt(0)
    out.loc[fan_start.notna(), "start_source"] = "FANTRAX_DETAILED_MATCH_ATTRIBUTABLE"
    out["minutes"] = fan_minutes.combine_first(_num(out, "understat_exact_minutes")).combine_first(ws_minutes)
    out["minutes_source"] = "MISSING"
    out.loc[ws_minutes.notna(), "minutes_source"] = "WHOSCORED_LINEUP_SUBSTITUTION_DERIVED"
    out.loc[_num(out, "understat_exact_minutes").notna(), "minutes_source"] = "UNDERSTAT_EXACT_PLAYER_MATCH"
    out.loc[fan_minutes.notna(), "minutes_source"] = "FANTRAX_DETAILED_MATCH_ATTRIBUTABLE"
    out.loc[~out.appeared, "minutes"] = np.nan

    pos = out.fantrax_player_id.map(dict(zip(weekly_one.fantrax_player_id, weekly_one.fantrax_position)))
    out["fantrax_position"] = pos
    primary = pos.astype("string").str.split(r"[,/]", regex=True).str[0].str.strip()
    out["clean_sheet_eligible"] = out.appeared & _num(out, "minutes").ge(60) & primary.isin(["G", "D", "M"])
    derived_cs = (out.team_clean_sheet & out.clean_sheet_eligible).astype(int)
    fan_cs = _num(out, "fantrax_clean_sheets").where(club_matches)
    out["clean_sheet_awarded_or_derived"] = fan_cs.combine_first(derived_cs.where(out.appeared))
    out["clean_sheet_source"] = np.where(fan_cs.notna(), "FANTRAX_DETAILED", np.where(out.appeared, "DERIVED_MATCH_CONTEXT", "NA_NO_APPEARANCE"))
    out["tactical_role"] = out.get("actual_position_standardized")
    out["identity_status"] = "RESOLVED"
    columns = ["season", "canonical_match_id", "fantrax_period", "date", "canonical_player_id", "fantrax_player_id", "whoscored_player_id", "understat_player_id", "club_id", "opponent_id", "venue", "appeared", "started", "substitute_used", "unused_substitute", "minutes", "sub_on_minute", "sub_off_minute", "tactical_role", "formation", "manager_id", "team_goals_for", "team_goals_against", "team_clean_sheet", "clean_sheet_eligible", "clean_sheet_awarded_or_derived", "participation_source", "minutes_source", "start_source", "clean_sheet_source", "identity_status", "fantrax_position"]
    return out.reindex(columns=columns).sort_values(["date", "canonical_match_id", "club_id", "started"], ascending=[True, True, True, False]).reset_index(drop=True)


def overlay_weekly_participation(weekly: pd.DataFrame, participation: pd.DataFrame) -> pd.DataFrame:
    """Promote canonical observed denominators into the current weekly contract."""
    if weekly.empty or participation.empty:
        return weekly.copy()
    observed = participation[participation.appeared].groupby(["fantrax_player_id", "fantrax_period"], as_index=False).agg(
        canonical_appearance=("appeared", "sum"), canonical_start=("started", "sum"), canonical_minutes=("minutes", lambda x: pd.to_numeric(x, errors="coerce").sum(min_count=1)), canonical_clean_sheets=("clean_sheet_awarded_or_derived", lambda x: pd.to_numeric(x, errors="coerce").sum(min_count=1))
    ).rename(columns={"fantrax_period": "period"})
    out = weekly.copy(); out["fantrax_player_id"] = out.fantrax_player_id.astype(str).str.strip("*")
    out = out.merge(observed, on=["fantrax_player_id", "period"], how="left", validate="one_to_one")
    for target in ("appearance", "start", "minutes", "clean_sheets"):
        canonical = f"canonical_{target}"
        mask = out[canonical].notna(); out.loc[mask, target] = out.loc[mask, canonical]
        source = "start_source" if target == "start" else f"{target}_source"
        if source not in out: out[source] = pd.NA
        out.loc[mask, source] = "CANONICAL_PLAYER_MATCH_PARTICIPATION"
    return out.drop(columns=[c for c in out if c.startswith("canonical_") and c in {"canonical_appearance", "canonical_start", "canonical_minutes", "canonical_clean_sheets"}])
