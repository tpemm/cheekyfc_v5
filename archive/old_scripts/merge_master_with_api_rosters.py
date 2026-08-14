#!/usr/bin/env python3
r"""
merge_master_with_api_rosters.py

Purpose
-------
Bridge the existing player-week master dataset with the new Fantrax API roster layer.

Inputs:
    C:\Users\Tommy\fantrax_data\data\processed\master_player_weekly_2526.csv
    C:\Users\Tommy\fantrax_data\processed_data\fantrax_api\rosters_by_week.csv
    C:\Users\Tommy\fantrax_data\processed_data\fantrax_api\player_info.csv
    C:\Users\Tommy\fantrax_data\processed_data\fantrax_api\matchups_by_week.csv
    C:\Users\Tommy\fantrax_data\processed_data\fantrax_api\standings.csv

Outputs:
    C:\Users\Tommy\fantrax_data\data\processed\manager_player_weekly_2526.csv
    C:\Users\Tommy\fantrax_data\data\processed\manager_week_summary_2526.csv
    C:\Users\Tommy\fantrax_data\data\processed\manager_season_summary_2526.csv
    C:\Users\Tommy\fantrax_data\data\processed\lineup_quality_summary_2526.csv
    C:\Users\Tommy\fantrax_data\data\processed\api_merge_validation_report_2526.txt

Run:
    python C:\Users\Tommy\fantrax_data\scripts\merge_master_with_api_rosters.py

What this creates
-----------------
manager_player_weekly_2526.csv:
    One row per Fantrax player/week, enriched with API team_id, team_name,
    API roster status, starter flag, and eligible positions.

manager_week_summary_2526.csv:
    One row per manager/team/week with starter totals, bench totals,
    goals, assists, clean sheets, points, Understat metrics, and lineup counts.

manager_season_summary_2526.csv:
    One row per manager/team with season totals.

lineup_quality_summary_2526.csv:
    Same manager/week grain, focused on roster completeness and bench points.
"""

from __future__ import annotations

from pathlib import Path
import pandas as pd


# =============================================================================
# CONFIG
# =============================================================================

PROJECT_ROOT = Path(r"C:\Users\Tommy\fantrax_data")
SEASON_ID = "2526"

MASTER_FILE = PROJECT_ROOT / "data" / "processed" / f"master_player_weekly_{SEASON_ID}.csv"

API_DIR = PROJECT_ROOT / "processed_data" / "fantrax_api"
API_ROSTERS_FILE = API_DIR / "rosters_by_week.csv"
API_PLAYER_INFO_FILE = API_DIR / "player_info.csv"
API_MATCHUPS_FILE = API_DIR / "matchups_by_week.csv"
API_STANDINGS_FILE = API_DIR / "standings.csv"

OUT_DIR = PROJECT_ROOT / "data" / "processed"
OUT_MANAGER_PLAYER = OUT_DIR / f"manager_player_weekly_{SEASON_ID}.csv"
OUT_MANAGER_WEEK = OUT_DIR / f"manager_week_summary_{SEASON_ID}.csv"
OUT_MANAGER_SEASON = OUT_DIR / f"manager_season_summary_{SEASON_ID}.csv"
OUT_LINEUP_QUALITY = OUT_DIR / f"lineup_quality_summary_{SEASON_ID}.csv"
OUT_REPORT = OUT_DIR / f"api_merge_validation_report_{SEASON_ID}.txt"


# =============================================================================
# HELPERS
# =============================================================================

def read_csv(path: Path, dtype: str | None = None) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    if dtype:
        return pd.read_csv(path, dtype=dtype, encoding="utf-8-sig")
    return pd.read_csv(path, encoding="utf-8-sig")


def coerce_id(df: pd.DataFrame, col: str) -> None:
    if col in df.columns:
        s = df[col].astype(str).str.strip()
        s = s.replace({"nan": pd.NA, "None": pd.NA, "": pd.NA, "<NA>": pd.NA})
        df[col] = s


def numeric(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series([0] * len(df), index=df.index, dtype="float64")
    return pd.to_numeric(df[col], errors="coerce").fillna(0)


def bool_series(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series([False] * len(df), index=df.index)
    return df[col].astype(str).str.lower().isin(["true", "1", "yes"])


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"Saved: {path}")
    print(f"Rows: {len(df)}")
    if len(df):
        print(df.head(5).to_string(index=False))
    print()


def first_existing(cols: list[str], df: pd.DataFrame) -> str | None:
    for c in cols:
        if c in df.columns:
            return c
    return None


# =============================================================================
# MAIN
# =============================================================================

def main() -> None:
    print("Merge Master Weekly Dataset + Fantrax API Rosters")
    print(f"Master: {MASTER_FILE}")
    print(f"API rosters: {API_ROSTERS_FILE}")
    print()

    master = read_csv(MASTER_FILE, dtype=str)
    rosters = read_csv(API_ROSTERS_FILE, dtype=str)
    player_info = read_csv(API_PLAYER_INFO_FILE, dtype=str)
    matchups = read_csv(API_MATCHUPS_FILE, dtype=str)
    standings = read_csv(API_STANDINGS_FILE, dtype=str)

    # Normalize join keys.
    master["fantrax_gw"] = pd.to_numeric(master["fantrax_gw"], errors="coerce").astype("Int64")
    rosters["period"] = pd.to_numeric(rosters["period"], errors="coerce").astype("Int64")

    coerce_id(master, "fantrax_player_id")
    coerce_id(rosters, "player_id")
    coerce_id(rosters, "team_id")
    coerce_id(player_info, "player_id")
    coerce_id(standings, "team_id")

    # Prepare roster fields and avoid name collisions.
    roster_api = rosters.rename(columns={
        "period": "fantrax_gw",
        "player_id": "fantrax_player_id",
        "team_id": "api_team_id",
        "team_name": "api_team_name",
        "position": "api_position_used",
        "status": "api_roster_status",
        "starter": "api_starter",
    }).copy()

    roster_api["api_starter"] = roster_api["api_starter"].astype(str).str.lower().isin(["true", "1", "yes"])

    # Validate roster uniqueness for merge.
    dup_roster_keys = (
        roster_api
        .groupby(["fantrax_gw", "fantrax_player_id"], dropna=False)
        .size()
        .reset_index(name="n")
    )
    dup_roster_keys = dup_roster_keys[dup_roster_keys["n"] > 1]

    if len(dup_roster_keys):
        raise ValueError(
            "API rosters have duplicate (fantrax_gw, fantrax_player_id) keys. "
            "This should not happen if validation passed."
        )

    # Add player info fields from API.
    player_info_api = player_info.rename(columns={
        "player_id": "fantrax_player_id",
        "eligible_pos": "api_eligible_pos",
        "eligible_pos_count": "api_eligible_pos_count",
        "eligible_pos_list": "api_eligible_pos_list",
        "status": "api_player_pool_status",
    }).copy()

    # Merge master + roster API.
    enriched = master.merge(
        roster_api[
            [
                "fantrax_gw",
                "fantrax_player_id",
                "api_team_id",
                "api_team_name",
                "api_position_used",
                "api_roster_status",
                "api_starter",
            ]
        ],
        on=["fantrax_gw", "fantrax_player_id"],
        how="left",
        validate="one_to_one",
    )

    enriched = enriched.merge(
        player_info_api[
            [
                "fantrax_player_id",
                "api_eligible_pos",
                "api_eligible_pos_count",
                "api_eligible_pos_list",
                "api_player_pool_status",
            ]
        ],
        on="fantrax_player_id",
        how="left",
        validate="many_to_one",
    )

    # Helpful final fields.
    enriched["is_rostered_api"] = enriched["api_team_id"].notna()
    enriched["is_started_api"] = enriched["api_starter"].fillna(False).astype(bool)
    enriched["api_lineup_slot_counted"] = enriched["api_roster_status"].eq("ACTIVE")

    # Prefer actual manager name from existing master where available, otherwise API team name.
    if "manager" in enriched.columns:
        enriched["manager_label"] = enriched["manager"].fillna(enriched["api_team_name"])
    else:
        enriched["manager_label"] = enriched["api_team_name"]

    # Fantrax player name convenience.
    name_col = first_existing(["mgr_player", "avail_player", "fantrax_player_name"], enriched)
    if name_col:
        enriched["player_name_display"] = enriched[name_col]
    else:
        enriched["player_name_display"] = enriched["fantrax_player_id"]

    # Numeric fields needed for aggregation.
    # Fantrax stat columns from your master.
    stat_cols = {
        "fantasy_points": "mgr_fantasy_points",
        "goals": "mgr_g",
        "assists": "mgr_at",
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

    for out_col, src_col in stat_cols.items():
        enriched[f"num_{out_col}"] = numeric(enriched, src_col)

    # Understat columns, if present.
    us_cols = {
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

    for out_col, src_col in us_cols.items():
        enriched[f"num_{out_col}"] = numeric(enriched, src_col)

    # Save player-level enriched dataset.
    save_csv(enriched, OUT_MANAGER_PLAYER)

    # Manager/week summary. Use only rows that API says were rostered.
    rostered = enriched[enriched["is_rostered_api"]].copy()

    # Group by API team/week for reliable team IDs.
    group_keys = ["fantrax_gw", "api_team_id", "api_team_name"]

    manager_week = (
        rostered
        .groupby(group_keys, dropna=False)
        .agg(
            roster_players=("fantrax_player_id", "count"),
            active_players=("api_roster_status", lambda s: (s == "ACTIVE").sum()),
            reserve_players=("api_roster_status", lambda s: (s == "RESERVE").sum()),
            injured_reserve_players=("api_roster_status", lambda s: (s == "INJURED_RESERVE").sum()),

            starter_fantasy_points=("num_fantasy_points", lambda s: s[rostered.loc[s.index, "is_started_api"]].sum()),
            bench_fantasy_points=("num_fantasy_points", lambda s: s[~rostered.loc[s.index, "is_started_api"]].sum()),

            starter_goals=("num_goals", lambda s: s[rostered.loc[s.index, "is_started_api"]].sum()),
            bench_goals=("num_goals", lambda s: s[~rostered.loc[s.index, "is_started_api"]].sum()),

            starter_assists=("num_assists", lambda s: s[rostered.loc[s.index, "is_started_api"]].sum()),
            bench_assists=("num_assists", lambda s: s[~rostered.loc[s.index, "is_started_api"]].sum()),

            starter_clean_sheets=("num_clean_sheets", lambda s: s[rostered.loc[s.index, "is_started_api"]].sum()),
            bench_clean_sheets=("num_clean_sheets", lambda s: s[~rostered.loc[s.index, "is_started_api"]].sum()),

            starter_minutes=("num_minutes", lambda s: s[rostered.loc[s.index, "is_started_api"]].sum()),
            bench_minutes=("num_minutes", lambda s: s[~rostered.loc[s.index, "is_started_api"]].sum()),

            starter_xg=("num_understat_xg", lambda s: s[rostered.loc[s.index, "is_started_api"]].sum()),
            bench_xg=("num_understat_xg", lambda s: s[~rostered.loc[s.index, "is_started_api"]].sum()),
            starter_xa=("num_understat_xa", lambda s: s[rostered.loc[s.index, "is_started_api"]].sum()),
            bench_xa=("num_understat_xa", lambda s: s[~rostered.loc[s.index, "is_started_api"]].sum()),
            starter_understat_shots=("num_understat_shots", lambda s: s[rostered.loc[s.index, "is_started_api"]].sum()),
            bench_understat_shots=("num_understat_shots", lambda s: s[~rostered.loc[s.index, "is_started_api"]].sum()),

            players_with_understat_match=("num_understat_matches_in_gw", lambda s: (s > 0).sum()),
        )
        .reset_index()
        .sort_values(["fantrax_gw", "api_team_name"])
    )

    manager_week["missing_active_slots"] = (11 - manager_week["active_players"]).clip(lower=0)
    manager_week["total_fantasy_points_rostered"] = (
        manager_week["starter_fantasy_points"] + manager_week["bench_fantasy_points"]
    )

    # Add weekly matchup opponent and home/away where possible.
    matchup_rows = []
    m = matchups.copy()
    m["period"] = pd.to_numeric(m["period"], errors="coerce").astype("Int64")

    for _, row in m.iterrows():
        period = row.get("period")
        home_id = row.get("home_team_id")
        away_id = row.get("away_team_id")
        home_name = row.get("home_team_name")
        away_name = row.get("away_team_name")
        matchup_index = row.get("matchup_index")

        if pd.notna(home_id) and str(home_id).strip():
            matchup_rows.append({
                "fantrax_gw": period,
                "api_team_id": str(home_id),
                "matchup_index": matchup_index,
                "home_away": "home",
                "opponent_team_id": away_id,
                "opponent_team_name": away_name,
            })
        if pd.notna(away_id) and str(away_id).strip():
            matchup_rows.append({
                "fantrax_gw": period,
                "api_team_id": str(away_id),
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

    save_csv(manager_week, OUT_MANAGER_WEEK)

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
            total_starter_assists=("starter_assists", "sum"),
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

    # Add current official standings if available.
    standings_small = standings.rename(columns={
        "team_id": "api_team_id",
        "team_name": "standings_team_name",
        "rank": "official_rank",
        "record": "official_record",
        "total_points_for": "official_total_points_for",
        "win_percentage": "official_win_percentage",
        "games_back": "official_games_back",
    })

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

    season_summary["api_team_id"] = season_summary["api_team_id"].astype(str)
    standings_small["api_team_id"] = standings_small["api_team_id"].astype(str)

    season_summary = season_summary.merge(
        standings_small[keep_standings],
        on="api_team_id",
        how="left",
        validate="one_to_one",
    )

    # Nice ordering.
    if "official_rank" in season_summary.columns:
        season_summary["official_rank_num"] = pd.to_numeric(season_summary["official_rank"], errors="coerce")
        season_summary = season_summary.sort_values(["official_rank_num", "api_team_name"]).drop(columns=["official_rank_num"])
    else:
        season_summary = season_summary.sort_values(["total_starter_points"], ascending=False)

    save_csv(season_summary, OUT_MANAGER_SEASON)

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
            "starter_assists",
            "bench_assists",
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

    # Validation report.
    report = []
    report.append("API Roster Merge Validation Report")
    report.append("=" * 80)
    report.append(f"Master rows: {len(master):,}")
    report.append(f"API roster rows: {len(rosters):,}")
    report.append(f"Enriched rows: {len(enriched):,}")
    report.append(f"Rostered API rows matched into master: {int(enriched['is_rostered_api'].sum()):,}")
    report.append(f"Unmatched API roster rows check:")

    # API roster rows missing from master.
    master_keys = set(zip(master["fantrax_gw"].astype(str), master["fantrax_player_id"].astype(str)))
    roster_keys = set(zip(roster_api["fantrax_gw"].astype(str), roster_api["fantrax_player_id"].astype(str)))
    missing_api_keys = roster_keys - master_keys

    report.append(f"  API roster player/week keys not found in master: {len(missing_api_keys):,}")

    report.append("")
    report.append("Output files:")
    report.append(f"  {OUT_MANAGER_PLAYER}")
    report.append(f"  {OUT_MANAGER_WEEK}")
    report.append(f"  {OUT_MANAGER_SEASON}")
    report.append(f"  {OUT_LINEUP_QUALITY}")

    report.append("")
    report.append("Notes:")
    report.append("- Missing active starter slots are real league behavior if managers failed to set full lineups.")
    report.append("- manager_week_summary uses API ACTIVE status as starter flag.")
    report.append("- Fantrax stat columns are still from the original master dataset.")
    report.append("- Understat xG/xA/shots are included where player mapping exists.")

    OUT_REPORT.write_text("\n".join(report), encoding="utf-8")

    print("\n".join(report))
    print(f"\nSaved report: {OUT_REPORT}")


if __name__ == "__main__":
    main()
