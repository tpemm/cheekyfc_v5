"""Pure, deterministic Cup bracket construction from league seeds and weekly scores."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
import pandas as pd

ROUNDS=("Opening Round","Quarterfinals","Semifinals","Championship")
WEEK_FIELDS={"Opening Round":"opening_round_week","Quarterfinals":"quarterfinal_week","Semifinals":"semifinal_week","Championship":"championship_week"}

def validate_configuration(config:dict[str,Any])->None:
    required=("season","tournament_name","teams","byes","seeding_week",*WEEK_FIELDS.values(),"reseed_after_round","score_source","tie_break_method")
    missing=[key for key in required if key not in config or pd.isna(config[key])]
    if missing: raise ValueError(f"Cup configuration is missing: {', '.join(missing)}")
    teams=int(config["teams"]); byes=int(config["byes"])
    if teams<4 or byes<0 or byes>=teams: raise ValueError("Cup teams/byes are invalid")
    weeks=[int(config["seeding_week"]),*(int(config[key]) for key in WEEK_FIELDS.values())]
    if weeks!=sorted(weeks) or len(set(weeks))!=len(weeks): raise ValueError("Cup weeks must be unique and chronological")

def create_seed_snapshot(standings:pd.DataFrame,config:dict[str,Any],*,timestamp:str|None=None)->pd.DataFrame:
    validate_configuration(config); count=int(config["teams"]); frame=standings.copy()
    period=pd.to_numeric(frame.get("period"),errors="coerce")
    if period.notna().any(): frame=frame[period.eq(int(config["seeding_week"]))]
    rank=pd.to_numeric(frame.get("rank"),errors="coerce"); frame=frame.assign(_rank=rank).sort_values(["_rank","manager_id"],kind="stable").head(count)
    if len(frame)<count or frame["_rank"].isna().any(): raise ValueError(f"Seeding requires {count} complete standings rows from GW{int(config['seeding_week'])}")
    created=timestamp or datetime.now(timezone.utc).isoformat()
    return pd.DataFrame({"season":str(config["season"]),"manager_id":frame["manager_id"].astype(str),"manager":frame.get("manager_name",frame.get("manager",frame["manager_id"])).astype(str),"seed":frame["_rank"].astype(int),"league_rank":frame["_rank"].astype(int),"league_points":pd.to_numeric(frame.get("points"),errors="coerce"),"points_scored":pd.to_numeric(frame.get("fantasy_points_for",frame.get("points_for")),errors="coerce"),"snapshot_week":int(config["seeding_week"]),"snapshot_timestamp":created})

def matchup_state(week:int,current_week:int|None,score_count:int)->str:
    if score_count==2 and current_week is not None and current_week>=week: return "Final"
    if current_week is not None and current_week==week: return "Live"
    return "Waiting for week" if current_week is not None and current_week<week else "Upcoming"

def build_tournament(config:dict[str,Any],seeds:pd.DataFrame,scores:pd.DataFrame|None=None,*,current_week:int|None=None)->pd.DataFrame:
    validate_configuration(config)
    if seeds.empty: return _empty_matchups()
    seed_rows={int(row.seed):row for row in seeds.sort_values("seed").itertuples()}; scores=scores if scores is not None else pd.DataFrame()
    all_rows=[]; opening_seeds=list(range(int(config["byes"])+1,int(config["teams"])+1)); participants=[]
    for left,right in _pair_outer(opening_seeds): participants.append((seed_rows[left],seed_rows[right]))
    previous=[]
    for round_index,round_name in enumerate(ROUNDS):
        week=int(config[WEEK_FIELDS[round_name]])
        if round_index>0:
            survivors=[seed_rows[i] for i in range(1,int(config["byes"])+1)] if round_index==1 else []
            winners=[_winner_row(row,seed_rows) for row in previous if row["status"]=="Final" and pd.notna(row["winner_seed"])]
            survivors.extend(winners)
            needed={"Quarterfinals":8,"Semifinals":4,"Championship":2}[round_name]
            if len(survivors)<needed: break
            survivors=sorted(survivors,key=lambda row:int(row.seed)); participants=_pair_outer(survivors)
        current=[]
        for index,(home,away) in enumerate(participants,1):
            row=_matchup(round_name,index,week,home,away,scores,current_week,config)
            current.append(row); all_rows.append(row)
        if previous:
            for index,row in enumerate(previous): row["next_matchup_id"]=current[index//2]["matchup_id"] if index//2<len(current) else ""
        previous=current
    return pd.DataFrame(all_rows,columns=_empty_matchups().columns)

def _pair_outer(items):
    values=list(items); return [(values[i],values[-1-i]) for i in range(len(values)//2)]

def _score(scores,manager_id,week):
    if scores.empty: return None
    manager_col=next((c for c in ("manager_id","fantasy_team_id","manager") if c in scores),None); week_col=next((c for c in ("period","gameweek","week","fantrax_gw") if c in scores),None); value_col=next((c for c in ("total_score","official_fantasy_score","starter_fantasy_points","fantasy_points") if c in scores),None)
    if not all((manager_col,week_col,value_col)): return None
    match=scores[scores[manager_col].astype(str).eq(str(manager_id)) & pd.to_numeric(scores[week_col],errors="coerce").eq(week)]
    value=pd.to_numeric(match[value_col],errors="coerce").dropna(); return None if value.empty else float(value.iloc[-1])

def _matchup(round_name,index,week,home,away,scores,current_week,config):
    hs=_score(scores,home.manager_id,week); aws=_score(scores,away.manager_id,week); state=matchup_state(week,current_week,int(hs is not None)+int(aws is not None)); winner_seed=pd.NA
    if state=="Final":
        if hs>aws: winner_seed=int(home.seed)
        elif aws>hs: winner_seed=int(away.seed)
        else: winner_seed=min(int(home.seed),int(away.seed))
    winner_id="" if pd.isna(winner_seed) else str(home.manager_id if winner_seed==int(home.seed) else away.manager_id)
    return {"matchup_id":f"{round_name.lower().replace(' ','_')}_{index}","round":round_name,"week":week,"home_seed":int(home.seed),"home_manager_id":str(home.manager_id),"home_manager":str(home.manager),"home_score":hs,"away_seed":int(away.seed),"away_manager_id":str(away.manager_id),"away_manager":str(away.manager),"away_score":aws,"winner_seed":winner_seed,"winner_manager_id":winner_id,"status":state,"winner_path":"Champion" if round_name=="Championship" and winner_id else "Advances" if winner_id else "","next_matchup_id":"","tie_break_method":str(config["tie_break_method"])}

def _winner_row(matchup,seed_rows): return seed_rows[int(matchup["winner_seed"])]
def _empty_matchups(): return pd.DataFrame(columns=("matchup_id","round","week","home_seed","home_manager_id","home_manager","home_score","away_seed","away_manager_id","away_manager","away_score","winner_seed","winner_manager_id","status","winner_path","next_matchup_id","tie_break_method"))

def tournament_schedule(config):
    validate_configuration(config)
    return pd.DataFrame([{"stage":"Seeding Lock","week":int(config["seeding_week"])},*({"stage":name,"week":int(config[field])} for name,field in WEEK_FIELDS.items())])
