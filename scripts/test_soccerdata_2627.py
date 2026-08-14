#!/usr/bin/env python3
"""
Evaluate SoccerData coverage for the 2026/27 English Premier League season.

Primary goal:
- Test whether Understat already exposes 2026/27 EPL data.
- Save all useful current-season data that SoccerData can retrieve.
- Probe other SoccerData providers for schedules, forecasts, lineups, and player data.
- Produce a clear JSON/CSV coverage report before we integrate anything into Fantrax Data v5.

This script is intentionally read-only. It does not modify existing 2025/26 datasets.

Install:
    pip install -U soccerdata pandas lxml html5lib beautifulsoup4

Run from the Fantrax project root:
    python scripts/test_soccerdata_2627.py

Optional:
    python scripts/test_soccerdata_2627.py --output data/raw/soccerdata/coverage_2627
"""

from __future__ import annotations

import argparse
import inspect
import json
import platform
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd


LEAGUE = "ENG-Premier League"
SEASON_CANDIDATES = ["2627", "2026/2027", "2026-2027", 2026]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_name(value: str) -> str:
    return (
        value.lower()
        .replace(" ", "_")
        .replace("/", "_")
        .replace("-", "_")
        .replace(".", "_")
    )


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    if isinstance(out.index, pd.MultiIndex):
        out = out.reset_index()
    elif out.index.name is not None:
        out = out.reset_index()

    if isinstance(out.columns, pd.MultiIndex):
        out.columns = [
            "__".join(str(part) for part in col if str(part) not in {"", "None"})
            for col in out.columns.to_flat_index()
        ]
    else:
        out.columns = [str(col) for col in out.columns]

    # Avoid duplicate-column failures when saving.
    counts: dict[str, int] = {}
    renamed: list[str] = []
    for col in out.columns:
        counts[col] = counts.get(col, 0) + 1
        renamed.append(col if counts[col] == 1 else f"{col}_{counts[col]}")
    out.columns = renamed
    return out


def dataframe_summary(df: pd.DataFrame) -> dict[str, Any]:
    flat = flatten_columns(df)
    return {
        "rows": int(len(flat)),
        "columns": int(len(flat.columns)),
        "column_names": list(flat.columns),
        "sample": flat.head(3).where(pd.notna(flat.head(3)), None).to_dict("records"),
    }


def save_dataframe(df: pd.DataFrame, path: Path) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    flat = flatten_columns(df)
    flat.to_csv(path, index=False, encoding="utf-8-sig")
    return dataframe_summary(df)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def public_read_methods(obj: Any) -> list[str]:
    methods = []
    for name in dir(obj):
        if name.startswith("read_"):
            member = getattr(obj, name, None)
            if callable(member):
                methods.append(name)
    return sorted(methods)


def build_reader(reader_class: Any, season: Any, output_dir: Path) -> Any:
    kwargs = {
        "leagues": LEAGUE,
        "seasons": season,
        "no_cache": True,
        "data_dir": output_dir / "_soccerdata_cache",
    }
    sig = inspect.signature(reader_class)
    accepted = {k: v for k, v in kwargs.items() if k in sig.parameters}
    return reader_class(**accepted)


def call_method(
    source_name: str,
    reader: Any,
    method_name: str,
    output_dir: Path,
    report: dict[str, Any],
    kwargs: dict[str, Any] | None = None,
) -> pd.DataFrame | None:
    kwargs = kwargs or {}
    method = getattr(reader, method_name, None)

    result_record: dict[str, Any] = {
        "method": method_name,
        "kwargs": kwargs,
        "started_at_utc": utc_now(),
    }

    if not callable(method):
        result_record.update({"ok": False, "skipped": True, "reason": "Method unavailable"})
        report["methods"][method_name] = result_record
        return None

    try:
        print(f"  -> {source_name}.{method_name}({kwargs})")
        result = method(**kwargs)

        if not isinstance(result, pd.DataFrame):
            result_record.update(
                {
                    "ok": True,
                    "returned_type": type(result).__name__,
                    "note": "Method did not return a DataFrame.",
                }
            )
            report["methods"][method_name] = result_record
            return None

        filename = f"{safe_name(source_name)}__{safe_name(method_name)}.csv"
        summary = save_dataframe(result, output_dir / filename)
        result_record.update(
            {
                "ok": True,
                "output_file": filename,
                **summary,
            }
        )
        report["methods"][method_name] = result_record
        return result

    except Exception as exc:
        result_record.update(
            {
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(limit=8),
            }
        )
        report["methods"][method_name] = result_record
        print(f"     FAILED: {type(exc).__name__}: {exc}")
        return None


def detect_understat_season(sd: Any, output_dir: Path, report: dict[str, Any]) -> tuple[Any | None, Any | None]:
    """Try known SoccerData season formats and return the first working Understat reader."""
    attempts: list[dict[str, Any]] = []

    for season in SEASON_CANDIDATES:
        attempt = {"season_input": season, "started_at_utc": utc_now()}
        print(f"\nTesting Understat season input: {season!r}")

        try:
            reader = build_reader(sd.Understat, season, output_dir)
            attempt["selected_seasons"] = list(getattr(reader, "seasons", []))

            seasons_df = reader.read_seasons()
            attempt["read_seasons"] = dataframe_summary(seasons_df)

            schedule_df = reader.read_schedule(
                include_matches_without_data=True,
                force_cache=False,
            )
            attempt["read_schedule"] = dataframe_summary(schedule_df)

            # A season is useful if it returns a schedule or clearly resolves to 2627.
            selected = [str(x).replace("/", "").replace("-", "") for x in getattr(reader, "seasons", [])]
            useful = len(schedule_df) > 0 or any("2627" in item for item in selected)
            attempt["usable"] = bool(useful)
            attempts.append(attempt)

            if useful:
                report["season_detection_attempts"] = attempts
                return season, reader

        except Exception as exc:
            attempt.update(
                {
                    "usable": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            attempts.append(attempt)
            print(f"  Not usable: {type(exc).__name__}: {exc}")

    report["season_detection_attempts"] = attempts
    return None, None


def inspect_current_teams(player_df: pd.DataFrame | None, schedule_df: pd.DataFrame | None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "teams_from_player_stats": [],
        "teams_from_schedule": [],
        "team_count_from_player_stats": 0,
        "team_count_from_schedule": 0,
    }

    if player_df is not None and not player_df.empty:
        flat = flatten_columns(player_df)
        team_cols = [c for c in flat.columns if c.lower() in {"team", "team_name"}]
        if team_cols:
            teams = sorted(flat[team_cols[0]].dropna().astype(str).unique().tolist())
            result["teams_from_player_stats"] = teams
            result["team_count_from_player_stats"] = len(teams)

    if schedule_df is not None and not schedule_df.empty:
        flat = flatten_columns(schedule_df)
        values: set[str] = set()
        for col in flat.columns:
            if col.lower() in {"home_team", "away_team", "home", "away"}:
                values.update(flat[col].dropna().astype(str).tolist())
        teams = sorted(values)
        result["teams_from_schedule"] = teams
        result["team_count_from_schedule"] = len(teams)

    return result


def probe_source(
    sd: Any,
    source_name: str,
    class_name: str,
    season: Any,
    output_dir: Path,
    method_plan: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    source_report: dict[str, Any] = {
        "source": source_name,
        "class_name": class_name,
        "season_input": season,
        "methods": {},
    }

    reader_class = getattr(sd, class_name, None)
    if reader_class is None:
        source_report["fatal_error"] = f"soccerdata has no {class_name} class."
        return source_report

    try:
        reader = build_reader(reader_class, season, output_dir)
        source_report["selected_leagues"] = list(getattr(reader, "leagues", []))
        source_report["selected_seasons"] = list(getattr(reader, "seasons", []))
        source_report["available_read_methods"] = public_read_methods(reader)
    except Exception as exc:
        source_report["fatal_error"] = f"{type(exc).__name__}: {exc}"
        return source_report

    for method_name, kwargs in method_plan:
        call_method(
            source_name=source_name,
            reader=reader,
            method_name=method_name,
            output_dir=output_dir,
            report=source_report,
            kwargs=kwargs,
        )

    return source_report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test SoccerData coverage for the 2026/27 Premier League season."
    )
    parser.add_argument(
        "--output",
        default="data/raw/soccerdata/coverage_2627",
        help="Output directory relative to the project root.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "started_at_utc": utc_now(),
        "python_version": sys.version,
        "platform": platform.platform(),
        "league": LEAGUE,
        "requested_season": "2026/27",
        "sources": {},
        "important_interpretation": {
            "understat_is_not_a_roster_database": (
                "Understat player-season data only includes players already represented "
                "on the selected season page. Before matches begin, it may be empty or incomplete."
            ),
            "predictions_are_source_specific": (
                "SoccerData itself is a scraper framework. Forecasts or predictions are only "
                "available if an underlying source exposes them through a supported reader."
            ),
        },
    }

    try:
        import soccerdata as sd
        report["soccerdata_version"] = getattr(sd, "__version__", "unknown")
    except Exception as exc:
        report["fatal_error"] = (
            "Could not import soccerdata. Install it with: "
            "pip install -U soccerdata pandas lxml html5lib beautifulsoup4"
        )
        report["import_error"] = f"{type(exc).__name__}: {exc}"
        save_json(output_dir / "soccerdata_2627_coverage_report.json", report)
        print(report["fatal_error"], file=sys.stderr)
        return 2

    print("=" * 76)
    print("SOCCERDATA 2026/27 PREMIER LEAGUE COVERAGE TEST")
    print("=" * 76)
    print(f"Output: {output_dir}")
    print(f"SoccerData version: {report['soccerdata_version']}")

    # ------------------------------------------------------------------
    # UNDERSTAT: main current-season scrape
    # ------------------------------------------------------------------
    understat_report: dict[str, Any] = {
        "source": "Understat",
        "methods": {},
    }
    detected_season, understat = detect_understat_season(
        sd, output_dir / "understat", understat_report
    )

    if understat is None:
        understat_report["fatal_error"] = (
            "No tested 2026/27 season format produced usable Understat data."
        )
    else:
        understat_report["detected_season_input"] = detected_season
        understat_report["selected_seasons"] = list(getattr(understat, "seasons", []))
        understat_report["available_read_methods"] = public_read_methods(understat)

        schedule = call_method(
            "Understat",
            understat,
            "read_schedule",
            output_dir / "understat",
            understat_report,
            {"include_matches_without_data": True, "force_cache": False},
        )
        player_season = call_method(
            "Understat",
            understat,
            "read_player_season_stats",
            output_dir / "understat",
            understat_report,
            {"force_cache": False},
        )
        team_match = call_method(
            "Understat",
            understat,
            "read_team_match_stats",
            output_dir / "understat",
            understat_report,
            {"force_cache": False},
        )

        # Avoid full player-match and shot-event calls before the season has data.
        has_completed_data = False
        if schedule is not None and not schedule.empty:
            flat_schedule = flatten_columns(schedule)
            if "has_data" in flat_schedule.columns:
                has_completed_data = bool(flat_schedule["has_data"].fillna(False).astype(bool).any())
            elif "is_result" in flat_schedule.columns:
                has_completed_data = bool(flat_schedule["is_result"].fillna(False).astype(bool).any())

        understat_report["has_completed_match_data"] = has_completed_data
        understat_report["current_team_evidence"] = inspect_current_teams(
            player_season, schedule
        )

        if has_completed_data:
            call_method(
                "Understat",
                understat,
                "read_player_match_stats",
                output_dir / "understat",
                understat_report,
            )
            call_method(
                "Understat",
                understat,
                "read_shot_events",
                output_dir / "understat",
                understat_report,
            )
        else:
            understat_report["methods"]["read_player_match_stats"] = {
                "ok": False,
                "skipped": True,
                "reason": "No completed 2026/27 Understat matches detected yet.",
            }
            understat_report["methods"]["read_shot_events"] = {
                "ok": False,
                "skipped": True,
                "reason": "No completed 2026/27 Understat matches detected yet.",
            }

    report["sources"]["understat"] = understat_report

    # ------------------------------------------------------------------
    # OTHER SOCCERDATA PROVIDERS
    # These are coverage probes, not yet production scrapers.
    # ------------------------------------------------------------------
    season_for_other_sources: Any = detected_season or "2627"

    provider_plans = [
        (
            "ESPN",
            "ESPN",
            [
                ("read_schedule", {}),
                ("read_matchsheet", {}),
                ("read_lineup", {}),
            ],
        ),
        (
            "Sofascore",
            "Sofascore",
            [
                ("read_schedule", {}),
                ("read_league_table", {}),
                ("read_team_match_stats", {}),
                ("read_player_match_stats", {}),
                ("read_lineups", {}),
            ],
        ),
        (
            "FBref",
            "FBref",
            [
                ("read_schedule", {}),
                ("read_player_season_stats", {"stat_type": "standard"}),
            ],
        ),
    ]

    for source_name, class_name, plan in provider_plans:
        print(f"\nProbing {source_name}...")
        source_dir = output_dir / safe_name(source_name)
        source_report = probe_source(
            sd=sd,
            source_name=source_name,
            class_name=class_name,
            season=season_for_other_sources,
            output_dir=source_dir,
            method_plan=plan,
        )
        report["sources"][safe_name(source_name)] = source_report

    # ------------------------------------------------------------------
    # FINAL COVERAGE VERDICT
    # ------------------------------------------------------------------
    understat_methods = report["sources"]["understat"].get("methods", {})
    schedule_info = understat_methods.get("read_schedule", {})
    players_info = understat_methods.get("read_player_season_stats", {})

    report["coverage_verdict"] = {
        "understat_2627_schedule_available": bool(
            schedule_info.get("ok") and schedule_info.get("rows", 0) > 0
        ),
        "understat_2627_player_stats_available": bool(
            players_info.get("ok") and players_info.get("rows", 0) > 0
        ),
        "understat_usable_for_complete_current_rosters_now": bool(
            players_info.get("ok")
            and players_info.get("rows", 0) >= 400
            and report["sources"]["understat"]
            .get("current_team_evidence", {})
            .get("team_count_from_player_stats", 0)
            >= 20
        ),
        "prediction_method_candidates": {
            key: [
                method
                for method, details in source.get("methods", {}).items()
                if details.get("ok") and any(
                    token in method.lower()
                    for token in ("forecast", "prediction", "odds", "lineup")
                )
            ]
            for key, source in report["sources"].items()
        },
        "recommended_next_step": (
            "Use the generated CSVs to assess current-team coverage. "
            "Do not treat an empty pre-season Understat player table as a failure; "
            "re-run this scraper after the first EPL matches."
        ),
    }

    report["completed_at_utc"] = utc_now()
    save_json(output_dir / "soccerdata_2627_coverage_report.json", report)

    print("\n" + "=" * 76)
    print("COVERAGE TEST COMPLETE")
    print("=" * 76)
    print(
        "Understat schedule rows: "
        f"{schedule_info.get('rows', 0) if schedule_info.get('ok') else 'FAILED'}"
    )
    print(
        "Understat player rows:   "
        f"{players_info.get('rows', 0) if players_info.get('ok') else 'FAILED'}"
    )
    print(f"Report: {output_dir / 'soccerdata_2627_coverage_report.json'}")
    print("\nPlease send back:")
    print("  1. The full PowerShell output")
    print("  2. soccerdata_2627_coverage_report.json")
    print("  3. Any generated Understat CSV files")
    print("=" * 76)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
