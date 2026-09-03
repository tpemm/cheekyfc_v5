"""Canonical preparation models for the Player Advanced analytics tab."""
from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.players.comparison import primary_position
from fantrax.analytics.core.fantrax_scoring import get_rule, normalize_scoring_position, score_stat

RATE_BASES=("Total","Per Start","Per 90")
NON_RATE_METRICS={"rating","pass_completion_pct","cross_success_pct","dribble_success_pct","aerial_win_pct","set_piece_rank"}

METRIC_GROUPS={
    "Fantasy Production":(("FPts","fantrax_points"),("Ghost","ghost_points"),("Goals","goals"),("Assists","assists"),("Clean Sheets","clean_sheets")),
    "Chance Creation":(("Key Passes","key_passes"),("xA","xa"),("Through Balls","through_balls"),("Cross Attempts","cross_attempts"),("Accurate Crosses","accurate_crosses"),("Assists","assists")),
    "Shooting / Threat":(("Goals","goals"),("xG","xg"),("Shots","shots"),("SOT","shots_on_target"),("Goals - xG","goals_minus_xg"),("xG / Shot","xg_per_shot"),("SOT Rate","sot_rate")),
    "Passing / Progression":(("Pass Attempts","passes_attempted"),("Pass Completions","passes_completed"),("Completion %","pass_completion_pct"),("Through Balls","through_balls")),
    "Dribbling":(("TakeOn Attempts","dribbles_attempted"),("Successful Dribbles / CoS","successful_dribbles"),("Success %","dribble_success_pct")),
    "Defensive Activity":(("Tackle Attempts","tackles"),("Tackles Won","tackles_won"),("Interceptions","interceptions"),("Clearances","clearances"),("Recoveries","recoveries"),("Blocked Passes","blocked_passes"),("Dispossessions","dispossessions")),
    "Aerials":(("Aerial Attempts","aerial_attempts"),("Aerial Wins","aerial_wins"),("Win %","aerial_win_pct")),
}

FIELD_ALIASES={
    "successful_dribbles":("successful_dribbles","fantrax_successful_dribbles","dribbles_successful"),
    "accurate_crosses":("accurate_crosses","fantrax_accurate_crosses","accurate_crosses_derived"),
    "tackles_won":("tackles_won","fantrax_tackles_won","tackles_won_derived"),
    "clean_sheets":("clean_sheets",), "dispossessions":("dispossessions",),
}

COMPONENTS=(
    ("G","Goals","goals"),("AT","Assists","assists"),("CS","Clean Sheets","clean_sheets"),
    ("KP","Key Passes","key_passes"),("SOT","Shots on Target","shots_on_target"),
    ("AC","Accurate Crosses","accurate_crosses"),("CoS","Successful Dribbles","successful_dribbles"),
    ("TkW","Tackles Won","tackles_won"),("Int","Interceptions","interceptions"),
    ("CLR","Clearances","clearances"),("AER","Aerial Wins","aerial_wins"),
    ("BS","Blocked Shots","blocks"),("DIS","Dispossessions","dispossessions"),
    ("YC","Yellow Cards","yellow_cards"),("RC","Red Cards","red_cards"),
    ("Sv","Saves","saves"),("PKS","Penalty Saves","penalties_saved"),
)


def _series(frame:pd.DataFrame,field:str)->pd.Series:
    result=pd.Series(np.nan,index=frame.index,dtype=float)
    for candidate in FIELD_ALIASES.get(field,(field,)):
        if candidate in frame:result=result.combine_first(pd.to_numeric(frame[candidate],errors="coerce"))
    return result


def overlay_fantrax_authority(supplemental:pd.DataFrame,match_log:pd.DataFrame)->pd.DataFrame:
    """Overlay authoritative current match facts, preserving explicit Fantrax zero."""
    if supplemental.empty or match_log.empty:return supplemental.copy()
    keys=[key for key in ("canonical_match_id","canonical_player_id") if key in supplemental and key in match_log]
    if not keys:return supplemental.copy()
    authority=("minutes","started","fantrax_points","ghost_points","goals","assists","clean_sheets","key_passes","shots_on_target","accurate_crosses","successful_dribbles","tackles_won","interceptions","clearances","aerial_wins","blocks","dispossessions","yellow_cards","red_cards","saves","penalties_saved","ghost_points_source","ghost_scoring_position")
    cols=[c for c in authority if c in match_log]
    overlay=match_log[keys+cols].drop_duplicates(keys).rename(columns={c:f"_fantrax_{c}" for c in cols})
    out=supplemental.merge(overlay,on=keys,how="left")
    for field in cols:
        trusted=out.pop(f"_fantrax_{field}")
        out[field]=trusted.where(trusted.notna(),out.get(field,pd.Series(np.nan,index=out.index)))
    return out


def safe_rate(numerator:object,denominator:object,multiplier:float=1)->float:
    n=pd.to_numeric(numerator,errors="coerce");d=pd.to_numeric(denominator,errors="coerce")
    return float(n/d*multiplier) if pd.notna(n) and pd.notna(d) and d>0 else float("nan")


def aggregate_advanced(matches:pd.DataFrame)->pd.Series:
    """Aggregate one player's canonical match observations without filling missing evidence."""
    starts=int(matches.get("started",pd.Series(False,index=matches.index)).fillna(False).astype(bool).sum())
    minutes=pd.to_numeric(matches.get("minutes"),errors="coerce").sum(min_count=1)
    result={"appearances":int(matches.get("canonical_match_id",pd.Series(index=matches.index)).nunique()),"starts":starts,"minutes":minutes}
    fields={field for group in METRIC_GROUPS.values() for _,field in group}|{field for _,_,field in COMPONENTS}|{"rating","xg","shots","shots_on_target","passes_attempted","passes_completed","dribbles_attempted","aerial_attempts","aerial_wins","cross_attempts","successful_dribbles"}
    derived={"goals_minus_xg","xg_per_shot","sot_rate","pass_completion_pct","dribble_success_pct","aerial_win_pct"}
    for field in fields-derived:
        values=_series(matches,field);result[field]=values.mean() if field=="rating" else values.sum(min_count=1)
    result.update({
        "goals_minus_xg":result.get("goals",np.nan)-result.get("xg",np.nan),
        "xg_per_shot":safe_rate(result.get("xg"),result.get("shots")),
        "sot_rate":safe_rate(result.get("shots_on_target"),result.get("shots"),100),
        "pass_completion_pct":safe_rate(result.get("passes_completed"),result.get("passes_attempted"),100),
        "dribble_success_pct":safe_rate(result.get("successful_dribbles"),result.get("dribbles_attempted"),100),
        "aerial_win_pct":safe_rate(result.get("aerial_wins"),result.get("aerial_attempts"),100),
    })
    return pd.Series(result)


def metric_value(profile:pd.Series,field:str,basis:str)->float:
    value=pd.to_numeric(profile.get(field),errors="coerce")
    if field in NON_RATE_METRICS or basis=="Total":return value
    return safe_rate(value,profile.get("starts")) if basis=="Per Start" else safe_rate(value,profile.get("minutes"),90)


def metric_group_frame(profile:pd.Series,group:str,basis:str)->pd.DataFrame:
    return pd.DataFrame([{"Metric":label,"Value":metric_value(profile,field,basis),"Field":field} for label,field in METRIC_GROUPS[group]])


def fantasy_contributions(profile:pd.Series,position:object,season:str="2627",sources:dict[str,str]|None=None)->pd.DataFrame:
    pos=normalize_scoring_position(position);rows=[]
    if not pos:return pd.DataFrame(columns=["Component","Stat","Scoring Weight","Fantasy Contribution","Source"])
    for code,label,field in COMPONENTS:
        count=pd.to_numeric(profile.get(field),errors="coerce")
        if pd.isna(count):continue
        try:rule=get_rule(season,pos,code);contribution=score_stat(season,pos,code,count)
        except KeyError:continue
        weight=f"{rule['points_each']:g} pts" if "points_each" in rule else "Banded"
        rows.append({"Code":code,"Component":label,"Stat":count,"Scoring Weight":weight,"Fantasy Contribution":contribution,"Source":(sources or {}).get(field,"Best available match observation")})
    return pd.DataFrame(rows)


def component_sources(matches:pd.DataFrame)->dict[str,str]:
    """Human-readable component provenance; implementation enums stay internal."""
    defaults={"goals":"Fantrax","assists":"Fantrax","clean_sheets":"Derived match context","xg":"Understat","xa":"Understat","shots":"WhoScored","passes_attempted":"WhoScored","passes_completed":"WhoScored","dribbles_attempted":"WhoScored","tackles":"WhoScored","recoveries":"WhoScored","aerial_attempts":"WhoScored"}
    source_fields={"ghost_points":"ghost_points_source","key_passes":"key_passes_source","successful_dribbles":"successful_dribbles_source","interceptions":"interceptions_source","clearances":"clearances_source","aerial_wins":"aerial_wins_source","accurate_crosses":"accurate_crosses_source","tackles_won":"tackles_won_source"}
    result={}
    for field in {field for _,_,field in COMPONENTS}:
        source_col=source_fields.get(field);observed=matches.get(source_col,pd.Series(index=matches.index,dtype=object)).dropna().astype(str).str.upper()
        if observed.str.contains("FANTRAX").any():result[field]="Fantrax detailed"
        elif len(observed):result[field]="WhoScored-derived / best available"
        else:result[field]=defaults.get(field,"Best available match observation")
    return result


def fantasy_reconciliation(profile:pd.Series,contributions:pd.DataFrame)->dict[str,float]:
    official=pd.to_numeric(profile.get("fantrax_points"),errors="coerce")
    known=pd.to_numeric(contributions.get("Fantasy Contribution"),errors="coerce").sum(min_count=1)
    return {"official_fpts":official,"known_component_contribution":known,"unreconciled_difference":official-known if pd.notna(official) and pd.notna(known) else float("nan")}


def return_points(profile:pd.Series,position:object,season:str="2627")->float:
    values=[]
    for code,field in (("G","goals"),("AT","assists"),("CS","clean_sheets")):
        count=pd.to_numeric(profile.get(field),errors="coerce")
        if pd.isna(count):continue
        try:values.append(score_stat(season,position,code,count))
        except (KeyError,ValueError):pass
    return float(sum(values)) if values else float("nan")


def positional_context(players:pd.DataFrame,selected_id:str,position:object,metrics:tuple[tuple[str,str],...])->pd.DataFrame:
    cohort=players[players.apply(primary_position,axis=1).eq(primary_position(pd.Series({"fantrax_position":position})))]
    selected=players[players.get("fantrax_player_id",pd.Series(index=players.index,dtype=object)).astype(str).eq(str(selected_id))]
    if selected.empty:return pd.DataFrame(columns=["Metric","Player","Position Average","Percentile","Peers"])
    row=selected.iloc[0];result=[]
    for label,field in metrics:
        values=pd.to_numeric(cohort.get(field,pd.Series(np.nan,index=cohort.index)),errors="coerce");value=pd.to_numeric(row.get(field),errors="coerce");n=int(values.count())
        result.append({"Metric":label,"Player":value,"Position Average":values.mean(),"Percentile":100*values.le(value).sum()/n if pd.notna(value) and n else np.nan,"Peers":n})
    return pd.DataFrame(result)


def current_historical_comparison(current:pd.Series,historical:pd.Series,metrics:tuple[tuple[str,str,str],...])->pd.DataFrame:
    rows=[]
    for label,current_field,historical_field in metrics:
        now=pd.to_numeric(current.get(current_field),errors="coerce");then=pd.to_numeric(historical.get(historical_field),errors="coerce")
        rows.append({"Metric":label,"Current":now,"Historical":then,"Difference":now-then if pd.notna(now) and pd.notna(then) else np.nan})
    return pd.DataFrame(rows)
