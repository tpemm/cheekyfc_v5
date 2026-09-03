"""Transparent team tactical-style calibration and application models."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Iterable
import numpy as np
import pandas as pd

from analytics.advanced_descriptive import add_plot_coordinates

METHODOLOGY_VERSION="team_tactical_v1"
DEFAULT_METHODOLOGY_PATH=Path(__file__).resolve().parents[2]/"config/team_tactical_traits.json"
RATE_FEATURES=("final_third_event_share","final_third_entries_per_match","wide_attacking_activity_share","crosses_per_match","crosses_per_100_attacking_events","central_creation_share","take_ons_per_match","take_ons_per_100_attacking_events","box_entries_per_match","box_event_share","key_passes_per_match","shots_per_match","shots_on_target_per_match","xg_per_match","defensive_event_activity_depth","advanced_defensive_action_share","successful_tackles_per_match","interceptions_per_match","recoveries_per_match","aerials_per_match")
EFFECTIVENESS_FEATURES=("cross_success_pct","take_on_success_pct","aerial_win_pct","xg_per_shot")

def load_methodology(path:Path|str)->dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))

def fingerprint_records(profile:pd.Series,methodology:dict,season_label:str)->pd.DataFrame:
    rows=[]
    for trait in methodology["traits"]:
        dimension=trait["dimension"];primary=max(trait["features"],key=trait["features"].get)
        rows.append({"Season":season_label,"Dimension":dimension.replace("_"," ").title(),"Trait":profile.get(f"{dimension}_trait","—"),"Percentile":profile.get(f"{dimension}_percentile"),"Underlying Metric":primary.replace("_"," ").title(),"Value":profile.get(primary),"Confidence":profile.get("confidence","—"),"Why":trait["description"],"Caveat":trait["caveat"]})
    return pd.DataFrame(rows)

def confidence_state(matches:int)->str:
    if matches>=10:return "Established"
    if matches>=5:return "Developing"
    if matches>=3:return "Emerging"
    return "Very Early"

def empirical_percentile(value:float,reference:pd.Series)->float:
    clean=pd.to_numeric(reference,errors="coerce").dropna().sort_values().to_numpy()
    return np.nan if pd.isna(value) or not len(clean) else 100*float(np.searchsorted(clean,value,side="right"))/len(clean)

def spatial_match_features(events:pd.DataFrame)->pd.DataFrame:
    """Build explicit match-team spatial features from immutable raw coordinates."""
    if events.empty:return pd.DataFrame(columns=["canonical_match_id","club_id"])
    e=add_plot_coordinates(events.copy());typ=e.event_type.astype(str);x=pd.to_numeric(e.plot_x,errors="coerce");y=pd.to_numeric(e.plot_y,errors="coerce")
    attacking=typ.isin(["Pass","TakeOn","Goal","SavedShot","MissedShots","ShotOnPost"]);final=attacking&y.ge(66.67);creative=(e.get("is_key_pass",False).fillna(False).astype(bool)|typ.isin(["Goal","SavedShot","MissedShots","ShotOnPost"]))&y.ge(66.67);defensive=typ.isin(["Tackle","Interception","Clearance","BlockedPass","BlockedShot","BallRecovery"]);red=e.get("qualifiers",pd.Series("",index=e.index)).astype(str).str.contains("Red|SecondYellow",case=False,na=False)
    e["_attacking_final"]=final;e["_wide_attacking_final"]=final&(x.lt(100/3)|x.ge(200/3));e["_creative"]=creative;e["_central_creative"]=creative&x.between(100/3,200/3);e["_defensive"]=defensive;e["_advanced_defensive"]=defensive&y.ge(66.67);e["_red"]=red
    rows=[]
    for (match,club),g in e.groupby(["canonical_match_id","club_id"],dropna=False):
        ratio=lambda a,b:100*int(g[a].sum())/int(g[b].sum()) if int(g[b].sum()) else np.nan
        rows.append({"canonical_match_id":match,"club_id":club,"wide_attacking_activity_share":ratio("_wide_attacking_final","_attacking_final"),"central_creation_share":ratio("_central_creative","_creative"),"advanced_defensive_action_share":ratio("_advanced_defensive","_defensive"),"attacking_event_count":int(g._attacking_final.sum()),"red_card_match":bool(g._red.any())})
    return pd.DataFrame(rows)

def tactical_match_features(team_match:pd.DataFrame,spatial:pd.DataFrame,season:str)->pd.DataFrame:
    d=team_match.copy().merge(spatial,on=["canonical_match_id","club_id"],how="left",validate="one_to_one")
    mapping={"crosses":"crosses_per_match","take_ons":"take_ons_per_match","box_entries":"box_entries_per_match","final_third_entries":"final_third_entries_per_match","key_passes":"key_passes_per_match","shots":"shots_per_match","shots_on_target":"shots_on_target_per_match","xg":"xg_per_match","successful_tackles":"successful_tackles_per_match","interceptions":"interceptions_per_match","recoveries":"recoveries_per_match","aerials":"aerials_per_match"}
    for source,target in mapping.items():d[target]=pd.to_numeric(d.get(source),errors="coerce")
    d["crosses_per_100_attacking_events"]=100*d.crosses_per_match/pd.to_numeric(d.attacking_event_count,errors="coerce").replace(0,np.nan);d["take_ons_per_100_attacking_events"]=100*d.take_ons_per_match/pd.to_numeric(d.attacking_event_count,errors="coerce").replace(0,np.nan);d["xg_per_shot"]=d.xg_per_match/d.shots_per_match.replace(0,np.nan)
    d["season"]=str(season);d["methodology_version"]=METHODOLOGY_VERSION;d["feature_class"]="OBSERVED_TACTICAL_FEATURE";d["contains_prediction"]=False
    keep=["season","canonical_match_id","match_date","club_id","opponent_id","home_away","manager_id","manager_name","formation","result","red_card_match",*RATE_FEATURES,*EFFECTIVENESS_FEATURES,"methodology_version","feature_class","contains_prediction"]
    return d.reindex(columns=keep).sort_values(["match_date","canonical_match_id","club_id"]).reset_index(drop=True)

def aggregate_features(matches:pd.DataFrame,group:list[str])->pd.DataFrame:
    fields=[c for c in (*RATE_FEATURES,*EFFECTIVENESS_FEATURES) if c in matches]
    agg={c:(c,"mean") for c in fields};agg.update(matches=("canonical_match_id","nunique"),red_card_matches=("red_card_match","sum"))
    return matches.groupby(group,dropna=False,as_index=False).agg(**agg)

def apply_dimensions(profile:pd.DataFrame,methodology:dict,reference:pd.DataFrame|None=None,*,strong_traits:bool=True)->pd.DataFrame:
    out=profile.copy();ref=out if reference is None else reference
    configured_features={feature for trait in methodology["traits"] for feature in trait["features"]}
    for feature in configured_features:
        if feature not in out:continue
        source=ref.get(feature,pd.Series(dtype=float));out[f"{feature}_percentile"]=[empirical_percentile(v,source) for v in pd.to_numeric(out[feature],errors="coerce")]
    high=methodology["thresholds"]["high_percentile"];low=methodology["thresholds"]["low_percentile"]
    for trait in methodology["traits"]:
        dimension=trait["dimension"];parts=[]
        for feature,weight in trait["features"].items():
            column=f"{feature}_percentile";parts.append(pd.to_numeric(out.get(column),errors="coerce")*float(weight))
        out[f"{dimension}_percentile"]=pd.concat(parts,axis=1).sum(axis=1,min_count=len(parts))
        def label(row):
            value=row[f"{dimension}_percentile"]
            if pd.isna(value):return "—"
            if not strong_traits or row.matches<int(trait["minimum_sample"]):return "Observation only"
            if value>=high:return trait["high_name"]
            if value<=low:return trait["low_name"]
            return trait["balanced_name"]
        out[f"{dimension}_trait"]=out.apply(label,axis=1)
    out["confidence"]=out.matches.fillna(0).astype(int).map(confidence_state);out["methodology_version"]=methodology["methodology_version"];out["contains_prediction"]=False
    return out

def build_profiles(matches:pd.DataFrame,methodology:dict,group:list[str],reference:pd.DataFrame|None=None)->pd.DataFrame:
    base=aggregate_features(matches,group);ref=aggregate_features(reference,group[:1]) if reference is not None else None
    return apply_dimensions(base,methodology,ref)

def trait_records(profile:pd.DataFrame,methodology:dict,season:str)->pd.DataFrame:
    rows=[]
    for row in profile.to_dict("records"):
        for trait in methodology["traits"]:
            dim=trait["dimension"];primary=max(trait["features"],key=trait["features"].get);rows.append({"season":season,"club":row.get("club_id"),"matches":row.get("matches"),"dimension":dim,"raw_value":row.get(primary),"league_average":pd.to_numeric(profile.get(primary),errors="coerce").mean(),"percentile":row.get(f"{dim}_percentile"),"trait":row.get(f"{dim}_trait"),"threshold":f"<={methodology['thresholds']['low_percentile']} / >={methodology['thresholds']['high_percentile']}","minimum_sample":trait["minimum_sample"],"confidence":row.get("confidence"),"validation_status":"PASS" if pd.notna(row.get(f"{dim}_percentile")) else "UNAVAILABLE"})
    return pd.DataFrame(rows)

def opponent_context(matches:pd.DataFrame,profiles:pd.DataFrame)->pd.DataFrame:
    dimensions=[c for c in profiles if c.endswith(("_percentile","_trait")) and not any(c.startswith(f+"_") for f in RATE_FEATURES)]
    lookup=profiles[["club_id","matches","confidence",*dimensions]].rename(columns={"club_id":"opponent_id","matches":"opponent_profile_matches","confidence":"opponent_confidence",**{c:f"opponent_{c}" for c in dimensions}})
    out=matches[["season","canonical_match_id","club_id","opponent_id"]].merge(lookup,on="opponent_id",how="left",validate="many_to_one");out["methodology_version"]=METHODOLOGY_VERSION;out["contains_prediction"]=False;return out

def join_player_opponent_context(player_matches:pd.DataFrame,context:pd.DataFrame)->pd.DataFrame:
    return player_matches.merge(context.drop(columns=["club_id"],errors="ignore"),on=["canonical_match_id","opponent_id"],how="left",validate="many_to_one")

def join_fantasy_allowed_tactical(fantasy:pd.DataFrame,context:pd.DataFrame)->pd.DataFrame:
    keys=[c for c in context if c.startswith("opponent_") or c in {"canonical_match_id","club_id","methodology_version"}];return fantasy.merge(context[keys],on=["canonical_match_id","club_id"],how="left",validate="many_to_one")

def pairwise_correlations(matches:pd.DataFrame)->pd.DataFrame:
    corr=matches[[c for c in RATE_FEATURES if c in matches]].corr();rows=[]
    for i,a in enumerate(corr):
        for b in corr.columns[i+1:]:rows.append({"feature_a":a,"feature_b":b,"pearson":corr.loc[a,b],"absolute_correlation":abs(corr.loc[a,b]),"redundant_candidate":abs(corr.loc[a,b])>=.85})
    return pd.DataFrame(rows)

def stability_analysis(matches:pd.DataFrame,methodology:dict)->pd.DataFrame:
    ordered=matches.sort_values(["club_id","match_date","canonical_match_id"]).copy();ordered["half"]=ordered.groupby("club_id").cumcount().ge(19);rows=[]
    for feature in RATE_FEATURES:
        if feature not in ordered:continue
        values=pd.to_numeric(ordered[feature],errors="coerce");means=ordered.assign(_v=values).groupby("club_id")._v.mean();within=ordered.assign(_v=values).groupby("club_id")._v.var().mean();half=ordered.assign(_v=values).groupby(["club_id","half"])._v.mean().unstack();pearson=half.corr(method="pearson").iloc[0,1] if half.shape[1]==2 else np.nan;spearman=half.corr(method="spearman").iloc[0,1] if half.shape[1]==2 else np.nan
        rows.append({"dimension":next((t["dimension"] for t in methodology["traits"] if feature in t["features"]),"effectiveness"),"feature":feature,"between_team_variance":means.var(),"within_team_variance":within,"split_half_spearman":spearman,"split_half_pearson":pearson,"stability_status":"STRONG" if pd.notna(spearman) and spearman>=.6 else "MODERATE" if pd.notna(spearman) and spearman>=.35 else "WEAK","notes":"Equal-match split; red-card matches retained and flagged."})
    return pd.DataFrame(rows)

def sample_size_analysis(matches:pd.DataFrame)->pd.DataFrame:
    ordered=matches.sort_values(["club_id","match_date","canonical_match_id"]);rows=[]
    for n in (1,3,5,8,10,15,19,38):
        for feature in RATE_FEATURES:
            if feature not in ordered:continue
            full=ordered.groupby("club_id")[feature].mean();partial=ordered.groupby("club_id").head(n).groupby("club_id")[feature].mean();joined=pd.concat([partial,full],axis=1,keys=["partial","full"]).dropna();rows.append({"matches":n,"feature":feature,"clubs":len(joined),"pearson_to_full":joined.corr(method="pearson").iloc[0,1],"spearman_to_full":joined.corr(method="spearman").iloc[0,1],"median_absolute_error":(joined.partial-joined.full).abs().median(),"confidence":confidence_state(n)})
    return pd.DataFrame(rows)
