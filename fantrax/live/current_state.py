"""Read-only hosted Fantrax state. Never publishes or modifies observations."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
import streamlit as st

from fantrax.live.acquisition import fetch_json, validate_api_payload
from fantrax.live.config import load_live_season_config
from fantrax.live.normalization import normalize_league_teams, normalize_rosters, normalize_standings
from fantrax.live.season_state import resolve_scoring_period_state

CACHE_TTL_SECONDS = 120
ROSTER_STATUS_OPTIONS = ("Available", "Rostered", "All")


def acquire_current_state(config, *, fetch=fetch_json, now=None) -> dict[str, Any]:
    """Acquire current pool status separately from period roster/lineup evidence."""
    instant = now or datetime.now(timezone.utc)
    state = dict(healthy=False, retrieved_at=None, attempted_at=instant.isoformat(),
                 current_period=None, source="published snapshot", freshness_state="stale",
                 teams=pd.DataFrame(), rosters=pd.DataFrame(), standings=pd.DataFrame(), errors={})
    endpoint = "getLeagueInfo"
    try:
        league_id = config.require_league_id()
        metadata = fetch("league_metadata", league_id)
        validate_api_payload(metadata)
        teams = normalize_league_teams(metadata, config, refreshed_at=instant.isoformat())
        if len(teams) != config.manager_count or teams.fantasy_team_id.isna().any() or teams.fantasy_team_id.duplicated().any() or teams.manager_id.isna().any():
            raise ValueError("Incomplete league team identities")
        periods = pd.DataFrame(metadata.get("scoringPeriods", [])).rename(columns={
            "number": "period", "startDate": "period_start", "endDate": "period_end"})
        period = resolve_scoring_period_state(periods, league_payload=metadata, now=instant).current_period
        if period is None:
            raise ValueError("Current scoring period unavailable")
        config.validate_period(period)
        player_info = metadata.get("playerInfo")
        if not isinstance(player_info, dict) or not player_info or any(not isinstance(v, dict) for v in player_info.values()):
            raise ValueError("Missing or malformed current playerInfo")
        state.update(metadata=metadata, current_period=period, teams=teams, healthy=True,
                     retrieved_at=instant.isoformat(), source="Fantrax getLeagueInfo.playerInfo", freshness_state="live")
        endpoint = "getTeamRosters"
        payload = fetch("rosters", league_id, period=period)
        validate_api_payload(payload)
        roster_map = payload.get("rosters")
        if payload.get("period") != period or not isinstance(roster_map, dict) or set(roster_map) != set(teams.fantasy_team_id.astype(str)):
            raise ValueError("Incomplete or wrong-period roster response")
        seen = set()
        for team_id, team in roster_map.items():
            if not isinstance(team, dict) or not isinstance(team.get("rosterItems"), list):
                raise ValueError("Missing team roster items")
            for item in team["rosterItems"]:
                if not isinstance(item, dict) or not item.get("id") or str(item["id"]) in seen:
                    raise ValueError("Missing or duplicate roster player identity")
                seen.add(str(item["id"]))
        rosters = normalize_rosters(payload, config, period=period, refreshed_at=instant.isoformat(), teams=teams)
        if len(rosters) != len(seen):
            raise ValueError("Roster normalization lost player identities")
        state["rosters"] = rosters
    except Exception as exc:
        state["errors"][endpoint] = f"{type(exc).__name__}: {exc}"
    # Standings failure must not discard independently validated ownership.
    if state.get("metadata") is not None:
        try:
            payload = fetch("standings", config.require_league_id())
            validate_api_payload(payload)
            standings = normalize_standings(payload, config, refreshed_at=instant.isoformat(), period=state["current_period"])
            if set(standings.fantasy_team_id.astype(str)) != set(state["teams"].fantasy_team_id.astype(str)):
                raise ValueError("Incomplete standings response")
            identities = state["teams"].set_index("fantasy_team_id").manager_id
            standings["manager_id"] = standings.fantasy_team_id.astype(str).map(identities)
            state["standings"] = overlay_manager_names(standings, state["teams"])
        except Exception as exc:
            state["errors"]["getStandings"] = f"{type(exc).__name__}: {exc}"
    pool_ids = list(state.get("metadata", {}).get("playerInfo", {}))
    state["players"] = overlay_player_state(pd.DataFrame({"fantrax_player_id": pool_ids}), pd.DataFrame(), state)
    return state


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False, max_entries=4)
def _cached_state(league_id: str) -> dict[str, Any]:
    from dataclasses import replace
    return acquire_current_state(replace(load_live_season_config(), league_id=league_id))


def get_current_state(*, force=False) -> dict[str, Any]:
    config = load_live_season_config()
    if force:
        _cached_state.clear()
    return _cached_state(config.league_id or "")


def overlay_manager_names(frame: pd.DataFrame, teams: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if teams.empty:
        return out
    key = "fantasy_team_id" if "fantasy_team_id" in out else "manager_id"
    if key not in out:
        return out
    lookup = teams.drop_duplicates(key).set_index(key)
    for column, source in (("manager_name", "manager_name"), ("manager", "manager_name"),
                           ("fantasy_team_name", "fantasy_team_name"), ("team", "fantasy_team_name")):
        if column in out:
            out[column] = out[key].astype(str).map(lookup[source]).fillna(out[column])
    return out


def overlay_player_state(frame: pd.DataFrame, snapshot: pd.DataFrame, state: dict) -> pd.DataFrame:
    """One ownership calculation shared by database, profile, comparison and squads."""
    out = frame.copy()
    if out.empty:
        return out
    ids = out.fantrax_player_id.astype("string")
    fields = ("current_manager_id", "current_manager_name", "ownership_status", "roster_status", "lineup_status", "available")
    # Only the published current snapshot may supply fallback ownership, never player-weeks.
    lookup = snapshot.drop_duplicates("fantrax_player_id").copy() if "fantrax_player_id" in snapshot else pd.DataFrame()
    if not lookup.empty:
        lookup.index = lookup.fantrax_player_id.astype("string")
    for field in fields:
        out[field] = ids.map(lookup[field]) if field in lookup else pd.NA
    out["retrieved_at"] = ids.map(lookup["source_retrieved_at"]) if "source_retrieved_at" in lookup else pd.NA
    out["current_period"] = state.get("current_period") if state["healthy"] else pd.NA
    out["source"] = state["source"]
    out["freshness_state"] = state["freshness_state"]
    out["live_player_status"] = pd.NA
    out["availability_type"] = "UNKNOWN"
    if state["healthy"]:
        statuses = {str(pid): info.get("status") for pid, info in state["metadata"]["playerInfo"].items()}
        out["live_player_status"] = ids.map(statuses)
        status = out.live_player_status
        available = status.isin(["FA", "WW"])
        owned = status.eq("T").fillna(False)
        known = available | owned
        # Unknown/missing codes retain only explicit published fallback evidence.
        out.loc[~known, "freshness_state"] = "stale"
        out.loc[~known, "source"] = "published snapshot"
        out.loc[known, "available"] = available[known]
        out.loc[known, "ownership_status"] = "Rostered"
        out.loc[available, "ownership_status"] = "Available"
        out.loc[known, "retrieved_at"] = state["retrieved_at"]
        out.loc[status.eq("FA").fillna(False), "availability_type"] = "FREE_AGENT"
        out.loc[status.eq("WW").fillna(False), "availability_type"] = "WAIVERS"
        out.loc[owned, "availability_type"] = "OWNED"
        # A period roster is owner evidence only for a player currently reported T.
        # It can never establish availability or carry an owner onto FA/WW rows.
        rosters = state["rosters"].copy()
        for field in ("current_manager_id", "current_manager_name", "roster_status", "lineup_status"):
            out.loc[known, field] = pd.NA
        if not rosters.empty:
            rosters.index = rosters.fantrax_player_id.astype("string")
            manager_ids = ids.map(rosters.manager_id)
            names = state["teams"].drop_duplicates("manager_id").set_index("manager_id").manager_name
            out.loc[owned, "current_manager_id"] = manager_ids[owned]
            out.loc[owned, "current_manager_name"] = manager_ids[owned].map(names)
            for field in ("roster_status", "lineup_status"):
                out.loc[owned, field] = ids[owned].map(rosters[field])
    out["available"] = out.available.astype("string").str.lower().eq("true").fillna(False)
    out["is_available"] = out.available
    out["ownership_state"] = out.ownership_status.fillna("Unknown")
    out["current_manager_display_name"] = out.current_manager_name
    for alias in ("current_manager", "current_fantasy_team", "current_team"):
        out[alias] = out.current_manager_name
    if "drafted_manager_id" in out:
        out["still_with_drafting_manager"] = out.current_manager_id.eq(out.drafted_manager_id).fillna(False)
    if "canonical_player_id" not in out:
        out["canonical_player_id"] = out.get("registry_player_id", pd.NA)
    return out


def filter_roster_status(frame: pd.DataFrame, status: str = "Available") -> pd.DataFrame:
    if status == "All":
        return frame.copy()
    if status == "Available":
        return frame[frame.available.fillna(False)].copy()
    return frame[frame.ownership_status.eq("Rostered")].copy()


def freshness_caption(state: dict) -> str:
    if state["healthy"]:
        suffix = " · standings: cached published snapshot" if "getStandings" in state.get("errors", {}) else ""
        if "getTeamRosters" in state.get("errors", {}):
            suffix += " · owner resolution unavailable"
        return f"Availability: live Fantrax player status · retrieved {state['retrieved_at']} · cache up to {CACHE_TTL_SECONDS}s{suffix}. Unknown statuses use stale published values when available."
    return "Ownership: cached/stale published snapshot · live Fantrax unavailable; last published values retained"


def overlay_current_standings(frame: pd.DataFrame, standings: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if standings.empty or "manager_id" not in out:
        return out
    lookup = standings.drop_duplicates("manager_id").set_index("manager_id")
    for target, source in (("current_rank", "rank"), ("rank", "rank"), ("wins", "wins"),
                           ("draws", "draws"), ("losses", "losses"), ("points_for", "fantasy_points_for"),
                           ("points_against", "fantasy_points_against"), ("games_played", "games_played")):
        if source in lookup:
            values = out.manager_id.astype(str).map(lookup[source])
            out[target] = values.fillna(out[target]) if target in out else values
    return out


def overlay_manager_roster_metrics(managers: pd.DataFrame, players: pd.DataFrame, state: dict) -> pd.DataFrame:
    """Reuse existing roster aggregation, retaining canonical season/lineup analytics."""
    out = overlay_current_standings(overlay_manager_names(managers, state["teams"]), state["standings"])
    if not state["healthy"] or players.empty:
        return out
    from fantrax.live.analytics import build_live_manager_analytics
    current = build_live_manager_analytics(players, state["teams"], state["standings"], pd.DataFrame(), pd.DataFrame()).set_index("manager_id")
    fields = [c for c in current if c.startswith("current_roster_") or c in {
        "roster_count", "active_count", "reserve_count", "ir_count", "historical_points_per_90",
        "historical_ghost_per_90", "historical_xgi_per_90", "projected_minutes_percentage", "drafted_players_retained"}]
    for column in fields:
        out[column] = out.manager_id.astype(str).map(current[column])
    if "drafted_players_total" in out:
        denominator = pd.to_numeric(out.drafted_players_total, errors="coerce").replace(0, float("nan"))
        out["draft_retention_pct"] = out.drafted_players_retained / denominator * 100
    return out
