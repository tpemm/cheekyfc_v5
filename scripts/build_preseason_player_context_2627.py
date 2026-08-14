from __future__ import annotations

import argparse
import html
import re
import sys
import unicodedata
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

HISTORICAL_SEASON = "2526"
TARGET_SEASON = "2627"


def discover_one(patterns: Iterable[str]) -> Path | None:
    for pattern in patterns:
        matches = sorted(PROJECT_ROOT.glob(pattern))
        if matches:
            return matches[0]
    return None


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig", low_memory=False)


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def normalize_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = html.unescape(str(value))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


TEAM_ALIASES = {
    "afc bournemouth": "bournemouth",
    "brighton and hove albion": "brighton",
    "brighton hove albion": "brighton",
    "manchester city": "man city",
    "manchester united": "man united",
    "newcastle united": "newcastle",
    "nottingham forest": "nottm forest",
    "tottenham hotspur": "tottenham",
    "wolverhampton wanderers": "wolves",
    "west ham united": "west ham",
    "leeds united": "leeds",
    "sunderland afc": "sunderland",
}


def normalize_team(value: object) -> str:
    clean = normalize_text(value)
    return TEAM_ALIASES.get(clean, clean)


def choose_column(frame: pd.DataFrame, candidates: Iterable[str], required: bool = False) -> str | None:
    lower_map = {str(col).casefold(): str(col) for col in frame.columns}
    for candidate in candidates:
        if candidate.casefold() in lower_map:
            return lower_map[candidate.casefold()]
    if required:
        raise KeyError("Missing required column. Tried: " + ", ".join(candidates))
    return None


def aggregate_historical_fantrax(master: pd.DataFrame) -> pd.DataFrame:
    id_col = choose_column(master, ["fantrax_player_id", "player_id", "fantrax_id"], True)
    name_col = choose_column(master, ["player_name_display", "player_name", "fantrax_player_name", "name"], True)
    team_col = choose_column(master, ["team", "team_name", "fantrax_team", "player_team", "club"])
    position_col = choose_column(master, ["position", "positions", "fantrax_position", "eligible_positions"])
    gw_col = choose_column(master, ["fantrax_gw", "gw", "gameweek"])

    metric_candidates = {
        "minutes": ["mgr_min", "minutes", "fantrax_minutes", "num_minutes"],
        "fantasy_points": ["mgr_fantasy_points", "fantasy_points", "official_fantasy_points", "num_fantasy_points"],
        "goals": ["mgr_g", "goals", "num_goals"],
        "assists": ["mgr_at", "assists_total", "assists", "num_assists_total"],
        "key_passes": ["mgr_kp", "key_passes", "num_key_passes"],
        "shots_on_target": ["mgr_sot", "shots_on_target", "num_shots_on_target"],
        "tackles_won": ["mgr_tkw", "tackles_won", "num_tackles_won"],
        "interceptions": ["mgr_int", "interceptions", "num_interceptions"],
        "clearances": ["mgr_clr", "clearances", "num_clearances"],
        "aerials_won": ["mgr_aer", "aerials_won", "num_aerials_won"],
        "successful_dribbles": ["mgr_cos", "successful_dribbles", "num_successful_dribbles"],
    }

    working = pd.DataFrame({
        "fantrax_player_id": master[id_col].astype(str),
        "fantrax_player_name": master[name_col].astype(str),
        "historical_team": master[team_col].astype(str) if team_col else "",
        "historical_position": master[position_col].astype(str) if position_col else "",
        "fantrax_gw": numeric(master[gw_col]) if gw_col else np.nan,
    })

    for metric, candidates in metric_candidates.items():
        source = choose_column(master, candidates)
        working[metric] = numeric(master[source]) if source else np.nan

    identity = (
        working.sort_values("fantrax_gw")
        .groupby("fantrax_player_id", as_index=False)
        .agg(
            fantrax_player_name=("fantrax_player_name", "last"),
            historical_team=("historical_team", "last"),
            historical_position=("historical_position", "last"),
            historical_weeks=("fantrax_gw", "nunique"),
        )
    )

    sums = working.groupby("fantrax_player_id", as_index=False)[list(metric_candidates)].sum(min_count=1)
    sums = sums.rename(columns={c: f"fantrax_2526_{c}" for c in metric_candidates})
    output = identity.merge(sums, on="fantrax_player_id", how="left", validate="one_to_one")

    mins = output["fantrax_2526_minutes"].replace(0, np.nan)
    output["fantrax_2526_fp_per90"] = output["fantrax_2526_fantasy_points"] / mins * 90
    output["fantrax_2526_key_passes_per90"] = output["fantrax_2526_key_passes"] / mins * 90
    output["fantrax_2526_tackles_won_per90"] = output["fantrax_2526_tackles_won"] / mins * 90
    output["player_name_key"] = output["fantrax_player_name"].map(normalize_text)
    output["historical_team_key"] = output["historical_team"].map(normalize_team)
    return output


def normalize_understat(players: pd.DataFrame) -> pd.DataFrame:
    id_col = choose_column(players, ["player_id", "understat_player_id"], True)
    name_col = choose_column(players, ["player", "player_name", "name"], True)
    team_col = choose_column(players, ["team", "team_name"], True)
    position_col = choose_column(players, ["position", "pos"])

    output = pd.DataFrame({
        "understat_player_id": players[id_col].astype(str),
        "understat_player_name": players[name_col].astype(str),
        "understat_team_2526": players[team_col].astype(str),
        "understat_position": players[position_col].astype(str) if position_col else "",
    })

    aliases = {
        "matches": ["matches"], "minutes": ["minutes"], "goals": ["goals"],
        "xg": ["xg"], "np_goals": ["np_goals", "npg"], "npxg": ["np_xg", "npxg"],
        "assists": ["assists"], "xa": ["xa"], "shots": ["shots"],
        "key_passes": ["key_passes"], "xg_chain": ["xg_chain", "xgchain"],
        "xg_buildup": ["xg_buildup", "xgbuildup"],
    }
    for metric, candidates in aliases.items():
        source = choose_column(players, candidates)
        output[f"understat_2526_{metric}"] = numeric(players[source]) if source else np.nan

    mins = output["understat_2526_minutes"].replace(0, np.nan)
    for metric in ["xg", "npxg", "xa", "shots", "key_passes"]:
        output[f"understat_2526_{metric}_per90"] = output[f"understat_2526_{metric}"] / mins * 90

    output["player_name_key"] = output["understat_player_name"].map(normalize_text)
    output["understat_team_key"] = output["understat_team_2526"].map(normalize_team)
    return output


def normalize_football_players(players: pd.DataFrame) -> pd.DataFrame:
    id_col = choose_column(players, ["football_data_player_id", "player_id"], True)
    name_col = choose_column(players, ["known_name", "player_name", "football_data_player_name"], True)
    full_name_col = choose_column(players, ["player_name", "full_name"])
    team_id_col = choose_column(players, ["team_id", "football_data_team_id"])
    team_col = choose_column(players, ["team_name", "football_data_team_name"])
    position_col = choose_column(players, ["position", "position_name"])
    dob_col = choose_column(players, ["date_of_birth", "dob"])
    nationality_col = choose_column(players, ["nationality"])

    output = pd.DataFrame({
        "football_data_player_id": players[id_col].astype(str),
        "football_data_player_name": players[name_col].astype(str),
        "football_data_full_name": players[full_name_col].astype(str) if full_name_col else players[name_col].astype(str),
        "football_data_team_id": players[team_id_col].astype(str) if team_id_col else "",
        "current_team": players[team_col].astype(str) if team_col else "",
        "football_data_position": players[position_col].astype(str) if position_col else "",
        "date_of_birth": players[dob_col].astype(str) if dob_col else "",
        "nationality": players[nationality_col].astype(str) if nationality_col else "",
    })
    output["player_name_key"] = output["football_data_player_name"].map(normalize_text)
    output["full_name_key"] = output["football_data_full_name"].map(normalize_text)
    output["current_team_key"] = output["current_team"].map(normalize_team)
    return output.drop_duplicates("football_data_player_id", keep="last")


def load_understat_map(path: Path | None) -> pd.DataFrame:
    if path is None or not path.exists():
        return pd.DataFrame()
    frame = read_csv(path)
    fantrax_col = choose_column(frame, ["fantrax_player_id", "fantrax_id"], True)
    understat_col = choose_column(frame, ["understat_player_id", "understat_id"], True)
    output = frame[[fantrax_col, understat_col]].copy()
    output.columns = ["fantrax_player_id", "understat_player_id"]
    output = output.astype(str)
    return output.drop_duplicates("fantrax_player_id", keep="last")


def attach_understat(historical: pd.DataFrame, understat: pd.DataFrame, mapping: pd.DataFrame) -> pd.DataFrame:
    output = historical.copy()
    if not mapping.empty:
        output = output.merge(mapping, on="fantrax_player_id", how="left", validate="one_to_one")
        output = output.merge(understat.drop(columns=["player_name_key"], errors="ignore"), on="understat_player_id", how="left", validate="many_to_one")
        output["understat_match_type"] = np.where(output["understat_player_name"].notna(), "existing_crosswalk", "")
        output["understat_match_score"] = np.where(output["understat_player_name"].notna(), 100, np.nan)
    else:
        output["understat_player_id"] = np.nan
        output["understat_match_type"] = ""
        output["understat_match_score"] = np.nan

    unresolved = output["understat_player_id"].isna()
    unique_names = understat.drop_duplicates("player_name_key", keep=False)
    candidates = output.loc[unresolved, ["fantrax_player_id", "player_name_key", "historical_team_key"]].merge(unique_names, on="player_name_key", how="left").set_index("fantrax_player_id")
    output = output.set_index("fantrax_player_id")

    for column in [c for c in understat.columns if c != "player_name_key"]:
        if column not in output.columns:
            output[column] = np.nan
        output.loc[candidates.index, column] = candidates[column]

    matched = candidates["understat_player_id"].notna()
    team_match = candidates["historical_team_key"].ne("") & candidates["understat_team_key"].ne("") & candidates["historical_team_key"].eq(candidates["understat_team_key"])
    output.loc[candidates.index[matched], "understat_match_type"] = "exact_name"
    output.loc[candidates.index[matched], "understat_match_score"] = 88
    output.loc[candidates.index[matched & team_match], "understat_match_type"] = "exact_name_team"
    output.loc[candidates.index[matched & team_match], "understat_match_score"] = 96
    output = output.reset_index()
    output["understat_match_status"] = np.select(
        [output["understat_match_score"].ge(95), output["understat_match_score"].ge(85), output["understat_match_score"].notna()],
        ["high", "review", "low"], default="unmatched"
    )
    return output


def match_football_data(historical: pd.DataFrame, football: pd.DataFrame) -> pd.DataFrame:
    unique_known = football.drop_duplicates("player_name_key", keep=False)
    output = historical.merge(unique_known, on="player_name_key", how="left")
    output["football_match_type"] = np.where(output["football_data_player_id"].notna(), "exact_name", "")
    output["football_match_score"] = np.where(output["football_data_player_id"].notna(), 90, np.nan)
    same_team = output["historical_team_key"].ne("") & output["current_team_key"].ne("") & output["historical_team_key"].eq(output["current_team_key"])
    output.loc[output["football_data_player_id"].notna() & same_team, ["football_match_type", "football_match_score"]] = ["exact_name_team", 98]

    unresolved = output["football_data_player_id"].isna()
    unique_full = football.drop_duplicates("full_name_key", keep=False)
    candidates = output.loc[unresolved, ["fantrax_player_id", "player_name_key"]].merge(unique_full, left_on="player_name_key", right_on="full_name_key", how="left").set_index("fantrax_player_id")
    output = output.set_index("fantrax_player_id")
    for column in ["football_data_player_id", "football_data_player_name", "football_data_full_name", "football_data_team_id", "current_team", "football_data_position", "date_of_birth", "nationality", "current_team_key"]:
        output.loc[candidates.index, column] = candidates[column]
    matched = candidates["football_data_player_id"].notna()
    output.loc[candidates.index[matched], "football_match_type"] = "exact_full_name"
    output.loc[candidates.index[matched], "football_match_score"] = 88
    output = output.reset_index()
    output["football_match_status"] = np.select(
        [output["football_match_score"].ge(95), output["football_match_score"].ge(85), output["football_match_score"].notna()],
        ["high", "review", "low"], default="unmatched"
    )
    return output


def attach_team_context(players: pd.DataFrame, team_strength: pd.DataFrame, fixture_strength: pd.DataFrame) -> pd.DataFrame:
    output = players.copy()
    ts_name = choose_column(team_strength, ["team_name", "team", "current_team"], True)
    team_strength = team_strength.copy()
    team_strength["team_key"] = team_strength[ts_name].map(normalize_team)
    output = output.merge(team_strength.drop(columns=[ts_name], errors="ignore"), left_on="current_team_key", right_on="team_key", how="left", suffixes=("", "_team"))

    fixtures = fixture_strength.copy()
    fixture_team = choose_column(fixtures, ["team_name", "team", "perspective_team", "club"], True)
    gw_col = choose_column(fixtures, ["game_week", "game_week_estimate", "fixture_order"])
    ease_col = choose_column(fixtures, ["overall_fixture_ease", "fixture_ease", "attacker_fixture_ease"], True)
    difficulty_col = choose_column(fixtures, ["fixture_difficulty"])
    fixtures["team_key"] = fixtures[fixture_team].map(normalize_team)
    fixtures["fixture_sort"] = numeric(fixtures[gw_col]) if gw_col else np.arange(len(fixtures))
    fixtures["fixture_ease_value"] = numeric(fixtures[ease_col])
    fixtures["fixture_difficulty_value"] = numeric(fixtures[difficulty_col]) if difficulty_col else 100 - fixtures["fixture_ease_value"]
    fixtures = fixtures.sort_values(["team_key", "fixture_sort"])

    rows = []
    for team_key, group in fixtures.groupby("team_key", dropna=False):
        rows.append({
            "team_key": team_key,
            "fixture_count_available": len(group),
            "fixture_ease_next_3": group["fixture_ease_value"].head(3).mean(),
            "fixture_ease_next_5": group["fixture_ease_value"].head(5).mean(),
            "fixture_ease_next_10": group["fixture_ease_value"].head(10).mean(),
            "fixture_difficulty_next_5": group["fixture_difficulty_value"].head(5).mean(),
        })
    fixture_summary = pd.DataFrame(rows)
    return output.merge(fixture_summary, left_on="current_team_key", right_on="team_key", how="left", suffixes=("", "_fixture"))


def add_transition_flags(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    output["team_changed_for_2627"] = output["historical_team_key"].ne("") & output["current_team_key"].ne("") & output["historical_team_key"].ne(output["current_team_key"])
    output["in_current_2627_player_pool"] = output["football_data_player_id"].notna()
    output["has_understat_2526"] = output["understat_player_id"].notna()
    output["has_fantrax_2526_history"] = output["fantrax_2526_fantasy_points"].notna()
    output["identity_confidence"] = output[["football_match_score", "understat_match_score"]].mean(axis=1, skipna=True).fillna(0).round(1)
    output["data_completeness_score"] = output[["has_fantrax_2526_history", "has_understat_2526", "in_current_2627_player_pool"]].astype(int).mean(axis=1).mul(100).round(1)
    output["preseason_context_status"] = np.select(
        [
            output["in_current_2627_player_pool"] & output["has_understat_2526"] & output["identity_confidence"].ge(95),
            output["in_current_2627_player_pool"] & output["identity_confidence"].ge(85),
            output["in_current_2627_player_pool"],
        ],
        ["ready", "review", "current_pool_unmatched_history"],
        default="not_in_current_pool",
    )
    output["historical_source_season"] = HISTORICAL_SEASON
    output["projection_target_season"] = TARGET_SEASON
    output["projection_stage"] = "preseason"
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Build 2026/27 preseason player context from 2025/26 Fantrax + Understat history and FootballData.io context.")
    parser.add_argument("--master", type=Path)
    parser.add_argument("--understat", type=Path)
    parser.add_argument("--understat-map", type=Path)
    args = parser.parse_args()

    master_path = args.master or discover_one(["data/**/master_player_weekly_2526.csv", "**/master_player_weekly_2526.csv"])
    understat_path = args.understat or discover_one(["data/**/understat_players_season_2526_ENG-Premier_League.csv", "**/understat_players_season_2526_ENG-Premier_League.csv"])
    map_path = args.understat_map or discover_one(["data/**/understat_fantrax_player_id_map.csv", "**/understat_fantrax_player_id_map.csv"])
    football_players_path = PROJECT_ROOT / "data" / "analytics" / "draft" / "football_players_2526.csv"
    team_strength_path = PROJECT_ROOT / "data" / "analytics" / "draft" / "team_strength_2526.csv"
    fixture_strength_path = PROJECT_ROOT / "data" / "analytics" / "draft" / "fixture_difficulty_2627.csv"

    required = {
        "Fantrax historical master": master_path,
        "Understat 2025/26 season players": understat_path,
        "FootballData normalized players": football_players_path,
        "Team strength": team_strength_path,
        "Fixture strength": fixture_strength_path,
    }
    missing = [f"{label}: {path}" for label, path in required.items() if path is None or not Path(path).exists()]
    if missing:
        raise FileNotFoundError("Required input files were not found:\n  - " + "\n  - ".join(missing))

    print(f"Historical Fantrax: {master_path}")
    print(f"Historical Understat: {understat_path}")
    print(f"Understat crosswalk: {map_path or 'not found'}")
    print(f"Current football pool: {football_players_path}")

    historical = aggregate_historical_fantrax(read_csv(master_path))
    understat = normalize_understat(read_csv(understat_path))
    football = normalize_football_players(read_csv(football_players_path))
    mapping = load_understat_map(map_path)

    merged = attach_understat(historical, understat, mapping)
    merged = match_football_data(merged, football)
    merged = attach_team_context(merged, read_csv(team_strength_path), read_csv(fixture_strength_path))
    merged = add_transition_flags(merged)

    output_dir = PROJECT_ROOT / "data" / "models" / "preseason_2627"
    review_dir = PROJECT_ROOT / "data" / "quality" / "preseason_2627"
    output_dir.mkdir(parents=True, exist_ok=True)
    review_dir.mkdir(parents=True, exist_ok=True)

    full_output = output_dir / "player_context_preseason_2627.csv"
    current_output = output_dir / "current_player_pool_2627.csv"
    identity_output = output_dir / "player_identity_crosswalk_2627.csv"
    review_output = review_dir / "player_identity_review_2627.csv"

    merged.to_csv(full_output, index=False, encoding="utf-8-sig")
    current = merged[merged["in_current_2627_player_pool"]].copy()
    current.to_csv(current_output, index=False, encoding="utf-8-sig")

    identity_cols = [
        "fantrax_player_id", "fantrax_player_name", "understat_player_id", "understat_player_name",
        "football_data_player_id", "football_data_player_name", "historical_team", "current_team",
        "team_changed_for_2627", "understat_match_type", "understat_match_score",
        "football_match_type", "football_match_score", "identity_confidence", "preseason_context_status",
    ]
    merged[[c for c in identity_cols if c in merged.columns]].to_csv(identity_output, index=False, encoding="utf-8-sig")
    review = merged[merged["preseason_context_status"].ne("ready") | merged["team_changed_for_2627"]].copy()
    review.to_csv(review_output, index=False, encoding="utf-8-sig")

    print("\n2026/27 preseason context complete.")
    print(f"Historical players: {len(merged):,}")
    print(f"Current 2026/27 player matches: {len(current):,}")
    print(f"Ready identities: {int(merged['preseason_context_status'].eq('ready').sum()):,}")
    print(f"Review identities: {int(merged['preseason_context_status'].eq('review').sum()):,}")
    print(f"Team changes detected: {int(merged['team_changed_for_2627'].sum()):,}")
    print(f"Saved: {full_output}")
    print(f"Saved: {current_output}")
    print(f"Saved: {identity_output}")
    print(f"Saved: {review_output}")


if __name__ == "__main__":
    main()
