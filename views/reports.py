"""Reports page backed by the foundation data services."""

from __future__ import annotations

from dataclasses import dataclass
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
from core.storage.storage_provider import ArtifactAccessError


STABLE_REPORT_KEYS: tuple[str, ...] = (
    "finalization_validation_report",
    "api_merge_report",
    "league_awards_report",
    "efficiency_ghost_awards_report",
    "formation_report",
)
RECENT_REPORTS_FAMILY_KEY = "recent_season_reports"


@dataclass(frozen=True, slots=True)
class _ReportEntry:
    label: str
    dataset_key: str
    resolved_path: Any
    member_name: str | None = None


def render(
    season_id: str,
    *,
    data_manager: DataManager | None = None,
    season_manager: SeasonManager | None = None,
    ui: Any = st,
) -> None:
    """Render the existing Reports page workflow."""

    seasons = season_manager or SeasonManager()
    season = seasons.context(season_id)
    namespace = seasons.resolve_namespace(season.season_id)
    data = data_manager or DataManager(season_manager=seasons)

    ui.markdown(
        '<div class="section-eyebrow">Validation and logs</div>'
        '<div class="section-title">Reports</div>'
        '<div class="section-copy">Review pipeline, analytics, and finalization reports.</div>',
        unsafe_allow_html=True,
    )
    ui.write("View validation, refresh, and analytics reports.")

    entries = _available_reports(
        data,
        season.season_id,
        namespace,
    )
    if not entries:
        ui.warning("No reports found yet.")
        ui.stop()
        return

    options = [entry.label for entry in entries]
    selected = ui.selectbox("Report", options)
    entry = entries[options.index(selected)]

    try:
        result = _load_entry(data, entry, season.season_id, namespace)
    except DatasetNotFoundError:
        ui.warning("No reports found yet.")
        return
    except (DatasetValidationError, UnsupportedFormatError, ArtifactAccessError) as exc:
        ui.error(str(exc))
        return

    ui.caption(str(entry.resolved_path))
    if result.status is DataStatus.INVALID:
        ui.error(_messages(result))
    content = result.data if isinstance(result.data, str) else ""
    ui.text_area("Report contents", content, height=750)


def _available_reports(
    data: DataManager,
    season_id: str,
    namespace: str,
) -> list[_ReportEntry]:
    entries: list[_ReportEntry] = []

    for dataset_key in STABLE_REPORT_KEYS:
        result = data.probe(dataset_key, season_id, namespace)
        if result.status is DataStatus.MISSING:
            continue
        entries.append(
            _ReportEntry(
                label=data.project_relative_path(
                    dataset_key,
                    season_id,
                    namespace,
                ),
                dataset_key=dataset_key,
                resolved_path=result.provenance.resolved_path,
            )
        )

    recent = sorted(
        data.inspect_family(
            RECENT_REPORTS_FAMILY_KEY,
            season_id,
            namespace,
        ),
        key=lambda artifact: artifact.modified_time.timestamp(),
        reverse=True,
    )[:10]
    entries.extend(
        _ReportEntry(
            label=data.project_relative_artifact_path(
                artifact.path,
                season_id,
                namespace,
            ),
            dataset_key=RECENT_REPORTS_FAMILY_KEY,
            resolved_path=artifact.path,
            member_name=artifact.name,
        )
        for artifact in recent
    )
    return entries


def _load_entry(
    data: DataManager,
    entry: _ReportEntry,
    season_id: str,
    namespace: str,
) -> DataResult[Any]:
    if entry.member_name is None:
        return data.load_text(
            entry.dataset_key,
            season_id,
            namespace,
            encoding="utf-8",
            errors="replace",
        )

    family = data.load_family(
        entry.dataset_key,
        season_id,
        namespace,
        filters={
            "name": entry.member_name,
            "limit": 1,
            "options": {
                "encoding": "utf-8",
                "text_errors": "replace",
            },
        },
    )
    if not family.data:
        raise DatasetNotFoundError(
            f"Report family member is missing: {entry.member_name}"
        )
    return family.data[0]


def _messages(result: DataResult[Any]) -> str:
    messages = (*result.validation_errors, *result.warnings)
    return "; ".join(messages) if messages else "Report validation failed."

