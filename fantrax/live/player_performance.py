"""Cache-only 2026/27 player-performance normalization and aggregation."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from fantrax.live.ghost import derive_return_ghost
from fantrax.live.current_identity import display_names
from fantrax.live.player_participation import add_canonical_rates


EVENT_FIELDS=("goals","assists","shots","shots_on_target","key_passes","accurate_crosses","successful_dribbles","tackles_won","interceptions","clearances","blocks","aerials_won","aerials_lost","dispossessions","fouls_drawn","fouls_committed","yellow_cards","red_cards","clean_sheets","goals_against","saves","penalties_saved","penalties_missed","own_goals")
FALLBACK_FIELDS=("appearance","minutes","goals","assists","shots","key_passes","yellow_cards","red_cards")
PROVENANCE_COLUMNS=(
    tuple(f"fantrax_{metric}" for metric in FALLBACK_FIELDS)
    + tuple(f"understat_{metric}" for metric in FALLBACK_FIELDS if metric!="minutes")
    + tuple(f"{metric}_source" for metric in FALLBACK_FIELDS)
    + ("xg_source","xa_source","xgi_source")
)
WEEKLY_COLUMNS=("season_id","period","fantrax_player_id","registry_player_id","canonical_name","player_name","club","fantrax_position","canonical_position","current_manager_id","current_manager_name","roster_status","lineup_status","fantasy_points","appearance","start","minutes","ghost_points",*EVENT_FIELDS,"xg","xa","xgi","understat_minutes",*PROVENANCE_COLUMNS,"opponent","source","source_retrieved_at","source_fields","build_timestamp","period_complete")

ALIASES={
 "period":("period","fantrax_gw","gameweek"),"fantrax_player_id":("fantrax_player_id","player_id","id"),"player_name":("player_name","Player","mgr_player","avail_player"),"club":("club","team","mgr_team","avail_team"),"fantrax_position":("fantrax_position","eligible_positions","mgr_eligible","avail_position"),"fantasy_points":("fantasy_points","fpts","FPts","mgr_fantasy_points","avail_fpts"),"appearance":("appearance","appeared","gp","mgr_gp"),"start":("start","started","gs","mgr_gs"),"minutes":("minutes","Min","mgr_min"),
 "goals":("goals","G","mgr_g"),"assists":("assists","A","AT","mgr_at"),"shots":("shots","Sh"),"shots_on_target":("shots_on_target","SOT","mgr_sot"),"key_passes":("key_passes","KP","mgr_kp"),"accurate_crosses":("accurate_crosses","AC","mgr_ac"),"successful_dribbles":("successful_dribbles","CoS","mgr_cos"),"tackles_won":("tackles_won","TkW","mgr_tkw"),"interceptions":("interceptions","Int","mgr_int"),"clearances":("clearances","CLR","mgr_clr"),"blocks":("blocks","BS","mgr_bs"),"aerials_won":("aerials_won","AER","mgr_aer"),"aerials_lost":("aerials_lost","AERL"),"dispossessions":("dispossessions","DIS","mgr_dis"),"fouls_drawn":("fouls_drawn","FD"),"fouls_committed":("fouls_committed","FC"),"yellow_cards":("yellow_cards","YC","mgr_yc"),"red_cards":("red_cards","RC","mgr_rc"),"clean_sheets":("clean_sheets","CS","mgr_cs"),"goals_against":("goals_against","GA","mgr_ga"),"saves":("saves","Sv","mgr_sv"),"penalties_saved":("penalties_saved","PKS","mgr_pks"),"penalties_missed":("penalties_missed","PKM","mgr_pkm"),"own_goals":("own_goals","OG","mgr_og"),"opponent":("opponent","mgr_opponent","avail_opponent"),
}


def empty_weekly() -> pd.DataFrame: return pd.DataFrame(columns=WEEKLY_COLUMNS)


def _source(frame: pd.DataFrame, aliases: tuple[str,...]) -> pd.Series:
    column=next((name for name in aliases if name in frame),None)
    return frame[column] if column else pd.Series(pd.NA,index=frame.index)


def normalize_weekly_export(frame: pd.DataFrame, *, retrieved_at: str, season_id: str="2627", period: int|None=None) -> pd.DataFrame:
    """Normalize the proven weekly export without interpreting missing as zero."""
    out=pd.DataFrame(index=frame.index)
    for target,aliases in ALIASES.items(): out[target]=_source(frame,aliases)
    out["season_id"]=season_id
    if period is not None: out["period"]=int(period)
    out["period"]=pd.to_numeric(out["period"],errors="coerce").astype("Int64")
    out["fantrax_player_id"]=out["fantrax_player_id"].astype("string").str.strip().str.strip("*")
    for column in ("fantasy_points","appearance","start","minutes",*EVENT_FIELDS): out[column]=pd.to_numeric(out[column],errors="coerce")
    out["canonical_position"]=out["fantrax_position"].astype("string").str.split(r"[,/]",regex=True).str[0].str.strip()
    out["registry_player_id"]=pd.NA; out["canonical_name"]=pd.NA
    out["current_manager_id"]=_source(frame,("current_manager_id","manager_id")); out["current_manager_name"]=_source(frame,("current_manager_name","manager_name"))
    out["lineup_status"]=_source(frame,("lineup_status","status")); out["roster_status"]=_source(frame,("roster_status",))
    out.loc[out["roster_status"].isna()&out["current_manager_id"].notna(),"roster_status"]="ROSTERED"
    for column in ("xg","xa","xgi","understat_minutes"): out[column]=np.nan
    for column in FALLBACK_FIELDS:
        out[f"fantrax_{column}"]=out[column]; out[f"understat_{column}"]=np.nan
        out[f"{column}_source"]=out[column].notna().map({True:"fantrax_weekly",False:pd.NA})
    for column in ("xg","xa","xgi"): out[f"{column}_source"]=pd.NA
    out["ghost_points"]=out.apply(_ghost_points,axis=1)
    out["source"]="Fantrax weekly CSV/export fallback"; out["source_retrieved_at"]=retrieved_at; out["source_fields"]=",".join(frame.columns); out["build_timestamp"]=datetime.now(timezone.utc).isoformat()
    if "period_complete" in frame:
        complete=frame["period_complete"]
        out["period_complete"]=complete.fillna(True) if pd.api.types.is_bool_dtype(complete) else complete.astype("string").str.strip().str.lower().map({"true":True,"1":True,"yes":True,"false":False,"0":False,"no":False}).fillna(True)
    else:
        out["period_complete"]=True
    return out.reindex(columns=WEEKLY_COLUMNS)


def _ghost_points(row: pd.Series) -> float:
    result=derive_return_ghost(fantasy_points=row.get("fantasy_points"),position=row.get("canonical_position"),goals=row.get("goals"),assists=row.get("assists"),clean_sheets=row.get("clean_sheets"),appeared=bool(pd.to_numeric(row.get("appearance"),errors="coerce") or 0))
    return result["ghost_points"]


def load_cached_weekly_exports(raw_root: Path) -> pd.DataFrame:
    parts=[]
    player_root=raw_root/"player_stats"
    candidates=sorted(set(player_root.glob("*.csv"))|set(player_root.rglob("weekly_player_stats.csv"))) if player_root.exists() else []
    for path in candidates:
        metadata_path=path.parent/"metadata.json"; metadata={}
        if metadata_path.exists():
            try: metadata=json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError,ValueError): metadata={}
        retrieved=str(metadata.get("retrieved_at") or datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat())
        normalized=normalize_weekly_export(pd.read_csv(path),retrieved_at=retrieved,period=metadata.get("period"))
        if metadata: normalized["period_complete"]=bool(metadata.get("finalized",False))
        parts.append(normalized)
    if not parts: return empty_weekly()
    return pd.concat(parts,ignore_index=True).drop_duplicates(["fantrax_player_id","period"],keep="last").reindex(columns=WEEKLY_COLUMNS)


def enrich_weekly(weekly: pd.DataFrame, registry: pd.DataFrame, ownership: pd.DataFrame, rosters: pd.DataFrame) -> pd.DataFrame:
    if weekly.empty: return weekly.copy()
    out=weekly.copy()
    if not registry.empty:
        cols=[c for c in ("fantrax_player_id","registry_player_id","canonical_name") if c in registry]; reg=registry[cols].copy(); reg["fantrax_player_id"]=reg["fantrax_player_id"].astype("string"); out=out.drop(columns=[c for c in ("registry_player_id","canonical_name") if c in out]).merge(reg.drop_duplicates("fantrax_player_id"),on="fantrax_player_id",how="left")
    out["player_name"] = display_names(out.get("canonical_name", pd.Series(pd.NA, index=out.index)), out["player_name"])
    if not rosters.empty:
        cols=[c for c in ("period","fantrax_player_id","manager_id","manager_name","roster_status","lineup_status") if c in rosters]; roster=rosters[cols].drop_duplicates(["period","fantrax_player_id"],keep="last").rename(columns={"manager_id":"current_manager_id_api","manager_name":"current_manager_name_api","roster_status":"roster_status_api","lineup_status":"lineup_status_api"}); out=out.merge(roster,on=["period","fantrax_player_id"],how="left")
        for column in ("current_manager_id","current_manager_name","roster_status","lineup_status"):
            api=column+"_api"
            if api in out: out[column]=out[api].combine_first(out[column]); out=out.drop(columns=api)
    return out.reindex(columns=WEEKLY_COLUMNS)


def completed_window(weekly: pd.DataFrame, window: str) -> tuple[pd.DataFrame,str]:
    complete=weekly[weekly.get("period_complete",pd.Series(False,index=weekly.index)).fillna(False).astype(bool)].copy()
    periods=sorted(pd.to_numeric(complete.get("period"),errors="coerce").dropna().astype(int).unique())
    requested=None if window=="Season" else int(window.split()[-1]); selected=periods if requested is None else periods[-requested:]
    label="Season" if requested is None else f"Last {requested} ({len(selected)} available)" if len(selected)<requested else f"Last {requested}"
    return complete[pd.to_numeric(complete.get("period"),errors="coerce").isin(selected)].copy(),label


def aggregate_player_window(weekly: pd.DataFrame, window: str="Season", *, include_partial:bool=False) -> tuple[pd.DataFrame,str]:
    if include_partial:
        source=weekly.copy();periods=sorted(pd.to_numeric(source.get("period"),errors="coerce").dropna().astype(int).unique());requested=None if window=="Season" else int(window.split()[-1]);selected=periods if requested is None else periods[-requested:];source=source[pd.to_numeric(source.get("period"),errors="coerce").isin(selected)];label="Season (including active period)" if requested is None else f"Last {requested} (including active period)"
    else:source,label=completed_window(weekly,window)
    if source.empty: return pd.DataFrame(),label
    sums=("fantasy_points","ghost_points","minutes",*EVENT_FIELDS,"xg","xa","xgi","understat_minutes")
    aggregations={column:(column,lambda values:pd.to_numeric(values,errors="coerce").sum(min_count=1)) for column in sums if column in source}
    for column in ("appearance","start"): aggregations[column]=(column,lambda values:pd.to_numeric(values,errors="coerce").sum(min_count=1))
    for column in ("registry_player_id","canonical_name","player_name","club","fantrax_position","canonical_position","current_manager_id","current_manager_name","roster_status"): aggregations[column]=(column,"last")
    out=source.groupby("fantrax_player_id",as_index=False).agg(**aggregations); out["periods_covered"]=source.groupby("fantrax_player_id")["period"].nunique().values
    out["games_played"]=out["appearance"];out["starts"]=out["start"]
    out=add_canonical_rates(out,tuple(x for x in ("fantasy_points","ghost_points",*EVENT_FIELDS,"xg","xa","xgi") if x in out))
    out["start_percentage"]=pd.to_numeric(out["start"],errors="coerce").mul(100).div(pd.to_numeric(out["appearance"],errors="coerce").where(pd.to_numeric(out["appearance"],errors="coerce").gt(0)))
    out["minutes_per_game"]=pd.to_numeric(out["minutes"],errors="coerce").div(pd.to_numeric(out["appearance"],errors="coerce").where(pd.to_numeric(out["appearance"],errors="coerce").gt(0)))
    return out,label


def manager_player_weekly(weekly: pd.DataFrame) -> pd.DataFrame:
    columns=("season_id","period","current_manager_id","current_manager_name","fantrax_player_id","registry_player_id","player_name","roster_status","lineup_status","canonical_position","fantrax_position","fantasy_points","ghost_points","minutes","start","goals","assists","key_passes","tackles_won","interceptions","aerials_won","xg","xa","xgi","club","opponent","source","source_retrieved_at")
    owned=weekly[weekly.get("current_manager_id",pd.Series(index=weekly.index,dtype=object)).notna()] if not weekly.empty else weekly
    return owned.reindex(columns=columns).rename(columns={"current_manager_id":"manager_id","current_manager_name":"manager_name"}) if not owned.empty else pd.DataFrame(columns=["manager_id" if c=="current_manager_id" else "manager_name" if c=="current_manager_name" else c for c in columns])


def weekly_validation(weekly: pd.DataFrame) -> pd.DataFrame:
    checks=[]
    def add(rule,status,detail): checks.append({"dataset":"current_player_weekly","rule":rule,"status":status,"detail":detail})
    add("unique_player_period","pass" if weekly.empty or not weekly.duplicated(["fantrax_player_id","period"]).any() else "fail",f"{len(weekly)} rows")
    add("stable_player_id","pass" if weekly.empty or weekly["fantrax_player_id"].notna().all() else "fail",f"{weekly['fantrax_player_id'].isna().sum() if 'fantrax_player_id' in weekly else 0} missing")
    minutes=pd.to_numeric(weekly.get("minutes"),errors="coerce") if not weekly.empty else pd.Series(dtype=float); add("nonnegative_minutes","pass" if not minutes.lt(0).any() else "fail",f"{int(minutes.lt(0).sum())} negative")
    add("preseason_empty_is_valid","pass","No false player-period rows are generated before a proven weekly source exists" if weekly.empty else "Weekly source present")
    return pd.DataFrame(checks)


STAT_FIELD_MAP={"KP":"key_passes","AER":"aerials_won","CLR":"clearances","CoS":"successful_dribbles","DIS":"dispossessions","G":"goals","OG":"own_goals","Int":"interceptions","GA":"goals_against","HCS":"high_claims","PKS":"penalties_saved","RC":"red_cards","Sv":"saves","SOT":"shots_on_target","CS":"clean_sheets","TkW":"tackles_won","Sm":"smothers","YC":"yellow_cards","AT":"assists","AC":"accurate_crosses","BS":"blocks","GAO":"goals_against_outfield","GS":"starts","Min":"minutes","PKD":"penalties_drawn","PKM":"penalties_missed","SBOF":"successful_dribbles_off","SBON":"successful_dribbles"}
PROVEN_WEEKLY_SHORT_NAMES=frozenset(STAT_FIELD_MAP)


def stat_dictionary(league_payload: dict[str,Any]) -> pd.DataFrame:
    rows=[]; groups=league_payload.get("scoringSystem",{}).get("scoringCategorySettings",[])
    for group in groups:
        group_name=group.get("group",{}).get("name")
        for config in group.get("configs",[]):
            stat=config.get("scoringCategory",{}); short=stat.get("shortName"); position=config.get("position",{}).get("shortName")
            normalized=STAT_FIELD_MAP.get(short,"unmapped")
            classification="FANTRAX_PRIMARY_UNDERSTAT_FALLBACK" if normalized in {"goals","assists","minutes","shots","key_passes","yellow_cards","red_cards"} else "FANTRAX_ONLY"
            rows.append({"fantrax_stat_id":stat.get("id"),"raw_label":stat.get("name"),"raw_short_name":short,"weekly_source_column":short,"weekly_source_available":short in PROVEN_WEEKLY_SHORT_NAMES,"normalized_field":normalized,"category":group_name,"scoring_weight":config.get("points"),"unit":"count","direction":"higher" if (config.get("points") or 0)>=0 else "lower","available_by_period":short in PROVEN_WEEKLY_SHORT_NAMES,"source_class":classification,"api_availability":"Scoring definition only; values require Fantrax weekly export","endpoint":"getLeagueInfo scoringSystem","provenance_notes":f"Position {position}; Understat fallback is analytical only and never enters Fantrax scoring"})
    for field,label in (("xg","Expected Goals"),("xa","Expected Assists"),("xgi","Expected Goal Involvement")):
        rows.append({"fantrax_stat_id":pd.NA,"raw_label":label,"raw_short_name":pd.NA,"weekly_source_column":pd.NA,"weekly_source_available":False,"normalized_field":field,"category":"Expected statistics","scoring_weight":pd.NA,"unit":"expected goals","direction":"higher","available_by_period":True,"source_class":"UNDERSTAT_PRIMARY","api_availability":"Not a Fantrax field","endpoint":"Understat player match stats","provenance_notes":"Understat-only; per-90 uses Understat minutes"})
    return pd.DataFrame(rows).drop_duplicates(["fantrax_stat_id","category","provenance_notes"])
