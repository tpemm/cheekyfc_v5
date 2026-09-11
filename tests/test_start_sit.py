import json
from pathlib import Path
from unittest.mock import MagicMock
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from fantrax.live.start_sit import analyze_start_sit, unique_legal_pairing, points_left, ReconciliationError
from fantrax.live.league_lineups import optimal_legal_xi, manager_performance_weeks
from views.manager_decision_review import render_review


def inputs():
    positions=["G"]+["D"]*4+["M"]*4+["F"]*2
    roster=pd.DataFrame([dict(manager_id="m1",period=1,fantrax_player_id=f"p{i:02}",player_name=f"Player {i}",
        fantrax_position=pos,lineup_status="ACTIVE",fantasy_points=10.,ghost_points=5.) for i,pos in enumerate(positions)])
    bench=pd.DataFrame([dict(manager_id="m1",period=1,fantrax_player_id="bench",player_name="Bench",fantrax_position="D,M",
        lineup_status="RESERVE",fantasy_points=20.,ghost_points=5.)])
    roster=pd.concat([roster,bench],ignore_index=True)
    weekly=roster.rename(columns={"manager_id":"current_manager_id"})
    weeks=pd.DataFrame([dict(manager_id="m1",manager_name="Manager",period=1,result="W",fantasy_points=110.)])
    return roster,weekly,weeks


def test_reuses_solver_and_reconciles_actual_optimal_and_bench():
    roster,weekly,weeks=inputs();before=roster.copy(deep=True)
    summary,decisions=analyze_start_sit(roster,weekly,weeks);row=summary.iloc[0]
    expected,ids=optimal_legal_xi(roster)
    assert row.actual_xi_points==110 and row.optimal_xi_points==expected==120
    assert row.points_left_on_bench==10 and row.bench_points_total==20
    assert row.lineup_efficiency_pct==pytest.approx(110/120*100)
    actual=set(roster.loc[roster.lineup_status.eq("ACTIVE"),"fantrax_player_id"])
    assert set(json.loads(row.actual_player_ids))==actual
    assert set(json.loads(row.optimal_player_ids))==set(ids)
    assert row.retained_selection_count==10 and row.decision_swap_count==1
    missed=decisions[decisions.decision_type.eq("MISSED_START")].iloc[0]
    assert missed.alternative_player_id=="bench" and missed.point_difference==10
    assert row.manager_id=="m1" and row.gameweek==1
    assert_frame_equal(roster,before)


def test_ambiguous_legal_pairing_retains_structural_sets():
    roster,weekly,weeks=inputs()
    extra=roster.iloc[-1].copy();extra.fantrax_player_id="bench2";extra.fantasy_points=21.
    roster=pd.concat([roster,pd.DataFrame([extra])],ignore_index=True)
    weekly=roster.rename(columns={"manager_id":"current_manager_id"})
    summary,decisions=analyze_start_sit(roster,weekly,weeks)
    structural=decisions[decisions.decision_type.eq("STRUCTURAL")].iloc[0]
    assert pd.isna(structural.started_player_id) and pd.isna(structural.alternative_player_id)
    assert len(json.loads(structural.displaced_players))==2
    assert {x["player_id"] for x in json.loads(structural.missed_players)}=={"bench","bench2"}
    assert summary.iloc[0].points_left_on_bench==21


def test_roundoff_floor_and_substantive_conflict_stop():
    assert points_left(10.,10.+1e-10)==0
    with pytest.raises(ReconciliationError):points_left(10,11)
    roster,weekly,weeks=inputs();roster.loc[0,"fantasy_points"]=11.
    with pytest.raises(ReconciliationError,match="differs"):analyze_start_sit(roster,weekly,weeks)


def test_unfinalized_week_excluded_and_zero_point_equivalents():
    roster,weekly,weeks=inputs();future=roster.assign(period=4)
    roster=pd.concat([roster,future]);weekly=pd.concat([weekly,weekly.assign(period=4)])
    weeks=pd.concat([weeks,weeks.assign(period=4,result=None)])
    summary,_=analyze_start_sit(roster,weekly,weeks)
    assert summary.gameweek.tolist()==[1]
    roster,weekly,weeks=inputs();roster.fantasy_points=0.;weekly.fantasy_points=0.
    summary,decisions=analyze_start_sit(roster,weekly,weeks)
    assert summary.points_left_on_bench.iloc[0]==0 and pd.isna(summary.lineup_efficiency_pct.iloc[0])


def test_current_data_reconciles_existing_efficiency():
    root=Path("data/models/season_2627")
    load=lambda key:pd.read_csv(root/f"{key}_2627.csv",low_memory=False)
    roster,weekly,weeks=load("manager_player_weekly"),load("current_player_weekly"),load("manager_week_summary")
    summary,decisions=analyze_start_sit(roster,weekly,weeks)
    assert len(summary)==36 and set(summary.gameweek)=={1,2,3}
    reference=manager_performance_weeks(weeks,weekly)
    for row in summary.itertuples():
        ref=reference[reference.manager_id.eq(row.manager_id)&reference.period.eq(row.gameweek)].iloc[0]
        assert row.actual_xi_points==pytest.approx(ref.starter_points)
        assert row.optimal_xi_points==pytest.approx(ref.optimal_xi_points)
        assert row.lineup_efficiency_pct==pytest.approx(ref.lineup_efficiency_pct)
    assert summary.points_left_on_bench.sum()==pytest.approx(516.)


def test_review_places_outcome_before_lineup_and_context():
    roster,weekly,weeks=inputs();summary,differences=analyze_start_sit(roster,weekly,weeks)
    ui=MagicMock();ui.selectbox.return_value=1
    teams=pd.DataFrame([dict(manager_id="m1",manager_name="Manager")])
    render_review(ui,roster,pd.DataFrame(),pd.DataFrame(),teams,"m1",summary,differences)
    headings=[call.args[0] for call in ui.subheader.call_args_list]
    assert headings[:3]==["Final XI outcome","Start / sit differences","Final lineup"]
