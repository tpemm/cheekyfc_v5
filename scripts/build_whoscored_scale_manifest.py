#!/usr/bin/env python3
"""Resolve the bounded GW36-38 scale sample from cached schedules only."""
from __future__ import annotations
import json,re
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
CLUBS={'Arsenal':'arsenal','Aston Villa':'aston_villa','Bournemouth':'bournemouth','Brentford':'brentford','Brighton':'brighton','Burnley':'burnley','Chelsea':'chelsea','Crystal Palace':'crystal_palace','Everton':'everton','Fulham':'fulham','Leeds':'leeds_united','Leeds United':'leeds_united','Liverpool':'liverpool','Manchester City':'manchester_city','Man City':'manchester_city','Manchester United':'manchester_united','Man Utd':'manchester_united','Newcastle':'newcastle_united','Newcastle United':'newcastle_united','Nottingham Forest':'nottingham_forest','Sunderland':'sunderland','Tottenham':'tottenham_hotspur','West Ham':'west_ham','Wolves':'wolverhampton_wanderers','Wolverhampton Wanderers':'wolverhampton_wanderers'}
def main():
    rows=[]
    for f in (ROOT/'data/raw/whoscored/2526/poc/_soccerdata_native/matches').glob('*.json'):
        for t in json.loads(f.read_text(encoding='utf-8')).get('tournaments',[]): rows.extend(t.get('matches',[]))
    ws=pd.DataFrame(rows).drop_duplicates('id');ws['date']=pd.to_datetime(ws.startTimeUtc).dt.strftime('%Y-%m-%d');ws['home_club_id']=ws.homeTeamName.map(CLUBS);ws['away_club_id']=ws.awayTeamName.map(CLUBS)
    us=pd.read_csv(ROOT/'data/seasons/2526/raw_index/understat_schedule_2526_ENG-Premier_League.csv');us=us[us.gameweek.between(36,38)].copy();us['date']=pd.to_datetime(us.kickoff_datetime).dt.strftime('%Y-%m-%d');us['home_club_id']=us.home_team.map(CLUBS);us['away_club_id']=us.away_team.map(CLUBS)
    out=[]
    for r in us.itertuples():
        hit=ws[ws.date.eq(r.date)&ws.home_club_id.eq(r.home_club_id)&ws.away_club_id.eq(r.away_club_id)]
        out.append({'canonical_match_id':f'understat:{r.game_id}','understat_match_id':r.game_id,'whoscored_match_id':hit.iloc[0].id if len(hit)==1 else pd.NA,'date':r.date,'home_club_id':r.home_club_id,'away_club_id':r.away_club_id,'home_team':r.home_team,'away_team':r.away_team,'pl_gameweek':r.gameweek,'fantrax_period':r.gameweek,'resolution_status':'RESOLVED' if len(hit)==1 else 'UNRESOLVED','resolution_method':'cached schedule exact date plus canonical home/away IDs','scale_sample':'GW36-38'})
    frame=pd.DataFrame(out).sort_values(['date','whoscored_match_id']);frame.to_csv(ROOT/'data/reference/whoscored_scale_sample_2526.csv',index=False)
    print(json.dumps({'matches':len(frame),'resolved':int(frame.resolution_status.eq('RESOLVED').sum()),'clubs':len(set(frame.home_club_id)|set(frame.away_club_id))}))
if __name__=='__main__':main()
