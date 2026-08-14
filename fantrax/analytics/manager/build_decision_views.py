#!/usr/bin/env python3
"""Build position-aware manager lineup decision views from the canonical file."""
from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.project_paths import PROJECT_ROOT
from fantrax.analytics.core.optimizer import LineupPlayer, optimize_lineup
from fantrax.analytics.core.scoring_engine import normalize_position, score_player_positions

SEASON_ID = "2526"
INPUT = PROJECT_ROOT / "data" / "processed" / f"manager_player_weekly_{SEASON_ID}.csv"
OUT_DIR = PROJECT_ROOT / "data" / "analytics_views"
OUT_WEEKLY = OUT_DIR / "manager_efficiency_weekly_v2.csv"
OUT_DETAILS = OUT_DIR / "lineup_decision_details_v2.csv"
OUT_VALIDATION = OUT_DIR / "manager_decision_validation_report.txt"


def _num(row: pd.Series, *names: str, default: float = 0.0) -> float:
    for name in names:
        if name in row.index and pd.notna(row[name]):
            try:
                return float(row[name])
            except (TypeError, ValueError):
                pass
    return default


def _text(row: pd.Series, *names: str) -> str:
    for name in names:
        if name in row.index and pd.notna(row[name]):
            value = str(row[name]).strip()
            if value:
                return value
    return ""


def _bool(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def build() -> tuple[pd.DataFrame, pd.DataFrame, str]:
    df = pd.read_csv(INPUT, encoding="utf-8-sig")
    rostered = df[df.get("is_rostered_api", False).map(_bool)].copy()
    if "api_roster_status" in rostered.columns:
        rostered = rostered[~rostered["api_roster_status"].fillna("").astype(str).str.upper().str.contains(r"\bIR\b|INJURED")]

    weekly_rows: list[dict] = []
    detail_rows: list[dict] = []
    validation = {"groups": 0, "legal": 0, "not_legal": 0, "rescorable_rows": 0, "official_only_rows": 0}

    group_cols = ["fantrax_gw", "api_team_id", "api_team_name"]
    for (gw, team_id, team_name), group in rostered.groupby(group_cols, dropna=False):
        validation["groups"] += 1
        players: list[LineupPlayer] = []
        row_results = {}
        for idx, row in group.iterrows():
            official_points = _num(row, "mgr_fantasy_points", "num_fantasy_points")
            actual_position = _text(row, "api_position_used", "mgr_pos")
            eligible = _text(row, "mgr_eligible", "avail_position")
            full_stats = bool(_text(row, "mgr_player"))
            result = score_player_positions(
                official_points=official_points,
                actual_position=actual_position,
                eligible_positions=eligible,
                goals=_num(row, "mgr_g", "num_goals"),
                assists=_num(row, "mgr_at", "num_assists_total"),
                clean_sheets=_num(row, "mgr_cs", "num_clean_sheets"),
                goals_against=_num(row, "mgr_ga", "num_goals_against") + _num(row, "mgr_gao"),
                full_stats_available=full_stats,
            )
            validation["rescorable_rows" if result.rescore_available else "official_only_rows"] += 1
            row_results[int(idx)] = result
            players.append(LineupPlayer(
                row_id=int(idx),
                player_id=_text(row, "fantrax_player_id"),
                player_name=_text(row, "player_name_display", "mgr_player", "avail_player"),
                scores_by_position=result.scores_by_position,
                actual_started=_bool(row.get("is_started_api", False)),
                actual_position=normalize_position(actual_position),
                rescore_available=result.rescore_available,
            ))

        optimized = optimize_lineup(players)
        validation["legal" if optimized.legal_solution_found else "not_legal"] += 1
        actual = [p for p in players if p.actual_started]
        actual_points = sum(row_results[p.row_id].official_points for p in actual)
        optimal_points = optimized.total_points if optimized.legal_solution_found else actual_points
        selected = set(optimized.selected_row_ids)
        actual_ids = {p.row_id for p in actual}

        weekly_rows.append({
            "fantrax_gw": int(gw), "api_team_id": team_id, "api_team_name": team_name,
            "actual_starter_points": round(actual_points, 2),
            "optimal_lineup_points": round(optimal_points, 2),
            "missed_points": round(max(optimal_points - actual_points, 0.0), 2),
            "efficiency_pct": round(actual_points / optimal_points * 100, 2) if optimal_points > 0 else 0.0,
            "legal_solution_found": optimized.legal_solution_found,
            "players_in_pool": len(players),
            "position_rescorable_players": sum(p.rescore_available for p in players),
            "optimizer_warning": optimized.warning,
        })

        for player in players:
            if player.row_id not in (selected | actual_ids):
                continue
            result = row_results[player.row_id]
            actual_started = player.row_id in actual_ids
            optimal_selected = player.row_id in selected
            detail_rows.append({
                "fantrax_gw": int(gw), "api_team_id": team_id, "api_team_name": team_name,
                "fantrax_player_id": player.player_id, "player_name": player.player_name,
                "eligible_positions": ",".join(result.eligible_positions),
                "actual_started": actual_started, "actual_scored_position": result.actual_position,
                "optimal_selected": optimal_selected,
                "optimal_assigned_position": optimized.assignments.get(player.row_id, ""),
                "official_fantasy_points": round(result.official_points, 2),
                "optimal_position_points": round(result.scores_by_position.get(optimized.assignments.get(player.row_id, ""), result.official_points), 2),
                "position_rescore_available": result.rescore_available,
                "scoring_source": result.scoring_source,
                "decision_type": (
                    "correct_start" if actual_started and optimal_selected else
                    "missed_bench_start" if (not actual_started and optimal_selected) else
                    "should_have_sat" if actual_started and not optimal_selected else ""
                ),
            })

    weekly = pd.DataFrame(weekly_rows).sort_values(["fantrax_gw", "api_team_name"])
    details = pd.DataFrame(detail_rows).sort_values(["fantrax_gw", "api_team_name", "decision_type", "player_name"])
    report = "\n".join([
        "Manager decision engine validation",
        "=================================",
        *(f"{k}: {v}" for k, v in validation.items()),
        "",
        "Important data limitation:",
        "All-player/waiver exports contain official points and eligibility but not the complete Fantrax event line.",
        "Position-dependent rescoring is therefore performed only for rostered rows with manager weekly stats.",
        "Waiver-player official points remain valid for player/waiver rankings but are not used for hypothetical cross-position scoring.",
    ])
    return weekly, details, report


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    weekly, details, report = build()
    weekly.to_csv(OUT_WEEKLY, index=False, encoding="utf-8-sig")
    details.to_csv(OUT_DETAILS, index=False, encoding="utf-8-sig")
    OUT_VALIDATION.write_text(report, encoding="utf-8")
    print(f"Saved {OUT_WEEKLY} ({len(weekly):,} rows)")
    print(f"Saved {OUT_DETAILS} ({len(details):,} rows)")
    print(report)


if __name__ == "__main__":
    main()
