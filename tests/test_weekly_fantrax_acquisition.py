from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest

from fantrax.live.player_performance import aggregate_player_window,load_cached_weekly_exports, normalize_weekly_export
from fantrax.live.pipeline import _weekly_score_reconciliation
from fantrax.live.weekly_acquisition import (
    commit_period, normalize_period_exports, period_state, plan_periods,
    read_period_metadata, refresh_weekly_stats, valid_cached_period,
    weekly_period_status,
)


NOW=datetime(2026,9,2,tzinfo=timezone.utc)


def league():
    return {"teamInfo":{"t1":{"id":"t1","name":"Manager"}},"scoringPeriods":[
        {"number":1,"startDate":"2026-08-21T15:00:00-0400","endDate":"2026-08-28T14:59:59-0400"},
        {"number":2,"startDate":"2026-08-28T15:00:00-0400","endDate":"2026-09-04T14:59:59-0400"},
        {"number":3,"startDate":"2026-09-04T15:00:00-0400","endDate":"2026-09-11T14:59:59-0400"},
    ]}


def raw_root(): return Path(".test_artifacts")/f"weekly-acquisition-{uuid4().hex}"/"data"/"raw"/"fantrax"/"2627"


def all_players(points="10.5"):
    return f"ID,Player,Team,Position,Opponent,FPts\n*p1*,Known,ARS,\"D,M\",CHE,{points}\n*p2*,Free,LIV,F,ARS,0\n".encode()


def team_export(key_passes="2"):
    return ('"","Outfielder"\nID,Pos,Player,Team,Eligible,Status,Opponent,Fantasy Points,GP,GS,Min,CS,GA,YC,RC,TkW,DIS,G,KP,AT,Int,CLR,CoS,AER,OG,SOT,AC,BS,PKM\n'
            f'*p1*,D,Known,ARS,"D,M",Act,CHE,10.5,1,1,90,1,0,0,0,3,0,0,{key_passes},1,2,4,1,5,0,1,2,1,0\n').encode()


def fetched(**_kwargs): return all_players(),{"t1":("Manager",team_export())}


def test_legacy_acquisition_contract_is_audited_before_reuse():
    all_source=Path("fantrax/scraping/scrape_allplayers_weekly_fantrax.py").read_text(encoding="utf-8")
    roster_source=Path("fantrax/scraping/scrape_team_rosters_weekly_fantrax.py").read_text(encoding="utf-8")
    parser_source=Path("fantrax/analytics/core/build_master_weekly.py").read_text(encoding="utf-8")
    assert "playwright" in all_source and "Download all as CSV" in all_source and "fantrax_auth_state.json" in all_source
    assert "statsType=1" in roster_source and "Goalkeeper" in parser_source and "Outfielder" in parser_source


def test_period_state_and_incremental_plan_use_authoritative_boundaries():
    current,completed=period_state(league(),now=NOW); assert current==2 and completed==[1]
    plan=plan_periods(league(),raw_root(),now=NOW); assert plan["targets"]==[1,2]


def test_preseason_is_successful_and_performs_no_fetch():
    called=[]; result=refresh_weekly_stats(league(),league_id="league",raw_root=raw_root(),project_root=Path.cwd(),now=datetime(2026,8,1,tzinfo=timezone.utc),fetcher=lambda **kwargs:called.append(kwargs))
    assert result["status"]=="PRESEASON_NO_PLAYER_STATS" and called==[]


def test_period_export_retains_ids_positions_points_advanced_events_and_zero():
    result=normalize_period_exports(all_players(),{"t1":("Manager",team_export())},period=1); known=result.set_index("fantrax_player_id").loc["p1"]; free=result.set_index("fantrax_player_id").loc["p2"]
    assert known.fantrax_position=="D,M" and known.fantasy_points==10.5 and known.key_passes==2 and known.tackles_won==3
    assert pd.isna(free.fantasy_points) and pd.isna(free.key_passes)


def test_partial_period_preserves_observed_zero_for_played_club_and_na_for_unplayed_club():
    players=("ID,Player,Team,Position,Opponent,FPts\n*p1*,Starter,ARS,M,CHE,5\n*p2*,Bench,ARS,M,CHE,0\n*p3*,Future,LIV,M,EVE,0\n").encode()
    team=('"","Outfielder"\nID,Pos,Player,Team,Eligible,Status,Opponent,Fantasy Points,GP,GS,Min\n*p1*,M,Starter,ARS,M,Act,CHE,5,1,1,90\n*p2*,M,Bench,ARS,M,Res,CHE,0,0,0,0\n').encode()
    result=normalize_period_exports(players,{"t1":("Manager",team)},period=1).set_index("fantrax_player_id")
    assert result.loc["p2","fantasy_points"]==0
    assert pd.isna(result.loc["p3","fantasy_points"]) and pd.isna(result.loc["p3","appearance"])
    normalized=normalize_weekly_export(result.reset_index(),retrieved_at="now",period=1);normalized["period_complete"]=False
    totals,_=aggregate_player_window(normalized,"Season",include_partial=True)
    assert set(totals.fantrax_player_id)=={"p1","p2","p3"} and totals.set_index("fantrax_player_id").loc["p1","fantasy_points"]==5


def test_invalid_empty_or_bad_response_never_overwrites_valid_cache():
    root=raw_root(); first=commit_period(root,1,all_players(),{"t1":("Manager",team_export())},finalized=True); path=root/"player_stats"/"period_01"/"weekly_player_stats.csv"; before=path.read_bytes()
    with pytest.raises(ValueError): commit_period(root,1,b"ID,Player,FPts\n",{},finalized=True)
    assert path.read_bytes()==before and read_period_metadata(root,1)["checksum"]==first["checksum"]


def test_finalized_period_skips_backfill_and_force_is_explicit():
    root=raw_root(); commit_period(root,1,all_players(),{"t1":("Manager",team_export())},finalized=True)
    assert valid_cached_period(root,1) and plan_periods(league(),root,mode="backfill",now=NOW)["targets"]==[]
    assert plan_periods(league(),root,mode="force_current",period=1,force=True,now=NOW)["targets"]==[1]


def test_missing_completed_period_acquires_and_backfill_is_idempotent():
    root=raw_root(); calls=[]
    def fetch(**kwargs): calls.append(kwargs["period"]); return fetched()
    result=refresh_weekly_stats(league(),league_id="league",raw_root=root,project_root=Path.cwd(),mode="backfill",now=NOW,fetcher=fetch)
    assert result["status"]=="WEEKLY_STATS_UPDATED" and calls==[1]
    second=refresh_weekly_stats(league(),league_id="league",raw_root=root,project_root=Path.cwd(),mode="backfill",now=NOW,fetcher=fetch)
    assert second["status"]=="NO_NEW_WEEKLY_DATA" and calls==[1]


def test_cache_loader_reads_only_valid_canonical_period_files_and_marks_final():
    root=raw_root(); commit_period(root,1,all_players(),{"t1":("Manager",team_export())},finalized=True,retrieved_at="now")
    weekly=load_cached_weekly_exports(root); row=weekly.set_index("fantrax_player_id").loc["p1"]
    assert len(weekly)==2 and row.period==1 and row.fantasy_points==10.5 and row.key_passes==2 and bool(row.period_complete)
    assert row.current_manager_id=="t1" and row.lineup_status=="Act"
    assert not weekly.duplicated(["fantrax_player_id","period"]).any()


def test_quality_period_status_distinguishes_final_missing_and_current():
    root=raw_root(); commit_period(root,1,all_players(),{"t1":("Manager",team_export())},finalized=True)
    status=weekly_period_status(root,league(),now=NOW).set_index("period")
    assert status.loc[1,"status"]=="ACQUIRED" and bool(status.loc[1,"finalized"])
    assert status.loc[2,"status"]=="PERIOD_NOT_COMPLETED"


def test_completed_empty_refresh_preserves_existing_models_and_cache():
    root=raw_root(); commit_period(root,1,all_players(),{"t1":("Manager",team_export())},finalized=True); before=(root/"player_stats"/"period_01"/"weekly_player_stats.csv").read_bytes()
    with pytest.raises(ValueError): refresh_weekly_stats(league(),league_id="league",raw_root=root,project_root=Path.cwd(),mode="force_current",period=1,force=True,now=NOW,fetcher=lambda **_kwargs:(b"ID,Player,FPts\n",{}))
    assert (root/"player_stats"/"period_01"/"weekly_player_stats.csv").read_bytes()==before


def test_known_2526_goalkeeper_ghost_reconciles_to_proven_export():
    all_bytes=Path("data/raw/fantrax/all_players_weekly/Fantrax_WeeklyStats_AvailablePlayers_GW38.csv").read_bytes(); teams={}
    for path in Path("data/raw/fantrax/team_rosters_weekly").glob("*_GW38.csv"):
        manager=path.stem.split("_")[2]; teams[manager]=(manager,path.read_bytes())
    raw=normalize_period_exports(all_bytes,teams,period=38); weekly=normalize_weekly_export(raw,retrieved_at="historical")
    pickford=weekly.set_index("fantrax_player_id").loc["032f9"]
    assert pickford.fantasy_points==3.5 and pickford.ghost_points==3.5


def test_manager_score_reconciliation_reports_difference_without_correction():
    players=pd.DataFrame([{"period":1,"manager_name":"Manager","lineup_status":"ACTIVE","fantasy_points":10},{"period":1,"manager_name":"Manager","lineup_status":"RESERVE","fantasy_points":5}])
    official=pd.DataFrame([{"period":1,"manager":"Manager","total_score":11}]); result=_weekly_score_reconciliation(players,official).iloc[0]
    assert result.normalized_active_points==10 and result.difference==-1 and result.status=="review"
