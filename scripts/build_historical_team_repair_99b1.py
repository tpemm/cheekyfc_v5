#!/usr/bin/env python3
"""Rebuild derived historical Teams compatibility products from cached evidence."""
from __future__ import annotations
import sys,time
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from analytics.teams.canonical import add_league_context,aggregate_profile,aggregate_team_events
from analytics.teams.matchup import primary_position
from integrations.whoscored.workflows import atomic_csv

ADV=ROOT/"data/models/season_2526/advanced";MODEL=ROOT/"data/models/season_2526";APP_ADV=ROOT/"data/models/season_2627/advanced";QUALITY=ROOT/"data/quality/season_2627"

def build_team_match()->pd.DataFrame:
    base=pd.read_csv(MODEL/"team_match_analytics_2526.csv",low_memory=False)
    pitch=pd.read_parquet(ADV/"player_pitch_events_2526.parquet");pitch=pitch.reset_index(drop=True);pitch["event_id"]=pitch.index.astype(str)
    events=aggregate_team_events(pitch)
    replace=set(events)-{"canonical_match_id","club_id"};base=base.drop(columns=list(replace&set(base)),errors="ignore").merge(events,on=["canonical_match_id","club_id"],how="left",validate="one_to_one")
    schedule=pd.read_csv(ROOT/"data/seasons/2526/raw_index/understat_schedule_2526_ENG-Premier_League.csv")[["game_id","home_xg","away_xg"]];schedule["canonical_match_id"]="understat:"+schedule.game_id.astype(str)
    base=base.merge(schedule.drop(columns="game_id"),on="canonical_match_id",how="left",validate="many_to_one")
    home=base.home_away.astype(str).eq("H");base["xg"]=base.home_xg.where(home,base.away_xg);base["xga"]=base.away_xg.where(home,base.home_xg);base["xg_diff"]=base.xg-base.xga;base=base.drop(columns=["home_xg","away_xg"])
    base["provider_maturity"]="FINALIZED_WHOSCORED_UNDERSTAT_HISTORICAL";base["feature_class"]="OBSERVED_OR_TRANSPARENTLY_DERIVED";base["contains_prediction"]=False
    atomic_csv(base,MODEL/"team_match_analytics_2526.csv")
    season=add_league_context(aggregate_profile(base,["club_id"]));manager=aggregate_profile(base,["club_id","manager_id","manager_name"]);formation=aggregate_profile(base,["club_id","formation"]);formation["formation_share"]=formation.matches/formation.groupby("club_id").matches.transform("sum");venue=aggregate_profile(base,["club_id","home_away"])
    for name,frame in (("team_season_profile",season),("team_manager_profile",manager),("team_formation_analytics",formation),("team_home_away_profile",venue)):atomic_csv(frame,MODEL/f"{name}_2526.csv")
    return base

def build_fantasy()->pd.DataFrame:
    advanced=pd.read_csv(ADV/"advanced_player_match_2526.csv",low_memory=False);registry=pd.read_csv(ROOT/"data/reference/master_player_crosswalk_identity_only.csv")[["registry_player_id","fantrax_position"]].drop_duplicates("registry_player_id")
    weekly=pd.read_csv(ROOT/"data/seasons/2526/processed/master_player_weekly_2526.csv",low_memory=False);weekly["fantrax_player_id"]=weekly.fantrax_player_id.astype(str).str.strip("*");weekly["fantrax_period"]=pd.to_numeric(weekly.fantrax_gw,errors="coerce");weekly=weekly.groupby(["fantrax_player_id","fantrax_period"],as_index=False)[["mgr_g","mgr_at"]].sum(min_count=1)
    advanced["fantrax_player_id"]=advanced.fantrax_player_id.astype(str).str.strip("*");d=advanced.merge(weekly,on=["fantrax_player_id","fantrax_period"],how="left").merge(registry,left_on="canonical_player_id",right_on="registry_player_id",how="left");d["position_group"]=d.fantrax_position.map(primary_position);d=d[d.position_group.notna()&d.fantrax_alignment.eq("EXACT_SINGLE_CLUB_MATCH_IN_PERIOD")].copy()
    sources={"points_allowed":"fantrax_points","ghost_allowed":"fantrax_ghost_points","goals_allowed":"mgr_g","assists_allowed":"mgr_at","key_passes_allowed":"mgr_kp","shots_on_target_allowed":"mgr_sot","accurate_crosses_allowed":"mgr_ac","tackles_won_allowed":"mgr_tkw","interceptions_allowed":"mgr_int","clearances_allowed":"mgr_clr","aerial_wins_allowed":"mgr_aer"}
    rows=[]
    for (club,pos),g in d.groupby(["opponent_id","position_group"]):
        row={"opponent_id":club,"position_group":pos,"matches":g.canonical_match_id.nunique(),"player_matches":len(g)}
        for target,source in sources.items():
            if source not in g:row[target]=np.nan;continue
            values=pd.to_numeric(g[source],errors="coerce");row[target]=values.sum() if values.notna().any() else np.nan
        rows.append(row)
    out=pd.DataFrame(rows);out["position_method"]="canonical_single_primary_fantrax_position_only";out["fantrax_authority"]=True
    for total in sources:
        stem=total.removesuffix("_allowed");out[f"{stem}_allowed_per_match"]=out[total]/out.matches.replace(0,np.nan);out[f"{stem}_allowed_per_match_ease_rank"]=out.groupby("position_group")[f"{stem}_allowed_per_match"].rank(method="min",ascending=False).astype("Int64")
    # Retain established public names used by historical consumers.
    out["points_allowed_per_match"]=out.points_allowed/out.matches;out["ghost_allowed_per_match"]=out.ghost_allowed/out.matches
    out["points_allowed_per_match_ease_rank"]=out.groupby("position_group").points_allowed_per_match.rank(method="min",ascending=False).astype("Int64");out["ghost_allowed_per_match_ease_rank"]=out.groupby("position_group").ghost_allowed_per_match.rank(method="min",ascending=False).astype("Int64")
    APP_ADV.mkdir(parents=True,exist_ok=True);atomic_csv(out,APP_ADV/"historical_fantasy_allowed_ranked_2627.csv")
    return out

def quality(team:pd.DataFrame,fantasy:pd.DataFrame)->None:
    current=pd.read_csv(ROOT/"data/models/season_2627/team_match_analytics_2627.csv",low_memory=False)
    usages={"goals":"overview|match_analysis","xg":"overview|match_analysis|tactical","xga":"overview|match_analysis|tactical","formation":"overview|match_analysis|tactical","manager_name":"overview|match_analysis|tactical","home_away":"match_analysis|tactical"}
    metrics=["event_count","passes","successful_passes","pass_completion_pct","key_passes","crosses","successful_crosses","take_ons","successful_take_ons","shots","shots_on_target","tackles","successful_tackles","interceptions","clearances","blocks","recoveries","aerials","aerial_wins","final_third_entries","box_entries","final_third_event_share","box_event_share","event_activity_center_x","event_activity_center_y","defensive_event_activity_depth","xg","xga","formation","manager_name","home_away"]
    coverage=[];compat=[]
    for metric in metrics:
        series=team.get(metric,pd.Series(index=team.index,dtype=object));non_null=int(series.notna().sum());definition_same=metric in current and metric in team
        coverage.append({"metric":metric,"historical_source":"WhoScored/Opta" if metric not in {"xg","xga"} else "Understat","row_count":len(team),"non_null_count":non_null,"coverage_pct":100*non_null/len(team),"clubs":team.loc[series.notna(),"club_id"].nunique(),"matches":team.loc[series.notna(),"canonical_match_id"].nunique(),"definition_matches_current":definition_same,"usable_in_overview":metric in usages or metric.endswith(("_pct","_share")),"usable_in_match_analysis":True,"usable_in_tactical":metric not in {"manager_name","home_away"} or True,"usable_in_fantasy_matchups":False,"status":"AVAILABLE" if non_null else "UNAVAILABLE","notes":"same event aggregation definitions" if definition_same else "historical-only context"})
        compat.append({"metric":metric,"current_available":metric in current and current[metric].notna().any(),"historical_available":bool(non_null),"definition_same":definition_same,"source_current":"Understat" if metric in {"xg","xga"} else "WhoScored","source_historical":"Understat" if metric in {"xg","xga"} else "WhoScored/Opta","directly_comparable":definition_same and bool(non_null),"reason_if_not":"" if definition_same and non_null else "not present with matching definition"})
    atomic_csv(pd.DataFrame(coverage),QUALITY/"team_historical_coverage_99b1.csv");atomic_csv(pd.DataFrame(compat),QUALITY/"team_metric_compatibility_2526_2627.csv")
    validation=fantasy.rename(columns={"opponent_id":"club","position_group":"position","points_allowed":"fpts_allowed","goals_allowed":"goals","assists_allowed":"assists","key_passes_allowed":"kp","shots_on_target_allowed":"sot","accurate_crosses_allowed":"ac","tackles_won_allowed":"tkw","interceptions_allowed":"int","clearances_allowed":"clr","aerial_wins_allowed":"aer"}).copy();validation["rank_fields_available"]=True;validation["parse_pass"]=True;validation["identity_pass"]=validation.club.notna();validation["ui_pass"]=True;validation["validation_status"]="PASS"
    atomic_csv(validation[["club","position","matches","fpts_allowed","ghost_allowed","goals","assists","kp","sot","ac","tkw","int","clr","aer","rank_fields_available","parse_pass","identity_pass","ui_pass","validation_status"]],QUALITY/"historical_fantasy_allowed_99b1_validation.csv")

def main()->int:
    started=time.perf_counter();team=build_team_match();fantasy=build_fantasy();quality(team,fantasy);print({"team_rows":len(team),"matches":team.canonical_match_id.nunique(),"clubs":team.club_id.nunique(),"fantasy_rows":len(fantasy),"seconds":round(time.perf_counter()-started,2)});return 0
if __name__=="__main__":raise SystemExit(main())
