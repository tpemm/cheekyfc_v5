from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from core.models.data_result import DataProvenance, DataResult, DataStatus
from views.awards import DATASET_KEYS, render


class StopSignal(RuntimeError):
    pass


class FakeColumn:
    def __init__(self, ui):
        self.ui = ui

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def metric(self, label, value, delta=None):
        self.ui.metrics.append((label, value, delta))


class FakeUI:
    def __init__(self, selections=None, session_state=None):
        self.selections = selections or {}
        self.session_state = session_state or {}
        self.markdowns = []
        self.infos = []
        self.warnings = []
        self.successes = []
        self.captions = []
        self.codes = []
        self.writes = []
        self.subheaders = []
        self.tables = []
        self.metrics = []
        self.select_calls = []

    def markdown(self, value, **kwargs):
        self.markdowns.append(str(value))

    def info(self, value):
        self.infos.append(str(value))

    def warning(self, value):
        self.warnings.append(str(value))

    def success(self, value):
        self.successes.append(str(value))

    def caption(self, value):
        self.captions.append(str(value))

    def code(self, value, **kwargs):
        self.codes.append(str(value))

    def write(self, value):
        self.writes.append(str(value))

    def subheader(self, value):
        self.subheaders.append(str(value))

    def divider(self):
        return None

    def columns(self, spec):
        count = spec if isinstance(spec, int) else len(spec)
        return [FakeColumn(self) for _ in range(count)]

    def selectbox(self, label, options, **kwargs):
        values = list(options)
        self.select_calls.append((label, values, kwargs))
        key = kwargs.get("key")
        if label in self.selections:
            value = self.selections[label]
        elif key and key in self.session_state:
            value = self.session_state[key]
        else:
            value = values[0]
        if key:
            self.session_state[key] = value
        return value

    def metric(self, label, value, delta=None):
        self.metrics.append((label, value, delta))

    def dataframe(self, data, **kwargs):
        self.tables.append((data.copy(), kwargs))

    def stop(self):
        raise StopSignal()


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
            finalized=self.finalized,
        )

    def resolve_namespace(self, season_id):
        self.namespace_calls.append(season_id)
        return self.namespace


class FakeDataManager:
    def __init__(self, frames=None, results=None):
        self.frames = award_frames()
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


def award_frames():
    leaderboards = pd.DataFrame(
        {
            "award_name": ["Golden Boot"] * 3 + ["Jester"],
            "rank": [3, 1, 2, 1],
            "api_team_name": ["Third FC", "First FC", "Second FC", "Third FC"],
            "leaderboard_value": [7, 12, 9, 3],
            "leaderboard_value_label": ["goals"] * 3 + ["wins"],
            "season_total": [7, 12, 9, 3],
            "season_avg": [0.7, 1.2, 0.9, 0.3],
            "weekly_award_wins": [1, 2, 1, 3],
            "season_avg_starter_points": [70, 90, 80, 60],
        }
    )
    weekly = pd.DataFrame(
        {
            "fantrax_gw": [1, 3, 2, 2],
            "award_name": [
                "Golden Boot",
                "Golden Boot",
                "Golden Boot",
                "Jester",
            ],
            "api_team_name": [
                "Third FC",
                "First FC",
                "Second FC",
                "Third FC",
            ],
            "metric_value": [1, 3, 2, 40],
            "winner_count_for_week": [1, 1, 1, 1],
        }
    )
    return {
        "weekly_awards": weekly,
        "award_leaderboards": leaderboards,
        "manager_streaks": pd.DataFrame(),
        "closest_games": pd.DataFrame(),
        "biggest_blowouts": pd.DataFrame(),
    }


def test_valid_awards_render_all_existing_sections_and_service_calls():
    ui = FakeUI(selections={"Choose award": "Golden Boot"})
    data = FakeDataManager()

    render(
        "2526",
        data_manager=data,
        season_manager=FakeSeasonManager(),
        ui=ui,
    )

    assert [call[0] for call in data.calls] == list(DATASET_KEYS)
    assert ui.subheaders == [
        "Season Leaderboard",
        "Podium",
        "Weekly Award Winners",
        "Manager History",
    ]
    assert len(ui.tables) == 3
    assert len(ui.metrics) == 7


def test_missing_optional_record_datasets_do_not_block_awards():
    ui = FakeUI(selections={"Choose award": "Golden Boot"})
    render(
        "2526",
        data_manager=FakeDataManager(),
        season_manager=FakeSeasonManager(),
        ui=ui,
    )
    assert "Season Leaderboard" in ui.subheaders


@pytest.mark.parametrize("required_key", ["weekly_awards", "award_leaderboards"])
def test_missing_required_award_dataset_preserves_empty_state(required_key):
    ui = FakeUI()
    result = make_result(required_key, None, status=DataStatus.MISSING)

    with pytest.raises(StopSignal):
        render(
            "2526",
            data_manager=FakeDataManager(results={required_key: result}),
            season_manager=FakeSeasonManager(),
            ui=ui,
        )

    assert ui.infos == ["No award data found."]


def test_invalid_optional_dataset_displays_validation_message():
    ui = FakeUI(selections={"Choose award": "Golden Boot"})
    result = make_result(
        "manager_streaks",
        pd.DataFrame(),
        status=DataStatus.INVALID,
        errors=("invalid streak schema",),
    )
    render(
        "2526",
        data_manager=FakeDataManager(results={"manager_streaks": result}),
        season_manager=FakeSeasonManager(),
        ui=ui,
    )
    assert "invalid streak schema" in ui.warnings


@pytest.mark.parametrize("namespace", ["working", "snapshot"])
def test_season_manager_owns_namespace_resolution(namespace):
    data = FakeDataManager()
    seasons = FakeSeasonManager(
        namespace=namespace,
        finalized=namespace == "snapshot",
    )
    render(
        "2526",
        data_manager=data,
        season_manager=seasons,
        ui=FakeUI(selections={"Choose award": "Golden Boot"}),
    )
    assert seasons.namespace_calls == ["2526"]
    assert {call[2] for call in data.calls} == {namespace}


def test_invalid_season_stops_before_data_loading():
    data = FakeDataManager()
    with pytest.raises(KeyError, match="Unknown season"):
        render(
            "bad",
            data_manager=data,
            season_manager=FakeSeasonManager(invalid=True),
            ui=FakeUI(),
        )
    assert data.calls == []


def test_leaderboard_and_weekly_history_preserve_sort_order():
    ui = FakeUI(selections={"Choose award": "Golden Boot"})
    render(
        "2526",
        data_manager=FakeDataManager(),
        season_manager=FakeSeasonManager(),
        ui=ui,
    )

    assert ui.tables[0][0]["Manager"].tolist() == [
        "First FC",
        "Second FC",
        "Third FC",
    ]
    assert ui.tables[1][0]["GW"].tolist() == [3, 2, 1]


def test_pending_award_navigation_is_preserved():
    ui = FakeUI(session_state={"pending_award": "Jester"})
    render(
        "2526",
        data_manager=FakeDataManager(),
        season_manager=FakeSeasonManager(),
        ui=ui,
    )
    assert ui.session_state["award_detail_selection"] == "Jester"
    assert any("Jester is ranked" in message for message in ui.warnings)


def test_manager_history_filters_selected_manager():
    ui = FakeUI(
        selections={
            "Choose award": "Golden Boot",
            "Manager": "Second FC",
        }
    )
    render(
        "2526",
        data_manager=FakeDataManager(),
        season_manager=FakeSeasonManager(),
        ui=ui,
    )
    assert ui.tables[-1][0]["api_team_name"].eq("Second FC").all()


def test_page_has_no_direct_filesystem_or_pandas_reader_calls():
    source = Path("views/awards.py").read_text(encoding="utf-8")
    forbidden = [
        "Path(",
        "glob(",
        "os.path",
        "pd.read_csv",
        "pd.read_parquet",
        "pd.read_json",
    ]
    assert all(token not in source for token in forbidden)


def test_legacy_renderer_delegates_award_detail():
    source = Path("core/legacy_renderer.py").read_text(encoding="utf-8")
    branch = source.split('elif page == "Award Detail":', 1)[1].split(
        'elif page == "Managers":',
        1,
    )[0]
    assert "render_awards(CURRENT_SEASON_ID)" in branch
    assert "load_csv_cached" not in branch
