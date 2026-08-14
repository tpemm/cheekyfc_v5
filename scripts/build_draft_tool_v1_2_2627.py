from __future__ import annotations

import argparse
import html
import re
import unicodedata
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def discover(patterns: Iterable[str]) -> Path | None:
    for pattern in patterns:
        matches = sorted(PROJECT_ROOT.glob(pattern))
        if matches:
            return matches[0]
    return None


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig", low_memory=False)


def normalize_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = html.unescape(str(value))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


TEAM_ALIASES = {
    "afc bournemouth": "BOU",
    "bournemouth": "BOU",
    "arsenal": "ARS",
    "aston villa": "AVL",
    "brentford": "BRE",
    "brighton and hove albion": "BHA",
    "brighton": "BHA",
    "burnley": "BUR",
    "chelsea": "CHE",
    "coventry city": "COV",
    "crystal palace": "CRY",
    "everton": "EVE",
    "hull city": "HUL",
    "leeds united": "LEE",
    "leeds": "LEE",
    "liverpool": "LIV",
    "manchester city": "MCI",
    "man city": "MCI",
    "manchester united": "MUN",
    "man united": "MUN",
    "newcastle united": "NEW",
    "newcastle": "NEW",
    "nottingham forest": "NFO",
    "nottm forest": "NFO",
    "sunderland": "SUN",
    "tottenham hotspur": "TOT",
    "tottenham": "TOT",
    "west ham united": "WHU",
    "west ham": "WHU",
    "wolverhampton wanderers": "WOL",
    "wolves": "WOL",
}




def normalize_player_id(value: object) -> str:
    """Normalize Fantrax IDs across API, bridge, and historical files.

    Historical exports commonly wrap IDs in asterisks (for example *06fv8*)
    while API files store the same ID as 06fv8.
    """
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip().casefold()
    text = re.sub(r"[^a-z0-9]", "", text)
    return text

def normalize_team(value: object) -> str:
    clean = normalize_text(value)
    if clean.upper() in set(TEAM_ALIASES.values()):
        return clean.upper()
    return TEAM_ALIASES.get(clean, str(value).strip().upper())


def choose_column(frame: pd.DataFrame, candidates: Iterable[str], required: bool = False) -> str | None:
    lookup = {str(column).casefold(): str(column) for column in frame.columns}
    for candidate in candidates:
        if candidate.casefold() in lookup:
            return lookup[candidate.casefold()]
    if required:
        raise KeyError("Missing required column. Tried: " + ", ".join(candidates))
    return None


def number(frame: pd.DataFrame, candidates: Iterable[str], default=np.nan) -> pd.Series:
    column = choose_column(frame, candidates)
    if column is None:
        return pd.Series(default, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def percentile(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    ranked = numeric.rank(pct=True, method="average")
    if not higher_is_better:
        ranked = 1 - ranked
    return ranked.fillna(0.0) * 100


def percent_number(series: pd.Series) -> pd.Series:
    """Convert Fantrax percentage strings such as 100% or 12.5% to numbers."""
    return pd.to_numeric(
        series.astype(str).str.replace("%", "", regex=False).str.strip(),
        errors="coerce",
    )


def load_current_fantrax(path: Path) -> pd.DataFrame:
    """Load either the API lookup or Fantrax's downloadable player export."""
    raw = read_csv(path)
    id_col = choose_column(raw, ["ID", "api_player_id", "fantrax_player_id", "player_id"], required=True)
    name_col = choose_column(raw, ["Player", "api_player_name", "fantrax_player_name", "player_name", "name"], required=True)
    team_col = choose_column(raw, ["Team", "api_team_code", "team_code", "team", "team_short_name"], required=True)
    pos_col = choose_column(raw, ["Position", "api_position", "position", "positions"], required=True)

    output = pd.DataFrame({
        "fantrax_player_id": raw[id_col].map(normalize_player_id),
        "player_name": raw[name_col].astype(str).str.strip(),
        "team_2627": raw[team_col].map(normalize_team),
        "position_2627": raw[pos_col].astype(str).str.strip(),
    })

    adp_col = choose_column(raw, [
        "ADP", "adp", "fantrax_adp", "average_draft_position", "avg_draft_position",
        "avgdraftposition", "draft_position"
    ])
    rank_col = choose_column(raw, [
        "RkOv", "rkov", "overall_rank", "adp_rank", "fantrax_adp_rank",
        "draft_rank", "consensus_rank", "rank"
    ])
    projected_points_col = choose_column(raw, [
        "FPts", "fpts", "projected_points", "fantrax_projected_points", "proj_points"
    ])
    projected_ppg_col = choose_column(raw, [
        "FP/G", "fp/g", "projected_ppg", "fantrax_projected_ppg", "proj_ppg"
    ])
    drafted_col = choose_column(raw, ["%D", "%d", "drafted_pct", "percent_drafted"])
    rostered_col = choose_column(raw, [
        "rostered_pct", "rostered_percent", "ownership_pct", "percent_owned"
    ])
    ros_col = choose_column(raw, ["Ros", "ros", "rest_of_season", "ros_rating"])
    plus_minus_col = choose_column(raw, ["+/-", "plus_minus", "change_pct"])
    status_col = choose_column(raw, ["Status", "status"])
    opponent_col = choose_column(raw, ["Opponent", "opponent"])

    output["fantrax_adp"] = pd.to_numeric(raw[adp_col], errors="coerce") if adp_col else np.nan
    output["fantrax_overall_rank"] = pd.to_numeric(raw[rank_col], errors="coerce") if rank_col else np.nan
    # Keep a market-rank alias for the existing value-vs-ADP logic. ADP remains
    # the preferred comparison where available.
    output["fantrax_adp_rank"] = output["fantrax_overall_rank"]
    output["fantrax_projected_points"] = pd.to_numeric(raw[projected_points_col], errors="coerce") if projected_points_col else np.nan
    output["fantrax_projected_ppg"] = pd.to_numeric(raw[projected_ppg_col], errors="coerce") if projected_ppg_col else np.nan
    output["drafted_pct"] = percent_number(raw[drafted_col]) if drafted_col else np.nan
    output["rostered_pct"] = percent_number(raw[rostered_col]) if rostered_col else np.nan
    output["fantrax_ros_pct"] = percent_number(raw[ros_col]) if ros_col else np.nan
    output["fantrax_plus_minus_pct"] = percent_number(raw[plus_minus_col]) if plus_minus_col else np.nan
    output["fantrax_status"] = raw[status_col].astype(str).str.strip() if status_col else ""
    output["opening_opponent"] = raw[opponent_col].astype(str).str.strip() if opponent_col else ""
    output["player_name_key"] = output["player_name"].map(normalize_text)
    return output[output["fantrax_player_id"].ne("")].drop_duplicates("fantrax_player_id", keep="last")

def build_historical_player_summary(master: pd.DataFrame) -> pd.DataFrame:
    id_col = choose_column(master, ["fantrax_player_id", "player_id", "api_player_id"], required=True)
    name_col = choose_column(master, ["player_name_display", "player_name", "fantrax_player_name", "name"], required=True)
    gw_col = choose_column(master, ["fantrax_gw", "gw", "gameweek"])
    team_col = choose_column(master, ["team", "team_name", "fantrax_team", "club"])
    pos_col = choose_column(master, ["position", "positions", "fantrax_position"])

    working = pd.DataFrame({
        "fantrax_player_id": master[id_col].map(normalize_player_id),
        "historical_name": master[name_col].astype(str).str.strip(),
        "historical_team": master[team_col].map(normalize_team) if team_col else "",
        "historical_position": master[pos_col].astype(str) if pos_col else "",
        "gw": number(master, ["fantrax_gw", "gw", "gameweek"]),
        "minutes": number(master, ["mgr_min", "minutes", "fantrax_minutes", "num_minutes"]),
        "fantasy_points": number(master, [
            "official_fantasy_points", "mgr_fantasy_points", "fantasy_points",
            "num_fantasy_points", "fpts"
        ]),
        "ghost_points": number(master, [
            "ghost_points", "ghost_points_total", "non_gacs_points",
            "ghost_fantasy_points"
        ]),
        "goals": number(master, ["mgr_g", "goals", "num_goals"]),
        "assists": number(master, ["mgr_at", "assists_total", "assists", "num_assists_total"]),
        "starts": number(master, ["mgr_gs", "starts", "num_starts", "started"]),
        "understat_xg": number(master, ["understat_xg", "xg"]),
        "understat_xa": number(master, ["understat_xa", "xa"]),
        "understat_npxg": number(master, ["understat_npxg", "npxg", "np_xg"]),
        "understat_key_passes": number(master, ["understat_key_passes", "key_passes"]),
        "understat_minutes": number(master, ["understat_minutes", "minutes"]),
        "understat_player_id": (
            master[choose_column(master, ["understat_player_id"])].astype(str)
            if choose_column(master, ["understat_player_id"]) else ""
        ),
    })

    # Master weekly files may repeat season totals or contain weekly values.
    # Prefer a weekly sum, but only across one row per player-week.
    working = working.sort_values(["fantrax_player_id", "gw"]).drop_duplicates(
        ["fantrax_player_id", "gw"], keep="last"
    )

    # Fallback start proxy where an explicit start field is absent.
    if working["starts"].isna().all():
        working["starts"] = (working["minutes"] >= 60).astype(float)

    max_gw = working["gw"].max()
    recent = working[working["gw"] >= max_gw - 5].copy() if pd.notna(max_gw) else working.iloc[0:0]

    agg = working.groupby("fantrax_player_id", as_index=False).agg(
        historical_name=("historical_name", "last"),
        team_2526=("historical_team", "last"),
        position_2526=("historical_position", "last"),
        weeks_available=("gw", "nunique"),
        minutes_2526=("minutes", "sum"),
        starts_2526=("starts", "sum"),
        fantasy_points_2526=("fantasy_points", "sum"),
        ghost_points_2526=("ghost_points", "sum"),
        goals_2526=("goals", "sum"),
        assists_2526=("assists", "sum"),
        understat_xg_2526=("understat_xg", "sum"),
        understat_xa_2526=("understat_xa", "sum"),
        understat_npxg_2526=("understat_npxg", "sum"),
        understat_key_passes_2526=("understat_key_passes", "sum"),
        understat_minutes_2526=("understat_minutes", "sum"),
        understat_player_id=("understat_player_id", "last"),
    )

    recent_agg = recent.groupby("fantrax_player_id", as_index=False).agg(
        recent_minutes_6=("minutes", "sum"),
        recent_starts_6=("starts", "sum"),
        recent_fp_6=("fantasy_points", "sum"),
    )
    agg = agg.merge(recent_agg, on="fantrax_player_id", how="left")

    played_weeks = agg["weeks_available"].replace(0, np.nan)
    minutes = agg["minutes_2526"].replace(0, np.nan)
    agg["fantasy_ppg_2526"] = agg["fantasy_points_2526"] / played_weeks
    agg["ghost_ppg_2526"] = agg["ghost_points_2526"] / played_weeks
    agg["fantasy_fp90_2526"] = agg["fantasy_points_2526"] / minutes * 90
    agg["xgi90_2526"] = (
        agg["understat_xg_2526"].fillna(0) + agg["understat_xa_2526"].fillna(0)
    ) / agg["understat_minutes_2526"].replace(0, np.nan) * 90
    agg["start_rate_2526"] = agg["starts_2526"] / played_weeks
    agg["recent_start_rate_6"] = agg["recent_starts_6"] / 6
    return agg


def attach_bridge(current: pd.DataFrame, bridge_path: Path | None) -> pd.DataFrame:
    if bridge_path is None or not bridge_path.exists():
        current["historical_fantrax_player_id"] = current["fantrax_player_id"]
        return current

    bridge = read_csv(bridge_path)
    api_col = choose_column(bridge, ["api_player_id", "fantrax_api_player_id"], required=True)
    historical_col = choose_column(bridge, ["fantrax_player_id", "master_player_id"], required=True)
    keep = pd.DataFrame({
        "fantrax_player_id": bridge[api_col].map(normalize_player_id),
        "historical_fantrax_player_id": bridge[historical_col].map(normalize_player_id),
    }).drop_duplicates("fantrax_player_id", keep="last")
    output = current.merge(keep, on="fantrax_player_id", how="left")
    output["historical_fantrax_player_id"] = output["historical_fantrax_player_id"].fillna(output["fantrax_player_id"])
    return output


def attach_ghost_points(players: pd.DataFrame, ghost_path: Path | None) -> pd.DataFrame:
    """Attach authoritative player ghost totals from the existing analytics view."""
    out = players.copy()
    if ghost_path is None or not ghost_path.exists():
        return out

    raw = read_csv(ghost_path)
    id_col = choose_column(raw, ["fantrax_player_id", "player_id", "api_player_id"], required=True)
    total_col = choose_column(raw, ["total_ghost_points", "ghost_points_2526", "ghost_points"])
    avg_col = choose_column(raw, ["avg_ghost_points", "ghost_ppg_2526", "ghost_ppg"])
    appearances_col = choose_column(raw, ["appearances", "weeks_available", "games_played"])
    fantasy_col = choose_column(raw, ["total_fantasy_points", "fantasy_points_2526"])

    ghost = pd.DataFrame({
        "historical_fantrax_player_id": raw[id_col].map(normalize_player_id),
        "ghost_points_2526_authoritative": pd.to_numeric(raw[total_col], errors="coerce") if total_col else np.nan,
        "ghost_ppg_2526_authoritative": pd.to_numeric(raw[avg_col], errors="coerce") if avg_col else np.nan,
        "ghost_appearances_2526": pd.to_numeric(raw[appearances_col], errors="coerce") if appearances_col else np.nan,
        "ghost_source_fantasy_points_2526": pd.to_numeric(raw[fantasy_col], errors="coerce") if fantasy_col else np.nan,
    }).drop_duplicates("historical_fantrax_player_id", keep="last")

    out = out.merge(ghost, on="historical_fantrax_player_id", how="left")
    out["ghost_points_2526"] = out["ghost_points_2526_authoritative"].combine_first(out.get("ghost_points_2526"))
    calculated_ppg = out["ghost_points_2526_authoritative"] / out["ghost_appearances_2526"].replace(0, np.nan)
    out["ghost_ppg_2526"] = (
        out["ghost_ppg_2526_authoritative"]
        .combine_first(calculated_ppg)
        .combine_first(out.get("ghost_ppg_2526"))
    )
    out["ghost_fp90_2526"] = out["ghost_points_2526"] / out["minutes_2526"].replace(0, np.nan) * 90
    fantasy_denominator = out["ghost_source_fantasy_points_2526"].combine_first(out["fantasy_points_2526"])
    out["ghost_share_pct_2526"] = out["ghost_points_2526"] / fantasy_denominator.replace(0, np.nan) * 100
    return out


def attach_team_context(players: pd.DataFrame, team_strength: pd.DataFrame, fixtures: pd.DataFrame) -> pd.DataFrame:
    ts_team = choose_column(team_strength, ["team_code", "team_short_name", "team_name", "team"], required=True)
    ts = team_strength.copy()
    ts["team_2627"] = ts[ts_team].map(normalize_team)

    attack_col = choose_column(ts, ["attack_rating", "team_attack_rating", "attack_strength", "attack_index"])
    defense_col = choose_column(ts, ["defense_rating", "team_defense_rating", "defense_strength", "defense_index"])
    overall_col = choose_column(ts, ["overall_team_rating", "overall_rating", "team_strength_rating", "team_strength", "strength_rating"])

    team_context = pd.DataFrame({"team_2627": ts["team_2627"]})
    team_context["team_attack_rating"] = pd.to_numeric(ts[attack_col], errors="coerce") if attack_col else np.nan
    team_context["team_defense_rating"] = pd.to_numeric(ts[defense_col], errors="coerce") if defense_col else np.nan
    team_context["team_strength_rating"] = pd.to_numeric(ts[overall_col], errors="coerce") if overall_col else np.nan
    team_context = team_context.drop_duplicates("team_2627", keep="last")

    fx_team = choose_column(fixtures, ["team_code", "team_name", "team", "perspective_team"], required=True)
    ease_col = choose_column(fixtures, ["overall_fixture_ease", "fixture_ease", "attacker_fixture_ease"])
    diff_col = choose_column(fixtures, ["fixture_difficulty"])
    order_col = choose_column(fixtures, ["game_week", "game_week_estimate", "fixture_order", "match_date"])

    fx = fixtures.copy()
    fx["team_2627"] = fx[fx_team].map(normalize_team)
    fx["fixture_order_value"] = (
        pd.to_numeric(fx[order_col], errors="coerce") if order_col else np.arange(len(fx))
    )
    if ease_col:
        fx["fixture_ease_value"] = pd.to_numeric(fx[ease_col], errors="coerce")
    elif diff_col:
        fx["fixture_ease_value"] = 100 - pd.to_numeric(fx[diff_col], errors="coerce")
    else:
        fx["fixture_ease_value"] = np.nan

    fx = fx.sort_values(["team_2627", "fixture_order_value"])
    fixture_context = fx.groupby("team_2627", as_index=False).agg(
        fixture_ease_next_3=("fixture_ease_value", lambda x: x.head(3).mean()),
        fixture_ease_next_5=("fixture_ease_value", lambda x: x.head(5).mean()),
        fixture_ease_next_10=("fixture_ease_value", lambda x: x.head(10).mean()),
    )

    return players.merge(team_context, on="team_2627", how="left").merge(
        fixture_context, on="team_2627", how="left"
    )


def build_minutes_outlook(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()

    season_share = (out["minutes_2526"] / (38 * 90)).clip(0, 1)
    recent_share = (out["recent_minutes_6"] / (6 * 90)).clip(0, 1)
    start_rate = out["start_rate_2526"].clip(0, 1)
    recent_start = out["recent_start_rate_6"].clip(0, 1)

    known_history = out["minutes_2526"].fillna(0) > 0
    same_team = out["team_2526"].fillna("").eq(out["team_2627"].fillna(""))

    minutes_score = (
        0.40 * season_share.fillna(0)
        + 0.30 * recent_share.fillna(0)
        + 0.20 * start_rate.fillna(0)
        + 0.10 * recent_start.fillna(0)
    ) * 100

    # Small uncertainty penalty for a detected transfer.
    minutes_score = minutes_score - np.where(known_history & ~same_team, 8, 0)
    out["projected_minutes_share"] = minutes_score.clip(0, 100).round(1)

    out["minutes_outlook"] = pd.cut(
        out["projected_minutes_share"],
        bins=[-1, 20, 45, 68, 84, 101],
        labels=["Bench / Unknown", "Rotation Risk", "Likely Rotation", "Likely Starter", "Locked Starter"],
    ).astype(str)

    out.loc[~known_history, "minutes_outlook"] = "Unknown / New Arrival"
    out["minutes_confidence"] = np.select(
        [
            out["minutes_2526"].fillna(0) >= 2200,
            out["minutes_2526"].fillna(0) >= 1200,
            out["minutes_2526"].fillna(0) > 0,
        ],
        [90, 75, 55],
        default=25,
    )
    out.loc[known_history & ~same_team, "minutes_confidence"] -= 15
    out["minutes_confidence"] = out["minutes_confidence"].clip(0, 100)
    out["team_changed"] = known_history & ~same_team
    return out


def build_rankings(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()

    production = (
        0.60 * percentile(out["fantasy_ppg_2526"])
        + 0.40 * percentile(out["fantasy_fp90_2526"])
    )
    ghost = percentile(out["ghost_ppg_2526"])
    attacking = percentile(out["xgi90_2526"])
    minutes = out["projected_minutes_share"].fillna(0)
    team = (
        0.65 * percentile(out["team_attack_rating"])
        + 0.35 * percentile(out["team_strength_rating"])
    )
    fixtures = percentile(out["fixture_ease_next_5"])

    out["production_score"] = production.round(1)
    out["ghost_score"] = ghost.round(1)
    out["attacking_score"] = attacking.round(1)
    out["minutes_score"] = minutes.round(1)
    out["team_context_score"] = team.round(1)
    out["fixture_score"] = fixtures.round(1)

    out["draft_score"] = (
        0.30 * production
        + 0.20 * minutes
        + 0.15 * ghost
        + 0.15 * attacking
        + 0.10 * team
        + 0.10 * fixtures
    ).round(2)

    out["data_confidence"] = (
        0.45 * out["minutes_confidence"].fillna(0)
        + 25 * out["fantasy_points_2526"].notna().astype(int)
        + 20 * out["understat_player_id"].replace("", np.nan).notna().astype(int)
        + 10 * out["team_strength_rating"].notna().astype(int)
    ).clip(0, 100).round(1)

    out = out.sort_values(
        ["draft_score", "data_confidence", "fantasy_ppg_2526"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    out["overall_rank"] = np.arange(1, len(out) + 1)

    out["tier"] = pd.cut(
        out["overall_rank"],
        bins=[0, 12, 36, 72, 120, 180, 300, np.inf],
        labels=["Tier 1", "Tier 2", "Tier 3", "Tier 4", "Tier 5", "Tier 6", "Deep"],
    ).astype(str)

    adp_reference = out["fantrax_adp_rank"].combine_first(out["fantrax_adp"])
    out["value_vs_adp"] = adp_reference - out["overall_rank"]
    out["adp_status"] = np.select(
        [
            adp_reference.isna(),
            out["value_vs_adp"] >= 20,
            out["value_vs_adp"] >= 8,
            out["value_vs_adp"] <= -20,
            out["value_vs_adp"] <= -8,
        ],
        ["ADP unavailable", "Strong value", "Value", "Major reach", "Reach"],
        default="Near market",
    )
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fantrax-pool", type=Path)
    parser.add_argument("--master", type=Path)
    parser.add_argument("--bridge", type=Path)
    parser.add_argument("--team-strength", type=Path)
    parser.add_argument("--fixtures", type=Path)
    parser.add_argument("--fantrax-export", type=Path)
    parser.add_argument("--ghost-leaders", type=Path)
    args = parser.parse_args()

    fantrax_path = args.fantrax_pool or discover([
        "processed_data/fantrax_api/api_player_lookup.csv",
        "data/**/api_player_lookup.csv",
        "**/api_player_lookup.csv",
    ])
    fantrax_export_path = args.fantrax_export or discover([
        "data/imports/draft/Fantrax-Players*.csv",
        "data/raw/draft/Fantrax-Players*.csv",
        "Fantrax-Players*.csv",
    ])
    master_path = args.master or discover([
        "data/**/master_player_weekly_2526.csv",
        "**/master_player_weekly_2526.csv",
    ])
    bridge_path = args.bridge or discover([
        "data/reference/api_to_master_player_id_bridge_2526.csv",
        "**/api_to_master_player_id_bridge_2526.csv",
    ])
    ghost_path = args.ghost_leaders or discover([
        "data/seasons/2526/analytics_views/ghost_points_player_leaders.csv",
        "data/analytics_views/ghost_points_player_leaders.csv",
        "**/ghost_points_player_leaders.csv",
    ])
    team_strength_path = args.team_strength or discover([
        "data/analytics/draft/team_strength_2526.csv",
        "**/team_strength_2526.csv",
    ])
    fixtures_path = args.fixtures or discover([
        "data/analytics/draft/fixture_difficulty_2627.csv",
        "**/fixture_difficulty_2627.csv",
    ])

    required = {
        "2026/27 Fantrax player pool": fantrax_path,
        "2025/26 master weekly": master_path,
        "team strength": team_strength_path,
        "2026/27 fixture difficulty": fixtures_path,
    }
    missing = [f"{label}: {path}" for label, path in required.items() if path is None or not Path(path).exists()]
    if missing:
        raise FileNotFoundError("Missing required inputs:\n  - " + "\n  - ".join(missing))

    print(f"Fantrax target pool: {fantrax_path}")
    print(f"Fantrax preseason export: {fantrax_export_path or 'not found; API pool only'}")
    print(f"Historical master: {master_path}")
    print(f"Historical bridge: {bridge_path or 'not found; direct IDs will be used'}")
    print(f"Ghost leaders: {ghost_path or 'not found; master columns only'}")
    print(f"Team strength: {team_strength_path}")
    print(f"Fixtures: {fixtures_path}")

    current = load_current_fantrax(fantrax_export_path or fantrax_path)
    current = attach_bridge(current, bridge_path)
    history = build_historical_player_summary(read_csv(master_path))

    current_ids = set(current["historical_fantrax_player_id"].dropna())
    historical_ids = set(history["fantrax_player_id"].dropna())
    print(f"Normalized current IDs: {len(current_ids):,}")
    print(f"Normalized historical IDs: {len(historical_ids):,}")
    print(f"Direct historical ID overlap: {len(current_ids & historical_ids):,}")

    pool = current.merge(
        history,
        left_on="historical_fantrax_player_id",
        right_on="fantrax_player_id",
        how="left",
        suffixes=("", "_historical"),
    )
    pool = pool.drop(columns=["fantrax_player_id_historical"], errors="ignore")
    pool = attach_ghost_points(pool, ghost_path)
    pool = attach_team_context(pool, read_csv(team_strength_path), read_csv(fixtures_path))
    pool = build_minutes_outlook(pool)
    rankings = build_rankings(pool)

    out_dir = PROJECT_ROOT / "data" / "models" / "draft_2627"
    out_dir.mkdir(parents=True, exist_ok=True)
    quality_dir = PROJECT_ROOT / "data" / "quality" / "draft_2627"
    quality_dir.mkdir(parents=True, exist_ok=True)

    pool_path = out_dir / "draft_player_pool_2627.csv"
    ranking_path = out_dir / "draft_rankings_2627.csv"
    quality_path = quality_dir / "draft_data_quality_2627.csv"

    pool.to_csv(pool_path, index=False, encoding="utf-8-sig")
    rankings.to_csv(ranking_path, index=False, encoding="utf-8-sig")

    quality = rankings[
        rankings["historical_name"].isna()
        | rankings["team_strength_rating"].isna()
        | rankings["fixture_ease_next_5"].isna()
        | rankings["data_confidence"].lt(60)
    ].copy()
    quality.to_csv(quality_path, index=False, encoding="utf-8-sig")

    print("\nDraft Tool v1.2 data build complete.")
    print(f"Current Fantrax players: {len(rankings):,}")
    print(f"With historical Fantrax data: {rankings['historical_name'].notna().sum():,}")
    print(f"With Understat identity: {rankings['understat_player_id'].replace('', np.nan).notna().sum():,}")
    print(f"With team context: {rankings['team_strength_rating'].notna().sum():,}")
    print(f"With fixture context: {rankings['fixture_ease_next_5'].notna().sum():,}")
    print(f"With ghost-point history: {rankings['ghost_points_2526'].notna().sum():,}")
    print(f"With ADP: {rankings['fantrax_adp'].notna().sum():,}")
    print(f"With Fantrax projections: {rankings['fantrax_projected_points'].notna().sum():,}")
    print(f"\nSaved: {pool_path}")
    print(f"Saved: {ranking_path}")
    print(f"Saved: {quality_path}")


if __name__ == "__main__":
    main()
