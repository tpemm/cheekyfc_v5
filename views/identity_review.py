"""Administrative Player Identity Review dashboard."""

from __future__ import annotations

import re
from typing import Any

import pandas as pd
import streamlit as st

from core.models.data_result import DataStatus
from core.models.operation_result import OperationResult
from core.services.data_manager import DataManager
from core.services.operations_service import OperationsService
from core.services.season_manager import SeasonManager


DATASET_KEYS = (
    "player_identity_review", "player_alias_overrides", "player_registry",
    "player_registry_quality", "player_registry_unresolved",
    "current_squad_snapshot", "draft_rankings", "draft_player_pool",
)
OPERATION_LOCK_KEY = "_identity_review_operation"
PENDING_STATUS_FILTER_KEY = "identity_review_pending_status_filter"
EXPECTED_OPERATION_ERRORS = (
    "transfer aliases require explicit acknowledgement",
    "invalid candidate pair",
    "decision not found",
    "missing required",
)


def _operation_error_message(result: OperationResult) -> str:
    combined = "\n".join(
        str(value or "")
        for value in (
            getattr(result, "exception_message", ""),
            getattr(result, "stderr", ""),
            getattr(result, "stdout", ""),
        )
    )
    lowered = combined.casefold()
    for expected in EXPECTED_OPERATION_ERRORS:
        if expected in lowered:
            return expected[0].upper() + expected[1:] + "."
    if getattr(result, "error_type", "") == "TimeoutExpired":
        return (
            "The operation exceeded the 3-minute safety timeout. It was stopped; "
            "no success was recorded. Review the technical details and try again."
        )
    return "The operation did not complete. Expand technical details for diagnostics."


def _apply_pending_status_filter(ui: Any) -> None:
    """Apply widget state only before the widget is instantiated."""
    pending = ui.session_state.pop(PENDING_STATUS_FILTER_KEY, None)
    if pending is not None:
        ui.session_state["identity_review_status_filter"] = list(pending)
    elif "identity_review_status_filter" not in ui.session_state:
        ui.session_state["identity_review_status_filter"] = [
            "Unreviewed", "Approved", "Ignored"
        ]


def _verify_decision_projection(
    data: DataManager,
    season_id: str,
    parameters: dict[str, Any],
) -> tuple[bool, str]:
    """Reload both authoritative artifacts and verify the requested pair."""
    decisions = _load_optional(data, "player_alias_overrides", season_id, "working")
    review = _load_optional(data, "player_identity_review", season_id, "working")
    fantrax_id = re.sub(
        r"[^a-z0-9]", "",
        str(parameters.get("fantrax_player_id", "")).casefold(),
    )
    fpl_id = str(parameters.get("current_fpl_player_id", "")).removesuffix(".0")
    decision = str(parameters.get("decision", ""))
    decision_mask = (
        decisions.get(
            "historical_fantrax_player_id",
            pd.Series("", index=decisions.index),
        ).astype(str).str.casefold().str.replace(r"[^a-z0-9]", "", regex=True).eq(
            fantrax_id
        )
        & decisions.get(
            "current_fpl_player_id", pd.Series("", index=decisions.index)
        ).astype(str).str.removesuffix(".0").eq(fpl_id)
    )
    review_mask = (
        review.get(
            "fantrax_player_id", pd.Series("", index=review.index)
        ).astype(str).str.casefold().str.replace(r"[^a-z0-9]", "", regex=True).eq(
            fantrax_id
        )
        & review.get(
            "current_candidate_fpl_id", pd.Series("", index=review.index)
        ).astype(str).str.removesuffix(".0").eq(fpl_id)
    )
    expected_review = "Unreviewed" if decision == "Clear" else decision
    decision_ok = not decision_mask.any() if decision == "Clear" else bool(
        decision_mask.any()
        and decisions.loc[decision_mask, "decision"].eq(decision).any()
    )
    review_ok = bool(
        review_mask.any()
        and review.loc[review_mask, "review_status"].eq(expected_review).any()
    )
    if not decision_ok:
        return False, "The saved decision could not be verified."
    if not review_ok:
        return False, "The Identity Review artifact is not synchronized."
    return True, ""


def _load_optional(
    data: DataManager, key: str, season_id: str, namespace: str
) -> pd.DataFrame:
    result = data.load_frame(key, season_id, namespace)
    if result.status in {DataStatus.MISSING, DataStatus.EMPTY}:
        return pd.DataFrame()
    return result.data.copy()


def _run(
    ui: Any,
    operations: OperationsService,
    operation: str,
    season_id: str,
    parameters: dict[str, Any] | None = None,
    *,
    show_success: bool = True,
) -> OperationResult:
    if ui.session_state.get(OPERATION_LOCK_KEY):
        ui.error(
            f"Another Identity Review operation is already running: "
            f"{ui.session_state[OPERATION_LOCK_KEY]}."
        )
        return OperationResult(
            operation_key=operation, success=False,
            started_at=pd.Timestamp.now(tz="UTC").to_pydatetime(),
            finished_at=pd.Timestamp.now(tz="UTC").to_pydatetime(),
            duration_seconds=0, return_code=None,
            message="Operation blocked by active workflow.",
        )
    ui.session_state[OPERATION_LOCK_KEY] = operation
    try:
        progress_message = (
            "Saving decision and synchronizing Identity Review..."
            if operation == "save_identity_review_decision"
            else (
                f"Running {operation}. This may take several minutes; "
                "a 3-minute safety timeout applies..."
            )
        )
        with ui.spinner(progress_message):
            result = operations.run(operation, season_id, parameters or {})
        if result.success and show_success:
            ui.success(result.message)
        elif not result.success:
            ui.error(_operation_error_message(result))
            if hasattr(ui, "expander"):
                with ui.expander("Technical details"):
                    ui.code(result.display_log())
        return result
    finally:
        ui.session_state.pop(OPERATION_LOCK_KEY, None)


def _refresh_review_data(
    ui: Any,
    data: DataManager,
    operations: OperationsService,
    season_id: str,
    notice: str,
) -> bool:
    """Regenerate registered review data, invalidate local reads, and rerun."""
    regenerated = _run(
        ui,
        operations,
        "generate_identity_review",
        season_id,
        show_success=False,
    )
    if not regenerated.success:
        return False
    data.invalidate("player_identity_review", season_id)
    data.invalidate("player_alias_overrides", season_id)
    ui.session_state[PENDING_STATUS_FILTER_KEY] = ui.session_state.get(
        "identity_review_status_filter",
        ["Unreviewed", "Approved", "Ignored"],
    )
    ui.session_state["_identity_review_notice"] = notice
    ui.rerun()
    return True


def _save_decision_and_refresh(
    ui: Any,
    data: DataManager,
    operations: OperationsService,
    season_id: str,
    parameters: dict[str, Any],
) -> bool:
    """Persist one decision and its authoritative narrow review projection."""
    saved = _run(
        ui,
        operations,
        "save_identity_review_decision",
        season_id,
        parameters,
        show_success=False,
    )
    if not saved.success:
        return False
    decision = str(parameters["decision"])
    status = "Unreviewed" if decision == "Clear" else decision
    data.invalidate("player_identity_review", season_id)
    data.invalidate("player_alias_overrides", season_id)
    with ui.spinner("Refreshing and verifying Identity Review..."):
        verified, verification_error = _verify_decision_projection(
            data, season_id, parameters
        )
    if not verified:
        ui.error(verification_error)
        if hasattr(ui, "expander"):
            with ui.expander("Technical details"):
                ui.code(saved.display_log())
        return False
    refreshed_review = _load_optional(
        data, "player_identity_review", season_id, "working"
    )
    queue_remaining = int(
        refreshed_review.get(
            "review_status", pd.Series(dtype=str)
        ).eq("Unreviewed").sum()
    )
    ui.session_state.pop("_identity_review_selected_pair", None)
    ui.session_state[PENDING_STATUS_FILTER_KEY] = ui.session_state.get(
        "identity_review_status_filter",
        ["Unreviewed", "Approved", "Ignored"],
    )
    elapsed = getattr(saved, "duration_seconds", None)
    elapsed_text = f" in {elapsed:.1f}s" if elapsed is not None else ""
    notice = {
        "Approved": "Alias approved",
        "Ignored": "Suggestion ignored",
        "Clear": "Decision cleared",
    }[decision]
    ui.session_state["_identity_review_notice"] = (
        f"Verified · {notice}{elapsed_text}. Status is now {status}. "
        f"{queue_remaining} unresolved suggestions remain."
    )
    ui.rerun()
    return True


def render(
    season_id: str,
    *,
    data_manager: DataManager | None = None,
    operations_service: OperationsService | None = None,
    season_manager: SeasonManager | None = None,
    ui: Any = st,
) -> None:
    """Render review data and submit decisions only through approved services."""
    seasons = season_manager or SeasonManager()
    namespace = seasons.resolve_namespace(season_id)
    data = data_manager or DataManager(season_manager=seasons)
    operations = operations_service or OperationsService(season_manager=seasons)

    _apply_pending_status_filter(ui)
    notice = ui.session_state.pop("_identity_review_notice", "")
    if notice:
        ui.success(notice)

    ui.markdown(
        '<div class="section-eyebrow">Player Registry administration</div>'
        '<div class="section-title">Player Identity Review</div>'
        '<div class="section-copy">Review conservative identity suggestions '
        "before approving any alias.</div>",
        unsafe_allow_html=True,
    )
    review = _load_optional(data, "player_identity_review", season_id, namespace)
    registry = _load_optional(data, "player_registry", season_id, namespace)
    decisions = _load_optional(data, "player_alias_overrides", season_id, namespace)

    unresolved = int(registry.get("registry_status", pd.Series(dtype=str)).eq(
        "Unresolved"
    ).sum())
    historical = int(registry.get("registry_status", pd.Series(dtype=str)).eq(
        "Historical Only"
    ).sum())
    high = int(review.get("confidence_class", pd.Series(dtype=str)).eq(
        "High confidence"
    ).sum())
    medium = int(review.get("confidence_class", pd.Series(dtype=str)).eq(
        "Medium confidence"
    ).sum())
    no_safe = int(review.get("confidence_class", pd.Series(dtype=str)).eq(
        "No safe candidate"
    ).sum())
    queue_remaining = int(
        review.get("review_status", pd.Series(dtype=str)).eq("Unreviewed").sum()
    )
    approved = int(decisions.get("decision", pd.Series(dtype=str)).eq("Approved").sum())
    ignored = int(decisions.get("decision", pd.Series(dtype=str)).eq("Ignored").sum())
    metric_values = (
        ("Unresolved", unresolved), ("Historical Only", historical),
        ("High confidence", high), ("Medium confidence", medium),
        ("No safe candidate", no_safe), ("Unreviewed queue", queue_remaining),
        ("Approved aliases", approved),
        ("Ignored", ignored),
    )
    for column, (label, value) in zip(ui.columns(len(metric_values)), metric_values):
        column.metric(label, value)

    if review.empty:
        ui.info(
            "No review artifact is available. Run Generate Identity Review below."
        )
        if ui.button("Generate Identity Review", key="identity_generate_empty"):
            _refresh_review_data(
                ui, data, operations, season_id, "Identity review regenerated."
            )
        return

    ui.subheader("Filters")
    filter_columns = ui.columns(4)
    review_status_options = ["Unreviewed", "Approved", "Ignored"]
    status = filter_columns[0].multiselect(
        "Review status",
        review_status_options,
        key="identity_review_status_filter",
    )
    registry_status = filter_columns[1].multiselect(
        "Registry status",
        sorted(review["current_registry_status"].dropna().astype(str).unique()),
        default=sorted(review["current_registry_status"].dropna().astype(str).unique()),
    )
    confidence = filter_columns[2].multiselect(
        "Candidate confidence",
        sorted(review["confidence_class"].dropna().astype(str).unique()),
        default=sorted(review["confidence_class"].dropna().astype(str).unique()),
    )
    teams = filter_columns[3].multiselect(
        "Team",
        sorted(review["current_candidate_team_code"].dropna().astype(str).unique()),
        default=sorted(review["current_candidate_team_code"].dropna().astype(str).unique()),
    )
    position_options = sorted(
        review["current_candidate_position"].dropna().astype(str).unique()
    )
    positions = ui.multiselect(
        "Position", position_options, default=position_options
    )
    methods = sorted(review["current_match_method"].dropna().astype(str).unique())
    selected_methods = ui.multiselect("Match method", methods, default=methods)
    draft_filter = ui.selectbox(
        "Draft eligibility", ["All", "Eligible", "Ineligible"]
    )
    search = ui.text_input("Search by player name")
    production_only = ui.checkbox("Only players with historical production")
    high_value_only = ui.checkbox("Only high-value players")

    filtered = review[
        review["review_status"].isin(status)
        & review["current_registry_status"].isin(registry_status)
        & review["confidence_class"].isin(confidence)
        & review["current_candidate_team_code"].isin(teams)
        & review["current_candidate_position"].isin(positions)
        & review["current_match_method"].isin(selected_methods)
    ].copy()
    if draft_filter != "All":
        expected = draft_filter == "Eligible"
        filtered = filtered[filtered["current_draft_eligible"].astype(bool).eq(expected)]
    if search.strip():
        pattern = search.strip()
        filtered = filtered[
            filtered["historical_name"].str.contains(pattern, case=False, na=False)
            | filtered["current_candidate_name"].str.contains(
                pattern, case=False, na=False
            )
        ]
    if production_only:
        filtered = filtered[
            pd.to_numeric(
                filtered["historical_fantasy_points"], errors="coerce"
            ).fillna(0).gt(0)
        ]
    if high_value_only:
        projected = pd.to_numeric(
            filtered["historical_projected_points"], errors="coerce"
        ).fillna(0)
        adp = pd.to_numeric(filtered["historical_adp"], errors="coerce")
        filtered = filtered[projected.ge(150) | adp.le(150)]

    ui.subheader("Review queue")
    display = filtered[
        [
            "historical_name", "current_candidate_name",
            "historical_team_code", "current_candidate_team_code",
            "current_candidate_position", "confidence_class", "candidate_score",
            "candidate_reason", "current_registry_status", "review_status",
        ]
    ].rename(
        columns={
            "historical_name": "Historical player",
            "current_candidate_name": "Candidate FPL player",
            "historical_team_code": "Historical club",
            "current_candidate_team_code": "Current club",
            "current_candidate_position": "Position",
            "confidence_class": "Confidence",
            "candidate_score": "Score",
            "candidate_reason": "Reason",
            "current_registry_status": "Registry status",
            "review_status": "Review status",
        }
    )
    ui.dataframe(display, width="stretch", hide_index=True)
    if filtered.empty:
        ui.info("No suggestions match the selected filters.")
        return

    options = filtered.index.tolist()
    selected_pair = ui.session_state.get("_identity_review_selected_pair")
    selected_option_index = 0
    if selected_pair:
        for option_index, row_index in enumerate(options):
            pair = (
                str(filtered.at[row_index, "fantrax_player_id"]),
                str(filtered.at[row_index, "current_candidate_fpl_id"]),
            )
            if pair == tuple(selected_pair):
                selected_option_index = option_index
                break
    selected_index = ui.selectbox(
        "Select suggestion",
        options,
        index=selected_option_index,
        format_func=lambda index: (
            f"{filtered.at[index, 'historical_name']} → "
            f"{filtered.at[index, 'current_candidate_name']}"
        ),
    )
    selected = filtered.loc[selected_index]
    ui.subheader("Selected-player evidence")
    historical_column, candidate_column, evidence_column = ui.columns(3)
    historical_column.write(
        {
            "Name": selected["historical_name"],
            "Fantrax ID": selected["fantrax_player_id"],
            "Team": selected["historical_team_code"],
            "Position": selected["historical_position"],
            "Minutes": selected["historical_minutes"],
            "Fantasy points": selected["historical_fantasy_points"],
            "Ghost points": selected["historical_ghost_points"],
            "ADP": selected["historical_adp"],
            "Registry status": selected["current_registry_status"],
            "Match method": selected["current_match_method"],
        }
    )
    candidate_column.write(
        {
            "Official name": selected["current_candidate_name"],
            "FPL ID": selected["current_candidate_fpl_id"],
            "Team": selected["current_candidate_team_code"],
            "Position": selected["current_candidate_position"],
            "Active": selected["candidate_active_epl"],
            "Availability": selected["candidate_availability_status"],
        }
    )
    evidence_column.write(
        {
            "Normalized historical": selected["normalized_historical_name"],
            "Normalized candidate": selected["normalized_candidate_name"],
            "Shared tokens": selected["shared_tokens"],
            "Team compatible": selected["team_compatible"],
            "Position compatible": selected["position_compatible"],
            "Unique": selected["candidate_unique"],
            "Already linked": selected.get("candidate_already_linked", False),
            "Reason": selected["candidate_reason"],
            "Score": selected["candidate_score"],
            "Confidence": selected["confidence_class"],
        }
    )

    note = ui.text_area("Review note", value=str(selected["review_note"] or ""))
    transfer = not bool(selected["team_compatible"])
    pair_key = (
        f"{selected['fantrax_player_id']}_"
        f"{selected['current_candidate_fpl_id']}"
    )
    if transfer:
        ui.warning(
            "The clubs differ, so approving this alias requires explicit "
            "acknowledgement that the player may have transferred."
        )
    acknowledge_transfer = ui.checkbox(
        "Acknowledge possible transfer",
        value=False,
        disabled=not transfer,
        key=f"identity_transfer_ack_{pair_key}",
    )
    operation_active = bool(ui.session_state.get(OPERATION_LOCK_KEY))
    decision_columns = ui.columns(3)
    actions = (
        ("Approve Alias", "Approved"),
        ("Ignore Suggestion", "Ignored"),
        ("Clear Review Decision", "Clear"),
    )
    for column, (label, decision) in zip(decision_columns, actions):
        approval_blocked = (
            decision == "Approved" and transfer and not acknowledge_transfer
        )
        if column.button(
            label,
            key=f"identity_{decision.lower()}",
            disabled=operation_active or approval_blocked,
        ):
            ui.session_state["_identity_review_selected_pair"] = (
                str(selected["fantrax_player_id"]),
                str(selected["current_candidate_fpl_id"]),
            )
            _save_decision_and_refresh(
                ui,
                data,
                operations,
                season_id,
                {
                    "season_id": season_id,
                    "fantrax_player_id": selected["fantrax_player_id"],
                    "current_fpl_player_id": selected[
                        "current_candidate_fpl_id"
                    ],
                    "decision": decision,
                    "review_note": note,
                    "acknowledge_transfer": acknowledge_transfer,
                },
            )

    ui.subheader("Rebuild actions")
    operations_to_render = (
        ("Generate Identity Review", "generate_identity_review"),
        ("Build Player Registry", "build_player_registry"),
        ("Validate Player Registry", "validate_player_registry"),
        ("Generate Registry Reports", "generate_registry_reports"),
        ("Build Draft Outputs", "build_draft_outputs"),
    )
    for column, (label, operation) in zip(
        ui.columns(len(operations_to_render)), operations_to_render
    ):
        if column.button(
            label,
            key=f"identity_operation_{operation}",
            disabled=operation_active,
        ):
            if operation == "generate_identity_review":
                _refresh_review_data(
                    ui,
                    data,
                    operations,
                    season_id,
                    "Identity review regenerated.",
                )
            else:
                _run(ui, operations, operation, season_id)
