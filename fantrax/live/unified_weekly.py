"""Pure Fantrax-first current player-week enrichment and Fantasy Allowed."""
from __future__ import annotations
import pandas as pd
from fantrax.live.current_identity import display_names

SAFE_SUPPLEMENTS={"goals":"goals","key_passes":"key_passes","tackles_won":"tackles_won_derived","interceptions":"interceptions","aerials_won":"aerials_won","accurate_crosses":"accurate_crosses_derived"}
ADVANCED_METRICS=("rating","goals","key_passes","official_assists","cross_attempts","accurate_crosses_derived","dribbles_attempted","dribbles_successful","aerials_attempted","aerials_won","tackle_attempts","tackles_won_derived","tackles","interceptions","clearances","recoveries","blocked_passes","crosses","through_balls","shots","shots_on_target","passes_attempted","passes_completed")

def _numeric(frame:pd.DataFrame,column:str)->pd.Series:return pd.to_numeric(frame.get(column,pd.Series(index=frame.index,dtype=float)),errors="coerce")

def build_unified_weekly(fantrax:pd.DataFrame,advanced:pd.DataFrame,understat:pd.DataFrame,identity:pd.DataFrame,fixtures:pd.DataFrame,clubs:pd.DataFrame)->pd.DataFrame:
    """Keep every all-player Fantrax row and enrich it without changing authority."""
    out=fantrax.copy()
    if out.empty:return out
    out["fantrax_player_id"]=out.fantrax_player_id.astype(str).str.strip("*")
    out["display_name"]=display_names(
        out.get("canonical_name",pd.Series(pd.NA,index=out.index)),
        out.get("player_name",pd.Series(pd.NA,index=out.index)),
    )
    out["fantrax_detail_source"]=out.get("current_manager_id",out.get("manager_id",pd.Series(index=out.index))).notna().map({True:"FANTRAX_DETAILED",False:"FANTRAX_ALL_PLAYER_ONLY"})
    out["fantrax_points_source"]=out.fantasy_points.notna().map({True:"FANTRAX_OFFICIAL",False:"MISSING"})
    bridge=identity.dropna(subset=["canonical_player_id","fantrax_player_id"])[["canonical_player_id","fantrax_player_id"]].drop_duplicates("canonical_player_id").copy() if not identity.empty else pd.DataFrame(columns=["canonical_player_id","fantrax_player_id"])
    bridge["fantrax_player_id"]=bridge.fantrax_player_id.astype(str).str.strip("*")
    if not advanced.empty:
        adv=advanced.copy();mapped=adv.canonical_player_id.astype(str).map(dict(zip(bridge.canonical_player_id.astype(str),bridge.fantrax_player_id)))
        adv["fantrax_player_id"]=adv.get("fantrax_player_id",pd.Series(index=adv.index,dtype=object)).combine_first(mapped)
    else:adv=pd.DataFrame()
    if not adv.empty:
        adv=adv.rename(columns={"aerial_attempts":"aerials_attempted","aerial_wins":"aerials_won","raw_crosses":"crosses"})
        agg={metric:(metric,"mean" if metric=="rating" else "sum") for metric in ADVANCED_METRICS if metric in adv}
        role_column="actual_tactical_role" if "actual_tactical_role" in adv else "actual_position_standardized"
        agg.update(actual_role=(role_column,"last"),formation=("formation","last"),whoscored_manager=("manager_name","last"),whoscored_matches=("canonical_match_id","nunique"))
        aw=adv.groupby(["fantrax_player_id","fantrax_period"],dropna=False,as_index=False).agg(**agg).rename(columns={"fantrax_period":"period"});out=out.merge(aw,on=["fantrax_player_id","period"],how="left",suffixes=("","_whoscored"))
    out["whoscored_available"]=out.get("whoscored_matches",pd.Series(0,index=out.index)).fillna(0).gt(0)
    # Fantrax detail wins, including explicit zero. Approved WhoScored metrics
    # may fill genuine missingness for rostered or all-player-only rows.
    for target,ws in SAFE_SUPPLEMENTS.items():
        ws_col=ws+"_whoscored" if ws in out and ws+"_whoscored" in out else ws
        value=_numeric(out,target);source=out.get(f"{target}_source",pd.Series(index=out.index,dtype=object)).astype("string")
        authoritative=out.fantrax_detail_source.eq("FANTRAX_DETAILED")|source.str.casefold().str.startswith("fantrax",na=False)
        official=value.where(authoritative);supp=_numeric(out,ws_col)
        can_fill=official.isna()&supp.notna()&out.whoscored_available
        out[target]=official.where(~can_fill,supp);out[f"{target}_source"]="MISSING";out.loc[official.notna(),f"{target}_source"]="FANTRAX_DETAILED";out.loc[can_fill,f"{target}_source"]="WHOSCORED_DERIVED_VALIDATED"
    # Clearly named provider concepts; never alias these to Fantrax AT/TkW/CoS.
    for column in ("official_assists","cross_attempts","tackle_attempts"):
        if column in out:out[f"{column}_source"]=out[column].notna().map({True:"WHOSCORED_SOURCE_SPECIFIC",False:"MISSING"})
    if not understat.empty:
        us=understat.copy();us["fantrax_player_id"]=us.fantrax_player_id.astype(str).str.strip("*");keep=[c for c in ("fantrax_player_id","period","xg","xa","xgi","understat_minutes") if c in us];out=out.drop(columns=[c for c in ("xg","xa","xgi","understat_minutes") if c in out]).merge(us[keep].drop_duplicates(["fantrax_player_id","period"]),on=["fantrax_player_id","period"],how="left")
    out["understat_available"]=out.get("xgi",pd.Series(index=out.index,dtype=float)).notna()
    code_map=dict(zip(clubs.fantrax_code.astype(str),clubs.canonical_club_id.astype(str))) if not clubs.empty else {};mapped_club=out.get("club",pd.Series(index=out.index,dtype=object)).map(code_map);out["club_id"]=mapped_club.combine_first(out["club_id"]) if "club_id" in out else mapped_club;out["canonical_position"]=out.get("canonical_position",out.get("fantrax_position",pd.Series(index=out.index))).astype("string").str.split(r"[,/]",regex=True).str[0].str.strip().replace({"G":"GK","D":"DEF","M":"MID","F":"FWD"})
    observed=advanced[["canonical_match_id","club_id","opponent_id","fantrax_period"]].drop_duplicates(["canonical_match_id","club_id"]) if not advanced.empty else pd.DataFrame(columns=["canonical_match_id","club_id","opponent_id","fantrax_period"])
    counts=observed.groupby(["club_id","fantrax_period"]).agg(observed_matches=("canonical_match_id","nunique"),attributed_match_id=("canonical_match_id","first"),attributed_opponent_id=("opponent_id","first")).reset_index().rename(columns={"fantrax_period":"period"});out=out.merge(counts,on=["club_id","period"],how="left");out["fantrax_match_attribution"]=out.observed_matches.map(lambda x:"EXACT_SINGLE_CLUB_MATCH" if x==1 else "AMBIGUOUS_MULTI_FIXTURE_PERIOD" if pd.notna(x) and x>1 else "NO_COMPLETED_MATCH_EVIDENCE")
    out["source_coverage"]=out.apply(lambda r:" + ".join([r.fantrax_detail_source,"WHOSCORED" if r.whoscored_available else "NO_WHOSCORED","UNDERSTAT" if r.understat_available else "NO_UNDERSTAT"]),axis=1)
    return out

def current_fantasy_allowed(unified:pd.DataFrame)->pd.DataFrame:
    columns=["opponent_id","position_group","matches","players","points_allowed","points_allowed_per_match","sample_status"]
    required={"fantrax_match_attribution","fantasy_points","canonical_position"}
    if unified.empty or not required.issubset(unified.columns):return pd.DataFrame(columns=columns)
    eligible=unified[unified.fantrax_match_attribution.eq("EXACT_SINGLE_CLUB_MATCH")&unified.fantasy_points.notna()&unified.canonical_position.isin(["GK","DEF","MID","FWD"])].copy()
    if eligible.empty:return pd.DataFrame(columns=columns)
    result=eligible.groupby(["attributed_opponent_id","canonical_position"],as_index=False).agg(matches=("attributed_match_id","nunique"),players=("fantrax_player_id","nunique"),points_allowed=("fantasy_points","sum")).rename(columns={"attributed_opponent_id":"opponent_id","canonical_position":"position_group"});result["points_allowed_per_match"]=result.points_allowed/result.matches;result["sample_status"]=result.matches.map(lambda n:f"{int(n)} observed match" if n==1 else f"{int(n)} observed matches");return result

def source_coverage(unified:pd.DataFrame)->pd.DataFrame:
    if unified.empty:return pd.DataFrame(columns=["period","source_coverage","players"])
    return unified.groupby(["period","source_coverage"],dropna=False).size().rename("players").reset_index()
