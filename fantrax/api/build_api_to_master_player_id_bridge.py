#!/usr/bin/env python3
r"""
build_api_to_master_player_id_bridge.py

Purpose
-------
Build a bridge table between Fantrax API roster player IDs and existing master/Fantrax CSV player IDs.

Why
---
The Fantrax API roster player_id values do not match the player IDs used in the
Fantrax CSV exports/master dataset. This script creates candidate matches and an
auto-accepted bridge where the evidence is strong enough.

Important
---------
The API roster file does not include player names, only API player IDs. So this
first bridge uses:
- same Fantrax week / period
- same manager/team ownership
- same position
- repeated evidence across weeks

If too many players remain unresolved, the next step is fetching/scraping an API
player-id-to-name table.

Inputs:
    C:\Users\Tommy\fantrax_data\data\processed\master_player_weekly_2526.csv
    C:\Users\Tommy\fantrax_data\processed_data\fantrax_api\rosters_by_week.csv

Outputs:
    C:\Users\Tommy\fantrax_data\data\reference\api_to_master_player_id_bridge_2526.csv
    C:\Users\Tommy\fantrax_data\data\reference\api_to_master_player_id_candidates_2526.csv
    C:\Users\Tommy\fantrax_data\data\reference\api_to_master_player_id_unresolved_2526.csv
    C:\Users\Tommy\fantrax_data\data\reference\api_to_master_player_id_bridge_report_2526.txt

Run:
    python C:\Users\Tommy\fantrax_data\scripts\build_api_to_master_player_id_bridge.py
"""

from __future__ import annotations

import sys

from pathlib import Path
import re
import pandas as pd


# Portable project configuration
_PROJECT_ROOT_BOOTSTRAP = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT_BOOTSTRAP) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT_BOOTSTRAP))
from config.project_paths import PROJECT_ROOT
SEASON_ID = "2526"

MASTER_FILE = PROJECT_ROOT / "data" / "processed" / f"master_player_weekly_{SEASON_ID}.csv"
API_ROSTERS_FILE = PROJECT_ROOT / "processed_data" / "fantrax_api" / "rosters_by_week.csv"

REFERENCE_DIR = PROJECT_ROOT / "data" / "reference"
OUT_BRIDGE = REFERENCE_DIR / f"api_to_master_player_id_bridge_{SEASON_ID}.csv"
OUT_CANDIDATES = REFERENCE_DIR / f"api_to_master_player_id_candidates_{SEASON_ID}.csv"
OUT_UNRESOLVED = REFERENCE_DIR / f"api_to_master_player_id_unresolved_{SEASON_ID}.csv"
OUT_REPORT = REFERENCE_DIR / f"api_to_master_player_id_bridge_report_{SEASON_ID}.txt"

TEAM_ID_TO_MANAGER = {
    "ss2dromsme3cbmga": "grant",
    "zxivny5tme3hojrx": "garrett",
    "eaz9h4hfme2wdh8p": "evan",
    "qocqs3wjme34472y": "liam",
    "ih2b4z8ome1job2n": "nick",
    "ne94j2bxme0vsmkq": "paurav",
    "zf53q9hdme32qmoe": "rob",
    "0t8m7z91mdhjhvye": "tommy",
    "fm7cv4p0me3j48nk": "jon",
    "116s0o6ume0s7s58": "marco",
    "avv7b4d5me2tlsrt": "will",
    "xnt9wpm9me0us0r4": "yudesh",
}

AUTO_ACCEPT_SCORE = 95


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")
    return pd.read_csv(path, dtype=str, encoding="utf-8-sig")


def clean_id_series(s: pd.Series) -> pd.Series:
    return (
        s.astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .replace({"nan": pd.NA, "None": pd.NA, "": pd.NA, "<NA>": pd.NA})
    )


def clean_pos_series(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str).str.strip().str.upper()


def get_first_existing(df: pd.DataFrame, cols: list[str], fallback: str = "") -> pd.Series:
    out = pd.Series([fallback] * len(df), index=df.index, dtype="object")
    for col in cols:
        if col in df.columns:
            mask = out.eq(fallback) & df[col].notna() & df[col].astype(str).str.strip().ne("")
            out.loc[mask] = df.loc[mask, col].astype(str).str.strip()
    return out


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"Saved: {path} rows={len(df):,}")


def main() -> None:
    print("Build API → Master Player ID Bridge")
    print(f"Master:      {MASTER_FILE}")
    print(f"API rosters: {API_ROSTERS_FILE}")
    print()

    master = read_csv(MASTER_FILE)
    api = read_csv(API_ROSTERS_FILE)

    master["fantrax_gw"] = pd.to_numeric(master["fantrax_gw"], errors="coerce").astype("Int64")
    api["period"] = pd.to_numeric(api["period"], errors="coerce").astype("Int64")

    master["fantrax_player_id"] = clean_id_series(master["fantrax_player_id"])
    api["player_id"] = clean_id_series(api["player_id"])

    if "manager" not in master.columns:
        raise ValueError("Master file does not have manager column, which is needed for this bridge.")

    # API rosters have team_id, not manager slug. Add manager slug from known team IDs.
    api["manager"] = api["team_id"].map(TEAM_ID_TO_MANAGER)

    missing_manager = api[api["manager"].isna()][["team_id", "team_name"]].drop_duplicates()
    if len(missing_manager):
        print("WARNING: Some API team IDs are not in TEAM_ID_TO_MANAGER:")
        print(missing_manager.to_string(index=False))

    # Existing master rostered rows only.
    master_rostered = master[master["manager"].notna()].copy()

    # Master compact fields.
    master_rostered["master_player_name"] = get_first_existing(
        master_rostered,
        ["mgr_player", "fantrax_player_name", "avail_player"],
        fallback="",
    )
    master_rostered["master_position"] = get_first_existing(master_rostered, ["mgr_pos", "avail_position"], fallback="")
    master_rostered["master_team"] = get_first_existing(master_rostered, ["mgr_team", "fantrax_team_name", "avail_team"], fallback="")
    master_rostered["master_points"] = pd.to_numeric(master_rostered.get("mgr_fantasy_points", 0), errors="coerce").fillna(0)

    master_small = master_rostered[
        [
            "fantrax_gw",
            "manager",
            "fantrax_player_id",
            "master_player_name",
            "master_position",
            "master_team",
            "master_points",
        ]
    ].drop_duplicates()

    # API compact fields.
    api_small = api.rename(columns={
        "period": "fantrax_gw",
        "player_id": "api_player_id",
        "position": "api_position",
        "status": "api_status",
        "team_id": "api_team_id",
        "team_name": "api_team_name",
    })[
        [
            "fantrax_gw",
            "manager",
            "api_team_id",
            "api_team_name",
            "api_player_id",
            "api_position",
            "api_status",
        ]
    ].drop_duplicates()

    # Candidate join: same week and same manager.
    candidates = api_small.merge(
        master_small,
        on=["fantrax_gw", "manager"],
        how="left",
        validate="many_to_many",
    )

    candidates["api_position_clean"] = clean_pos_series(candidates["api_position"])
    candidates["master_position_clean"] = clean_pos_series(candidates["master_position"])
    candidates["position_match"] = candidates["api_position_clean"].eq(candidates["master_position_clean"])

    # Count how many possible master IDs share this API player's week-manager-position bucket.
    pos_counts = (
        candidates[candidates["position_match"]]
        .groupby(["fantrax_gw", "manager", "api_player_id", "api_position_clean"])["fantrax_player_id"]
        .nunique()
        .reset_index(name="same_position_candidate_count")
    )

    candidates = candidates.merge(
        pos_counts,
        on=["fantrax_gw", "manager", "api_player_id", "api_position_clean"],
        how="left",
    )
    candidates["same_position_candidate_count"] = pd.to_numeric(
        candidates["same_position_candidate_count"], errors="coerce"
    ).fillna(0).astype(int)

    # Candidate score.
    candidates["confidence_score"] = 40
    candidates.loc[candidates["position_match"], "confidence_score"] += 25
    candidates.loc[
        candidates["position_match"] & candidates["same_position_candidate_count"].eq(1),
        "confidence_score",
    ] += 30
    candidates.loc[candidates["fantrax_player_id"].isna(), "confidence_score"] = 0

    candidates = candidates.sort_values(
        ["fantrax_gw", "manager", "api_player_id", "confidence_score", "master_points"],
        ascending=[True, True, True, False, False],
    )

    # Best candidate per API player per week.
    best_weekly = (
        candidates
        .dropna(subset=["api_player_id", "fantrax_player_id"])
        .groupby(["fantrax_gw", "manager", "api_player_id"], as_index=False)
        .head(1)
        .copy()
    )

    # Vote across weeks to create season-level bridge.
    high_conf = best_weekly[best_weekly["confidence_score"] >= AUTO_ACCEPT_SCORE].copy()

    bridge_votes = (
        high_conf
        .groupby(["api_player_id", "fantrax_player_id"], dropna=False)
        .agg(
            vote_count=("fantrax_gw", "nunique"),
            avg_confidence=("confidence_score", "mean"),
            managers=("manager", lambda s: "|".join(sorted(set(s.dropna().astype(str))))),
            sample_master_name=("master_player_name", lambda s: s.dropna().astype(str).iloc[0] if len(s.dropna()) else pd.NA),
            sample_master_team=("master_team", lambda s: s.dropna().astype(str).iloc[0] if len(s.dropna()) else pd.NA),
            sample_api_position=("api_position", lambda s: s.dropna().astype(str).iloc[0] if len(s.dropna()) else pd.NA),
            sample_master_position=("master_position", lambda s: s.dropna().astype(str).iloc[0] if len(s.dropna()) else pd.NA),
        )
        .reset_index()
        .sort_values(["api_player_id", "vote_count", "avg_confidence"], ascending=[True, False, False])
    )

    if len(bridge_votes):
        bridge_votes["rank_for_api_id"] = bridge_votes.groupby("api_player_id").cumcount() + 1

        top = bridge_votes[bridge_votes["rank_for_api_id"] == 1].copy()
        second = bridge_votes[bridge_votes["rank_for_api_id"] == 2][["api_player_id", "vote_count"]].rename(
            columns={"vote_count": "second_vote_count"}
        )
        top = top.merge(second, on="api_player_id", how="left")
        top["second_vote_count"] = pd.to_numeric(top["second_vote_count"], errors="coerce").fillna(0)

        # Accept only repeated evidence or no second-place challenger.
        bridge = top[
            (top["vote_count"] >= 2) &
            (top["vote_count"] > top["second_vote_count"])
        ].copy()
    else:
        bridge = pd.DataFrame(columns=[
            "api_player_id",
            "fantrax_player_id",
            "vote_count",
            "avg_confidence",
            "managers",
            "sample_master_name",
            "sample_master_team",
            "sample_api_position",
            "sample_master_position",
        ])

    bridge = bridge[
        [
            "api_player_id",
            "fantrax_player_id",
            "vote_count",
            "avg_confidence",
            "managers",
            "sample_master_name",
            "sample_master_team",
            "sample_api_position",
            "sample_master_position",
        ]
    ].sort_values(["sample_master_name", "api_player_id"], na_position="last")

    # Unresolved API IDs.
    all_api_ids = set(api_small["api_player_id"].dropna().astype(str).unique())
    resolved_ids = set(bridge["api_player_id"].dropna().astype(str).unique())
    unresolved_ids = sorted(all_api_ids - resolved_ids)

    unresolved = api_small[api_small["api_player_id"].isin(unresolved_ids)].copy()
    unresolved = (
        unresolved
        .groupby(["api_player_id", "api_position"], dropna=False)
        .agg(
            weeks_seen=("fantrax_gw", "nunique"),
            managers_seen=("manager", lambda s: "|".join(sorted(set(s.dropna().astype(str))))),
            teams_seen=("api_team_name", lambda s: "|".join(sorted(set(s.dropna().astype(str))))),
            statuses_seen=("api_status", lambda s: "|".join(sorted(set(s.dropna().astype(str))))),
        )
        .reset_index()
        .sort_values(["weeks_seen", "api_player_id"], ascending=[False, True])
    )

    save_csv(candidates, OUT_CANDIDATES)
    save_csv(bridge, OUT_BRIDGE)
    save_csv(unresolved, OUT_UNRESOLVED)

    report = []
    report.append("API → Master Player ID Bridge Report")
    report.append("=" * 80)
    report.append(f"API roster rows: {len(api):,}")
    report.append(f"Unique API player IDs: {len(all_api_ids):,}")
    report.append(f"Master rostered rows: {len(master_rostered):,}")
    report.append(f"Unique master Fantrax IDs in rostered rows: {master_rostered['fantrax_player_id'].nunique():,}")
    report.append("")
    report.append(f"Bridge rows auto-created: {len(bridge):,}")
    report.append(f"Unresolved API IDs: {len(unresolved_ids):,}")
    report.append("")
    report.append("Files written:")
    report.append(f"  Bridge:     {OUT_BRIDGE}")
    report.append(f"  Candidates: {OUT_CANDIDATES}")
    report.append(f"  Unresolved: {OUT_UNRESOLVED}")
    report.append("")
    report.append("Important note:")
    report.append("  API rosters do not include player names, only API player IDs.")
    report.append("  This first bridge is based on week + manager + position + repeated voting.")
    report.append("  Review unresolved/candidate files before treating this as final.")
    report.append("")
    report.append("If too many players are unresolved:")
    report.append("  We should fetch/scrape API player names and then match by player name.")

    OUT_REPORT.write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))


if __name__ == "__main__":
    main()
