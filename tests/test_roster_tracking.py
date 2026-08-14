from __future__ import annotations

import json
from pathlib import Path
import shutil
import uuid

import pandas as pd
import pytest

from fantrax.live.roster_tracking import archive_snapshot, detect_changes, stable_roster_checksum, update_history
from scripts.refresh_live_fantrax import roster_periods
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def project_path():
    path=ROOT/".test_artifacts"/f"roster_{uuid.uuid4().hex}"; path.mkdir(parents=True)
    try: yield path
    finally: shutil.rmtree(path,ignore_errors=True)


def roster(manager="m1", lineup="starter", registry="r1", observed="2026-08-01T00:00:00Z"):
    return pd.DataFrame([{"season_id":"2627","observed_at":observed,"source_retrieved_at":observed,"period":1,"manager_id":manager,"manager_name":manager.upper(),"fantasy_team_id":f"t-{manager}","fantasy_team_name":f"Team {manager}","fantrax_player_id":"p1","registry_player_id":registry,"player_name":"Player One","roster_status":"rostered","lineup_status":lineup,"validation_status":"valid"}])


def changes(before, after, event_time="2026-08-02T00:00:00Z"):
    return detect_changes(before,after,previous_checksum=stable_roster_checksum(before),new_checksum=stable_roster_checksum(after),detected_at=event_time,period=1)


def test_checksum_excludes_volatile_timestamps():
    assert stable_roster_checksum(roster(observed="a")) == stable_roster_checksum(roster(observed="b"))


def test_baseline_archives_once_and_starts_history_without_add_events(project_path):
    current=roster(); root=project_path/"rosters"
    first=archive_snapshot(current,archive_root=root,season_id="2627",league_id="league",observed_at="2026-08-01T00:00:00Z",source_retrieved_at="2026-08-01T00:00:00Z",period=1,valid=True)
    second=archive_snapshot(roster(observed="later"),archive_root=root,season_id="2627",league_id="league",observed_at="2026-08-02T00:00:00Z",source_retrieved_at="later",period=1,valid=True)
    history=update_history(pd.DataFrame(),current,pd.DataFrame(),observed_at=first["observed_at"],period=1)
    assert first["created"] and not first["materially_changed"]
    assert not second["created"] and len(list(root.glob("*.csv")))==1
    assert len(history)==1 and bool(history.iloc[0]["currently_active"])


def test_invalid_roster_is_not_archived(project_path):
    result=archive_snapshot(roster(),archive_root=project_path,season_id="2627",league_id="league",observed_at="2026-08-01T00:00:00Z",source_retrieved_at="now",period=1,valid=False)
    assert not result["created"] and not list(project_path.glob("*.csv"))


def test_changed_snapshot_is_immutable_and_checksum_chain_is_correct(project_path):
    first=archive_snapshot(roster(),archive_root=project_path,season_id="2627",league_id="league",observed_at="2026-08-01T00:00:00Z",source_retrieved_at="one",period=1,valid=True)
    before=Path(first["snapshot_path"]).read_bytes()
    second=archive_snapshot(roster(lineup="bench"),archive_root=project_path,season_id="2627",league_id="league",observed_at="2026-08-02T00:00:00Z",source_retrieved_at="two",period=1,valid=True)
    metadata=json.loads(Path(second["snapshot_path"]).with_suffix(".metadata.json").read_text())
    assert second["created"] and metadata["previous_snapshot_checksum"]==first["checksum"]
    assert Path(first["snapshot_path"]).read_bytes()==before and len(list(project_path.glob("*.csv")))==2


def test_ownership_and_lineup_event_types_are_deterministic():
    added=changes(pd.DataFrame(columns=roster().columns),roster())
    dropped=changes(roster(),pd.DataFrame(columns=roster().columns))
    transferred=changes(roster(),roster(manager="m2"))
    reserve=changes(roster(),roster(lineup="bench"))
    active=changes(roster(lineup="bench"),roster())
    moved_ir=changes(roster(),roster(lineup="ir"))
    returned=changes(roster(lineup="ir"),roster())
    assert added["event_type"].tolist()==["PLAYER_ADDED"]
    assert dropped["event_type"].tolist()==["PLAYER_DROPPED"]
    assert transferred["event_type"].tolist()==["PLAYER_TRANSFERRED_BETWEEN_MANAGERS"] and "TRADE" not in transferred["event_type"].iat[0]
    assert reserve["event_type"].iat[0]=="MOVED_TO_RESERVE"
    assert active["event_type"].iat[0]=="MOVED_TO_ACTIVE"
    assert moved_ir["event_type"].iat[0]=="MOVED_TO_IR"
    assert returned["event_type"].iat[0]=="RETURNED_FROM_IR"
    assert changes(roster(),roster(lineup="bench"))["event_id"].iat[0]==reserve["event_id"].iat[0]


def test_identity_resolution_and_history_interval_update_are_idempotent():
    before=roster(registry=pd.NA); after=roster(registry="r1")
    events=changes(before,after)
    baseline=update_history(pd.DataFrame(),before,pd.DataFrame(),observed_at="2026-08-01T00:00:00Z",period=1)
    updated=update_history(baseline,after,events,observed_at="2026-08-02T00:00:00Z",period=1)
    assert events["event_type"].tolist()==["PLAYER_IDENTITY_RESOLVED"]
    assert len(updated)==2 and updated["currently_active"].fillna(False).sum()==1
    assert updated.iloc[0]["ownership_ended_at"]=="2026-08-02T00:00:00Z"


def test_normal_refresh_uses_current_period_and_full_history_is_explicit():
    config=SimpleNamespace(period_minimum=1,period_maximum=38,validate_period=lambda value:int(value))
    assert roster_periods(config,league_payload={"currentScoringPeriod":3})==(3,)
    assert roster_periods(config,league_payload={})==(1,)
    assert roster_periods(config,explicit=7)==(7,)
    assert roster_periods(config,full_history=True)==tuple(range(1,39))
