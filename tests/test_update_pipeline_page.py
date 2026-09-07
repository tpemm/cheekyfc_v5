from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import views.update_pipeline as update_pipeline

from core.models.data_result import DataProvenance, DataResult, DataStatus
from core.models.operation_result import OperationResult
from views.update_pipeline import render


class FakeElement:
    def __init__(self, ui):
        self.ui = ui

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def metric(self, label, value, delta=None):
        self.ui.metrics.append((label, value, delta))

    def button(self, label, **kwargs):
        return self.ui.button(label, **kwargs)

    def progress(self, value, **kwargs):
        self.ui.progress_values.append((value, kwargs.get("text")))


class FakeCache:
    def __init__(self):
        self.clears = 0

    def clear(self):
        self.clears += 1


class FakeUI:
    def __init__(self, values=None, session_state=None):
        self.values = values or {}
        self.session_state = session_state or {}
        self.cache_data = FakeCache()
        self.markdowns = []
        self.writes = []
        self.successes = []
        self.errors = []
        self.warnings = []
        self.infos = []
        self.metrics = []
        self.subheaders = []
        self.codes = []
        self.text_areas = []
        self.json_values = []
        self.text_values = []
        self.buttons = []
        self.spinners = []
        self.dataframes = []
        self.progress_values = []
        self.captions = []

    def markdown(self, value, **kwargs):
        self.markdowns.append(str(value))

    def write(self, value):
        self.writes.append(str(value))

    def success(self, value):
        self.successes.append(str(value))

    def error(self, value):
        self.errors.append(str(value))

    def warning(self, value, **kwargs):
        self.warnings.append(str(value))

    def info(self, value):
        self.infos.append(str(value))

    def caption(self,value):
        self.captions.append(str(value))

    def columns(self, spec):
        count = spec if isinstance(spec, int) else len(spec)
        return [FakeElement(self) for _ in range(count)]

    def selectbox(self, label, options, index=0):
        return self.values.get(label, list(options)[index])

    def text_input(self, label, **kwargs):
        return self.values.get(label, "")

    def checkbox(self, label, value=False):
        return self.values.get(label, value)

    def button(self, label, **kwargs):
        self.buttons.append((label, kwargs))
        return self.values.get(label, False)

    def subheader(self, value):
        self.subheaders.append(str(value))

    def code(self, value, **kwargs):
        self.codes.append((str(value), kwargs))

    def spinner(self, value):
        self.spinners.append(str(value))
        return FakeElement(self)

    def text_area(self, label, value, height):
        self.text_areas.append((label, value, height))

    def expander(self, *args, **kwargs):
        return FakeElement(self)

    def json(self, value):
        self.json_values.append(value)

    def text(self, value):
        self.text_values.append(value)

    def dataframe(self, value, **kwargs):
        self.dataframes.append(value)

    def progress(self, value, **kwargs):
        self.progress_values.append((value, kwargs.get("text")))
        return FakeElement(self)


class FakeSeasonManager:
    def __init__(self, finalized=False, namespace="working", invalid=False):
        self.finalized = finalized
        self.namespace = namespace
        self.invalid = invalid

    def context(self, season_id):
        if self.invalid:
            raise KeyError(f"Unknown season ID: {season_id!r}")
        return SimpleNamespace(
            season_id=season_id,
            display_name="2026/27" if not self.finalized else "2025/26",
            finalized=self.finalized,
            mutable=not self.finalized,
        )

    def resolve_namespace(self, season_id):
        return self.namespace


class FakeDataManager:
    def __init__(self, manifest=None, validation=None):
        self.manifest = manifest
        self.validation = validation
        self.json_calls = []
        self.text_calls = []

    def load_json(self, key, season_id, namespace):
        self.json_calls.append((key, season_id, namespace))
        return result(key, self.manifest, namespace)

    def load_text(self, key, season_id, namespace, encoding, errors):
        self.text_calls.append(
            (key, season_id, namespace, encoding, errors)
        )
        return result(key, self.validation, namespace)


class FakeOperationsService:
    def __init__(self, available=True, results=None):
        self.available = available
        self.results = list(results or [])
        self.can_run_calls = []
        self.run_calls = []

    def can_run(self, operation_id, season_id):
        self.can_run_calls.append((operation_id, season_id))
        return self.available

    def run(self, operation_id, season_id, parameters):
        self.run_calls.append((operation_id, season_id, parameters))
        if self.results:
            return self.results.pop(0)
        return operation_result(operation_id)


def result(key, data, namespace):
    return DataResult(
        status=DataStatus.AVAILABLE if data is not None else DataStatus.MISSING,
        data=data,
        provenance=DataProvenance(
            dataset_key=key,
            requested_key=key,
            season_id="2526",
            namespace=namespace,
            resolved_path=Path(f"/project/{key}"),
            format="json" if isinstance(data, dict) else "txt",
            modified_time=datetime.now(timezone.utc),
            size_bytes=20,
        ),
    )


def operation_result(key, success=True, stdout="done", stderr=""):
    now = datetime.now(timezone.utc)
    return OperationResult(
        operation_key=key,
        success=success,
        started_at=now,
        finished_at=now,
        duration_seconds=0.1,
        return_code=0 if success else 1,
        message="done" if success else "failed",
        stdout=stdout,
        stderr=stderr,
    )


def test_working_page_renders_operations_center_and_quick_actions():
    ui = FakeUI()
    operations = FakeOperationsService()
    render(
        "2627",
        data_manager=FakeDataManager(),
        season_manager=FakeSeasonManager(),
        operations_service=operations,
        ui=ui,
    )
    assert "Operations Center" in "\n".join(ui.markdowns)
    assert [button[0] for button in ui.buttons] == [
        "SMART REFRESH",
            "Initialize Cup",
            "Build Cup Bracket",
            "Rebuild Cup",
            "Validate Cup",
    ]
    assert operations.run_calls == []


def test_unavailable_operations_leave_smart_planner_available():
    ui = FakeUI()
    render(
        "2627",
        data_manager=FakeDataManager(),
        season_manager=FakeSeasonManager(),
        operations_service=FakeOperationsService(available=False),
        ui=ui,
    )
    assert "disabled" not in ui.buttons[0][1]
    assert all(button[1]["disabled"] for button in ui.buttons[1:])


def test_smart_refresh_handles_desktop_required_cleanly(monkeypatch):
    ui = FakeUI(values={"SMART REFRESH": True})
    plan=SimpleNamespace(current_gw=3,previous_gw=2,current_gw_status="ACTIVE",previous_gw_status="AWAITING_STABILITY",fantrax=SimpleNamespace(status="DESKTOP_REQUIRED"),whoscored=SimpleNamespace(status="CACHE_HIT"),understat=SimpleNamespace(status="CACHE_HIT"))
    monkeypatch.setattr(update_pipeline,"run_smart_refresh",lambda operations,season:SimpleNamespace(status="DESKTOP_REQUIRED",final_plan=plan))
    operations = FakeOperationsService()
    render(
        "2627",
        data_manager=FakeDataManager(),
        season_manager=FakeSeasonManager(),
        operations_service=operations,
        ui=ui,
    )
    assert operations.run_calls == []
    assert "DESKTOP DATA REQUIRED" in ui.warnings
    assert ("python scripts/refresh_desktop_sources.py",{"language":"text"}) in ui.codes


def test_smart_refresh_completes_when_inputs_exist(monkeypatch):
    ui = FakeUI(values={"SMART REFRESH": True})
    plan=SimpleNamespace(current_gw=3,previous_gw=2,current_gw_status="COMPLETE_PENDING_CORRECTIONS",previous_gw_status="FINALIZED",fantrax=SimpleNamespace(status="CACHE_HIT"),whoscored=SimpleNamespace(status="NO_ACTION_REQUIRED"),understat=SimpleNamespace(status="CACHE_HIT"))
    monkeypatch.setattr(update_pipeline,"run_smart_refresh",lambda operations,season:SimpleNamespace(status="PASS",final_plan=plan))
    operations = FakeOperationsService()
    render(
        "2627",
        data_manager=FakeDataManager(),
        season_manager=FakeSeasonManager(),
        operations_service=operations,
        ui=ui,
    )
    assert ui.successes == ["REFRESH COMPLETE"]
    assert ui.cache_data.clears == 1


def test_running_state_prevents_duplicate_execution():
    ui = FakeUI(
        values={"SMART REFRESH": True},
        session_state={"_operation_running_smart_refresh": True},
    )
    operations = FakeOperationsService()
    render(
        "2627",
        data_manager=FakeDataManager(),
        season_manager=FakeSeasonManager(),
        operations_service=operations,
        ui=ui,
    )
    assert operations.run_calls == []
    assert "This operation is already running." in ui.warnings


def test_finalized_season_renders_status_artifacts_without_operations():
    ui = FakeUI()
    data = FakeDataManager(
        manifest={"season_id": "2526"},
        validation="validation passed",
    )
    operations = FakeOperationsService()
    render(
        "2526",
        data_manager=data,
        season_manager=FakeSeasonManager(
            finalized=True,
            namespace="snapshot",
        ),
        operations_service=operations,
        ui=ui,
    )
    assert ui.successes == [
        "2025/26 is finalized and protected from live API refreshes."
    ]
    assert ui.json_values == [{"season_id": "2526"}]
    assert ui.text_values == ["validation passed"]
    assert operations.can_run_calls == []
    assert operations.run_calls == []


def test_missing_finalized_artifacts_are_optional():
    ui = FakeUI()
    render(
        "2526",
        data_manager=FakeDataManager(),
        season_manager=FakeSeasonManager(
            finalized=True,
            namespace="snapshot",
        ),
        operations_service=FakeOperationsService(),
        ui=ui,
    )
    assert ui.json_values == []
    assert ui.text_values == []


def test_invalid_season_stops_before_services_are_used():
    operations = FakeOperationsService()
    with pytest.raises(KeyError, match="Unknown season"):
        render(
            "bad",
            data_manager=FakeDataManager(),
            season_manager=FakeSeasonManager(invalid=True),
            operations_service=operations,
            ui=FakeUI(),
        )
    assert operations.can_run_calls == []


def test_page_has_no_direct_execution_or_filesystem_orchestration():
    source = Path("views/update_pipeline.py").read_text(encoding="utf-8")
    forbidden = [
        "Path(",
        "pathlib",
        "glob(",
        "os.path",
        "os.chdir",
        "os.environ",
        "os.listdir",
        "os.scandir",
        "subprocess",
        "runpy",
        "system(",
        "Popen(",
        "pd.read_csv",
        "pd.read_parquet",
        "pd.read_json",
        "refresh_all_fantrax_data",
        "build_league_awards_views",
    ]
    assert all(token not in source for token in forbidden)
    assert "rosters_by_week.csv" not in source


def test_legacy_renderer_delegates_update_pipeline():
    source = Path("core/legacy_renderer.py").read_text(encoding="utf-8")
    branch = source.split('elif page == "Operations Center":', 1)[1].split(
        'elif page == "Raw Data Browser":',
        1,
    )[0]
    assert "render_update_pipeline(CURRENT_SEASON_ID)" in branch
    assert "run_refresh" not in branch
