"""Explicit resilient orchestration for the hosted core refresh."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.models.operation_result import OperationResult


@dataclass(frozen=True, slots=True)
class RefreshStage:
    label: str
    operation: str
    required: bool
    result: OperationResult


@dataclass(frozen=True, slots=True)
class CoreRefreshResult:
    status: str
    stages: tuple[RefreshStage, ...]

    @property
    def succeeded(self)->tuple[RefreshStage,...]:return tuple(x for x in self.stages if x.result.success)
    @property
    def attention(self)->tuple[RefreshStage,...]:return tuple(x for x in self.stages if not x.result.success)


STAGES=(("League metadata","refresh_live_league_metadata",True),("Standings","refresh_live_standings",False),("Rosters","refresh_live_rosters",False),("Players, managers, ownership, and analytics","build_live_season_datasets",True))


def run_core_refresh(operations:Any,season_id:str)->CoreRefreshResult:
    results=[];critical_failed=False
    for label,operation,required in STAGES:
        if critical_failed:break
        result=operations.run(operation,season_id,{})
        results.append(RefreshStage(label,operation,required,result))
        if required and not result.success:critical_failed=True
    if any(x.required and not x.result.success for x in results):status="FAILED"
    elif any(not x.result.success for x in results):status="PARTIAL"
    else:status="SUCCESS"
    return CoreRefreshResult(status,tuple(results))
