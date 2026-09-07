from pathlib import Path
from datetime import date, datetime, timezone
import json
import shutil
from types import SimpleNamespace
import uuid

import numpy as np
import pandas as pd
import pytest

from core.services.operations_service import (
    DEFAULT_OPERATIONS,
    OperationNotAllowedError,
    OperationParameterError,
    OperationsService,
    OperationsServiceError,
    UnknownOperationError,
    _RegisteredOperation,
    _to_json_safe,
)
from core.services.season_manager import SeasonManager


SEASONS = {
    "active": {
        "label": "Active",
        "status": "active",
        "enabled": True,
        "data_ready": True,
    },
    "historic": {
        "label": "Historic",
        "status": "finalized",
        "enabled": True,
        "data_ready": True,
    },
}


class RecordingExecutor:
    def __init__(self, returncode=0, stdout="done", stderr="", error=None):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.error = error
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if self.error:
            raise self.error
        return SimpleNamespace(
            returncode=self.returncode,
            stdout=self.stdout,
            stderr=self.stderr,
        )


@pytest.fixture
def project_path():
    path = Path.cwd() / ".test_artifacts" / f"operations_{uuid.uuid4().hex}"
    path.mkdir(parents=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def seasons(project_path):
    return SeasonManager(
        definitions=SEASONS,
        default_season_id="active",
        project_root=project_path,
    )


def service(project_path, seasons, executor=None):
    return OperationsService(
        season_manager=seasons,
        project_root=project_path,
        executor=executor or RecordingExecutor(),
    )


def test_subprocess_receives_inherited_environment(project_path, seasons, monkeypatch):
    monkeypatch.setenv("FANTRAX_LEAGUE_ID_2627", "new-league")
    executor=RecordingExecutor(stdout="REFRESH_CONTEXT season_id=active league_id=new-league")
    service(project_path,seasons,executor).run("refresh_live_fantrax_sources","active")
    assert executor.calls[0][1]["env"]["FANTRAX_LEAGUE_ID_2627"]=="new-league"


def test_2627_refresh_subprocess_receives_local_streamlit_secret(project_path,monkeypatch):
    monkeypatch.delenv("FANTRAX_LEAGUE_ID_2627",raising=False)
    secret=project_path/".streamlit"/"secrets.toml";secret.parent.mkdir(parents=True)
    secret.write_text('FANTRAX_LEAGUE_ID_2627 = "local-current-league"\n',encoding="utf-8")
    manager=SeasonManager(definitions={"2627":{"label":"2026/27","status":"active","enabled":True,"data_ready":True}},default_season_id="2627",project_root=project_path)
    executor=RecordingExecutor(stdout="REFRESH_CONTEXT season_id=2627 league_id=local-current-league")
    OperationsService(season_manager=manager,project_root=project_path,executor=executor).run("refresh_live_standings","2627")
    assert executor.calls[0][1]["env"]["FANTRAX_LEAGUE_ID_2627"]=="local-current-league"


def test_failed_stage_context_and_streams_are_retained(project_path,seasons):
    executor=RecordingExecutor(returncode=1,stdout="REFRESH_CONTEXT season_id=active league_id=league-x",stderr="REFRESH_FAILURE stage=getStandings exception_type=HTTPError message=Forbidden")
    result=service(project_path,seasons,executor).run("refresh_live_fantrax_sources","active")
    assert not result.success and result.failed_stage=="getStandings"
    assert result.resolved_league_id=="league-x" and result.season_id=="active"
    assert result.error_type=="HTTPError" and result.exception_message=="Forbidden"
    assert "REFRESH_CONTEXT" in result.stdout and "REFRESH_FAILURE" in result.stderr
    assert result.command and "refresh_live_fantrax.py" in result.command


def test_known_operations_are_listed_with_public_metadata(project_path, seasons):
    operations = service(project_path, seasons)
    definitions = operations.list_operations()
    assert [item.key for item in definitions] == [
        "initialize_cup",
        "build_cup_bracket",
        "rebuild_cup",
        "validate_cup",
            "refresh_live_fantrax_sources",
            "backfill_live_weekly_stats",
            "force_refresh_live_weekly_stats",
            "refresh_live_league_metadata",
        "refresh_live_standings",
            "refresh_live_rosters",
            "build_live_season_datasets",
            "rebuild_current_cached_products",
            "build_roster_tracking",
        "validate_roster_ownership",
        "refresh_fantrax_data",
        "build_league_analytics",
        "refresh_current_squad",
        "build_player_registry",
        "validate_player_registry",
        "generate_registry_reports",
        "generate_identity_review",
        "save_identity_review_decision",
        "build_draft_outputs",
        "build_draft_grades",
    ]
    assert operations.inspect_operation("refresh_fantrax_data").label == (
        "Run refresh"
    )
    assert [item.key for item in operations.list_operations("active")] == [
        "initialize_cup",
        "build_cup_bracket",
        "rebuild_cup",
        "validate_cup",
            "refresh_live_fantrax_sources",
            "backfill_live_weekly_stats",
            "force_refresh_live_weekly_stats",
            "refresh_live_league_metadata",
        "refresh_live_standings",
            "refresh_live_rosters",
            "build_live_season_datasets",
            "rebuild_current_cached_products",
            "build_roster_tracking",
        "validate_roster_ownership",
        "refresh_fantrax_data",
        "build_league_analytics",
        "refresh_current_squad",
        "build_player_registry",
        "validate_player_registry",
        "generate_registry_reports",
        "generate_identity_review",
        "save_identity_review_decision",
        "build_draft_outputs",
        "build_draft_grades",
    ]
    assert operations.list_operations("historic") == ()


def test_unknown_operation_is_rejected(project_path, seasons):
    with pytest.raises(UnknownOperationError, match="Unknown operation ID"):
        service(project_path, seasons).run("arbitrary_command", "active")


def test_identity_review_decision_uses_validated_json_stdin(
    project_path, seasons
):
    executor = RecordingExecutor()
    parameters = {
        "season_id": "active",
        "fantrax_player_id": "fx1",
        "current_fpl_player_id": "121",
        "decision": "Ignored",
        "review_note": "Not the same player",
        "acknowledge_transfer": False,
    }
    result = service(project_path, seasons, executor).run(
        "save_identity_review_decision", "active", parameters
    )
    _, kwargs = executor.calls[0]
    assert result.success
    assert '"decision": "Ignored"' in kwargs["input"]
    assert '"fantrax_player_id": "fx1"' in kwargs["input"]
    assert kwargs["timeout"] == 180.0


def test_identity_review_decision_rejects_missing_or_unknown_values(
    project_path, seasons
):
    operations = service(project_path, seasons)
    with pytest.raises(OperationParameterError, match="Missing"):
        operations.run(
            "save_identity_review_decision",
            "active",
            {"decision": "Approved"},
        )
    with pytest.raises(OperationParameterError, match="Unsupported"):
        operations.run(
            "save_identity_review_decision",
            "active",
            {
                "season_id": "active",
                "fantrax_player_id": "fx1",
                "current_fpl_player_id": "121",
                "decision": "Maybe",
            },
        )


def test_json_normalizer_preserves_types_and_missing_semantics():
    timestamp = pd.Timestamp("2026-07-29 12:34:56", tz="UTC")
    moment = datetime(2026, 7, 29, 12, 34, tzinfo=timezone.utc)
    calendar_date = date(2026, 7, 29)
    value = {
        "integer": np.int64(452),
        "floating": np.float64(12.5),
        "boolean": np.bool_(True),
        "timestamp": timestamp,
        "datetime": moment,
        "date": calendar_date,
        "path": Path("data/reference"),
        "pandas_missing": pd.NA,
        "numpy_missing": np.nan,
        "nested": {
            "items": [np.int32(7), np.float32(2.5), np.bool_(False)],
        },
        "ordinary": {"text": "unchanged", "integer": 3, "none": None},
    }
    safe = _to_json_safe(value)
    encoded = json.dumps(safe, allow_nan=False)
    decoded = json.loads(encoded)
    assert decoded["integer"] == 452
    assert isinstance(decoded["integer"], int)
    assert decoded["floating"] == 12.5
    assert decoded["boolean"] is True
    assert decoded["timestamp"] == timestamp.isoformat()
    assert decoded["datetime"] == moment.isoformat()
    assert decoded["date"] == calendar_date.isoformat()
    assert decoded["path"] == str(Path("data/reference"))
    assert decoded["pandas_missing"] is None
    assert decoded["numpy_missing"] is None
    assert decoded["nested"]["items"] == [7, 2.5, False]
    assert decoded["ordinary"] == {
        "text": "unchanged", "integer": 3, "none": None,
    }


@pytest.mark.parametrize("decision", ["Approved", "Ignored", "Clear"])
def test_identity_actions_accept_dataframe_derived_scalars(
    project_path, seasons, decision
):
    row = pd.DataFrame(
        {
            "fantrax_player_id": np.array([123], dtype=np.int64),
            "current_fpl_player_id": np.array([121], dtype=np.int64),
            "acknowledge_transfer": np.array([False], dtype=np.bool_),
        }
    ).iloc[0]
    executor = RecordingExecutor()
    result = service(project_path, seasons, executor).run(
        "save_identity_review_decision",
        "active",
        {
            "season_id": "active",
            "fantrax_player_id": row["fantrax_player_id"],
            "current_fpl_player_id": row["current_fpl_player_id"],
            "decision": decision,
            "review_note": pd.NA,
            "acknowledge_transfer": row["acknowledge_transfer"],
        },
    )
    payload = json.loads(executor.calls[0][1]["input"])
    assert result.success
    assert payload["fantrax_player_id"] == 123
    assert payload["current_fpl_player_id"] == 121
    assert payload["acknowledge_transfer"] is False
    assert payload["review_note"] is None


def test_duplicate_operation_ids_are_rejected(project_path, seasons):
    duplicate = (
        DEFAULT_OPERATIONS[0],
        _RegisteredOperation(
            definition=DEFAULT_OPERATIONS[0].definition,
            script_relative_path="different.py",
            input_builder=lambda parameters: None,
        ),
    )
    with pytest.raises(OperationsServiceError, match="Duplicate operation"):
        OperationsService(
            season_manager=seasons,
            project_root=project_path,
            operations=duplicate,
        )


@pytest.mark.parametrize(
    ("parameters", "expected_input"),
    [
        ({"mode": "AUTO"}, "AUTO\n"),
        ({"mode": "REBUILD"}, "REBUILD\n"),
        ({"mode": "SPECIFIC", "specific_weeks": "34-36"}, "SPECIFIC\n34-36\n"),
        ({"mode": "FULL"}, "FULL\nAUTO\n"),
    ],
)
def test_refresh_parameters_produce_approved_stdin(
    project_path,
    seasons,
    parameters,
    expected_input,
):
    executor = RecordingExecutor()
    result = service(project_path, seasons, executor).run(
        "refresh_fantrax_data",
        "active",
        parameters,
    )
    command, kwargs = executor.calls[0]
    assert result.success
    assert kwargs["input"] == expected_input
    assert kwargs["shell"] is False
    assert isinstance(command, list)
    assert command[1].endswith("refresh_all_fantrax_data.py")


@pytest.mark.parametrize(
    "parameters",
    [
        {"mode": "UNKNOWN"},
        {"mode": "SPECIFIC", "specific_weeks": "../34"},
        {"mode": "AUTO", "specific_weeks": "34"},
        {"mode": "AUTO", "command": "whoami"},
    ],
)
def test_invalid_or_unsafe_parameters_are_rejected(
    project_path,
    seasons,
    parameters,
):
    with pytest.raises(OperationParameterError):
        service(project_path, seasons).run(
            "refresh_fantrax_data",
            "active",
            parameters,
        )


def test_build_operation_rejects_parameters(project_path, seasons):
    with pytest.raises(OperationParameterError, match="Unknown parameters"):
        service(project_path, seasons).run(
            "build_league_analytics",
            "active",
            {"script_path": "unsafe.py"},
        )


def test_finalized_namespace_rejects_execution(project_path, seasons):
    operations = service(project_path, seasons)
    assert not operations.can_run("refresh_fantrax_data", "historic")
    with pytest.raises(OperationNotAllowedError, match="immutable"):
        operations.run("refresh_fantrax_data", "historic", {"mode": "AUTO"})


def test_success_and_failure_results_capture_output(project_path, seasons):
    success_executor = RecordingExecutor(stdout="all good")
    failure_executor = RecordingExecutor(
        returncode=2,
        stdout="partial",
        stderr="failed",
    )
    success = service(project_path, seasons, success_executor).run(
        "build_league_analytics",
        "active",
    )
    failure = service(project_path, seasons, failure_executor).run(
        "build_league_analytics",
        "active",
    )
    assert success.success and success.return_code == 0
    assert success.stdout == "all good"
    assert not failure.success and failure.return_code == 2
    assert failure.stderr == "failed"
    assert "Exit code: 2" in failure.display_log()


def test_executor_exception_becomes_structured_result(project_path, seasons):
    executor = RecordingExecutor(error=RuntimeError("boom"))
    result = service(project_path, seasons, executor).run(
        "build_league_analytics",
        "active",
    )
    assert not result.success
    assert result.return_code is None
    assert result.error_type == "RuntimeError"
    assert result.exception_message == "boom"


def test_service_contains_no_shell_true_or_arbitrary_command_api():
    source = Path("core/services/operations_service.py").read_text(
        encoding="utf-8"
    )
    assert "shell=True" not in source
    assert "command:" not in source
    assert "script_path:" not in source
