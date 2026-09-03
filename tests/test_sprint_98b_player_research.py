from pathlib import Path
import inspect
import pandas as pd
import pytest
from analytics.players.research_overview import ATTACKING_AXES,DEFENSIVE_AXES,FANTASY_AXES,KPI_FIELDS,fixed_radar_records,next_fixtures,overview_gameweek_table,overlay_current_ownership,overlay_current_summary,resolve_metric

ROOT=Path(__file__).resolve().parents[1];MODEL=ROOT/"data/models/season_2627"

def test_fixed_kpis():assert [x[0] for x in KPI_FIELDS]==["SEASON POINTS","AVG PTS/GW","AVG PTS/START","GHOST PTS/START","GAMES PLAYED / STARTS","OWNERSHIP","xG/90","xA/90"]
def test_fantasy_axes():assert [x[0] for x in FANTASY_AXES]==["Season Points","Avg Pts/Start","Ghost Pts/Start","Games Started"]
def test_attacking_axes():assert [x[0] for x in ATTACKING_AXES]==["Goals","Assists","Key Passes","Shots on Target","Successful Dribbles"]
def test_defensive_axes():assert [x[0] for x in DEFENSIVE_AXES]==["Tackles Won","Interceptions","Clearances","Aerials Won","Clean Sheets"]
def test_fantrax_zero_wins():assert resolve_metric(fantrax_value=0,fantrax_observed=True,derived_value=9)["value"]==0
def test_validated_fallback():assert resolve_metric(fantrax_value=pd.NA,fantrax_observed=False,derived_value=3)["authority"]=="VALIDATED_DERIVED"
def test_caveated_fallback():assert resolve_metric(fantrax_value=pd.NA,fantrax_observed=False,approximate_value=2)["authority"]=="CAVEATED_PROVIDER"
def test_missing_stays_missing():assert pd.isna(resolve_metric(fantrax_value=pd.NA,fantrax_observed=False)["value"])
def test_history_never_fills_current():
    f=pd.DataFrame([{"fantrax_player_id":"p","historical_points_per_start":10,"current_points_per_start":99}]);s=pd.DataFrame([{"fantrax_player_id":"p","fantasy_points_per_start":pd.NA}]);assert pd.isna(overlay_current_summary(f,s).iloc[0].current_points_per_start)
def test_add_drop_refresh_overlay():
    f=pd.DataFrame([{"fantrax_player_id":"a","current_manager_name":"Old","available":False},{"fantrax_player_id":"b","current_manager_name":pd.NA,"available":True}]);o=pd.DataFrame([{"fantrax_player_id":"a","current_manager_name":pd.NA,"available":True},{"fantrax_player_id":"b","current_manager_name":"New","available":False}]);r=overlay_current_ownership(f,o).set_index("fantrax_player_id");assert r.loc["a","available"] and pd.isna(r.loc["a","current_manager_name"]);assert r.loc["b","current_manager_name"]=="New" and not r.loc["b","available"]

def real():return overlay_current_summary(pd.read_csv(MODEL/"live_player_analytics_2627.csv",low_memory=False),pd.read_csv(MODEL/"current_player_season_summary_2627.csv"))
@pytest.mark.parametrize("pid,gp,starts,minutes",[("06y9m",2,2,167),("05tre",2,2,180),("07877",2,2,165)])
def test_real_participation(pid,gp,starts,minutes):
    r=real()[lambda x:x.fantrax_player_id.astype(str).eq(pid)].iloc[0];assert (r.current_appearances,r.current_starts,r.current_minutes)==(gp,starts,minutes);assert pd.notna(r.current_points_per_start)
def test_mamadou_name():assert real()[lambda x:x.fantrax_player_id.astype(str).eq("07877")].iloc[0].player_name=="Mamadou Sangare"
def test_waiver_whoscored_understat():
    r=pd.read_csv(MODEL/"current_player_match_log_2627.csv",low_memory=False).query("fantrax_player_id == '070hq'").iloc[0];assert pd.isna(r.current_manager_id) and pd.notna(r.whoscored_player_id) and pd.notna(r.xg)
def test_waiver_whoscored_only():
    r=pd.read_csv(MODEL/"current_player_match_log_2627.csv",low_memory=False).query("fantrax_player_id == '062ct'").iloc[0];assert pd.isna(r.current_manager_id) and pd.notna(r.whoscored_player_id) and pd.isna(r.xg)
def test_unplayed_has_missing_advanced_rates():
    r=real()[lambda x:x.fantrax_player_id.astype(str).eq("02lk5")].iloc[0];assert r.current_appearances==0 and pd.isna(r.current_points_per_start) and pd.isna(r.current_xg)
def test_position_cohort():
    f=pd.DataFrame([{"fantrax_player_id":"p1","fantrax_position":"D,M","current_fantasy_points":1},{"fantrax_player_id":"p2","fantrax_position":"D","current_fantasy_points":2},{"fantrax_player_id":"p3","fantrax_position":"M","current_fantasy_points":3}]);records,label=fixed_radar_records(f,f.iloc[0],FANTASY_AXES,False);assert label=="defenders" and records[0]["metrics"][0]["peer_count"]==2
def test_next_five_existing_fdr():
    r=next_fixtures(pd.read_csv(MODEL/"team_fixtures_2627.csv"),"brentford");assert len(r)==5 and list(r)==["GW","Opponent","H/A","FDR"]
def test_gameweek_canonical_fields():
    r=overview_gameweek_table(pd.read_csv(MODEL/"current_player_match_log_2627.csv",low_memory=False),"05tre",pd.read_csv(MODEL/"team_fixtures_2627.csv")).iloc[0];assert (r.GP,r.Start,r.Minutes)==(1,1,90)
def test_assist_and_ghost_semantics():
    r=pd.read_csv(MODEL/"current_player_match_log_2627.csv",low_memory=False).query("fantrax_player_id == '05tre'").iloc[0];assert r.assist_semantics=="OFFICIAL_ASSIST" and r.ghost_points_source.startswith("DERIVED_FROM_RETURNS")
def test_no_render_acquisition():
    import views.players as m;source=inspect.getsource(m.render).lower();assert "playwright" not in source and "requests." not in source
def test_explicit_history_toggle_and_current_default():
    import views.players as m;source=inspect.getsource(m._compact_profile);assert 'toggle("Compare to 2025/26"' in source and 'Historical Comparison' not in source and "2026/27 Player Research" in source
def test_historical_events_remain_selected_lazily():
    import views.players as m;source=inspect.getsource(m.render);assert source.count("get_historical_player_advanced") == 1 and 'season="2627"' in source
def test_real_audit_passes():
    a=pd.read_csv(ROOT/"data/quality/season_2627/player_overview_98b_validation_2627.csv");assert len(a)==6 and a.validation_status.eq("PASS").all()
