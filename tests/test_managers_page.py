from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from core.models.data_result import DataProvenance, DataResult, DataStatus
from views.managers import DATASET_KEYS, render


class StopSignal(RuntimeError):
    pass


class FakeElement:
    def __init__(self, ui):
        self.ui = ui

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def markdown(self, value, **kwargs):
        self.ui.markdown(value, **kwargs)

    def metric(self, label, value, delta=None, **kwargs):
        self.ui.metrics.append((label, value, delta))

    def caption(self, value):
        self.ui.captions.append(value)


class FakeUI(FakeElement):
    def __init__(self, selections=None):
        super().__init__(self)
        self.selections = selections or {}
        self.markdowns = []
        self.captions = []
        self.warnings = []
        self.infos = []
        self.metrics = []
        self.tables = []
        self.charts = []
        self.tab_labels = []
        self.select_calls = []
        self.downloads = []

    def markdown(self, value, **kwargs):
        self.markdowns.append(str(value))

    def caption(self, value):
        self.captions.append(str(value))

    def warning(self, value):
        self.warnings.append(str(value))

    def info(self, value):
        self.infos.append(str(value))

    def stop(self):
        raise StopSignal()

    def tabs(self, labels):
        self.tab_labels = list(labels)
        return [FakeElement(self) for _ in labels]

    def columns(self, spec, **kwargs):
        count = spec if isinstance(spec, int) else len(spec)
        return [FakeElement(self) for _ in range(count)]

    def selectbox(self, label, options, **kwargs):
        values = list(options)
        self.select_calls.append((label, values, kwargs))
        return self.selections.get(label, values[0] if values else None)

    def multiselect(self, label, options, default=None, **kwargs):
        return self.selections.get(label, default or [])

    def slider(self, label, min_value, max_value, value, **kwargs):
        return self.selections.get(label, value)

    def checkbox(self, label, value=False, **kwargs):
        return self.selections.get(label, value)

    def toggle(self, label, value=False, **kwargs):
        return self.selections.get(label, value)

    def dataframe(self, data, **kwargs):
        self.tables.append((data, kwargs))

    def line_chart(self, data, **kwargs):
        self.charts.append(("line", data, kwargs))

    def bar_chart(self, data, **kwargs):
        self.charts.append(("bar", data, kwargs))

    def plotly_chart(self, figure, **kwargs):
        self.charts.append(("plotly", figure, kwargs))

    def vega_lite_chart(self, *args, **kwargs):
        self.charts.append(("vega", args, kwargs))

    def download_button(self, label, **kwargs):
        self.downloads.append((label, kwargs))

    def expander(self, *args, **kwargs):
        return FakeElement(self)

    def write(self, value):
        self.markdowns.append(str(value))


class FakeSeasonManager:
    def __init__(self, namespace="working", finalized=False, invalid=False):
        self.namespace = namespace
        self.finalized = finalized
        self.invalid = invalid
        self.context_calls = []
        self.namespace_calls = []

    def context(self, season_id):
        self.context_calls.append(season_id)
        if self.invalid:
            raise KeyError(f"Unknown season ID: {season_id!r}")
        return SimpleNamespace(
            season_id=season_id,
            display_name="2025/26",
            finalized=self.finalized,
        )

    def resolve_namespace(self, season_id):
        self.namespace_calls.append(season_id)
        return self.namespace


class FakeDataManager:
    def __init__(self, frames=None, results=None):
        self.frames = minimal_frames()
        self.frames.update(frames or {})
        self.results = results or {}
        self.calls = []

    def load_frame(self, key, season_id, namespace):
        self.calls.append((key, season_id, namespace))
        if key in self.results:
            return self.results[key]
        frame = self.frames.get(key, pd.DataFrame())
        status = DataStatus.EMPTY if frame.empty else DataStatus.AVAILABLE
        return make_result(key, frame, status=status, namespace=namespace)


def make_result(
    key,
    data,
    *,
    status=DataStatus.AVAILABLE,
    namespace="working",
    errors=(),
):
    return DataResult(
        status=status,
        data=data,
        provenance=DataProvenance(
            dataset_key=key,
            requested_key=key,
            season_id="2526",
            namespace=namespace,
            resolved_path=Path(f"/project/{namespace}/{key}.csv"),
            format="csv",
            modified_time=datetime(2026, 7, 29, tzinfo=timezone.utc),
            size_bytes=128,
        ),
        validation_errors=errors,
    )


def minimal_frames():
    profile = pd.DataFrame(
        {
            "api_team_name": ["Alpha FC"],
            "official_rank": [1],
            "official_record": ["3-1"],
            "total_starter_points": [300.0],
            "season_efficiency_pct": [88.0],
        }
    )
    return {
        key: profile.copy()
        if key == "manager_profile_summary"
        else pd.DataFrame()
        for key in DATASET_KEYS
    }


def output(ui):
    return "\n".join(ui.markdowns + ui.captions)


def test_valid_manager_renders_all_existing_tabs_and_uses_data_manager():
    ui = FakeUI()
    data = FakeDataManager()

    render(
        "2526",
        data_manager=data,
        season_manager=FakeSeasonManager(),
        ui=ui,
    )

    assert ui.tab_labels == [
        "Overview",
        "Performance",
        "Squad",
        "Decisions",
        "Explorer",
    ]
    assert [call[0] for call in data.calls] == list(DATASET_KEYS)
    assert "Alpha FC" in output(ui)


def test_invalid_manager_is_reported_without_traceback():
    ui = FakeUI(selections={"Manager": "Missing FC"})

    with pytest.raises(StopSignal):
        render(
            "2526",
            data_manager=FakeDataManager(),
            season_manager=FakeSeasonManager(),
            ui=ui,
        )

    assert "Missing FC" in ui.warnings[0]


def test_missing_required_profile_preserves_empty_state():
    ui = FakeUI()
    data = FakeDataManager(
        results={
            "manager_profile_summary": make_result(
                "manager_profile_summary",
                None,
                status=DataStatus.MISSING,
            )
        }
    )

    with pytest.raises(StopSignal):
        render(
            "2526",
            data_manager=data,
            season_manager=FakeSeasonManager(),
            ui=ui,
        )

    assert ui.infos == [
        "Manager analytics are not available yet for this season."
    ]


def test_missing_optional_datasets_still_render_all_tabs():
    ui = FakeUI()
    render(
        "2526",
        data_manager=FakeDataManager(),
        season_manager=FakeSeasonManager(),
        ui=ui,
    )
    assert len(ui.tab_labels) == 5
    assert any("No " in message for message in ui.infos)


def test_invalid_optional_dataset_displays_data_manager_validation_message():
    ui = FakeUI()
    result = make_result(
        "formation_weekly",
        pd.DataFrame(),
        status=DataStatus.INVALID,
        errors=("invalid formation schema",),
    )
    render(
        "2526",
        data_manager=FakeDataManager(
            results={"formation_weekly": result}
        ),
        season_manager=FakeSeasonManager(),
        ui=ui,
    )
    assert "invalid formation schema" in ui.warnings


@pytest.mark.parametrize("namespace", ["working", "snapshot"])
def test_season_manager_owns_namespace_resolution(namespace):
    data = FakeDataManager()
    seasons = FakeSeasonManager(
        namespace=namespace,
        finalized=namespace == "snapshot",
    )

    render("2526", data_manager=data, season_manager=seasons, ui=FakeUI())

    assert seasons.namespace_calls == ["2526"]
    assert {call[2] for call in data.calls} == {namespace}


def test_invalid_season_stops_before_dataset_loading():
    data = FakeDataManager()
    with pytest.raises(KeyError, match="Unknown season"):
        render(
            "bad",
            data_manager=data,
            season_manager=FakeSeasonManager(invalid=True),
            ui=FakeUI(),
        )
    assert data.calls == []


def test_regression_sections_for_overview_performance_and_decisions_exist():
    source = Path("views/managers.py").read_text(encoding="utf-8")
    required = [
        "Recent Form",
        "Weekly Scoring",
        "League Position",
        "Performance Analytics",
        "Expected",
        "Luck",
        "Optimal",
        "Bench",
        "Formation",
    ]
    assert all(label in source for label in required)


def test_regression_sections_for_squad_and_explorer_exist():
    source = Path("views/managers.py").read_text(encoding="utf-8")
    required = [
        "Contribution Leaderboard",
        "Ownership Timeline",
        "Player Detail",
        "Analysis level",
        "Gameweek range",
        "Download Results CSV",
    ]
    assert all(label in source for label in required)


def test_chart_and_table_rendering_calls_are_preserved():
    source = Path("views/managers.py").read_text(encoding="utf-8")
    assert "st.line_chart(" in source
    assert "st.bar_chart(" in source
    assert "st.plotly_chart(" in source
    assert "st.vega_lite_chart(" in source
    assert "st.dataframe(" in source


def test_page_has_no_direct_filesystem_or_pandas_reader_calls():
    source = Path("views/managers.py").read_text(encoding="utf-8")
    forbidden = [
        "Path(",
        "glob(",
        "os.path",
        "pd.read_csv",
        "pd.read_parquet",
        "pd.read_json",
    ]
    assert all(token not in source for token in forbidden)


def test_legacy_renderer_delegates_managers_only():
    source = Path("core/legacy_renderer.py").read_text(encoding="utf-8")
    branch = source.split('elif page == "Managers":', 1)[1].split(
        'elif page == "Draft HQ":',
        1,
    )[0]
    assert "render_managers(CURRENT_SEASON_ID)" in branch
    assert "load_csv_cached" not in branch
