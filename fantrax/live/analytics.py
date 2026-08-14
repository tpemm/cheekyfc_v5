"""Presentation-ready live player and manager analytics.

All joins are cache-only and ID based.  Draft-day fields remain read-only inputs.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from fantrax.live.manager_identity import normalize_manager_alias


CURRENT_COLUMNS = (
    "current_fantasy_points", "current_ghost_points", "current_minutes",
    "current_starts", "current_appearances", "current_xg", "current_xa",
    "current_xgi", "current_points_per_game", "current_points_per_90",
    "current_ghost_per_90", "current_xgi_per_90", "rolling_form",
)


def _id(frame: pd.DataFrame) -> pd.Series:
    return frame.get("fantrax_player_id", pd.Series(index=frame.index, dtype=object)).astype("string")


def _first(frame: pd.DataFrame, names: tuple[str, ...], default: Any = pd.NA) -> pd.Series:
    for name in names:
        if name in frame:
            return frame[name]
    return pd.Series(default, index=frame.index)


def _num(frame: pd.DataFrame, names: tuple[str, ...]) -> pd.Series:
    return pd.to_numeric(_first(frame, names), errors="coerce")


def build_live_player_analytics(
    pool: pd.DataFrame, ownership: pd.DataFrame, rosters: pd.DataFrame,
    draft_rankings: pd.DataFrame, draft_results: pd.DataFrame,
    roster_events: pd.DataFrame, *, season_id: str = "2627",
) -> pd.DataFrame:
    """Build one row per Fantrax player, preserving missing analytical values."""
    base = pool.copy()
    if base.empty:
        base = ownership[[c for c in ownership if c in {"fantrax_player_id", "player_name"}]].copy()
    base["fantrax_player_id"] = _id(base)
    base = base.drop_duplicates("fantrax_player_id", keep="first")
    # Roster-only IDs can be absent from the preseason export. Keep them explicit
    # rather than silently losing current ownership or guessing an identity.
    if not ownership.empty:
        missing = ownership[~_id(ownership).isin(set(base["fantrax_player_id"].dropna()))].copy()
        if not missing.empty:
            missing["fantrax_player_id"] = _id(missing)
            base = pd.concat([base, missing], ignore_index=True, sort=False)
    out = pd.DataFrame({"fantrax_player_id": base["fantrax_player_id"]})
    out["season_id"] = str(season_id)
    out["player_name"] = _first(base, ("fantrax_player_name", "player_name", "canonical_name"))
    out["premier_league_club"] = _first(base, ("fantrax_current_team", "current_team", "club"))
    out["fantrax_position"] = _first(base, ("fantrax_position", "position_2627"))
    out["fantrax_projected_points"] = _num(base, ("fantrax_projected_points", "projected_points"))

    rankings = draft_rankings.copy()
    if not rankings.empty:
        rankings["fantrax_player_id"] = _id(rankings)
        rankings = rankings.drop_duplicates("fantrax_player_id")
        keep = [c for c in rankings if c != "player_name"]
        out = out.merge(rankings[keep], on="fantrax_player_id", how="left", suffixes=("", "_draft"))
        out["player_name"] = out["player_name"].fillna(_first(out, ("canonical_name", "historical_name")))
        out["premier_league_club"] = out["premier_league_club"].fillna(_first(out, ("team_2627", "current_team_code")))
        out["fantrax_position"] = out["fantrax_position"].fillna(_first(out, ("fantrax_position_eligibility", "position_2627")))

    own = ownership.copy()
    if not own.empty:
        own["fantrax_player_id"] = _id(own)
        own = own.drop_duplicates("fantrax_player_id", keep="last")
        ownership_columns = [c for c in ("fantrax_player_id", "registry_player_id", "canonical_name", "ownership_status", "current_manager_id", "current_manager_name", "current_fantasy_team", "roster_status", "lineup_status", "available", "ownership_change_count", "last_change_event", "last_change_at", "drafted_manager", "drafted_manager_id", "drafted_round", "drafted_overall_pick", "still_with_drafting_manager", "currently_free_agent") if c in own]
        out = out.merge(own[ownership_columns], on="fantrax_player_id", how="left", suffixes=("", "_ownership"))

    drafted = draft_results.copy()
    if not drafted.empty:
        drafted["fantrax_player_id"] = _id(drafted)
        drafted = drafted.sort_values("overall_pick", key=lambda x: pd.to_numeric(x, errors="coerce")).drop_duplicates("fantrax_player_id")
        origin = pd.DataFrame({
            "fantrax_player_id": drafted["fantrax_player_id"],
            "drafted": True,
            "drafted_manager_result": _first(drafted, ("manager", "drafted_manager")),
            "draft_round": _num(drafted, ("round", "draft_round")),
            "overall_pick": _num(drafted, ("overall_pick",)),
        })
        out = out.merge(origin, on="fantrax_player_id", how="left")
    else:
        out["drafted"] = False
    out["drafted"] = out["drafted"].fillna(False).astype(bool)
    if "drafted_manager_result" in out:
        origin_manager=out.pop("drafted_manager_result")
        out["drafted_manager"] = out["drafted_manager"].fillna(origin_manager) if "drafted_manager" in out else origin_manager
    out["draft_round"] = _num(out, ("draft_round", "drafted_round"))
    out["overall_pick"] = _num(out, ("overall_pick", "drafted_overall_pick"))
    out["draft_rank"] = _num(out, ("overall_rank", "draft_rank"))
    out["adp"] = _num(out, ("fantrax_adp", "adp"))
    out["draft_score"] = _num(out, ("draft_score", "Draft Score"))
    out["fantrax_projected_points"] = _num(out, ("fantrax_projected_points", "projected_points"))
    out["canonical_position"] = _first(out, ("position_2627", "current_position", "fantrax_position")).astype("string").str.split(",").str[0]
    out["available"] = out.get("available", pd.Series(True, index=out.index)).fillna(True).astype(bool)
    out["ownership_status"] = out.get("ownership_status", pd.Series(index=out.index, dtype=object)).fillna("Free Agent")
    out["currently_free_agent"] = out.get("currently_free_agent", out["available"]).fillna(out["available"]).astype(bool)
    out["still_with_drafting_manager"] = out.get("still_with_drafting_manager", pd.Series(False, index=out.index)).fillna(False).astype(bool)
    out["latest_roster_event"] = _first(out, ("last_change_event",))
    out["latest_roster_event_at"] = _first(out, ("last_change_at",))

    # Stable presentation names for proven frozen/historical measures.
    aliases = {
        "historical_fantasy_points": ("fantasy_points_2526",), "historical_points_per_appearance": ("fantasy_ppg_2526",),
        "historical_points_per_90": ("fantasy_fp90_2526",), "historical_ghost_points": ("ghost_points_2526_authoritative", "ghost_points_2526"),
        "historical_ghost_per_appearance": ("ghost_ppg_2526_authoritative", "ghost_ppg_2526"), "historical_ghost_per_90": ("ghost_fp90_2526",),
        "historical_minutes": ("minutes_2526",), "historical_starts": ("starts_2526",), "historical_start_percentage": ("start_rate_2526",),
        "historical_xg": ("understat_xg_2526",), "historical_xa": ("understat_xa_2526",), "historical_xgi_per_90": ("xgi90_2526",),
        "projected_minutes_percentage": ("projected_minutes_share",), "team_strength_percentile": ("team_strength_rating",),
        "next_five_fixture_ease_percentile": ("fixture_ease_next_5",),
    }
    for target, sources in aliases.items(): out[target] = _num(out, sources)
    out["historical_appearances"] = np.where(out.get("fantasy_ppg_2526", pd.Series(index=out.index)).notna(), _num(out, ("weeks_available",)), np.nan)
    out["historical_points_per_start"] = out["historical_fantasy_points"].div(out["historical_starts"].replace(0, np.nan))
    out["historical_ghost_per_start"] = out["historical_ghost_points"].div(out["historical_starts"].replace(0, np.nan))
    out["historical_xgi"] = out["historical_xg"] + out["historical_xa"]
    minutes = _num(out, ("understat_minutes_2526",))
    out["historical_xg_per_90"] = out["historical_xg"] * 90 / minutes.replace(0, np.nan)
    out["historical_xa_per_90"] = out["historical_xa"] * 90 / minutes.replace(0, np.nan)
    out["historical_minutes_percentage"] = out["historical_minutes"] / (38 * 90) * 100
    for column in CURRENT_COLUMNS: out[column] = np.nan
    out["last_refreshed"] = datetime.now(timezone.utc).isoformat()
    return out.drop_duplicates("fantrax_player_id").reset_index(drop=True)


def expected_record(manager_week: pd.DataFrame) -> pd.DataFrame:
    """Return the established all-play expected-win result by manager.

    Each weekly score is compared with every other score from that completed
    period. Ties count as one half win, matching the finalized 2025/26 page.
    """
    columns = ["manager_id", "expected_wins", "actual_wins", "luck_wins"]
    if manager_week.empty or not {"period", "fantasy_points"}.issubset(manager_week):
        return pd.DataFrame(columns=columns)
    frame = manager_week.dropna(subset=["period", "fantasy_points"]).copy()
    rows = []
    for _, week in frame.groupby("period"):
        scores = pd.to_numeric(week["fantasy_points"], errors="coerce")
        for index, row in week.iterrows():
            score = scores.loc[index]
            opponents = scores.drop(index).dropna()
            if pd.isna(score) or opponents.empty:
                continue
            rows.append({
                "manager_id": row.get("manager_id"),
                "expected_wins": float((opponents.lt(score).sum() + .5 * opponents.eq(score).sum()) / len(opponents)),
                "actual_wins": float(str(row.get("result", "")).upper() == "W"),
            })
    if not rows:
        return pd.DataFrame(columns=columns)
    result = pd.DataFrame(rows).groupby("manager_id", as_index=False).sum(numeric_only=True)
    result["luck_wins"] = result["actual_wins"] - result["expected_wins"]
    return result.reindex(columns=columns)


def build_live_manager_analytics(players: pd.DataFrame, teams: pd.DataFrame, standings: pd.DataFrame, events: pd.DataFrame, draft_results: pd.DataFrame, manager_week: pd.DataFrame | None = None) -> pd.DataFrame:
    """Aggregate current rosters with explicitly minute-weighted historical rates."""
    managers = teams.copy()
    if managers.empty: return pd.DataFrame()
    latest = standings.copy()
    if not latest.empty and "period" in latest:
        periods = pd.to_numeric(latest["period"], errors="coerce"); latest = latest[periods.eq(periods.max())]
    join_key = "manager_id" if "manager_id" in latest and "manager_id" in managers else None
    rows=[]
    for team in managers.to_dict("records"):
        manager_id=team.get("manager_id"); manager_name=team.get("manager_name")
        roster=players[players.get("current_manager_id", pd.Series(index=players.index)).astype(str).eq(str(manager_id))]
        if roster.empty: roster=players[players.get("current_manager_name", pd.Series(index=players.index)).eq(manager_name)]
        standing = latest[latest[join_key].astype(str).eq(str(manager_id))].head(1) if join_key else latest[latest.get("manager", pd.Series(index=latest.index)).eq(manager_name)].head(1)
        s=standing.iloc[0] if not standing.empty else pd.Series(dtype=object)
        def series(col: str) -> pd.Series:
            return pd.to_numeric(roster[col],errors="coerce") if col in roster else pd.Series(index=roster.index,dtype=float)
        minutes=series("historical_minutes"); understat_minutes=series("understat_minutes_2526")
        fp=series("historical_fantasy_points"); ghost=series("historical_ghost_points"); xgi=series("historical_xgi")
        drafted_aliases={normalize_manager_alias(manager_name),normalize_manager_alias(team.get("fantasy_team_name"))}
        drafted_total = int(_first(draft_results, ("manager", "drafted_manager")).map(normalize_manager_alias).isin(drafted_aliases).sum()) if not draft_results.empty else 0
        retained=int(roster.get("still_with_drafting_manager",pd.Series(dtype=bool)).fillna(False).astype(bool).sum())
        involved=events[(events.get("previous_manager_id",pd.Series(index=events.index)).astype(str).eq(str(manager_id))) | (events.get("new_manager_id",pd.Series(index=events.index)).astype(str).eq(str(manager_id)))] if not events.empty else events
        def mean(col: str) -> float: return series(col).mean()
        current_minutes=series("current_minutes"); current_points=series("current_fantasy_points"); current_ghost=series("current_ghost_points"); current_xgi=series("current_xgi")
        current_starts=series("current_starts"); current_apps=series("current_appearances")
        drafted_mask=roster.get("drafted_manager_id",pd.Series(index=roster.index,dtype=object)).astype(str).eq(str(manager_id)) if "drafted_manager_id" in roster else roster.get("still_with_drafting_manager",pd.Series(False,index=roster.index)).fillna(False).astype(bool)
        projection=series("fantrax_projected_points")
        latest_change=involved.sort_values("detected_at").tail(1) if "detected_at" in involved else pd.DataFrame()
        valid_history=minutes.gt(0);valid_understat=understat_minutes.gt(0);valid_current=current_minutes.gt(0)
        rows.append({"season_id":team.get("season_id"),"manager_id":manager_id,"manager_name":manager_name,"fantasy_team_id":team.get("fantasy_team_id"),"fantasy_team_name":team.get("fantasy_team_name"),"draft_slot":team.get("draft_slot"),"draft_grade":pd.NA,"draft_relative_score":pd.NA,
            "current_rank":s.get("rank"),"rank":s.get("rank"),"wins":s.get("wins"),"draws":s.get("draws"),"losses":s.get("losses"),"league_points":s.get("points"),"points_for":s.get("fantasy_points_for"),"points_against":s.get("fantasy_points_against"),"games_played":s.get("games_played"),"streak":s.get("streak"),
            "roster_count":len(roster),"active_count":int(roster.get("lineup_status",pd.Series(dtype=str)).eq("ACTIVE").sum()),"reserve_count":int(roster.get("lineup_status",pd.Series(dtype=str)).eq("RESERVE").sum()),"ir_count":int(roster.get("roster_status",pd.Series(dtype=str)).isin(["IR","INJURED_RESERVE"]).sum()),
            "current_roster_projection":projection.sum(min_count=1),"average_projection":mean("fantrax_projected_points"),"average_draft_score":mean("draft_score"),"average_adp":mean("adp"),
            "historical_points_per_90":fp[valid_history].sum(min_count=1)*90/minutes[valid_history].sum() if valid_history.any() else np.nan,
            "historical_ghost_per_90":ghost[valid_history].sum(min_count=1)*90/minutes[valid_history].sum() if valid_history.any() else np.nan,
            "historical_xgi_per_90":xgi[valid_understat].sum(min_count=1)*90/understat_minutes[valid_understat].sum() if valid_understat.any() else np.nan,
            "historical_start_pct":mean("historical_start_percentage"),"historical_minutes_pct":mean("historical_minutes_percentage"),
            "current_roster_points":current_points.sum(min_count=1),"current_roster_points_per_game":current_points.sum(min_count=1)/current_apps.sum(min_count=1) if current_apps.sum(min_count=1)>0 else np.nan,"current_roster_points_per_start":current_points.sum(min_count=1)/current_starts.sum(min_count=1) if current_starts.sum(min_count=1)>0 else np.nan,"current_roster_points_per_90":current_points[valid_current].sum(min_count=1)*90/current_minutes[valid_current].sum() if valid_current.any() else np.nan,
            "current_roster_ghost":current_ghost.sum(min_count=1),"current_roster_ghost_per_start":current_ghost.sum(min_count=1)/current_starts.sum(min_count=1) if current_starts.sum(min_count=1)>0 else np.nan,"current_roster_ghost_per_90":current_ghost[valid_current].sum(min_count=1)*90/current_minutes[valid_current].sum() if valid_current.any() else np.nan,"current_roster_xgi":current_xgi.sum(min_count=1),"current_roster_xgi_per_90":current_xgi[valid_current].sum(min_count=1)*90/current_minutes[valid_current].sum() if valid_current.any() else np.nan,"current_roster_minutes":current_minutes.sum(min_count=1),"current_roster_starts":current_starts.sum(min_count=1),"current_roster_start_pct":current_starts.sum(min_count=1)/current_apps.sum(min_count=1)*100 if current_apps.sum(min_count=1)>0 else np.nan,
            "projected_minutes_percentage":mean("projected_minutes_percentage"),"drafted_players_retained":retained,"drafted_players_total":drafted_total,"current_roster_drafted_by_manager":int(drafted_mask.sum()),"current_roster_acquired_later":int((~drafted_mask).sum()),
            "draft_retention_pct":retained/drafted_total*100 if drafted_total else np.nan,"draft_retention_percentage":retained/drafted_total*100 if drafted_total else np.nan,"players_added":int(involved.get("event_type",pd.Series(dtype=str)).eq("PLAYER_ADDED").sum()),"players_dropped":int(involved.get("event_type",pd.Series(dtype=str)).eq("PLAYER_DROPPED").sum()),"roster_change_count":len(involved),"ownership_changes":len(involved),"latest_roster_change":latest_change.iloc[0].get("event_type") if not latest_change.empty else pd.NA,"latest_roster_change_at":latest_change.iloc[0].get("detected_at") if not latest_change.empty else pd.NA})
    output=pd.DataFrame(rows)
    weekly=manager_week if manager_week is not None else pd.DataFrame()
    if not weekly.empty:
        complete=weekly.dropna(subset=["fantasy_points"]) if "fantasy_points" in weekly else pd.DataFrame()
        summaries=[]
        for manager_id,part in complete.groupby("manager_id"):
            scores=pd.to_numeric(part["fantasy_points"],errors="coerce").dropna()
            summaries.append({"manager_id":manager_id,"average_weekly_score":scores.mean(),"weekly_score_std":scores.std(),"median_weekly_score":scores.median(),"high_score":scores.max(),"low_score":scores.min(),"form":" ".join(part.sort_values("period")["result"].dropna().astype(str).tail(5))})
        output=output.merge(pd.DataFrame(summaries),on="manager_id",how="left") if summaries else output
        luck=expected_record(weekly)
        if not luck.empty: output=output.merge(luck,on="manager_id",how="left")
    return output


def build_live_position_strength(players: pd.DataFrame, managers: pd.DataFrame) -> pd.DataFrame:
    """Assign each player once by canonical position and rank manager groups."""
    rostered=players[~players.get("available",pd.Series(True,index=players.index)).fillna(True)].copy()
    rostered["position_group"] = rostered.get("canonical_position", "").map({"G":"Defense + Goalkeeper","D":"Defense + Goalkeeper","M":"Midfield","F":"Forwards"}).fillna("Bench")
    rows=[]
    for (manager_id,group), part in rostered.groupby(["current_manager_id","position_group"],dropna=False):
        rows.append({"season_id":part["season_id"].iat[0],"manager_id":manager_id,"position_group":group,"player_count":len(part),"raw_value":pd.to_numeric(part["draft_score"],errors="coerce").mean()})
    result=pd.DataFrame(rows)
    if not result.empty: result["league_rank"] = result.groupby("position_group")["raw_value"].rank(ascending=False,method="min")
    return result
