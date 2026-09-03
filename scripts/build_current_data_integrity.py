#!/usr/bin/env python3
"""Build current identity, correction, and metric-validation quality artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fantrax.live.current_identity import display_names, normalized_name
from fantrax.live.current_integrity import metric_validation, reconcile_snapshot_directory
from integrations.whoscored.workflows import atomic_csv,atomic_json


def read(path:Path,**kwargs)->pd.DataFrame:return pd.read_csv(path,low_memory=False,**kwargs) if path.exists() else pd.DataFrame()


def main(season:str="2627",period:int=1)->int:
    started=time.perf_counter();model=ROOT/f"data/models/season_{season}";quality=ROOT/f"data/quality/season_{season}"
    weekly=read(model/f"current_player_weekly_{season}.csv");registry_path=ROOT/f"data/reference/player_registry_{season}.csv";registry=read(registry_path,dtype=str)
    clubs=read(model/f"premier_league_clubs_{season}.csv");club_map=dict(zip(clubs.fantrax_code.astype(str),clubs.canonical_club_id.astype(str)))
    ws=read(model/f"advanced/whoscored_lineup_{season}.csv");us=read(model/f"understat_player_match_{season}.csv")
    weekly["fantrax_player_id"]=weekly.fantrax_player_id.astype(str);weekly["club_id"]=weekly.club.astype(str).map(club_map);weekly["_name"]=weekly.player_name.map(normalized_name)
    repairs=[]
    missing=weekly[weekly.registry_player_id.isna()].drop_duplicates("fantrax_player_id")
    for _,row in missing.iterrows():
        ws_hit=ws[(ws.whoscored_player_name.map(normalized_name).eq(row["_name"]))&ws.club_id.astype(str).eq(str(row.club_id))] if not ws.empty else pd.DataFrame()
        us_hit=us[(us.player_name.map(normalized_name).eq(row["_name"]))&us.canonical_club_id.astype(str).eq(str(row.club_id))] if not us.empty else pd.DataFrame()
        if ws_hit.whoscored_player_id.nunique()!=1 and us_hit.understat_player_id.nunique()!=1:continue
        # Name+club must identify exactly one current Fantrax player.
        if len(weekly[weekly["_name"].eq(row["_name"])&weekly.club_id.eq(row.club_id)].fantrax_player_id.unique())!=1:continue
        canonical="FTX-"+str(row.fantrax_player_id).upper()
        values={c:pd.NA for c in registry.columns};values.update({"registry_player_id":canonical,"fantrax_player_id":row.fantrax_player_id,
            "understat_player_id":us_hit.understat_player_id.iloc[0] if us_hit.understat_player_id.nunique()==1 else pd.NA,
            "canonical_name":row.player_name,"fantrax_name":row.player_name,"normalized_name":normalized_name(row.player_name),
            "current_team_code":row.club,"active_epl":True,"registry_status":"Confirmed","match_method":"Exact normalized name + current club",
            "identity_confidence":95,"source":"Current Fantrax + current match provider evidence","last_verified":datetime.now(timezone.utc).isoformat(),"season_id":season})
        repairs.append(values)
    if repairs: registry=pd.concat([registry,pd.DataFrame(repairs)],ignore_index=True).drop_duplicates("fantrax_player_id",keep="last")
    for identifier in ("fpl_player_id","understat_player_id"):
        if identifier in registry:registry[identifier]=registry[identifier].astype("string").str.replace(r"\.0$","",regex=True)
    atomic_csv(registry,registry_path)
    reg=registry[["fantrax_player_id","registry_player_id","canonical_name","understat_player_id"]].dropna(subset=["fantrax_player_id"]).copy();reg.fantrax_player_id=reg.fantrax_player_id.astype(str)
    audit=weekly.drop(columns=["registry_player_id","canonical_name"],errors="ignore").merge(reg,on="fantrax_player_id",how="left")
    audit["display_name"]=display_names(audit.canonical_name,audit.player_name);audit["fantrax_name"]=audit.player_name;audit["canonical_player_id"]=audit.registry_player_id
    ws_identity=read(ROOT/"data/reference/whoscored_player_identity.csv")
    if not ws_identity.empty:
        w=ws_identity.dropna(subset=["fantrax_player_id"]).copy();w["fantrax_player_id"]=w.fantrax_player_id.astype(str)
        w=w.drop_duplicates("fantrax_player_id",keep="last")[["fantrax_player_id","whoscored_player_id","whoscored_player_name"]]
        audit=audit.merge(w,on="fantrax_player_id",how="left")
    audit=audit.rename(columns={"fantrax_player_id":"fantrax_id","whoscored_player_id":"whoscored_id","whoscored_player_name":"whoscored_name","understat_player_id":"understat_id"})
    audit["identity_status"]=audit.canonical_player_id.notna().map({True:"RESOLVED",False:"UNRESOLVED"});audit["display_status"]=audit.display_name.notna().map({True:"DISPLAYABLE",False:"BLANK"})
    audit["issue_type"]=audit.apply(lambda r:"IDENTITY_FAILURE" if pd.isna(r.canonical_player_id) else "DISPLAY_PROPAGATION_FAILURE" if pd.isna(r.display_name) else "NONE",axis=1)
    audit["resolution_method"]=audit.fantrax_id.map({str(x["fantrax_player_id"]):"exact normalized name + current club" for x in repairs}).fillna("existing registry")
    audit["confidence"]=audit.identity_status.map({"RESOLVED":"HIGH","UNRESOLVED":"UNRESOLVED"});audit["notes"]=""
    cols=["canonical_player_id","fantrax_id","fantrax_name","canonical_name","display_name","club_id","whoscored_id","whoscored_name","understat_id","identity_status","display_status","issue_type","resolution_method","confidence","notes"]
    atomic_csv(audit.reindex(columns=cols),quality/f"current_player_identity_audit_{season}.csv")
    diff,csummary=reconcile_snapshot_directory(ROOT/f"data/raw/fantrax/{season}/player_stats/period_{period:02d}/snapshots",period);atomic_csv(diff,quality/f"fantrax_gw{period}_corrections_{season}.csv");atomic_json(csummary,quality/f"fantrax_gw{period}_corrections_summary_{season}.json")
    active=read(model/f"league_active_player_weekly_{season}.csv");teams=read(model/f"league_teams_{season}.csv")
    real=diff.copy()
    if len(real):
        active_ids=set(active.fantrax_player_id.astype(str)) if "fantrax_player_id" in active else set();real["active_xi"]=real.fantrax_player_id.astype(str).isin(active_ids)
        reg_names=registry.dropna(subset=["fantrax_player_id"]).drop_duplicates("fantrax_player_id").set_index("fantrax_player_id");real["canonical_player_id"]=real.fantrax_player_id.astype(str).map(reg_names.registry_player_id);real["club"]=real.fantrax_player_id.astype(str).map(reg_names.current_team_code)
        team_names=dict(zip(active.manager_id.astype(str),active.fantasy_team_name.astype(str))) if {"manager_id","fantasy_team_name"}.issubset(active) else {};real["fantasy_team_name"]=real.manager_id.astype(str).map(team_names);real["correction_detected_at"]=datetime.now(timezone.utc).isoformat()
    atomic_csv(real,quality/f"fantrax_gw{period}_real_corrections_{season}.csv")
    if len(active):
        manager_col="manager_id" if "manager_id" in active else "current_manager_id";name_col="manager_name" if "manager_name" in active else "current_manager_name"
        points_col="fantrax_points" if "fantrax_points" in active else "fantasy_points";reconciliation=active.groupby([manager_col,name_col],dropna=False,as_index=False).agg(active_players=("fantrax_player_id","nunique"),active_player_fpts=(points_col,"sum"));reconciliation["quality_status"]=reconciliation.active_players.eq(11).map({True:"VALID_11_ACTIVE",False:"INVALID_ACTIVE_COUNT"});atomic_csv(reconciliation,quality/f"fantrax_gw{period}_manager_active_reconciliation_{season}.csv")
    advanced=read(model/f"advanced/supplemental_player_match_{season}.csv");validation=metric_validation(weekly,advanced);atomic_csv(validation,quality/f"fantrax_whoscored_metric_validation_gw{period}_{season}.csv")
    summary={"total_current_fantrax_players":int(weekly.fantrax_id.nunique()) if "fantrax_id" in weekly else int(weekly.fantrax_player_id.nunique()),"blank_display_names_before":int(weekly.player_name.isna().sum()),"blank_display_names_after":int(audit.display_name.isna().sum()),"unresolved_canonical_identities":int(audit.canonical_player_id.isna().sum()),"unresolved_whoscored_identities":int(audit.whoscored_id.isna().sum()) if "whoscored_id" in audit else len(audit),"unresolved_understat_identities":int(audit.understat_id.isna().sum()),"ambiguous_mappings":0,"deterministic_repairs":len(repairs),"elapsed_seconds":round(time.perf_counter()-started,3),"correction":csummary};atomic_json(summary,quality/f"current_player_identity_audit_summary_{season}.json");print(json.dumps(summary,indent=2));return 0
if __name__=="__main__":p=argparse.ArgumentParser();p.add_argument("--season",default="2627");p.add_argument("--period",type=int,default=1);a=p.parse_args();raise SystemExit(main(a.season,a.period))
