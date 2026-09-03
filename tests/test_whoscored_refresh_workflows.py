from datetime import datetime,timezone
from pathlib import Path
import json
import pandas as pd

from core.services.refresh_status import derive_refresh_status
from integrations.whoscored.workflows import atomic_json,build_season_manifest,eligible_completed

ROOT=Path(__file__).resolve().parents[1]

def test_historical_manifest_targets_exact_completed_380_without_duplicates():
    frame=build_season_manifest(ROOT,'2526')
    assert len(frame)==380 and frame.is_completed.all()
    assert frame.canonical_match_id.is_unique and frame.whoscored_match_id.is_unique
    assert frame.resolution_status.eq('RESOLVED').all()

def test_completed_eligibility_excludes_future_and_incomplete():
    frame=pd.DataFrame([
      {'kickoff_datetime':'2026-01-01T12:00:00Z','is_completed':True,'whoscored_match_id':1},
      {'kickoff_datetime':'2026-01-01T12:00:00Z','is_completed':False,'whoscored_match_id':2},
      {'kickoff_datetime':'2027-01-01T12:00:00Z','is_completed':True,'whoscored_match_id':3},
      {'kickoff_datetime':'2026-01-01T12:00:00Z','is_completed':True,'whoscored_match_id':None},])
    out=eligible_completed(frame,datetime(2026,8,19,tzinfo=timezone.utc))
    assert out.whoscored_match_id.tolist()==[1]

def test_atomic_report_replaces_complete_json():
    path=ROOT/'.test_artifacts/whoscored_refresh_atomic.json';path.parent.mkdir(exist_ok=True)
    try:
        atomic_json({'state':'old'},path);atomic_json({'state':'new'},path)
        assert json.loads(path.read_text())=={'state':'new'} and not path.with_suffix('.json.tmp').exists()
    finally:
        path.unlink(missing_ok=True)

def test_refresh_status_is_derived_from_real_manifests():
    status=derive_refresh_status(ROOT,'2526').set_index('area')
    assert status.loc['WhoScored Advanced','coverage']=='380/380'
    assert status.loc['WhoScored Advanced','state']=='Complete'
    assert status.loc['Quality','state']=='Current'

def test_hosted_refresh_has_no_whoscored_or_selenium_boundary():
    view=(ROOT/'views/update_pipeline.py').read_text(encoding='utf-8').casefold()
    service=(ROOT/'core/services/operations_service.py').read_text(encoding='utf-8').casefold()
    refresh=(ROOT/'scripts/refresh_live_fantrax.py').read_text(encoding='utf-8').casefold()
    assert 'weekly_advanced_refresh' not in service and 'selenium' not in refresh and 'whoscored' not in refresh
    assert 'commissioner-only' in view

def test_weekly_workflow_can_invoke_whoscored_but_is_not_registered_publicly():
    weekly=(ROOT/'scripts/weekly_advanced_refresh.py').read_text(encoding='utf-8')
    assert 'from integrations.whoscored.controller import acquire' in weekly
    assert "a.plan or a.cache_only" in weekly

def test_quality_failures_remain_visible():
    status=derive_refresh_status(ROOT,'2526')
    assert {'area','state','detail','coverage'}.issubset(status.columns)
    assert 'failed validation gates' in status.loc[status.area.eq('Quality'),'detail'].iloc[0]
