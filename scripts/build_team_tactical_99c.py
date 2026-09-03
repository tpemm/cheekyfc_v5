#!/usr/bin/env python3
"""Calibrate team_tactical_v1 on 2025/26 and apply it cache-only to 2026/27."""
from __future__ import annotations
import argparse,json,sys,time
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from analytics.teams.tactical import RATE_FEATURES,EFFECTIVENESS_FEATURES,METHODOLOGY_VERSION,build_profiles,empirical_percentile,load_methodology,opponent_context,pairwise_correlations,sample_size_analysis,spatial_match_features,stability_analysis,tactical_match_features,trait_records
from core.services.historical_advanced import historical_club_id
from integrations.whoscored.workflows import atomic_csv,atomic_json

CONFIG=ROOT/"config/team_tactical_traits.json";QUALITY=ROOT/"data/quality/season_2627"

def load_inputs(season:str)->tuple[pd.DataFrame,pd.DataFrame]:
    model=ROOT/f"data/models/season_{season}";matches=pd.read_csv(model/f"team_match_analytics_{season}.csv",low_memory=False)
    events=pd.read_parquet(model/"advanced"/f"player_pitch_events_{season}.parquet") if season=="2526" else pd.read_csv(model/"advanced"/f"whoscored_event_{season}.csv",low_memory=False)
    return matches,events

def add_match_baseline_percentiles(frame:pd.DataFrame,baseline:pd.DataFrame)->pd.DataFrame:
    out=frame.copy()
    for feature in RATE_FEATURES:out[f"{feature}_historical_match_percentile"]=[empirical_percentile(v,baseline[feature]) for v in pd.to_numeric(out[feature],errors="coerce")]
    return out

def products_for(season:str,matches:pd.DataFrame,events:pd.DataFrame,method:dict,historical_match:pd.DataFrame,historical_season:pd.DataFrame)->dict[str,pd.DataFrame]:
    match=tactical_match_features(matches,spatial_match_features(events),season);match=add_match_baseline_percentiles(match,historical_match)
    profile=build_profiles(match,method,["club_id"])
    manager=build_profiles(match,method,["club_id","manager_id","manager_name"],historical_match);formation=build_profiles(match,method,["club_id","formation"],historical_match);venue=build_profiles(match,method,["club_id","home_away"],historical_match)
    context=opponent_context(match,profile)
    return {"team_tactical_match_features":match,"team_tactical_profile":profile,"team_manager_tactical_profile":manager,"team_formation_tactical_profile":formation,"team_venue_tactical_profile":venue,"team_opponent_tactical_context":context}

def methodology_artifact(method:dict,history:pd.DataFrame,current:pd.DataFrame,stability:pd.DataFrame)->pd.DataFrame:
    accepted={feature:(trait["dimension"],weight) for trait in method["traits"] for feature,weight in trait["features"].items()};definitions={
      "final_third_event_share":"Share of recorded team events in the attacking third.","final_third_entries_per_match":"Successful passes entering the final third from outside per match.","wide_attacking_activity_share":"Share of final-third attacking events in outer thirds.","crosses_per_match":"Cross attempts per match.","crosses_per_100_attacking_events":"Cross attempts per 100 final-third attacking events.","central_creation_share":"Share of final-third key-pass/shot actions in central third.","take_ons_per_match":"TakeOn attempts per match.","take_ons_per_100_attacking_events":"TakeOn attempts per 100 final-third attacking events.","box_entries_per_match":"Successful passes entering the box from outside per match.","box_event_share":"Share of recorded events in opponent box.","key_passes_per_match":"Key passes per match.","shots_per_match":"Shots per match.","xg_per_match":"Understat xG per match.","defensive_event_activity_depth":"Mean normalized attacking-direction depth of defensive events.","advanced_defensive_action_share":"Share of defensive events in attacking third.","successful_tackles_per_match":"Successful tackles per match.","interceptions_per_match":"Interceptions per match.","recoveries_per_match":"Recoveries per match.","aerials_per_match":"Aerial contests per match."}
    candidates=[*RATE_FEATURES,*EFFECTIVENESS_FEATURES,"possession_pct","forward_progressing_pass_rate","high_press"]
    rows=[]
    for feature in candidates:
        included=feature in accepted;status=stability.loc[stability.feature.eq(feature),"stability_status"]
        rows.append({"dimension":accepted.get(feature,("effectiveness" if feature in EFFECTIVENESS_FEATURES else "deferred",0))[0],"feature":feature,"definition":definitions.get(feature,"Effectiveness or deferred candidate."),"source":"Understat" if feature=="xg_per_match" else "WhoScored/Opta","rate_basis":"equal-match mean","direction":"higher = more of characteristic","weight":accepted.get(feature,(None,0))[1],"historical_coverage":history.get(feature,pd.Series(dtype=float)).notna().mean(),"current_coverage":current.get(feature,pd.Series(dtype=float)).notna().mean(),"stability":status.iloc[0] if len(status) else "NOT_TESTED","included":included,"exclusion_reason":"" if included else "Effectiveness kept separate" if feature in EFFECTIVENESS_FEATURES else "No validated direct evidence / deferred"})
    return pd.DataFrame(rows)

def main()->int:
    parser=argparse.ArgumentParser();parser.add_argument("--season",default="2627");parser.add_argument("--calibrate",action="store_true");args=parser.parse_args();started=time.perf_counter();method=load_methodology(CONFIG)
    cm,ce=load_inputs(args.season);historical=None
    if args.calibrate:
        hm,he=load_inputs("2526");hbase=tactical_match_features(hm,spatial_match_features(he),"2526");hseason=build_profiles(hbase,method,["club_id"]);historical=products_for("2526",hm,he,method,hbase,hseason)
        for key,frame in historical.items():atomic_csv(frame,ROOT/f"data/models/season_2526/{key}_2526.csv")
    else:
        hbase=pd.read_csv(ROOT/"data/models/season_2526/team_tactical_match_features_2526.csv",low_memory=False);hseason=pd.read_csv(ROOT/"data/models/season_2526/team_tactical_profile_2526.csv",low_memory=False)
    current=products_for(args.season,cm,ce,method,hbase,hseason)
    current_profile=current["team_tactical_profile"];current_profile["historical_reference_club_id"]=current_profile.club_id.astype(str).map(historical_club_id);historical_ids=set(hseason.club_id.astype(str));current_profile["historical_reference_available"]=current_profile.historical_reference_club_id.isin(historical_ids)
    for key,frame in current.items():atomic_csv(frame,ROOT/f"data/models/season_{args.season}/{key}_{args.season}.csv")
    QUALITY.mkdir(parents=True,exist_ok=True)
    if historical is not None:
        correlation=pairwise_correlations(historical["team_tactical_match_features"]);stability=stability_analysis(historical["team_tactical_match_features"],method);sample=sample_size_analysis(historical["team_tactical_match_features"]);traits=pd.concat([trait_records(historical["team_tactical_profile"],method,"2526"),trait_records(current["team_tactical_profile"],method,args.season)],ignore_index=True);profiles=pd.concat([historical["team_tactical_profile"].assign(season="2526"),current["team_tactical_profile"].assign(season=args.season)],ignore_index=True);inventory=methodology_artifact(method,historical["team_tactical_match_features"],current["team_tactical_match_features"],stability)
        atomic_csv(correlation,QUALITY/"team_tactical_feature_correlation_99c.csv");atomic_csv(stability,QUALITY/"team_tactical_stability_99c.csv");atomic_csv(sample,QUALITY/"team_tactical_sample_size_99c.csv");atomic_csv(traits,QUALITY/"team_tactical_traits_99c_validation.csv");atomic_csv(profiles,QUALITY/"team_tactical_profile_99c_validation.csv");atomic_csv(inventory,QUALITY/"team_tactical_methodology_99c.csv")
    summary={"methodology_version":METHODOLOGY_VERSION,"mode":"CALIBRATION_AND_APPLICATION" if args.calibrate else "WEEKLY_APPLICATION","historical_baseline_available":True,"historical_rows":len(hbase),"historical_clubs":hseason.club_id.nunique(),"current_rows":len(current["team_tactical_match_features"]),"current_clubs":current["team_tactical_profile"].club_id.nunique(),"current_match_count":cm.canonical_match_id.nunique(),"trait_confidence_state":current["team_tactical_profile"].confidence.mode().iat[0],"products_status":"CURRENT","elapsed_seconds":round(time.perf_counter()-started,3)};atomic_json(summary,QUALITY/"team_tactical_build_99c_latest.json");print(json.dumps(summary,indent=2));return 0
if __name__=="__main__":raise SystemExit(main())
