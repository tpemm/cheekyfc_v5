"""Approved, framework-independent execution boundary for application jobs."""

from __future__ import annotations

import re
import json
import math
import subprocess
import sys
import time
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from core.models.operation_definition import OperationDefinition
from core.models.operation_result import OperationResult
from core.services.season_manager import SeasonManager
from fantrax.live.config import load_live_season_config
from core.services.machine_role import commissioner_refresh_enabled,require_commissioner_writer,MachineRoleError


class OperationsServiceError(RuntimeError):
    """Base error for invalid operation registration or invocation."""


class UnknownOperationError(OperationsServiceError, KeyError):
    """Raised when an operation ID is not registered."""


class OperationNotAllowedError(OperationsServiceError, PermissionError):
    """Raised when a season or namespace may not run an operation."""


class OperationParameterError(OperationsServiceError, ValueError):
    """Raised when operation parameters are unknown or invalid."""

AUTHORITATIVE_LIVE_OPERATIONS={"refresh_live_fantrax_sources","backfill_live_weekly_stats","force_refresh_live_weekly_stats","refresh_live_league_metadata","refresh_live_standings","refresh_live_rosters","refresh_fantrax_data","refresh_current_squad","build_live_season_datasets","build_roster_tracking"}


@dataclass(frozen=True, slots=True)
class _RegisteredOperation:
    definition: OperationDefinition
    script_relative_path: str
    input_builder: Callable[[Mapping[str, Any]], str | None]


def _refresh_input(parameters: Mapping[str, Any]) -> str:
    mode = str(parameters.get("mode", "AUTO")).strip().upper()
    if mode not in {"AUTO", "REBUILD", "SPECIFIC", "FULL"}:
        raise OperationParameterError(f"Unsupported refresh mode: {mode!r}")
    specific_weeks = str(parameters.get("specific_weeks", "")).strip()
    if mode == "SPECIFIC":
        if not re.fullmatch(r"\d+(?:-\d+)?", specific_weeks):
            raise OperationParameterError(
                "SPECIFIC mode requires one gameweek or a gameweek range"
            )
        return f"SPECIFIC\n{specific_weeks}\n"
    if specific_weeks:
        raise OperationParameterError(
            "specific_weeks is only valid for SPECIFIC mode"
        )
    if mode == "FULL":
        return "FULL\nAUTO\n"
    return f"{mode}\n"


def _no_input(parameters: Mapping[str, Any]) -> None:
    if parameters:
        names = ", ".join(sorted(parameters))
        raise OperationParameterError(f"Unknown parameters: {names}")
    return None


def _live_refresh_input(source: str) -> Callable[[Mapping[str, Any]], str]:
    def build(parameters: Mapping[str, Any]) -> str:
        payload: dict[str, Any] = {"source": source}
        if "period" in parameters and str(parameters["period"]).strip():
            try:
                period = int(parameters["period"])
            except (TypeError, ValueError) as exc:
                raise OperationParameterError("period must be an integer") from exc
            if not 1 <= period <= 38:
                raise OperationParameterError("period must be between 1 and 38")
            payload["period"] = period
        if "full_history" in parameters:
            payload["full_history"] = bool(parameters["full_history"])
        if "weekly_mode" in parameters:
            mode=str(parameters["weekly_mode"])
            if mode not in {"normal","backfill","force_current"}: raise OperationParameterError("Unsupported weekly_mode")
            payload["weekly_mode"]=mode
        if "force" in parameters: payload["force"]=bool(parameters["force"])
        return json.dumps(payload, sort_keys=True)
    return build

def _weekly_refresh_input(mode:str)->Callable[[Mapping[str,Any]],str]:
    base=_live_refresh_input("weekly_stats")
    def build(parameters:Mapping[str,Any])->str:
        return base({**parameters,"weekly_mode":mode,"force":bool(parameters.get("force",mode=="force_current"))})
    return build

def _cup_input(action: str) -> Callable[[Mapping[str, Any]], str]:
    def build(parameters: Mapping[str, Any]) -> str:
        if parameters: raise OperationParameterError(f"Cup {action} accepts no parameters")
        return json.dumps({"action":action},sort_keys=True)
    return build


def _to_json_safe(value: Any) -> Any:
    """Recursively convert pandas/NumPy values to strict JSON-native values."""
    if isinstance(value, Mapping):
        return {
            _to_json_safe(key): _to_json_safe(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_to_json_safe(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted(
            (_to_json_safe(item) for item in value),
            key=lambda item: repr(item),
        )
    if value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        value = float(value)
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return value


def _identity_decision_input(parameters: Mapping[str, Any]) -> str:
    required = {
        "fantrax_player_id", "current_fpl_player_id", "decision", "season_id",
    }
    missing = required - set(parameters)
    if missing:
        raise OperationParameterError(
            "Missing identity decision parameters: " + ", ".join(sorted(missing))
        )
    decision = str(parameters["decision"])
    if decision not in {"Approved", "Ignored", "Clear"}:
        raise OperationParameterError(f"Unsupported review decision: {decision!r}")
    safe_parameters = _to_json_safe(dict(parameters))
    return json.dumps(
        safe_parameters,
        sort_keys=True,
        allow_nan=False,
    )


DEFAULT_OPERATIONS: tuple[_RegisteredOperation, ...] = (
    *(
        _RegisteredOperation(
            definition=OperationDefinition(key=key,label=label,description=description,capability="build_master"),
            script_relative_path="scripts/manage_cup.py",input_builder=_cup_input(action),
        )
        for key,label,description,action in (
            ("initialize_cup","Initialize Cup","Freeze seeds once the configured seeding week is complete.","initialize"),
            ("build_cup_bracket","Build Cup Bracket","Build the configured bracket from the immutable seed snapshot.","build"),
            ("rebuild_cup","Rebuild Cup","Refresh progression and results without changing frozen seeds.","rebuild"),
            ("validate_cup","Validate Cup","Validate configuration, schedule, snapshot, and bracket artifacts.","validate"),
        )
    ),
    _RegisteredOperation(
        definition=OperationDefinition(
            key="refresh_live_fantrax_sources", label="Refresh Current Season",
            description="Refresh proven league, standings, and roster sources into validated raw cache.", capability="refresh",
        ), script_relative_path="scripts/refresh_live_fantrax.py", input_builder=_live_refresh_input("all"),
    ),
    _RegisteredOperation(
        definition=OperationDefinition(
            key="backfill_live_weekly_stats", label="Backfill Weekly Player Stats",
            description="Acquire missing completed Fantrax player-stat periods without replacing valid finalized caches.", capability="refresh", parameters=("force",),
        ), script_relative_path="scripts/refresh_live_fantrax.py", input_builder=_weekly_refresh_input("backfill"),
    ),
    _RegisteredOperation(
        definition=OperationDefinition(
            key="force_refresh_live_weekly_stats", label="Force Refresh Current Period",
            description="Explicitly reacquire one Fantrax weekly-stat period, preserving prior cache if validation fails.", capability="refresh", parameters=("period","force"),
        ), script_relative_path="scripts/refresh_live_fantrax.py", input_builder=_weekly_refresh_input("force_current"),
    ),
    _RegisteredOperation(
        definition=OperationDefinition(
            key="refresh_live_league_metadata", label="Refresh Fantrax League Metadata",
            description="Refresh validated league settings, teams, matchups, and scoring metadata.", capability="refresh",
        ), script_relative_path="scripts/refresh_live_fantrax.py", input_builder=_live_refresh_input("league_metadata"),
    ),
    _RegisteredOperation(
        definition=OperationDefinition(
            key="refresh_live_standings", label="Refresh Fantrax Standings",
            description="Refresh the current authoritative standings response.", capability="refresh",
        ), script_relative_path="scripts/refresh_live_fantrax.py", input_builder=_live_refresh_input("standings"),
    ),
    _RegisteredOperation(
        definition=OperationDefinition(
            key="refresh_live_rosters", label="Refresh Fantrax Rosters",
            description="Refresh the current authoritative roster period, one explicit period, or opt-in full history.", capability="refresh", parameters=("period", "full_history"),
        ), script_relative_path="scripts/refresh_live_fantrax.py", input_builder=_live_refresh_input("rosters"),
    ),
    _RegisteredOperation(
        definition=OperationDefinition(
            key="build_live_season_datasets", label="Build Live Season Datasets",
            description="Normalize cached raw sources, join Player Registry, validate outputs, and write quality/manifest artifacts.", capability="build_master",
        ), script_relative_path="scripts/build_live_season.py", input_builder=_no_input,
    ),
    _RegisteredOperation(
        definition=OperationDefinition(
            key="build_roster_tracking", label="Build Roster Tracking",
            description="Build immutable roster snapshots, changes, history, ownership, and quality reports from cache.", capability="build_master",
        ), script_relative_path="scripts/build_live_season.py", input_builder=_no_input,
    ),
    _RegisteredOperation(
        definition=OperationDefinition(
            key="validate_roster_ownership", label="Validate Ownership",
            description="Rebuild and validate roster ownership reconciliation without network access.", capability="build_master",
        ), script_relative_path="scripts/build_live_season.py", input_builder=_no_input,
    ),
    _RegisteredOperation(
        definition=OperationDefinition(
            key="refresh_fantrax_data",
            label="Run refresh",
            description="Run the approved Fantrax refresh pipeline.",
            capability="refresh",
            parameters=("mode", "specific_weeks"),
        ),
        script_relative_path="fantrax/refresh/refresh_all_fantrax_data.py",
        input_builder=_refresh_input,
    ),
    _RegisteredOperation(
        definition=OperationDefinition(
            key="build_league_analytics",
            label="Only rebuild League Hub analytics",
            description="Rebuild the approved League Hub analytics views.",
            capability="build_analytics",
        ),
        script_relative_path=(
            "fantrax/analytics/build_league_awards_views.py"
        ),
        input_builder=_no_input,
    ),
    _RegisteredOperation(
        definition=OperationDefinition(
            key="refresh_current_squad",
            label="Refresh Current Squad",
            description="Download and cache the approved Official FPL squad snapshot.",
            capability="refresh",
        ),
        script_relative_path="scripts/refresh_current_squad.py",
        input_builder=_no_input,
    ),
    _RegisteredOperation(
        definition=OperationDefinition(
            key="build_player_registry",
            label="Build Player Registry",
            description="Build the canonical registry from cached source datasets.",
            capability="build_draft",
        ),
        script_relative_path="scripts/build_player_registry.py",
        input_builder=_no_input,
    ),
    _RegisteredOperation(
        definition=OperationDefinition(
            key="validate_player_registry",
            label="Validate Player Registry",
            description="Validate registry identity and uniqueness invariants.",
            capability="build_draft",
        ),
        script_relative_path="scripts/validate_player_registry.py",
        input_builder=_no_input,
    ),
    _RegisteredOperation(
        definition=OperationDefinition(
            key="generate_registry_reports",
            label="Generate Registry Reports",
            description="Regenerate registry quality and unresolved reports.",
            capability="build_draft",
        ),
        script_relative_path="scripts/generate_registry_reports.py",
        input_builder=_no_input,
    ),
    _RegisteredOperation(
        definition=OperationDefinition(
            key="generate_identity_review",
            label="Generate Identity Review",
            description="Generate conservative unresolved-player suggestions.",
            capability="build_draft",
        ),
        script_relative_path="scripts/generate_identity_review.py",
        input_builder=_no_input,
    ),
    _RegisteredOperation(
        definition=OperationDefinition(
            key="save_identity_review_decision",
            label="Save Identity Review Decision",
            description="Validate and save one pair-specific alias decision.",
            capability="build_draft",
            parameters=(
                "fantrax_player_id", "current_fpl_player_id", "decision",
                "review_note", "acknowledge_transfer", "season_id",
            ),
        ),
        script_relative_path="scripts/save_identity_review_decision.py",
        input_builder=_identity_decision_input,
    ),
    _RegisteredOperation(
        definition=OperationDefinition(
            key="build_draft_outputs",
            label="Build Draft Outputs",
            description="Rebuild the registered 2026/27 Draft datasets.",
            capability="build_draft",
        ),
        script_relative_path="scripts/build_draft_outputs.py",
        input_builder=_no_input,
    ),
    _RegisteredOperation(
        definition=OperationDefinition(
            key="build_draft_grades",
            label="Build Draft Grades",
            description="Validate completed results, preserve the immutable snapshot, and build grade reports.",
            capability="build_draft",
        ),
        script_relative_path="scripts/build_draft_grades.py",
        input_builder=_no_input,
    ),
)


class OperationsService:
    """Execute only centrally registered application operations."""

    def __init__(
        self,
        *,
        season_manager: SeasonManager | None = None,
        project_root: str | Path | None = None,
        operations: tuple[_RegisteredOperation, ...] = DEFAULT_OPERATIONS,
        executor: Callable[..., Any] = subprocess.run,
        timeout_seconds: float | None = None,
    ) -> None:
        self._seasons = season_manager or SeasonManager()
        default_root = Path(__file__).resolve().parents[2]
        self._project_root = Path(project_root or default_root).resolve()
        self._executor = executor
        # Bound synchronous UI jobs so a failed subprocess cannot leave the
        # application appearing to run forever.
        self._timeout_seconds = 180.0 if timeout_seconds is None else timeout_seconds
        self._operations: dict[str, _RegisteredOperation] = {}
        for operation in operations:
            key = operation.definition.key
            if key in self._operations:
                raise OperationsServiceError(
                    f"Duplicate operation ID: {key!r}"
                )
            self._operations[key] = operation

    def list_operations(
        self,
        season_id: str | None = None,
    ) -> tuple[OperationDefinition, ...]:
        """Return registered operation metadata, optionally filtered by season."""

        definitions = tuple(
            operation.definition for operation in self._operations.values()
        )
        if season_id is None:
            return definitions
        return tuple(
            definition
            for definition in definitions
            if self.can_run(definition.key, season_id)
        )

    def inspect_operation(self, operation_id: str) -> OperationDefinition:
        """Return public metadata for one approved operation."""

        return self._get(operation_id).definition

    def can_run(self, operation_id: str, season_id: str) -> bool:
        """Return whether the season capability and namespace permit execution."""

        operation = self._get(operation_id)
        context = self._seasons.context(season_id)
        namespace = self._seasons.resolve_namespace(season_id)
        return (
            namespace == "working"
            and context.mutable
            and (operation_id not in AUTHORITATIVE_LIVE_OPERATIONS or commissioner_refresh_enabled())
            and self._seasons.supports_operation(
                season_id,
                operation.definition.capability,
            )
        )

    def run(
        self,
        operation_id: str,
        season_id: str,
        parameters: Mapping[str, Any] | None = None,
    ) -> OperationResult:
        """Validate and synchronously execute one approved operation."""

        operation = self._get(operation_id)
        if operation_id in AUTHORITATIVE_LIVE_OPERATIONS:
            try:require_commissioner_writer(operation_id)
            except MachineRoleError as exc:raise OperationNotAllowedError(str(exc)) from exc
        context = self._seasons.context(season_id)
        namespace = self._seasons.resolve_namespace(season_id)
        if namespace != "working" or not context.mutable:
            raise OperationNotAllowedError(
                f"Season {season_id!r} is immutable"
            )
        if not self._seasons.supports_operation(
            season_id,
            operation.definition.capability,
        ):
            raise OperationNotAllowedError(
                f"Operation {operation_id!r} is not supported for "
                f"season {season_id!r}"
            )

        supplied = dict(parameters or {})
        unknown = set(supplied) - set(operation.definition.parameters)
        if unknown:
            names = ", ".join(sorted(unknown))
            raise OperationParameterError(f"Unknown parameters: {names}")
        input_text = operation.input_builder(supplied)
        script_path = (
            self._project_root / operation.script_relative_path
        ).resolve()
        if not script_path.is_relative_to(self._project_root):
            raise OperationsServiceError(
                "Registered operation resolves outside the project root"
            )

        started_at = datetime.now(timezone.utc)
        started = time.perf_counter()
        try:
            child_environment=os.environ.copy()
            if season_id=="2627" and operation.definition.capability=="refresh":
                resolved=load_live_season_config(project_root=self._project_root).league_id
                if resolved:child_environment["FANTRAX_LEAGUE_ID_2627"]=resolved
            completed = self._executor(
                [sys.executable, str(script_path)],
                input=input_text,
                text=True,
                cwd=str(self._project_root),
                capture_output=True,
                timeout=self._timeout_seconds,
                shell=False,
                env=child_environment,
            )
            return_code = int(completed.returncode)
            combined=f"{completed.stdout or ''}\n{completed.stderr or ''}"
            stage_match=re.search(r"(?:REFRESH|BUILD)_FAILURE stage=([^\s]+)",combined)
            league_match=re.search(r"league_id=([^\s]+)",combined)
            exception_match=re.search(r"exception_type=([^\s]+) message=(.*)",combined)
            success = return_code == 0
            message = (
                "Operation completed."
                if success
                else "Operation did not finish cleanly."
            )
            return OperationResult(
                operation_key=operation_id,
                success=success,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                duration_seconds=time.perf_counter() - started,
                return_code=return_code,
                message=message,
                stdout=str(completed.stdout or ""),
                stderr=str(completed.stderr or ""),
                error_type=exception_match.group(1) if exception_match and return_code else None,
                exception_message=exception_match.group(2).strip() if exception_match and return_code else None,
                season_id=season_id,
                resolved_league_id=league_match.group(1) if league_match else None,
                failed_stage=stage_match.group(1) if stage_match else None,
                command=f"{sys.executable} {script_path}",
            )
        except Exception as exc:
            return OperationResult(
                operation_key=operation_id,
                success=False,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                duration_seconds=time.perf_counter() - started,
                return_code=None,
                message="Operation execution failed.",
                error_type=type(exc).__name__,
                exception_message=str(exc),
                season_id=season_id,
                resolved_league_id=child_environment.get("FANTRAX_LEAGUE_ID_2627") if season_id=="2627" else None,
                failed_stage="subprocess_execution",
                command=f"{sys.executable} {script_path}",
            )

    def _get(self, operation_id: str) -> _RegisteredOperation:
        try:
            return self._operations[str(operation_id)]
        except KeyError as exc:
            raise UnknownOperationError(
                f"Unknown operation ID: {operation_id!r}"
            ) from exc
