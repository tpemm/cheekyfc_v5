from __future__ import annotations

import sys

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd
import soccerdata as sd


# ✅ Change this if your project lives somewhere else
# Portable project configuration
_PROJECT_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT_BOOTSTRAP))
from config.project_paths import PROJECT_ROOT


@dataclass
class UnderstatPlayersConfig:
    league: str = "ENG-Premier League"
    season: str = "2025"  # 2025/26 EPL (start year)
    proxy: Optional[str] = None
    no_cache: bool = False
    force_cache: bool = False
    out_dir: Path = PROJECT_ROOT / "data" / "raw" / "understat"


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def scrape_understat_players(cfg: UnderstatPlayersConfig) -> pd.DataFrame:
    out_understat = cfg.out_dir
    ensure_dir(out_understat)
    out_path = out_understat / "players.parquet"

    us = sd.Understat(
        leagues=cfg.league,
        seasons=cfg.season,
        proxy=cfg.proxy,
        no_cache=cfg.no_cache,
    )

    df = us.read_player_season_stats(force_cache=cfg.force_cache)
    if df is None or df.empty:
        raise RuntimeError("read_player_season_stats() returned no rows.")

    # soccerdata often returns index levels (multiindex)
    df = df.reset_index()

    if "player_id" not in df.columns:
        raise KeyError(f"'player_id' not found. Columns: {list(df.columns)}")

    name_col = None
    for cand in ["player", "player_name", "name"]:
        if cand in df.columns:
            name_col = cand
            break
    if name_col is None:
        raise KeyError(f"Could not find player name col. Columns: {list(df.columns)}")

    df["player_id"] = pd.to_numeric(df["player_id"], errors="coerce").astype("Int64")
    if "team_id" in df.columns:
        df["team_id"] = pd.to_numeric(df["team_id"], errors="coerce").astype("Int64")

    df[name_col] = df[name_col].astype(str).str.strip()
    if "team" in df.columns:
        df["team"] = df["team"].astype(str).str.strip()

    if "minutes" in df.columns:
        df["_mins"] = pd.to_numeric(df["minutes"], errors="coerce").fillna(0)
    else:
        df["_mins"] = 0

    players = (
        df.dropna(subset=["player_id"])
          .sort_values(["player_id", "_mins"], ascending=[True, False])
          .drop_duplicates(subset=["player_id"], keep="first")
          .drop(columns=["_mins"])
          .sort_values("player_id")
          .reset_index(drop=True)
    )

    players.to_parquet(out_path, index=False)
    print(f"Saved Understat players: {out_path} | rows={len(players):,}")
    print("Name column used:", name_col)
    print("Columns:", list(players.columns))
    return players


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Understat EPL player season list to players.parquet")
    parser.add_argument("--league", default="ENG-Premier League", help='e.g. "ENG-Premier League"')
    parser.add_argument("--season", default="2025", help='Start year as string: "2025" for 2025/26')
    parser.add_argument("--proxy", default=None, help="Optional proxy URL")
    parser.add_argument("--no-cache", action="store_true", help="Disable soccerdata cache reads")
    parser.add_argument("--force-cache", action="store_true", help="Force refresh cached response")
    parser.add_argument(
        "--out-dir",
        default=str(PROJECT_ROOT / "data" / "raw" / "understat"),
        help="Output directory (writes players.parquet here)",
    )
    args = parser.parse_args()

    cfg = UnderstatPlayersConfig(
        league=args.league,
        season=args.season,
        proxy=args.proxy,
        no_cache=bool(args.no_cache),
        force_cache=bool(args.force_cache),
        out_dir=Path(args.out_dir),
    )

    scrape_understat_players(cfg)


if __name__ == "__main__":
    main()