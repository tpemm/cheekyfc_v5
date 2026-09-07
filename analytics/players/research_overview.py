"""Rigid Sprint 9.8B player-research presentation contracts."""
from __future__ import annotations

import numpy as np
import pandas as pd
import html

from analytics.players.comparison import primary_position, stable_player_id

KPI_FIELDS=(
    ("SEASON POINTS","current_fantasy_points"),("AVG PTS/GW","current_points_per_game"),
    ("AVG PTS/START","current_points_per_start"),("GHOST PTS/START","current_ghost_per_start"),
    ("GAMES PLAYED / STARTS","games_starts_display"),("OWNERSHIP","ownership_display"),
    ("xG/90","current_xg_per_90"),("xA/90","current_xa_per_90"),
)

KPI_DIGITS={"current_fantasy_points":1,"current_points_per_game":2,"current_points_per_start":2,"current_ghost_per_start":2,"current_xg_per_90":2,"current_xa_per_90":2}

def format_overview_value(key:str,value)->str:
    """Presentation-only KPI formatting; missing observations remain visibly missing."""
    if isinstance(value,str):return value if value.strip() and value.lower() not in {"none","nan","<na>"} else "—"
    numeric=pd.to_numeric(value,errors="coerce")
    if pd.isna(numeric):return "—"
    if key=="ownership_display":return f"{numeric:.0f}%"
    return f"{numeric:,.{KPI_DIGITS.get(key,1)}f}"

def set_piece_chips(profile:pd.DataFrame)->list[str]:
    if profile.empty:return []
    names={"corner":"Corners","corners":"Corners","direct_free_kick":"Direct FK","indirect_free_kick":"Indirect FK","penalty":"Penalties","penalties":"Penalties"}
    ordered=profile.sort_values([c for c in ("set_piece_type","rank") if c in profile])
    return ordered.apply(lambda x:f"{names.get(str(x.get('set_piece_type','')).lower(),str(x.get('set_piece_type','')).replace('_',' ').title())} #{int(x['rank'])}",axis=1).drop_duplicates().tolist()

def fixture_cards_html(frame:pd.DataFrame)->str:
    if frame.empty:return '<div class="player-empty-inline">No upcoming league fixtures.</div>'
    cards=[]
    for _,row in frame.iterrows():
        gw=html.escape(str(row.get("GW","—")));opponent=html.escape(str(row.get("Opponent","—")));venue=html.escape(str(row.get("H/A","—")));fdr=row.get("FDR",np.nan);fdr="—" if pd.isna(fdr) else f"{float(fdr):g}"
        cards.append(f'<div class="fixture-card"><span>GW {gw}</span><b>{opponent}</b><small>{venue} · FDR {fdr}</small></div>')
    return '<div class="fixture-grid">'+''.join(cards)+'</div>'
FANTASY_AXES=(
    ("Season Points","current_fantasy_points","historical_fantasy_points"),
    ("Avg Pts/Start","current_points_per_start","historical_points_per_start"),
    ("Ghost Pts/Start","current_ghost_per_start","historical_ghost_per_start"),
    ("Games Started","current_start_percentage","historical_start_percentage"),
)
ATTACKING_AXES=(
    ("Goals","current_goals_per_start","historical_goals_per_start"),
    ("Assists","current_assists_per_start","historical_assists_per_start"),
    ("Key Passes","current_key_passes_per_start","historical_key_passes_per_start"),
    ("Shots on Target","current_shots_on_target_per_start","historical_shots_on_target_per_start"),
    ("Successful Dribbles","current_successful_dribbles_per_start","historical_successful_dribbles_per_start"),
)
DEFENSIVE_AXES=(
    ("Tackles Won","current_tackles_won_per_start","historical_tackles_won_per_start"),
    ("Interceptions","current_interceptions_per_start","historical_interceptions_per_start"),
    ("Clearances","current_clearances_per_start","historical_clearances_per_start"),
    ("Aerials Won","current_aerials_won_per_start","historical_aerials_won_per_start"),
    ("Clean Sheets","current_clean_sheets_per_start","historical_clean_sheets_per_start"),
)

SUMMARY_ALIASES={
    "fantasy_points":"current_fantasy_points","fantasy_points_per_game":"current_points_per_game",
    "fantasy_points_per_start":"current_points_per_start","fantasy_points_per_90":"current_points_per_90",
    "ghost_points":"current_ghost_points","ghost_points_per_game":"current_ghost_per_game",
    "ghost_points_per_start":"current_ghost_per_start","ghost_points_per_90":"current_ghost_per_90",
    "games_played":"current_appearances","starts":"current_starts","minutes":"current_minutes",
    "start_percentage":"current_start_percentage","xg":"current_xg","xa":"current_xa","xgi":"current_xgi",
}
for _metric in ("goals","assists","key_passes","shots_on_target","successful_dribbles","tackles_won","interceptions","clearances","aerial_wins","accurate_crosses","clean_sheets","xg","xa","xgi"):
    SUMMARY_ALIASES.setdefault(_metric,f"current_{_metric}")
    for _suffix in ("per_game","per_start","per_90"):
        SUMMARY_ALIASES[f"{_metric}_{_suffix}"]=f"current_{_metric}_{_suffix}"
SUMMARY_ALIASES["aerial_wins"]="current_aerials_won"
for _suffix in ("per_game","per_start","per_90"):SUMMARY_ALIASES[f"aerial_wins_{_suffix}"]=f"current_aerials_won_{_suffix}"


def preserve_canonical_club(frame: pd.DataFrame) -> pd.DataFrame:
    """Resolve display club from the same canonical player row, before ownership joins.

    Players added after the preseason pool can have a populated ``club`` but no
    ``premier_league_club``. Never interpret fantasy ``current_team`` as a club.
    """
    from fantrax.live.current_identity import nonblank
    out = frame.copy()
    primary = out.get("premier_league_club", pd.Series(index=out.index, dtype="string"))
    fallback = out.get("club", pd.Series(index=out.index, dtype="string"))
    out["premier_league_club"] = nonblank(primary).combine_first(nonblank(fallback))
    return out


def overlay_current_summary(frame:pd.DataFrame,summary:pd.DataFrame,observations:pd.DataFrame|None=None)->pd.DataFrame:
    """Promote the canonical 9.8A summary without historical or projection fallback."""
    if frame.empty or summary.empty:return frame.copy()
    from fantrax.live.player_participation import starter_observation_rates
    source=starter_observation_rates(summary,observations) if observations is not None else summary.copy()
    source["fantrax_player_id"]=source.fantrax_player_id.astype(str)
    keep=["fantrax_player_id",*[c for c in SUMMARY_ALIASES if c in source]]
    overlay=source[keep].rename(columns=SUMMARY_ALIASES)
    base=frame.drop(columns=[c for c in overlay if c!="fantrax_player_id" and c in frame],errors="ignore")
    return base.merge(overlay,on="fantrax_player_id",how="left",validate="one_to_one")


def overlay_current_ownership(frame:pd.DataFrame,ownership:pd.DataFrame)->pd.DataFrame:
    """Apply the latest roster snapshot so add/drop state is refresh-sensitive."""
    if frame.empty or ownership.empty:return frame.copy()
    fields=[c for c in ("fantrax_player_id","current_manager_id","current_manager_name","ownership_status","roster_status","available","ownership_change_count") if c in ownership]
    latest=ownership[fields].drop_duplicates("fantrax_player_id",keep="last").copy();latest["fantrax_player_id"]=latest.fantrax_player_id.astype(str)
    base=frame.drop(columns=[c for c in fields if c!="fantrax_player_id" and c in frame],errors="ignore")
    return base.merge(latest,on="fantrax_player_id",how="left",validate="one_to_one")


def overlay_historical_advanced(frame:pd.DataFrame,profile:pd.DataFrame)->pd.DataFrame:
    """Attach compact normalized 2025/26 profile rates; never fill current fields."""
    if frame.empty or profile.empty:return frame.copy()
    mapping={"goals_per_start":"historical_goals_per_start","assists_per_start":"historical_assists_per_start","key_passes_per_start":"historical_key_passes_per_start","shots_on_target_per_start":"historical_shots_on_target_per_start","dribbles_successful_per_start":"historical_successful_dribbles_per_start","tackles_won_per_start":"historical_tackles_won_per_start","interceptions_per_start":"historical_interceptions_per_start","clearances_per_start":"historical_clearances_per_start","aerial_wins_per_start":"historical_aerials_won_per_start"}
    if "tackles_won_per_start" not in profile and "tackles_per_start" in profile:mapping["tackles_per_start"]="historical_tackles_won_per_start"
    compact=profile[["canonical_player_id",*[c for c in mapping if c in profile]]].rename(columns=mapping).copy()
    compact["_historical_key"]=compact.pop("canonical_player_id").astype(str).str.replace(r"^FTX-","",regex=True).str.strip().str.lower()
    compact=compact.drop_duplicates("_historical_key")
    base=frame.drop(columns=[c for c in mapping.values() if c in frame],errors="ignore").copy()
    identity=base.get("historical_fantrax_player_id",base.get("historical_player_id",base.get("fantrax_player_id",pd.Series(index=base.index,dtype=object))))
    base["_historical_key"]=identity.astype("string").str.replace(r"^FTX-","",regex=True).str.strip("*").str.lower()
    out=base.merge(compact,on="_historical_key",how="left",validate="many_to_one").drop(columns="_historical_key")
    semantics={"goals":"WHOSCORED_HISTORICAL","assists":"WHOSCORED_OFFICIAL_ASSIST","key_passes":"WHOSCORED_HISTORICAL_VALIDATED","shots_on_target":"WHOSCORED_HISTORICAL_DERIVED","successful_dribbles":"WHOSCORED_HISTORICAL_VALIDATED","tackles_won":"WHOSCORED_HISTORICAL_VALIDATED","interceptions":"WHOSCORED_HISTORICAL","clearances":"WHOSCORED_HISTORICAL","aerials_won":"WHOSCORED_HISTORICAL"}
    for metric,source in semantics.items():out[f"historical_{metric}_per_start_source"]=source
    return out


def historical_profile_availability(row:pd.Series)->dict:
    """Resolve each profile once while retaining metric-level availability and provenance."""
    result={}
    for name,axes in (("fantasy",FANTASY_AXES),("attacking",ATTACKING_AXES),("defensive",DEFENSIVE_AXES)):
        available=[];missing=[];sources={}
        for label,_,field in axes:
            if pd.notna(pd.to_numeric(row.get(field),errors="coerce")):
                available.append(label);sources[label]=row.get(f"{field}_source","HISTORICAL_COMPACT_PROFILE")
            else:missing.append(label)
        result[name]={"available":len(available)>=3,"available_axes":available,"missing_axes":missing,"sources":sources}
    return result


def resolve_metric(*,fantrax_value,fantrax_observed:bool,derived_value=pd.NA,derived_source="PROVIDER_DERIVED",approximate_value=pd.NA,approximate_source="PROVIDER_OBSERVED") -> dict:
    """Resolve display authority while preserving authoritative Fantrax zeroes."""
    if fantrax_observed and pd.notna(fantrax_value):return {"value":fantrax_value,"source":"FANTRAX","authority":"AUTHORITATIVE"}
    if pd.notna(derived_value):return {"value":derived_value,"source":derived_source,"authority":"VALIDATED_DERIVED"}
    if pd.notna(approximate_value):return {"value":approximate_value,"source":approximate_source,"authority":"CAVEATED_PROVIDER"}
    return {"value":pd.NA,"source":"MISSING","authority":"MISSING"}


def ownership_text(row:pd.Series)->str:
    if str(row.get("available", False)).lower()=="true":
        return "Available / Waivers" if row.get("availability_type")=="WAIVERS" else "Available / Free Agent" if row.get("availability_type")=="FREE_AGENT" else "Available"
    manager=row.get("current_manager_name")
    if pd.notna(manager) and str(manager).strip():return str(manager)
    return "Ownership unknown"


def overview_kpis(row:pd.Series)->list[dict]:
    prepared=row.copy();games=pd.to_numeric(row.get("current_appearances"),errors="coerce");starts=pd.to_numeric(row.get("current_starts"),errors="coerce");prepared["games_starts_display"]=f"{int(games) if pd.notna(games) else 0} / {int(starts) if pd.notna(starts) else 0}"
    pct=pd.to_numeric(row.get("rostered_pct"),errors="coerce");prepared["ownership_display"]=(f"{pct:.0f}%" if pd.notna(pct) else ownership_text(row))
    return [{"label":label,"key":key,"value":prepared.get(key)} for label,key in KPI_FIELDS]


def _cohort(frame:pd.DataFrame,row:pd.Series)->tuple[pd.DataFrame,str]:
    position=primary_position(row);peers=frame[frame.apply(primary_position,axis=1).eq(position)]
    labels={"G":"goalkeepers","GK":"goalkeepers","D":"defenders","DEF":"defenders","M":"midfielders","MID":"midfielders","F":"forwards","FWD":"forwards"}
    return peers,labels.get(position,position.lower() if position else "players")


def fixed_radar_records(frame:pd.DataFrame,row:pd.Series,axes:tuple[tuple[str,str,str],...],historical:bool)->tuple[list[dict],str]:
    """Separate within-season percentiles over one deterministic primary-position cohort."""
    peers,label=_cohort(frame,row);records=[]
    for season,index in (("2026/27 Current",1),("2025/26",2)):
        if index==2 and not historical:continue
        metrics=[]
        for axis,current,historical_field in axes:
            field=current if index==1 else historical_field;values=pd.to_numeric(peers.get(field,pd.Series(index=peers.index,dtype=float)),errors="coerce");raw=pd.to_numeric(row.get(field),errors="coerce")
            pct=float(values.le(raw).sum()/values.count()*100) if pd.notna(raw) and values.count() else np.nan
            metrics.append({"key":axis,"label":axis,"raw":raw,"formatted":"—" if pd.isna(raw) else f"{raw:,.2f}","percentile":pct,"rank":int(values.gt(raw).sum()+1) if pd.notna(raw) else np.nan,"peer_count":int(values.count()),"peer_group":label,"source":season,"low_peers":values.count()<5})
        records.append({"player_id":stable_player_id(row),"player_name":season,"metrics":metrics})
    return records,label


def next_fixtures(fixtures:pd.DataFrame,club_id:str,n:int=5)->pd.DataFrame:
    if fixtures.empty:return pd.DataFrame(columns=["GW","Opponent","H/A","FDR"])
    own=fixtures[fixtures.club_id.astype(str).eq(str(club_id))&~fixtures.completed.fillna(False).astype(bool)].sort_values(["fantrax_period","date"]).head(n)
    return own.rename(columns={"fantrax_period":"GW","opponent":"Opponent","home_away":"H/A","fixture_difficulty":"FDR"})[["GW","Opponent","H/A","FDR"]]


def overview_gameweek_table(match_log:pd.DataFrame,player_id:str,fixtures:pd.DataFrame)->pd.DataFrame:
    own=match_log[match_log.fantrax_player_id.astype(str).eq(str(player_id))].copy() if not match_log.empty else pd.DataFrame()
    columns=["GW","Opponent","H/A","FDR","FPts","Ghost","GP","Start","Minutes","Goals","Assists","KP","SOT","Accurate Crosses","Successful Dribbles","Tackles Won","Interceptions","Clearances","Aerial Wins","Clean Sheets"]
    if own.empty:return pd.DataFrame(columns=columns)
    fdr=dict(zip(fixtures.get("match_id",pd.Series(dtype=str)).astype(str),pd.to_numeric(fixtures.get("fixture_difficulty"),errors="coerce"))) if not fixtures.empty else {}
    table=pd.DataFrame({"GW":own.fantrax_period,"Opponent":own.opponent_id,"H/A":own.venue,"FDR":own.canonical_match_id.astype(str).map(fdr),"FPts":own.fantrax_points,"Ghost":own.ghost_points,"GP":own.appeared.astype(int),"Start":own.started.astype(int),"Minutes":own.minutes,"Goals":own.goals,"Assists":own.assists,"KP":own.key_passes,"SOT":own.shots_on_target,"Accurate Crosses":own.accurate_crosses,"Successful Dribbles":own.successful_dribbles,"Tackles Won":own.tackles_won,"Interceptions":own.interceptions,"Clearances":own.clearances,"Aerial Wins":own.aerial_wins,"Clean Sheets":own.clean_sheets})
    return table.sort_values("GW").reset_index(drop=True)
