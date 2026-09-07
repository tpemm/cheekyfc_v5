from pathlib import Path
from types import SimpleNamespace
import shutil
import pandas as pd
import pytest
from core.services.refresh_status import derive_refresh_status, published_period_progress, team_model_status
from core.services.data_manager import DataManager
from views.league_hub import _load_frame

ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def published_root(tmp_path):
    paths=[
        "data/models/season_2627/live_season_manifest_2627.json",
        "data/models/season_2627/fantrax_matchups_2627.csv",
        "data/models/season_2627/understat_team_match_2627.csv",
        "data/models/season_2627/team_match_analytics_2627.csv",
        "data/models/season_2627/advanced/advanced_player_match_2627.csv",
        "data/models/season_2627/advanced/whoscored_event_2627.csv",
        "data/reference/whoscored_season_manifest_2627.csv",
        "data/reference/whoscored_player_identity.csv",
        "data/reference/manager_observations_2627.csv",
    ]
    paths += ["data/quality/season_2627/"+name for name in [
        "weekly_commissioner_refresh_latest.json","weekly_period_status_2627.csv",
        "fantrax_matchup_three_way_reconciliation_2627.csv","weekly_unified_latest_2627.json",
        "understat_live_latest_2627.json","understat_gw1_quality_gates_2627.csv"]]
    for name in paths:
        target=tmp_path/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    assert not (tmp_path/"data/raw").exists()
    return tmp_path


def test_published_status_without_any_raw_or_auth(published_root):
    status=derive_refresh_status(published_root).set_index("area")
    assert status.loc["Fantrax Weekly Exports","state"]=="Current"
    assert status.loc["Fantrax Weekly Exports","coverage"]=="12/12 managers"
    assert "all-player 668 rows" in status.loc["Fantrax Weekly Exports","detail"]
    assert status.loc["Fantrax Matchup Scores","state"]=="Current"
    assert "12/12 teams" in status.loc["Fantrax Matchup Scores","coverage"]
    assert "6/6 matchups" in status.loc["Fantrax Matchup Scores","coverage"]
    assert status.loc["WhoScored Advanced","state"]=="Complete"
    assert status.loc["WhoScored Advanced","coverage"]=="30/30"
    assert status.loc["Schedule / Understat","state"]=="Current"
    assert status.loc["Schedule / Understat","coverage"]=="30 matches "+chr(183)+" 60 team "+chr(183)+" 929 player"
    assert "Latest completed GW 3" in status.loc["Schedule / Understat","detail"]
    assert status.loc["Player / Matchup Reconciliation","coverage"]=="12/12 live exact"
    assert status.loc["Team Models","state"]=="CURRENT"
    assert "30 matches" in status.loc["Team Models","coverage"]


def test_core_progress_uses_published_results_not_elapsed_fixtures():
    fixtures=pd.read_csv(ROOT/"data/models/season_2627/team_matches_2627.csv")
    results=pd.read_csv(ROOT/"data/models/season_2627/advanced/whoscored_match_2627.csv")
    before=fixtures.copy(deep=True)
    assert published_period_progress(fixtures,3,results)==dict(state="COMPLETE_PENDING_CORRECTIONS",completed=10,total=10)
    assert published_period_progress(fixtures,3,results.iloc[:0])["completed"]==0
    pd.testing.assert_frame_equal(fixtures,before)


def test_team_status_checks_grain_not_single_gameweek_count():
    team=pd.read_csv(ROOT/"data/models/season_2627/team_match_analytics_2627.csv")
    assert len(team)==60 and team.canonical_match_id.nunique()==30
    assert team_model_status(team)=="CURRENT"
    assert team_model_status(team.iloc[1:])=="STALE_OR_MISSING"
    assert team_model_status(pd.concat([team,team.iloc[[0]]]))=="STALE_OR_MISSING"


def test_league_hub_published_csv_parses_without_warning(monkeypatch):
    warnings=[];calls=[];read=pd.read_csv
    def csv(*args,**kwargs):
        calls.append(kwargs)
        return read(*args,**kwargs)
    monkeypatch.setattr(pd,"read_csv",csv)
    frame=_load_frame(DataManager(),"league_active_player_weekly","2627","working",SimpleNamespace(warning=warnings.append))
    assert not warnings
    assert len(frame)==396 and frame.groupby("period").size().to_dict()=={1:132,2:132,3:132}
    assert frame.groupby("period").manager_id.nunique().eq(12).all()
    assert any(c.get("engine")=="python" and c.get("dtype",{}).get("fantrax_player_id") is str for c in calls)
