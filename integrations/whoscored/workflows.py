"""Offline planning primitives for weekly and historical WhoScored workflows."""
from __future__ import annotations
import json,time
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

TEAM_ALIASES={'Arsenal':'arsenal','Aston Villa':'aston_villa','Bournemouth':'bournemouth','Brentford':'brentford','Brighton':'brighton','Burnley':'burnley','Chelsea':'chelsea','Crystal Palace':'crystal_palace','Everton':'everton','Fulham':'fulham','Leeds':'leeds_united','Leeds United':'leeds_united','Liverpool':'liverpool','Manchester City':'manchester_city','Man City':'manchester_city','Manchester United':'manchester_united','Man Utd':'manchester_united','Newcastle':'newcastle_united','Newcastle United':'newcastle_united','Nottingham Forest':'nottingham_forest','Sunderland':'sunderland','Tottenham':'tottenham_hotspur','West Ham':'west_ham','Wolves':'wolverhampton_wanderers','Wolverhampton Wanderers':'wolverhampton_wanderers'}

def atomic_csv(frame:pd.DataFrame,path:Path)->None:
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp');frame.to_csv(tmp,index=False)
    for attempt in range(20):
        try:tmp.replace(path);return
        except PermissionError:
            if attempt==19:raise
            time.sleep(.25)

def atomic_json(value:dict,path:Path)->None:
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,indent=2,default=str),encoding='utf-8')
    for attempt in range(20):
        try:tmp.replace(path);return
        except PermissionError:
            if attempt==19:raise
            time.sleep(.25)

def cached_whoscored_schedule(root:Path,season:str)->pd.DataFrame:
    rows=[]
    base=root/f'data/raw/whoscored/{season}/poc/_soccerdata_native/matches'
    for path in base.glob('*.json'):
        for tournament in json.loads(path.read_text(encoding='utf-8')).get('tournaments',[]): rows.extend(tournament.get('matches',[]))
    frame=pd.DataFrame(rows).drop_duplicates('id')
    if frame.empty:return frame
    frame['date']=pd.to_datetime(frame.startTimeUtc,utc=True).dt.strftime('%Y-%m-%d');frame['home_club_id']=frame.homeTeamName.map(TEAM_ALIASES);frame['away_club_id']=frame.awayTeamName.map(TEAM_ALIASES)
    return frame

def build_season_manifest(root:Path,season:str)->pd.DataFrame:
    source=root/f'data/seasons/{season}/raw_index/understat_schedule_{season}_ENG-Premier_League.csv'
    schedule=pd.read_csv(source);schedule['date']=pd.to_datetime(schedule.kickoff_datetime,utc=True).dt.strftime('%Y-%m-%d');schedule['home_club_id']=schedule.home_team.map(TEAM_ALIASES);schedule['away_club_id']=schedule.away_team.map(TEAM_ALIASES)
    ws=cached_whoscored_schedule(root,season);out=[]
    for row in schedule.itertuples():
        hit=ws[ws.date.eq(row.date)&ws.home_club_id.eq(row.home_club_id)&ws.away_club_id.eq(row.away_club_id)] if not ws.empty else ws
        out.append({'canonical_match_id':f'understat:{int(row.game_id)}','understat_match_id':int(row.game_id),'whoscored_match_id':int(hit.iloc[0].id) if len(hit)==1 else pd.NA,'date':row.date,'kickoff_datetime':row.kickoff_datetime,'home_club_id':row.home_club_id,'away_club_id':row.away_club_id,'home_team':row.home_team,'away_team':row.away_team,'pl_gameweek':row.gameweek,'fantrax_period':row.gameweek,'is_completed':bool(row.is_result),'resolution_status':'RESOLVED' if len(hit)==1 else 'UNRESOLVED','resolution_method':'cached schedule exact date plus canonical home/away IDs'})
    return pd.DataFrame(out).sort_values(['date','canonical_match_id']).reset_index(drop=True)

def eligible_completed(manifest:pd.DataFrame,now:datetime|None=None)->pd.DataFrame:
    now=now or datetime.now(timezone.utc);kickoff=pd.to_datetime(manifest.kickoff_datetime,utc=True,errors='coerce') if 'kickoff_datetime' in manifest else pd.to_datetime(manifest.date,utc=True,errors='coerce')
    resolved=manifest.whoscored_match_id.notna() if 'whoscored_match_id' in manifest else pd.Series(False,index=manifest.index)
    completed=manifest.is_completed.fillna(False).astype(bool) if 'is_completed' in manifest else pd.Series(False,index=manifest.index)
    return manifest[completed&resolved&kickoff.le(pd.Timestamp(now))].copy()
