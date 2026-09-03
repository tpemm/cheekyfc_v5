"""Pure descriptive models for Player Role & Tactical research."""
from __future__ import annotations
import pandas as pd


def filter_role_scope(matches: pd.DataFrame, events: pd.DataFrame, *, context="All", start_status="All appearances", role="All Roles", formation="All Formations") -> tuple[pd.DataFrame,pd.DataFrame]:
    selected=matches.copy()
    if context in {"Home","Away"}: selected=selected[selected.get("venue",pd.Series(index=selected.index,dtype=object)).astype(str).str.upper().str[0].eq(context[0])]
    if start_status=="Starts": selected=selected[selected.get("started",False).fillna(False).astype(bool)]
    elif start_status=="Subs": selected=selected[~selected.get("started",False).fillna(False).astype(bool)]
    if role!="All Roles": selected=selected[selected.get("actual_tactical_role",selected.get("tactical_role")).astype(str).eq(role)]
    if formation!="All Formations": selected=selected[selected.get("formation",pd.Series(index=selected.index,dtype=object)).astype(str).eq(formation)]
    ids=set(selected.get("canonical_match_id",pd.Series(dtype=object)).astype(str))
    return selected,events[events.get("canonical_match_id",pd.Series(index=events.index,dtype=object)).astype(str).isin(ids)]


def role_snapshot(matches: pd.DataFrame) -> dict[str, object]:
    roles=matches.get("actual_tactical_role",matches.get("tactical_role",pd.Series(index=matches.index,dtype=object))).dropna().astype(str)
    starts=matches[matches.get("started",pd.Series(False,index=matches.index)).fillna(False).astype(bool)]
    start_roles=starts.get("actual_tactical_role",starts.get("tactical_role",pd.Series(index=starts.index,dtype=object))).dropna().astype(str)
    counts=start_roles.value_counts(); formations=starts.get("formation",pd.Series(index=starts.index,dtype=object)).dropna().astype(str).value_counts()
    return {"appearances":len(matches),"starts":len(starts),"primary_role":counts.index[0] if len(counts) else (roles.mode().iat[0] if len(roles) else pd.NA),"secondary_role":counts.index[1] if len(counts)>1 else pd.NA,"role_share":counts.iloc[0]/counts.sum() if counts.sum() else float("nan"),"role_sample":int(counts.sum()),"primary_formation":formations.index[0] if len(formations) else pd.NA,"formation_share":formations.iloc[0]/formations.sum() if formations.sum() else float("nan"),"minutes_per_start":pd.to_numeric(starts.get("minutes"),errors="coerce").mean()}


def event_activity_by_zone(events: pd.DataFrame) -> dict[str, object]:
    x=pd.to_numeric(events.get("plot_x"),errors="coerce"); y=pd.to_numeric(events.get("plot_y"),errors="coerce"); valid=x.notna()&y.notna(); n=int(valid.sum())
    pct=lambda mask: (100*int((valid&mask).sum())/n) if n else float("nan")
    return {"events":n,"center_x":x[valid].mean(),"center_y":y[valid].mean(),"defensive_third_share":pct(y<100/3),"middle_third_share":pct((y>=100/3)&(y<200/3)),"final_third_share":pct(y>=200/3),"left_share":pct(x<100/3),"center_share":pct((x>=100/3)&(x<200/3)),"right_share":pct(x>=200/3),"box_count":int((valid&(y>=82)&x.between(20,80)).sum()),"box_share":pct((y>=82)&x.between(20,80))}
