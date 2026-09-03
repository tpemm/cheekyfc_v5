"""Stable-ID manager display-name history and current-label resolution."""
from __future__ import annotations
import pandas as pd

COLUMNS=("season_id","manager_id","display_name","valid_from_period","valid_to_period","first_seen_at","last_seen_at","is_current")

def update_manager_name_history(existing:pd.DataFrame,current:pd.DataFrame,*,period:int,observed_at:str)->pd.DataFrame:
    history=existing.reindex(columns=COLUMNS).copy() if not existing.empty else pd.DataFrame(columns=COLUMNS)
    for row in current.drop_duplicates("manager_id").to_dict("records"):
        mid=str(row["manager_id"]);name=str(row.get("fantasy_team_name") or row.get("manager_name"));mask=history.manager_id.astype(str).eq(mid)&history.is_current.fillna(False).astype(bool)
        if mask.any() and history.loc[mask,"display_name"].astype(str).eq(name).all():history.loc[mask,"last_seen_at"]=observed_at;continue
        history.loc[mask,"is_current"]=False;history.loc[mask,"valid_to_period"]=period-1;history.loc[mask,"last_seen_at"]=observed_at
        history.loc[len(history)]={"season_id":row.get("season_id"),"manager_id":mid,"display_name":name,"valid_from_period":period,"valid_to_period":pd.NA,"first_seen_at":observed_at,"last_seen_at":observed_at,"is_current":True}
    return history.reindex(columns=COLUMNS).sort_values(["manager_id","valid_from_period"],kind="stable").reset_index(drop=True)

def current_manager_names(teams:pd.DataFrame)->dict[str,str]:
    if teams.empty:return {}
    return {str(row.manager_id):str(row.fantasy_team_name or row.manager_name) for row in teams.itertuples()}

def resolve_current_manager_names(frame:pd.DataFrame,teams:pd.DataFrame)->pd.DataFrame:
    """Resolve presentation labels by stable IDs without changing identity/history."""
    out=frame.copy();names=current_manager_names(teams)
    for id_col,name_cols in (("manager_id",("manager_name","manager","fantasy_team_name")),("opponent_manager_id",("opponent_manager_name","opponent"))):
        if id_col not in out:continue
        resolved=out[id_col].astype(str).map(names)
        for name_col in name_cols:
            if name_col in out:out[name_col]=resolved.fillna(out[name_col])
    return out
