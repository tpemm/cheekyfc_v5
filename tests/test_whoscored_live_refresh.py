import hashlib,json
from pathlib import Path
import pandas as pd

from integrations.whoscored.controller import validate_cache
from integrations.whoscored.live_refresh import acquisition_plan,build_live_manifest,cached_provider_schedule,canonical_2627_fixtures,exact_provider_resolution,fixture_eligibility,maturity_after_recheck


def fixtures():
    return pd.DataFrame({"match_id":["m1","m1","m2","m2"],"kickoff_time":["2026-08-21T19:00:00Z"]*2+["2026-08-25T19:00:00Z"]*2,"status":["scheduled"]*4,"completed":[False]*4,"club_id":["a","b","c","d"],"opponent_id":["b","a","d","c"],"home_away":["H","A","H","A"]})


def test_canonical_fixture_collapse_and_post_match_eligibility():
    frame=canonical_2627_fixtures(fixtures());assert len(frame)==2 and frame.iloc[0].home_club_id=="a"
    row=frame.iloc[0].rename({"kickoff":"kickoff"})
    assert fixture_eligibility(row,now="2026-08-21T21:00:00Z")=="IN_PROGRESS_OR_TOO_RECENT"
    assert fixture_eligibility(row,now="2026-08-21T22:31:00Z")=="ELIGIBLE_MISSING"
    assert fixture_eligibility(frame.iloc[1],now="2026-08-21T22:31:00Z")=="FUTURE"


def test_provider_resolution_requires_one_exact_fixture():
    frame=canonical_2627_fixtures(fixtures());provider=pd.DataFrame({"kickoff":["2026-08-21T19:00:00Z"],"home_club_id":["a"],"away_club_id":["b"],"whoscored_match_id":[99]})
    out=exact_provider_resolution(frame,provider);assert out.iloc[0].whoscored_match_id==99 and out.iloc[1].resolution_status=="UNRESOLVED"
    duplicate=pd.concat([provider,provider]);assert exact_provider_resolution(frame,duplicate).iloc[0].resolution_status=="AMBIGUOUS_REJECTED"


def test_incremental_plan_skips_stable_and_rechecks_preliminary():
    existing=pd.DataFrame({"canonical_match_id":["m1"],"whoscored_match_id":[99],"cache_status":["PRELIMINARY"],"acquisition_status":["ACQUIRED"]})
    manifest=build_live_manifest(fixtures(),existing=existing,now="2026-08-24T12:00:00Z")
    plan=acquisition_plan(manifest);assert plan["preliminary"]==1 and plan["would_recheck"]==1
    manifest.loc[manifest.canonical_match_id.eq("m1"),"cache_status"]="STABLE";manifest["planner_status"]=manifest.apply(lambda r:fixture_eligibility(r,now="2026-08-24T12:00:00Z"),axis=1)
    assert acquisition_plan(manifest)["would_recheck"]==0


def test_changed_preliminary_stays_preliminary_and_unchanged_can_stabilize():
    previous=pd.Series({"last_checked_at":"2026-08-23T00:00:00Z","payload_hash":"a","event_count":10,"lineup_count":22,"ratings_count":22})
    same={"payload_hash":"a","event_count":10,"lineup_count":22,"ratings_count":22}
    assert maturity_after_recheck(previous,same,checked_at="2026-08-24T00:00:00Z")=="STABLE"
    assert maturity_after_recheck(previous,{**same,"event_count":11},checked_at="2026-08-24T00:00:00Z")=="PRELIMINARY"


def test_cached_schedule_parses_promoted_clubs_without_browser():
    root=Path('.test_artifacts/whoscored_cached_schedule');folder=root/'matches';folder.mkdir(parents=True,exist_ok=True)
    payload={'tournaments':[{'matches':[{'id':7,'startTimeUtc':'2026-08-21T19:00:00Z','homeTeamName':'Coventry','awayTeamName':'Hull'}]}]}
    (folder/'ENG-Premier League_2627_25544_7.json').write_text(json.dumps(payload),encoding='utf-8')
    result=cached_provider_schedule(root)
    assert result.iloc[0][['home_club_id','away_club_id']].tolist()==['coventry_city','hull_city']


def test_rescheduled_fixture_uses_unique_exact_pair_and_rejects_ambiguity():
    frame=canonical_2627_fixtures(fixtures()).iloc[[0]];provider=pd.DataFrame({'kickoff':['2026-08-22T19:00:00Z'],'home_club_id':['a'],'away_club_id':['b'],'whoscored_match_id':[99]})
    result=exact_provider_resolution(frame,provider).iloc[0]
    assert result.resolution_status=='RESOLVED_EXACT_PAIR' and result.whoscored_match_id==99
    duplicate=pd.concat([provider,provider.assign(whoscored_match_id=100)])
    assert exact_provider_resolution(frame,duplicate).iloc[0].resolution_status=='AMBIGUOUS_REJECTED'


def test_current_cache_is_provider_keyed_and_validated():
    tmp_path=Path('.test_artifacts/whoscored_current_cache');tmp_path.mkdir(parents=True,exist_ok=True)
    payload={'home':{'name':'Coventry'},'away':{'name':'Hull'},'startDate':'2026-08-21T00:00:00','events':[{'id':1}]};raw=json.dumps(payload).encode();target=tmp_path/'match_7';target.mkdir(exist_ok=True);(target/'raw_match.json').write_bytes(raw)
    digest=hashlib.sha256(raw).hexdigest();(target/'metadata.json').write_text(json.dumps({'whoscored_match_id':7,'checksum':digest}),encoding='utf-8')
    result=validate_cache(tmp_path,{'whoscored_match_id':7,'date':'2026-08-21','home_club_id':'coventry_city','away_club_id':'hull_city'})
    assert result['cache_valid'] is True and result['event_count']==1
