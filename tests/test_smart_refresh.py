from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from core.models.operation_result import OperationResult
from core.services.smart_refresh import build_smart_refresh_plan, run_smart_refresh, status_succeeded
import scripts.refresh_desktop_sources as desktop


def source_plan(**updates):
    value={"fantrax_current_period":3,"fantrax_maturity":"COMPLETE_PENDING_CORRECTIONS","previous_gw_status":"FINALIZED","fantrax_targets":[],"whoscored":{"would_acquire":0,"would_recheck":0},"understat":{"would_acquire":0,"would_recheck":0},"model_rebuild_required":False}
    value.update(updates);return value


def test_cache_hit_and_no_action_are_success():
    assert status_succeeded("CACHE_HIT") and status_succeeded("NO_ACTION_REQUIRED")


def test_planner_identifies_desktop_and_previous_correction():
    plan=build_smart_refresh_plan(source_plan=source_plan(previous_gw_status="COMPLETE_AWAITING_STABILITY",whoscored={"would_acquire":1,"would_recheck":2}))
    assert plan.desktop_acquisition_required and plan.correction_check_required
    assert plan.whoscored.status=="DESKTOP_REQUIRED" and plan.previous_gw==2


def test_finalized_previous_gw_is_protected():
    plan=build_smart_refresh_plan(source_plan=source_plan())
    assert not plan.correction_check_required
    assert plan.finalization_eligibility=="FINALIZED_PROTECTED"


def test_cache_rebuild_runs_only_when_all_inputs_exist():
    now=datetime.now(timezone.utc)
    result=OperationResult("rebuild_current_cached_products",True,now,now,.1,0,"ok")
    ops=SimpleNamespace(run=lambda *args:result)
    run=run_smart_refresh(ops,plan_loader=lambda season:source_plan(model_rebuild_required=True))
    assert run.status=="PASS" and len(run.stages)==1


def test_desktop_command_contains_role_guard_and_previous_check():
    source=Path("scripts/refresh_desktop_sources.py").read_text(encoding="utf-8")
    assert "require_commissioner_writer" in source
    assert "build_current_data_integrity.py" in source


def test_desktop_command_rejects_client_mode(monkeypatch):
    monkeypatch.setenv("FANTRAX_MACHINE_ROLE","client")
    monkeypatch.setenv("COMMISSIONER_REFRESH_ENABLED","false")
    monkeypatch.setattr("sys.argv",["refresh_desktop_sources.py"])
    assert desktop.main()==2


def test_desktop_command_runs_previous_gw_correction_check(monkeypatch):
    plan=SimpleNamespace(current_gw=3,previous_gw=2,whoscored=SimpleNamespace(status="CACHE_HIT"),understat=SimpleNamespace(status="CACHE_HIT"))
    calls=[]
    monkeypatch.setattr(desktop,"require_commissioner_writer",lambda name:None)
    monkeypatch.setattr(desktop,"build_smart_refresh_plan",lambda season:plan)
    monkeypatch.setattr(desktop,"_run",lambda script,*args:calls.append((script,args)) or 0)
    monkeypatch.setattr(desktop,"atomic_json",lambda *args,**kwargs:None)
    monkeypatch.setattr(desktop,"publish_refresh",lambda *args,**kwargs:SimpleNamespace(status="NO_ACTION_REQUIRED",files=(),blockers=(),commit=None))
    monkeypatch.setattr("sys.argv",["refresh_desktop_sources.py"])
    assert desktop.main()==0
    assert ("build_current_data_integrity.py",("--season","2627","--period",2)) in calls
