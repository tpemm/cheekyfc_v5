from pathlib import Path
import json
import pandas as pd
import pytest

from fantrax.live.ghost import derive_return_ghost

ROOT=Path(__file__).resolve().parents[1]
MODEL=ROOT/"data/models/season_2627"

def derive(**overrides):
    values={"fantasy_points":20,"position":"M","goals":0,"assists":0,"clean_sheets":0,"appeared":True,"assist_semantics":"FANTRAX_FANTASY_ASSIST"};values.update(overrides);return derive_return_ghost(**values)

def test_exact_fantrax_always_wins():
    result=derive(exact_ghost=3,goals=2);assert result["ghost_points"]==3 and result["ghost_points_source"]=="FANTRAX_COMPONENT_DERIVED"

@pytest.mark.parametrize("position,expected",[("G",8),("D",11),("M",11),("F",11)])
def test_position_specific_goal_return(position,expected):assert derive(position=position,goals=1)["ghost_points"]==expected

@pytest.mark.parametrize("position,expected",[("G",13),("D",13),("M",14),("F",14)])
def test_position_specific_assist_return(position,expected):assert derive(position=position,assists=1)["ghost_points"]==expected

@pytest.mark.parametrize("position,expected",[("G",14),("D",14),("M",19),("F",20)])
def test_position_specific_clean_sheet(position,expected):assert derive(position=position,clean_sheets=1)["ghost_points"]==expected

def test_official_assist_fallback_is_labeled():assert derive(assists=1,assist_semantics="OFFICIAL_ASSIST")["ghost_points_source"]=="DERIVED_FROM_RETURNS_OFFICIAL_ASSIST_FALLBACK"
def test_no_returns_means_ghost_equals_fpts():assert derive(fantasy_points=11.5)["ghost_points"]==11.5
def test_explicit_zeroes_are_complete():assert derive(fantasy_points=0)["ghost_return_completeness"]==1
def test_unknown_return_evidence_is_not_zero_filled():
    result=derive(assists=pd.NA);assert pd.isna(result["ghost_points"]) and result["ghost_points_source"]=="PARTIAL_DERIVED"
def test_unplayed_does_not_get_ghost():assert pd.isna(derive(fantasy_points=0,appeared=False)["ghost_points"])

def test_peripherals_are_never_inputs_to_derivation():
    import inspect
    source=inspect.getsource(derive_return_ghost)
    for field in ("key_passes","shots_on_target","accurate_crosses","tackles_won","interceptions","clearances","aerials_won","dribbles"):assert field not in source

def test_jack_hinshelwood_general_formula():
    result=derive(fantasy_points=28.5,position="M",goals=2,assists=0,clean_sheets=1,assist_semantics="OFFICIAL_ASSIST")
    assert result["ghost_points"]==9.5 and result["ghost_goal_points_removed"]==18 and result["ghost_cs_points_removed"]==1

def test_real_jack_propagates_to_match_and_summary():
    match=pd.read_csv(MODEL/"current_player_match_log_2627.csv",low_memory=False).query("fantrax_player_id == '067ys'").iloc[0]
    summary=pd.read_csv(MODEL/"current_player_season_summary_2627.csv").query("fantrax_player_id == '067ys'").iloc[0]
    assert match.ghost_points==9.5 and match.ghost_points_source=="DERIVED_FROM_RETURNS_OFFICIAL_ASSIST_FALLBACK"
    assert summary.ghost_points==summary.ghost_points_per_game==summary.ghost_points_per_start==9.5
    assert round(summary.ghost_points_per_90,6)==round(9.5*90/69,6)

def test_exact_population_and_quality_outputs():
    report=pd.read_csv(ROOT/"data/quality/season_2627/ghost_return_derivation_validation_2627.csv")
    summary=json.loads((ROOT/"data/quality/season_2627/ghost_return_derivation_summary_2627.json").read_text())
    assert report.component_derived_ghost.notna().sum()==484 and summary["derived_ghost_observations"]==435 and summary["waiver_derived_observations"]==435

def test_historical_sources_are_outside_rebuild_scope():
    import inspect,scripts.build_current_player_participation as builder
    source=inspect.getsource(builder.main);assert "season_2526" not in source and "raw/whoscored/2526" not in source
