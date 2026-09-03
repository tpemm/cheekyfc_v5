"""Provider-neutral club and fixture normalization.

The functions in this module are deliberately framework-free.  Acquisition is
performed elsewhere; views consume the registered CSV products through
``DataManager``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


REQUIRED_CLUB_COLUMNS = (
    "canonical_club_id", "canonical_name", "short_name", "abbreviation",
    "fantrax_code", "football_data_team_id", "aliases",
)


def load_clubs(path: str | Path) -> pd.DataFrame:
    clubs = pd.read_csv(path, dtype={"football_data_team_id": "string"})
    missing = set(REQUIRED_CLUB_COLUMNS).difference(clubs.columns)
    if missing:
        raise ValueError(f"Club registry missing columns: {sorted(missing)}")
    if len(clubs) != 20 or clubs["canonical_club_id"].duplicated().any():
        raise ValueError("The 2026/27 club registry must contain 20 unique clubs")
    return clubs


def alias_map(clubs: pd.DataFrame) -> dict[str, str]:
    """Return an exact, case-insensitive alias map; never fuzzy matches."""
    result: dict[str, str] = {}
    for row in clubs.itertuples(index=False):
        values = [row.canonical_club_id, row.canonical_name, row.short_name,
                  row.abbreviation, row.fantrax_code]
        values.extend(str(row.aliases).split("|"))
        for value in values:
            key = str(value).strip().casefold()
            if key and key != "nan":
                if key in result and result[key] != row.canonical_club_id:
                    raise ValueError(f"Ambiguous club alias: {value}")
                result[key] = row.canonical_club_id
    return result


def resolve_club(value: Any, clubs: pd.DataFrame) -> str | None:
    if pd.isna(value):
        return None
    return alias_map(clubs).get(str(value).strip().casefold())


def canonicalize_matches(raw: pd.DataFrame, clubs: pd.DataFrame, *,
                         retrieved_at: str | None = None) -> pd.DataFrame:
    """Normalize one provider row per match into the canonical architecture."""
    by_provider = {str(row.football_data_team_id): row for row in clubs.itertuples(index=False)}
    rows: list[dict[str, Any]] = []
    retrieved = retrieved_at or datetime.now(timezone.utc).isoformat()
    for match in raw.itertuples(index=False):
        home = by_provider.get(str(match.home_team_id))
        away = by_provider.get(str(match.away_team_id))
        date = pd.to_datetime(match.match_date, errors="coerce", utc=True)
        status = str(match.status or "scheduled").lower()
        rows.append({
            "match_id": f"fdio:{match.match_id}", "season": "2627",
            "competition": "Premier League", "competition_type": "league",
            "date": date.date().isoformat() if pd.notna(date) else pd.NA,
            "kickoff_time": date.isoformat() if pd.notna(date) else pd.NA,
            "home_club_id": getattr(home, "canonical_club_id", pd.NA),
            "away_club_id": getattr(away, "canonical_club_id", pd.NA),
            "home_club": getattr(home, "canonical_name", match.home_team),
            "away_club": getattr(away, "canonical_name", match.away_team),
            "status": status, "round": getattr(match, "game_week", pd.NA),
            "provider_match_id": match.match_id, "fantrax_period": pd.NA,
            "completed": status in {"complete", "completed", "finished"},
            "home_score": getattr(match, "home_score", pd.NA),
            "away_score": getattr(match, "away_score", pd.NA),
            "source": "football-data.io cached normalization", "retrieved_at": retrieved,
        })
    out = pd.DataFrame(rows).drop_duplicates("match_id", keep="last")
    return out.sort_values(["kickoff_time", "match_id"], na_position="last").reset_index(drop=True)


def map_fantrax_periods(matches: pd.DataFrame, periods: pd.DataFrame) -> pd.DataFrame:
    """Map timestamps into authoritative period windows, supporting DGWs."""
    out = matches.copy()
    out["fantrax_period"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
    kickoff = pd.to_datetime(out["kickoff_time"], errors="coerce", utc=True)
    for period in periods.itertuples(index=False):
        start = pd.to_datetime(getattr(period, "period_start"), errors="coerce", utc=True)
        end = pd.to_datetime(getattr(period, "period_end"), errors="coerce", utc=True)
        number = pd.to_numeric(getattr(period, "fantrax_gw"), errors="coerce")
        if pd.notna(start) and pd.notna(end) and pd.notna(number):
            out.loc[kickoff.between(start, end, inclusive="both"), "fantrax_period"] = int(number)
    return out


def build_team_fixtures(matches: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for match in matches.to_dict("records"):
        common = {k: match.get(k) for k in ("match_id", "date", "kickoff_time", "competition",
                  "competition_type", "status", "fantrax_period", "completed")}
        for side, opponent, venue in (("home", "away", "H"), ("away", "home", "A")):
            gf = match.get(f"{side}_score") if match.get("completed") else pd.NA
            ga = match.get(f"{opponent}_score") if match.get("completed") else pd.NA
            rows.append({**common, "club_id": match.get(f"{side}_club_id"),
                         "club": match.get(f"{side}_club"),
                         "opponent_id": match.get(f"{opponent}_club_id"),
                         "opponent": match.get(f"{opponent}_club"),
                         "home_away": venue, "venue": "Home" if venue == "H" else "Away",
                         "goals_for": gf, "goals_against": ga})
    return pd.DataFrame(rows).sort_values(["club_id", "kickoff_time", "match_id"]).reset_index(drop=True)


def next_league_fixtures(team_fixtures: pd.DataFrame, club_id: str, *,
                         now: Any = None, limit: int = 5) -> pd.DataFrame:
    current = pd.Timestamp.now(tz="UTC") if now is None else pd.to_datetime(now, utc=True)
    kickoff = pd.to_datetime(team_fixtures["kickoff_time"], errors="coerce", utc=True)
    eligible = team_fixtures[
        team_fixtures["club_id"].eq(club_id)
        & team_fixtures["competition_type"].eq("league")
        & ~team_fixtures["completed"].fillna(False).astype(bool)
        & kickoff.ge(current)
    ].copy()
    eligible["_kickoff"] = pd.to_datetime(eligible["kickoff_time"], utc=True)
    return eligible.sort_values(["_kickoff", "match_id"]).drop(columns="_kickoff").head(limit)


def enrich_players_with_fixtures(players: pd.DataFrame, clubs: pd.DataFrame,
                                  fixtures: pd.DataFrame, *, now: Any = None) -> pd.DataFrame:
    """Wire existing player fixture fields through canonical club identity."""
    out=players.copy()
    code_to_id=dict(zip(clubs["fantrax_code"],clubs["canonical_club_id"]))
    out["canonical_club_id"]=out.get("premier_league_club",pd.Series(index=out.index,dtype=object)).map(code_to_id)
    contexts={}
    for club_id in clubs.canonical_club_id:
        upcoming=next_league_fixtures(fixtures,club_id,now=now,limit=10)
        first=upcoming.head(1)
        contexts[club_id]={
            "opening_opponent": pd.NA if first.empty else first.iloc[0]["opponent"],
            "opening_venue": pd.NA if first.empty else first.iloc[0]["home_away"],
            "fixture_ease_next_3":pd.to_numeric(upcoming.head(3).get("overall_fixture_ease"),errors="coerce").mean(),
            "fixture_ease_next_5":pd.to_numeric(upcoming.head(5).get("overall_fixture_ease"),errors="coerce").mean(),
            "fixture_ease_next_10":pd.to_numeric(upcoming.head(10).get("overall_fixture_ease"),errors="coerce").mean(),
            "opening_opponent_elo":pd.NA if first.empty else first.iloc[0].get("opponent_elo",pd.NA),
            "opening_opponent_elo_rank_pl":pd.NA if first.empty else first.iloc[0].get("opponent_elo_rank_pl",pd.NA),
        }
    context=pd.DataFrame.from_dict(contexts,orient="index")
    for field in context.columns:
        out[field]=out["canonical_club_id"].map(context[field])
    out["next_five_fixture_ease_percentile"]=out["fixture_ease_next_5"]
    return out
