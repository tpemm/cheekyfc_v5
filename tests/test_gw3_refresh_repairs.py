"""Regression coverage for the first production GW3 refresh; no live requests."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from integrations.whoscored.controller import acquire, validate_cache
from integrations.whoscored.live_refresh import build_live_manifest, validated_cache_manifest, acquisition_plan
from scripts import refresh_desktop_sources as desktop
from scripts import refresh_understat_live as understat
from scripts import refresh_whoscored_live_match as match_worker
from core.services.refresh_publisher import PublishResult


def fixture_frame():
    return pd.DataFrame([
        {"match_id":"m1","kickoff_time":"2026-08-21T15:00:00Z","status":"completed","completed":True,"home_club_id":"arsenal","away_club_id":"chelsea","fantrax_period":1},
        {"match_id":"m3","kickoff_time":"2026-09-05T15:00:00Z","status":"completed","completed":True,"home_club_id":"liverpool","away_club_id":"everton","fantrax_period":3},
    ])


def worker_manifest(tmp_path):
    path=tmp_path/"manifest.csv"
    pd.DataFrame([{"canonical_match_id":"m3","whoscored_match_id":101,"date":"2026-09-05","home_club_id":"liverpool","away_club_id":"everton"}]).to_csv(path,index=False)
    return path


@pytest.mark.parametrize("failures", [0, 1, 2])
def test_worker_creates_missing_directories_and_promotes_real_download(tmp_path,monkeypatch,failures):
    manifest=worker_manifest(tmp_path)
    closed=[]
    calls=[]
    class Reader:
        def __init__(self,**kwargs):
            self.base=kwargs["data_dir"]
            self._driver=SimpleNamespace(quit=lambda:closed.append(True),session_id="test",service=SimpleNamespace(process=SimpleNamespace(poll=lambda:None),is_connectable=lambda:True))
        def read_events(self,**kwargs):
            calls.append(kwargs["match_id"])
            if len(calls)<=failures:raise ConnectionRefusedError("WinError 10061")
            assert kwargs["match_id"]==101 and kwargs["live"]
            path=self.base/"events/ENG-Premier League_2627/101.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({"home":{"name":"Liverpool"},"away":{"name":"Everton"},"events":[{"id":1}],"startDate":"2026-09-05"}))
    monkeypatch.setattr(match_worker,"create_reader",lambda **kwargs:Reader(**kwargs))
    monkeypatch.setattr(match_worker,"ROOT",tmp_path)
    monkeypatch.setattr(match_worker,"require_commissioner_writer",lambda name:None)
    monkeypatch.setattr(sys,"argv",["worker","--manifest",str(manifest),"--whoscored-match-id","101","--force"])
    assert match_worker.main()==(1 if failures else 0)
    assert calls==[101]
    assert len(closed)==len(calls)
    base=tmp_path/"data/raw/whoscored/2627/poc"
    assert validate_cache(base,pd.read_csv(manifest).iloc[0].to_dict())["cache_valid"] is (failures==0)
    metadata=json.loads((base/"match_101/metadata.json").read_text())
    assert len(metadata["browser_attempts"])==len(calls)
    if failures:
        assert metadata["browser_attempts"][0]["error_message"]=="WinError 10061"
    if failures:
        assert metadata["error_type"]=="ConnectionRefusedError"
    else:
        result=acquire(pd.read_csv(manifest),root=tmp_path,manifest_path=manifest,season="2627",worker=lambda *args:pytest.fail("valid cache reacquired"))
        assert result.iloc[0].status=="CACHE_HIT"


def test_missing_payload_reports_original_dependency_failure(tmp_path):
    manifest=worker_manifest(tmp_path)
    rows=pd.read_csv(manifest)
    def worker(command,timeout):
        target=tmp_path/"data/raw/whoscored/2627/poc/match_101"
        target.mkdir(parents=True)
        (target/"metadata.json").write_text(json.dumps({"status":"error","error_type":"ModuleNotFoundError","error_message":"No module named 'soccerdata'"}))
        return {"returncode":1,"seconds":0,"timed_out":False}
    result=acquire(rows,root=tmp_path,manifest_path=manifest,season="2627",session_backed=True,worker=worker,retries=0)
    assert result.iloc[0].status=="FAILED"
    assert result.iloc[0].error_type=="ModuleNotFoundError"
    assert "soccerdata" in result.iloc[0].error_message
    assert not (tmp_path/"data/raw/whoscored/2627/poc/match_101/raw_match.json").exists()


def test_failed_metadata_is_not_present_even_if_manifest_says_stable(tmp_path):
    manifest=build_live_manifest(fixture_frame(),now="2026-09-07T00:00:00Z")
    manifest["whoscored_match_id"]=[100,101]
    manifest["cache_status"]="STABLE"
    manifest["acquisition_status"]="FAILED"
    target=tmp_path/"match_101";target.mkdir()
    (target/"metadata.json").write_text('{"status":"error","error_type":"ModuleNotFoundError"}')
    validated,metadata=validated_cache_manifest(manifest,tmp_path)
    assert metadata==[]
    assert acquisition_plan(validated)["stable"]==0
    assert acquisition_plan(validated)["failed_retryable"]==2


def setup_understat(tmp_path,monkeypatch):
    monkeypatch.setattr(understat,"ROOT",tmp_path)
    models=tmp_path/"data/models/season_2627";models.mkdir(parents=True)
    fixture_frame().to_csv(models/"team_matches_2627.csv",index=False)
    reference=tmp_path/"data/reference";reference.mkdir(parents=True)
    # Saved WhoScored plan predates GW3. Understat must not inherit FUTURE.
    stale=build_live_manifest(fixture_frame(),now="2026-08-24T00:00:00Z")
    stale.to_csv(reference/"whoscored_season_manifest_2627.csv",index=False)
    raw=tmp_path/"data/raw/understat/2627";raw.mkdir(parents=True)
    pd.DataFrame([{"game_id":1,"home_team":"Arsenal","away_team":"Chelsea","gameweek":1,"has_data":True,"home_xg":1.2,"away_xg":0.8}]).to_csv(raw/"understat_schedule_2627_ENG-Premier_League.csv",index=False)
    pd.DataFrame([{"game_id":1,"player_id":5}]).to_csv(raw/"understat_player_match_stats_2627_ENG-Premier_League.csv",index=False)
    return raw


def test_understat_uses_current_fixtures_not_stale_whoscored_plan(tmp_path,monkeypatch):
    setup_understat(tmp_path,monkeypatch)
    state=understat.refresh_plan()
    assert state["expected_completed_matches"]==2
    assert state["cached_completed_matches"]==1 and state["would_acquire"]==1
    assert state["gameweeks"]=="1-3"
    assert state["maturity"]["expected"]==2 and state["maturity"]["present"]==1
    assert state["maturity"]["stable"]==0


def test_understat_zero_exit_with_missing_data_is_partial(tmp_path,monkeypatch,capsys):
    setup_understat(tmp_path,monkeypatch)
    monkeypatch.setattr(understat,"require_commissioner_writer",lambda name:None)
    calls=[]
    monkeypatch.setattr(understat.subprocess,"run",lambda cmd,**kwargs:calls.append(cmd) or SimpleNamespace(returncode=0))
    monkeypatch.setattr(sys,"argv",["understat"])
    assert understat.main()==2
    assert "--missing-only" in calls[0]
    assert '"status": "PARTIAL"' in capsys.readouterr().out


def test_understat_missing_player_payload_not_counted(tmp_path,monkeypatch):
    raw=setup_understat(tmp_path,monkeypatch)
    pd.DataFrame(columns=["game_id","player_id"]).to_csv(raw/"understat_player_match_stats_2627_ENG-Premier_League.csv",index=False)
    assert understat.refresh_plan()["cached_completed_matches"]==0


def test_understat_incremental_selection_skips_cached_matches(tmp_path):
    from fantrax.scraping.scrape_understat_to_csv import missing_match_schedule
    schedule=pd.DataFrame([{"game_id":1,"has_data":True,"home_xg":1,"away_xg":0},{"game_id":3,"has_data":True,"home_xg":1,"away_xg":1},{"game_id":4,"has_data":False}])
    schedule.iloc[:1].to_csv(tmp_path/"understat_schedule_2627_EPL.csv",index=False)
    pd.DataFrame([{"game_id":1,"player_id":5}]).to_csv(tmp_path/"understat_player_match_stats_2627_EPL.csv",index=False)
    assert missing_match_schedule(schedule,tmp_path,"2627","EPL").game_id.tolist()==[3]


def test_fantrax_status_is_independent_of_whoscored_failure():
    stages=[{"stage":name,"returncode":0} for name in ("fantrax_weekly","fantrax_matchups","core_build","unified_models","correction_and_identity_reconciliation","understat_acquisition","understat_products")]
    stages.append({"stage":"whoscored_advanced","returncode":1})
    report={"stages":stages,"final_plan":{"understat":{"missing_matches":10}}}
    assert desktop.provider_statuses(report)=={"Fantrax":"PASS","WhoScored":"FAIL","Understat":"PARTIAL"}
    stages[0]["returncode"]=1
    assert desktop.provider_statuses(report)["Fantrax"]!="PASS"
    assert desktop.provider_statuses({})["Fantrax"]=="FAIL"


@pytest.mark.parametrize("status,success,allow",[
    ("BLOCKED",False,False),("BLOCKED",True,False),("DRY_RUN",False,False),
    ("NO_ACTION_REQUIRED",False,False),("NO_ACTION_REQUIRED",True,True),("PUBLISHED",True,True)])
def test_smart_refresh_instruction_requires_successful_handoff(status,success,allow,capsys):
    desktop.print_publish(PublishResult(status),refresh_succeeded=success)
    out=capsys.readouterr().out
    assert ("Open the Streamlit app" in out)==allow
    assert ("Do not run SMART REFRESH yet." in out)==(not allow)


def test_dependency_preflight_blocks_before_acquisition(monkeypatch,capsys):
    monkeypatch.setattr(desktop,"require_commissioner_writer",lambda name:None)
    monkeypatch.setattr(desktop,"build_smart_refresh_plan",lambda season:SimpleNamespace(current_gw=3))
    monkeypatch.setattr(desktop,"desktop_dependencies",lambda:["soccerdata"])
    monkeypatch.setattr(desktop,"_run",lambda *args:pytest.fail("acquisition must not run"))
    monkeypatch.setattr(sys,"argv",["desktop"])
    assert desktop.main()==2
    assert "requirements-desktop.txt" in capsys.readouterr().out


@pytest.mark.parametrize("expected,status",[(0,"NO_ACTION_REQUIRED"),(30,"CACHE_HIT")])
def test_understat_no_work_statuses(monkeypatch,capsys,expected,status):
    monkeypatch.setattr(understat,"refresh_plan",lambda season:{"would_acquire":0,"expected_completed_matches":expected})
    monkeypatch.setattr(understat.subprocess,"run",lambda *args,**kwargs:pytest.fail("no acquisition needed"))
    monkeypatch.setattr(sys,"argv",["understat"])
    assert understat.main()==0
    assert f'"status": "{status}"' in capsys.readouterr().out


def test_understat_success_requires_rechecked_coverage(monkeypatch,capsys):
    states=iter([{"would_acquire":10,"gameweeks":"1-3"},{"missing_matches":0}])
    monkeypatch.setattr(understat,"refresh_plan",lambda season:next(states))
    monkeypatch.setattr(understat,"require_commissioner_writer",lambda name:None)
    monkeypatch.setattr(understat.subprocess,"run",lambda *args,**kwargs:SimpleNamespace(returncode=0))
    monkeypatch.setattr(sys,"argv",["understat"])
    assert understat.main()==0
    assert '"status": "PASS"' in capsys.readouterr().out


def test_missing_fresh_stage_report_cannot_publish(tmp_path,monkeypatch):
    monkeypatch.setattr(desktop,"ROOT",tmp_path)
    monkeypatch.setattr(desktop,"require_commissioner_writer",lambda name:None)
    monkeypatch.setattr(desktop,"desktop_dependencies",lambda:[])
    monkeypatch.setattr(desktop,"build_smart_refresh_plan",lambda season:SimpleNamespace(current_gw=3,previous_gw=None))
    monkeypatch.setattr(desktop,"_run",lambda *args:0)
    monkeypatch.setattr(desktop,"atomic_json",lambda *args:None)
    def publish(*args,**kwargs):
        assert kwargs["refresh_status"]=="FAIL"
        return PublishResult("BLOCKED")
    monkeypatch.setattr(desktop,"publish_refresh",publish)
    monkeypatch.setattr(sys,"argv",["desktop"])
    assert desktop.main()==2
