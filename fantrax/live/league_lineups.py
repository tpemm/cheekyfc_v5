"""League-specific active-lineup facts and legal-XI analytics."""
from __future__ import annotations

from pathlib import Path
import json
import pandas as pd


ACTIVE_STATUSES=frozenset({"ACTIVE","ACT","STARTER","STARTING"})
POSITION_LIMITS={"G":(1,1),"D":(3,5),"M":(2,5),"F":(1,3)}


def completed_whoscored_periods(raw_root:Path,periods:pd.DataFrame,manifest_path:Path)->set[int]:
    """Periods whose complete fixture slate has terminal cached match payloads."""
    if periods.empty or not manifest_path.exists():return set()
    manifest=pd.read_csv(manifest_path)
    manifest=manifest[manifest.get("acquisition_status",pd.Series(index=manifest.index,dtype=object)).eq("ACQUIRED")].copy()
    manifest["kickoff"]=pd.to_datetime(manifest.get("kickoff"),errors="coerce",utc=True)
    terminal=[]
    for row in manifest.itertuples():
        match_id=pd.to_numeric(getattr(row,"whoscored_match_id",None),errors="coerce")
        path=raw_root/f"match_{int(match_id)}"/"raw_match.json" if pd.notna(match_id) else Path()
        if not path.is_file():continue
        try:payload=json.loads(path.read_text(encoding="utf-8"))
        except (OSError,json.JSONDecodeError):continue
        if pd.to_numeric(payload.get("statusCode"),errors="coerce")==6:terminal.append(row)
    terminal=pd.DataFrame(terminal)
    complete=set()
    for period in periods.itertuples():
        number=int(getattr(period,"period",None) if getattr(period,"period",None) is not None else getattr(period,"fantrax_gw"))
        start=pd.to_datetime(getattr(period,"period_start",None) if getattr(period,"period_start",None) is not None else getattr(period,"start_datetime",None),errors="coerce",utc=True)
        end=pd.to_datetime(getattr(period,"period_end",None) if getattr(period,"period_end",None) is not None else getattr(period,"end_datetime",None),errors="coerce",utc=True)
        scheduled=manifest[manifest.kickoff.between(start,end,inclusive="both")]
        finished=terminal[terminal.kickoff.between(start,end,inclusive="both")] if not terminal.empty else terminal
        if len(scheduled)==10 and len(finished)==len(scheduled):complete.add(number)
    return complete


def active_player_weekly(weekly:pd.DataFrame,completed_periods:set[int])->pd.DataFrame:
    """One historically attributed row per active fantasy starter and period."""
    if weekly.empty:return pd.DataFrame()
    out=weekly[weekly.get("lineup_status",pd.Series(index=weekly.index,dtype=object)).astype(str).str.upper().isin(ACTIVE_STATUSES)].copy()
    out=out[out.get("current_manager_id",pd.Series(index=out.index,dtype=object)).notna()]
    out["active_start"]=True;out["position_started"]=out.get("fantrax_position")
    out["period_complete"]=pd.to_numeric(out.get("period"),errors="coerce").isin(completed_periods)
    out["manager_id"]=out.get("current_manager_id");out["manager_name"]=out.get("current_manager_name")
    out["fantasy_team_id"]=out.get("current_manager_id");out["fantasy_team_name"]=out.get("current_manager_name")
    columns=("season_id","period","manager_id","manager_name","fantasy_team_id","fantasy_team_name","registry_player_id","fantrax_player_id","player_name","active_start","position_started","fantrax_points","goals","assists","clean_sheets","ghost_points","period_complete")
    out["fantrax_points"]=pd.to_numeric(out.get("fantasy_points"),errors="coerce")
    return out.reindex(columns=columns).sort_values(["period","manager_id","fantrax_player_id"],kind="stable").reset_index(drop=True)


def _eligible(value:object)->tuple[str,...]:
    text=str(value).upper().replace("GK","G").replace("DEF","D").replace("MID","M").replace("FWD","F")
    return tuple(position for position in POSITION_LIMITS if position in {part.strip() for part in text.replace("/",",").split(",")})


def optimal_legal_xi(roster:pd.DataFrame)->tuple[float,tuple[str,...]]:
    """Dynamic-programming maximum under G1, D3-5, M2-5, F1-3 rules."""
    states={(0,0,0,0):(0.0,())}
    ordered=roster.assign(_score=pd.to_numeric(roster.get("fantasy_points"),errors="coerce").fillna(0),_id=roster.get("fantrax_player_id").astype(str)).sort_values("_id")
    for _,row in ordered.iterrows():
        updated=dict(states)
        for counts,(score,ids) in states.items():
            for position in _eligible(row.get("fantrax_position")):
                index=("G","D","M","F").index(position);new=list(counts);new[index]+=1;new=tuple(new)
                if new[index]>POSITION_LIMITS[position][1] or sum(new)>11:continue
                candidate=(score+float(row["_score"]),ids+(str(row["_id"]),))
                if new not in updated or candidate[0]>updated[new][0] or (candidate[0]==updated[new][0] and candidate[1]<updated[new][1]):updated[new]=candidate
        states=updated
    legal=[value for counts,value in states.items() if sum(counts)==11 and all(POSITION_LIMITS[p][0]<=counts[i]<=POSITION_LIMITS[p][1] for i,p in enumerate(("G","D","M","F")))]
    return max(legal,key=lambda value:(value[0],tuple(reversed(value[1])))) if legal else (float("nan"),())


def enrich_manager_weeks(weeks:pd.DataFrame,weekly:pd.DataFrame,completed_periods:set[int])->pd.DataFrame:
    out=weeks.copy()
    ordered_periods=sorted(completed_periods)
    active_sets={}
    for period in ordered_periods:
        players=weekly[pd.to_numeric(weekly.get("period"),errors="coerce").eq(period)]
        for manager_id,roster in players[players.get("current_manager_id",pd.Series(index=players.index,dtype=object)).notna()].groupby("current_manager_id"):
            active=roster[roster.get("lineup_status",pd.Series(index=roster.index,dtype=object)).astype(str).str.upper().isin(ACTIVE_STATUSES)]
            active_sets[(period,str(manager_id))]=set(active.get("fantrax_player_id",pd.Series(dtype=object)).astype(str))
            actual=pd.to_numeric(active.get("fantasy_points"),errors="coerce").sum(min_count=1);ghost=pd.to_numeric(active.get("ghost_points"),errors="coerce").sum(min_count=1)
            optimal,_=optimal_legal_xi(roster);mask=pd.to_numeric(out.get("period"),errors="coerce").eq(period)&out.get("manager_id",pd.Series(index=out.index,dtype=object)).astype(str).eq(str(manager_id))
            out.loc[mask,["starter_points","ghost_points","active_players","bench_players"]]=[actual,ghost,len(active),len(roster)-len(active)]
            out.loc[mask,["optimal_xi_points","optimal_xi_score","points_missed","lineup_efficiency_pct"]]=[optimal,optimal,max(optimal-actual,0),100*actual/optimal if pd.notna(optimal) and optimal else pd.NA]
            if period==min(completed_periods):out.loc[mask,"lineup_changes"]=pd.NA
            else:
                previous=max(candidate for candidate in ordered_periods if candidate<period)
                prior=active_sets.get((previous,str(manager_id)),set())
                out.loc[mask,"lineup_changes"]=len(active_sets[(period,str(manager_id))]-prior)
    return out
