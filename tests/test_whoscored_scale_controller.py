import hashlib,json,shutil,uuid
from pathlib import Path
import pandas as pd
import pytest
from integrations.whoscored.controller import acquire,validate_cache

ROOT=Path(__file__).resolve().parents[1]
@pytest.fixture
def project_path():
    path=ROOT/'.test_artifacts'/f'ws_controller_{uuid.uuid4().hex}';path.mkdir(parents=True)
    try:yield path
    finally:shutil.rmtree(path,ignore_errors=True)

def rows():
    return pd.DataFrame([{'canonical_match_id':'understat:1','understat_match_id':1,'whoscored_match_id':101,'date':'2026-01-01','home_club_id':'arsenal','away_club_id':'chelsea'}, {'canonical_match_id':'understat:2','understat_match_id':2,'whoscored_match_id':102,'date':'2026-01-02','home_club_id':'liverpool','away_club_id':'everton'}])

def valid(root,canonical,provider):
    target=root/f'data/raw/whoscored/2526/poc/match_{canonical}';target.mkdir(parents=True,exist_ok=True)
    home,away,date=('Arsenal','Chelsea','2026-01-01') if canonical==1 else ('Liverpool','Everton','2026-01-02')
    payload={'home':{'teamId':1,'name':home},'away':{'teamId':2,'name':away},'startDate':date+'T15:00:00','events':[{'id':1}]};encoded=json.dumps(payload,sort_keys=True,indent=2).encode();(target/'raw_match.json').write_bytes(encoded)
    (target/'metadata.json').write_text(json.dumps({'whoscored_match_id':provider,'checksum':hashlib.sha256(encoded).hexdigest()}))

def test_cache_first_never_invokes_worker(project_path):
    valid(project_path,1,101);calls=[]
    result=acquire(rows().head(1),root=project_path,manifest_path=project_path/'m.csv',worker=lambda c,t:calls.append(c),cache_only=True)
    assert result.iloc[0].status=='CACHE_HIT' and calls==[] and result.iloc[0].attempt_count==0

def test_cache_only_reports_missing_without_browser(project_path):
    result=acquire(rows().head(1),root=project_path,manifest_path=project_path/'m.csv',worker=lambda *_:(_ for _ in ()).throw(AssertionError()),cache_only=True)
    assert result.iloc[0].status=='MISSING' and result.iloc[0].attempt_count==0

def test_timeout_retries_with_clean_worker_and_commits(project_path):
    calls=[]
    def worker(command,timeout):
        calls.append(command)
        if len(calls)==1:return {'timed_out':True,'returncode':-9,'stdout':'','stderr':'','seconds':timeout}
        valid(project_path,1,101);return {'timed_out':False,'returncode':0,'stdout':'','stderr':'','seconds':1}
    result=acquire(rows().head(1),root=project_path,manifest_path=project_path/'m.csv',worker=worker,retries=1,retry_delay=0)
    assert result.iloc[0].status=='ACQUIRED' and result.iloc[0].attempt_count==2 and len(calls)==2

def test_failed_match_does_not_stop_next_match(project_path):
    def worker(command,timeout):
        canonical=int(command[command.index('--match-id')+1])
        if canonical==2: valid(project_path,2,102)
        return {'timed_out':False,'returncode':1 if canonical==1 else 0,'stdout':'','stderr':'failed','seconds':1}
    result=acquire(rows(),root=project_path,manifest_path=project_path/'m.csv',worker=worker,retries=0,retry_delay=0)
    assert result.status.tolist()==['FAILED','ACQUIRED']

def test_invalid_hash_is_not_a_cache_hit(project_path):
    valid(project_path,1,101);p=project_path/'data/raw/whoscored/2526/poc/match_1/raw_match.json';p.write_text('{}')
    assert not validate_cache(project_path/'data/raw/whoscored/2526/poc',rows().iloc[0].to_dict())['cache_valid']
