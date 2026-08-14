from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Set

import pandas as pd
import soccerdata as sd


# ✅ Change this if your project lives somewhere else
PROJECT_ROOT = Path(r"C:\Users\Tommy\fantrax_data")


@dataclass
class UnderstatScrapeConfig:
    league: str = "ENG-Premier League"
    season: str = "2025"  # 2025/26 EPL start year
    proxy: Optional[str] = None
    no_cache: bool = False
    force_cache: bool = False
    only_completed_with_data: bool = True
    out_dir: Path = PROJECT_ROOT / "data" / "raw" / "understat"


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def read_existing_game_ids(player_match_path: Path) -> Set[int]:
    if not player_match_path.exists():
        return set()
    df = pd.read_parquet(player_match_path)
    if "game_id" not in df.columns:
        return set()
    return set(pd.to_numeric(df["game_id"], errors="coerce").dropna().astype(int).unique())


def safe_parquet_append(path: Path, df_new: pd.DataFrame) -> None:
    if path.exists():
        df_old = pd.read_parquet(path)
        df_all = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_all = df_new.copy()

    df_all = df_all.drop_duplicates()

    sort_cols = [c for c in ["season_id", "game_id", "team_id", "player_id"] if c in df_all.columns]
    if sort_cols:
        df_all = df_all.sort_values(sort_cols).reset_index(drop=True)

    df_all.to_parquet(path, index=False)


def scrape_understat_epl(cfg: UnderstatScrapeConfig) -> None:
    out_understat = cfg.out_dir
    ensure_dir(out_understat)

    schedule_path = out_understat / "schedule.parquet"
    player_match_path = out_understat / "player_match_stats.parquet"

    us = sd.Understat(
        leagues=cfg.league,
        seasons=cfg.season,
        proxy=cfg.proxy,
        no_cache=cfg.no_cache,
    )

    # -------------------------
    # 1) schedule
    # -------------------------
    schedule = us.read_schedule(force_cache=cfg.force_cache)
    if "date" in schedule.columns:
        schedule["date"] = pd.to_datetime(schedule["date"], errors="coerce")

    schedule.to_parquet(schedule_path, index=False)
    print(f"Saved schedule: {schedule_path} | rows={len(schedule):,}")

    schedule_filtered = schedule.copy()
    if cfg.only_completed_with_data:
        if "is_result" in schedule_filtered.columns:
            schedule_filtered = schedule_filtered[schedule_filtered["is_result"].astype(bool)]
        if "has_data" in schedule_filtered.columns:
            schedule_filtered = schedule_filtered[schedule_filtered["has_data"].astype(bool)]

    if "game_id" not in schedule_filtered.columns:
        raise KeyError(f"'game_id' not found in schedule. Columns: {list(schedule_filtered.columns)}")

    game_ids = (
        pd.to_numeric(schedule_filtered["game_id"], errors="coerce")
        .dropna()
        .astype(int)
        .unique()
        .tolist()
    )

    # -------------------------
    # 2) incremental logic
    # -------------------------
    existing = read_existing_game_ids(player_match_path)
    new_game_ids = [gid for gid in game_ids if gid not in existing]

    print(f"Schedule matches eligible: {len(game_ids):,}")
    print(f"Already saved matches:     {len(existing):,}")
    print(f"New matches to scrape:     {len(new_game_ids):,}")

    if not new_game_ids:
        print("No new matches to scrape. You're up to date.")
        return

    # -------------------------
    # 3) player match stats
    # -------------------------
    try:
    player_ms = us.read_player_match_stats(
        match_id=new_game_ids,
        force_cache=cfg.force_cache
    )
    except TypeError:
    # newer soccerdata versions removed force_cache
    player_ms = us.read_player_match_stats(match_id=new_game_ids)
    if player_ms is None or len(player_ms) == 0:
        print("WARNING: read_player_match_stats returned no rows.")
        return

    # enforce grain
    dupes = player_ms.duplicated(subset=["game_id", "player_id"]).sum()
    if dupes:
        print(f"WARNING: {dupes} duplicate (game_id, player_id) rows. Dropping duplicates.")
        player_ms = player_ms.drop_duplicates(subset=["game_id", "player_id"], keep="first")

    # stable schema (NO match_id column)
    KEEP = [
        "league_id", "season_id",
        "game_id", "team_id", "player_id",
        "position", "position_id", "minutes",
        "goals", "own_goals", "assists",
        "shots", "xg", "xa",
        "key_passes",
        "yellow_cards", "red_cards",
        "xg_chain", "xg_buildup",
    ]
    player_ms = player_ms[[c for c in KEEP if c in player_ms.columns]].copy()

    safe_parquet_append(player_match_path, player_ms)
    print(f"Saved player match stats: {player_match_path} | new_rows={len(player_ms):,}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Understat EPL schedule + player match stats (incremental).")
    parser.add_argument("--league", default="ENG-Premier League")
    parser.add_argument("--season", default="2025", help='Start year string, e.g. "2025" for 2025/26')
    parser.add_argument("--proxy", default=None)
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--force-cache", action="store_true")
    parser.add_argument("--include-future", action="store_true",
                        help="Include matches even if not completed / no data yet")
    parser.add_argument(
        "--out-dir",
        default=str(PROJECT_ROOT / "data" / "raw" / "understat"),
        help="Output directory for parquet files",
    )
    args = parser.parse_args()

    cfg = UnderstatScrapeConfig(
        league=args.league,
        season=args.season,
        proxy=args.proxy,
        no_cache=bool(args.no_cache),
        force_cache=bool(args.force_cache),
        only_completed_with_data=not bool(args.include_future),
        out_dir=Path(args.out_dir),
    )

    scrape_understat_epl(cfg)


if __name__ == "__main__":
    main()