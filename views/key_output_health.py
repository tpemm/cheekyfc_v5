"""Key Output Health page backed by the foundation data services."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import streamlit as st

from core.models.data_result import DataResult, DataStatus
from core.services.data_manager import (
    DataManager,
    DatasetNotFoundError,
    DatasetValidationError,
    UnsupportedFormatError,
)
from core.services.season_manager import SeasonManager


ANALYTICS_DATASET_KEYS: tuple[str, ...] = (
    "league_table",
    "weekly_awards",
    "award_leaderboards",
    "manager_streaks",
    "lineup_changes",
    "closest_games",
    "biggest_blowouts",
    "league_hub_cards",
    "manager_awards_dynamic",
    "manager_profile_summary",
    "manager_efficiency_weekly",
    "manager_efficiency_season",
    "lineup_decision_details",
    "ghost_points_player_leaders",
    "ghost_points_manager_weekly",
    "ghost_points_manager_season",
    "position_points_manager_season",
    "roster_adds_weekly",
    "roster_adds_leaders",
    "manager_behavior_weekly",
    "manager_behavior_season",
    "formation_weekly",
    "formation_manager_summary",
    "formation_league_summary",
)

HEALTH_DATASET_KEYS: tuple[str, ...] = (
    "master_player_weekly",
    "manager_player_weekly",
    "manager_week_summary",
    "manager_season_summary",
    "lineup_quality_summary",
    "matchup_week_summary",
    "api_merge_report",
    *ANALYTICS_DATASET_KEYS,
)

SUMMARY_DATASET_KEYS: tuple[str, ...] = (
    "manager_week_summary",
    "manager_season_summary",
    "lineup_quality_summary",
    "matchup_week_summary",
    *ANALYTICS_DATASET_KEYS,
)


def render(
    season_id: str,
    *,
    data_manager: DataManager | None = None,
    season_manager: SeasonManager | None = None,
    ui: Any = st,
) -> None:
    """Render the existing Key Output Health workflow."""

    seasons = season_manager or SeasonManager()
    season = seasons.context(season_id)
    namespace = seasons.resolve_namespace(season.season_id)
    data = data_manager or DataManager(season_manager=seasons)

    ui.markdown(
        '<div class="section-eyebrow">Quality control</div>'
        '<div class="section-title">Key Output Health</div>'
        '<div class="section-copy">Check the files and tables required by the dashboard.</div>',
        unsafe_allow_html=True,
    )
    ui.write("Quick status check for the files the dashboard depends on.")

    health_rows = [
        _health_row(
            data.probe(dataset_key, season.season_id, namespace),
            data.project_relative_path(dataset_key, season.season_id, namespace),
        )
        for dataset_key in HEALTH_DATASET_KEYS
    ]
    ui.dataframe(
        health_rows,
        use_container_width=True,
        column_order=["status", "relative_path", "type", "size_mb", "modified"],
    )

    ui.subheader("Quick summaries")

    for dataset_key in SUMMARY_DATASET_KEYS:
        probe = data.probe(dataset_key, season.season_id, namespace)
        with ui.expander(probe.provenance.resolved_path.name, expanded=False):
            if probe.status is DataStatus.MISSING:
                ui.error("Missing")
                continue
            if probe.status is DataStatus.EMPTY:
                ui.error("Artifact is empty.")
                continue
            if probe.status is DataStatus.UNSUPPORTED:
                ui.error(_messages(probe))
                continue

            try:
                result = data.load_frame(
                    dataset_key,
                    season.season_id,
                    namespace,
                )
            except DatasetNotFoundError:
                ui.error("Missing")
                continue
            except (DatasetValidationError, UnsupportedFormatError) as exc:
                ui.error(str(exc))
                continue

            if result.status is DataStatus.EMPTY or result.data is None:
                ui.error("Artifact is empty.")
                continue
            if result.status is DataStatus.INVALID:
                ui.error(_messages(result))

            frame = result.data
            columns = list(frame.columns)
            c1, c2, c3 = ui.columns(3)
            c1.metric("Rows", f"{len(frame):,}")
            c2.metric("Columns", f"{len(columns):,}")
            if "fantrax_gw" in columns:
                c3.metric("Max GW", str(frame["fantrax_gw"].max()))
            else:
                size_bytes = result.provenance.size_bytes or 0
                c3.metric("Size MB", round(size_bytes / (1024 * 1024), 3))

            ui.dataframe(frame.head(20), use_container_width=True)


def _health_row(result: DataResult[Any], relative_path: str) -> dict[str, Any]:
    modified = result.provenance.modified_time
    return {
        "status": "MISSING" if result.status is DataStatus.MISSING else "OK",
        "relative_path": relative_path,
        "type": result.provenance.format,
        "size_mb": (
            round(result.provenance.size_bytes / (1024 * 1024), 3)
            if result.provenance.size_bytes is not None
            else None
        ),
        "modified": _format_modified(modified),
    }


def _format_modified(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _messages(result: DataResult[Any]) -> str:
    messages = (*result.validation_errors, *result.warnings)
    return "; ".join(messages) if messages else "Dataset validation failed."

