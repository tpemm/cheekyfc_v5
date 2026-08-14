#!/usr/bin/env python3
r"""
transform_fantrax_api_json.py

Purpose
-------
Flatten raw Fantrax API JSON files into clean CSV tables.

Inputs expected:
    C:\Users\Tommy\fantrax_data\raw_data\fantrax_api\league_info.json
    C:\Users\Tommy\fantrax_data\raw_data\fantrax_api\standings.json

Outputs:
    C:\Users\Tommy\fantrax_data\processed_data\fantrax_api\standings.csv
    C:\Users\Tommy\fantrax_data\processed_data\fantrax_api\matchups_by_week.csv
    C:\Users\Tommy\fantrax_data\processed_data\fantrax_api\player_info.csv
    C:\Users\Tommy\fantrax_data\processed_data\fantrax_api\roster_settings.csv
    C:\Users\Tommy\fantrax_data\processed_data\fantrax_api\scoring_rules.csv
    C:\Users\Tommy\fantrax_data\processed_data\fantrax_api\league_summary.csv

Run:
    python C:\Users\Tommy\fantrax_data\scripts\transform_fantrax_api_json.py

Notes
-----
- Uses encoding="utf-8-sig" for Excel-friendly CSVs.
- Matchups for playoff weeks may contain seeds/TBD instead of team IDs.
- Scoring rules are flattened from scoringCategorySettings when available.
"""

from __future__ import annotations

import sys

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd


# =============================================================================
# CONFIG
# =============================================================================

# Portable project configuration
_PROJECT_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT_BOOTSTRAP))
from config.project_paths import PROJECT_ROOT
from fantrax.utils.cli import configure_unicode_console, safe_console_print

RAW_API_DIR = PROJECT_ROOT / "raw_data" / "fantrax_api"
PROCESSED_API_DIR = PROJECT_ROOT / "processed_data" / "fantrax_api"

LEAGUE_INFO_FILE = RAW_API_DIR / "league_info.json"
STANDINGS_FILE = RAW_API_DIR / "standings.json"


# =============================================================================
# HELPERS
# =============================================================================

def load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_csv(df: pd.DataFrame, path: Path) -> None:
    """Persist first; console diagnostics are deliberately non-fatal."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    safe_console_print(f"Saved: {path}")
    safe_console_print(f"Rows: {len(df)}")
    if len(df):
        try:
            safe_console_print(df.head(5).to_string(index=False))
        except Exception as exc:
            safe_console_print(f"Preview unavailable ({type(exc).__name__}); CSV was saved successfully.")
    safe_console_print()


def parse_record(record_text: Any) -> tuple[int | None, int | None, int | None]:
    """
    Fantrax standings uses a string like "22-0-13".
    For this league, this appears as W-T-L or similar Fantrax record format.
    We preserve the original in record and also split into three numeric parts.
    """
    if record_text is None:
        return None, None, None

    text = str(record_text).strip()
    parts = text.split("-")

    if len(parts) != 3:
        return None, None, None

    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None, None, None


def team_side_to_fields(side: dict[str, Any] | None, prefix: str) -> dict[str, Any]:
    """
    Flatten a matchup side.

    Regular season side:
        {"name": "...", "id": "...", "shortName": "..."}

    Playoff side may be:
        {"seed": 1}
        {"TBD": true}
    """
    side = side or {}

    return {
        f"{prefix}_team_id": side.get("id"),
        f"{prefix}_team_name": side.get("name"),
        f"{prefix}_team_short_name": side.get("shortName"),
        f"{prefix}_seed": side.get("seed"),
        f"{prefix}_tbd": side.get("TBD", False),
    }


def flatten_points_rule(rule: Any) -> str | None:
    """
    Convert simple scoringCategories values like:
        points6
        range0|2|9|1.0$3|99|12|1.0

    into a readable string.

    This keeps the original logic compact while making the CSV easier to inspect.
    """
    if rule is None:
        return None

    text = str(rule)

    if text.startswith("points"):
        return text.replace("points", "")

    if text.startswith("range"):
        return text

    return text


def safe_get(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = d
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
    return cur if cur is not None else default


# =============================================================================
# TRANSFORMS
# =============================================================================

def transform_standings(standings: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []

    for row in standings:
        record = row.get("points")
        rec_a, rec_b, rec_c = parse_record(record)

        rows.append({
            "rank": row.get("rank"),
            "team_id": row.get("teamId"),
            "team_name": row.get("teamName"),
            "record": record,
            "record_part_1": rec_a,
            "record_part_2": rec_b,
            "record_part_3": rec_c,
            "total_points_for": row.get("totalPointsFor"),
            "games_back": row.get("gamesBack"),
            "win_percentage": row.get("winPercentage"),
        })

    df = pd.DataFrame(rows)

    if len(df):
        df = df.sort_values(["rank", "team_name"], na_position="last")

    return df


def transform_matchups(league_info: dict[str, Any]) -> pd.DataFrame:
    rows = []

    for period_obj in league_info.get("matchups", []):
        period = period_obj.get("period")
        matchup_list = period_obj.get("matchupList", [])

        for matchup_index, matchup in enumerate(matchup_list, start=1):
            row = {
                "period": period,
                "matchup_index": matchup_index,
            }

            row.update(team_side_to_fields(matchup.get("home"), "home"))
            row.update(team_side_to_fields(matchup.get("away"), "away"))

            # Useful flags for separating regular season vs playoff TBD/seed rows.
            row["has_team_ids"] = bool(row.get("home_team_id")) and bool(row.get("away_team_id"))
            row["has_seed"] = pd.notna(row.get("home_seed")) or pd.notna(row.get("away_seed"))
            row["has_tbd"] = bool(row.get("home_tbd")) or bool(row.get("away_tbd"))

            rows.append(row)

    df = pd.DataFrame(rows)

    if len(df):
        df = df.sort_values(["period", "matchup_index"], na_position="last")

    return df


def transform_player_info(league_info: dict[str, Any]) -> pd.DataFrame:
    rows = []

    player_info = league_info.get("playerInfo", {})

    for player_id, info in player_info.items():
        eligible_pos_text = info.get("eligiblePos")
        eligible_positions = []
        if eligible_pos_text:
            eligible_positions = [x.strip() for x in str(eligible_pos_text).split(",") if x.strip()]

        rows.append({
            "player_id": player_id,
            "eligible_pos": eligible_pos_text,
            "eligible_pos_count": len(eligible_positions),
            "eligible_pos_list": "|".join(eligible_positions),
            "status": info.get("status"),
        })

    df = pd.DataFrame(rows)

    if len(df):
        df = df.sort_values(["player_id"])

    return df


def transform_roster_settings(league_info: dict[str, Any]) -> pd.DataFrame:
    rows = []

    roster_info = league_info.get("rosterInfo", {})

    # League-wide limits
    rows.append({
        "setting_type": "league_limit",
        "position": None,
        "setting_name": "maxTotalPlayers",
        "setting_value": roster_info.get("maxTotalPlayers"),
    })
    rows.append({
        "setting_type": "league_limit",
        "position": None,
        "setting_name": "maxTotalActivePlayers",
        "setting_value": roster_info.get("maxTotalActivePlayers"),
    })
    rows.append({
        "setting_type": "league_limit",
        "position": None,
        "setting_name": "maxTotalReservePlayers",
        "setting_value": roster_info.get("maxTotalReservePlayers"),
    })

    # Position constraints
    position_constraints = roster_info.get("positionConstraints", {})
    for position, constraints in position_constraints.items():
        for setting_name, setting_value in constraints.items():
            rows.append({
                "setting_type": "position_constraint",
                "position": position,
                "setting_name": setting_name,
                "setting_value": setting_value,
            })

    return pd.DataFrame(rows)


def transform_league_summary(league_info: dict[str, Any]) -> pd.DataFrame:
    """
    One-row league metadata table.
    """
    draft_settings = league_info.get("draftSettings", {})
    pool_settings = league_info.get("poolSettings", {})

    rows = [{
        "league_name": league_info.get("leagueName"),
        "start_date": league_info.get("startDate"),
        "end_date": league_info.get("endDate"),
        "draft_type": draft_settings.get("draftType"),
        "duplicate_player_type": pool_settings.get("duplicatePlayerType"),
        "player_source_type": pool_settings.get("playerSourceType"),
    }]

    return pd.DataFrame(rows)


def transform_scoring_rules_from_settings(league_info: dict[str, Any]) -> pd.DataFrame:
    """
    Preferred scoring rules transform.

    league_info["scoringSystem"]["scoringCategorySettings"] has readable names,
    category IDs, short names, position groups, config-level positions,
    points, ranges, and cumulative flags.
    """
    rows = []

    settings = safe_get(league_info, "scoringSystem", "scoringCategorySettings", default=[])

    for group_obj in settings:
        group = group_obj.get("group", {})

        group_code = group.get("code")
        group_name = group.get("name")
        group_id = group.get("id")
        group_short_name = group.get("shortName")

        for config in group_obj.get("configs", []):
            position = config.get("position", {})
            category = config.get("scoringCategory", {})

            ranges = config.get("ranges")
            range_text = None
            if ranges:
                range_parts = []
                for r in ranges:
                    start = safe_get(r, "range", "start")
                    end = safe_get(r, "range", "end")
                    points = r.get("points")
                    interval = r.get("interval")
                    range_parts.append(f"{start}-{end}: {points} per {interval}")
                range_text = " | ".join(range_parts)

            rows.append({
                "group_code": group_code,
                "group_name": group_name,
                "group_id": group_id,
                "group_short_name": group_short_name,

                "config_position_code": position.get("code"),
                "config_position_name": position.get("name"),
                "config_position_id": position.get("id"),
                "config_position_short_name": position.get("shortName"),

                "category_code": category.get("code"),
                "category_name": category.get("name"),
                "category_id": category.get("id"),
                "category_short_name": category.get("shortName"),

                "points": config.get("points"),
                "cumulative": config.get("cumulative"),
                "range_type": config.get("rangeType"),
                "ranges": range_text,
            })

    df = pd.DataFrame(rows)

    if len(df):
        df = df.sort_values(
            ["group_short_name", "category_short_name", "config_position_short_name"],
            na_position="last",
        )

    return df


def transform_scoring_rules_compact(league_info: dict[str, Any]) -> pd.DataFrame:
    """
    Backup/compact scoring rules transform from:
        scoringSystem.scoringCategories

    This captures the raw points/range strings by group/category/position override.
    """
    rows = []

    scoring_categories = safe_get(league_info, "scoringSystem", "scoringCategories", default={})

    for scoring_group, categories in scoring_categories.items():
        for category_short_name, pos_rules in categories.items():
            if not isinstance(pos_rules, dict):
                rows.append({
                    "scoring_group": scoring_group,
                    "category_short_name": category_short_name,
                    "position": None,
                    "rule_raw": pos_rules,
                    "rule_readable": flatten_points_rule(pos_rules),
                })
                continue

            for position, rule in pos_rules.items():
                rows.append({
                    "scoring_group": scoring_group,
                    "category_short_name": category_short_name,
                    "position": position,
                    "rule_raw": rule,
                    "rule_readable": flatten_points_rule(rule),
                })

    df = pd.DataFrame(rows)

    if len(df):
        df = df.sort_values(["scoring_group", "category_short_name", "position"], na_position="last")

    return df


# =============================================================================
# MAIN
# =============================================================================

def main() -> None:
    configure_unicode_console()
    print("Fantrax API JSON Transformer")
    print(f"Raw API dir:       {RAW_API_DIR}")
    print(f"Processed API dir: {PROCESSED_API_DIR}")
    print()

    league_info = load_json(LEAGUE_INFO_FILE)
    standings = load_json(STANDINGS_FILE)

    PROCESSED_API_DIR.mkdir(parents=True, exist_ok=True)

    # Core outputs
    standings_df = transform_standings(standings)
    save_csv(standings_df, PROCESSED_API_DIR / "standings.csv")

    matchups_df = transform_matchups(league_info)
    save_csv(matchups_df, PROCESSED_API_DIR / "matchups_by_week.csv")

    player_info_df = transform_player_info(league_info)
    save_csv(player_info_df, PROCESSED_API_DIR / "player_info.csv")

    roster_settings_df = transform_roster_settings(league_info)
    save_csv(roster_settings_df, PROCESSED_API_DIR / "roster_settings.csv")

    league_summary_df = transform_league_summary(league_info)
    save_csv(league_summary_df, PROCESSED_API_DIR / "league_summary.csv")

    # Scoring outputs
    scoring_rules_df = transform_scoring_rules_from_settings(league_info)
    save_csv(scoring_rules_df, PROCESSED_API_DIR / "scoring_rules.csv")

    compact_scoring_df = transform_scoring_rules_compact(league_info)
    save_csv(compact_scoring_df, PROCESSED_API_DIR / "scoring_rules_compact.csv")

    print("DONE")
    print("Recommended next checks:")
    print("1. Open processed_data/fantrax_api/matchups_by_week.csv")
    print("2. Open processed_data/fantrax_api/standings.csv")
    print("3. Open processed_data/fantrax_api/scoring_rules.csv")
    print("4. Confirm player_info.csv has player IDs matching rosters_by_week.csv")


if __name__ == "__main__":
    main()
