#!/usr/bin/env python3
r"""
build_efficiency_ghost_awards_views.py

Purpose
-------
Build the "skill analytics" layer for the Fantrax app:

1. Lineup efficiency
   Actual starter points vs best legal lineup from that manager's roster that GW.

2. Ghost points
   Fantrax points excluding goals, assists, clean sheets, and goals-against penalties.
   Goals-against is -2 for defenders/goalkeepers for each goal conceded after the first.

3. Roster adds
   Player appears on a manager's roster this GW but was not on that manager's roster last GW.
   This is a roster-add proxy, not guaranteed waiver-only unless transaction data is added later.

4. Dynamic manager award leaderboards
   One long CSV that the app can filter by:
      scope = season / weekly
      award_name = Goals, Assists, Clean Sheets, Efficiency, Ghost Points, etc.

Inputs:
    C:\Users\Tommy\fantrax_data\data\processed\manager_player_weekly_2526.csv
    C:\Users\Tommy\fantrax_data\data\processed\manager_week_summary_2526.csv
    C:\Users\Tommy\fantrax_data\data\processed\manager_season_summary_2526.csv
    C:\Users\Tommy\fantrax_data\data\analytics_views\lineup_changes.csv

Outputs:
    C:\Users\Tommy\fantrax_data\data\analytics_views\manager_efficiency_weekly.csv
    C:\Users\Tommy\fantrax_data\data\analytics_views\manager_efficiency_season.csv
    C:\Users\Tommy\fantrax_data\data\analytics_views\lineup_decision_details.csv
    C:\Users\Tommy\fantrax_data\data\analytics_views\ghost_points_player_weekly.csv
    C:\Users\Tommy\fantrax_data\data\analytics_views\ghost_points_player_leaders.csv
    C:\Users\Tommy\fantrax_data\data\analytics_views\ghost_points_manager_weekly.csv
    C:\Users\Tommy\fantrax_data\data\analytics_views\ghost_points_manager_season.csv
    C:\Users\Tommy\fantrax_data\data\analytics_views\position_points_manager_weekly.csv
    C:\Users\Tommy\fantrax_data\data\analytics_views\position_points_manager_season.csv
    C:\Users\Tommy\fantrax_data\data\analytics_views\roster_adds_weekly.csv
    C:\Users\Tommy\fantrax_data\data\analytics_views\roster_adds_leaders.csv
    C:\Users\Tommy\fantrax_data\data\analytics_views\manager_awards_dynamic.csv
    C:\Users\Tommy\fantrax_data\data\analytics_views\manager_profile_summary.csv
    C:\Users\Tommy\fantrax_data\data\analytics_views\efficiency_ghost_awards_report.txt

Run:
    python C:\Users\Tommy\fantrax_data\scripts\build_efficiency_ghost_awards_views.py
"""

from __future__ import annotations

import sys

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import math
import re
import pandas as pd


# =============================================================================
# CONFIG
# =============================================================================

# Portable project configuration
_PROJECT_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT_BOOTSTRAP))
from config.project_paths import PROJECT_ROOT
SEASON_ID = "2526"

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
ANALYTICS_DIR = PROJECT_ROOT / "data" / "analytics_views"

MANAGER_PLAYER_FILE = PROCESSED_DIR / f"manager_player_weekly_{SEASON_ID}.csv"
MANAGER_WEEK_FILE = PROCESSED_DIR / f"manager_week_summary_{SEASON_ID}.csv"
MANAGER_SEASON_FILE = PROCESSED_DIR / f"manager_season_summary_{SEASON_ID}.csv"
LINEUP_CHANGES_FILE = ANALYTICS_DIR / "lineup_changes.csv"

OUT_EFF_WEEKLY = ANALYTICS_DIR / "manager_efficiency_weekly.csv"
OUT_EFF_SEASON = ANALYTICS_DIR / "manager_efficiency_season.csv"
OUT_DECISIONS = ANALYTICS_DIR / "lineup_decision_details.csv"

OUT_GHOST_PLAYER_WEEKLY = ANALYTICS_DIR / "ghost_points_player_weekly.csv"
OUT_GHOST_PLAYER_LEADERS = ANALYTICS_DIR / "ghost_points_player_leaders.csv"
OUT_GHOST_MANAGER_WEEKLY = ANALYTICS_DIR / "ghost_points_manager_weekly.csv"
OUT_GHOST_MANAGER_SEASON = ANALYTICS_DIR / "ghost_points_manager_season.csv"

OUT_POSITION_WEEKLY = ANALYTICS_DIR / "position_points_manager_weekly.csv"
OUT_POSITION_SEASON = ANALYTICS_DIR / "position_points_manager_season.csv"

OUT_ROSTER_ADDS_WEEKLY = ANALYTICS_DIR / "roster_adds_weekly.csv"
OUT_ROSTER_ADDS_LEADERS = ANALYTICS_DIR / "roster_adds_leaders.csv"

OUT_MANAGER_AWARDS = ANALYTICS_DIR / "manager_awards_dynamic.csv"
OUT_MANAGER_PROFILE = ANALYTICS_DIR / "manager_profile_summary.csv"
OUT_REPORT = ANALYTICS_DIR / "efficiency_ghost_awards_report.txt"


# Confirmed from Fantrax league setup screenshot.
TOTAL_ACTIVE_SLOTS = 11
MIN_ACTIVE = {"G": 1, "D": 3, "M": 2, "F": 1}
MAX_ACTIVE = {"G": 1, "D": 5, "M": 5, "F": 3}

# Confirmed league event scoring.
GOAL_POINTS_BASE = {"G": 12.0, "D": 10.0, "M": 9.0, "F": 9.0}
GOAL_POINTS_THIRD_PLUS = {"M": 12.0, "F": 12.0}
ASSIST_POINTS = {"G": 6.0, "D": 7.0, "M": 6.0, "F": 6.0}
CLEAN_SHEET_POINTS = {"G": 6.0, "D": 6.0, "M": 1.0, "F": 0.0}

# Confirmed league goals-against scoring:
# Goalkeepers and defenders lose 2 points for every goal conceded after the first.
# Example: GA=0 -> 0, GA=1 -> 0, GA=2 -> -2, GA=3 -> -4.
GOALS_AGAINST_AFTER_FIRST_POINTS = {"G": -2.0, "D": -2.0, "M": 0.0, "F": 0.0}


# =============================================================================
# HELPERS
# =============================================================================

def read_csv(path: Path, required: bool = True) -> pd.DataFrame:
    if not path.exists():
        if required:
            raise FileNotFoundError(f"Missing required file: {path}")
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8-sig")


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"Saved: {path} rows={len(df):,}")
    if len(df):
        print(df.head(5).to_string(index=False))
    print()


def clean_display_name(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value)
    text = text.replace("â€™", "’")
    for bad in ["🤡", "ðŸ¤¡"]:
        text = text.replace(bad, "")
    return " ".join(text.split()).strip()


def to_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().isin(["true", "1", "yes", "y"])


def num(df: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in df.columns:
        return pd.Series([default] * len(df), index=df.index, dtype="float64")
    return pd.to_numeric(df[col], errors="coerce").fillna(default)


def first_existing_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for c in candidates:
        if c in df.columns:
            return c
    return None


def normalize_position(value: object) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip().upper()

    if "," in text:
        text = text.split(",")[0].strip()
    if "/" in text:
        text = text.split("/")[0].strip()

    aliases = {
        "GK": "G",
        "GOALKEEPER": "G",
        "DEF": "D",
        "DEFENDER": "D",
        "MID": "M",
        "MIDFIELDER": "M",
        "FWD": "F",
        "FORWARD": "F",
        "ST": "F",
    }
    text = aliases.get(text, text)
    return text if text in {"G", "D", "M", "F"} else ""


def parse_eligible_positions(value: object, fallback: str = "") -> tuple[str, ...]:
    if pd.isna(value):
        value = ""

    text = str(value).upper().strip()
    positions: list[str] = []

    for raw in re.split(r"[,/|; ]+", text):
        p = normalize_position(raw)
        if p and p not in positions:
            positions.append(p)

    if not positions:
        p = normalize_position(fallback)
        if p:
            positions.append(p)

    return tuple(positions)


def safe_round(value: object, places: int = 3) -> float:
    try:
        if pd.isna(value):
            return 0.0
        return round(float(value), places)
    except Exception:
        return 0.0


def goal_component(position: str, goals: float) -> float:
    position = normalize_position(position)
    goals = float(goals or 0)
    if goals <= 0:
        return 0.0

    if position in GOAL_POINTS_THIRD_PLUS:
        first_two = min(goals, 2)
        extra = max(goals - 2, 0)
        return first_two * GOAL_POINTS_BASE.get(position, 0.0) + extra * GOAL_POINTS_THIRD_PLUS[position]

    return goals * GOAL_POINTS_BASE.get(position, 0.0)


def clean_team_cols(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ["api_team_name", "team_name", "opponent_team_name", "manager", "display_player_name", "player_name"]:
        if col in out.columns:
            out[col] = out[col].map(clean_display_name)
    return out


# =============================================================================
# PREP
# =============================================================================

def prepare_manager_player() -> pd.DataFrame:
    df = read_csv(MANAGER_PLAYER_FILE)

    df = clean_team_cols(df)

    if "fantrax_gw" in df.columns:
        df["fantrax_gw"] = pd.to_numeric(df["fantrax_gw"], errors="coerce").astype("Int64")

    df["fantasy_points"] = num(df, "mgr_fantasy_points")
    df["actual_started"] = to_bool(df["is_started_api"]) if "is_started_api" in df.columns else False
    df["is_rostered"] = to_bool(df["is_rostered_api"]) if "is_rostered_api" in df.columns else df.get("manager", pd.Series(False, index=df.index)).notna()

    name_col = first_existing_col(df, ["mgr_player", "avail_player", "fantrax_player_name"])
    df["display_player_name"] = df[name_col].fillna("").astype(str) if name_col else ""

    if "api_team_name" not in df.columns:
        df["api_team_name"] = df["manager"] if "manager" in df.columns else ""

    # Position player was actually scored/played as.
    actual_pos_col = first_existing_col(df, ["mgr_pos", "api_position", "position", "avail_position"])
    if actual_pos_col:
        df["scored_position"] = df[actual_pos_col].map(normalize_position)
    else:
        df["scored_position"] = ""

    # Eligible positions for lineup optimization.
    elig_col = first_existing_col(df, ["mgr_eligible", "api_eligible_pos", "avail_position", "eligible_pos"])
    df["eligible_positions_raw"] = df[elig_col].fillna("").astype(str) if elig_col else df["scored_position"]

    # Default position fallback.
    default_pos_col = first_existing_col(df, ["api_position", "position", "avail_position", "mgr_pos"])
    df["default_position"] = df[default_pos_col].map(normalize_position) if default_pos_col else df["scored_position"]
    df.loc[df["default_position"].eq(""), "default_position"] = df["eligible_positions_raw"].map(
        lambda x: parse_eligible_positions(x, "")[0] if parse_eligible_positions(x, "") else ""
    )

    df["eligible_positions_tuple"] = [
        parse_eligible_positions(raw, fallback)
        for raw, fallback in zip(df["eligible_positions_raw"], df["default_position"])
    ]
    df["eligible_positions"] = df["eligible_positions_tuple"].map(lambda xs: ",".join(xs))

    return df


# =============================================================================
# EFFICIENCY ENGINE
# =============================================================================

@dataclass(frozen=True)
class PlayerOption:
    idx: int
    player_id: str
    player_name: str
    points: float
    eligible: tuple[str, ...]
    actual_started: bool


def lineup_counts_are_legal(g: int, d: int, m: int, f: int, used: int) -> bool:
    if used != TOTAL_ACTIVE_SLOTS:
        return False
    counts = {"G": g, "D": d, "M": m, "F": f}
    for pos in ("G", "D", "M", "F"):
        if counts[pos] < MIN_ACTIVE[pos] or counts[pos] > MAX_ACTIVE[pos]:
            return False
    return True


def counts_can_still_be_legal(g: int, d: int, m: int, f: int, used: int, remaining: int) -> bool:
    counts = {"G": g, "D": d, "M": m, "F": f}

    if used > TOTAL_ACTIVE_SLOTS:
        return False
    if used + remaining < TOTAL_ACTIVE_SLOTS:
        return False

    for pos in ("G", "D", "M", "F"):
        if counts[pos] > MAX_ACTIVE[pos]:
            return False

    min_needed = sum(max(MIN_ACTIVE[pos] - counts[pos], 0) for pos in ("G", "D", "M", "F"))
    open_slots = TOTAL_ACTIVE_SLOTS - used
    return min_needed <= open_slots


def optimize_lineup(players: list[PlayerOption]) -> tuple[float, list[int], dict[int, str], bool]:
    """
    Maximize exported Fantrax points using real lineup constraints:
    11 starters, G 1-1, D 3-5, M 2-5, F 1-3.
    """

    players = [p for p in players if p.eligible]

    if not players:
        return 0.0, [], {}, False

    if len(players) < TOTAL_ACTIVE_SLOTS:
        # Not enough rosterable players. Use best possible fallback.
        top = sorted(players, key=lambda p: p.points, reverse=True)
        return sum(p.points for p in top), [p.idx for p in top], {p.idx: p.eligible[0] for p in top}, False

    @lru_cache(maxsize=None)
    def dp(i: int, used: int, g: int, d: int, m: int, f: int) -> tuple[float, tuple[tuple[int, str], ...]]:
        remaining = len(players) - i

        if used == TOTAL_ACTIVE_SLOTS:
            if not lineup_counts_are_legal(g, d, m, f, used):
                return (-10**9, tuple())
            return 0.0, tuple()

        if i >= len(players):
            return (-10**9, tuple())

        if not counts_can_still_be_legal(g, d, m, f, used, remaining):
            return (-10**9, tuple())

        player = players[i]

        best_score, best_assign = dp(i + 1, used, g, d, m, f)

        for pos in player.eligible:
            ng, nd, nm, nf = g, d, m, f
            if pos == "G":
                ng += 1
            elif pos == "D":
                nd += 1
            elif pos == "M":
                nm += 1
            elif pos == "F":
                nf += 1
            else:
                continue

            new_counts = {"G": ng, "D": nd, "M": nm, "F": nf}
            if new_counts[pos] > MAX_ACTIVE[pos]:
                continue

            score_next, assign_next = dp(i + 1, used + 1, ng, nd, nm, nf)
            score = player.points + score_next

            if score > best_score:
                best_score = score
                best_assign = ((player.idx, pos),) + assign_next

        return best_score, best_assign

    score, assignments = dp(0, 0, 0, 0, 0, 0)

    if score < -10**8:
        top = sorted(players, key=lambda p: p.points, reverse=True)[:TOTAL_ACTIVE_SLOTS]
        return sum(p.points for p in top), [p.idx for p in top], {p.idx: p.eligible[0] for p in top}, False

    selected_ids = [idx for idx, _pos in assignments]
    assigned_positions = {idx: pos for idx, pos in assignments}
    return float(score), selected_ids, assigned_positions, True


def build_efficiency_views(mp: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rostered = mp[mp["is_rostered"]].copy()

    status_col = first_existing_col(rostered, ["api_status", "status", "mgr_status"])
    if status_col:
        status = rostered[status_col].fillna("").astype(str).str.upper()
        pool = rostered[~status.str.contains("INJURED_RESERVE|INJURED RESERVE|\\bIR\\b", regex=True)].copy()
    else:
        pool = rostered.copy()

    weekly_rows = []
    decision_rows = []

    group_cols = ["fantrax_gw", "api_team_id", "api_team_name"]
    for (gw, team_id, team_name), g in pool.groupby(group_cols, dropna=False):
        g = g.copy()

        players: list[PlayerOption] = []
        for idx, row in g.iterrows():
            player_id = str(row.get("fantrax_player_id", "")).strip()
            if not player_id:
                continue

            players.append(
                PlayerOption(
                    idx=int(idx),
                    player_id=player_id,
                    player_name=str(row.get("display_player_name", "")),
                    points=float(row.get("fantasy_points", 0.0)),
                    eligible=tuple(row.get("eligible_positions_tuple", tuple())),
                    actual_started=bool(row.get("actual_started")),
                )
            )

        actual_starters = g[g["actual_started"]]
        actual_points = float(actual_starters["fantasy_points"].sum())
        actual_starter_ids = set(actual_starters.index.astype(int).tolist())

        optimal_points, optimal_idx, assigned_positions, legal_solution = optimize_lineup(players)
        optimal_ids = set(optimal_idx)

        missed_points = max(optimal_points - actual_points, 0.0)
        efficiency_pct = actual_points / optimal_points * 100 if optimal_points > 0 else 0.0

        bench_should_start = optimal_ids - actual_starter_ids
        starters_to_drop = actual_starter_ids - optimal_ids

        weekly_rows.append({
            "fantrax_gw": int(gw) if not pd.isna(gw) else None,
            "api_team_id": team_id,
            "api_team_name": clean_display_name(team_name),
            "actual_starter_points": safe_round(actual_points, 2),
            "optimal_lineup_points": safe_round(optimal_points, 2),
            "missed_points": safe_round(missed_points, 2),
            "efficiency_pct": safe_round(efficiency_pct, 2),
            "actual_starter_count": len(actual_starters),
            "optimization_pool_players": len(g),
            "optimal_selected_count": len(optimal_ids),
            "legal_solution_found": legal_solution,
            "bench_players_should_have_started": len(bench_should_start),
            "starters_who_should_have_sat": len(starters_to_drop),
        })

        relevant_ids = actual_starter_ids | optimal_ids
        for idx in relevant_ids:
            row = g.loc[idx]
            was_started = idx in actual_starter_ids
            in_optimal = idx in optimal_ids

            decision = (
                "correct_start" if was_started and in_optimal else
                "missed_bench_start" if (not was_started and in_optimal) else
                "should_have_sat" if was_started and not in_optimal else
                "not_relevant"
            )

            decision_rows.append({
                "fantrax_gw": int(gw) if not pd.isna(gw) else None,
                "api_team_id": team_id,
                "api_team_name": clean_display_name(team_name),
                "fantrax_player_id": row.get("fantrax_player_id"),
                "player_name": clean_display_name(row.get("display_player_name")),
                "eligible_positions": row.get("eligible_positions"),
                "actual_started": was_started,
                "optimal_selected": in_optimal,
                "optimal_assigned_position": assigned_positions.get(idx, ""),
                "actual_scored_position": row.get("scored_position"),
                "fantasy_points": safe_round(row.get("fantasy_points", 0.0), 2),
                "decision_type": decision,
            })

    weekly = pd.DataFrame(weekly_rows)
    decisions = pd.DataFrame(decision_rows)

    if weekly.empty:
        return weekly, pd.DataFrame(), decisions

    season = (
        weekly
        .groupby(["api_team_id", "api_team_name"], dropna=False)
        .agg(
            weeks=("fantrax_gw", "nunique"),
            actual_starter_points=("actual_starter_points", "sum"),
            optimal_lineup_points=("optimal_lineup_points", "sum"),
            missed_points=("missed_points", "sum"),
            avg_efficiency_pct=("efficiency_pct", "mean"),
            best_efficiency_pct=("efficiency_pct", "max"),
            worst_efficiency_pct=("efficiency_pct", "min"),
            total_missed_bench_starts=("bench_players_should_have_started", "sum"),
            total_should_have_sat=("starters_who_should_have_sat", "sum"),
            legal_solution_weeks=("legal_solution_found", "sum"),
        )
        .reset_index()
    )

    season["season_efficiency_pct"] = (
        season["actual_starter_points"] / season["optimal_lineup_points"]
    ).replace([math.inf, -math.inf], 0).fillna(0) * 100

    season = season.sort_values(["season_efficiency_pct", "missed_points"], ascending=[False, True])
    season["efficiency_rank"] = range(1, len(season) + 1)

    for c in [
        "actual_starter_points", "optimal_lineup_points", "missed_points",
        "avg_efficiency_pct", "best_efficiency_pct", "worst_efficiency_pct",
        "season_efficiency_pct",
    ]:
        season[c] = season[c].map(lambda x: safe_round(x, 2))

    weekly = weekly.sort_values(["fantrax_gw", "efficiency_pct"], ascending=[True, False])
    decisions = decisions.sort_values(
        ["fantrax_gw", "api_team_name", "decision_type", "fantasy_points"],
        ascending=[True, True, True, False],
    )

    return weekly, season, decisions


# =============================================================================
# GHOST POINTS ENGINE
# =============================================================================

def build_ghost_views(mp: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    df = mp.copy()

    df["goals"] = num(df, "mgr_g")
    df["assists"] = num(df, "mgr_at")
    df["clean_sheets"] = num(df, "mgr_cs")
    df["goals_against"] = num(df, "mgr_ga") + num(df, "mgr_gao")

    df["ghost_position"] = df["scored_position"]
    df.loc[df["ghost_position"].eq(""), "ghost_position"] = df["default_position"]

    df["goal_points_component"] = [
        goal_component(pos, goals)
        for pos, goals in zip(df["ghost_position"], df["goals"])
    ]
    df["assist_points_component"] = [
        ASSIST_POINTS.get(normalize_position(pos), 0.0) * assists
        for pos, assists in zip(df["ghost_position"], df["assists"])
    ]
    df["clean_sheet_points_component"] = [
        CLEAN_SHEET_POINTS.get(normalize_position(pos), 0.0) * cs
        for pos, cs in zip(df["ghost_position"], df["clean_sheets"])
    ]
    df["goals_against_points_component"] = [
        GOALS_AGAINST_AFTER_FIRST_POINTS.get(normalize_position(pos), 0.0) * max(float(ga or 0) - 1.0, 0.0)
        for pos, ga in zip(df["ghost_position"], df["goals_against"])
    ]

    df["major_event_points"] = (
        df["goal_points_component"] +
        df["assist_points_component"] +
        df["clean_sheet_points_component"] +
        df["goals_against_points_component"]
    )
    df["ghost_points"] = df["fantasy_points"] - df["major_event_points"]

    keep_cols = [
        "fantrax_gw", "api_team_id", "api_team_name", "manager",
        "fantrax_player_id", "display_player_name", "ghost_position",
        "eligible_positions", "actual_started", "is_rostered",
        "fantasy_points", "ghost_points", "major_event_points",
        "goal_points_component", "assist_points_component",
        "clean_sheet_points_component", "goals_against_points_component",
        "goals", "assists", "clean_sheets", "goals_against",
        "mgr_min", "mgr_kp", "mgr_tkw", "mgr_int", "mgr_clr", "mgr_aer", "mgr_sot",
    ]
    keep_cols = [c for c in keep_cols if c in df.columns]
    weekly = clean_team_cols(df[keep_cols].copy())

    for c in [
        "fantasy_points", "ghost_points", "major_event_points",
        "goal_points_component", "assist_points_component",
        "clean_sheet_points_component", "goals_against_points_component",
    ]:
        if c in weekly.columns:
            weekly[c] = pd.to_numeric(weekly[c], errors="coerce").fillna(0).map(lambda x: safe_round(x, 3))

    rostered = weekly[weekly["is_rostered"]].copy()

    # Manager-level ghost points should match the award/profile comparison to
    # starter points, so use ACTIVE starters only. Player leaders still use all
    # rostered appearances below.
    starters = rostered[rostered["actual_started"]].copy()

    ghost_manager_weekly = (
        starters
        .groupby(["fantrax_gw", "api_team_id", "api_team_name"], dropna=False)
        .agg(
            rostered_player_weeks=("fantrax_player_id", "count"),
            starter_player_weeks=("actual_started", "sum"),
            fantasy_points=("fantasy_points", "sum"),
            ghost_points=("ghost_points", "sum"),
            major_event_points=("major_event_points", "sum"),
            goals=("goals", "sum"),
            assists=("assists", "sum"),
            clean_sheets=("clean_sheets", "sum"),
        )
        .reset_index()
    )

    ghost_manager_season = (
        ghost_manager_weekly
        .groupby(["api_team_id", "api_team_name"], dropna=False)
        .agg(
            weeks=("fantrax_gw", "nunique"),
            rostered_player_weeks=("rostered_player_weeks", "sum"),
            starter_player_weeks=("starter_player_weeks", "sum"),
            fantasy_points=("fantasy_points", "sum"),
            ghost_points=("ghost_points", "sum"),
            major_event_points=("major_event_points", "sum"),
            goals=("goals", "sum"),
            assists=("assists", "sum"),
            clean_sheets=("clean_sheets", "sum"),
        )
        .reset_index()
    )
    ghost_manager_season["ghost_points_share_pct"] = (
        ghost_manager_season["ghost_points"] / ghost_manager_season["fantasy_points"]
    ).replace([math.inf, -math.inf], 0).fillna(0) * 100
    ghost_manager_season = ghost_manager_season.sort_values("ghost_points", ascending=False)
    ghost_manager_season["ghost_points_rank"] = range(1, len(ghost_manager_season) + 1)

    for out in [ghost_manager_weekly, ghost_manager_season]:
        for c in ["fantasy_points", "ghost_points", "major_event_points", "ghost_points_share_pct"]:
            if c in out.columns:
                out[c] = out[c].map(lambda x: safe_round(x, 3))

    player_leaders = (
        rostered
        .groupby(["fantrax_player_id", "display_player_name"], dropna=False)
        .agg(
            appearances=("fantrax_gw", "count"),
            starts=("actual_started", "sum"),
            total_fantasy_points=("fantasy_points", "sum"),
            total_ghost_points=("ghost_points", "sum"),
            avg_ghost_points=("ghost_points", "mean"),
            total_major_event_points=("major_event_points", "sum"),
            total_goals=("goals", "sum"),
            total_assists=("assists", "sum"),
            total_clean_sheets=("clean_sheets", "sum"),
        )
        .reset_index()
    )
    player_leaders = player_leaders.sort_values("total_ghost_points", ascending=False)
    player_leaders["ghost_points_rank"] = range(1, len(player_leaders) + 1)

    for c in ["total_fantasy_points", "total_ghost_points", "avg_ghost_points", "total_major_event_points"]:
        player_leaders[c] = player_leaders[c].map(lambda x: safe_round(x, 3))

    pos_base = rostered.copy()
    pos_base["position_group"] = pos_base["ghost_position"].map(normalize_position)

    position_weekly = (
        pos_base
        .groupby(["fantrax_gw", "api_team_id", "api_team_name", "position_group"], dropna=False)
        .agg(
            player_weeks=("fantrax_player_id", "count"),
            starts=("actual_started", "sum"),
            fantasy_points=("fantasy_points", "sum"),
            ghost_points=("ghost_points", "sum"),
            goals=("goals", "sum"),
            assists=("assists", "sum"),
            clean_sheets=("clean_sheets", "sum"),
        )
        .reset_index()
    )

    position_season = (
        position_weekly
        .groupby(["api_team_id", "api_team_name", "position_group"], dropna=False)
        .agg(
            weeks=("fantrax_gw", "nunique"),
            player_weeks=("player_weeks", "sum"),
            starts=("starts", "sum"),
            fantasy_points=("fantasy_points", "sum"),
            ghost_points=("ghost_points", "sum"),
            goals=("goals", "sum"),
            assists=("assists", "sum"),
            clean_sheets=("clean_sheets", "sum"),
        )
        .reset_index()
    )

    for out in [position_weekly, position_season]:
        for c in ["fantasy_points", "ghost_points"]:
            out[c] = out[c].map(lambda x: safe_round(x, 3))

    return weekly, player_leaders, ghost_manager_weekly, ghost_manager_season, position_weekly, position_season


# =============================================================================
# ROSTER ADDS
# =============================================================================

def build_roster_adds(mp: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rostered = mp[mp["is_rostered"]].copy()
    rostered["fantrax_gw_num"] = pd.to_numeric(rostered["fantrax_gw"], errors="coerce")
    rostered = rostered.dropna(subset=["fantrax_gw_num", "api_team_id", "fantrax_player_id"])

    rows = []

    for team_id, g in rostered.groupby("api_team_id", dropna=False):
        team_name = clean_display_name(g["api_team_name"].dropna().iloc[0]) if g["api_team_name"].notna().any() else str(team_id)

        previous_roster: set[str] | None = None
        for gw, week in g.groupby("fantrax_gw_num"):
            week = week.copy()
            current_roster = set(week["fantrax_player_id"].dropna().astype(str))

            if previous_roster is None:
                added_ids = set()
            else:
                added_ids = current_roster - previous_roster

            for pid in sorted(added_ids):
                player_rows = g[g["fantrax_player_id"].astype(str) == pid].copy()
                after_rows = player_rows[player_rows["fantrax_gw_num"] >= gw].copy()
                first_row = week[week["fantrax_player_id"].astype(str) == pid].iloc[0]

                rows.append({
                    "api_team_id": team_id,
                    "api_team_name": team_name,
                    "fantrax_player_id": pid,
                    "player_name": clean_display_name(first_row.get("display_player_name")),
                    "added_gw": int(gw),
                    "points_in_added_gw": safe_round(first_row.get("fantasy_points", 0), 2),
                    "started_in_added_gw": bool(first_row.get("actual_started")),
                    "weeks_rostered_after_add": int(after_rows["fantrax_gw_num"].nunique()),
                    "starts_after_add": int(after_rows["actual_started"].sum()),
                    "points_after_add": safe_round(after_rows["fantasy_points"].sum(), 2),
                    "avg_points_after_add": safe_round(after_rows["fantasy_points"].mean(), 2) if len(after_rows) else 0,
                })

            previous_roster = current_roster

    weekly = pd.DataFrame(rows)
    if weekly.empty:
        return weekly, pd.DataFrame()

    leaders = (
        weekly
        .groupby(["api_team_id", "api_team_name"], dropna=False)
        .agg(
            roster_adds=("fantrax_player_id", "count"),
            total_points_after_adds=("points_after_add", "sum"),
            avg_points_per_add=("points_after_add", "mean"),
            total_starts_after_adds=("starts_after_add", "sum"),
            best_single_add_points=("points_after_add", "max"),
        )
        .reset_index()
    )
    leaders = leaders.sort_values("total_points_after_adds", ascending=False)
    leaders["roster_add_value_rank"] = range(1, len(leaders) + 1)

    for c in ["total_points_after_adds", "avg_points_per_add", "best_single_add_points"]:
        leaders[c] = leaders[c].map(lambda x: safe_round(x, 2))

    return weekly.sort_values(["added_gw", "points_after_add"], ascending=[True, False]), leaders


# =============================================================================
# DYNAMIC AWARDS
# =============================================================================

def add_award_rows(
    rows: list[dict],
    df: pd.DataFrame,
    scope: str,
    award_name: str,
    value_col: str,
    high_wins: bool = True,
    extra_cols: list[str] | None = None,
    gw_col: str = "fantrax_gw",
    team_id_col: str = "api_team_id",
    team_name_col: str = "api_team_name",
    description: str = "",
) -> None:
    extra_cols = extra_cols or []

    if df.empty or value_col not in df.columns:
        return

    work = df.copy()
    work[value_col] = pd.to_numeric(work[value_col], errors="coerce")

    group_cols = []
    if scope == "weekly" and gw_col in work.columns:
        group_cols = [gw_col]

    if group_cols:
        for group_value, g in work.groupby(group_cols[0], dropna=False):
            g = g.dropna(subset=[value_col]).copy()
            if g.empty:
                continue
            g = g.sort_values(value_col, ascending=not high_wins)
            for rank, (_, row) in enumerate(g.iterrows(), start=1):
                out = {
                    "scope": scope,
                    "fantrax_gw": int(group_value) if not pd.isna(group_value) else None,
                    "award_name": award_name,
                    "rank": rank,
                    "api_team_id": row.get(team_id_col),
                    "api_team_name": clean_display_name(row.get(team_name_col)),
                    "value": safe_round(row.get(value_col), 3),
                    "value_col": value_col,
                    "description": description,
                }
                for c in extra_cols:
                    out[c] = row.get(c)
                rows.append(out)
    else:
        work = work.dropna(subset=[value_col]).copy()
        work = work.sort_values(value_col, ascending=not high_wins)
        for rank, (_, row) in enumerate(work.iterrows(), start=1):
            out = {
                "scope": scope,
                "fantrax_gw": None,
                "award_name": award_name,
                "rank": rank,
                "api_team_id": row.get(team_id_col),
                "api_team_name": clean_display_name(row.get(team_name_col)),
                "value": safe_round(row.get(value_col), 3),
                "value_col": value_col,
                "description": description,
            }
            for c in extra_cols:
                out[c] = row.get(c)
            rows.append(out)


def build_manager_awards(
    manager_week: pd.DataFrame,
    manager_season: pd.DataFrame,
    eff_weekly: pd.DataFrame,
    eff_season: pd.DataFrame,
    ghost_weekly: pd.DataFrame,
    ghost_season: pd.DataFrame,
    roster_add_leaders: pd.DataFrame,
    lineup_changes: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict] = []

    manager_week = clean_team_cols(manager_week)
    manager_season = clean_team_cols(manager_season)

    # Season scoring leaderboards. xG/xA are context columns, not separate awards.
    add_award_rows(
        rows, manager_season, "season", "Goals", "total_starter_goals", True,
        extra_cols=["total_xg", "total_starter_points"],
        description="Total starter goals, with xG as context.",
    )
    add_award_rows(
        rows, manager_season, "season", "Assists", "total_starter_assists_total", True,
        extra_cols=["total_xa", "total_starter_points"],
        description="Total starter assists, with xA as context.",
    )
    add_award_rows(
        rows, manager_season, "season", "Clean Sheets", "total_starter_clean_sheets", True,
        extra_cols=["total_starter_points"],
        description="Total starter clean sheets.",
    )
    add_award_rows(
        rows, manager_season, "season", "Total Starter Points", "total_starter_points", True,
        extra_cols=["avg_starter_points", "best_week_points", "worst_week_points"],
        description="Total points from active starters.",
    )
    add_award_rows(
        rows, manager_season, "season", "Highest Single Week", "best_week_points", True,
        extra_cols=["total_starter_points"],
        description="Best single-week starter score.",
    )

    # Weekly scoring awards.
    add_award_rows(
        rows, manager_week, "weekly", "Goals", "starter_goals", True,
        extra_cols=["starter_xg", "starter_fantasy_points"],
        description="Weekly starter goals, with xG as context.",
    )
    add_award_rows(
        rows, manager_week, "weekly", "Assists", "starter_assists_total", True,
        extra_cols=["starter_xa", "starter_fantasy_points"],
        description="Weekly starter assists, with xA as context.",
    )
    add_award_rows(
        rows, manager_week, "weekly", "Clean Sheets", "starter_clean_sheets", True,
        extra_cols=["starter_fantasy_points"],
        description="Weekly starter clean sheets.",
    )
    add_award_rows(
        rows, manager_week, "weekly", "Highest Score", "starter_fantasy_points", True,
        extra_cols=["starter_goals", "starter_assists_total", "starter_clean_sheets"],
        description="Highest starter fantasy points in a gameweek.",
    )
    add_award_rows(
        rows, manager_week, "weekly", "Jester", "starter_fantasy_points", False,
        extra_cols=["starter_goals", "starter_assists_total", "starter_clean_sheets"],
        description="Lowest starter fantasy points in a gameweek.",
    )

    # Efficiency awards.
    add_award_rows(
        rows, eff_season, "season", "Efficiency", "season_efficiency_pct", True,
        extra_cols=["missed_points", "actual_starter_points", "optimal_lineup_points"],
        description="Actual starter points divided by optimal legal lineup points.",
    )
    add_award_rows(
        rows, eff_season, "season", "Missed Points", "missed_points", False,
        extra_cols=["season_efficiency_pct", "actual_starter_points", "optimal_lineup_points"],
        description="Fewest missed points from lineup decisions. Lower is better.",
    )
    add_award_rows(
        rows, eff_weekly, "weekly", "Efficiency", "efficiency_pct", True,
        extra_cols=["missed_points", "actual_starter_points", "optimal_lineup_points"],
        description="Weekly actual points divided by optimal legal lineup points.",
    )
    add_award_rows(
        rows, eff_weekly, "weekly", "Missed Points", "missed_points", False,
        extra_cols=["efficiency_pct", "actual_starter_points", "optimal_lineup_points"],
        description="Fewest missed points in a gameweek. Lower is better.",
    )

    # Ghost points.
    add_award_rows(
        rows, ghost_season, "season", "Ghost Points", "ghost_points", True,
        extra_cols=["fantasy_points", "major_event_points", "ghost_points_share_pct"],
        description="Total points excluding goals, assists, clean sheets, and GA penalties.",
    )
    add_award_rows(
        rows, ghost_weekly, "weekly", "Ghost Points", "ghost_points", True,
        extra_cols=["fantasy_points", "major_event_points", "goals", "assists", "clean_sheets"],
        description="Weekly points excluding goals, assists, clean sheets, and GA penalties.",
    )

    # Roster adds.
    add_award_rows(
        rows, roster_add_leaders, "season", "Roster Add Value", "total_points_after_adds", True,
        extra_cols=["roster_adds", "avg_points_per_add", "total_starts_after_adds", "best_single_add_points"],
        description="Total points produced by players after being added to a manager's roster.",
    )
    add_award_rows(
        rows, roster_add_leaders, "season", "Roster Adds", "roster_adds", True,
        extra_cols=["total_points_after_adds", "avg_points_per_add"],
        description="Most roster additions. This is not guaranteed waiver-only without transaction data.",
    )

    # Lineup changes from existing analytics.
    if not lineup_changes.empty and "view_type" in lineup_changes.columns:
        season_lineup = lineup_changes[lineup_changes["view_type"] == "season_summary"].copy()
        season_lineup = season_lineup.copy()
        if "total_starter_changes" in season_lineup.columns:
            season_lineup["net_starter_swaps"] = pd.to_numeric(
                season_lineup["total_starter_changes"], errors="coerce"
            ).fillna(0) / 2
        if "avg_starter_changes" in season_lineup.columns:
            season_lineup["avg_net_starter_swaps"] = pd.to_numeric(
                season_lineup["avg_starter_changes"], errors="coerce"
            ).fillna(0) / 2

        add_award_rows(
            rows, season_lineup, "season", "Lineup Changes", "net_starter_swaps", True,
            extra_cols=[
                "total_starter_changes", "avg_starter_changes",
                "avg_net_starter_swaps", "total_roster_turnover", "avg_roster_turnover"
            ],
            description="Estimated starter swaps. Existing raw change count is adds + removals, so this is total_starter_changes / 2.",
        )

        weekly_lineup = lineup_changes[lineup_changes["view_type"] == "weekly"].copy()
        add_award_rows(
            rows, weekly_lineup, "weekly", "Lineup Changes", "starter_changes", True,
            extra_cols=["roster_turnover", "starters_added", "starters_removed"],
            description="Most starter changes in a gameweek.",
        )

    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["scope", "award_name", "fantrax_gw", "rank"], na_position="first")
    return out


# =============================================================================
# MANAGER PROFILE SUMMARY
# =============================================================================

def build_manager_profile_summary(
    manager_season: pd.DataFrame,
    eff_season: pd.DataFrame,
    ghost_season: pd.DataFrame,
    roster_add_leaders: pd.DataFrame,
    lineup_changes: pd.DataFrame,
    position_season: pd.DataFrame,
) -> pd.DataFrame:
    profile = clean_team_cols(manager_season.copy())

    if not eff_season.empty:
        profile = profile.merge(
            eff_season[[
                "api_team_id", "season_efficiency_pct", "missed_points",
                "optimal_lineup_points", "efficiency_rank",
            ]],
            on="api_team_id",
            how="left",
        )

    if not ghost_season.empty:
        profile = profile.merge(
            ghost_season[[
                "api_team_id", "ghost_points", "major_event_points",
                "ghost_points_share_pct", "ghost_points_rank",
            ]],
            on="api_team_id",
            how="left",
        )

    if not roster_add_leaders.empty:
        profile = profile.merge(
            roster_add_leaders[[
                "api_team_id", "roster_adds", "total_points_after_adds",
                "avg_points_per_add", "roster_add_value_rank",
            ]],
            on="api_team_id",
            how="left",
        )

    if not lineup_changes.empty and "view_type" in lineup_changes.columns:
        season_lineup = lineup_changes[lineup_changes["view_type"] == "season_summary"].copy()
        season_lineup = season_lineup.copy()
        if "total_starter_changes" in season_lineup.columns:
            # Existing total_starter_changes counts adds + removals, so one simple
            # lineup swap often counts as 2. net_starter_swaps is easier to read.
            season_lineup["net_starter_swaps"] = pd.to_numeric(
                season_lineup["total_starter_changes"], errors="coerce"
            ).fillna(0) / 2
        if "avg_starter_changes" in season_lineup.columns:
            season_lineup["avg_net_starter_swaps"] = pd.to_numeric(
                season_lineup["avg_starter_changes"], errors="coerce"
            ).fillna(0) / 2

        profile = profile.merge(
            season_lineup[[
                "api_team_id", "total_starter_changes", "avg_starter_changes",
                "net_starter_swaps", "avg_net_starter_swaps",
                "total_roster_turnover", "avg_roster_turnover",
            ]],
            on="api_team_id",
            how="left",
        )

    # Flatten position totals into columns.
    if not position_season.empty:
        pos = position_season.pivot_table(
            index=["api_team_id"],
            columns="position_group",
            values="fantasy_points",
            aggfunc="sum",
            fill_value=0,
        ).reset_index()
        pos.columns = ["api_team_id"] + [f"points_from_{c}" for c in pos.columns[1:]]
        profile = profile.merge(pos, on="api_team_id", how="left")

        starts = position_season.pivot_table(
            index=["api_team_id"],
            columns="position_group",
            values="starts",
            aggfunc="sum",
            fill_value=0,
        ).reset_index()
        starts.columns = ["api_team_id"] + [f"starts_from_{c}" for c in starts.columns[1:]]
        profile = profile.merge(starts, on="api_team_id", how="left")

    return profile


# =============================================================================
# MAIN
# =============================================================================

def main() -> None:
    print("Building Efficiency, Ghost Points, Roster Adds, and Dynamic Awards")
    ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)

    mp = prepare_manager_player()
    manager_week = read_csv(MANAGER_WEEK_FILE)
    manager_season = read_csv(MANAGER_SEASON_FILE)
    lineup_changes = read_csv(LINEUP_CHANGES_FILE, required=False)

    manager_week = clean_team_cols(manager_week)
    manager_season = clean_team_cols(manager_season)
    lineup_changes = clean_team_cols(lineup_changes) if not lineup_changes.empty else lineup_changes

    eff_weekly, eff_season, decisions = build_efficiency_views(mp)
    (
        ghost_player_weekly,
        ghost_player_leaders,
        ghost_manager_weekly,
        ghost_manager_season,
        position_weekly,
        position_season,
    ) = build_ghost_views(mp)

    roster_adds_weekly, roster_adds_leaders = build_roster_adds(mp)

    manager_awards = build_manager_awards(
        manager_week=manager_week,
        manager_season=manager_season,
        eff_weekly=eff_weekly,
        eff_season=eff_season,
        ghost_weekly=ghost_manager_weekly,
        ghost_season=ghost_manager_season,
        roster_add_leaders=roster_adds_leaders,
        lineup_changes=lineup_changes,
    )

    manager_profile = build_manager_profile_summary(
        manager_season=manager_season,
        eff_season=eff_season,
        ghost_season=ghost_manager_season,
        roster_add_leaders=roster_adds_leaders,
        lineup_changes=lineup_changes,
        position_season=position_season,
    )

    outputs = [
        (eff_weekly, OUT_EFF_WEEKLY),
        (eff_season, OUT_EFF_SEASON),
        (decisions, OUT_DECISIONS),
        (ghost_player_weekly, OUT_GHOST_PLAYER_WEEKLY),
        (ghost_player_leaders, OUT_GHOST_PLAYER_LEADERS),
        (ghost_manager_weekly, OUT_GHOST_MANAGER_WEEKLY),
        (ghost_manager_season, OUT_GHOST_MANAGER_SEASON),
        (position_weekly, OUT_POSITION_WEEKLY),
        (position_season, OUT_POSITION_SEASON),
        (roster_adds_weekly, OUT_ROSTER_ADDS_WEEKLY),
        (roster_adds_leaders, OUT_ROSTER_ADDS_LEADERS),
        (manager_awards, OUT_MANAGER_AWARDS),
        (manager_profile, OUT_MANAGER_PROFILE),
    ]

    for df, path in outputs:
        save_csv(df, path)

    report = []
    report.append("Efficiency, Ghost Points, Roster Adds, and Dynamic Awards Build Report")
    report.append("=" * 90)
    report.append(f"manager_player rows: {len(mp):,}")
    report.append("")
    for df, path in outputs:
        report.append(f"{path.name}: {len(df):,} rows")
    report.append("")
    report.append("Scoring / rules assumptions:")
    report.append(f"- Total starters: {TOTAL_ACTIVE_SLOTS}")
    report.append(f"- Minimum active positions: {MIN_ACTIVE}")
    report.append(f"- Maximum active positions: {MAX_ACTIVE}")
    report.append(f"- Goal points: {GOAL_POINTS_BASE}, with M/F 3rd+ goal worth 12")
    report.append(f"- Assist points: {ASSIST_POINTS}")
    report.append(f"- Clean sheet points: {CLEAN_SHEET_POINTS}")
    report.append(f"- Goals-against after first points: {GOALS_AGAINST_AFTER_FIRST_POINTS}")
    report.append("")
    report.append("Important notes:")
    report.append("- Efficiency uses actual exported Fantrax points and manager roster eligibility.")
    report.append("- Manager ghost points are starter-only so they compare correctly to starter fantasy points.")
    report.append("- Player ghost point leaders use all rostered appearances.")
    report.append("- Roster adds are inferred from roster changes; transaction logs are required to separate waivers from trades.")
    report.append("- xG/xA are included as context columns beside goals/assists, not as standalone awards.")

    OUT_REPORT.write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))
    print(f"\nSaved report: {OUT_REPORT}")


if __name__ == "__main__":
    main()
