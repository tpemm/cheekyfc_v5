#!/usr/bin/env python3
"""Build the eight-match WhoScored historical POC entirely from raw caches."""
from __future__ import annotations
import json,re,sys,unicodedata
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from analytics.advanced_match_poc import normalize_match,normalize_lineups,normalize_events,build_advanced_player_match

TEAM_ALIASES={"Man Utd":"Manchester United","Man City":"Manchester City","Newcastle":"Newcastle United"}
CLUB_CODES={'arsenal':'ARS','aston_villa':'AVL','bournemouth':'BOU','brentford':'BRF','brighton':'BHA','burnley':'BUR','chelsea':'CHE','crystal_palace':'CRY','everton':'EVE','fulham':'FUL','leeds_united':'LEE','liverpool':'LIV','manchester_city':'MCI','manchester_united':'MUN','newcastle_united':'NEW','nottingham_forest':'NOT','sunderland':'SUN','tottenham_hotspur':'TOT','west_ham':'WHU','wolverhampton_wanderers':'WOL'}
REVIEWED_ALIASES={'Alisson Becker':'Alisson','Andy Robertson':'Andrew Robertson','Evann Guessand':'Evann Guessand','Florentino':'Florentino Ibrain Morris Luis','Joe Gomez':'Joseph Gomez','João Gomes':'João Gomes','Kepa Arrizabalaga':'Kepa','Maximilian Kilman':'Max Kilman','Ollie Scarles':'Oliver Scarles','Pape Matar Sarr':'Pape Sarr','Reinildo Mandava':'Reinildo','Savinho':'Savio','Toti Gomes':'Toti','Trey Nyoni':'Treymaurice Nyoni'}
def norm(v): return re.sub(r"[^a-z0-9]","",unicodedata.normalize("NFKD",str(v)).encode("ascii","ignore").decode().casefold())

def build_crosswalk(payloads,manifest):
    season=pd.read_csv(ROOT/'data/seasons/2526/raw_index/understat_players_season_2526_ENG-Premier_League.csv')
    registry=pd.read_csv(ROOT/'data/reference/master_player_crosswalk_identity_only.csv')
    registry['understat_player_id']=pd.to_numeric(registry.understat_player_id,errors='coerce')
    by_us=registry.dropna(subset=['understat_player_id']).drop_duplicates('understat_player_id').set_index('understat_player_id')
    permanent=ROOT/'data/reference/whoscored_player_identity.csv'
    saved=pd.read_csv(permanent) if permanent.exists() else pd.DataFrame()
    saved_by_id={} if saved.empty else {int(r.whoscored_player_id):r for r in saved[saved.mapping_status.eq('PROVEN')].itertuples()}
    roster={}
    for r in season.itertuples(): roster.setdefault((str(r.team),norm(r.player)),[]).append(r)
    rows=[]; seen=set()
    for sample,payload in payloads:
        for side in ('home','away'):
            team=TEAM_ALIASES.get(payload[side]['name'],payload[side]['name'])
            club=sample[f'{side}_club_id']
            for player in payload[side].get('players',[]):
                wsid=int(player['playerId'])
                if wsid in seen: continue
                seen.add(wsid); candidates=roster.get((team,norm(player['name'])),[])
                status='UNRESOLVED'; method='unresolved'; confidence='UNRESOLVED'; reason='no deterministic Fantrax/Understat/registry evidence'; rid=fid=uid=pd.NA
                if wsid in saved_by_id:
                    prior=saved_by_id[wsid];rid=prior.canonical_player_id;fid=prior.fantrax_player_id;uid=prior.understat_player_id
                    status='PROVEN';method='persistent_whoscored_provider_id';confidence='HIGH';reason=pd.NA
                elif len(candidates)==1:
                    uid=int(candidates[0].player_id)
                    if uid in by_us.index:
                        reg=by_us.loc[uid]; rid=reg.registry_player_id; fid=reg.fantrax_player_id
                        status='PROVEN'; method='exact_name_plus_historical_understat_club_then_explicit_registry_id';confidence='HIGH';reason=pd.NA
                if status!='PROVEN':
                    target=REVIEWED_ALIASES.get(player['name'],player['name']); code=CLUB_CODES.get(club)
                    direct=registry[(registry.fantrax_player_name.map(norm).eq(norm(target))) & (registry.fantrax_current_team.eq(code))]
                    # Reviewed aliases may rely on historical Understat club when current club changed.
                    if direct.empty and player['name'] in REVIEWED_ALIASES:
                        direct=registry[registry.fantrax_player_name.map(norm).eq(norm(target))]
                    if len(direct)==1:
                        reg=direct.iloc[0];rid=reg.registry_player_id;fid=reg.fantrax_player_id;uid=reg.understat_player_id
                        status='PROVEN';method='reviewed_alias_plus_club_registry' if player['name'] in REVIEWED_ALIASES else 'exact_fantrax_name_plus_club_registry';confidence='HIGH';reason=pd.NA
                rows.append({'whoscored_player_id':wsid,'whoscored_player_name':player['name'],'registry_player_id':rid,
                  'fantrax_player_id':fid,'understat_player_id':uid,'canonical_club_id':club,'season':'2526',
                  'mapping_method':method,'mapping_status':status,'mapping_confidence':confidence,'unresolved_reason':reason,
                  'provenance':'WhoScored raw plus finalized Understat roster/Fantrax pool plus canonical registry'})
    return pd.DataFrame(rows).sort_values(['mapping_status','whoscored_player_name'],ascending=[True,True])

def main():
    manifest=pd.read_csv(ROOT/'data/reference/advanced_match_poc_sample_2526.csv')
    payloads=[]
    for _,s in manifest.iterrows():
        path=ROOT/f"data/raw/whoscored/2526/poc/match_{int(s.understat_match_id)}/raw_match.json"
        if path.exists(): payloads.append((s,json.loads(path.read_text(encoding='utf-8'))))
    cross=build_crosswalk(payloads,manifest); cross.to_csv(ROOT/'data/reference/whoscored_player_crosswalk_poc_2526.csv',index=False)
    cross.rename(columns={'registry_player_id':'canonical_player_id'}).to_csv(ROOT/'data/reference/whoscored_player_identity.csv',index=False)
    player_map=dict(zip(pd.to_numeric(cross.loc[cross.mapping_status.eq('PROVEN'),'whoscored_player_id']).astype(int),cross.loc[cross.mapping_status.eq('PROVEN'),'registry_player_id']))
    matches=[];lineups=[];events=[]
    for s,payload in payloads:
        meta=json.loads((ROOT/f"data/raw/whoscored/2526/poc/match_{int(s.understat_match_id)}/metadata.json").read_text())
        context={'canonical_match_id':s.canonical_match_id,'whoscored_match_id':int(s.whoscored_match_id),'date':s.date,
          'home_club_id':s.home_club_id,'away_club_id':s.away_club_id,'retrieved_at':meta.get('retrieved_at')}
        matches.append(normalize_match(payload,context)); l=normalize_lineups(payload,context)
        l['canonical_player_id']=pd.to_numeric(l.whoscored_player_id).map(player_map);lineups.append(l)
        events.append(normalize_events(payload,context,player_map))
    match=pd.DataFrame(matches);lineup=pd.concat(lineups,ignore_index=True);event=pd.concat(events,ignore_index=True)
    advanced=build_advanced_player_match(lineup[lineup.canonical_player_id.notna()],event[event.canonical_player_id.notna()])
    advanced=advanced.merge(manifest[['canonical_match_id','understat_match_id','date','fantrax_period']],on='canonical_match_id',how='left')
    advanced=advanced.merge(cross[['registry_player_id','fantrax_player_id','understat_player_id']].dropna(subset=['registry_player_id']).drop_duplicates('registry_player_id'),left_on='canonical_player_id',right_on='registry_player_id',how='left')
    us=pd.read_csv(ROOT/'data/seasons/2526/raw_index/understat_player_match_stats_2526_ENG-Premier_League.csv')
    advanced['understat_player_id']=pd.to_numeric(advanced.understat_player_id,errors='coerce');us['player_id']=pd.to_numeric(us.player_id,errors='coerce')
    advanced=advanced.merge(us[['game_id','player_id','xg','xa','minutes']].rename(columns={'game_id':'understat_match_id','player_id':'understat_player_id','minutes':'understat_minutes'}),on=['understat_match_id','understat_player_id'],how='left')
    advanced['xgi']=advanced.xg+advanced.xa; advanced['understat_alignment']=advanced.xg.notna().map({True:'EXACT_PLAYER_MATCH',False:'UNRESOLVED'})
    master=pd.read_csv(ROOT/'data/seasons/2526/processed/master_player_weekly_2526.csv');master['fantrax_id_clean']=master.fantrax_player_id.astype(str).str.strip('*').str.casefold()
    master['fantrax_period']=pd.to_numeric(master.fantrax_gw,errors='coerce'); advanced['fantrax_id_clean']=advanced.fantrax_player_id.astype(str).str.strip('*').str.casefold()
    fcols=['fantrax_id_clean','fantrax_period','mgr_fantasy_points','avail_fpts','mgr_min','mgr_kp','mgr_tkw','mgr_int','mgr_clr','mgr_cos','mgr_aer','mgr_sot','mgr_ac']
    advanced=advanced.merge(master[fcols].drop_duplicates(['fantrax_id_clean','fantrax_period']),on=['fantrax_id_clean','fantrax_period'],how='left')
    advanced['fantrax_points']=advanced.mgr_fantasy_points.combine_first(advanced.avail_fpts)
    advanced['fantrax_alignment']=advanced.fantrax_points.notna().map({True:'EXACT_SINGLE_CLUB_MATCH_IN_PERIOD',False:'UNRESOLVED'})
    # Sample-only formation and role usage.
    formation_usage=(match.melt(id_vars=['canonical_match_id'],value_vars=['home_club_id','away_club_id'],var_name='side',value_name='club_id'))
    formation_usage['formation']=[match.loc[match.canonical_match_id.eq(mid),'home_formation' if side=='home_club_id' else 'away_formation'].iloc[0] for mid,side in zip(formation_usage.canonical_match_id,formation_usage.side)]
    formation_usage=formation_usage.groupby(['club_id','formation'],as_index=False).agg(formation_count=('canonical_match_id','size'),matches_observed=('canonical_match_id','nunique'))
    formation_usage['formation_share']=formation_usage.formation_count/formation_usage.groupby('club_id').formation_count.transform('sum');formation_usage['scope']='POC_SAMPLE_ONLY'
    roles=lineup[lineup.started & lineup.canonical_player_id.notna() & lineup.actual_position_standardized.notna()].groupby(['canonical_player_id','club_id','actual_position_standardized'],as_index=False).agg(starts_observed=('canonical_match_id','size'),matches_observed=('canonical_match_id','nunique'))
    roles['role_share']=roles.starts_observed/roles.groupby(['canonical_player_id','club_id']).starts_observed.transform('sum');roles['scope']='POC_SAMPLE_ONLY'
    out=ROOT/'data/models/season_2526';out.mkdir(parents=True,exist_ok=True)
    for name,df in [('whoscored_match_poc_2526',match),('whoscored_lineup_poc_2526',lineup),('whoscored_event_poc_2526',event),('advanced_player_match_poc_2526',advanced),('team_formation_usage_poc_2526',formation_usage),('player_role_usage_poc_2526',roles)]: df.to_csv(out/f'{name}.csv',index=False)
    print(json.dumps({'matches':len(match),'lineups':len(lineup),'events':len(event),'unique_players':int(lineup.whoscored_player_id.nunique()),'mapped_players':int(cross.mapping_status.eq('PROVEN').sum()),'advanced_rows':len(advanced),'understat_exact':int(advanced.xg.notna().sum()),'fantrax_exact':int(advanced.fantrax_points.notna().sum())}))
if __name__=='__main__':main()
