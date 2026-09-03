"""Presentation-only player match analysis over registered weekly datasets."""
from __future__ import annotations

import numpy as np
import pandas as pd

DEFAULT_COLUMNS=("GW","Opponent","H/A","FDR","Minutes","Started","Points","Ghost Points","Goals","Assists")
OPTIONAL_FIELDS={
    "Shots":"shots","Shots on Target":"shots_on_target","Key Passes":"key_passes","Accurate Crosses":"accurate_crosses","Successful Dribbles":"successful_dribbles","xG":"xg","xA":"xa","xGI":"xgi",
    "Tackles Won":"tackles_won","Interceptions":"interceptions","Clearances":"clearances","Blocks":"blocks","Aerials Won":"aerials_won","Aerials Lost":"aerials_lost",
    "Dispossessions":"dispossessions","Fouls Drawn":"fouls_drawn","Fouls Committed":"fouls_committed","Yellow Cards":"yellow_cards","Red Cards":"red_cards",
    "Saves":"saves","Clean Sheets":"clean_sheets","Goals Against":"goals_against","Penalties Saved":"penalties_saved",
}

RESEARCH_COLUMNS=("GW","Date","Opp","H/A","Result","FDR","Start","Min","Position","Formation","Rating","FPts","Ghost","G","A","xG","xA","KP","SOT","AC","TkW","Int","CLR","AER","CS")

def prepare_match_research_frame(source:pd.DataFrame,player_id:str,*,season:str)->pd.DataFrame:
    """Normalize compact canonical current/historical player-match products."""
    if source.empty:return pd.DataFrame()
    ids=_series(source,"fantrax_player_id").astype("string").str.replace(r"^FTX-","",regex=True).str.strip("*").str.lower()
    own=source[ids.eq(str(player_id).replace("FTX-","").strip("*").lower())].copy()
    if own.empty:return pd.DataFrame()
    historical=season.startswith("2025")
    aliases={
        "match_id":"canonical_match_id","period":"fantrax_period","opponent":"opponent_id","venue":"venue","date":"date","minutes":"minutes","formation":"formation","rating":"rating","xg":"xg","xa":"xa","goals":"goals","key_passes":"key_passes","shots_on_target":"shots_on_target","interceptions":"interceptions","clearances":"clearances","aerials_won":"aerial_wins" if not historical else "aerial_wins","fantasy_points":"fantrax_points","ghost_points":"ghost_points",
        "started":"started","position":"fantrax_position" if not historical else "actual_tactical_role","role":"tactical_role" if not historical else "actual_tactical_role","assists":"assists","accurate_crosses":"accurate_crosses" if not historical else "raw_crosses","tackles_won":"tackles_won" if not historical else "mgr_tkw","clean_sheets":"clean_sheets",
    }
    result=pd.DataFrame(index=own.index)
    for target,column in aliases.items():result[target]=_series(own,column)
    if not historical:
        result["appearance"]=_series(own,"appeared");result["assist_source"]=_series(own,"assist_source");result["ghost_source"]=_series(own,"ghost_points_source");result["clean_sheet_source"]=_series(own,"clean_sheet_source")
        result["result"]=_num(own,"team_goals_for").astype("Int64").astype("string")+"–"+_num(own,"team_goals_against").astype("Int64").astype("string")
    else:
        result["appearance"]=_num(own,"started").fillna(0).gt(0)|_num(own,"fantrax_points").notna()|_num(own,"rating").notna();result["assist_source"]="WHOSCORED_OFFICIAL_ASSIST";result["ghost_source"]=np.where(_num(own,"ghost_points").notna(),"FANTRAX_HISTORICAL","MISSING");result["clean_sheet_source"]="MISSING";result["result"]=pd.NA
    result["season"]=season;result["appearance_type"]=np.where(_num(result,"started").gt(0),"Started",np.where(pd.Series(result["appearance"],index=result.index).fillna(False).astype(bool),"Sub",pd.NA))
    result["venue"]=_series(result,"venue").astype("string").str.upper().replace({"HOME":"H","AWAY":"A"})
    result["xgi"]=_num(result,"xg")+_num(result,"xa")
    return result.sort_values(["period","date"],kind="stable").reset_index(drop=True)

def match_research_summary(frame:pd.DataFrame)->dict:
    starts=frame[_num(frame,"started").gt(0)&_num(frame,"fantasy_points").notna()]
    points=_num(starts,"fantasy_points");ghost=_num(starts,"ghost_points");minutes=_num(starts,"minutes")
    count=len(points);enough=count>=10
    total=_num(frame,"fantasy_points").sum(min_count=1);ghost_total=_num(frame,"ghost_points").sum(min_count=1)
    exact_ghost=_series(frame,"ghost_source").dropna().astype(str).str.contains("FANTRAX",case=False).all() and _series(frame,"ghost_source").notna().any()
    dependency=(total-ghost_total)/total*100 if exact_ghost and pd.notna(total) and total!=0 and pd.notna(ghost_total) else np.nan
    return {"starts":count,"fpts_per_start":points.mean(),"ghost_per_start":ghost.mean(),"fpts_per_90":_num(frame,"fantasy_points").sum(min_count=1)*90/_num(frame,"minutes").sum(min_count=1) if _num(frame,"minutes").sum(min_count=1)>0 else np.nan,"minutes_per_start":minutes.mean(),"median":points.median(),"floor":points.quantile(.10) if enough else np.nan,"ceiling":points.quantile(.90) if enough else np.nan,"std_dev":points.std(ddof=0) if count>=2 else np.nan,"return_dependency":dependency,"return_dependency_estimated":not exact_ghost}

def production_distribution(frame:pd.DataFrame)->pd.DataFrame:
    points=_num(frame[_num(frame,"started").gt(0)],"fantasy_points").dropna();bins=[-np.inf,10,15,20,np.inf];labels=("<10","10–14.9","15–19.9","20+")
    counts=pd.cut(points,bins=bins,labels=labels,right=False).value_counts(sort=False)
    return pd.DataFrame({"Band":labels,"Starts":[int(counts.get(label,0)) for label in labels],"Share":[counts.get(label,0)/len(points)*100 if len(points) else np.nan for label in labels]})

def prepare_match_research_table(frame:pd.DataFrame)->pd.DataFrame:
    if frame.empty:return pd.DataFrame(columns=RESEARCH_COLUMNS)
    started=_num(frame,"started");table=pd.DataFrame({"GW":frame.get("period"),"Date":frame.get("date"),"Opp":frame.get("opponent"),"H/A":frame.get("venue"),"Result":frame.get("result"),"FDR":frame.get("fdr"),"Start":started.map(lambda x:"Yes" if pd.notna(x) and x>0 else "No" if pd.notna(x) else pd.NA),"Min":frame.get("minutes"),"Position":frame.get("position"),"Formation":frame.get("formation"),"Rating":frame.get("rating"),"FPts":frame.get("fantasy_points"),"Ghost":frame.get("ghost_points"),"G":frame.get("goals"),"A":frame.get("assists"),"xG":frame.get("xg"),"xA":frame.get("xa"),"KP":frame.get("key_passes"),"SOT":frame.get("shots_on_target"),"AC":frame.get("accurate_crosses"),"TkW":frame.get("tackles_won"),"Int":frame.get("interceptions"),"CLR":frame.get("clearances"),"AER":frame.get("aerials_won"),"CS":frame.get("clean_sheets")})
    return table[list(RESEARCH_COLUMNS)]
_HISTORICAL_ALIASES={
    "period":"fantrax_gw","fantasy_points":"mgr_fantasy_points","fantasy_points_fallback":"avail_fpts","minutes":"mgr_min","start":"mgr_gs","appearance":"mgr_gp","opponent":"mgr_opponent","opponent_fallback":"avail_opponent","roster_status":"mgr_status",
    "goals":"mgr_g","assists":"mgr_at","shots":"shots","shots_on_target":"mgr_sot","key_passes":"mgr_kp","accurate_crosses":"mgr_ac","successful_dribbles":"mgr_cos","xg":"xg","xa":"xa","tackles_won":"mgr_tkw","interceptions":"mgr_int","clearances":"mgr_clr","blocks":"mgr_bs","aerials_won":"mgr_aer","dispossessions":"mgr_dis","yellow_cards":"mgr_yc","red_cards":"mgr_rc","saves":"mgr_sv","clean_sheets":"mgr_cs","goals_against":"mgr_ga","penalties_saved":"mgr_pks",
}


def _series(frame:pd.DataFrame,column:str)->pd.Series:
    return frame[column] if column in frame else pd.Series(pd.NA,index=frame.index)


def _num(frame:pd.DataFrame,column:str)->pd.Series:
    return pd.to_numeric(_series(frame,column),errors="coerce")


def _opponent(value)->tuple[object,object]:
    if pd.isna(value) or not str(value).strip(): return pd.NA,pd.NA
    text=str(value).strip(); away=text.startswith("@"); clean=text[1:] if away else text
    return clean.split()[0],"A" if away else "H"


def prepare_player_gameweek_frame(weekly:pd.DataFrame,player_id:str,*,season:str,include_live:bool=False)->pd.DataFrame:
    """Normalize one player's proven Fantrax scoring-period rows without zero filling."""
    if weekly.empty: return _empty()
    source=weekly.copy(); ids=_series(source,"fantrax_player_id").astype("string").str.strip().str.strip("*")
    own=source[ids.eq(str(player_id).strip().strip("*"))].copy()
    if own.empty: return _empty()
    historical=season=="2025/26"
    if not historical and not include_live:
        complete=_series(own,"period_complete")
        mask=complete.fillna(False).astype(bool) if not complete.empty else pd.Series(False,index=own.index)
        own=own[mask].copy()
    result=pd.DataFrame(index=own.index)
    if historical:
        result["period"]=_num(own,_HISTORICAL_ALIASES["period"])
        result["fantasy_points"]=_num(own,"mgr_fantasy_points").combine_first(_num(own,"avail_fpts"))
        for field in ("minutes","start","appearance","goals","assists","shots","shots_on_target","key_passes","accurate_crosses","successful_dribbles","xg","xa","tackles_won","interceptions","clearances","blocks","aerials_won","dispossessions","yellow_cards","red_cards","saves","clean_sheets","goals_against","penalties_saved"):
            result[field]=_num(own,_HISTORICAL_ALIASES.get(field,field))
        result["opponent"]=_series(own,"mgr_opponent").combine_first(_series(own,"avail_opponent")); result["roster_status"]=_series(own,"mgr_status")
        result["ghost_points"]=np.nan; result["aerials_lost"]=np.nan; result["fouls_drawn"]=np.nan; result["fouls_committed"]=np.nan
    else:
        result["period"]=_num(own,"period")
        for field in ("fantasy_points","ghost_points","minutes","start","appearance",*OPTIONAL_FIELDS.values()): result[field]=_num(own,field)
        result["opponent"]=_series(own,"opponent"); result["roster_status"]=_series(own,"roster_status")
    result["xgi"]=_num(result,"xgi").combine_first(_num(result,"xg")+_num(result,"xa"))
    parsed=result["opponent"].map(_opponent); result["opponent"]=parsed.map(lambda item:item[0]); result["venue"]=parsed.map(lambda item:item[1])
    result["fdr"]=_num(own,next((field for field in ("fdr","fixture_difficulty") if field in own),"__missing__"))
    appeared=_num(result,"appearance").gt(0)|_num(result,"minutes").gt(0); started=_num(result,"start").gt(0)
    result["appearance_type"]=pd.Series(pd.NA,index=result.index,dtype="object"); result.loc[started,"appearance_type"]="Started"; result.loc[appeared&~started,"appearance_type"]="Sub"
    proven_dnp=result["roster_status"].notna()&_num(result,"minutes").eq(0)&_num(result,"appearance").eq(0); result.loc[proven_dnp,"appearance_type"]="DNP"
    result["season"]=season
    return result.sort_values("period",kind="stable").reset_index(drop=True)


def prepare_last_n_periods(frame:pd.DataFrame,n:int=5)->pd.DataFrame:
    periods=sorted(pd.to_numeric(_series(frame,"period"),errors="coerce").dropna().unique())[-n:]
    return frame[pd.to_numeric(_series(frame,"period"),errors="coerce").isin(periods)].sort_values("period",kind="stable").reset_index(drop=True)


def supported_optional_columns(frame:pd.DataFrame)->tuple[str,...]:
    return tuple(label for label,field in OPTIONAL_FIELDS.items() if field in frame and pd.to_numeric(frame[field],errors="coerce").notna().any())


def prepare_gameweek_table(frame:pd.DataFrame,*,home_away:str="All",appearance:str="All",fdr_range:tuple[float,float]|None=None,extra_columns:tuple[str,...]=())->pd.DataFrame:
    filtered=frame.copy()
    if home_away!="All": filtered=filtered[filtered["venue"].eq("H" if home_away=="Home" else "A")]
    if appearance!="All": filtered=filtered[filtered["appearance_type"].eq(appearance)]
    if fdr_range is not None and pd.to_numeric(filtered.get("fdr"),errors="coerce").notna().any(): filtered=filtered[pd.to_numeric(filtered["fdr"],errors="coerce").between(*fdr_range)]
    table=pd.DataFrame({"GW":filtered.get("period"),"Opponent":filtered.get("opponent"),"H/A":filtered.get("venue"),"FDR":filtered.get("fdr"),"Minutes":filtered.get("minutes"),"Started":filtered.get("start").map(lambda value:"Yes" if pd.notna(value) and float(value)>0 else "No" if pd.notna(value) else pd.NA),"Points":filtered.get("fantasy_points"),"Ghost Points":filtered.get("ghost_points"),"Goals":filtered.get("goals"),"Assists":filtered.get("assists")})
    for label in extra_columns:
        field=OPTIONAL_FIELDS.get(label)
        if field in filtered: table[label]=filtered[field]
    return table.sort_values("GW",kind="stable").reset_index(drop=True)


def calculate_home_away_split(frame:pd.DataFrame,basis:str)->pd.DataFrame:
    rows=[]
    for label,venue in (("Home","H"),("Away","A")):
        own=frame[frame.get("venue",pd.Series(index=frame.index,dtype=object)).eq(venue)]; points=_num(own,"fantasy_points")
        if basis=="Per Game": denominator=int((_num(own,"appearance").gt(0)|_num(own,"minutes").gt(0)).sum()); value=points.sum(min_count=1)/denominator if denominator else np.nan
        elif basis=="Per Start": denominator=int(_num(own,"start").gt(0).sum()); value=points.sum(min_count=1)/denominator if denominator else np.nan
        else: denominator=_num(own,"minutes").sum(min_count=1); value=points.sum(min_count=1)*90/denominator if pd.notna(denominator) and denominator>0 else np.nan
        rows.append({"Venue":label,"Average":value,"Sample":denominator})
    return pd.DataFrame(rows)


def calculate_points_breakdown(frame:pd.DataFrame)->dict:
    total=_num(frame,"fantasy_points").sum(min_count=1); ghost=_num(frame,"ghost_points").sum(min_count=1)
    non_ghost=total-ghost if pd.notna(total) and pd.notna(ghost) else np.nan
    return {"total":total,"ghost":ghost,"non_ghost":non_ghost,"pie_safe":pd.notna(ghost) and pd.notna(non_ghost) and ghost>=0 and non_ghost>=0}


def _empty()->pd.DataFrame:
    return pd.DataFrame(columns=("season","period","opponent","venue","fdr","minutes","start","appearance","appearance_type","fantasy_points","ghost_points","goals","assists",*OPTIONAL_FIELDS.values()))
