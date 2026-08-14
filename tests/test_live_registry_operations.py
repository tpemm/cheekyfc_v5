import json
from pathlib import Path
import shutil
import uuid

import pytest

from core.services.dataset_registry import DatasetRegistry
from core.services.data_manager import DataManager
from core.services.operations_service import OperationsService
from core.services.season_manager import SeasonManager


LIVE_KEYS={"league_teams","current_rosters","roster_history","roster_change_events","roster_snapshots_manifest","roster_tracking_quality","league_standings","weekly_matchups","manager_week_summary","league_transactions","player_ownership","current_player_weekly","understat_player_weekly","manager_player_weekly","live_season_manifest"}


@pytest.fixture
def project_path():
    path=Path.cwd()/".test_artifacts"/f"live_ops_{uuid.uuid4().hex}"; path.mkdir(parents=True)
    try: yield path
    finally: shutil.rmtree(path,ignore_errors=True)


def test_all_live_datasets_are_registered_for_season_models():
    registry=DatasetRegistry()
    assert LIVE_KEYS.issubset({item.key for item in registry.list_all()})
    for key in LIVE_KEYS:
        definition=registry.get(key)
        assert definition.producer and "season_{season_id}" in definition.working_subdirectory


def test_live_operations_are_registered_with_fixed_project_scripts():
    service=OperationsService(season_manager=SeasonManager())
    keys={item.key for item in service.list_operations("2627")}
    expected={"refresh_live_fantrax_sources","backfill_live_weekly_stats","force_refresh_live_weekly_stats","refresh_live_league_metadata","refresh_live_standings","refresh_live_rosters","build_live_season_datasets","build_roster_tracking","validate_roster_ownership"}
    assert expected.issubset(keys)
    for item in service._operations.values():
        path=Path(item.script_relative_path)
        assert not path.is_absolute() and ".." not in path.parts


def test_roster_operation_validates_period_and_serializes_fixed_source(project_path):
    calls=[]
    class Executor:
        def __call__(self,command,**kwargs):
            calls.append((command,kwargs)); return type("Done",(),{"returncode":0,"stdout":"ok","stderr":""})()
    seasons=SeasonManager(project_root=project_path)
    service=OperationsService(season_manager=seasons,project_root=project_path,executor=Executor())
    assert service.run("refresh_live_rosters","2627",{"period":3}).success
    assert json.loads(calls[0][1]["input"])=={"period":3,"source":"rosters"}
    assert calls[0][0][1].endswith("scripts\\refresh_live_fantrax.py")


def test_weekly_advanced_operations_serialize_backfill_and_explicit_force(project_path):
    calls=[]
    class Executor:
        def __call__(self,command,**kwargs): calls.append(json.loads(kwargs["input"])); return type("Done",(),{"returncode":0,"stdout":"ok","stderr":""})()
    service=OperationsService(season_manager=SeasonManager(project_root=project_path),project_root=project_path,executor=Executor())
    assert service.run("backfill_live_weekly_stats","2627",{}).success
    assert service.run("force_refresh_live_weekly_stats","2627",{"period":4}).success
    assert calls==[{"force":False,"source":"weekly_stats","weekly_mode":"backfill"},{"force":True,"period":4,"source":"weekly_stats","weekly_mode":"force_current"}]


def test_data_manager_loads_registered_live_outputs(project_path):
    registry=DatasetRegistry(); season_root=project_path/"data/models/season_2627"; season_root.mkdir(parents=True)
    for key in LIVE_KEYS-{"live_season_manifest"}:
        definition=registry.get(key); columns=definition.required_columns or ("season_id",)
        import pandas as pd
        pd.DataFrame([{column:"value" for column in columns}]).to_csv(season_root/definition.filename_template.format(season_id="2627"),index=False)
    (season_root/"live_season_manifest_2627.json").write_text('{"season_id":"2627","datasets":[]}',encoding="utf-8")
    seasons=SeasonManager(project_root=project_path)
    manager=DataManager(registry=registry,season_manager=seasons)
    for key in LIVE_KEYS-{"live_season_manifest"}: assert manager.load_frame(key,"2627").data is not None
    assert manager.load_json("live_season_manifest","2627").data["season_id"]=="2627"
