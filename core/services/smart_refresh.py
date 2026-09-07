"""Shared planning and cache-side orchestration for Season Refresh V1."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable

from core.models.operation_result import OperationResult

SUCCESS_STATES = frozenset({"PASS", "CACHE_HIT", "NO_ACTION_REQUIRED"})
DESKTOP_COMMAND = "python scripts/refresh_desktop_sources.py"
CACHE_REBUILD_OPERATION = "rebuild_current_cached_products"


def status_succeeded(status: str) -> bool:
    return str(status).upper() in SUCCESS_STATES


@dataclass(frozen=True, slots=True)
class ProviderRefreshState:
    status: str
    detail: str
    acquire: int = 0
    recheck: int = 0


@dataclass(frozen=True, slots=True)
class SmartRefreshPlan:
    season: str
    current_gw: int | None
    previous_gw: int | None
    current_gw_status: str
    previous_gw_status: str
    fantrax: ProviderRefreshState
    whoscored: ProviderRefreshState
    understat: ProviderRefreshState
    desktop_acquisition_required: bool
    canonical_rebuild_required: bool
    team_rebuild_required: bool
    league_hub_rebuild_required: bool
    correction_check_required: bool
    finalization_eligibility: str
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SmartRefreshResult:
    status: str
    initial_plan: SmartRefreshPlan
    final_plan: SmartRefreshPlan
    stages: tuple[OperationResult, ...] = ()


def _provider_state(name: str, acquire: int, recheck: int) -> ProviderRefreshState:
    if acquire or recheck:
        return ProviderRefreshState("DESKTOP_REQUIRED", f"{acquire} acquisition(s), {recheck} correction recheck(s)", acquire, recheck)
    return ProviderRefreshState("CACHE_HIT", f"Current valid {name} cache retained")


def build_smart_refresh_plan(
    season: str = "2627", *, source_plan: dict[str, Any] | None = None,
    plan_loader: Callable[[str], dict[str, Any]] | None = None,
) -> SmartRefreshPlan:
    """Translate the established commissioner plan into one UI/CLI contract."""
    if source_plan is None:
        if plan_loader is None:
            from scripts.weekly_commissioner_refresh import plan as plan_loader
        source_plan = plan_loader(season)
    current_value = source_plan.get("fantrax_current_period")
    current = int(current_value) if current_value else None
    previous = current - 1 if current and current > 1 else None
    fantrax_targets = tuple(source_plan.get("fantrax_targets") or ())
    correction_required = bool(previous) and str(source_plan.get("previous_gw_status", "")).upper() != "FINALIZED" and not bool(source_plan.get("previous_correction_checked"))
    fantrax = _provider_state("Fantrax", len(fantrax_targets), int(correction_required))
    ws = source_plan.get("whoscored") or {}
    whoscored = _provider_state("WhoScored", int(ws.get("would_acquire", 0)), int(ws.get("would_recheck", 0)))
    us = source_plan.get("understat") or {}
    understat = _provider_state("Understat", int(us.get("would_acquire", 0)), int(us.get("would_recheck", 0)))
    desktop = any(item.status == "DESKTOP_REQUIRED" for item in (fantrax, whoscored, understat))
    rebuild = bool(source_plan.get("model_rebuild_required"))
    current_status = str(source_plan.get("fantrax_maturity") or "MISSING")
    previous_status = str(source_plan.get("previous_gw_status") or ("FINALIZED" if previous is None else "CORRECTION_RECHECK_REQUIRED"))
    eligibility = "FINALIZED_PROTECTED" if previous_status == "FINALIZED" else "AWAITING_STABILITY" if correction_required else "FINALIZATION_READY"
    return SmartRefreshPlan(season, current, previous, current_status, previous_status, fantrax, whoscored, understat, desktop, rebuild, rebuild, rebuild, correction_required, eligibility)


def run_smart_refresh(operations: Any, season: str = "2627", *, plan_loader: Callable[[str], dict[str, Any]] | None = None) -> SmartRefreshResult:
    """Run only rebuilds that are safe with the caches available to the app."""
    initial = build_smart_refresh_plan(season, plan_loader=plan_loader)
    stages: list[OperationResult] = []
    if initial.canonical_rebuild_required and not initial.desktop_acquisition_required:
        stages.append(operations.run(CACHE_REBUILD_OPERATION, season, {}))
    final = build_smart_refresh_plan(season, plan_loader=plan_loader)
    status = "FAIL" if any(not stage.success for stage in stages) else "DESKTOP_REQUIRED" if final.desktop_acquisition_required else "PASS"
    return SmartRefreshResult(status, initial, final, tuple(stages))
