#!/usr/bin/env python3
r"""
build_name_based_api_player_bridge.py

Purpose
-------
Build the reliable crosswalk:

    API roster player_id
        -> API player name from api_player_lookup.csv
        -> existing Fantrax CSV/master player ID via name matching

This uses your existing Understat/Fantrax crosswalk as the main source of
Fantrax player names and Fantrax CSV IDs:

    data\reference\understat_fantrax_player_id_map.csv

Important
---------
Your existing crosswalk stores fantrax_player_id with asterisks like:
    *062og*

The master dataset stores:
    062og

So this script cleans those IDs.

Inputs:
    C:\Users\Tommy\fantrax_data\processed_data\fantrax_api\api_player_lookup.csv
    C:\Users\Tommy\fantrax_data\data\reference\understat_fantrax_player_id_map.csv
    C:\Users\Tommy\fantrax_data\data\processed\master_player_weekly_2526.csv
    C:\Users\Tommy\fantrax_data\processed_data\fantrax_api\rosters_by_week.csv

Outputs:
    C:\Users\Tommy\fantrax_data\data\reference\api_to_master_player_id_bridge_2526.csv
    C:\Users\Tommy\fantrax_data\data\reference\api_to_master_player_id_bridge_candidates_2526.csv
    C:\Users\Tommy\fantrax_data\data\reference\api_to_master_player_id_bridge_unresolved_2526.csv
    C:\Users\Tommy\fantrax_data\data\reference\api_to_master_player_id_bridge_report_2526.txt

Run:
    python C:\Users\Tommy\fantrax_data\scripts\build_name_based_api_player_bridge.py
"""

from __future__ import annotations

import sys

from difflib import SequenceMatcher
from pathlib import Path
import re
import unicodedata

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

API_LOOKUP_FILE = PROJECT_ROOT / "processed_data" / "fantrax_api" / "api_player_lookup.csv"
API_ROSTERS_FILE = PROJECT_ROOT / "processed_data" / "fantrax_api" / "rosters_by_week.csv"

EXISTING_CROSSWALK_FILE = PROJECT_ROOT / "data" / "reference" / "understat_fantrax_player_id_map.csv"
MASTER_FILE = PROJECT_ROOT / "data" / "processed" / f"master_player_weekly_{SEASON_ID}.csv"

REFERENCE_DIR = PROJECT_ROOT / "data" / "reference"

OUT_BRIDGE = REFERENCE_DIR / f"api_to_master_player_id_bridge_{SEASON_ID}.csv"
OUT_CANDIDATES = REFERENCE_DIR / f"api_to_master_player_id_bridge_candidates_{SEASON_ID}.csv"
OUT_UNRESOLVED = REFERENCE_DIR / f"api_to_master_player_id_bridge_unresolved_{SEASON_ID}.csv"
OUT_REPORT = REFERENCE_DIR / f"api_to_master_player_id_bridge_report_{SEASON_ID}.txt"

AUTO_ACCEPT_MIN_SCORE = 92


# =============================================================================
# HELPERS
# =============================================================================

def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig")


def clean_fantrax_id(value: object) -> str | pd.NA:
    if pd.isna(value):
        return pd.NA
    text = str(value).strip()
    text = text.replace("*", "")
    text = re.sub(r"\.0$", "", text)
    if text.lower() in {"", "nan", "none", "<na>"}:
        return pd.NA
    return text


def normalize_name(value: object) -> str:
    if pd.isna(value):
        return ""

    text = str(value).strip()

    # Convert "Last, First" -> "First Last"
    if "," in text:
        parts = [p.strip() for p in text.split(",")]
        if len(parts) >= 2:
            last = parts[0]
            first = " ".join(parts[1:])
            text = f"{first} {last}".strip()

    text = text.lower()

    # Remove accents.
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))

    # Normalize punctuation and common suffix noise.
    text = text.replace("'", "")
    text = text.replace("’", "")
    text = re.sub(r"[^a-z0-9\s-]", " ", text)
    text = text.replace("-", " ")
    text = re.sub(r"\s+", " ", text).strip()

    return text


def token_sort_name(value: object) -> str:
    norm = normalize_name(value)
    return " ".join(sorted(norm.split()))


def name_score(api_name: str, fantrax_name: str) -> float:
    a = normalize_name(api_name)
    b = normalize_name(fantrax_name)

    if not a or not b:
        return 0.0

    if a == b:
        return 100.0

    a_sort = token_sort_name(api_name)
    b_sort = token_sort_name(fantrax_name)

    direct = SequenceMatcher(None, a, b).ratio() * 100
    token = SequenceMatcher(None, a_sort, b_sort).ratio() * 100

    # Strong partial token overlap helps names with accents/compound names.
    a_tokens = set(a.split())
    b_tokens = set(b.split())
    overlap = len(a_tokens & b_tokens)
    max_tokens = max(len(a_tokens), len(b_tokens), 1)
    overlap_score = 100 * overlap / max_tokens

    return max(direct, token, overlap_score)


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"Saved: {path} rows={len(df):,}")


# =============================================================================
# MAIN
# =============================================================================

def main() -> None:
    print("Build Name-Based API → Master Player ID Bridge")
    print(f"API lookup: {API_LOOKUP_FILE}")
    print(f"Existing crosswalk: {EXISTING_CROSSWALK_FILE}")
    print()

    api_lookup = read_csv(API_LOOKUP_FILE)
    api_rosters = read_csv(API_ROSTERS_FILE)
    crosswalk = read_csv(EXISTING_CROSSWALK_FILE)
    master = read_csv(MASTER_FILE)

    # Keep only API players that appear in rosters.
    roster_api_ids = set(api_rosters["player_id"].astype(str).str.strip().dropna())
    api_lookup = api_lookup[api_lookup["api_player_id"].astype(str).str.strip().isin(roster_api_ids)].copy()

    # Clean API fields.
    api_lookup["api_player_id"] = api_lookup["api_player_id"].astype(str).str.strip()
    api_lookup["api_player_name"] = api_lookup["api_player_name"].astype(str).str.strip()
    api_lookup["api_name_norm"] = api_lookup["api_player_name"].map(normalize_name)
    api_lookup["api_name_token_sort"] = api_lookup["api_player_name"].map(token_sort_name)
    api_lookup["api_team_code"] = api_lookup.get("api_team_code", pd.Series([pd.NA] * len(api_lookup))).astype(str).str.strip()
    api_lookup["api_position"] = api_lookup.get("api_position", pd.Series([pd.NA] * len(api_lookup))).astype(str).str.strip()

    # Main candidate source: existing Understat/Fantrax crosswalk.
    crosswalk["fantrax_player_id_clean"] = crosswalk["fantrax_player_id"].map(clean_fantrax_id)
    crosswalk["fantrax_player_name"] = crosswalk["fantrax_player_name"].astype(str).str.strip()
    crosswalk["fantrax_name_norm"] = crosswalk["fantrax_player_name"].map(normalize_name)
    crosswalk["fantrax_name_token_sort"] = crosswalk["fantrax_player_name"].map(token_sort_name)
    crosswalk["fantrax_team_name"] = crosswalk["fantrax_team_name"].astype(str).str.strip()

    xwalk_players = crosswalk[
        [
            "fantrax_player_id_clean",
            "fantrax_player_name",
            "fantrax_name_norm",
            "fantrax_name_token_sort",
            "fantrax_team_name",
            "understat_player_id",
            "understat_player_name",
            "understat_team_name",
        ]
    ].dropna(subset=["fantrax_player_id_clean", "fantrax_player_name"]).drop_duplicates()

    # Backup candidate source: names from master, in case a player is not in crosswalk yet.
    master["fantrax_player_id_clean"] = master["fantrax_player_id"].map(clean_fantrax_id)

    master_name_cols = [c for c in ["fantrax_player_name", "mgr_player", "avail_player"] if c in master.columns]
    master_team_cols = [c for c in ["fantrax_team_name", "mgr_team", "avail_team"] if c in master.columns]

    master_names = []
    for _, row in master.iterrows():
        pid = row.get("fantrax_player_id_clean")
        if pd.isna(pid):
            continue

        name = None
        for c in master_name_cols:
            val = row.get(c)
            if pd.notna(val) and str(val).strip():
                name = str(val).strip()
                break
        if not name:
            continue

        team = None
        for c in master_team_cols:
            val = row.get(c)
            if pd.notna(val) and str(val).strip():
                team = str(val).strip()
                break

        master_names.append({
            "fantrax_player_id_clean": pid,
            "fantrax_player_name": name,
            "fantrax_name_norm": normalize_name(name),
            "fantrax_name_token_sort": token_sort_name(name),
            "fantrax_team_name": team,
            "understat_player_id": pd.NA,
            "understat_player_name": pd.NA,
            "understat_team_name": pd.NA,
        })

    master_players = pd.DataFrame(master_names).drop_duplicates()

    # Combine crosswalk + master candidates, preferring crosswalk rows.
    xwalk_players["source_priority"] = 1
    master_players["source_priority"] = 2

    fantrax_candidates = pd.concat([xwalk_players, master_players], ignore_index=True, sort=False)
    fantrax_candidates = fantrax_candidates.sort_values(["fantrax_player_id_clean", "source_priority"])
    fantrax_candidates = fantrax_candidates.drop_duplicates(
        subset=["fantrax_player_id_clean", "fantrax_name_norm"],
        keep="first",
    )

    # Candidate generation:
    # Start with exact normalized names/token names, then fuzzy all rostered API names.
    rows = []

    for _, api_row in api_lookup.iterrows():
        api_id = api_row["api_player_id"]
        api_name = api_row["api_player_name"]
        api_norm = api_row["api_name_norm"]
        api_token = api_row["api_name_token_sort"]
        api_team = api_row.get("api_team_code")
        api_position = api_row.get("api_position")

        # Narrow exact-ish candidates first.
        exactish = fantrax_candidates[
            (fantrax_candidates["fantrax_name_norm"] == api_norm) |
            (fantrax_candidates["fantrax_name_token_sort"] == api_token)
        ].copy()

        # If no exact-ish, use fuzzy over all candidates.
        if len(exactish) == 0:
            pool = fantrax_candidates.copy()
        else:
            pool = exactish.copy()

        for _, ft_row in pool.iterrows():
            ft_name = ft_row["fantrax_player_name"]
            score = name_score(api_name, ft_name)

            # Team bonus if code matches. fantrax_team_name is usually EPL abbreviation.
            team_bonus = 0
            ft_team = str(ft_row.get("fantrax_team_name", "")).strip()
            if api_team and ft_team and str(api_team).upper() == ft_team.upper():
                team_bonus = 3

            final_score = min(100, score + team_bonus)

            if final_score >= 80 or len(exactish) > 0:
                rows.append({
                    "api_player_id": api_id,
                    "api_player_name": api_name,
                    "api_team_code": api_team,
                    "api_position": api_position,
                    "fantrax_player_id": ft_row["fantrax_player_id_clean"],
                    "fantrax_player_name": ft_name,
                    "fantrax_team_name": ft_team,
                    "understat_player_id": ft_row.get("understat_player_id"),
                    "understat_player_name": ft_row.get("understat_player_name"),
                    "name_score": round(score, 2),
                    "team_bonus": team_bonus,
                    "final_score": round(final_score, 2),
                    "match_type": "exact_or_token" if len(exactish) > 0 else "fuzzy",
                })

    candidates = pd.DataFrame(rows)

    if len(candidates):
        candidates = candidates.sort_values(
            ["api_player_id", "final_score", "team_bonus", "name_score"],
            ascending=[True, False, False, False],
        )

        # Rank candidates per API ID.
        candidates["rank_for_api_id"] = candidates.groupby("api_player_id").cumcount() + 1

        top = candidates[candidates["rank_for_api_id"] == 1].copy()
        second = candidates[candidates["rank_for_api_id"] == 2][
            ["api_player_id", "final_score", "fantrax_player_id"]
        ].rename(columns={
            "final_score": "second_best_score",
            "fantrax_player_id": "second_best_fantrax_player_id",
        })

        top = top.merge(second, on="api_player_id", how="left")
        top["second_best_score"] = pd.to_numeric(top["second_best_score"], errors="coerce").fillna(0)
        top["score_gap"] = top["final_score"] - top["second_best_score"]

        # Accept:
        # - high score exact/token match
        # - OR perfect/near-perfect fuzzy with score gap
        bridge = top[
            (
                (top["final_score"] >= AUTO_ACCEPT_MIN_SCORE) &
                (top["score_gap"] >= 2)
            )
            |
            (
                (top["final_score"] >= 99)
            )
        ].copy()
    else:
        candidates = pd.DataFrame()
        bridge = pd.DataFrame()

    bridge_cols = [
        "api_player_id",
        "api_player_name",
        "api_team_code",
        "api_position",
        "fantrax_player_id",
        "fantrax_player_name",
        "fantrax_team_name",
        "understat_player_id",
        "understat_player_name",
        "final_score",
        "name_score",
        "team_bonus",
        "score_gap",
        "match_type",
    ]

    if len(bridge):
        bridge = bridge[[c for c in bridge_cols if c in bridge.columns]].sort_values(
            ["api_player_name", "api_player_id"]
        )

    # Unresolved rostered API players.
    all_api_ids = set(api_lookup["api_player_id"].dropna().astype(str))
    resolved_ids = set(bridge["api_player_id"].dropna().astype(str)) if len(bridge) else set()
    unresolved_ids = sorted(all_api_ids - resolved_ids)

    unresolved = api_lookup[api_lookup["api_player_id"].isin(unresolved_ids)].copy()
    unresolved = unresolved[
        [c for c in ["api_player_id", "api_player_name", "api_team_code", "api_position"] if c in unresolved.columns]
    ].sort_values(["api_player_name", "api_player_id"])

    save_csv(candidates, OUT_CANDIDATES)
    save_csv(bridge, OUT_BRIDGE)
    save_csv(unresolved, OUT_UNRESOLVED)

    report = []
    report.append("Name-Based API → Master Player ID Bridge Report")
    report.append("=" * 80)
    report.append(f"Rostered API player IDs: {len(all_api_ids):,}")
    report.append(f"Fantrax candidate players: {fantrax_candidates['fantrax_player_id_clean'].nunique():,}")
    report.append("")
    report.append(f"Bridge rows accepted: {len(bridge):,}")
    report.append(f"Unresolved API players: {len(unresolved):,}")
    report.append("")
    report.append("Files:")
    report.append(f"  Bridge:     {OUT_BRIDGE}")
    report.append(f"  Candidates: {OUT_CANDIDATES}")
    report.append(f"  Unresolved: {OUT_UNRESOLVED}")
    report.append("")
    if len(bridge):
        report.append("Bridge sample:")
        report.append(bridge.head(25).to_string(index=False))
    if len(unresolved):
        report.append("")
        report.append("Unresolved sample:")
        report.append(unresolved.head(25).to_string(index=False))

    OUT_REPORT.write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))


if __name__ == "__main__":
    main()
