#!/usr/bin/env python3
"""Build the deterministic GW2 laptop-to-desktop migration checkpoint."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SEASON = "2627"
MODEL = ROOT / f"data/models/season_{SEASON}"
QUALITY = ROOT / f"data/quality/season_{SEASON}"

DATASETS = {
    "canonical_fixtures": MODEL / f"team_matches_{SEASON}.csv",
    "current_player_universe": MODEL / f"current_player_weekly_{SEASON}.csv",
    "current_player_summary": MODEL / f"current_player_season_summary_{SEASON}.csv",
    "current_player_match_log": MODEL / f"current_player_match_log_{SEASON}.csv",
    "participation": MODEL / f"player_match_participation_{SEASON}.csv",
    "team_match_analytics": MODEL / f"team_match_analytics_{SEASON}.csv",
    "team_season_profile": MODEL / f"team_season_profile_{SEASON}.csv",
    "team_fantasy_allowed_match": MODEL / f"team_fantasy_allowed_match_{SEASON}.csv",
    "team_fantasy_allowed_position_match": MODEL / f"team_fantasy_allowed_position_match_{SEASON}.csv",
    "team_tactical_match_features": MODEL / f"team_tactical_match_features_{SEASON}.csv",
    "team_tactical_profile": MODEL / f"team_tactical_profile_{SEASON}.csv",
    "manager_weekly_summary": MODEL / f"manager_week_summary_{SEASON}.csv",
    "league_standings": MODEL / f"league_standings_{SEASON}.csv",
    "fantrax_matchups": MODEL / f"fantrax_matchups_{SEASON}.csv",
    "live_season_manifest": MODEL / f"live_season_manifest_{SEASON}.json",
    "whoscored_manifest": ROOT / f"data/reference/whoscored_season_manifest_{SEASON}.csv",
    "understat_identity_manifest": ROOT / f"data/reference/understat_match_identity_{SEASON}.csv",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metadata(name: str, path: Path) -> dict:
    result = {"dataset": name, "path": str(path.relative_to(ROOT)), "rows": None,
              "expected_grain": "registered dataset", "season": SEASON, "max_gw": None,
              "freshness": None, "sha256": None, "validation_status": "MISSING", "notes": ""}
    if not path.exists():
        return result
    result.update(sha256=digest(path), freshness=datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(), validation_status="PRESENT")
    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path, low_memory=False)
        result["rows"] = len(frame)
        period = next((c for c in ("fantrax_period", "period", "gameweek", "gw") if c in frame), None)
        values = pd.to_numeric(frame[period], errors="coerce").dropna() if period else pd.Series(dtype=float)
        result["max_gw"] = int(values.max()) if len(values) else None
    return result


def json_read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-result", default="PENDING")
    args = parser.parse_args()
    QUALITY.mkdir(parents=True, exist_ok=True)
    rows = [metadata(name, path) for name, path in DATASETS.items()]
    manifest = pd.DataFrame(rows)
    manifest_path = QUALITY / "gw2_postmatch_refresh_validation.csv"
    manifest.to_csv(manifest_path, index=False)

    ws = pd.read_csv(ROOT / f"data/reference/whoscored_season_manifest_{SEASON}.csv")
    ws_current = ws[ws.planner_status.isin(["STABLE", "ELIGIBLE_PRELIMINARY", "FAILED_RETRYABLE"])]
    understat = pd.read_csv(ROOT / f"data/reference/understat_match_identity_{SEASON}.csv")
    weekly = pd.read_csv(MODEL / f"current_player_weekly_{SEASON}.csv", low_memory=False)
    participation = pd.read_csv(MODEL / f"player_match_participation_{SEASON}.csv", low_memory=False)
    team = pd.read_csv(MODEL / f"team_match_analytics_{SEASON}.csv", low_memory=False)
    tactical = pd.read_csv(MODEL / f"team_tactical_match_features_{SEASON}.csv", low_memory=False)
    standings = pd.read_csv(MODEL / f"league_standings_{SEASON}.csv", low_memory=False)
    identity_summary = json_read(QUALITY / f"current_player_identity_audit_summary_{SEASON}.json")
    fan_meta = json_read(ROOT / f"data/raw/fantrax/{SEASON}/player_stats/period_02/metadata.json")
    matchup_meta = json_read(ROOT / f"data/raw/fantrax/{SEASON}/matchups/period_02/metadata.json")
    understat_meta = json_read(QUALITY / f"understat_live_latest_{SEASON}.json")
    scoring = json_read(ROOT / f"config/fantrax_scoring_{SEASON}.json")
    checkpoint = {
        "checkpoint_name": "GW2_POST_MATCH_REFRESH_COMPLETE",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "machine_role": "AUTHORITATIVE_COMMISSIONER_ACQUISITION_LAPTOP",
        "season": SEASON,
        "current_period": 2,
        "gw1_status": "FINALIZED",
        "gw2_status": "COMPLETE_AWAITING_STABILITY",
        "gw2_finalized": False,
        "stability_basis": "FIRST_COMPLETE_POST_MATCH_SNAPSHOT",
        "fantrax_acquisition_timestamp": max(filter(None, [fan_meta.get("retrieved_at"), matchup_meta.get("acquired_at")]), default=None),
        "whoscored_acquisition_timestamp": ws_current.get("last_checked_at", pd.Series(dtype=object)).dropna().astype(str).max() if len(ws_current) else None,
        "understat_acquisition_timestamp": understat_meta.get("retrieved_at"),
        "fantrax_league_id": "o1wb36vdmrp1z5t8",
        "canonical_player_row_count": int(weekly.fantrax_player_id.nunique()),
        "player_match_row_count": len(participation),
        "team_match_row_count": len(team),
        "team_tactical_match_row_count": len(tactical),
        "manager_count": int(standings.manager_id.nunique()),
        "club_count": int(team.club_id.nunique()),
        "fixture_count": int(team.canonical_match_id.nunique()),
        "identity_unresolved_count": int(identity_summary.get("unresolved_canonical_identities", identity_summary.get("unresolved", 0))),
        "whoscored_match_count": int(ws_current.canonical_match_id.nunique()),
        "understat_match_count": int(understat.canonical_match_id.nunique()),
        "test_result": args.test_result,
        "methodology_versions": {"team_tactical": "team_tactical_v1", "fantrax_scoring_config_version": scoring.get("version", "configured")},
        "important_artifacts": {row["dataset"]: row["sha256"] for row in rows if row["sha256"]},
        "known_limitations": ["Nottingham Forest GW2 explicit WhoScored lineup contains 10 starters; no start inferred.", "Provider stability requires a later independent snapshot."],
    }
    checkpoint_path = QUALITY / "gw2_laptop_migration_checkpoint.json"
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")

    inventory = {
        "created_at": checkpoint["created_at"],
        "recommendation": "Authenticate Fantrax fresh on the desktop; do not copy session credentials unless explicitly approved.",
        "categories": {
            "A_GIT_TRACKED_CODE": ["application code", "scripts", "config", "tests", "requirements files"],
            "B_SYNCHRONIZED_DATA_MODELS_CACHE": ["data/raw/fantrax/2627", "data/raw/whoscored/2627", "data/raw/understat/2627", "data/models/season_2627", "data/quality/season_2627", "data/reference"],
            "C_LOCAL_ENVIRONMENT": [f"Python {platform.python_version()}", ".venv (regenerate from requirements)", "Playwright package and browser binaries", "SOCCERDATA_DIR-compatible writable cache"],
            "D_LOCAL_SECRETS": ["environment variables and .streamlit/secrets.toml remain local; never commit"],
            "E_LOCAL_AUTH_BROWSER_STATE": ["data/raw/fantrax/2627/auth/storage_state.json contains session credentials; generate fresh on desktop"],
            "F_REGENERABLE_ARTIFACTS": ["derived data/models products", "data/quality reports", "pytest caches", "Python bytecode"],
        },
        "one_writer_entry_points": ["scripts/weekly_commissioner_refresh.py", "scripts/refresh_live_fantrax.py", "scripts/weekly_advanced_refresh.py", "scripts/refresh_whoscored_live_match.py", "scripts/refresh_understat_live.py", "fantrax/scraping/scrape_understat_to_csv.py", "views/update_pipeline.py"],
        "absolute_path_audit": {"runtime_blockers": [], "legacy_or_documentation_only": ["archive/old_apps/fantrax_data_appV1.py", "archive/old_scripts", "fantrax/finalize and diagnostics docstrings"], "finding": "No active runtime dependency on a laptop-specific C:\\Users or OneDrive root was found."},
        "authority_change_performed": False,
    }
    (QUALITY / "gw2_desktop_migration_inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    print(json.dumps({"checkpoint": str(checkpoint_path), "validation": str(manifest_path), "inventory": str(QUALITY / 'gw2_desktop_migration_inventory.json')}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
