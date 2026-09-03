"""Canonical descriptive team-match analytics built from cached provider products."""
from __future__ import annotations
import numpy as np
import pandas as pd

from analytics.advanced_descriptive import add_plot_coordinates
from analytics.players.comparison import primary_position

EVENT_COUNT_FIELDS=("event_count","passes","successful_passes","key_passes","crosses","successful_crosses","take_ons","successful_take_ons","shots","shots_on_target","goals","tackles","successful_tackles","interceptions","clearances","blocks","recoveries","aerials","aerial_wins","final_third_entries","box_entries")


def aggregate_team_events(events:pd.DataFrame)->pd.DataFrame:
    """Aggregate each unique WhoScored event once to its acting match/team."""
    if events.empty:return pd.DataFrame(columns=["canonical_match_id","club_id",*EVENT_COUNT_FIELDS])
    e=events.drop_duplicates(["canonical_match_id","event_id"]).copy();e=add_plot_coordinates(e)
    typ=e.event_type.astype(str);successful=e.outcome.astype(str).eq("Successful");qual=e.qualifiers.astype(str)
    e["_pass"]=typ.eq("Pass");e["_successful_pass"]=e._pass&successful;e["_key_pass"]=e.is_key_pass.fillna(False).astype(bool)
    e["_cross"]=e._pass&qual.str.contains('Cross',case=False,na=False);e["_successful_cross"]=e._cross&successful
    e["_take_on"]=typ.eq("TakeOn");e["_successful_take_on"]=e._take_on&successful
    e["_shot"]=typ.isin(["Goal","SavedShot","MissedShots","ShotOnPost"]);e["_sot"]=typ.eq("Goal")|(typ.eq("SavedShot")&~qual.str.contains('Blocked',case=False,na=False));e["_goal"]=typ.eq("Goal")
    e["_tackle"]=typ.eq("Tackle");e["_successful_tackle"]=e._tackle&successful;e["_interception"]=typ.eq("Interception");e["_clearance"]=typ.eq("Clearance");e["_block"]=typ.isin(["BlockedPass","BlockedShot"]);e["_recovery"]=typ.eq("BallRecovery");e["_aerial"]=typ.eq("Aerial");e["_aerial_win"]=e._aerial&successful
    x=pd.to_numeric(e.x,errors="coerce");y=pd.to_numeric(e.y,errors="coerce");ex=pd.to_numeric(e.end_x,errors="coerce");ey=pd.to_numeric(e.end_y,errors="coerce")
    e["_final_third_entry"]=e._successful_pass&x.lt(66.67)&ex.ge(66.67)
    e["_box_entry"]=e._successful_pass&~(x.ge(83)&y.between(21.1,78.9))&ex.ge(83)&ey.between(21.1,78.9)
    e["_defensive"]=typ.isin(["Tackle","Interception","Clearance","BlockedPass","BlockedShot","BallRecovery"])
    rows=[]
    for (match,club),g in e.groupby(["canonical_match_id","club_id"],dropna=False):
        gx=pd.to_numeric(g.plot_x,errors="coerce");gy=pd.to_numeric(g.plot_y,errors="coerce");valid=gx.notna()&gy.notna();n=int(valid.sum());pct=lambda mask:100*int((valid&mask).sum())/n if n else np.nan
        values={"canonical_match_id":match,"club_id":club,"event_count":len(g),"passes":int(g._pass.sum()),"successful_passes":int(g._successful_pass.sum()),"key_passes":int(g._key_pass.sum()),"crosses":int(g._cross.sum()),"successful_crosses":int(g._successful_cross.sum()),"take_ons":int(g._take_on.sum()),"successful_take_ons":int(g._successful_take_on.sum()),"shots":int(g._shot.sum()),"shots_on_target":int(g._sot.sum()),"goals":int(g._goal.sum()),"tackles":int(g._tackle.sum()),"successful_tackles":int(g._successful_tackle.sum()),"interceptions":int(g._interception.sum()),"clearances":int(g._clearance.sum()),"blocks":int(g._block.sum()),"recoveries":int(g._recovery.sum()),"aerials":int(g._aerial.sum()),"aerial_wins":int(g._aerial_win.sum()),"final_third_entries":int(g._final_third_entry.sum()),"box_entries":int(g._box_entry.sum()),"event_activity_center_x":gx[valid].mean(),"event_activity_center_y":gy[valid].mean(),"defensive_third_event_share":pct(gy<100/3),"middle_third_event_share":pct((gy>=100/3)&(gy<200/3)),"final_third_event_share":pct(gy>=200/3),"box_event_count":int((valid&gy.ge(82)&gx.between(20,80)).sum()),"defensive_event_activity_depth":pd.to_numeric(g.loc[g._defensive,"plot_y"],errors="coerce").mean()}
        rows.append(values)
    out=pd.DataFrame(rows)
    out["pass_completion_pct"]=100*out.successful_passes/out.passes.replace(0,np.nan);out["cross_success_pct"]=100*out.successful_crosses/out.crosses.replace(0,np.nan);out["take_on_success_pct"]=100*out.successful_take_ons/out.take_ons.replace(0,np.nan);out["aerial_win_pct"]=100*out.aerial_wins/out.aerials.replace(0,np.nan);out["box_event_share"]=100*out.box_event_count/out.event_count.replace(0,np.nan)
    return out


def build_team_match_analytics(formations:pd.DataFrame,events:pd.DataFrame,understat:pd.DataFrame,match_log:pd.DataFrame,clubs:pd.DataFrame,season:str="2627")->pd.DataFrame:
    context=formations.drop_duplicates(["canonical_match_id","club_id"]).copy();aggregated=aggregate_team_events(events)
    out=context.merge(aggregated,on=["canonical_match_id","club_id"],how="left",validate="one_to_one")
    us=understat.rename(columns={"canonical_club_id":"club_id","xga":"xga_understat","xg":"xg_understat","period":"understat_period","date":"understat_date","venue":"understat_venue"})
    out=out.merge(us[[c for c in ("canonical_match_id","club_id","xg_understat","xga_understat","understat_period","understat_date") if c in us]],on=["canonical_match_id","club_id"],how="left",validate="one_to_one")
    scores=(match_log.groupby(["canonical_match_id","club_id"],as_index=False).agg(team_goals=("team_goals_for","max"),opponent_goals=("team_goals_against","max"),period=("fantrax_period","max"))) if not match_log.empty else pd.DataFrame()
    if not scores.empty:out=out.merge(scores,on=["canonical_match_id","club_id"],how="left",validate="one_to_one")
    names=dict(zip(clubs.get("canonical_club_id",clubs.get("club_id",pd.Series(dtype=object))).astype(str),clubs.get("canonical_name",clubs.get("club_name",clubs.get("premier_league_club",pd.Series(dtype=object))))))
    out["season"]=season;out["match_date"]=out.get("date",out.get("understat_date"));out["club_name"]=out.club_id.astype(str).map(names);out["opponent_name"]=out.opponent_id.astype(str).map(names);out["home_away"]=out.venue.astype(str).str.upper().str[0];out["goal_difference"]=pd.to_numeric(out.team_goals,errors="coerce")-pd.to_numeric(out.opponent_goals,errors="coerce");out["result"]=np.select([out.goal_difference.gt(0),out.goal_difference.eq(0),out.goal_difference.lt(0)],["W","D","L"],default=pd.NA);out["xg"]=out.xg_understat;out["xga"]=out.xga_understat;out["xg_diff"]=out.xg-out.xga;out["match_completed"]=out.team_goals.notna()&out.opponent_goals.notna();out["provider_maturity"]=np.where(out.xg.notna(),"WHOSCORED_UNDERSTAT_FANTRAX_CURRENT","WHOSCORED_FANTRAX_PARTIAL");out["feature_class"]="OBSERVED_OR_TRANSPARENTLY_DERIVED";out["contains_prediction"]=False
    first=["season","period","canonical_match_id","match_date","club_id","club_name","opponent_id","opponent_name","venue","home_away","team_goals","opponent_goals","goal_difference","result","manager_id","manager_name","formation","match_completed","provider_maturity","xg","xga","xg_diff"]
    return out[[*first,*[c for c in out if c not in first and not c.startswith(("xg_understat","xga_understat","understat_"))]]].sort_values(["canonical_match_id","club_id"]).reset_index(drop=True)


def reciprocal_validation(team_match:pd.DataFrame)->pd.DataFrame:
    rows=[]
    for match,g in team_match.groupby("canonical_match_id"):
        valid=len(g)==2
        if valid:
            a,b=g.iloc[0],g.iloc[1];checks={"opponent_reciprocal":a.opponent_id==b.club_id and b.opponent_id==a.club_id,"score_reciprocal":a.team_goals==b.opponent_goals and b.team_goals==a.opponent_goals,"xg_reciprocal":np.isclose(a.xg,b.xga,equal_nan=False) and np.isclose(b.xg,a.xga,equal_nan=False),"venue_reciprocal":{a.home_away,b.home_away}=={"H","A"}}
        else:checks={k:False for k in ("opponent_reciprocal","score_reciprocal","xg_reciprocal","venue_reciprocal")}
        rows.append({"match":match,"rows":len(g),**checks,"validation_status":"PASS" if valid and all(checks.values()) else "FAIL"})
    return pd.DataFrame(rows)


def aggregate_profile(team_match:pd.DataFrame,group:list[str])->pd.DataFrame:
    counts=[c for c in EVENT_COUNT_FIELDS if c in team_match];base=team_match.groupby(group,dropna=False).agg(matches=("canonical_match_id","nunique"),wins=("result",lambda s:s.eq("W").sum()),draws=("result",lambda s:s.eq("D").sum()),losses=("result",lambda s:s.eq("L").sum()),goals_for=("team_goals","sum"),goals_against=("opponent_goals","sum"),xg=("xg","sum"),xga=("xga","sum"),**{f"{c}_per_match":(c,"mean") for c in counts}).reset_index();base["xg_diff"]=base.xg-base.xga
    for share in ("pass_completion_pct","cross_success_pct","take_on_success_pct","aerial_win_pct","final_third_event_share","box_event_share"):
        if share in team_match:base[share]=team_match.groupby(group,dropna=False)[share].mean().values
    base["feature_class"]="DESCRIPTIVE_OBSERVED_AGGREGATE";base["contains_prediction"]=False
    return base


def add_league_context(profile:pd.DataFrame)->pd.DataFrame:
    out=profile.copy()
    for field in [c for c in out if c.endswith("_per_match") or c in {"pass_completion_pct","final_third_event_share","box_event_share"}]:
        values=pd.to_numeric(out[field],errors="coerce");out[f"{field}_league_average"]=values.mean();out[f"{field}_volume_rank"]=values.rank(method="min",ascending=False).astype("Int64");out[f"{field}_percentile"]=values.rank(pct=True)*100
    return out


def fantasy_allowed_foundation(match_log:pd.DataFrame)->tuple[pd.DataFrame,pd.DataFrame]:
    d=match_log[match_log.get("appeared",pd.Series(False,index=match_log.index)).fillna(False).astype(bool)].copy();d["position_group"]=d.apply(primary_position,axis=1).replace({"G":"GK","D":"DEF","M":"MID","F":"FWD"})
    metrics={"fantasy_points_allowed":("fantrax_points","sum"),"ghost_allowed":("ghost_points","sum"),"goals_allowed":("goals","sum"),"assists_allowed":("assists","sum"),"key_passes_allowed":("key_passes","sum"),"tackles_won_allowed":("tackles_won","sum"),"accurate_crosses_allowed":("accurate_crosses","sum"),"interceptions_allowed":("interceptions","sum"),"clearances_allowed":("clearances","sum"),"aerial_wins_allowed":("aerial_wins","sum")}
    metrics={k:v for k,v in metrics.items() if v[0] in d};group=["canonical_match_id","opponent_id"]
    total=d.groupby(group,as_index=False).agg(players=("fantrax_player_id","nunique"),**metrics);total=total.rename(columns={"opponent_id":"club_id"});total["feature_class"]="MATCH_ATTRIBUTABLE_BEST_AVAILABLE";total["contains_prediction"]=False
    position=d.groupby([*group,"position_group"],as_index=False).agg(players=("fantrax_player_id","nunique"),**metrics).rename(columns={"opponent_id":"club_id"});position["feature_class"]="MATCH_ATTRIBUTABLE_BEST_AVAILABLE";position["contains_prediction"]=False
    return total,position
