"""Pure cache-to-table normalization; this module has no network imports."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from fantrax.live.config import LiveSeasonConfig


DATASET_COLUMNS = {
    "league_teams": ("season_id", "league_id", "manager_id", "manager_name", "fantasy_team_id", "fantasy_team_name", "draft_slot", "active", "source", "last_refreshed"),
    "current_rosters": ("season_id", "observed_at", "source_retrieved_at", "scoring_period", "period", "manager_id", "manager_name", "fantasy_team_id", "fantasy_team_name", "fantrax_player_id", "registry_player_id", "canonical_name", "player_name", "premier_league_club", "club", "fantrax_position", "roster_status", "lineup_status", "active", "reserve", "injured_reserve", "acquired_via", "acquired_date", "source", "validation_status", "last_refreshed"),
    "league_standings": ("season_id", "period", "rank", "manager_id", "manager", "fantasy_team_id", "team", "wins", "draws", "losses", "points", "fantasy_points_for", "fantasy_points_against", "games_played", "streak", "source", "source_retrieved_at", "last_refreshed"),
    "weekly_matchups": ("season_id", "period", "matchup_id", "home_manager", "away_manager", "home_team_id", "away_team_id", "home_score", "away_score", "winner", "margin", "status", "source", "source_retrieved_at", "last_refreshed"),
    "manager_week_summary": ("season_id", "period", "manager_id", "manager_name", "fantasy_team_id", "fantasy_team_name", "opponent_manager_id", "opponent_manager_name", "fantasy_points", "opponent_points", "result", "cumulative_wins", "cumulative_draws", "cumulative_losses", "league_points_after_week", "rank_after_week", "points_for_after_week", "points_against_after_week", "starter_points", "bench_points", "optimal_xi_points", "points_missed", "lineup_efficiency_pct", "ghost_points", "xgi", "active_players", "bench_players", "lineup_changes", "manager", "total_score", "opponent", "opponent_score", "record_after_week", "optimal_xi_score", "source_coverage", "source", "last_refreshed"),
    "league_transactions": ("season_id", "transaction_id", "timestamp", "transaction_type", "source_transaction_type", "manager", "team", "player_added", "player_dropped", "trade_partner", "players_sent", "players_received", "waiver_priority", "faab", "fantrax_player_id", "registry_player_id", "source", "source_retrieved_at", "last_refreshed"),
    "player_ownership": ("season_id", "fantrax_player_id", "registry_player_id", "canonical_name", "player_name", "current_manager_id", "current_manager_name", "current_manager", "current_fantasy_team", "current_team", "ownership_status", "roster_status", "lineup_status", "available", "last_change_event", "last_change_at", "last_transaction_type", "last_transaction_at", "last_transaction_date", "source_retrieved_at", "drafted_manager", "drafted_manager_id", "drafted_round", "drafted_overall_pick", "still_with_drafting_manager", "changed_teams_since_draft", "currently_free_agent", "ownership_change_count", "source", "last_refreshed"),
}
DATASET_COLUMNS["manager_week_summary"] = DATASET_COLUMNS["manager_week_summary"][:2] + ("period_completed_at",) + DATASET_COLUMNS["manager_week_summary"][2:]


def empty_dataset(key: str) -> pd.DataFrame:
    return pd.DataFrame(columns=DATASET_COLUMNS[key])


def _records(payload: Any, *keys: str) -> list[dict[str, Any]]:
    value = payload
    if isinstance(payload, dict):
        for key in keys:
            candidate = payload.get(key)
            if isinstance(candidate, (list, dict)):
                value = candidate
                break
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        return [dict(row, _map_key=identifier) if isinstance(row, dict) else {"id": identifier, "value": row} for identifier, row in value.items()]
    return []


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def _metadata_timestamp(path: Path) -> str | None:
    metadata = path.with_suffix(path.suffix + ".metadata.json")
    if metadata.exists():
        return json.loads(metadata.read_text(encoding="utf-8")).get("retrieved_at")
    return None


def load_cached_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_league_teams(payload: Any, config: LiveSeasonConfig, *, refreshed_at: str) -> pd.DataFrame:
    rows = _records(payload, "teams", "teamInfo", "fantasyTeams")
    output = []
    for index, row in enumerate(rows, 1):
        manager = row.get("manager") if isinstance(row.get("manager"), dict) else {}
        output.append({
            "season_id": config.season_id, "league_id": config.league_id,
            "manager_id": _first(row, "managerId", "ownerId") or _first(manager, "id") or _first(row,"id","_map_key"),
            "manager_name": _first(row, "managerName", "ownerName") or _first(manager, "name") or _first(row,"name"),
            "fantasy_team_id": _first(row, "teamId", "id", "_map_key"),
            "fantasy_team_name": _first(row, "teamName", "name"),
            "draft_slot": _first(row, "draftSlot", "draftPosition"), "active": bool(row.get("active", True)),
            "source": "Fantrax getLeagueInfo", "last_refreshed": refreshed_at,
        })
    return pd.DataFrame(output, columns=DATASET_COLUMNS["league_teams"])


def _walk_player_rows(payload: Any, inherited: dict[str, Any] | None = None) -> Iterable[dict[str, Any]]:
    inherited = dict(inherited or {})
    if isinstance(payload, list):
        for item in payload:
            yield from _walk_player_rows(item, inherited)
    elif isinstance(payload, dict):
        context = dict(inherited)
        for source, target in (("teamId", "fantasy_team_id"), ("teamName", "fantasy_team_name"), ("managerId", "manager_id"), ("managerName", "manager_name")):
            if payload.get(source) is not None:
                context[target] = payload[source]
        player_id = _first(payload, "fantraxId", "playerId", "player_id")
        player_name = _first(payload, "playerName", "name")
        if player_id is not None and player_name is not None:
            yield {**context, **payload}
            return
        for value in payload.values():
            if isinstance(value, (dict, list)):
                yield from _walk_player_rows(value, context)


def normalize_rosters(payload: Any, config: LiveSeasonConfig, *, period: int, refreshed_at: str, player_info: dict[str,Any]|None=None, teams: pd.DataFrame|None=None) -> pd.DataFrame:
    output = []
    real_rows=[]
    roster_map=payload.get("rosters") if isinstance(payload,dict) else None
    if isinstance(roster_map,dict):
        team_lookup={str(row.fantasy_team_id):row for row in teams.itertuples()} if teams is not None and not teams.empty else {}
        for team_id,team in roster_map.items():
            if not isinstance(team,dict): continue
            identity=team_lookup.get(str(team_id))
            for item in team.get("rosterItems",[]):
                if isinstance(item,dict): real_rows.append({**item,"playerId":item.get("id"),"fantasy_team_id":team_id,"fantasy_team_name":team.get("teamName"),"manager_id":getattr(identity,"manager_id",team_id),"manager_name":getattr(identity,"manager_name",team.get("teamName"))})
    rows=real_rows or list(_walk_player_rows(payload))
    for row in rows:
        status = str(_first(row, "status", "rosterStatus") or "rostered")
        lineup = str(_first(row, "lineupStatus", "slot", "positionStatus") or status)
        lower = lineup.lower()
        player_id=_first(row,"fantraxId","playerId","player_id","id"); info=(player_info or {}).get(str(player_id),{})
        output.append({
            "season_id": config.season_id, "observed_at": refreshed_at, "source_retrieved_at": refreshed_at, "scoring_period": int(period), "period": int(period), "manager_id": row.get("manager_id") or _first(row, "managerId"),
            "manager_name": row.get("manager_name") or _first(row, "managerName"), "fantasy_team_id": row.get("fantasy_team_id") or _first(row, "teamId"),
            "fantasy_team_name": row.get("fantasy_team_name") or _first(row, "teamName"), "fantrax_player_id": player_id,
            "registry_player_id": pd.NA, "canonical_name": pd.NA, "player_name": _first(row, "playerName", "name"), "premier_league_club": _first(row, "club", "team", "proTeam"), "club": _first(row, "club", "team", "proTeam"),
            "fantrax_position": _first(info,"eligiblePos") or _first(row, "eligiblePos", "position", "positions"), "roster_status": status,
            "lineup_status": lineup, "active": lower in {"active", "starter", "starting"}, "reserve": lower in {"reserve", "bench", "res"}, "injured_reserve": lower in {"ir", "injured reserve", "injured_reserve"},
            "acquired_via": _first(row, "acquiredVia", "acquisitionType"), "acquired_date": _first(row, "acquiredDate"),
            "source": "Fantrax getTeamRosters", "validation_status": "pending", "last_refreshed": refreshed_at,
        })
    return pd.DataFrame(output, columns=DATASET_COLUMNS["current_rosters"])


def join_player_registry(frame: pd.DataFrame, registry: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if frame.empty:
        return frame.copy(), frame.copy()
    lookup = registry[["fantrax_player_id", "registry_player_id", "canonical_name"]].dropna(subset=["fantrax_player_id"]).copy()
    lookup["fantrax_player_id"] = lookup["fantrax_player_id"].astype(str)
    out = frame.drop(columns=["registry_player_id", "canonical_name"], errors="ignore").copy()
    out["fantrax_player_id"] = out["fantrax_player_id"].astype(str)
    out = out.merge(lookup.drop_duplicates("fantrax_player_id"), on="fantrax_player_id", how="left")
    unresolved = out[out["registry_player_id"].isna()][[column for column in ("fantrax_player_id", "player_name", "club", "fantrax_position", "source") if column in out]].drop_duplicates()
    return out, unresolved


def normalize_standings(payload: Any, config: LiveSeasonConfig, *, refreshed_at: str, period: int | None = None) -> pd.DataFrame:
    output = []
    for row in _records(payload, "standings", "rows"):
        record = str(_first(row, "record", "points") or "")
        parts = record.split("-") if record.count("-") == 2 else []
        output.append({
            "season_id": config.season_id, "period": period, "rank": _first(row, "rank"), "manager_id": _first(row, "managerId", "ownerId") or _first(row,"teamId","id"),
            "manager": _first(row, "managerName", "ownerName") or _first(row,"teamName","name"), "fantasy_team_id": _first(row, "teamId", "id"), "team": _first(row, "teamName", "name"),
            "wins": _first(row, "wins") if not parts else parts[0], "draws": _first(row, "draws", "ties") if not parts else parts[1],
            "losses": _first(row, "losses") if not parts else parts[2], "points": _first(row, "tablePoints", "standingsPoints"),
            "fantasy_points_for": _first(row, "totalPointsFor", "pointsFor"), "fantasy_points_against": _first(row, "totalPointsAgainst", "pointsAgainst"),
            "games_played": _first(row, "gamesPlayed"), "streak": _first(row, "streak"), "source": "Fantrax getStandings",
            "source_retrieved_at": refreshed_at, "last_refreshed": refreshed_at,
        })
    return pd.DataFrame(output, columns=DATASET_COLUMNS["league_standings"])


def normalize_matchups(payload: Any, config: LiveSeasonConfig, *, refreshed_at: str) -> pd.DataFrame:
    output = []
    for period_obj in _records(payload, "matchups"):
        period = int(_first(period_obj, "period", "scoringPeriod") or 0)
        for index, row in enumerate(_records(period_obj, "matchupList", "matchups"), 1):
            home, away = row.get("home", {}) or {}, row.get("away", {}) or {}
            home_score, away_score = pd.to_numeric(_first(row, "homeScore") or home.get("score"), errors="coerce"), pd.to_numeric(_first(row, "awayScore") or away.get("score"), errors="coerce")
            winner = pd.NA
            if pd.notna(home_score) and pd.notna(away_score):
                winner = _first(home, "name") if home_score > away_score else _first(away, "name") if away_score > home_score else "Draw"
            output.append({"season_id": config.season_id, "period": period, "matchup_id": _first(row, "matchupId", "id") or f"{period:02d}-{index:02d}",
                "home_manager": _first(home, "managerName", "ownerName", "name"), "away_manager": _first(away, "managerName", "ownerName", "name"),
                "home_team_id": _first(home, "teamId", "id"), "away_team_id": _first(away, "teamId", "id"), "home_score": home_score, "away_score": away_score,
                "winner": winner, "margin": abs(home_score-away_score) if pd.notna(home_score) and pd.notna(away_score) else np.nan,
                "status": _first(row, "status") or ("completed" if pd.notna(home_score) and pd.notna(away_score) else "scheduled"),
                "source": "Fantrax getLeagueInfo", "source_retrieved_at": refreshed_at, "last_refreshed": refreshed_at})
    return pd.DataFrame(output, columns=DATASET_COLUMNS["weekly_matchups"])


TRANSACTION_TYPES = {"draft":"draft", "add":"add", "drop":"drop", "waiver":"waiver", "trade":"trade", "commissioner":"commissioner action"}


def normalize_transactions(payload: Any, config: LiveSeasonConfig, *, refreshed_at: str) -> pd.DataFrame:
    output=[]
    for index,row in enumerate(_records(payload,"transactions","rows"),1):
        raw=str(_first(row,"transactionType","type") or "unknown"); lower=raw.lower()
        normalized=next((value for key,value in TRANSACTION_TYPES.items() if key in lower),"unknown")
        output.append({"season_id":config.season_id,"transaction_id":_first(row,"transactionId","id") or f"unkeyed-{index}","timestamp":_first(row,"timestamp","date","createdAt"),
            "transaction_type":normalized,"source_transaction_type":raw,"manager":_first(row,"manager","managerName"),"team":_first(row,"team","teamName"),
            "player_added":_first(row,"playerAdded","addedPlayer"),"player_dropped":_first(row,"playerDropped","droppedPlayer"),"trade_partner":_first(row,"tradePartner"),
            "players_sent":_first(row,"playersSent"),"players_received":_first(row,"playersReceived"),"waiver_priority":_first(row,"waiverPriority"),"faab":_first(row,"faab","bid"),
            "fantrax_player_id":_first(row,"fantraxPlayerId","playerId"),"registry_player_id":pd.NA,"source":"Fantrax cached transaction export","source_retrieved_at":refreshed_at,"last_refreshed":refreshed_at})
    return pd.DataFrame(output,columns=DATASET_COLUMNS["league_transactions"])
