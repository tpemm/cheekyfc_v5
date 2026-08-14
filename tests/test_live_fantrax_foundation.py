import hashlib
import json
from pathlib import Path
import shutil
import uuid

import pandas as pd
import pytest

from fantrax.live.acquisition import FantraxAccessError, fetch_json
from urllib.error import HTTPError
from fantrax.live.cache import cache_filename, cache_path, refresh_json, write_validated_json
from fantrax.live.config import load_live_season_config
from fantrax.live.normalization import normalize_transactions
from fantrax.live.pipeline import build_live_season
from fantrax.live.validation import (
    validate_league_teams, validate_matchups, validate_ownership,
    validate_rosters, validate_standings, validate_transactions,
)


ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def project_path():
    path=ROOT/".test_artifacts"/f"live_{uuid.uuid4().hex}"; path.mkdir(parents=True)
    try: yield path
    finally: shutil.rmtree(path,ignore_errors=True)


def config(tmp_path):
    return load_live_season_config(environ={"FANTRAX_LEAGUE_ID_2627":"live-league"},project_root=tmp_path)


def valid(payload):
    if not payload: raise ValueError("invalid")


def teams_payload():
    return {"teamInfo":{f"t{i}":{"teamId":f"t{i}","teamName":f"Team {i}","managerId":f"m{i}","managerName":f"Manager {i}","draftSlot":i} for i in range(1,13)},
        "matchups":[{"period":1,"matchupList":[{"id":f"game-{i}","home":{"id":f"t{i}","name":f"Manager {i}","score":100+i},"away":{"id":f"t{i+6}","name":f"Manager {i+6}","score":90+i},"status":"completed"} for i in range(1,7)]}]}


def standings_payload():
    return [{"rank":i,"teamId":f"t{i}","teamName":f"Team {i}","managerId":f"m{i}","managerName":f"Manager {i}","record":"1-0-0","tablePoints":3,"totalPointsFor":100+i,"totalPointsAgainst":90+i,"gamesPlayed":1} for i in range(1,13)]


def roster_payload():
    return {"teams":[{"teamId":f"t{i}","teamName":f"Team {i}","managerId":f"m{i}","managerName":f"Manager {i}","players":[{"playerId":f"p{i}","playerName":f"Player {i}","eligiblePos":"D,M","status":"starter","team":"ARS"}]} for i in range(1,13)]}


def seed_cache(cfg):
    for category,request,payload,period in (("league","league_metadata",teams_payload(),None),("standings","standings",standings_payload(),None),("rosters","rosters",roster_payload(),1)):
        path=cache_path(cfg,category,request,period=period) if period else cache_path(cfg,category,request)
        write_validated_json(path,payload,config=cfg,request_type=request,source="fixture",validator=valid)
    registry=cfg.model_root.parents[1]/"reference"/"player_registry_2627.csv"; registry.parent.mkdir(parents=True)
    pd.DataFrame({"fantrax_player_id":[f"p{i}" for i in range(1,13)],"registry_player_id":[f"r{i}" for i in range(1,13)],"canonical_name":[f"Player {i}" for i in range(1,13)]}).to_csv(registry,index=False)


def test_configuration_centralizes_2627_and_requires_external_league_id(project_path):
    missing=load_live_season_config(environ={},project_root=project_path)
    assert missing.season_id=="2627" and missing.manager_count==12 and missing.league_id is None
    with pytest.raises(RuntimeError,match="FANTRAX_LEAGUE_ID_2627"): missing.require_league_id()
    assert config(project_path).require_league_id()=="live-league"
    source=(ROOT/"config/live_season_2627.json").read_text(encoding="utf-8")
    assert "rg1i70pfmdhjhvn3" not in source and "FANTRAX_LEAGUE_ID_2627" in source
    assert "*auth_state*.json" in (ROOT/".gitignore").read_text(encoding="utf-8")
    inventory=(ROOT/"docs/fantrax_data_sources.md").read_text(encoding="utf-8")
    for component in ("fetch_fantrax_api_data.py","transform_fantrax_api_json.py","fetch_fantrax_api_player_ids_epl.py","scrape_allplayers_weekly_fantrax.py","scrape_team_rosters_weekly_fantrax.py","refresh_all_fantrax_data.py","merge_master_with_api_rosters_v2.py"):
        assert component in inventory


def test_cache_names_metadata_and_failed_refresh_preserve_valid_artifact(project_path):
    cfg=config(project_path); path=cache_path(cfg,"rosters","rosters",period=1)
    assert cache_filename("rosters",cfg,period=1)=="rosters_2627_period_01.json"
    metadata=refresh_json(path,lambda:{"rows":[1]},config=cfg,request_type="rosters",source="mock",validator=valid)
    before=path.read_bytes(); assert metadata["retrieved_at"] and metadata["validation_status"]=="valid"
    assert json.loads(path.with_suffix(".json.metadata.json").read_text())["sha256"]
    with pytest.raises(ValueError): refresh_json(path,lambda:{},config=cfg,request_type="rosters",source="mock",validator=valid)
    assert path.read_bytes()==before


def test_refresh_network_boundary_accepts_mocked_http_only():
    class Response:
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def read(self): return b'{"teams": [1]}'
    calls=[]
    def opener(request,timeout): calls.append((request.full_url,timeout)); return Response()
    assert fetch_json("league_metadata","league",opener=opener)=={"teams":[1]}
    assert "getLeagueInfo" in calls[0][0]
    with pytest.raises(ValueError,match="No proven"): fetch_json("transactions","league",opener=opener)


def test_authorization_failure_is_actionable():
    def denied(*args,**kwargs): raise HTTPError("url",403,"Forbidden",{},None)
    with pytest.raises(FantraxAccessError,match="league is public|authenticated"):
        fetch_json("league_metadata","private",opener=denied)


def test_real_response_shape_fixture_normalizes_team_and_roster(project_path):
    cfg=config(project_path)
    league={"teamInfo":{"t1":{"id":"t1","name":"Manager One"}},"playerInfo":{"p1":{"eligiblePos":"D,M","status":"FA"}}}
    teams=__import__("fantrax.live.normalization",fromlist=["normalize_league_teams"]).normalize_league_teams(league,cfg,refreshed_at="now")
    payload={"period":1,"rosters":{"t1":{"teamName":"Team One","salaryCap":200.0,"rosterItems":[{"id":"p1","position":"D","status":"ACTIVE"}]}}}
    from fantrax.live.normalization import normalize_rosters
    roster=normalize_rosters(payload,cfg,period=1,refreshed_at="now",player_info=league["playerInfo"],teams=teams)
    assert teams.iloc[0]["manager_id"]=="t1" and teams.iloc[0]["manager_name"]=="Manager One"
    assert roster.iloc[0]["fantrax_player_id"]=="p1" and roster.iloc[0]["fantrax_position"]=="D,M" and bool(roster.iloc[0]["active"])


def test_cache_only_build_normalizes_registry_quality_and_manifest(project_path,monkeypatch):
    cfg=config(project_path); seed_cache(cfg)
    monkeypatch.setattr("urllib.request.urlopen",lambda *a,**k: (_ for _ in ()).throw(AssertionError("HTTP called")))
    result=build_live_season(cfg)
    assert len(result["datasets"]["league_teams"])==12
    assert len(result["datasets"]["current_rosters"])==12
    assert result["datasets"]["current_rosters"]["registry_player_id"].notna().all()
    assert len(result["datasets"]["roster_history"])==12
    assert len(result["datasets"]["weekly_matchups"])==6
    assert len(result["datasets"]["manager_week_summary"])==12
    assert len(result["datasets"]["player_ownership"])==12
    manifest=json.loads(result["manifest_path"].read_text()); assert len(manifest["datasets"])==19
    assert "live_league_summary" in result["datasets"]
    assert all(item["sha256"] and item["validation_result"]=="valid" for item in manifest["datasets"])
    assert (cfg.quality_root/"live_season_quality_summary.csv").exists()
    assert (cfg.quality_root/"unresolved_live_player_identities.csv").exists()
    for name in ("roster_validation_2627.csv","matchup_validation_2627.csv","transaction_validation_2627.csv","standings_validation_2627.csv"):
        assert (cfg.quality_root/name).exists()


def test_failed_build_preserves_previous_normalized_outputs(project_path):
    cfg=config(project_path); seed_cache(cfg); build_live_season(cfg)
    output=cfg.model_root/"league_teams_2627.csv"; before=output.read_bytes()
    bad=teams_payload(); bad["teamInfo"].pop("t12")
    write_validated_json(cache_path(cfg,"league","league_metadata"),bad,config=cfg,request_type="league_metadata",source="fixture",validator=valid)
    with pytest.raises(ValueError,match="prior normalized"): build_live_season(cfg)
    assert output.read_bytes()==before


def test_validation_rejects_duplicate_ids_rosters_standings_matchups_and_ownership(project_path):
    cfg=config(project_path)
    teams=pd.DataFrame([{"active":True,"manager_id":"same","fantasy_team_id":"same","manager_name":"","fantasy_team_name":"X"}]*12)
    assert set(validate_league_teams(teams,cfg)["rule"]) >= {"unique_manager_id","unique_fantasy_team_id","nonblank_names"}
    rosters=pd.DataFrame([{"period":1,"fantrax_player_id":"p","fantasy_team_id":"t1","lineup_status":"starter","fantrax_position":"D/M"},{"period":1,"fantrax_player_id":"p","fantasy_team_id":"t2","lineup_status":"invalid","fantrax_position":"D/M"}])
    assert {"one_owner_per_period","lineup_status"}.issubset(set(validate_rosters(rosters,cfg)["rule"]))
    standings=pd.DataFrame([{"period":1,"rank":1,"wins":-1,"draws":0,"losses":0,"fantasy_points_for":"x"}]*12)
    assert {"unique_rank","valid_numeric"}.issubset(set(validate_standings(standings,cfg)["rule"]))
    matchups=pd.DataFrame([{"period":1,"matchup_id":"x","home_team_id":"a","away_team_id":"b","status":"completed","home_score":2,"away_score":1,"home_manager":"A","away_manager":"B","winner":"B"}]*2)
    assert {"unique_matchup_id","one_matchup_per_period","winner_consistency"}.issubset(set(validate_matchups(matchups)["rule"]))
    ownership=pd.DataFrame([{"fantrax_player_id":"p","available":True,"current_manager":"A"},{"fantrax_player_id":"p","available":False,"current_manager":"B"}])
    assert {"one_current_status","availability_exclusive"}.issubset(set(validate_ownership(ownership,rosters)["rule"]))


def test_transaction_types_identity_fields_and_timestamp_validation(project_path):
    cfg=config(project_path); payload={"transactions":[
        {"id":"a","type":"Player Add","timestamp":"2026-08-03T12:00:00Z","playerAdded":"One"},
        {"id":"b","type":"Drop","timestamp":"2026-08-03T12:01:00Z","playerDropped":"Two"},
        {"id":"c","type":"Trade","timestamp":"2026-08-03T12:02:00Z","playersSent":"Three","playersReceived":"Four"},
        {"id":"d","type":"Mystery","timestamp":"bad"}]}
    frame=normalize_transactions(payload,cfg,refreshed_at="now")
    assert frame["transaction_type"].tolist()==["add","drop","trade","unknown"]
    assert validate_transactions(frame)["rule"].tolist()==["timestamp"]


def test_protected_artifacts_and_finalized_manifest_are_unchanged():
    expected={
        "data/snapshots/draft_2627/draft_rankings_draft_day_2627.csv":"1cb42077c845c567f2149e78ef1674f9df3a8fd993a6b8ed43427f4c5014e7f1",
        "data/models/draft_2627/draft_pick_grades_2627.csv":"4242032df9c47d6f0398fc997e598abae09e8dc0caecd46aa0c89d99b144fcf5",
        "data/seasons/2526/season_manifest.json":"d12e9a23b2783d895771ff95e5e0b39d067bfc1fed6a2c18f2800ce1a6f0d616"}
    for name,digest in expected.items(): assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest
