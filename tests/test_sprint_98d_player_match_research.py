from pathlib import Path
import inspect
import numpy as np
import pandas as pd

from analytics.players.match_analysis import match_research_summary,prepare_match_research_frame,prepare_match_research_table,production_distribution

ROOT=Path(__file__).resolve().parents[1]

def rows(points,ghost=None,started=None):
    n=len(points);return pd.DataFrame({"fantasy_points":points,"ghost_points":ghost if ghost is not None else points,"started":started if started is not None else [1]*n,"minutes":[90]*n,"ghost_source":["FANTRAX"]*n})

def test_floor_ceiling_median_and_consistency():
    summary=match_research_summary(rows(list(range(1,11))))
    assert summary["floor"]==1.9 and summary["ceiling"]==9.1 and summary["median"]==5.5
    assert np.isclose(summary["std_dev"],np.std(range(1,11)))

def test_small_sample_suppresses_tail_statistics():
    summary=match_research_summary(rows([1,20,7,8,9]));assert pd.isna(summary["floor"]) and pd.isna(summary["ceiling"])

def test_substitute_excluded_from_start_distribution_but_retained():
    frame=rows([5,25],[5,0],[1,0]);distribution=production_distribution(frame)
    assert distribution.Starts.sum()==1 and distribution.set_index("Band").loc["<10","Starts"]==1
    assert len(prepare_match_research_table(frame.assign(period=[1,2])))==2

def test_return_dependency_requires_exact_ghost():
    assert match_research_summary(rows([20],[10]))["return_dependency"]==50
    frame=rows([20],[10]);frame["ghost_source"]="PARTIAL_DERIVED";assert pd.isna(match_research_summary(frame)["return_dependency"])

def test_zero_is_observed_and_missing_stays_missing_in_table():
    frame=rows([0],[0]).assign(period=1,xg=0.0,xa=np.nan)
    table=prepare_match_research_table(frame);assert table.loc[0,"FPts"]==0 and table.loc[0,"xG"]==0 and pd.isna(table.loc[0,"xA"])

def test_real_current_authority_and_provider_context():
    source=pd.read_csv(ROOT/"data/models/season_2627/current_player_match_log_2627.csv",low_memory=False)
    frame=prepare_match_research_frame(source,"06y9m",season="2026/27");row=frame.iloc[0]
    assert row.fantasy_points==36 and row.ghost_points==14 and row.started and row.minutes==77
    assert row.rating==8.49 and pd.notna(row.xg) and pd.notna(row.xa) and row.position=="D,M"

def test_real_historical_identity_and_match_continuity():
    source=pd.read_csv(ROOT/"data/models/season_2526/advanced/supplemental_player_match_2526.csv",low_memory=False)
    frame=prepare_match_research_frame(source,"06y9m",season="2025/26")
    assert len(frame)==36 and frame.match_id.nunique()==36 and frame.rating.notna().mean()>.8
    assert frame.xg.notna().any() and frame.xa.notna().any() and frame.fantasy_points.notna().any()

def test_no_dnp_or_future_zero_is_created():
    source=pd.DataFrame([{"fantrax_player_id":"p","canonical_match_id":"m","fantrax_period":2,"started":False,"fantrax_points":np.nan}])
    frame=prepare_match_research_frame(source,"p",season="2025/26");assert frame.appearance_type.isna().all() and frame.fantasy_points.isna().all()

def test_render_is_compact_and_never_loads_historical_events():
    import views.players as players
    source=inspect.getsource(players._performance_match_analysis);render=inspect.getsource(players.render).lower()
    assert "production_distribution" in source and "prepare_match_research_table" in source
    assert "whoscored_event" not in render and "player_event_data" not in render and "requests." not in render and "playwright" not in render
