from datetime import datetime,timezone
from types import SimpleNamespace

import pandas as pd

from core.models.operation_result import OperationResult
from core.services.core_refresh import run_core_refresh
from fantrax.live.season_state import live_period_phase,resolve_scoring_period_state
from scripts.refresh_live_fantrax import roster_periods
from fantrax.live.config import load_live_season_config
from pathlib import Path


def result(key,success=True,message="ok"):
    now=datetime.now(timezone.utc)
    return OperationResult(key,success,now,now,.1,0 if success else 1,message,error_type=None if success else "TestError",exception_message=None if success else message)


class Ops:
    def __init__(self,fail=()):self.fail=set(fail);self.calls=[]
    def run(self,key,season,parameters):self.calls.append(key);return result(key,key not in self.fail,"endpoint unavailable")


def periods():
    return pd.DataFrame({"period":range(1,39),"period_start":pd.date_range("2026-08-21",periods=38,freq="7D",tz="UTC"),"period_end":pd.date_range("2026-08-28",periods=38,freq="7D",tz="UTC")-pd.Timedelta(seconds=1)})


def test_registered_38_periods_do_not_make_gw38_current():
    state=resolve_scoring_period_state(periods(),now="2026-08-24T12:00:00Z")
    assert state.current_period==1 and state.latest_completed_period is None and state.next_period==2
    assert state.source=="league_period_window"


def test_live_period_phase_accepts_partial_results_without_inventing_elapsed_completion():
    fixtures=pd.DataFrame({"match_id":["a","b","c"],"fantrax_period":[1,1,1],"kickoff_time":["2026-08-21T12:00:00Z"]*3,"completed":[True,False,False]})
    assert live_period_phase(fixtures,1,now="2026-08-22T12:00:00Z")=={"state":"ACTIVE_PARTIAL","completed":1,"total":3}
    fixtures["completed"]=False
    assert live_period_phase(fixtures,1,now="2026-08-22T12:00:00Z")["state"]=="ACTIVE_AWAITING_RESULT_EVIDENCE"


def test_explicit_current_period_wins_over_period_inventory():
    state=resolve_scoring_period_state(periods(),league_payload={"currentScoringPeriod":2},now="2026-08-24T12:00:00Z")
    assert state.current_period==2 and state.source=="league_explicit_field"


def test_roster_request_uses_active_window_not_maximum_period():
    config=load_live_season_config(environ={"FANTRAX_LEAGUE_ID_2627":"league"},project_root=".test_artifacts/core_state_config")
    payload={"scoringPeriods":[{"number":int(r.period),"startDate":r.period_start.isoformat(),"endDate":r.period_end.isoformat()} for r in periods().itertuples()]}
    assert roster_periods(config,league_payload=payload,now="2026-08-24T12:00:00Z")== (1,)


def test_core_refresh_success_partial_and_critical_failure():
    assert run_core_refresh(Ops(),"2627").status=="SUCCESS"
    partial=Ops({"refresh_live_standings"});run=run_core_refresh(partial,"2627")
    assert run.status=="PARTIAL" and "build_live_season_datasets" in partial.calls
    critical=Ops({"refresh_live_league_metadata"});run=run_core_refresh(critical,"2627")
    assert run.status=="FAILED" and critical.calls==["refresh_live_league_metadata"]


def test_hosted_core_refresh_has_no_browser_acquisition_path():
    sources="\n".join(Path(path).read_text(encoding="utf-8") for path in ("core/services/core_refresh.py","scripts/refresh_live_fantrax.py"))
    assert all(token not in sources.lower() for token in ("selenium","chromedriver","whoscored","weekly_advanced_refresh"))
