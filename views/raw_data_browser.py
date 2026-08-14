"""Read-only Raw Data Browser backed by the foundation data services."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from core.models.artifact_info import ArtifactInfo
from core.models.data_result import DataStatus
from core.services.data_manager import (
    DataManager,
    DataManagerError,
    DatasetNotFoundError,
    DatasetValidationError,
    UnsupportedFormatError,
)
from core.services.season_manager import SeasonManager


SUPPORTED_SUFFIXES = (".csv", ".json", ".txt", ".parquet")


def render(
    season_id: str,
    *,
    data_manager: DataManager | None = None,
    season_manager: SeasonManager | None = None,
    ui: Any = st,
) -> None:
    """Render the existing read-only Raw Data Browser workflow."""

    seasons = season_manager or SeasonManager()
    season = seasons.context(season_id)
    namespace = seasons.resolve_namespace(season.season_id)
    data = data_manager or DataManager(season_manager=seasons)

    ui.markdown(
        '<div class="section-eyebrow">Data explorer</div>'
        '<div class="section-title">Raw Data Browser</div>'
        '<div class="section-copy">Inspect project files without leaving '
        "the application.</div>",
        unsafe_allow_html=True,
    )
    ui.write(
        "Browse CSV, JSON, TXT, and Parquet files from the project data folders."
    )

    artifacts = data.catalog(
        season.season_id,
        namespace,
        filters={"recursive": True, "suffixes": SUPPORTED_SUFFIXES},
    )
    rows = [_artifact_row(data, artifact, season.season_id, namespace) for artifact in artifacts]
    files_df = pd.DataFrame(rows)
    if files_df.empty:
        ui.warning("No data files found.")
        ui.stop()
        return
    files_df = files_df.sort_values(
        ["modified", "relative_path"],
        ascending=[False, True],
    )

    col1, col2, col3 = ui.columns([2, 1, 1])
    with col1:
        file_search = ui.text_input(
            "Search file paths",
            placeholder="fantrax, understat, rosters, manager_week...",
        )
    with col2:
        type_filter = ui.multiselect(
            "File type",
            sorted(files_df["type"].dropna().unique()),
            default=[],
        )
    with col3:
        status_filter = ui.multiselect(
            "Status",
            sorted(files_df["status"].dropna().unique()),
            default=[],
        )

    filtered_files = files_df.copy()
    if file_search.strip():
        filtered_files = filtered_files[
            filtered_files["relative_path"]
            .astype(str)
            .str.lower()
            .str.contains(file_search.lower(), na=False)
        ]
    if type_filter:
        filtered_files = filtered_files[filtered_files["type"].isin(type_filter)]
    if status_filter:
        filtered_files = filtered_files[
            filtered_files["status"].isin(status_filter)
        ]

    ui.subheader("Files")
    ui.dataframe(
        filtered_files[
            ["status", "relative_path", "type", "size_mb", "modified"]
        ],
        use_container_width=True,
        height=280,
    )

    if filtered_files.empty:
        ui.warning("No data files found.")
        ui.stop()
        return

    selected_rel = ui.selectbox(
        "Open file",
        filtered_files["relative_path"].tolist(),
    )
    selected_row = filtered_files[
        filtered_files["relative_path"].eq(selected_rel)
    ].iloc[0]
    selected_artifact = selected_row["_artifact"]
    ui.caption(str(selected_artifact.path))

    max_rows = ui.slider(
        "Preview row limit",
        100,
        20000,
        5000,
        step=100,
    )

    try:
        result = data.preview_artifact(
            selected_artifact,
            season.season_id,
            namespace,
            row_limit=max_rows,
            column_limit=10000,
        )
    except (
        DataManagerError,
        DatasetNotFoundError,
        DatasetValidationError,
        UnsupportedFormatError,
    ) as exc:
        ui.error(str(exc))
        ui.stop()
        return

    if result.status is DataStatus.INVALID:
        message = "; ".join(result.validation_errors or result.warnings)
        ui.error(message or "Dataset validation failed.")
        ui.stop()
        return
    if result.status is DataStatus.MISSING:
        ui.error("Selected dataset is missing.")
        ui.stop()
        return
    if result.status is DataStatus.EMPTY:
        ui.warning("Could not load file preview.")
        ui.stop()
        return

    frame = _preview_frame(result.data, max_rows)
    if frame is None:
        ui.warning("Could not load file preview.")
        ui.stop()
        return

    ui.subheader("Preview / Filter")
    col1, col2 = ui.columns([1, 2])
    with col1:
        search_text = ui.text_input("Search within loaded rows")
    with col2:
        selected_cols = ui.multiselect(
            "Columns to show",
            frame.columns.tolist(),
            default=[],
        )

    display_df = _filter_dataframe(frame, search_text, selected_cols)
    ui.write(
        f"Loaded rows: {len(frame):,} | Displayed rows: "
        f"{len(display_df):,} | Columns: {len(display_df.columns):,}"
    )
    ui.dataframe(display_df, use_container_width=True, height=600)

    stem = (
        selected_artifact.name.rsplit(".", 1)[0]
        if "." in selected_artifact.name
        else selected_artifact.name
    )
    ui.download_button(
        "Download displayed rows as CSV",
        data=display_df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"filtered_{stem}.csv",
        mime="text/csv",
    )


def _artifact_row(
    data: DataManager,
    artifact: ArtifactInfo,
    season_id: str,
    namespace: str,
) -> dict[str, Any]:
    return {
        "status": "OK",
        "relative_path": data.project_relative_artifact_path(
            artifact.path,
            season_id,
            namespace,
        ),
        "type": artifact.suffix.lstrip("."),
        "size_mb": round(artifact.size_bytes / (1024 * 1024), 3),
        "modified": artifact.modified_time.astimezone().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "_artifact": artifact,
    }


def _preview_frame(value: Any, max_rows: int) -> pd.DataFrame | None:
    if isinstance(value, pd.DataFrame):
        return value.head(max_rows).copy()
    if isinstance(value, list):
        return pd.json_normalize(value).head(max_rows)
    if isinstance(value, dict):
        if all(isinstance(item, dict) for item in value.values()):
            return (
                pd.DataFrame.from_dict(value, orient="index")
                .reset_index(names="key")
                .head(max_rows)
            )
        return pd.json_normalize(value).head(max_rows)
    if isinstance(value, str):
        lines = value.splitlines()[:max_rows]
        return pd.DataFrame(
            {
                "line_number": range(1, len(lines) + 1),
                "text": lines,
            }
        )
    if value is not None:
        return pd.DataFrame({"value": [str(value)]})
    return None


def _filter_dataframe(
    frame: pd.DataFrame,
    search_text: str,
    selected_columns: list[str],
) -> pd.DataFrame:
    output = frame.copy()
    if selected_columns:
        keep = [
            column for column in selected_columns if column in output.columns
        ]
        if keep:
            output = output[keep]
    if search_text.strip():
        query = search_text.strip().lower()
        mask = pd.Series(False, index=output.index)
        for column in output.columns:
            mask |= (
                output[column]
                .astype(str)
                .str.lower()
                .str.contains(query, na=False, regex=False)
            )
        output = output[mask]
    return output
