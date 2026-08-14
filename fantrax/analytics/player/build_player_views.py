#!/usr/bin/env python3
"""Build canonical player analytics views from the master player-week dataset.

The master file contains one row per Fantrax player and gameweek. Every row has
an official Fantrax fantasy score, while complete event statistics are only
available when the player was rostered in the league. These outputs preserve
that distinction explicitly so downstream dashboards never infer missing stats.
"""
from __future__ import annotations

import sys
from pathlib import Path
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.project_paths import PROJECT_ROOT
from fantrax.analytics.core.scoring_engine import normalize_position, parse_eligible_positions, score_player_positions

SEASON_ID = "2526"
INPUT = PROJECT_ROOT / "data" / "processed" / f"master_player_weekly_{SEASON_ID}.csv"
OUT_DIR = PROJECT_ROOT / "data" / "analytics_views" / "player"
OUT_WEEKLY = OUT_DIR / "player_weekly.csv"
OUT_SEASON = OUT_DIR / "player_season_summary.csv"
OUT_MANAGER = OUT_DIR / "player_manager_summary.csv"
OUT_POSITION = OUT_DIR / "player_position_weekly.csv"
OUT_COVERAGE = OUT_DIR / "player_data_coverage.csv"
OUT_REPORT = OUT_DIR / "player_views_report.txt"


def _num(df: pd.DataFrame, name: str, default: float = 0.0) -> pd.Series:
    if name not in df.columns:
        return pd.Series(default, index=df.index, dtype="float64")
    return pd.to_numeric(df[name], errors="coerce").fillna(default)


def _text(df: pd.DataFrame, *names: str) -> pd.Series:
    result = pd.Series("", index=df.index, dtype="object")
    for name in names:
        if name not in df.columns:
            continue
        candidate = df[name].fillna("").astype(str).str.strip()
        result = result.mask(result.eq("") & candidate.ne(""), candidate)
    return result


def _bool(series: pd.Series) -> pd.Series:
    return series.fillna(False).astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def _safe_div(num: pd.Series, den: pd.Series) -> pd.Series:
    out = num.div(den.where(den.ne(0)))
    return out.fillna(0.0)


def build_weekly(master: pd.DataFrame) -> pd.DataFrame:
    weekly = pd.DataFrame(index=master.index)
    weekly["season"] = _text(master, "season").replace("", SEASON_ID)
    weekly["gameweek"] = _num(master, "fantrax_gw").astype("Int64")
    weekly["fantrax_player_id"] = _text(master, "fantrax_player_id")
    weekly["player_name"] = _text(master, "fantrax_player_name", "avail_player", "mgr_player")
    weekly["epl_team"] = _text(master, "fantrax_team_name", "avail_team", "mgr_team")
    weekly["eligible_positions"] = _text(master, "mgr_eligible", "avail_position")
    weekly["default_position"] = weekly["eligible_positions"].map(lambda x: normalize_position(str(x).split(",")[0].strip()))
    weekly["official_fantasy_points"] = _num(master, "avail_fpts")
    # When available, the roster export is the authoritative actual-position score.
    roster_score = pd.to_numeric(master.get("mgr_fantasy_points"), errors="coerce") if "mgr_fantasy_points" in master else pd.Series(pd.NA, index=master.index)
    weekly["official_fantasy_points"] = roster_score.fillna(weekly["official_fantasy_points"])
    weekly["season_fppg_at_export"] = _num(master, "avail_fp_per_g")
    weekly["rostered"] = _text(master, "manager").ne("")
    weekly["manager_name"] = _text(master, "manager")
    weekly["lineup_status"] = _text(master, "api_roster_status", "mgr_status")
    weekly["started"] = _bool(master["is_started_api"]) if "is_started_api" in master else weekly["lineup_status"].str.upper().eq("ACTIVE")
    weekly["actual_position"] = _text(master, "api_position_used", "mgr_pos").map(normalize_position)

    # Event lines are only complete for rostered exports. Keep raw fields useful
    # for player analytics while marking coverage rather than filling fake zeros.
    event_map = {
        "minutes": "mgr_min", "goals": "mgr_g", "assists": "mgr_at",
        "clean_sheets": "mgr_cs", "goals_against": "mgr_ga",
        "saves": "mgr_sv", "key_passes": "mgr_kp", "tackles_won": "mgr_tkw",
        "interceptions": "mgr_int", "clearances": "mgr_clr", "aerials_won": "mgr_aer",
        "successful_dribbles": "mgr_sbon", "shots_on_target": "mgr_sot",
        "yellow_cards": "mgr_yc", "red_cards": "mgr_rc",
        "xg": "xg", "xa": "xa", "understat_minutes": "minutes",
    }
    for out_col, source_col in event_map.items():
        weekly[out_col] = pd.to_numeric(master[source_col], errors="coerce") if source_col in master else pd.NA

    weekly["fantrax_event_stats_available"] = _text(master, "mgr_player").ne("")
    weekly["understat_stats_available"] = pd.to_numeric(master.get("understat_player_id"), errors="coerce").notna() if "understat_player_id" in master else False
    weekly["position_rescore_available"] = weekly["fantrax_event_stats_available"] & weekly["actual_position"].ne("")
    weekly["data_scope"] = weekly["fantrax_event_stats_available"].map({True: "official_points_plus_rostered_stats", False: "official_points_only"})

    # Stable one-row-per-player-week key.
    weekly["source_row_id"] = master.index
    weekly = weekly.sort_values(["gameweek", "player_name", "fantrax_player_id"]).reset_index(drop=True)
    return weekly


def build_position_weekly(master: pd.DataFrame, weekly: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    weekly_by_source = weekly.set_index("source_row_id", drop=False)
    for idx, row in master.iterrows():
        if idx not in weekly_by_source.index or not bool(weekly_by_source.loc[idx, "fantrax_event_stats_available"]):
            continue
        wrow = weekly_by_source.loc[idx]
        actual_position = wrow["actual_position"]
        eligible = wrow["eligible_positions"]
        result = score_player_positions(
            official_points=wrow["official_fantasy_points"],
            actual_position=actual_position,
            eligible_positions=eligible,
            goals=row.get("mgr_g"),
            assists=row.get("mgr_at"),
            clean_sheets=row.get("mgr_cs"),
            goals_against=(pd.to_numeric(pd.Series([row.get("mgr_ga")]), errors="coerce").fillna(0).iloc[0]
                           + pd.to_numeric(pd.Series([row.get("mgr_gao")]), errors="coerce").fillna(0).iloc[0]),
            full_stats_available=True,
        )
        for pos in result.eligible_positions:
            rows.append({
                "season": wrow["season"],
                "gameweek": wrow["gameweek"],
                "fantrax_player_id": wrow["fantrax_player_id"],
                "player_name": wrow["player_name"],
                "manager_name": wrow["manager_name"],
                "epl_team": wrow["epl_team"],
                "actual_position": result.actual_position,
                "candidate_position": pos,
                "official_fantasy_points": round(result.official_points, 3),
                "candidate_position_points": round(result.scores_by_position[pos], 3),
                "position_delta": round(result.scores_by_position[pos] - result.official_points, 3),
                "is_actual_position": pos == result.actual_position,
                "scoring_source": result.scoring_source,
            })
    return pd.DataFrame(rows).sort_values(["gameweek", "player_name", "candidate_position"]).reset_index(drop=True)


def build_season_summary(weekly: pd.DataFrame) -> pd.DataFrame:
    work = weekly.copy()
    work["appearance"] = work["official_fantasy_points"].notna() & (work["official_fantasy_points"].ne(0) | work["minutes"].fillna(0).gt(0))
    work["detailed_week"] = work["fantrax_event_stats_available"].astype(int)
    work["rostered_week"] = work["rostered"].astype(int)
    work["started_week"] = work["started"].astype(int)

    grouped = work.groupby(["fantrax_player_id", "player_name"], dropna=False)
    summary = grouped.agg(
        epl_team=("epl_team", "last"),
        eligible_positions=("eligible_positions", "last"),
        gameweeks_in_master=("gameweek", "nunique"),
        appearances=("appearance", "sum"),
        total_fantasy_points=("official_fantasy_points", "sum"),
        average_points_per_week=("official_fantasy_points", "mean"),
        median_points=("official_fantasy_points", "median"),
        max_points=("official_fantasy_points", "max"),
        rostered_weeks=("rostered_week", "sum"),
        starts_in_league=("started_week", "sum"),
        detailed_stat_weeks=("detailed_week", "sum"),
        managers_owned_by=("manager_name", lambda s: s[s.ne("")].nunique()),
    ).reset_index()
    summary["points_per_appearance"] = _safe_div(summary["total_fantasy_points"], summary["appearances"])
    summary["detailed_stat_coverage_pct"] = _safe_div(summary["detailed_stat_weeks"] * 100, summary["gameweeks_in_master"])
    summary["complete_fantrax_stats"] = summary["detailed_stat_weeks"].eq(summary["gameweeks_in_master"])
    return summary.sort_values(["total_fantasy_points", "player_name"], ascending=[False, True]).reset_index(drop=True)


def build_manager_summary(weekly: pd.DataFrame) -> pd.DataFrame:
    rostered = weekly[weekly["rostered"]].copy()
    rostered["started_points"] = rostered["official_fantasy_points"].where(rostered["started"], 0.0)
    rostered["bench_points"] = rostered["official_fantasy_points"].where(~rostered["started"], 0.0)
    rostered["started_int"] = rostered["started"].astype(int)
    rostered["bench_int"] = (~rostered["started"]).astype(int)
    grouped = rostered.groupby(["manager_name", "fantrax_player_id", "player_name"], dropna=False)
    out = grouped.agg(
        epl_team=("epl_team", "last"),
        eligible_positions=("eligible_positions", "last"),
        first_owned_gw=("gameweek", "min"),
        last_owned_gw=("gameweek", "max"),
        rostered_weeks=("gameweek", "nunique"),
        starts=("started_int", "sum"),
        bench_weeks=("bench_int", "sum"),
        total_points_while_owned=("official_fantasy_points", "sum"),
        starter_points=("started_points", "sum"),
        bench_points=("bench_points", "sum"),
        average_points_while_owned=("official_fantasy_points", "mean"),
    ).reset_index()
    out["start_rate_pct"] = _safe_div(out["starts"] * 100, out["rostered_weeks"])
    out["points_per_start"] = _safe_div(out["starter_points"], out["starts"])
    return out.sort_values(["manager_name", "total_points_while_owned"], ascending=[True, False]).reset_index(drop=True)


def build_coverage(weekly: pd.DataFrame) -> pd.DataFrame:
    def row(scope: str, frame: pd.DataFrame) -> dict:
        return {
            "scope": scope,
            "player_week_rows": len(frame),
            "unique_players": frame["fantrax_player_id"].nunique(),
            "official_points_rows": frame["official_fantasy_points"].notna().sum(),
            "fantrax_event_stat_rows": frame["fantrax_event_stats_available"].sum(),
            "position_rescorable_rows": frame["position_rescore_available"].sum(),
            "understat_rows": frame["understat_stats_available"].sum(),
            "rostered_rows": frame["rostered"].sum(),
        }
    return pd.DataFrame([
        row("all_players", weekly),
        row("rostered_player_weeks", weekly[weekly["rostered"]]),
        row("waiver_or_unrostered_player_weeks", weekly[~weekly["rostered"]]),
    ])


def build() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, str]:
    master = pd.read_csv(INPUT, encoding="utf-8-sig")
    weekly = build_weekly(master)
    position = build_position_weekly(master, weekly)
    season = build_season_summary(weekly)
    manager = build_manager_summary(weekly)
    coverage = build_coverage(weekly)
    report = "\n".join([
        "Player analytics views validation",
        "=================================",
        f"master_rows: {len(master)}",
        f"player_weekly_rows: {len(weekly)}",
        f"unique_player_week_keys: {weekly[['fantrax_player_id','gameweek']].drop_duplicates().shape[0]}",
        f"player_season_rows: {len(season)}",
        f"player_manager_rows: {len(manager)}",
        f"position_candidate_rows: {len(position)}",
        f"rostered_detailed_rows: {int(weekly['fantrax_event_stats_available'].sum())}",
        f"official_points_only_rows: {int((~weekly['fantrax_event_stats_available']).sum())}",
        "",
        "Coverage rule:",
        "Official Fantrax points are available for every player-week and power universal rankings.",
        "Complete Fantrax event statistics and hypothetical position rescoring are limited to rostered player-weeks.",
        "Missing waiver event statistics are left unavailable rather than inferred as zero.",
    ])
    return weekly, season, manager, position, coverage, report


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    weekly, season, manager, position, coverage, report = build()
    weekly.to_csv(OUT_WEEKLY, index=False, encoding="utf-8-sig")
    season.to_csv(OUT_SEASON, index=False, encoding="utf-8-sig")
    manager.to_csv(OUT_MANAGER, index=False, encoding="utf-8-sig")
    position.to_csv(OUT_POSITION, index=False, encoding="utf-8-sig")
    coverage.to_csv(OUT_COVERAGE, index=False, encoding="utf-8-sig")
    OUT_REPORT.write_text(report, encoding="utf-8")
    print(f"Saved {OUT_WEEKLY} ({len(weekly):,} rows)")
    print(f"Saved {OUT_SEASON} ({len(season):,} rows)")
    print(f"Saved {OUT_MANAGER} ({len(manager):,} rows)")
    print(f"Saved {OUT_POSITION} ({len(position):,} rows)")
    print(f"Saved {OUT_COVERAGE} ({len(coverage):,} rows)")
    print(report)


if __name__ == "__main__":
    main()
