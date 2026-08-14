from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from core.models.data_result import DataProvenance, DataResult, DataStatus
from views.key_output_health import (
    HEALTH_DATASET_KEYS,
    SUMMARY_DATASET_KEYS,
    render,
)


class FakeColumn:
    def __init__(self, ui):
        self.ui = ui

    def metric(self, label, value):
        self.ui.metrics.append((label, value))


class FakeExpander:
    def __init__(self, ui, label):
        self.ui = ui
        self.label = label

    def __enter__(self):
        self.ui.expanders.append(self.label)
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class FakeUI:
    def __init__(self):
        self.markdowns = []
        self.writes = []
        self.dataframes = []
        self.subheaders = []
        self.expanders = []
        self.errors = []
        self.metrics = []

    def markdown(self, value, **kwargs):
        self.markdowns.append((value, kwargs))

    def write(self, value):
        self.writes.append(value)

    def dataframe(self, value, **kwargs):
        self.dataframes.append((value, kwargs))

    def subheader(self, value):
        self.subheaders.append(value)

    def expander(self, label, expanded=False):
        return FakeExpander(self, label)

    def error(self, value):
        self.errors.append(value)

    def columns(self, count):
        return tuple(FakeColumn(self) for _ in range(count))


class FakeSeasonManager:
    def __init__(self, namespace="working", invalid=False):
        self.namespace = namespace
        self.invalid = invalid
        self.context_calls = []
        self.namespace_calls = []

    def context(self, season_id):
        self.context_calls.append(season_id)
        if self.invalid:
            raise KeyError(f"Unknown season ID: {season_id!r}")
        return SimpleNamespace(season_id=season_id)

    def resolve_namespace(self, season_id):
        self.namespace_calls.append(season_id)
        return self.namespace


class FakeDataManager:
    def __init__(self, overrides=None):
        self.overrides = overrides or {}
        self.probe_calls = []
        self.path_calls = []
        self.load_calls = []

    def probe(self, dataset_key, season_id, namespace):
        self.probe_calls.append((dataset_key, season_id, namespace))
        result = self.overrides.get(dataset_key)
        if result is not None:
            return result
        return make_result(dataset_key, season_id, namespace)

    def project_relative_path(self, dataset_key, season_id, namespace):
        self.path_calls.append((dataset_key, season_id, namespace))
        return f"data/{namespace}/{dataset_key}.csv"

    def load_frame(self, dataset_key, season_id, namespace):
        self.load_calls.append((dataset_key, season_id, namespace))
        result = self.overrides.get(dataset_key)
        if result is not None:
            return result
        return make_result(dataset_key, season_id, namespace)


def make_result(
    dataset_key,
    season_id="2627",
    namespace="working",
    *,
    status=DataStatus.AVAILABLE,
    errors=(),
    warnings=(),
    data=None,
):
    frame = (
        pd.DataFrame({"fantrax_gw": [1, 2], "value": [10, 20]})
        if data is None and status in {DataStatus.AVAILABLE, DataStatus.INVALID}
        else data
    )
    return DataResult(
        status=status,
        data=frame,
        provenance=DataProvenance(
            dataset_key=dataset_key,
            requested_key=dataset_key,
            season_id=season_id,
            namespace=namespace,
            resolved_path=Path(f"/project/data/{dataset_key}.csv"),
            format="csv",
            modified_time=datetime(2026, 7, 29, tzinfo=timezone.utc),
            size_bytes=1024,
        ),
        validation_errors=errors,
        warnings=warnings,
    )


def render_page(*, overrides=None, namespace="working"):
    ui = FakeUI()
    seasons = FakeSeasonManager(namespace=namespace)
    data = FakeDataManager(overrides)
    render(
        "2627" if namespace == "working" else "2526",
        data_manager=data,
        season_manager=seasons,
        ui=ui,
    )
    return ui, seasons, data


def test_page_renders_with_valid_datasets():
    ui, _, data = render_page()

    assert "Key Output Health" in ui.markdowns[0][0]
    assert ui.subheaders == ["Quick summaries"]
    assert len(ui.dataframes) == 1 + len(SUMMARY_DATASET_KEYS)
    assert not ui.errors
    assert [call[0] for call in data.probe_calls[: len(HEALTH_DATASET_KEYS)]] == list(
        HEALTH_DATASET_KEYS
    )


def test_missing_optional_dataset_is_user_friendly():
    missing = make_result(
        "manager_behavior_weekly",
        status=DataStatus.MISSING,
        warnings=("Optional dataset is missing.",),
        data=None,
    )

    ui, _, _ = render_page(overrides={"manager_behavior_weekly": missing})

    assert "Missing" in ui.errors
    assert "manager_behavior_weekly.csv" in ui.expanders


def test_missing_required_dataset_is_user_friendly():
    missing = make_result(
        "league_table",
        status=DataStatus.MISSING,
        errors=("Required dataset is missing.",),
        data=None,
    )

    ui, _, _ = render_page(overrides={"league_table": missing})

    assert "Missing" in ui.errors
    health_rows = ui.dataframes[0][0]
    league_row = next(
        row for row in health_rows if row["relative_path"].endswith("league_table.csv")
    )
    assert league_row["status"] == "MISSING"


def test_invalid_season_propagates_without_data_access():
    ui = FakeUI()
    seasons = FakeSeasonManager(invalid=True)
    data = FakeDataManager()

    with pytest.raises(KeyError, match="Unknown season ID"):
        render(
            "invalid",
            data_manager=data,
            season_manager=seasons,
            ui=ui,
        )

    assert data.probe_calls == []


def test_validation_messages_are_displayed():
    invalid = make_result(
        "league_table",
        status=DataStatus.INVALID,
        errors=("Missing required columns: rank",),
    )

    ui, _, _ = render_page(overrides={"league_table": invalid})

    assert "Missing required columns: rank" in ui.errors


def test_empty_dataset_is_reported_without_rendering_summary():
    empty = make_result(
        "league_table",
        status=DataStatus.EMPTY,
        errors=("Artifact is empty.",),
        data=None,
    )

    ui, _, data = render_page(overrides={"league_table": empty})

    assert "Artifact is empty." in ui.errors
    assert not any(call[0] == "league_table" for call in data.load_calls)


def test_finalized_snapshot_namespace_is_used_for_every_request():
    _, seasons, data = render_page(namespace="snapshot")

    assert seasons.context_calls == ["2526"]
    assert seasons.namespace_calls == ["2526"]
    assert all(call[2] == "snapshot" for call in data.probe_calls)
    assert all(call[2] == "snapshot" for call in data.load_calls)


def test_working_namespace_and_data_manager_interactions():
    _, seasons, data = render_page(namespace="working")

    assert seasons.context_calls == ["2627"]
    assert seasons.namespace_calls == ["2627"]
    assert {call[0] for call in data.path_calls} == set(HEALTH_DATASET_KEYS)
    assert [call[0] for call in data.load_calls] == list(SUMMARY_DATASET_KEYS)
    assert all(call[2] == "working" for call in data.load_calls)
