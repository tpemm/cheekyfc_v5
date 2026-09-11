from unittest.mock import MagicMock
import pandas as pd
from pandas.testing import assert_frame_equal

from fantrax.live.manager_decisions import decision_summary, final_lineup, timeline
from views.manager_decision_review import render_review


def fixtures():
    canonical=pd.DataFrame([dict(manager_id="m1",period=2,fantrax_player_id="p1",player_name="Player",lineup_status="RESERVE"),
                            dict(manager_id="m1",period=2,fantrax_player_id="p2",player_name="Other",lineup_status="ACTIVE")])
    teams=pd.DataFrame([dict(manager_id="m1",manager_name="Manager"),dict(manager_id="m2",manager_name="Other")])
    common=dict(manager_id="m1",raw_manager_name="Manager",gameweek=2,player_id="p1",raw_player_name="Player",club="LIV",position="M")
    moves=pd.DataFrame([{**common,"lineup_event_id":f"l{i}","event_timestamp":f"2026-08-25T11:{i:02}:00-05:00","from_roster_state":a,"to_roster_state":b}
        for i,(a,b) in enumerate([("RESERVE","ACTIVE"),("ACTIVE","RESERVE"),("RESERVE","ACTIVE")])])
    tx=pd.DataFrame([{**common,"transaction_event_id":f"t{i}","event_timestamp":"2026-08-25T10:00:00-05:00","normalized_transaction_type":typ,"raw_transaction_type":typ.title(),"transaction_group_id":"candidate-1"}
        for i,typ in enumerate(["CLAIM","DROP"])])
    return canonical,tx,moves,teams


def test_canonical_authority_and_descriptive_summary_preserve_inputs():
    canonical,tx,moves,teams=fixtures();before=canonical.copy(deep=True);before_moves=moves.copy(deep=True)
    summary,events=decision_summary(canonical,tx,moves,teams)
    row=summary[summary.manager_id.eq("m1")].iloc[0]
    assert row.final_active_count==1 and row.final_reserve_count==1
    assert row.lineup_event_count==3 and row.unique_players_tinkered==1 and row.repeated_tinkers==1
    assert row.claim_count==1 and row.drop_count==1 and row.transaction_group_count==1
    assert row.canonical_lineup_source=="manager_player_weekly"
    assert final_lineup(canonical,"m1",2).iloc[0].lineup_status=="RESERVE"
    assert events.iloc[-1].to_state=="ACTIVE"
    assert_frame_equal(canonical,before);assert_frame_equal(moves,before_moves)


def test_timeline_preserves_repeated_actions_groups_timestamps_and_exported_gw():
    canonical,tx,moves,teams=fixtures()
    events=timeline(tx.iloc[::-1],moves.iloc[::-1])
    assert events.source_event_id.tolist()==["t0","t1","l0","l1","l2"]
    assert events.transaction_group_id.dropna().tolist()==["candidate-1"]*2
    assert events.event_timestamp.iloc[-1]==moves.event_timestamp.iloc[-1]
    assert events.gameweek.eq(2).all() and events.player_id.eq("p1").all() and events.manager_id.eq("m1").all()
    assert not any("lock" in column or "deadline" in column for column in events)


def test_zero_events_and_unknown_coverage_do_not_fabricate_activity_or_final_lineup():
    canonical,tx,moves,teams=fixtures()
    summary,events=decision_summary(canonical,tx,moves,teams)
    row=summary[summary.manager_id.eq("m2")].iloc[0]
    assert row.lineup_event_count==0 and row.transaction_event_count==0
    assert row.lineup_coverage_status=="NO_EVENT_COVERAGE" and pd.isna(row.final_active_count)
    coverage=pd.DataFrame([dict(manager_id="m2",gameweek=2,lineup_complete=True,transaction_complete=True)])
    known,_=decision_summary(canonical,tx,moves,teams,coverage=coverage)
    assert known[known.manager_id.eq("m2")].iloc[0].lineup_coverage_status=="NO_ACTIVITY"
    empty,_=decision_summary(canonical,pd.DataFrame(),pd.DataFrame(),teams)
    assert empty[empty.manager_id.eq("m1")].iloc[0].final_active_count==1


def test_review_renders_canonical_lineup_summary_and_timeline():
    canonical,tx,moves,teams=fixtures();ui=MagicMock();ui.selectbox.return_value=2
    render_review(ui,canonical,tx,moves,teams,"m1")
    assert [call.args[0] for call in ui.subheader.call_args_list]==["Final lineup","Decision summary","Activity timeline"]
    active=ui.dataframe.call_args_list[0].args[0]
    assert active.fantrax_player_id.tolist()==["p2"]
    assert len(ui.dataframe.call_args_list[-1].args[0])==5


def test_current_examples():
    from pathlib import Path
    root=Path("data/models/season_2627")
    load=lambda key:pd.read_csv(root/f"{key}_2627.csv",low_memory=False)
    summary,events=decision_summary(load("manager_player_weekly"),load("transaction_events"),load("lineup_events"),load("league_teams"))
    assert len(summary)==48 and len(events)==571
    assert summary.loc[summary.manager_id.eq("cjn4stydmrp1z5vp"),"lineup_event_count"].sum()==0
    assert summary.loc[summary.manager_id.eq("h1vdt8ynmrp1z5vp") & summary.gameweek.eq(1),"lineup_event_count"].iloc[0]==28
    diego=events[events.player_name.eq("Diego Gomez") & events.gameweek.eq(2) & events.event_category.eq("LINEUP")]
    assert diego.to_state.tolist()==["ACTIVE","RESERVE","ACTIVE"]
    assert summary.loc[summary.gameweek.eq(4),"final_active_count"].isna().all()
    assert summary.loc[summary.gameweek.le(3),"final_active_count"].eq(11).all()
    from fantrax.live.manager_decisions import ACTIVE_STATUSES
    canonical=load("manager_player_weekly")
    active=canonical[canonical.lineup_status.str.upper().isin(ACTIVE_STATUSES)]
    league=load("league_active_player_weekly")
    keys=["manager_id","period","fantrax_player_id"]
    assert set(active[keys].itertuples(index=False,name=None))==set(league[keys].itertuples(index=False,name=None))
