import io
import json
from pathlib import Path
import shutil
import sys
import uuid

import pandas as pd
import pytest

from core.services.operations_service import OperationsService
from core.services.season_manager import SeasonManager
from fantrax.api import transform_fantrax_api_json as transformer
from fantrax.refresh import refresh_all_fantrax_data as legacy_refresh
from fantrax.utils.cli import configure_unicode_console


ROOT=Path(__file__).resolve().parents[1]


class Cp1252Console:
    encoding="cp1252"
    def __init__(self): self.parts=[]
    def write(self,text):
        text.encode(self.encoding,errors="strict"); self.parts.append(text); return len(text)
    def flush(self): return None


class ReconfigurableConsole(Cp1252Console):
    def __init__(self): super().__init__(); self.calls=[]
    def reconfigure(self,**kwargs): self.calls.append(kwargs); self.encoding=kwargs["encoding"]


@pytest.fixture
def artifact_dir():
    path=ROOT/".test_artifacts"/f"unicode_{uuid.uuid4().hex}"; path.mkdir(parents=True)
    try: yield path
    finally: shutil.rmtree(path,ignore_errors=True)


def test_console_configuration_requests_utf8_and_replacement(monkeypatch):
    stdout,stderr=ReconfigurableConsole(),ReconfigurableConsole()
    monkeypatch.setattr(sys,"stdout",stdout); monkeypatch.setattr(sys,"stderr",stderr)
    configure_unicode_console()
    assert stdout.calls==[{"encoding":"utf-8","errors":"replace"}]
    assert stderr.calls==[{"encoding":"utf-8","errors":"replace"}]


def test_save_csv_preserves_unicode_when_cp1252_preview_cannot(monkeypatch,artifact_dir):
    output=artifact_dir/"standings.csv"; console=Cp1252Console(); monkeypatch.setattr(sys,"stdout",console)
    frame=pd.DataFrame([{"rank":1,"team_name":"Atlético 🤡 United"}])
    transformer.save_csv(frame,output)
    saved=pd.read_csv(output,encoding="utf-8-sig")
    assert saved.loc[0,"team_name"]=="Atlético 🤡 United"
    assert output.exists() and "Saved:" in "".join(console.parts)


def test_transformer_main_completes_and_preserves_unicode(monkeypatch,artifact_dir):
    raw=artifact_dir/"raw"; processed=artifact_dir/"processed"; raw.mkdir()
    league={"leagueName":"Líga 🤡","matchups":[],"playerInfo":{},"rosterInfo":{},"draftSettings":{},"poolSettings":{},"scoringSystem":{}}
    standings=[{"rank":1,"teamId":"t1","teamName":"Atlético 🤡 United","points":"0-0-0","totalPointsFor":0}]
    (raw/"league_info.json").write_text(json.dumps(league,ensure_ascii=False),encoding="utf-8")
    (raw/"standings.json").write_text(json.dumps(standings,ensure_ascii=False),encoding="utf-8")
    source_before={path.name:path.read_bytes() for path in raw.iterdir()}
    monkeypatch.setattr(transformer,"RAW_API_DIR",raw); monkeypatch.setattr(transformer,"PROCESSED_API_DIR",processed)
    monkeypatch.setattr(transformer,"LEAGUE_INFO_FILE",raw/"league_info.json"); monkeypatch.setattr(transformer,"STANDINGS_FILE",raw/"standings.json")
    console=Cp1252Console(); monkeypatch.setattr(sys,"stdout",console)
    transformer.main()
    saved=pd.read_csv(processed/"standings.csv",encoding="utf-8-sig")
    assert saved.loc[0,"team_name"]=="Atlético 🤡 United"
    assert (processed/"league_summary.csv").exists()
    assert {path.name:path.read_bytes() for path in raw.iterdir()}==source_before


def test_legacy_auto_reaches_roster_transform_after_step_two(monkeypatch,artifact_dir):
    calls=[]; roster_transform=artifact_dir/"transform_rosters.py"; roster_transform.write_text("",encoding="utf-8")
    monkeypatch.setattr("builtins.input",lambda prompt="":"AUTO")
    monkeypatch.setattr(legacy_refresh,"api_outputs_exist",lambda:False)
    monkeypatch.setattr(legacy_refresh,"pick_roster_transform_script",lambda:roster_transform)
    monkeypatch.setattr(legacy_refresh,"configure_unicode_console",lambda:None)
    def run_script(lines,script,args=None,**kwargs):
        calls.append((script,list(args or [])))
        if script==roster_transform: raise RuntimeError("past step two")
    monkeypatch.setattr(legacy_refresh,"run_script",run_script)
    with pytest.raises(RuntimeError,match="past step two"): legacy_refresh.main()
    assert [call[0] for call in calls[:3]]==[legacy_refresh.FETCH_API,legacy_refresh.TRANSFORM_API,roster_transform]
    assert "--force" in calls[0][1] and "--periods" not in calls[0][1]


def test_auto_operation_is_legacy_and_sprint7_refresh_is_separate():
    operations=OperationsService(season_manager=SeasonManager())
    assert operations._operations["refresh_fantrax_data"].script_relative_path=="fantrax/refresh/refresh_all_fantrax_data.py"
    assert operations._operations["refresh_live_fantrax_sources"].script_relative_path=="scripts/refresh_live_fantrax.py"
