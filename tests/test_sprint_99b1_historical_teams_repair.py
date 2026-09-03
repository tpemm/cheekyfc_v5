from pathlib import Path
import pandas as pd
from streamlit.testing.v1 import AppTest

from analytics.advanced_descriptive import add_plot_coordinates
from analytics.teams.research import prepare_team_historical_comparison,prepare_team_match_analysis,prepare_team_profile_percentiles
from core.services.data_manager import DataManager

ROOT=Path(__file__).resolve().parents[1]
HIST=ROOT/"data/models/season_2526/team_match_analytics_2526.csv"
FANTASY=ROOT/"data/models/season_2627/advanced/historical_fantasy_allowed_ranked_2627.csv"

def test_historical_fantasy_direct_and_registry_parse():
    direct=pd.read_csv(FANTASY);loaded=DataManager().load_frame("historical_fantasy_allowed_ranked","2627","working").data
    assert direct.shape==loaded.shape==(80,39)
    assert {"opponent_id","position_group","matches","points_allowed","ghost_allowed","assists_allowed","shots_on_target_allowed","accurate_crosses_allowed","tackles_won_allowed","interceptions_allowed","clearances_allowed","aerial_wins_allowed"}<=set(direct)

def test_historical_fantasy_grain_identity_and_null_zero_semantics():
    d=pd.read_csv(FANTASY)
    assert not d.duplicated(["opponent_id","position_group"]).any() and d.opponent_id.nunique()==20
    assert set(d.position_group)=={"GK","DEF","MID","FWD"} and len(d)==20*4
    assert d.accurate_crosses_allowed.isna().any() and d.goals_allowed.eq(0).any()

def test_historical_team_integrity_and_restored_event_spatial_xg():
    d=pd.read_csv(HIST,low_memory=False)
    assert (len(d),d.canonical_match_id.nunique(),d.club_id.nunique())==(760,380,20)
    for field in ("passes","successful_passes","pass_completion_pct","key_passes","crosses","successful_crosses","take_ons","successful_take_ons","shots","shots_on_target","tackles","successful_tackles","interceptions","clearances","blocks","recoveries","aerials","aerial_wins","final_third_event_share","box_event_share","event_activity_center_x","event_activity_center_y","defensive_event_activity_depth","xg","xga"):
        assert d[field].notna().all(),field
    assert d.home_away.isin(["H","A"]).all() and d.formation.notna().all() and d.manager_name.notna().all()

def test_historical_understat_is_reciprocal_and_real():
    d=pd.read_csv(HIST,low_memory=False)
    for _,g in d.groupby("canonical_match_id"):
        assert len(g)==2 and abs(g.iloc[0].xg-g.iloc[1].xga)<1e-9 and abs(g.iloc[1].xg-g.iloc[0].xga)<1e-9

def test_historical_profiles_and_splits_are_complete():
    season=pd.read_csv(ROOT/"data/models/season_2526/team_season_profile_2526.csv");manager=pd.read_csv(ROOT/"data/models/season_2526/team_manager_profile_2526.csv");formation=pd.read_csv(ROOT/"data/models/season_2526/team_formation_analytics_2526.csv");venue=pd.read_csv(ROOT/"data/models/season_2526/team_home_away_profile_2526.csv")
    assert len(season)==20 and season.matches.eq(38).all()
    assert manager.club_id.nunique()==formation.club_id.nunique()==venue.club_id.nunique()==20
    assert manager[manager.club_id.eq("nottingham_forest")].manager_name.nunique()==4
    assert set(venue.home_away)=={"H","A"}
    assert prepare_team_profile_percentiles(season,"arsenal")["Attacking Profile"]["Volume Percentile"].notna().all()

def test_set_piece_and_pitch_cache_evidence():
    pieces=pd.read_csv(ROOT/"data/models/season_2526/advanced/team_set_piece_hierarchy_2526.csv");pitch=pd.read_parquet(ROOT/"data/models/season_2526/advanced/player_pitch_events_2526.parquet",columns=["club_id","x","y","plot_x","plot_y"])
    assert len(pieces)==2438 and pieces.club_id.nunique()==20
    assert len(pitch)==571844 and pitch[["x","y","plot_x","plot_y"]].notna().all().all()
    prepared=add_plot_coordinates(pitch.head(1000))
    assert ((prepared.plot_x-(100-prepared.y)).abs()<1e-9).all() and ((prepared.plot_y-prepared.x).abs()<1e-9).all()

def test_bournemouth_bridge_coventry_and_historical_match_rows():
    d=pd.read_csv(HIST,low_memory=False);b=prepare_team_historical_comparison("afc_bournemouth",d);c=prepare_team_historical_comparison("coventry_city",d)
    assert b["available"] and len(b["matches"])==38 and b["historical_club_id"]=="bournemouth"
    assert not c["available"]
    assert len(prepare_team_match_analysis(d,"bournemouth")["rows"])==38

def test_compatibility_and_quality_artifacts():
    compatibility=pd.read_csv(ROOT/"data/quality/season_2627/team_metric_compatibility_2526_2627.csv");coverage=pd.read_csv(ROOT/"data/quality/season_2627/team_historical_coverage_99b1.csv");fantasy=pd.read_csv(ROOT/"data/quality/season_2627/historical_fantasy_allowed_99b1_validation.csv")
    assert {"current_available","historical_available","definition_same","source_current","source_historical","directly_comparable","reason_if_not"}<=set(compatibility)
    assert coverage.status.eq("AVAILABLE").all() and fantasy.validation_status.eq("PASS").all()

def test_repair_builder_is_cache_only_and_never_writes_protected_history():
    source=(ROOT/"scripts/build_historical_team_repair_99b1.py").read_text(encoding="utf-8")
    assert "selenium" not in source and "requests" not in source and "subprocess" not in source
    assert 'atomic_csv(base,MODEL/' in source and 'atomic_csv(out,APP_ADV/' in source
    assert 'atomic_csv(base,ROOT/"data/seasons/2526' not in source and 'atomic_csv(base,ROOT/"data/raw/whoscored/2526' not in source

def test_historical_teams_apptest_restored_tabs():
    app=AppTest.from_file(str(ROOT/"app.py"),default_timeout=60).run();app.sidebar.radio(key="page_nav").set_value("Teams").run();selector=next(x for x in app.selectbox if x.label=="Club");selector.set_value("AFC Bournemouth").run()
    next(x for x in app.toggle if x.label=="Compare to 2025/26").set_value(True).run();assert not app.exception
    assert any({"Metric","2026/27","2025/26"}<=set(getattr(x.value,"columns",[])) for x in app.dataframe)
    app.radio(key="team_match_season").set_value("2025/26 Historical").run();assert not app.exception
    assert any(len(x.value)==38 and {"Opponent","xG","xGA"}<=set(getattr(x.value,"columns",[])) for x in app.dataframe)
    app.radio(key="team_tactical_season").set_value("2025/26 Historical").run();assert not app.exception
    assert any("38 matches observed" in x.value for x in app.caption) and app.get("plotly_chart")
    app.radio(key="team_fantasy_season").set_value("2025/26 Historical").run();assert not app.exception
    assert any({"Position","Matches","FPts","Ghost","A","SOT","AC","TkW","Int","CLR","AER"}<=set(getattr(x.value,"columns",[])) for x in app.dataframe)
