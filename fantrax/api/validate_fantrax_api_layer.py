#!/usr/bin/env python3
r"""
validate_fantrax_api_layer.py

Purpose
-------
Validate the cleaned Fantrax API CSV layer before merging it into analytics.

Checks:
1. Required files exist.
2. Every roster player_id exists in player_info.csv.
3. Every matchup team_id exists in standings.csv.
4. Active starters per team/week = 11.
5. Total roster size per team/week <= 16.
6. Reserve count per team/week <= 4.
7. Injured reserve count is reported separately.
8. Matchup counts by period look reasonable.
9. Duplicate player ownership within the same period is flagged.

Inputs:
    C:\Users\Tommy\fantrax_data\processed_data\fantrax_api\rosters_by_week.csv
    C:\Users\Tommy\fantrax_data\processed_data\fantrax_api\player_info.csv
    C:\Users\Tommy\fantrax_data\processed_data\fantrax_api\standings.csv
    C:\Users\Tommy\fantrax_data\processed_data\fantrax_api\matchups_by_week.csv
    C:\Users\Tommy\fantrax_data\processed_data\fantrax_api\roster_settings.csv

Outputs:
    C:\Users\Tommy\fantrax_data\processed_data\fantrax_api\validation_report.txt
    C:\Users\Tommy\fantrax_data\processed_data\fantrax_api\validation_roster_counts.csv
    C:\Users\Tommy\fantrax_data\processed_data\fantrax_api\validation_missing_roster_player_ids.csv
    C:\Users\Tommy\fantrax_data\processed_data\fantrax_api\validation_missing_matchup_team_ids.csv
    C:\Users\Tommy\fantrax_data\processed_data\fantrax_api\validation_duplicate_player_periods.csv

Run:
    python C:\Users\Tommy\fantrax_data\scripts\validate_fantrax_api_layer.py
"""

from __future__ import annotations

import sys

from pathlib import Path

import pandas as pd


# =============================================================================
# CONFIG
# =============================================================================

# Portable project configuration
_PROJECT_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT_BOOTSTRAP))
from config.project_paths import PROJECT_ROOT
API_DIR = PROJECT_ROOT / "processed_data" / "fantrax_api"

ROSTERS_FILE = API_DIR / "rosters_by_week.csv"
PLAYER_INFO_FILE = API_DIR / "player_info.csv"
STANDINGS_FILE = API_DIR / "standings.csv"
MATCHUPS_FILE = API_DIR / "matchups_by_week.csv"
ROSTER_SETTINGS_FILE = API_DIR / "roster_settings.csv"

REPORT_FILE = API_DIR / "validation_report.txt"

ROSTER_COUNTS_OUT = API_DIR / "validation_roster_counts.csv"
MISSING_ROSTER_PLAYERS_OUT = API_DIR / "validation_missing_roster_player_ids.csv"
MISSING_MATCHUP_TEAMS_OUT = API_DIR / "validation_missing_matchup_team_ids.csv"
DUPLICATE_PLAYER_PERIODS_OUT = API_DIR / "validation_duplicate_player_periods.csv"


# =============================================================================
# HELPERS
# =============================================================================

def read_csv_required(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig")


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def as_int_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").astype("Int64")


def as_bool_series(series: pd.Series) -> pd.Series:
    # Handles True/False booleans and string versions.
    return series.astype(str).str.lower().isin(["true", "1", "yes"])


def get_setting_value(roster_settings: pd.DataFrame, setting_name: str, default: int) -> int:
    match = roster_settings.loc[roster_settings["setting_name"] == setting_name, "setting_value"]
    if match.empty:
        return default
    try:
        return int(float(match.iloc[0]))
    except Exception:
        return default


def add_section(lines: list[str], title: str) -> None:
    lines.append("")
    lines.append("=" * 80)
    lines.append(title)
    lines.append("=" * 80)


# =============================================================================
# MAIN VALIDATION
# =============================================================================

def main() -> None:
    print("Fantrax API Layer Validation")
    print(f"API dir: {API_DIR}")
    print()

    rosters = read_csv_required(ROSTERS_FILE)
    player_info = read_csv_required(PLAYER_INFO_FILE)
    standings = read_csv_required(STANDINGS_FILE)
    matchups = read_csv_required(MATCHUPS_FILE)
    roster_settings = read_csv_required(ROSTER_SETTINGS_FILE)

    # Normalize expected columns/types.
    rosters["period"] = as_int_series(rosters["period"])
    rosters["starter"] = as_bool_series(rosters["starter"])
    rosters["status"] = rosters["status"].fillna("")
    rosters["player_id"] = rosters["player_id"].astype(str)
    rosters["team_id"] = rosters["team_id"].astype(str)

    player_info["player_id"] = player_info["player_id"].astype(str)
    standings["team_id"] = standings["team_id"].astype(str)

    matchups["period"] = as_int_series(matchups["period"])
    for col in ["home_team_id", "away_team_id"]:
        if col in matchups.columns:
            matchups[col] = matchups[col].fillna("").astype(str)

    max_total_players = get_setting_value(roster_settings, "maxTotalPlayers", 16)
    max_active_players = get_setting_value(roster_settings, "maxTotalActivePlayers", 11)
    max_reserve_players = get_setting_value(roster_settings, "maxTotalReservePlayers", 4)

    report_lines: list[str] = []

    report_lines.append("Fantrax API Layer Validation Report")
    report_lines.append(f"API dir: {API_DIR}")
    report_lines.append("")
    report_lines.append(f"Roster rows: {len(rosters)}")
    report_lines.append(f"Player info rows: {len(player_info)}")
    report_lines.append(f"Standings teams: {len(standings)}")
    report_lines.append(f"Matchup rows: {len(matchups)}")
    report_lines.append("")
    report_lines.append(f"Expected max total players: {max_total_players}")
    report_lines.append(f"Expected active starters: {max_active_players}")
    report_lines.append(f"Expected max reserve players: {max_reserve_players}")

    # -------------------------------------------------------------------------
    # 1. Missing roster player IDs from player_info
    # -------------------------------------------------------------------------
    roster_player_ids = set(rosters["player_id"].dropna().astype(str))
    player_info_ids = set(player_info["player_id"].dropna().astype(str))

    missing_roster_player_ids = sorted(roster_player_ids - player_info_ids)

    missing_roster_players_df = rosters[
        rosters["player_id"].isin(missing_roster_player_ids)
    ].sort_values(["period", "team_name", "player_id"])

    write_csv(missing_roster_players_df, MISSING_ROSTER_PLAYERS_OUT)

    add_section(report_lines, "1. Roster player IDs missing from player_info.csv")
    if missing_roster_player_ids:
        report_lines.append(f"FAIL: {len(missing_roster_player_ids)} unique roster player IDs are missing.")
        report_lines.append(f"See: {MISSING_ROSTER_PLAYERS_OUT}")
        report_lines.extend([f"  - {pid}" for pid in missing_roster_player_ids[:25]])
        if len(missing_roster_player_ids) > 25:
            report_lines.append(f"  ... {len(missing_roster_player_ids) - 25} more")
    else:
        report_lines.append("PASS: Every roster player_id exists in player_info.csv.")

    # -------------------------------------------------------------------------
    # 2. Missing matchup team IDs from standings
    # -------------------------------------------------------------------------
    standings_team_ids = set(standings["team_id"].dropna().astype(str))

    matchup_team_rows = []
    for _, row in matchups.iterrows():
        for side in ["home", "away"]:
            team_id = row.get(f"{side}_team_id", "")
            team_name = row.get(f"{side}_team_name", "")
            if team_id and team_id not in standings_team_ids:
                matchup_team_rows.append({
                    "period": row.get("period"),
                    "matchup_index": row.get("matchup_index"),
                    "side": side,
                    "team_id": team_id,
                    "team_name": team_name,
                })

    missing_matchup_teams_df = pd.DataFrame(matchup_team_rows)
    if len(missing_matchup_teams_df):
        missing_matchup_teams_df = missing_matchup_teams_df.sort_values(["period", "matchup_index", "side"])

    write_csv(missing_matchup_teams_df, MISSING_MATCHUP_TEAMS_OUT)

    add_section(report_lines, "2. Matchup team IDs missing from standings.csv")
    if len(missing_matchup_teams_df):
        report_lines.append(f"FAIL: {len(missing_matchup_teams_df)} matchup team references are missing from standings.")
        report_lines.append(f"See: {MISSING_MATCHUP_TEAMS_OUT}")
    else:
        report_lines.append("PASS: Every concrete matchup team_id exists in standings.csv.")
        report_lines.append("Note: playoff seed/TBD rows do not have team IDs yet, and are ignored here.")

    # -------------------------------------------------------------------------
    # 3. Roster counts by period/team
    # -------------------------------------------------------------------------
    roster_counts = (
        rosters
        .groupby(["period", "team_id", "team_name"], dropna=False)
        .agg(
            total_players=("player_id", "count"),
            active_players=("status", lambda s: (s == "ACTIVE").sum()),
            reserve_players=("status", lambda s: (s == "RESERVE").sum()),
            injured_reserve_players=("status", lambda s: (s == "INJURED_RESERVE").sum()),
            starter_true_count=("starter", "sum"),
            unique_players=("player_id", "nunique"),
        )
        .reset_index()
        .sort_values(["period", "team_name"])
    )

    roster_counts["active_count_ok"] = roster_counts["active_players"] == max_active_players
    roster_counts["starter_flag_ok"] = roster_counts["starter_true_count"] == max_active_players
    roster_counts["total_count_ok"] = roster_counts["total_players"] <= max_total_players
    roster_counts["reserve_count_ok"] = roster_counts["reserve_players"] <= max_reserve_players
    roster_counts["unique_player_count_ok"] = roster_counts["unique_players"] == roster_counts["total_players"]

    write_csv(roster_counts, ROSTER_COUNTS_OUT)

    active_bad = roster_counts[~roster_counts["active_count_ok"]]
    total_bad = roster_counts[~roster_counts["total_count_ok"]]
    reserve_bad = roster_counts[~roster_counts["reserve_count_ok"]]
    unique_bad = roster_counts[~roster_counts["unique_player_count_ok"]]

    add_section(report_lines, "3. Roster size / starter count checks")
    report_lines.append(f"Saved roster count details: {ROSTER_COUNTS_OUT}")

    if len(active_bad):
        report_lines.append(f"WARN/FAIL: {len(active_bad)} team-periods do not have {max_active_players} ACTIVE players.")
        report_lines.append("First few:")
        for _, row in active_bad.head(15).iterrows():
            report_lines.append(
                f"  - period {row['period']}, {row['team_name']}: active={row['active_players']}, total={row['total_players']}"
            )
    else:
        report_lines.append(f"PASS: Every team-period has {max_active_players} ACTIVE players.")

    if len(total_bad):
        report_lines.append(f"WARN/FAIL: {len(total_bad)} team-periods exceed max total players ({max_total_players}).")
    else:
        report_lines.append(f"PASS: Every team-period has <= {max_total_players} total players.")

    if len(reserve_bad):
        report_lines.append(f"WARN: {len(reserve_bad)} team-periods exceed max reserve players ({max_reserve_players}).")
        report_lines.append("Note: this excludes INJURED_RESERVE from reserve count.")
    else:
        report_lines.append(f"PASS: Every team-period has <= {max_reserve_players} RESERVE players.")

    if len(unique_bad):
        report_lines.append(f"WARN/FAIL: {len(unique_bad)} team-periods have duplicate player rows inside the same roster.")
    else:
        report_lines.append("PASS: No duplicate player rows inside individual team-period rosters.")

    # -------------------------------------------------------------------------
    # 4. Duplicate player ownership within same period
    # -------------------------------------------------------------------------
    player_period_counts = (
        rosters
        .groupby(["period", "player_id"], dropna=False)
        .agg(
            team_count=("team_id", "nunique"),
            teams=("team_name", lambda s: " | ".join(sorted(set(map(str, s))))),
            statuses=("status", lambda s: " | ".join(sorted(set(map(str, s))))),
        )
        .reset_index()
    )

    duplicate_player_periods = player_period_counts[player_period_counts["team_count"] > 1].sort_values(
        ["period", "player_id"]
    )

    write_csv(duplicate_player_periods, DUPLICATE_PLAYER_PERIODS_OUT)

    add_section(report_lines, "4. Duplicate player ownership within same period")
    if len(duplicate_player_periods):
        report_lines.append(f"FAIL: {len(duplicate_player_periods)} player-periods appear on multiple teams.")
        report_lines.append(f"See: {DUPLICATE_PLAYER_PERIODS_OUT}")
        report_lines.append("First few:")
        for _, row in duplicate_player_periods.head(15).iterrows():
            report_lines.append(
                f"  - period {row['period']}, player_id {row['player_id']}, teams={row['teams']}"
            )
    else:
        report_lines.append("PASS: No player appears on multiple teams in the same period.")

    # -------------------------------------------------------------------------
    # 5. Matchup counts by period
    # -------------------------------------------------------------------------
    matchup_counts = (
        matchups
        .groupby("period", dropna=False)
        .agg(
            matchup_count=("matchup_index", "count"),
            concrete_matchups=("has_team_ids", lambda s: (s.astype(str).str.lower() == "true").sum() if s.dtype == object else s.sum()),
            seed_matchups=("has_seed", lambda s: (s.astype(str).str.lower() == "true").sum() if s.dtype == object else s.sum()),
            tbd_matchups=("has_tbd", lambda s: (s.astype(str).str.lower() == "true").sum() if s.dtype == object else s.sum()),
        )
        .reset_index()
        .sort_values("period")
    )

    add_section(report_lines, "5. Matchup counts by period")
    report_lines.append("Matchup count summary:")
    for _, row in matchup_counts.iterrows():
        report_lines.append(
            f"  - period {row['period']}: total={row['matchup_count']}, "
            f"teams={row['concrete_matchups']}, seeds={row['seed_matchups']}, TBD={row['tbd_matchups']}"
        )

    regular_weeks = matchup_counts[matchup_counts["period"] <= 35]
    regular_bad = regular_weeks[regular_weeks["matchup_count"] != 6]

    playoff_weeks = matchup_counts[matchup_counts["period"] >= 36]

    if len(regular_bad):
        report_lines.append(f"WARN/FAIL: {len(regular_bad)} regular-season periods do not have 6 matchups.")
    else:
        report_lines.append("PASS: Periods 1-35 each have 6 regular-season matchups.")

    if len(playoff_weeks):
        report_lines.append("INFO: Periods 36+ appear to be playoff/consolation style rows with seed/TBD logic.")

    # -------------------------------------------------------------------------
    # 6. Final status
    # -------------------------------------------------------------------------
    blocking_failures = 0
    blocking_failures += 1 if missing_roster_player_ids else 0
    blocking_failures += 1 if len(missing_matchup_teams_df) else 0
    blocking_failures += 1 if len(duplicate_player_periods) else 0

    warning_count = 0
    warning_count += len(active_bad)
    warning_count += len(total_bad)
    warning_count += len(reserve_bad)
    warning_count += len(unique_bad)
    warning_count += len(regular_bad)

    add_section(report_lines, "Final status")
    if blocking_failures == 0:
        report_lines.append("PASS: No blocking ID integrity issues found.")
    else:
        report_lines.append(f"FAIL: {blocking_failures} blocking ID integrity check group(s) failed.")

    if warning_count == 0:
        report_lines.append("PASS: No roster/matchup shape warnings found.")
    else:
        report_lines.append(f"WARN: {warning_count} roster/matchup shape warning row(s) found.")

    report_lines.append("")
    report_lines.append("Suggested next step:")
    report_lines.append("If this report is clean enough, build the first merge between:")
    report_lines.append("  - rosters_by_week.csv")
    report_lines.append("  - player_info.csv")
    report_lines.append("  - your Fantrax weekly player/stat dataset")

    REPORT_FILE.write_text("\n".join(report_lines), encoding="utf-8")

    print("\n".join(report_lines))
    print()
    print(f"Saved validation report: {REPORT_FILE}")


if __name__ == "__main__":
    main()
