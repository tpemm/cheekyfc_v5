#!/usr/bin/env python3
r"""
merge_master_with_api_rosters_v2.py

Purpose
-------
Create the final "gold table" by merging:

1. Existing master player-week dataset
   data\processed\master_player_weekly_2526.csv

2. Fantrax API weekly rosters
   processed_data\fantrax_api\rosters_by_week.csv

3. API -> master player ID bridge
   data\reference\api_to_master_player_id_bridge_2526.csv

4. Fantrax API player lookup
   processed_data\fantrax_api\api_player_lookup.csv

5. Matchups / standings
   processed_data\fantrax_api\matchups_by_week.csv
   processed_data\fantrax_api\standings.csv

Outputs
-------
data\processed\manager_player_weekly_2526.csv
data\processed\manager_week_summary_2526.csv
data\processed\manager_season_summary_2526.csv
data\processed\lineup_quality_summary_2526.csv
data\processed\matchup_week_summary_2526.csv
data\processed\api_merge_validation_report_2526.txt

Run
---
python C:\Users\Tommy\fantrax_data\scripts\merge_master_with_api_rosters_v2.py
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
SEASON_ID = "2526"

MASTER_FILE = PROJECT_ROOT / "data" / "processed" / f"master_player_weekly_{SEASON_ID}.csv"

API_DIR = PROJECT_ROOT / "processed_data" / "fantrax_api"
API_ROSTERS_FILE = API_DIR / "rosters_by_week.csv"
API_PLAYER_LOOKUP_FILE = API_DIR / "api_player_lookup.csv"
API_MATCHUPS_FILE = API_DIR / "matchups_by_week.csv"
API_STANDINGS_FILE = API_DIR / "standings.csv"

BRIDGE_FILE = PROJECT_ROOT / "data" / "reference" / f"api_to_master_player_id_bridge_{SEASON_ID}.csv"

OUT_DIR = PROJECT_ROOT / "data" / "processed"
OUT_MANAGER_PLAYER = OUT_DIR / f"manager_player_weekly_{SEASON_ID}.csv"
OUT_MANAGER_WEEK = OUT_DIR / f"manager_week_summary_{SEASON_ID}.csv"
OUT_MANAGER_SEASON = OUT_DIR / f"manager_season_summary_{SEASON_ID}.csv"
OUT_LINEUP_QUALITY = OUT_DIR / f"lineup_quality_summary_{SEASON_ID}.csv"
OUT_MATCHUP_WEEK = OUT_DIR / f"matchup_week_summary_{SEASON_ID}.csv"
OUT_REPORT = OUT_DIR / f"api_merge_validation_report_{SEASON_ID}.txt"


# =============================================================================
# HELPERS
# =============================================================================

def read_csv(path: Path, dtype: str | None = "str") -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    return pd.read_csv(path, dtype=dtype, encoding="utf-8-sig")


def clean_id_series(s: pd.Series) -> pd.Series:
    return (
        s.astype(str)
         .str.strip()
         .str.replace(r"\.0$", "", regex=True)
         .str.replace("*", "", regex=False)
         .replace({"nan": pd.NA, "None": pd.NA, "": pd.NA, "<NA>": pd.NA})
    )


def numeric(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series([0.0] * len(df), index=df.index)
    return pd.to_numeric(df[col], errors="coerce").fillna(0)


def bool_from_str(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().isin(["true", "1", "yes"])


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"Saved: {path}")
    print(f"Rows: {len(df):,}")
    if len(df):
        print(df.head(5).to_string(index=False))
    print()


def first_existing_name(df: pd.DataFrame) -> pd.Series:
    out = pd.Series([""] * len(df), index=df.index, dtype="object")
    for col in ["mgr_player", "fantrax_player_name", "avail_player"]:
        if col in df.columns:
            mask = out.eq("") & df[col].notna() & df[col].astype(str).str.strip().ne("")
            out.loc[mask] = df.loc[mask, col].astype(str).str.strip()
    return out


def starter_sum(group: pd.DataFrame, value_col: str) -> float:
    return pd.to_numeric(group.loc[group["is_started_api"], value_col], errors="coerce").fillna(0).sum()


def bench_sum(group: pd.DataFrame, value_col: str) -> float:
    return pd.to_numeric(group.loc[~group["is_started_api"], value_col], errors="coerce").fillna(0).sum()


# =============================================================================
# MAIN
# =============================================================================

def main() -> None:
    print("Merge Master Weekly Dataset + API Rosters v2")
    print(f"Master:  {MASTER_FILE}")
    print(f"Rosters: {API_ROSTERS_FILE}")
    print(f"Bridge:  {BRIDGE_FILE}")
    print()

    master = read_csv(MASTER_FILE)
    rosters = read_csv(API_ROSTERS_FILE)
    bridge = read_csv(BRIDGE_FILE)
    api_lookup = read_csv(API_PLAYER_LOOKUP_FILE)
    matchups = read_csv(API_MATCHUPS_FILE)
    standings = read_csv(API_STANDINGS_FILE)

    # Clean master keys.
    master["fantrax_gw"] = pd.to_numeric(master["fantrax_gw"], errors="coerce").astype("Int64")
    master["fantrax_player_id"] = clean_id_series(master["fantrax_player_id"])

    # Clean API roster keys.
    rosters["period"] = pd.to_numeric(rosters["period"], errors="coerce").astype("Int64")
    rosters["api_player_id"] = clean_id_series(rosters["player_id"])
    rosters["api_team_id"] = clean_id_series(rosters["team_id"])
    rosters["api_starter"] = bool_from_str(rosters["starter"])

    # Clean bridge.
    bridge["api_player_id"] = clean_id_series(bridge["api_player_id"])
    bridge["fantrax_player_id"] = clean_id_series(bridge["fantrax_player_id"])

    # Clean lookup.
    api_lookup["api_player_id"] = clean_id_series(api_lookup["api_player_id"])

    # Prepare API roster rows with master/Fantrax ID attached.
    roster_bridge = rosters.merge(
        bridge[
            [
                "api_player_id",
                "fantrax_player_id",
                "api_player_name",
                "fantrax_player_name",
                "final_score",
                "match_type",
            ]
        ],
        on="api_player_id",
        how="left",
        validate="many_to_one",
    )

    roster_bridge = roster_bridge.rename(columns={
        "period": "fantrax_gw",
        "team_name": "api_team_name",
        "position": "api_position_used",
        "status": "api_roster_status",
    })

    # Validate bridge coverage.
    missing_bridge = roster_bridge[roster_bridge["fantrax_player_id"].isna()].copy()

    # Merge master + bridged API roster.
    enriched = master.merge(
        roster_bridge[
            [
                "fantrax_gw",
                "fantrax_player_id",
                "api_player_id",
                "api_player_name",
                "api_team_id",
                "api_team_name",
                "api_position_used",
                "api_roster_status",
                "api_starter",
                "final_score",
                "match_type",
            ]
        ],
        on=["fantrax_gw", "fantrax_player_id"],
        how="left",
        validate="one_to_one",
    )

    enriched["is_rostered_api"] = enriched["api_team_id"].notna()
    enriched["is_started_api"] = enriched["api_starter"].fillna(False).astype(bool)
    enriched["player_name_display"] = first_existing_name(enriched)
    enriched["api_missing_bridge"] = False

    # Numeric fields from master/Fantrax.
    stat_source_cols = {
        "fantasy_points": "mgr_fantasy_points",
        "goals": "mgr_g",
        "assists_total": "mgr_at",
        "clean_sheets": "mgr_cs",
        "minutes": "mgr_min",
        "key_passes": "mgr_kp",
        "shots_on_target": "mgr_sot",
        "yellow_cards": "mgr_yc",
        "red_cards": "mgr_rc",
        "tackles_won": "mgr_tkw",
        "interceptions": "mgr_int",
        "clearances": "mgr_clr",
        "aerials_won": "mgr_aer",
        "successful_dribbles": "mgr_cos",
        "saves": "mgr_sv",
        "goals_against": "mgr_ga",
    }

    for out_col, src_col in stat_source_cols.items():
        enriched[f"num_{out_col}"] = numeric(enriched, src_col)

    # Numeric fields from Understat.
    understat_cols = {
        "understat_minutes": "minutes",
        "understat_goals": "goals",
        "understat_assists": "assists",
        "understat_shots": "shots",
        "understat_xg": "xg",
        "understat_xa": "xa",
        "understat_key_passes": "key_passes",
        "understat_yellow_cards": "yellow_cards",
        "understat_red_cards": "red_cards",
        "understat_matches_in_gw": "us_matches_in_gw",
    }

    for out_col, src_col in understat_cols.items():
        enriched[f"num_{out_col}"] = numeric(enriched, src_col)

    save_csv(enriched, OUT_MANAGER_PLAYER)

    # Create manager week summary from rostered rows only.
    rostered = enriched[enriched["is_rostered_api"]].copy()

    if len(rostered) == 0:
        raise RuntimeError("No roster rows matched after bridge merge. Check bridge IDs and master IDs.")

    group_keys = ["fantrax_gw", "api_team_id", "api_team_name"]

    rows = []
    for keys, g in rostered.groupby(group_keys, dropna=False):
        fantrax_gw, api_team_id, api_team_name = keys

        rows.append({
            "fantrax_gw": fantrax_gw,
            "api_team_id": api_team_id,
            "api_team_name": api_team_name,

            "roster_players": len(g),
            "active_players": int((g["api_roster_status"] == "ACTIVE").sum()),
            "reserve_players": int((g["api_roster_status"] == "RESERVE").sum()),
            "injured_reserve_players": int((g["api_roster_status"] == "INJURED_RESERVE").sum()),

            "starter_fantasy_points": starter_sum(g, "num_fantasy_points"),
            "bench_fantasy_points": bench_sum(g, "num_fantasy_points"),

            "starter_goals": starter_sum(g, "num_goals"),
            "bench_goals": bench_sum(g, "num_goals"),

            "starter_assists_total": starter_sum(g, "num_assists_total"),
            "bench_assists_total": bench_sum(g, "num_assists_total"),

            "starter_clean_sheets": starter_sum(g, "num_clean_sheets"),
            "bench_clean_sheets": bench_sum(g, "num_clean_sheets"),

            "starter_minutes": starter_sum(g, "num_minutes"),
            "bench_minutes": bench_sum(g, "num_minutes"),

            "starter_xg": starter_sum(g, "num_understat_xg"),
            "bench_xg": bench_sum(g, "num_understat_xg"),
            "starter_xa": starter_sum(g, "num_understat_xa"),
            "bench_xa": bench_sum(g, "num_understat_xa"),
            "starter_understat_shots": starter_sum(g, "num_understat_shots"),
            "bench_understat_shots": bench_sum(g, "num_understat_shots"),

            "players_with_understat_match": int((pd.to_numeric(g["num_understat_matches_in_gw"], errors="coerce").fillna(0) > 0).sum()),
        })

    manager_week = pd.DataFrame(rows)

    manager_week["missing_active_slots"] = (11 - manager_week["active_players"]).clip(lower=0)
    manager_week["total_fantasy_points_rostered"] = manager_week["starter_fantasy_points"] + manager_week["bench_fantasy_points"]

    # Add matchup opponent.
    matchups["period"] = pd.to_numeric(matchups["period"], errors="coerce").astype("Int64")
    matchup_rows = []

    for _, row in matchups.iterrows():
        period = row.get("period")
        matchup_index = row.get("matchup_index")
        home_id = row.get("home_team_id")
        away_id = row.get("away_team_id")
        home_name = row.get("home_team_name")
        away_name = row.get("away_team_name")

        if pd.notna(home_id) and str(home_id).strip():
            matchup_rows.append({
                "fantrax_gw": period,
                "api_team_id": str(home_id).strip(),
                "matchup_index": matchup_index,
                "home_away": "home",
                "opponent_team_id": away_id,
                "opponent_team_name": away_name,
            })

        if pd.notna(away_id) and str(away_id).strip():
            matchup_rows.append({
                "fantrax_gw": period,
                "api_team_id": str(away_id).strip(),
                "matchup_index": matchup_index,
                "home_away": "away",
                "opponent_team_id": home_id,
                "opponent_team_name": home_name,
            })

    matchup_lookup = pd.DataFrame(matchup_rows)

    if len(matchup_lookup):
        manager_week["api_team_id"] = manager_week["api_team_id"].astype(str)
        matchup_lookup["api_team_id"] = matchup_lookup["api_team_id"].astype(str)
        manager_week = manager_week.merge(
            matchup_lookup,
            on=["fantrax_gw", "api_team_id"],
            how="left",
            validate="many_to_one",
        )

    manager_week = manager_week.sort_values(["fantrax_gw", "api_team_name"])
    save_csv(manager_week, OUT_MANAGER_WEEK)

    # Matchup-level weekly summary: each manager row plus opponent points.
    matchup_week = manager_week.copy()
    points_lookup = manager_week[
        ["fantrax_gw", "api_team_id", "api_team_name", "starter_fantasy_points"]
    ].rename(columns={
        "api_team_id": "opponent_team_id",
        "api_team_name": "opponent_name_from_summary",
        "starter_fantasy_points": "opponent_starter_fantasy_points",
    })

    matchup_week["opponent_team_id"] = matchup_week["opponent_team_id"].astype(str)
    points_lookup["opponent_team_id"] = points_lookup["opponent_team_id"].astype(str)

    matchup_week = matchup_week.merge(
        points_lookup,
        on=["fantrax_gw", "opponent_team_id"],
        how="left",
        validate="many_to_one",
    )

    matchup_week["point_margin_vs_opponent"] = (
        matchup_week["starter_fantasy_points"] - matchup_week["opponent_starter_fantasy_points"]
    )
    matchup_week["computed_result"] = matchup_week["point_margin_vs_opponent"].apply(
        lambda x: "W" if pd.notna(x) and x > 0 else "L" if pd.notna(x) and x < 0 else "T" if pd.notna(x) else pd.NA
    )

    save_csv(matchup_week, OUT_MATCHUP_WEEK)

    # Season summary.
    season_summary = (
        manager_week
        .groupby(["api_team_id", "api_team_name"], dropna=False)
        .agg(
            weeks=("fantrax_gw", "nunique"),
            total_starter_points=("starter_fantasy_points", "sum"),
            total_bench_points=("bench_fantasy_points", "sum"),
            total_points_rostered=("total_fantasy_points_rostered", "sum"),
            total_starter_goals=("starter_goals", "sum"),
            total_starter_assists_total=("starter_assists_total", "sum"),
            total_starter_clean_sheets=("starter_clean_sheets", "sum"),
            total_missing_active_slots=("missing_active_slots", "sum"),
            avg_active_players=("active_players", "mean"),
            avg_starter_points=("starter_fantasy_points", "mean"),
            best_week_points=("starter_fantasy_points", "max"),
            worst_week_points=("starter_fantasy_points", "min"),
            total_xg=("starter_xg", "sum"),
            total_xa=("starter_xa", "sum"),
        )
        .reset_index()
    )

    standings_small = standings.rename(columns={
        "team_id": "api_team_id",
        "rank": "official_rank",
        "record": "official_record",
        "total_points_for": "official_total_points_for",
        "win_percentage": "official_win_percentage",
        "games_back": "official_games_back",
    })

    for df in [season_summary, standings_small]:
        df["api_team_id"] = clean_id_series(df["api_team_id"])

    keep_standings = [
        c for c in [
            "api_team_id",
            "official_rank",
            "official_record",
            "official_total_points_for",
            "official_win_percentage",
            "official_games_back",
        ] if c in standings_small.columns
    ]

    season_summary = season_summary.merge(
        standings_small[keep_standings],
        on="api_team_id",
        how="left",
        validate="one_to_one",
    )

    season_summary["official_rank_num"] = pd.to_numeric(season_summary.get("official_rank"), errors="coerce")
    season_summary = season_summary.sort_values(["official_rank_num", "api_team_name"]).drop(columns=["official_rank_num"])

    save_csv(season_summary, OUT_MANAGER_SEASON)

    # Lineup quality summary.
    lineup_quality = manager_week[
        [
            "fantrax_gw",
            "api_team_id",
            "api_team_name",
            "active_players",
            "reserve_players",
            "injured_reserve_players",
            "missing_active_slots",
            "starter_fantasy_points",
            "bench_fantasy_points",
            "total_fantasy_points_rostered",
            "starter_goals",
            "bench_goals",
            "starter_assists_total",
            "bench_assists_total",
            "starter_clean_sheets",
            "bench_clean_sheets",
        ]
    ].copy()

    lineup_quality["bench_points_as_pct_of_starter_points"] = (
        lineup_quality["bench_fantasy_points"] /
        lineup_quality["starter_fantasy_points"].replace({0: pd.NA})
    )

    lineup_quality = lineup_quality.sort_values(
        ["missing_active_slots", "bench_fantasy_points"],
        ascending=[False, False],
    )

    save_csv(lineup_quality, OUT_LINEUP_QUALITY)

    # Report.
    roster_keys = set(zip(roster_bridge["fantrax_gw"].astype(str), roster_bridge["fantrax_player_id"].astype(str)))
    master_keys = set(zip(master["fantrax_gw"].astype(str), master["fantrax_player_id"].astype(str)))
    missing_roster_from_master = roster_keys - master_keys

    report = []
    report.append("API Roster Merge Validation Report v2")
    report.append("=" * 80)
    report.append(f"Master rows: {len(master):,}")
    report.append(f"API roster rows: {len(rosters):,}")
    report.append(f"Bridge rows: {len(bridge):,}")
    report.append(f"Roster rows missing bridge: {len(missing_bridge):,}")
    report.append(f"Enriched rows: {len(enriched):,}")
    report.append(f"Rostered API rows matched into master: {int(enriched['is_rostered_api'].sum()):,}")
    report.append(f"API roster player/week keys not found in master after bridge: {len(missing_roster_from_master):,}")
    report.append("")
    report.append("Outputs:")
    report.append(f"  {OUT_MANAGER_PLAYER}")
    report.append(f"  {OUT_MANAGER_WEEK}")
    report.append(f"  {OUT_MANAGER_SEASON}")
    report.append(f"  {OUT_LINEUP_QUALITY}")
    report.append(f"  {OUT_MATCHUP_WEEK}")
    report.append("")
    report.append("Notes:")
    report.append("- manager_week_summary uses API ACTIVE as starter flag.")
    report.append("- matchup_week_summary compares calculated starter fantasy points vs opponent.")
    report.append("- Official standings remain the source of truth for league record/rank.")
    report.append("- Missing active slots are real league behavior if managers failed to start full lineups.")

    OUT_REPORT.write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))
    print(f"\nSaved report: {OUT_REPORT}")


if __name__ == "__main__":
    main()
