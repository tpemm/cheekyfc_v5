"""Cached percentile preparation and session-only comparison state."""
from __future__ import annotations
import numpy as np
import pandas as pd
import streamlit as st
from analytics.players.comparison_catalog import CATALOG, validate_metrics

COMPARE_KEY="player_compare_ids"; MAX_PLAYERS=5; MIN_POSITION_PEERS=5

def primary_position(row):
    canonical=str(row.get("canonical_position","")).strip()
    if canonical and canonical.lower() not in {"nan","none"}: return canonical
    raw=str(row.get("fantrax_position","")).replace("/",",")
    return next((part.strip() for part in raw.split(",") if part.strip()),"Unknown")

def stable_player_id(row):
    for field in ("registry_player_id","master_player_id","fantrax_player_id"):
        value=row.get(field)
        if pd.notna(value) and str(value).strip(): return str(value)
    return str(row.get("player_name","Unknown"))

def deterministic_tags(row):
    tags=[]
    rules=(("High Floor","historical_ghost_per_90",8),("Strong Historical Production","historical_points_per_90",12),("Strong xGI","historical_xgi_per_90",.5),("Minutes Secure","projected_minutes_percentage",80),("Fixture Boost","next_five_fixture_ease_percentile",60))
    for label,field,threshold in rules:
        value=pd.to_numeric(row.get(field),errors="coerce")
        if pd.notna(value) and value>=threshold: tags.append(label)
    projected=pd.to_numeric(row.get("projected_minutes_percentage"),errors="coerce")
    historical=pd.to_numeric(row.get("historical_minutes"),errors="coerce")
    if pd.notna(projected) and projected<50: tags.append("Rotation Risk")
    if bool(row.get("available",False)): tags.append("Free Agent")
    if len([p for p in str(row.get("fantrax_position","")).replace("/",",").split(",") if p.strip()])>1: tags.append("Multi-Position")
    adp_value=pd.to_numeric(row.get("value_vs_adp"),errors="coerce")
    if pd.notna(adp_value): tags.append("ADP Value" if adp_value>5 else "ADP Reach" if adp_value< -5 else "Near ADP")
    if pd.isna(historical) or historical<450: tags.append("Limited Historical Sample")
    if pd.isna(row.get("adp")): tags.append("No ADP")
    if pd.isna(row.get("historical_xgi")) and pd.isna(row.get("historical_xgi_per_90")): tags.append("No Understat Sample")
    return tags

def add_compare(state,pid):
    current=list(state.get(COMPARE_KEY,[])); pid=str(pid)
    if pid in current: return False,"Already in comparison"
    if len(current)>=MAX_PLAYERS: return False,"Comparison is limited to five players"
    state[COMPARE_KEY]=[*current,pid]; return True,"Added to comparison"
def remove_compare(state,pid): state[COMPARE_KEY]=[x for x in state.get(COMPARE_KEY,[]) if str(x)!=str(pid)]
def clear_compare(state): state[COMPARE_KEY]=[]

@st.cache_data(show_spinner=False)
def prepare_percentiles(frame:pd.DataFrame, metric_keys:tuple[str,...], rate_basis:str)->pd.DataFrame:
    validate_metrics(metric_keys)
    base=pd.DataFrame(index=frame.index); base["player_id"]=frame.apply(stable_player_id,axis=1); base["peer_position"]=frame.apply(primary_position,axis=1)
    for key in metric_keys:
        metric=CATALOG[key]; field=metric.field_for(rate_basis); raw=pd.to_numeric(frame.get(field,pd.Series(np.nan,index=frame.index)),errors="coerce")
        rank=raw.rank(method="min",ascending=not metric.higher_is_better,na_option="keep")
        pct=raw.rank(method="average",pct=True,ascending=metric.higher_is_better)*100
        base[f"{key}__raw"]=raw; base[f"{key}__league_pct"]=pct; base[f"{key}__league_rank"]=rank
        grouped=raw.groupby(base["peer_position"]); base[f"{key}__position_pct"]=grouped.rank(method="average",pct=True,ascending=metric.higher_is_better)*100
        base[f"{key}__position_rank"]=grouped.rank(method="min",ascending=not metric.higher_is_better,na_option="keep")
        base[f"{key}__position_n"]=grouped.transform("count"); base[f"{key}__league_n"]=raw.count()
    return base

def radar_records(frame,players,metric_keys,rate_basis,percentile_basis):
    prepared=prepare_percentiles(frame,tuple(metric_keys),rate_basis); lookup=prepared.set_index("player_id"); rows=[]; prefix=percentile_basis.lower()
    for _,player in players.iterrows():
        pid=stable_player_id(player)
        if pid not in lookup.index: continue
        values=[]
        for key in metric_keys:
            metric=CATALOG[key]; row=lookup.loc[pid]; n=int(row[f"{key}__{prefix}_n"]); raw=row[f"{key}__raw"]
            values.append({"key":key,"label":metric.label_for(rate_basis),"raw":raw,"formatted":format_metric(raw,metric),"percentile":row[f"{key}__{prefix}_pct"],"rank":row[f"{key}__{prefix}_rank"],"peer_count":n,"peer_group":"League" if prefix=="league" else str(row["peer_position"]),"source":metric.source,"low_peers":prefix=="position" and n<MIN_POSITION_PEERS})
        rows.append({"player_id":pid,"player_name":str(player.get("player_name","Unknown")),"metrics":values})
    return rows

def format_metric(value,metric):
    if pd.isna(value): return "—"
    suffix="%" if metric.unit=="percent" else ""
    return f"{float(value):,.{metric.digits}f}{suffix}"
