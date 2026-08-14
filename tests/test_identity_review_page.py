from pathlib import Path
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
import pandas as pd
from streamlit.testing.v1 import AppTest
from core.models.data_result import DataStatus

from views.identity_review import (
    OPERATION_LOCK_KEY,
    PENDING_STATUS_FILTER_KEY,
    _apply_pending_status_filter,
    _refresh_review_data,
    _run,
    _save_decision_and_refresh,
)


class _RefreshUI:
    def __init__(self):
        self.session_state = {}
        self.successes = []
        self.errors = []
        self.rerun_called = False

    def spinner(self, _label):
        return nullcontext()

    def success(self, message):
        self.successes.append(message)

    def error(self, message):
        self.errors.append(message)

    def rerun(self):
        self.rerun_called = True


class _RefreshData:
    def __init__(self, decision="Ignored", fantrax_id="123", fpl_id="456"):
        self.invalidations = []
        self.decision = decision
        self.fantrax_id = fantrax_id
        self.fpl_id = fpl_id

    def invalidate(self, dataset_key, season_id):
        self.invalidations.append((dataset_key, season_id))

    def load_frame(self, dataset_key, season_id, namespace):
        if dataset_key == "player_alias_overrides":
            data = pd.DataFrame(
                columns=[
                    "historical_fantrax_player_id",
                    "current_fpl_player_id",
                    "decision",
                ]
            )
            if self.decision != "Clear":
                data.loc[0] = [self.fantrax_id, self.fpl_id, self.decision]
        else:
            status = "Unreviewed" if self.decision == "Clear" else self.decision
            data = pd.DataFrame({
                "fantrax_player_id": [self.fantrax_id],
                "current_candidate_fpl_id": [self.fpl_id],
                "review_status": [status],
            })
        return SimpleNamespace(status=DataStatus.AVAILABLE, data=data)


class _RefreshOperations:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def run(self, operation, season_id, parameters):
        self.calls.append((operation, season_id, parameters))
        success = self.results.pop(0)
        return SimpleNamespace(
            success=success,
            message="Operation completed.",
            display_log=lambda: "operation failed",
        )


def test_identity_review_page_renders_registered_workflow():
    at = AppTest.from_file("app.py", default_timeout=30).run()
    at.selectbox[0].select("2026/27").run()
    next(item for item in at.radio if item.label == "Page").set_value(
        "Identity Review"
    ).run()
    assert not at.exception
    assert {
        "Unresolved", "Historical Only", "High confidence",
        "Medium confidence", "No safe candidate", "Approved aliases", "Ignored",
        "Unreviewed queue",
    }.issubset({item.label for item in at.metric})
    assert {
        "Review status", "Registry status", "Candidate confidence",
        "Team", "Position", "Match method",
    }.issubset({item.label for item in at.multiselect})
    assert len(at.dataframe) == 1
    assert {
        "Approve Alias", "Ignore Suggestion", "Clear Review Decision",
        "Generate Identity Review", "Build Player Registry",
        "Validate Player Registry", "Generate Registry Reports",
        "Build Draft Outputs",
    }.issubset({item.label for item in at.button})


def test_identity_review_page_has_no_file_or_builder_access():
    source = Path("views/identity_review.py").read_text(encoding="utf-8")
    assert "operations.run(" in source
    assert "pd.read_" not in source
    assert ".to_csv(" not in source
    assert "analytics.player_registry" not in source


def test_successful_review_refresh_invalidates_registered_data_and_reruns():
    ui = _RefreshUI()
    data = _RefreshData()
    operations = _RefreshOperations(True)
    refreshed = _refresh_review_data(
        ui, data, operations, "2627", "Decision saved."
    )
    assert refreshed
    assert operations.calls == [
        ("generate_identity_review", "2627", {})
    ]
    assert data.invalidations == [
        ("player_identity_review", "2627"),
        ("player_alias_overrides", "2627"),
    ]
    assert ui.session_state["_identity_review_notice"] == "Decision saved."
    assert ui.rerun_called


def test_failed_review_refresh_does_not_invalidate_or_rerun():
    ui = _RefreshUI()
    data = _RefreshData()
    operations = _RefreshOperations(False)
    refreshed = _refresh_review_data(
        ui, data, operations, "2627", "Decision saved."
    )
    assert not refreshed
    assert data.invalidations == []
    assert not ui.rerun_called
    assert ui.errors == [
        "The operation did not complete. Expand technical details for diagnostics."
    ]


@pytest.mark.parametrize(
    ("decision", "expected_status"),
    [
        ("Approved", "Approved"),
        ("Ignored", "Ignored"),
        ("Clear", "Unreviewed"),
    ],
)
def test_successful_decision_actions_save_regenerate_invalidate_and_rerun(
    decision, expected_status
):
    ui = _RefreshUI()
    ui.session_state["_identity_review_selected_pair"] = ("123", "456")
    data = _RefreshData(decision)
    operations = _RefreshOperations(True, True)
    parameters = {
        "season_id": "2627",
        "fantrax_player_id": 123,
        "current_fpl_player_id": 456,
        "decision": decision,
        "review_note": "",
        "acknowledge_transfer": False,
    }
    refreshed = _save_decision_and_refresh(
        ui, data, operations, "2627", parameters
    )
    assert refreshed
    assert operations.calls == [
        ("save_identity_review_decision", "2627", parameters),
    ]
    assert data.invalidations == [
        ("player_identity_review", "2627"),
        ("player_alias_overrides", "2627"),
    ]
    assert expected_status in ui.session_state["_identity_review_notice"]
    assert ui.session_state["_identity_review_notice"].startswith("Verified ·")
    assert "_identity_review_selected_pair" not in ui.session_state
    assert ui.rerun_called


def test_failed_decision_save_does_not_regenerate_or_false_update_ui():
    ui = _RefreshUI()
    data = _RefreshData()
    operations = _RefreshOperations(False)
    refreshed = _save_decision_and_refresh(
        ui,
        data,
        operations,
        "2627",
        {
            "season_id": "2627",
            "fantrax_player_id": 123,
            "current_fpl_player_id": 456,
            "decision": "Approved",
        },
    )
    assert not refreshed
    assert len(operations.calls) == 1
    assert data.invalidations == []
    assert not ui.rerun_called
    assert "_identity_review_notice" not in ui.session_state


def test_operation_lock_clears_after_success_and_failure():
    for succeeds in (True, False):
        ui = _RefreshUI()
        result = _run(
            ui, _RefreshOperations(succeeds), "generate_identity_review", "2627"
        )
        assert result.success is succeeds
        assert OPERATION_LOCK_KEY not in ui.session_state


def test_second_identity_operation_is_blocked():
    ui = _RefreshUI()
    ui.session_state[OPERATION_LOCK_KEY] = "save_identity_review_decision"
    operations = _RefreshOperations(True)
    result = _run(ui, operations, "generate_identity_review", "2627")
    assert not result.success
    assert operations.calls == []
    assert "already running" in ui.errors[0]


@pytest.mark.parametrize("decision", ["Approved", "Ignored", "Clear"])
def test_decision_uses_pending_filter_without_mutating_instantiated_widget(
    decision,
):
    ui = _RefreshUI()
    ui.session_state["identity_review_status_filter"] = ["Unreviewed"]
    operations = _RefreshOperations(True)
    result = _save_decision_and_refresh(
        ui,
        _RefreshData(decision, "fx1", "1"),
        operations,
        "2627",
        {
            "season_id": "2627",
            "fantrax_player_id": "fx1",
            "current_fpl_player_id": "1",
            "decision": decision,
        },
    )
    assert result
    assert ui.session_state["identity_review_status_filter"] == ["Unreviewed"]
    assert ui.session_state[PENDING_STATUS_FILTER_KEY] == ["Unreviewed"]


def test_pending_filter_applies_before_widget_and_is_removed():
    ui = _RefreshUI()
    ui.session_state[PENDING_STATUS_FILTER_KEY] = ["Ignored"]
    _apply_pending_status_filter(ui)
    assert ui.session_state["identity_review_status_filter"] == ["Ignored"]
    assert PENDING_STATUS_FILTER_KEY not in ui.session_state


def test_status_widget_has_session_initialization_without_default_argument():
    source = Path("views/identity_review.py").read_text(encoding="utf-8")
    widget = source.split('status = filter_columns[0].multiselect(', 1)[1].split(')', 1)[0]
    assert 'key="identity_review_status_filter"' in widget
    assert "default=" not in widget


def test_success_is_not_shown_when_authoritative_projection_verification_fails():
    ui = _RefreshUI()
    data = _RefreshData("Ignored", "different", "999")
    result = _save_decision_and_refresh(
        ui,
        data,
        _RefreshOperations(True),
        "2627",
        {
            "season_id": "2627",
            "fantrax_player_id": "fx1",
            "current_fpl_player_id": "1",
            "decision": "Ignored",
        },
    )
    assert not result
    assert ui.errors == ["The saved decision could not be verified."]
    assert not ui.rerun_called
