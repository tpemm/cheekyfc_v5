from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
import pytest
from uuid import uuid4

from fantrax.live.matchup_acquisition import commit_live_scoring, normalize_live_scoring, three_way_reconciliation
from fantrax.live.pipeline import _apply_live_matchup_scores


def payload():
    teams={f"t{i}":{"name":f"Manager {i}"} for i in range(1,13)}
    stats={}; scorer={"ACTIVE":{}}
    for i in range(1,13):
        pid=f"p{i}"; score=float(80+i)
        stats[f"t{i}"]={"ACTIVE":{"totalFpts":score,"statsMap":{pid:{"object1":score},"_5010":{"object1":score}}}}
        scorer["ACTIVE"][f"t{i}"]={"5010":[{"scorer":{"scorerId":pid,"name":f"Player {i}"}}]}
    data={"fantasyTeamInfo":teams,"statsPerTeam":{"allTeamsStats":stats},"scorerMap":scorer,"matchups":[f"t{i}_t{i+6}" for i in range(1,7)],"allEventsFinished":True}
    return {"responses":[{"data":data}]}


def test_live_scoring_normalizes_six_matchups_twelve_teams_and_players():
    matchups,players=normalize_live_scoring(payload(),season_id="2627",period=1,acquired_at="now")
    assert len(matchups)==6 and len(set(matchups.home_team_id)|set(matchups.away_team_id))==12
    assert len(players)==12 and players.live_scoring_fpts.sum()==sum(range(81,93))
    row=matchups.iloc[0]; assert row.away_team_id=="t1" and row.home_team_id=="t7" and row.away_score==81 and row.home_score==87 and row.winner=="Manager 7" and row.margin==6


def test_authoritative_period_is_not_overridden_by_csv_sum():
    matchups,_=normalize_live_scoring(payload(),season_id="2627",period=1,acquired_at="now")
    weekly=pd.DataFrame([{"period":1,"current_manager_id":"t7","lineup_status":"ACTIVE","fantasy_points":999}])
    result=_apply_live_matchup_scores(matchups,weekly,protected_periods={1})
    assert result.loc[result.home_team_id.eq("t7"),"home_score"].iat[0]==87


def test_three_way_reconciliation_separates_authority_states():
    matchups,live=normalize_live_scoring(payload(),season_id="2627",period=1,acquired_at="now")
    csv=live.rename(columns={"fantrax_team_id":"current_manager_id","live_scoring_fpts":"fantasy_points"}).copy();csv.loc[csv.current_manager_id.eq("t1"),"fantasy_points"]+=2
    managers,players=three_way_reconciliation(matchups,live,csv)
    assert managers.loc[managers.fantrax_team_id.eq("t1"),"status"].iat[0]=="SOURCE_STATE_DIFFERENCE"
    assert managers.diff_matchup_vs_live.abs().max()==0 and players.status.eq("review").sum()==1


def test_failed_commit_preserves_prior_valid_cache():
    root=Path(".test_artifacts")/f"matchup_{uuid4().hex[:8]}";raw=root/"raw";model=root/"model"
    commit_live_scoring(payload(),raw_root=raw,model_root=model,season_id="2627",period=1,acquired_at="first")
    cached=(raw/"matchups/period_01/live_scoring.json").read_bytes()
    with pytest.raises(ValueError):commit_live_scoring({"responses":[]},raw_root=raw,model_root=model,season_id="2627",period=1)
    assert (raw/"matchups/period_01/live_scoring.json").read_bytes()==cached


def test_real_cached_gw1_matches_private_live_scoring_not_csv_reconstruction():
    root=Path(__file__).resolve().parents[1]; matchups=pd.read_csv(root/"data/models/season_2627/fantrax_matchups_2627.csv")
    reconciliation=pd.read_csv(root/"data/quality/season_2627/fantrax_matchup_three_way_reconciliation_2627.csv")
    assert len(matchups.query("period == 1"))==6 and reconciliation.diff_matchup_vs_live.abs().max()<=.01
    result=matchups.query("period == 1 and home_manager == 'epatel3'").iloc[0]
    assert result.winner=="Berkshire’s Club" and result.margin==.5
