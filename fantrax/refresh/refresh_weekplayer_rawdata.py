from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import List, Optional, Set, Tuple

import pandas as pd


# =============================================================================
# CONFIG
# =============================================================================

# Portable project configuration
_PROJECT_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT_BOOTSTRAP))
from config.project_paths import PROJECT_ROOT
from fantrax.utils.cli import configure_unicode_console
REFRESH_DIR = PROJECT_ROOT / "fantrax" / "refresh"
SCRAPING_DIR = PROJECT_ROOT / "fantrax" / "scraping"
ANALYTICS_DIR = PROJECT_ROOT / "fantrax" / "analytics"
PYTHON_EXE = Path(sys.executable)

SEASON_ID = "2526"

SCRAPE_ALLPLAYERS = SCRAPING_DIR / "scrape_allplayers_weekly_fantrax.py"
SCRAPE_TEAM_ROSTERS = SCRAPING_DIR / "scrape_team_rosters_weekly_fantrax.py"
SCRAPE_US_PMS = SCRAPING_DIR / "scrape_understat_player_match_stats.py"
SCRAPE_US_PLAYERS = SCRAPING_DIR / "scrape_understat_epl_players.py"
SCRAPE_US_TO_CSV = SCRAPING_DIR / "scrape_understat_to_csv.py"
BUILD_MASTER = ANALYTICS_DIR / "build_master_weekly.py"

# Output checks
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUT_MASTER = PROCESSED_DIR / f"master_player_weekly_{SEASON_ID}.csv"
OUT_UNMAPPED_UNDERSTAT = PROCESSED_DIR / f"unmapped_understat_players_{SEASON_ID}.csv"


# =============================================================================
# Helpers
# =============================================================================

def banner(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80 + "\n")


def run_cmd(cmd: List[str], env: Optional[dict] = None) -> None:
    print("$ " + " ".join(cmd))
    proc = subprocess.run(cmd, env=env)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {proc.returncode}: {' '.join(cmd)}")


def parse_week_selection(s: str) -> List[int]:
    s = (s or "").strip()
    if not s:
        return []
    out: Set[int] = set()
    parts = re.split(r"[,\s]+", s)
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if "-" in p:
            a, b = p.split("-", 1)
            try:
                ia = int(a)
                ib = int(b)
            except Exception:
                continue
            lo, hi = min(ia, ib), max(ia, ib)
            out.update(range(lo, hi + 1))
        else:
            try:
                out.add(int(p))
            except Exception:
                continue
    return sorted([w for w in out if w >= 1])


def last_completed_fantrax_gw() -> int:
    """
    Conservative rule:
      - if a GW "ends today", we treat it as not completed yet
    You can override by choosing Specific weeks and typing that GW.
    """
    # If you ever want to improve this later, we can read SCORING_PERIODS and compare to today.
    # For now, just cap at 27 in your example output when run on 2026-03-02.
    # NOTE: your output already computed 27, so keep that same behavior.
    # We'll compute from scoring periods file if present.
    ref = PROJECT_ROOT / "data" / "reference" / f"fantrax_scoring_periods_{SEASON_ID}.csv"
    if ref.exists():
        df = pd.read_csv(ref)
        # try common columns
        cols = {c.lower(): c for c in df.columns}
        gw_col = cols.get("fantrax_gw") or cols.get("gw")
        end_col = cols.get("period_end") or cols.get("end")
        season_col = cols.get("season")
        if gw_col and end_col:
            x = df.copy()
            if season_col:
                x = x[x[season_col].astype(str).str.contains("2025", na=False) | x[season_col].astype(str).str.contains("2025/26", na=False)]
            x[end_col] = pd.to_datetime(x[end_col], errors="coerce")
            x[gw_col] = pd.to_numeric(x[gw_col], errors="coerce")
            today = pd.Timestamp(date.today())
            done = x[x[end_col] < today]  # strictly less than today => completed
            if len(done) > 0:
                return int(done[gw_col].max())
    # fallback
    return 0


def print_unmapped_understat_summary() -> None:
    banner("Unmapped summary (Understat IDs needing crosswalk)")
    if not OUT_UNMAPPED_UNDERSTAT.exists():
        print(f"Missing: {OUT_UNMAPPED_UNDERSTAT}")
        return
    df = pd.read_csv(OUT_UNMAPPED_UNDERSTAT)
    print(f"unmapped Understat IDs: {len(df):,} -> {OUT_UNMAPPED_UNDERSTAT}")
    if len(df) == 0:
        print("✅ None. Crosswalk is up to date with Understat match data.")
        return
    cols = [c for c in ["understat_player_id", "player_name", "team_name"] if c in df.columns]
    if cols:
        print("\nTop unmapped Understat examples:")
        print(df[cols].head(20).to_string(index=False))


# =============================================================================
# Main
# =============================================================================

def main() -> None:
    configure_unicode_console()
    banner("Refresh: weekplayer raw data (Fantrax + Understat + master build)")

    print("Choose refresh mode:")
    print("  1) AUTO: download missing weeks (completed weeks only)")
    print('  2) Specific weeks: re-download selected week(s) (OVERWRITES; archives old first)')
    print("  3) Rebuild only: do NOT download anything, just rerun Understat+master build\n")

    mode = input("Enter 1 / 2 / 3 (or type AUTO / SPECIFIC / REBUILD): ").strip().lower()
    if mode in {"1", "auto"}:
        mode = "auto"
    elif mode in {"2", "specific"}:
        mode = "specific"
    elif mode in {"3", "rebuild"}:
        mode = "rebuild"
    else:
        raise ValueError(f"Unknown mode: {mode}")

    force_cache = input("Force refresh Understat cache? (y/N): ").strip().lower() in {"y", "yes"}

    # Determine Fantrax week cap (AUTO)
    cap_gw = last_completed_fantrax_gw()
    if mode == "auto":
        if cap_gw <= 0:
            print("AUTO mode: could not determine completed weeks; will SKIP Fantrax downloads.")
            fantrax_env = None
        else:
            print(f"AUTO mode: capping Fantrax downloads at last completed GW = {cap_gw}")
            fantrax_env = os.environ.copy()
            fantrax_env["FANTRAX_START_GW"] = "1"
            fantrax_env["FANTRAX_END_GW"] = str(cap_gw)
            # missing only
            fantrax_env.pop("FANTRAX_ONLY_GWS", None)
            fantrax_env.pop("FANTRAX_FORCE_OVERWRITE", None)
    elif mode == "specific":
        sel = input('Which Fantrax weeks to refresh? e.g. "26" or "25-28,31": ').strip()
        weeks = parse_week_selection(sel)
        if not weeks:
            raise ValueError("No weeks selected.")
        # In specific mode we do NOT delete first. We overwrite by archiving the old file first.
        fantrax_env = os.environ.copy()
        fantrax_env["FANTRAX_ONLY_GWS"] = ",".join(str(w) for w in weeks)
        fantrax_env["FANTRAX_FORCE_OVERWRITE"] = "1"
        # keep start/end for printing (optional)
        fantrax_env["FANTRAX_START_GW"] = str(min(weeks))
        fantrax_env["FANTRAX_END_GW"] = str(max(weeks))
    else:
        fantrax_env = None

    # -------------------------------------------------------------------------
    # Fantrax downloads
    # -------------------------------------------------------------------------
    if mode == "rebuild" or fantrax_env is None:
        banner("Skipping Fantrax downloads (rebuild only)")
    else:
        banner("Running Fantrax downloaders")
        run_cmd([str(PYTHON_EXE), str(SCRAPE_ALLPLAYERS)], env=fantrax_env)
        run_cmd([str(PYTHON_EXE), str(SCRAPE_TEAM_ROSTERS)], env=fantrax_env)

    # -------------------------------------------------------------------------
    # Understat parquet updates
    # -------------------------------------------------------------------------
    banner("Updating Understat parquet (schedule + player_match_stats incremental)")
    cmd = [str(PYTHON_EXE), str(SCRAPE_US_PMS)]
    if force_cache:
        cmd.append("--force-cache")
    run_cmd(cmd)

    banner("Updating Understat players.parquet")
    cmd = [str(PYTHON_EXE), str(SCRAPE_US_PLAYERS)]
    if force_cache:
        cmd.append("--force-cache")
    run_cmd(cmd)

    # -------------------------------------------------------------------------
    # Understat CSVs (upsert)
    # -------------------------------------------------------------------------
    banner("Updating Understat CSVs (upsert)")
    run_cmd([str(PYTHON_EXE), str(SCRAPE_US_TO_CSV), "--mode", "upsert"])

    # -------------------------------------------------------------------------
    # Build master
    # -------------------------------------------------------------------------
    banner("Building processed weekly files + master")
    run_cmd([str(PYTHON_EXE), str(BUILD_MASTER)])

    # -------------------------------------------------------------------------
    # Unmapped: ONLY Understat
    # -------------------------------------------------------------------------
    print_unmapped_understat_summary()

    print("\n✅ Refresh complete.")


if __name__ == "__main__":
    main()
