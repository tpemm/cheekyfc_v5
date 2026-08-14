#!/usr/bin/env python3
r"""
refresh_all_fantrax_data.py

Purpose
-------
One-click master refresh runner for the Fantrax analytics project.

This script orchestrates the full project pipeline:

1. Fantrax API raw fetch
2. API JSON transforms
3. API roster transform
4. API validation
5. Fantrax + Understat + master weekly refresh
6. API player lookup refresh/flatten
7. API -> master player bridge rebuild
8. Final gold-table merge
9. Final report

Recommended location:
    C:\Users\Tommy\fantrax_data\scripts\refresh_all_fantrax_data.py

Run:
    python C:\Users\Tommy\fantrax_data\scripts\refresh_all_fantrax_data.py

Modes:
    AUTO
        Normal weekly update.
        - runs API refresh
        - refreshes Fantrax/Understat/master using existing refresh_weekplayer_rawdata.py
        - rebuilds final gold tables

    SPECIFIC
        Refresh selected gameweeks.
        - skips API fetch/transform/validation if API outputs already exist
        - passes through to refresh_weekplayer_rawdata.py specific mode
        - rebuilds final gold tables

    REBUILD
        No Fantrax downloads.
        - skips API fetch/transform/validation if API outputs already exist
        - rebuilds processed/master/gold outputs from existing raw data

    FULL
        Heavy cleanup-style refresh.
        - forces API JSON overwrite
        - asks existing Fantrax refresh script to refresh selected weeks or AUTO based on your choice
        - still relies on the existing downloaders' archive/overwrite logic

Important design
----------------
This does NOT replace your existing scripts.
It coordinates them so you only need one entry point.

Existing scripts remain the source of truth for individual tasks:
    refresh_weekplayer_rawdata.py
    fetch_fantrax_api_data.py
    transform_fantrax_api_json.py
    transform_fantrax_rosters.py OR rosters_by_week.csv script
    validate_fantrax_api_layer.py
    fetch_fantrax_api_player_ids_epl.py
    flatten_fantrax_api_player_lookup.py
    build_name_based_api_player_bridge.py
    merge_master_with_api_rosters_v2.py
"""

from __future__ import annotations

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


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
API_DIR = PROJECT_ROOT / "fantrax" / "api"
ANALYTICS_DIR = PROJECT_ROOT / "fantrax" / "analytics"
SCRAPING_DIR = PROJECT_ROOT / "fantrax" / "scraping"
PYTHON_EXE = Path(sys.executable)

SEASON_ID = "2526"
LEAGUE_ID = "rg1i70pfmdhjhvn3"

REFRESH_WEEKPLAYER = REFRESH_DIR / "refresh_weekplayer_rawdata.py"
FETCH_API = API_DIR / "fetch_fantrax_api_data.py"
TRANSFORM_API = API_DIR / "transform_fantrax_api_json.py"
VALIDATE_API = API_DIR / "validate_fantrax_api_layer.py"
ROSTER_TRANSFORM_CANDIDATES = [
    API_DIR / "transform_fantrax_rosters.py",
    API_DIR / "rosters_by_week.py",
]
FETCH_PLAYER_IDS_EPL = API_DIR / "fetch_fantrax_api_player_ids_epl.py"
FLATTEN_PLAYER_LOOKUP = API_DIR / "flatten_fantrax_api_player_lookup.py"
BUILD_NAME_BRIDGE = API_DIR / "build_name_based_api_player_bridge.py"
MERGE_GOLD = API_DIR / "merge_master_with_api_rosters_v2.py"
BUILD_AWARDS = ANALYTICS_DIR / "build_league_awards_views.py"

REPORT_DIR = PROJECT_ROOT / "data" / "processed" / "refresh_reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

RUN_TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
REPORT_PATH = REPORT_DIR / f"refresh_all_report_{RUN_TIMESTAMP}.txt"


# =============================================================================
# HELPERS
# =============================================================================

def write_report_line(lines: list[str], text: str = "") -> None:
    lines.append(text)
    print(text)


def banner(lines: list[str], title: str) -> None:
    write_report_line(lines)
    write_report_line(lines, "=" * 90)
    write_report_line(lines, title)
    write_report_line(lines, "=" * 90)


def script_exists(path: Path) -> bool:
    return path.exists() and path.is_file()


def pick_roster_transform_script() -> Optional[Path]:
    for p in ROSTER_TRANSFORM_CANDIDATES:
        if script_exists(p):
            return p
    return None


def api_outputs_exist() -> bool:
    """
    SPECIFIC and REBUILD can safely skip API work when these already exist.

    Use AUTO or FULL when you intentionally want updated API standings,
    API rosters, matchup structures, playerInfo, or scoring rules.
    """
    required = [
        PROJECT_ROOT / "raw_data" / "fantrax_api" / "league_info.json",
        PROJECT_ROOT / "raw_data" / "fantrax_api" / "standings.json",
        PROJECT_ROOT / "processed_data" / "fantrax_api" / "rosters_by_week.csv",
        PROJECT_ROOT / "processed_data" / "fantrax_api" / "standings.csv",
        PROJECT_ROOT / "processed_data" / "fantrax_api" / "matchups_by_week.csv",
    ]
    return all(p.exists() for p in required)


def api_player_lookup_exists() -> bool:
    required = [
        PROJECT_ROOT / "processed_data" / "fantrax_api" / "api_player_lookup.csv",
    ]
    return all(p.exists() for p in required)


def run_script(
    lines: list[str],
    script_path: Path,
    args: Optional[list[str]] = None,
    input_text: Optional[str] = None,
    required: bool = True,
) -> bool:
    args = args or []

    if not script_exists(script_path):
        msg = f"Missing script: {script_path}"
        if required:
            raise FileNotFoundError(msg)
        write_report_line(lines, f"SKIP optional: {msg}")
        return False

    cmd = [str(PYTHON_EXE), str(script_path), *args]

    write_report_line(lines, "$ " + " ".join(cmd))

    start = time.time()

    proc = subprocess.run(
        cmd,
        input=input_text,
        text=True,
        cwd=str(PROJECT_ROOT),
    )

    elapsed = time.time() - start
    write_report_line(lines, f"Exit code: {proc.returncode} | elapsed: {elapsed:.1f}s")

    if proc.returncode != 0:
        msg = f"FAILED script: {script_path.name} (exit code {proc.returncode})"
        if required:
            raise RuntimeError(msg)
        write_report_line(lines, f"WARNING optional failed: {msg}")
        return False

    return True


def build_refresh_weekplayer_input(mode: str, specific_weeks: Optional[str] = None) -> str:
    """
    Existing refresh_weekplayer_rawdata.py is interactive:
      mode prompt
      force understat cache prompt
      specific weeks prompt if needed

    We feed it input text so this orchestrator can run unattended after initial choice.
    """
    if mode == "auto":
        # 1 = AUTO
        # n = do not force Understat cache for normal weekly updates.
        return "1\nn\n"

    if mode == "specific":
        weeks = specific_weeks
        if not weeks:
            weeks = input('Which Fantrax weeks should be refreshed? e.g. "34" or "33-34": ').strip()
        if not weeks:
            raise ValueError("No weeks entered for SPECIFIC mode.")
        # 2 = SPECIFIC
        # y = force refresh Understat cache because this is a targeted correction.
        # then weeks
        return f"2\ny\n{weeks}\n"

    if mode == "rebuild":
        # 3 = REBUILD
        # n = do not force Understat cache
        return "3\nn\n"

    if mode == "full":
        choice = input(
            "FULL mode: refresh AUTO missing/latest weeks or SPECIFIC weeks? Type AUTO or SPECIFIC: "
        ).strip().lower()

        if choice in {"specific", "s", "2"}:
            weeks = input('Which Fantrax weeks should be force-refreshed? e.g. "1-34" or "34": ').strip()
            if not weeks:
                raise ValueError("No weeks entered for FULL/SPECIFIC mode.")
            # 2 = SPECIFIC, y force Understat cache
            return f"2\ny\n{weeks}\n"

        # default AUTO with force understat cache
        return "1\ny\n"

    raise ValueError(f"Unknown mode: {mode}")


def summarize_expected_outputs(lines: list[str]) -> None:
    banner(lines, "Expected key outputs")

    expected = [
        PROJECT_ROOT / "data" / "processed" / f"master_player_weekly_{SEASON_ID}.csv",
        PROJECT_ROOT / "processed_data" / "fantrax_api" / "rosters_by_week.csv",
        PROJECT_ROOT / "processed_data" / "fantrax_api" / "standings.csv",
        PROJECT_ROOT / "processed_data" / "fantrax_api" / "matchups_by_week.csv",
        PROJECT_ROOT / "processed_data" / "fantrax_api" / "api_player_lookup.csv",
        PROJECT_ROOT / "data" / "reference" / f"api_to_master_player_id_bridge_{SEASON_ID}.csv",
        PROJECT_ROOT / "data" / "processed" / f"manager_player_weekly_{SEASON_ID}.csv",
        PROJECT_ROOT / "data" / "processed" / f"manager_week_summary_{SEASON_ID}.csv",
        PROJECT_ROOT / "data" / "processed" / f"manager_season_summary_{SEASON_ID}.csv",
        PROJECT_ROOT / "data" / "processed" / f"lineup_quality_summary_{SEASON_ID}.csv",
        PROJECT_ROOT / "data" / "processed" / f"matchup_week_summary_{SEASON_ID}.csv",
        PROJECT_ROOT / "data" / "analytics_views" / "league_table.csv",
        PROJECT_ROOT / "data" / "analytics_views" / "award_leaderboards.csv",
        PROJECT_ROOT / "data" / "analytics_views" / "league_hub_cards.csv",
    ]

    for p in expected:
        if p.exists():
            size_mb = p.stat().st_size / (1024 * 1024)
            mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            write_report_line(lines, f"OK   {p} | {size_mb:.2f} MB | modified {mtime}")
        else:
            write_report_line(lines, f"MISS {p}")


# =============================================================================
# MAIN
# =============================================================================

def main() -> None:
    configure_unicode_console()
    lines: list[str] = []

    banner(lines, "Fantrax Analytics — One-Click Refresh")
    write_report_line(lines, f"Started:      {datetime.now().isoformat(timespec='seconds')}")
    write_report_line(lines, f"Project root: {PROJECT_ROOT}")
    write_report_line(lines, f"Python:       {PYTHON_EXE}")
    write_report_line(lines, f"League ID:    {LEAGUE_ID}")

    print()
    print("Choose refresh mode:")
    print("  1) AUTO     Normal weekly update")
    print("  2) SPECIFIC Refresh selected gameweek(s); skips API refresh if files exist")
    print("  3) REBUILD  No downloads; rebuild processed outputs")
    print("  4) FULL     More aggressive refresh")
    print()

    raw_mode = input("Enter 1 / 2 / 3 / 4 or AUTO / SPECIFIC / REBUILD / FULL: ").strip().lower()

    if raw_mode in {"1", "auto", ""}:
        mode = "auto"
    elif raw_mode in {"2", "specific"}:
        mode = "specific"
    elif raw_mode in {"3", "rebuild"}:
        mode = "rebuild"
    elif raw_mode in {"4", "full"}:
        mode = "full"
    else:
        raise ValueError(f"Unknown mode: {raw_mode}")

    specific_weeks = None
    if mode == "specific":
        specific_weeks = input('Which Fantrax weeks should be refreshed? e.g. "34" or "33-34": ').strip()
        if not specific_weeks:
            raise ValueError("No weeks entered for SPECIFIC mode.")

    write_report_line(lines, f"Mode:         {mode.upper()}")
    if specific_weeks:
        write_report_line(lines, f"Specific GWs: {specific_weeks}")

    # -------------------------------------------------------------------------
    # 1-4. Fantrax API layer
    # -------------------------------------------------------------------------
    skip_api_layer = mode in {"specific", "rebuild"} and api_outputs_exist()

    if skip_api_layer:
        banner(lines, "Steps 1–4 — API layer skipped for speed")
        write_report_line(lines, f"{mode.upper()} mode is using existing API files.")
        write_report_line(lines, "Run AUTO or FULL if you want to refresh standings/API rosters/scoring rules.")
    else:
        # ---------------------------------------------------------------------
        # 1. Fantrax API raw fetch
        # ---------------------------------------------------------------------
        banner(lines, "Step 1 — Fetch Fantrax API raw JSON")
        api_args = ["--league-id", LEAGUE_ID]

        # In AUTO/FULL, overwrite API raw JSON because standings/rosters can change.
        # In SPECIFIC/REBUILD, this only happens if API files are missing.
        if mode in {"auto", "specific", "full", "rebuild"}:
            api_args.append("--force")

        run_script(lines, FETCH_API, api_args, required=True)

        # ---------------------------------------------------------------------
        # 2. Transform API JSON
        # ---------------------------------------------------------------------
        banner(lines, "Step 2 — Transform Fantrax API JSON")
        run_script(lines, TRANSFORM_API, required=True)

        # ---------------------------------------------------------------------
        # 3. Transform API rosters
        # ---------------------------------------------------------------------
        banner(lines, "Step 3 — Transform API rosters into rosters_by_week.csv")
        roster_transform = pick_roster_transform_script()
        if roster_transform is None:
            write_report_line(lines, "WARNING: No roster transform script found.")
            write_report_line(lines, "Expected one of:")
            for p in ROSTER_TRANSFORM_CANDIDATES:
                write_report_line(lines, f"  - {p}")
            write_report_line(lines, "Continuing only if rosters_by_week.csv already exists.")
            existing_rosters = PROJECT_ROOT / "processed_data" / "fantrax_api" / "rosters_by_week.csv"
            if not existing_rosters.exists():
                raise FileNotFoundError(
                    "Missing rosters_by_week.csv and no roster transform script found. "
                    "Save the roster transformer as scripts\\transform_fantrax_rosters.py."
                )
        else:
            run_script(lines, roster_transform, required=True)

        # ---------------------------------------------------------------------
        # 4. Validate API layer
        # ---------------------------------------------------------------------
        banner(lines, "Step 4 — Validate Fantrax API layer")
        run_script(lines, VALIDATE_API, required=True)

    # -------------------------------------------------------------------------
    # 5. Existing Fantrax + Understat + master refresh
    # -------------------------------------------------------------------------
    banner(lines, "Step 5 — Refresh Fantrax CSVs + Understat + master weekly dataset")
    refresh_input = build_refresh_weekplayer_input(mode, specific_weeks=specific_weeks)
    run_script(lines, REFRESH_WEEKPLAYER, input_text=refresh_input, required=True)

    # -------------------------------------------------------------------------
    # 6. Fetch/flatten API player lookup
    # -------------------------------------------------------------------------
    skip_player_lookup = mode in {"specific", "rebuild"} and api_player_lookup_exists()

    if skip_player_lookup:
        banner(lines, "Step 6 — API player lookup skipped for speed")
        write_report_line(lines, f"{mode.upper()} mode is using existing api_player_lookup.csv.")
    else:
        banner(lines, "Step 6 — Refresh API player lookup")
        run_script(lines, FETCH_PLAYER_IDS_EPL, required=True)
        run_script(lines, FLATTEN_PLAYER_LOOKUP, required=True)

    # -------------------------------------------------------------------------
    # 7. Build API -> master player bridge
    # -------------------------------------------------------------------------
    banner(lines, "Step 7 — Build API → master player bridge")
    run_script(lines, BUILD_NAME_BRIDGE, required=True)

    # -------------------------------------------------------------------------
    # 8. Merge gold tables
    # -------------------------------------------------------------------------
    banner(lines, "Step 8 — Merge final gold tables")
    run_script(lines, MERGE_GOLD, required=True)

    # -------------------------------------------------------------------------
    # 9. Build League Hub analytics views if script exists
    # -------------------------------------------------------------------------
    if script_exists(BUILD_AWARDS):
        banner(lines, "Step 9 — Build League Hub analytics views")
        run_script(lines, BUILD_AWARDS, required=False)
    else:
        banner(lines, "Step 9 — League Hub analytics views skipped")
        write_report_line(lines, f"Optional script missing: {BUILD_AWARDS}")

    # -------------------------------------------------------------------------
    # 10. Final output summary
    # -------------------------------------------------------------------------
    summarize_expected_outputs(lines)

    banner(lines, "Refresh complete")
    write_report_line(lines, f"Finished: {datetime.now().isoformat(timespec='seconds')}")
    write_report_line(lines, f"Report:   {REPORT_PATH}")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print()
    print(f"Saved refresh report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
