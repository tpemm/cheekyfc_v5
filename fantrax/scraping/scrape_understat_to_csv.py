"""
scrape_understat_to_csv.py

Scrape Understat (via soccerdata) and write CSVs to a chosen output folder.

Outputs (CSV):
- understat_schedule_<season_id>_<league_sanitized>.csv
- understat_player_match_stats_<season_id>_<league_sanitized>.csv
- understat_players_season_<season_id>_<league_sanitized>.csv

Enriches player_match_stats with:
- league + season + season_id
- game_id + kickoff_datetime + home_team + away_team + gameweek (best effort)
- team_id + team_name (best effort)
- player_id + player_name (best effort)
"""

from __future__ import annotations

import sys

import argparse
import re
from pathlib import Path
from typing import List, Optional, Set

import pandas as pd
import soccerdata as sd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:sys.path.insert(0,str(PROJECT_ROOT))
from core.services.machine_role import require_commissioner_writer
DEFAULT_OUT_DIR = str(PROJECT_ROOT / "data" / "raw" / "understat")
DEFAULT_LEAGUE = "ENG-Premier League"
DEFAULT_SEASON = "2025/26"


# -----------------------------
# Helpers
# -----------------------------
def sanitize_filename(s: str) -> str:
    s = s.strip().replace(" ", "_")
    s = re.sub(r"[^A-Za-z0-9_\-]+", "", s)
    return s


def parse_season(season_str: str) -> tuple[int, str]:
    season_str = str(season_str).strip()
    if "/" in season_str:
        a, b = season_str.split("/", 1)
        start = int(a)
        end2 = int(b[-2:])
        season_id = f"{start % 100:02d}{end2:02d}"
        return start, season_id
    start = int(season_str)
    season_id = f"{start % 100:02d}{(start + 1) % 100:02d}"
    return start, season_id


def parse_gws(gws_str: str) -> Optional[Set[int]]:
    if not gws_str or gws_str.strip().upper() == "ALL":
        return None
    out: Set[int] = set()
    parts = [p.strip() for p in gws_str.split(",") if p.strip()]
    for p in parts:
        if "-" in p:
            lo, hi = p.split("-", 1)
            lo_i, hi_i = int(lo), int(hi)
            for x in range(min(lo_i, hi_i), max(lo_i, hi_i) + 1):
                out.add(x)
        else:
            out.add(int(p))
    return out


def coerce_int(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype("Int64")


def flatten_index(df: pd.DataFrame) -> pd.DataFrame:
    """
    If soccerdata returns a MultiIndex (common), reset it into columns.
    Avoid duplicate column names after reset.
    """
    if isinstance(df.index, pd.MultiIndex) or (df.index.names and any(n is not None for n in df.index.names)):
        out = df.reset_index(drop=False)
    else:
        out = df.copy()

    # If reset_index created duplicates, make them unique
    if out.columns.duplicated().any():
        new_cols = []
        seen = {}
        for c in out.columns:
            if c not in seen:
                seen[c] = 0
                new_cols.append(c)
            else:
                seen[c] += 1
                new_cols.append(f"{c}__idx{seen[c]}")
        out.columns = new_cols

    return out


def ensure_game_id(df: pd.DataFrame, table_name: str) -> pd.DataFrame:
    out = flatten_index(df)

    candidates = ["game_id", "match_id", "id"]
    found = None
    for c in candidates:
        if c in out.columns:
            found = c
            break
    if found is None:
        raise ValueError(
            f"[{table_name}] Could not find a match id column. "
            f"Expected one of {candidates}, got: {list(out.columns)}"
        )
    if found != "game_id":
        out = out.rename(columns={found: "game_id"})
    out["game_id"] = coerce_int(out["game_id"])
    return out


def standardize_schedule_columns(schedule: pd.DataFrame) -> pd.DataFrame:
    s = schedule.copy()

    # Team columns
    if "home_team" not in s.columns and "h" in s.columns:
        s = s.rename(columns={"h": "home_team"})
    if "away_team" not in s.columns and "a" in s.columns:
        s = s.rename(columns={"a": "away_team"})

    # Kickoff datetime candidates
    dt_col = None
    for c in ["kickoff_datetime", "datetime", "date", "match_date", "kickoff_time"]:
        if c in s.columns:
            dt_col = c
            break
    if dt_col is not None and dt_col != "kickoff_datetime":
        s = s.rename(columns={dt_col: "kickoff_datetime"})
    if "kickoff_datetime" in s.columns:
        s["kickoff_datetime"] = pd.to_datetime(s["kickoff_datetime"], errors="coerce")
        # PATCH: normalize to tz-naive (UTC) to avoid merge/filter issues later
        try:
            if getattr(s["kickoff_datetime"].dt, "tz", None) is not None:
                s["kickoff_datetime"] = s["kickoff_datetime"].dt.tz_convert("UTC").dt.tz_localize(None)
        except Exception:
            # If already tz-naive or conversion fails, leave as-is
            pass

    # Understat "gameweek"/"round" (not Fantrax GW)
    gw_col = None
    for c in ["gameweek", "round", "gw", "week", "matchweek"]:
        if c in s.columns:
            gw_col = c
            break
    if gw_col and gw_col != "gameweek":
        s["gameweek"] = coerce_int(s[gw_col])
    elif "gameweek" in s.columns:
        s["gameweek"] = coerce_int(s["gameweek"])
    else:
        # Best effort inference if missing
        if "kickoff_datetime" in s.columns:
            tmp = s.sort_values("kickoff_datetime").reset_index(drop=True)
            tmp["gameweek"] = ((tmp.index // 10) + 1).astype("Int64")
            s = s.merge(tmp[["game_id", "gameweek"]], on="game_id", how="left")
        else:
            s["gameweek"] = pd.Series(range(1, len(s) + 1), dtype="Int64")

    return s


def upsert_csv(df_new: pd.DataFrame, out_path: Path, key_cols: List[str]) -> pd.DataFrame:
    df_new = df_new.copy()

    missing_keys = [c for c in key_cols if c not in df_new.columns]
    if missing_keys:
        fallback = [c for c in ["game_id", "player_id", "team_id"] if c in df_new.columns]
        if not fallback:
            fallback = [df_new.columns[0]]
        print(
            f"WARNING: upsert keys {key_cols} not present in new df for {out_path.name}. "
            f"Falling back to keys: {fallback}"
        )
        key_cols = fallback

    if out_path.exists():
        df_old = pd.read_csv(out_path)
        combined = pd.concat([df_old, df_new], ignore_index=True, sort=False)
        key_cols = [c for c in key_cols if c in combined.columns]
        if key_cols:
            combined = combined.drop_duplicates(subset=key_cols, keep="last")
        combined.to_csv(out_path, index=False, encoding="utf-8")
        return combined

    df_new.to_csv(out_path, index=False, encoding="utf-8")
    return df_new


def overwrite_csv(df: pd.DataFrame, out_path: Path) -> pd.DataFrame:
    df.to_csv(out_path, index=False, encoding="utf-8")
    return df


def missing_match_schedule(schedule: pd.DataFrame, out_dir: Path, season_id: str, league_slug: str) -> pd.DataFrame:
    """Keep stable cached matches untouched during incremental acquisition."""
    schedule_path=out_dir/f"understat_schedule_{season_id}_{league_slug}.csv"
    players_path=out_dir/f"understat_player_match_stats_{season_id}_{league_slug}.csv"
    complete=set()
    if schedule_path.exists() and players_path.exists():
        prior=pd.read_csv(schedule_path);players=pd.read_csv(players_path)
        valid=prior.get("has_data",pd.Series(False,index=prior.index)).astype(str).str.lower().eq("true")
        for metric in ("home_xg","away_xg"):
            valid &= pd.to_numeric(prior.get(metric,pd.Series(index=prior.index,dtype=float)),errors="coerce").notna()
        complete=set(pd.to_numeric(prior.loc[valid,"game_id"],errors="coerce").dropna()) & set(pd.to_numeric(players.game_id,errors="coerce").dropna())
    has_data=schedule.get("has_data",pd.Series(False,index=schedule.index)).astype(str).str.lower().eq("true")
    return schedule[has_data & ~schedule.game_id.isin(complete)].copy()


# -----------------------------
# Main
# -----------------------------
def main():
    parser = argparse.ArgumentParser(description="Scrape Understat to CSV.")
    parser.add_argument("--season", default=DEFAULT_SEASON, help='Season like "2025/26" or "2025"')
    parser.add_argument("--league", default=DEFAULT_LEAGUE, help='League like "ENG-Premier League"')
    parser.add_argument("--out_dir", default=DEFAULT_OUT_DIR, help="Output directory for CSVs")
    parser.add_argument("--gws", default="ALL", help='Understat gameweeks to filter: "ALL" or "1-5,8,10-12"')
    parser.add_argument("--mode", default="upsert", choices=["upsert", "overwrite"], help="Write mode")
    parser.add_argument("--missing-only", action="store_true", help="Acquire only matches lacking usable cached player/team data")

    args = parser.parse_args()
    require_commissioner_writer("Understat provider-cache write")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    start_year, season_id = parse_season(args.season)
    league = args.league
    league_slug = sanitize_filename(league)
    gws_set = parse_gws(args.gws)

    print("Understat scrape")
    print(f"  season: {args.season} -> {season_id}")
    print(f"  league: {league}")
    print(f"  out:    {out_dir}")
    print(f"  gws:    {'ALL' if gws_set is None else sorted(list(gws_set))}")
    print(f"  mode:   {'APPEND/UPSERT' if args.mode == 'upsert' else 'OVERWRITE'}")

    us = sd.Understat(leagues=league, seasons=start_year)

    # Pull data (may come back as MultiIndex)
    schedule_raw = us.read_schedule()
    schedule = standardize_schedule_columns(ensure_game_id(schedule_raw, "schedule"))
    if gws_set is not None:
        schedule = schedule[schedule.gameweek.isin(gws_set)].copy()
    if args.missing_only:
        schedule = missing_match_schedule(schedule,out_dir,season_id,league_slug)
        if schedule.empty:
            print("NO_ACTION_REQUIRED: provider has no missing completed match payloads available.")
            return
    pms_raw = us.read_player_match_stats(match_id=schedule.game_id.dropna().astype(int).tolist())
    players_season_raw = us.read_player_season_stats()

    # Flatten + standardize keys
    pms = ensure_game_id(pms_raw, "player_match_stats")
    players_season = flatten_index(players_season_raw)

    # Add season context columns
    for df in (schedule, pms):
        if "league" not in df.columns:
            df["league"] = league
        if "season" not in df.columns:
            df["season"] = args.season
        if "season_id" not in df.columns:
            df["season_id"] = season_id

    # Standardize schedule columns
    schedule = standardize_schedule_columns(schedule)

    # Filter to requested UNDERSTAT gameweeks (not Fantrax)
    if gws_set is not None:
        if "gameweek" not in schedule.columns:
            raise ValueError("Could not determine Understat gameweek from schedule; cannot filter.")
        schedule = schedule[schedule["gameweek"].isin(list(gws_set))].copy()

    # Filter pms to schedule game_ids
    keep_game_ids = set(schedule["game_id"].dropna().astype(int).tolist())
    pms = pms[pms["game_id"].isin(list(keep_game_ids))].copy()

    # Clean schedule columns for enrichment (merge ON game_id only!)
    sched_cols = [c for c in ["game_id", "kickoff_datetime", "gameweek", "home_team", "away_team"] if c in schedule.columns]
    schedule_clean = schedule[sched_cols].drop_duplicates(subset=["game_id"]).copy()

    # Enrich pms
    pms = pms.merge(schedule_clean, on="game_id", how="left")

    # PATCH: ensure kickoff_datetime is tz-naive (UTC) in PMS too
    if "kickoff_datetime" in pms.columns:
        pms["kickoff_datetime"] = pd.to_datetime(pms["kickoff_datetime"], errors="coerce")
        try:
            if getattr(pms["kickoff_datetime"].dt, "tz", None) is not None:
                pms["kickoff_datetime"] = pms["kickoff_datetime"].dt.tz_convert("UTC").dt.tz_localize(None)
        except Exception:
            pass

    # Try to enrich player_name/team_name from players_season if possible
    ps = players_season.copy()
    if "id" in ps.columns and "player_id" not in ps.columns:
        ps = ps.rename(columns={"id": "player_id"})
    if "player_id" in ps.columns:
        ps["player_id"] = coerce_int(ps["player_id"])

    # standardize columns
    if "player_name" not in ps.columns:
        for c in ["player", "name"]:
            if c in ps.columns:
                ps = ps.rename(columns={c: "player_name"})
                break
    if "team_name" not in ps.columns:
        for c in ["team", "squad"]:
            if c in ps.columns:
                ps = ps.rename(columns={c: "team_name"})
                break

    players_clean_cols = [c for c in ["player_id", "player_name", "team_id", "team_name"] if c in ps.columns]
    players_clean = ps[players_clean_cols].copy() if players_clean_cols else None

    if players_clean is not None and "player_id" in pms.columns and "player_id" in players_clean.columns:
        pms["player_id"] = coerce_int(pms["player_id"])
        pms = pms.merge(players_clean, on="player_id", how="left", suffixes=("", "_season"))

    # Add league/season context onto pms (again, but safe)
    pms["league"] = league
    pms["season"] = args.season
    pms["season_id"] = season_id

    # PATCH: write kickoff_datetime as ISO string (stable in CSV)
    if "kickoff_datetime" in schedule.columns:
        schedule["kickoff_datetime"] = pd.to_datetime(schedule["kickoff_datetime"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")
    if "kickoff_datetime" in pms.columns:
        pms["kickoff_datetime"] = pd.to_datetime(pms["kickoff_datetime"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")

    # Output paths
    schedule_path = out_dir / f"understat_schedule_{season_id}_{league_slug}.csv"
    pms_path = out_dir / f"understat_player_match_stats_{season_id}_{league_slug}.csv"
    players_path = out_dir / f"understat_players_season_{season_id}_{league_slug}.csv"

    # Write
    if args.mode == "overwrite":
        schedule_out = overwrite_csv(schedule, schedule_path)
        pms_out = overwrite_csv(pms, pms_path)
        players_out = overwrite_csv(players_season, players_path)
    else:
        schedule_out = upsert_csv(schedule, schedule_path, key_cols=["game_id"])
        pms_keys = ["game_id"] + (["player_id"] if "player_id" in pms.columns else [])
        pms_out = upsert_csv(pms, pms_path, key_cols=pms_keys)
        players_key = ["player_id"] if "player_id" in players_season.columns else ["id"] if "id" in players_season.columns else [players_season.columns[0]]
        players_out = upsert_csv(players_season, players_path, key_cols=players_key)

    # Summary
    print(f"Schedule rows selected: {len(schedule_out)}")
    print(f"Game IDs found:         {schedule_out['game_id'].nunique(dropna=True) if 'game_id' in schedule_out.columns else 'n/a'}")
    print(f"Player match stat rows selected: {len(pms_out)}")
    print(f"Players season rows: {len(players_out)}")
    print("\nWrote:")
    print(f"  {schedule_path}")
    print(f"  {pms_path}")
    print(f"  {players_path}")


if __name__ == "__main__":
    main()
