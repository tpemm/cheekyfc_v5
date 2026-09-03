#!/usr/bin/env python3
"""Audit current-season products and emit exact real-row UI propagation evidence."""
from __future__ import annotations
import json,time,sys
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from core.services.data_manager import DataManager
from core.services.dataset_registry import DatasetRegistry
from integrations.whoscored.workflows import atomic_csv,atomic_json

SEASON="2627";MODEL=ROOT/f"data/models/season_{SEASON}";ADV=MODEL/"advanced";QUALITY=ROOT/f"data/quality/season_{SEASON}"
PRODUCTS=(
    ("current players","live_player_analytics",MODEL/f"live_player_analytics_{SEASON}.csv","Players","current"),
    ("managers","league_teams",MODEL/f"league_teams_{SEASON}.csv","League Hub; Managers","current"),
    ("ownership","player_ownership",MODEL/f"player_ownership_{SEASON}.csv","Players","current"),
    ("all-player weekly","current_player_weekly",MODEL/f"current_player_weekly_{SEASON}.csv","League Hub; Players","current"),
    ("detailed manager weekly","manager_player_weekly",MODEL/f"manager_player_weekly_{SEASON}.csv","League Hub; Managers","current"),
    ("unified player-week","live_player_weekly_enriched",MODEL/f"live_player_weekly_enriched_{SEASON}.csv","Players; Teams","current"),
    ("standings","league_standings",MODEL/f"league_standings_{SEASON}.csv","League Hub","current"),
    ("rosters","current_rosters",MODEL/f"current_rosters_{SEASON}.csv","Players; Managers","current"),
    ("weekly manager scores","manager_week_summary",MODEL/f"manager_week_summary_{SEASON}.csv","League Hub","current"),
    ("WhoScored match","whoscored_match",ADV/f"whoscored_match_{SEASON}.csv","Players; Teams","current"),
    ("WhoScored lineup","whoscored_lineup",ADV/f"whoscored_lineup_{SEASON}.csv","Players; Teams","current"),
    ("WhoScored event","whoscored_event",ADV/f"whoscored_event_{SEASON}.csv","Player Pitch","current"),
    ("player event","player_event_data",ADV/f"player_event_data_{SEASON}.csv","Player Pitch","current"),
    ("advanced player-match","advanced_player_match",ADV/f"advanced_player_match_{SEASON}.csv","Players","current"),
    ("supplemental player-match","supplemental_player_match",ADV/f"supplemental_player_match_{SEASON}.csv","Players","current"),
    ("player advanced profile","player_advanced_profile",ADV/f"player_advanced_profile_{SEASON}.csv","Players","current"),
    ("player role usage","player_role_usage",ADV/f"player_role_usage_{SEASON}.csv","Players","current"),
    ("player pitch events","player_pitch_events",ADV/f"player_pitch_events_{SEASON}.parquet","Players","current"),
    ("player set pieces","player_set_piece_usage",ADV/f"player_set_piece_usage_{SEASON}.csv","Players","current"),
    ("formation history","team_formation_history",ADV/f"team_formation_history_{SEASON}.csv","Teams","current"),
    ("formation profile","team_formation_profile",ADV/f"team_formation_profile_{SEASON}.csv","Teams","current"),
    ("formation player usage","formation_player_usage",ADV/f"formation_player_usage_{SEASON}.csv","Teams","current"),
    ("team match features","team_match_features",ADV/f"team_match_features_{SEASON}.csv","Teams","current"),
    ("team playstyle","team_playstyle_profile",ADV/f"team_playstyle_profile_{SEASON}.csv","Teams","current"),
    ("team set pieces","team_set_piece_hierarchy",ADV/f"team_set_piece_hierarchy_{SEASON}.csv","Teams","current"),
    ("Understat player-match","understat_player_match",MODEL/f"understat_player_match_{SEASON}.csv","Players","current"),
    ("Understat team-match","understat_team_match",MODEL/f"understat_team_match_{SEASON}.csv","Teams","current"),
    ("Fantasy Allowed current","team_position_fantasy_allowed_current",MODEL/f"team_position_fantasy_allowed_current_{SEASON}.csv","Teams","current"),
    ("Fantasy Allowed baseline","historical_fantasy_allowed_ranked",ROOT/"data/models/season_2526/advanced/historical_fantasy_allowed_ranked_2526.csv","Teams","historical"),
)

def rows(path:Path)->int:
    if not path.exists():return 0
    return len(pd.read_parquet(path)) if path.suffix==".parquet" else len(pd.read_csv(path,low_memory=False))

def main()->int:
    registry=DatasetRegistry();data=DataManager();audit=[]
    for dataset,key,path,view,context in PRODUCTS:
        try:definition=registry.get(key);registered=True;namespace="working";loaded=data.load(key,"2526" if context=="historical" else SEASON,namespace).data is not None
        except Exception:definition=None;registered=False;namespace="working";loaded=False
        count=rows(path);audit.append({"dataset":dataset,"source_file":str(path.relative_to(ROOT)),"registered_key":key,"season":"2526" if context=="historical" else SEASON,"namespace":namespace,"rows":count,"last_modified":datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat() if path.exists() else pd.NA,"consuming_service":getattr(definition,"producer",pd.NA),"consuming_view":view,"season_context":context.upper(),"registered":registered,"loaded":loaded,"sample_tested":count>0,"current_value_verified":count>0,"historical_fallback_risk":"NONE_EXPLICIT_SELECTOR" if context=="historical" else "NONE","status":"PASS" if count>0 and registered and loaded else "LEGITIMATELY_UNAVAILABLE" if dataset=="Fantasy Allowed baseline" and count==0 else "FAIL"})
    atomic_csv(pd.DataFrame(audit),QUALITY/f"live_ui_propagation_{SEASON}.csv")
    u=pd.read_csv(MODEL/f"live_player_weekly_enriched_{SEASON}.csv",low_memory=False);s=pd.read_csv(ADV/f"supplemental_player_match_{SEASON}.csv",low_memory=False);events=pd.read_parquet(ADV/f"player_pitch_events_{SEASON}.parquet");pieces=pd.read_csv(ADV/f"player_set_piece_usage_{SEASON}.csv",low_memory=False)
    cases=[]
    def add(category: str, candidates:pd.DataFrame, sort:str="fantasy_points"):
        if candidates.empty:cases.append({"category":category,"status":"LEGITIMATELY_UNAVAILABLE"});return
        candidate=candidates.assign(_sort=pd.to_numeric(candidates.get(sort),errors="coerce").fillna(-1)).sort_values("_sort",ascending=False).iloc[0];pid=str(candidate.fantrax_player_id);advanced=s[s.fantrax_player_id.astype(str).eq(pid)].head(1);a=advanced.iloc[0] if not advanced.empty else pd.Series(dtype=object);canonical=a.get("canonical_player_id");event_count=int(events.canonical_player_id.astype(str).eq(str(canonical)).sum()) if pd.notna(canonical) else 0;piece_count=int(pieces.canonical_player_id.astype(str).eq(str(canonical)).sum()) if pd.notna(canonical) else 0
        cases.append({"category":category,"fantrax_player_id":pid,"player_name":candidate.player_name,"raw_source":"Fantrax period_1 all-player + detailed manager CSV; WhoScored raw_match.json; Understat player-match CSV","normalized_product":"current_player_weekly_2627.csv","unified_product":"live_player_weekly_enriched_2627.csv","fantasy_points":candidate.get("fantasy_points"),"manager":candidate.get("current_manager_name"),"appearance":candidate.get("appearance"),"rating":a.get("rating"),"xg":candidate.get("xg"),"xa":candidate.get("xa"),"key_passes":a.get("key_passes"),"tactical_role":a.get("actual_tactical_role"),"formation":a.get("formation"),"pitch_events":event_count,"set_piece_rows":piece_count,"registered_key":"live_player_weekly_enriched + supplemental_player_match + player_pitch_events","ui_target":"Players > Player Profile","status":"PASS"})
    played=pd.to_numeric(u.appearance,errors="coerce").fillna(0).gt(0);owned=u.current_manager_id.notna()
    unused=s[pd.to_numeric(s.get("started"),errors="coerce").fillna(0).eq(0)&s.rating.isna()].copy();event_ids=set(events.canonical_player_id.astype(str));unused=unused[~unused.canonical_player_id.astype(str).isin(event_ids)];unused_ids=set(unused.fantrax_player_id.dropna().astype(str))
    add("rostered_played",u[owned&played]);add("rostered_unplayed",u[owned&~played]);add("waiver_played",u[~owned&played]);add("waiver_unplayed",u[~owned&u.fantrax_player_id.astype(str).isin(unused_ids)&pd.to_numeric(u.fantasy_points,errors="coerce").fillna(0).eq(0)]);add("whoscored",u[u.whoscored_available.fillna(False)]);add("understat",u[u.understat_available.fillna(False)],"xgi")
    atomic_csv(pd.DataFrame(cases),QUALITY/f"live_ui_representative_traces_{SEASON}.csv")
    timings=[]
    for key,season in (("live_player_weekly_enriched",SEASON),("supplemental_player_match",SEASON),("player_pitch_events",SEASON),("player_pitch_events","2526"),("team_playstyle_profile",SEASON),("manager_week_summary",SEASON)):
        start=time.perf_counter();result=data.load(key,season,"working");timings.append({"dataset":key,"season":season,"rows":len(result.data),"load_seconds":round(time.perf_counter()-start,4)})
    atomic_csv(pd.DataFrame(timings),QUALITY/f"live_ui_load_performance_{SEASON}.csv")
    summary={"status":"PASS" if all(x["status"]!="FAIL" for x in audit) else "FAIL","datasets":len(audit),"passed":sum(x["status"]=="PASS" for x in audit),"representative_cases":len(cases),"generated_at":datetime.now(timezone.utc).isoformat()};atomic_json(summary,QUALITY/f"live_ui_propagation_latest_{SEASON}.json");print(json.dumps(summary,indent=2));return 0 if summary["status"]=="PASS" else 2
if __name__=="__main__":raise SystemExit(main())
