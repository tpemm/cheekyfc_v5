import json
from pathlib import Path
from uuid import uuid4

import pandas as pd

from fantrax.live.acquisition import PROVEN_ENDPOINTS, fetch_json
from fantrax.live.player_performance import (
    aggregate_player_window, completed_window, enrich_weekly,
    load_cached_weekly_exports, manager_player_weekly,
    normalize_weekly_export, stat_dictionary, weekly_validation,
)
from views.players import apply_live_window


def export_rows():
    rows=[]
    for period in range(1,12):
        rows.append({"fantrax_gw":period,"fantrax_player_id":"*p1*","player_name":"Player","team":"ARS","eligible_positions":"D,M","FPts":10+period,"gp":1,"gs":1,"Min":90,"G":0,"AT":0,"CS":1,"GA":0,"KP":period,"TkW":2,"AER":3,"SOT":1})
    rows.append({"fantrax_gw":12,"fantrax_player_id":"*p1*","player_name":"Player","FPts":99,"period_complete":False})
    return pd.DataFrame(rows)


def test_only_documented_proven_endpoints_are_registered():
    assert PROVEN_ENDPOINTS=={"league_metadata":"getLeagueInfo","standings":"getStandings","rosters":"getTeamRosters"}
    try: fetch_json("player_stats","league",opener=lambda *_a,**_k:None)
    except ValueError as exc: assert "No proven Fantrax endpoint" in str(exc)
    else: raise AssertionError("An undocumented player-stat endpoint was accepted")


def test_weekly_export_normalizes_ids_positions_stats_and_missing_fields():
    output=normalize_weekly_export(export_rows().iloc[:1],retrieved_at="now")
    row=output.iloc[0]
    assert row.fantrax_player_id=="p1" and row.fantrax_position=="D,M"
    assert row.fantasy_points==11 and row.key_passes==1 and row.aerials_won==3
    assert pd.isna(row.shots) and pd.isna(row.xg)
    assert row.ghost_points==5  # 11 - six clean-sheet points for a defender


def test_cache_only_loader_reads_no_network_and_empty_cache_is_valid():
    cache_root=Path(".test_artifacts")/f"player-performance-{uuid4().hex}"
    assert load_cached_weekly_exports(cache_root).empty
    root=cache_root/"player_stats"; root.mkdir(parents=True); export_rows().iloc[:2].to_csv(root/"periods.csv",index=False)
    result=load_cached_weekly_exports(cache_root)
    assert len(result)==2 and not result.duplicated(["fantrax_player_id","period"]).any()
    assert weekly_validation(result).status.eq("pass").all()


def test_windows_exclude_incomplete_and_label_actual_coverage():
    weekly=normalize_weekly_export(export_rows(),retrieved_at="now")
    assert not bool(weekly.loc[weekly.period.eq(12),"period_complete"].iat[0])
    last3,label=completed_window(weekly,"Last 3"); assert sorted(last3.period.unique())==[9,10,11] and label=="Last 3"
    last5,label=completed_window(weekly.iloc[:3],"Last 5"); assert label=="Last 5 (3 available)"
    last10,_=completed_window(weekly,"Last 10"); assert sorted(last10.period.unique())==list(range(2,12))


def test_season_aggregation_rates_reconcile_and_invalid_denominators_stay_blank():
    weekly=normalize_weekly_export(export_rows().iloc[:2],retrieved_at="now")
    result,_=aggregate_player_window(weekly,"Season"); row=result.iloc[0]
    assert row.fantasy_points==23 and row.appearance==2 and row.fantasy_points_per_game==11.5
    assert row.fantasy_points_per_start==11.5 and round(row.fantasy_points_per_90,2)==11.5
    weekly["start"]=0; weekly["minutes"]=0; invalid,_=aggregate_player_window(weekly,"Season")
    assert pd.isna(invalid.iloc[0].fantasy_points_per_start) and pd.isna(invalid.iloc[0].fantasy_points_per_90)


def test_registry_roster_and_manager_player_weekly_join_by_stable_keys():
    weekly=normalize_weekly_export(export_rows().iloc[:1],retrieved_at="now")
    registry=pd.DataFrame([{"fantrax_player_id":"p1","registry_player_id":"r1","canonical_name":"Canonical"}])
    rosters=pd.DataFrame([{"period":1,"fantrax_player_id":"p1","manager_id":"m1","manager_name":"Manager","roster_status":"ACTIVE","lineup_status":"ACTIVE"}])
    enriched=enrich_weekly(weekly,registry,pd.DataFrame(),rosters); manager=manager_player_weekly(enriched)
    assert enriched.iloc[0].registry_player_id=="r1" and manager.iloc[0].manager_id=="m1"


def test_manager_join_uses_period_roster_not_current_ownership():
    weekly=normalize_weekly_export(export_rows().iloc[:2],retrieved_at="now")
    registry=pd.DataFrame([{"fantrax_player_id":"p1","registry_player_id":"r1","canonical_name":"Canonical"}])
    rosters=pd.DataFrame([{"period":1,"fantrax_player_id":"p1","manager_id":"old","manager_name":"Old","roster_status":"ACTIVE","lineup_status":"ACTIVE"},{"period":2,"fantrax_player_id":"p1","manager_id":"new","manager_name":"New","roster_status":"RESERVE","lineup_status":"RESERVE"}])
    enriched=enrich_weekly(weekly,registry,pd.DataFrame([{"fantrax_player_id":"p1","current_manager_id":"new"}]),rosters)
    manager=manager_player_weekly(enriched).sort_values("period")
    assert manager.manager_id.tolist()==["old","new"] and manager.lineup_status.tolist()==["ACTIVE","RESERVE"]
    assert not manager.duplicated(["manager_id","fantrax_player_id","period"]).any()


def test_stat_dictionary_captures_ids_weights_and_export_classification():
    payload={"scoringSystem":{"scoringCategorySettings":[{"group":{"name":"Outfield"},"configs":[{"points":2,"position":{"shortName":"Default"},"scoringCategory":{"id":"6002","name":"Key Passes","shortName":"KP"}}]}]}}
    result=stat_dictionary(payload); row=result.iloc[0]
    assert row.fantrax_stat_id=="6002" and row.normalized_field=="key_passes" and row.scoring_weight==2
    assert row.source_class=="FANTRAX_PRIMARY_UNDERSTAT_FALLBACK" and row.endpoint=="getLeagueInfo scoringSystem"


def test_live_window_overlay_drives_current_fields_without_touching_history():
    weekly=normalize_weekly_export(export_rows().iloc[:3],retrieved_at="now")
    base=pd.DataFrame([{"fantrax_player_id":"p1","historical_fantasy_points":100,"current_fantasy_points":pd.NA}])
    output,label=apply_live_window(base,weekly,"Last 3")
    assert output.iloc[0].current_fantasy_points==36 and output.iloc[0].historical_fantasy_points==100
    assert label=="Last 3"


def test_real_audit_cache_contains_only_supported_response_shapes():
    league=json.loads(Path("data/raw/fantrax/2627/league/league_metadata_2627_latest.json").read_text(encoding="utf-8")); roster=json.loads(Path("data/raw/fantrax/2627/rosters/rosters_2627_period_01.json").read_text(encoding="utf-8"))
    assert "scoringSystem" in league and "playerInfo" in league
    assert set(next(iter(league["playerInfo"].values()))) <= {"eligiblePos","status"}
    item=next(iter(next(iter(roster["rosters"].values()))["rosterItems"]))
    assert set(item)=={"id","position","status"}
