from pathlib import Path
from uuid import uuid4

import pandas as pd

from fantrax.live.player_performance import WEEKLY_COLUMNS, normalize_weekly_export
from fantrax.live.understat_live import (
    cache_understat_matches, load_cached_understat, map_matches_to_periods,
    normalize_understat_matches, player_source_coverage, build_understat_match_products,
    scoring_periods_from_league, supplement_fantrax,
)


def test_live_gw1_understat_products_are_exact_reciprocal_and_preserve_played_zero():
    identity=pd.read_csv("data/reference/understat_match_identity_2627.csv")
    players=pd.read_csv("data/models/season_2627/understat_player_match_2627.csv")
    teams=pd.read_csv("data/models/season_2627/understat_team_match_2627.csv")
    assert len(identity)==20 and identity.resolution_status.isin(["RESOLVED_EXACT","RESOLVED_EXACT_PAIR"]).all()
    assert len(teams)==40 and teams.canonical_club_id.nunique()==20
    for _,rows in teams.groupby("canonical_match_id"):
        assert len(rows)==2
        assert rows.iloc[0].xg==rows.iloc[1].xga and rows.iloc[0].xga==rows.iloc[1].xg
    # The deterministic current identity repair expands exact coverage beyond
    # the original 231-row bootstrap without changing the 310 observations.
    assert len(players)==622 and players.canonical_player_id.notna().sum()>=534
    sangare=players[players.understat_player_id.eq(13917)]
    assert len(sangare)==2 and sangare.canonical_player_id.notna().all()
    assert ((players.minutes>0)&players.xg.eq(0)&players.xa.eq(0)).any()


def test_gw1_known_good_snapshot_is_complete_and_authority_safe():
    import json
    snapshot=json.loads(Path("data/reference/validation/gw1_known_good_2627.json").read_text(encoding="utf-8"))
    assert snapshot["counts"]["matches"]==snapshot["counts"]["whoscored_matches"]==snapshot["counts"]["understat_matches"]==10
    assert snapshot["counts"]["clubs"]==20 and snapshot["counts"]["all_players"]==615
    assert snapshot["authority"]=={"fantasy":"Fantrax","advanced":"WhoScored","expected_goals":"Understat"}


def league_payload():
    return {"scoringPeriods":[
        {"number":1,"startDate":"2026-08-21T15:00:00-0400","endDate":"2026-08-28T14:59:59-0400"},
        {"number":2,"startDate":"2026-08-28T15:00:00-0400","endDate":"2026-09-04T14:59:59-0400"},
    ]}


def registry():
    return pd.DataFrame([{"understat_player_id":"10","registry_player_id":"r1","fantrax_player_id":"p1","canonical_name":"Known","current_team":"ARS"}])


def understat_matches():
    return pd.DataFrame([
        {"player_id":10,"game_id":100,"kickoff_datetime":"2026-08-22T14:00:00Z","player_name":"Known","team_name":"ARS","minutes":70,"goals":1,"assists":0,"shots":3,"key_passes":2,"yellow_cards":0,"red_cards":0,"xg":0.7,"xa":0.2},
        {"player_id":10,"game_id":101,"kickoff_datetime":"2026-08-27T19:00:00Z","player_name":"Known","team_name":"ARS","minutes":20,"goals":0,"assists":1,"shots":1,"key_passes":1,"yellow_cards":1,"red_cards":0,"xg":0.1,"xa":0.4},
    ])


def test_existing_understat_schema_audit_is_proven_by_cached_2526_matches():
    columns=pd.read_csv("data/raw/understat/understat_player_match_stats_2526_ENG-Premier_League.csv",nrows=1).columns
    assert {"player_id","game_id","kickoff_datetime","minutes","goals","assists","shots","key_passes","yellow_cards","red_cards","xg","xa","xg_chain","xg_buildup"} <= set(columns)
    assert "starts" not in columns


def test_preseason_empty_cache_is_valid_and_build_is_cache_only():
    weekly,unresolved=load_cached_understat(Path(".test_artifacts")/f"missing-understat-{uuid4().hex}",scoring_periods_from_league(league_payload()),registry())
    assert weekly.empty and unresolved.empty


def test_acquisition_cache_is_restricted_to_2627_raw_namespace():
    root=Path(".test_artifacts")/f"understat-2627-{uuid4().hex}"/"data"/"raw"/"understat"/"2627"
    path=cache_understat_matches(understat_matches(),root)
    assert path.parent==root and path.name=="understat_player_match_stats_2627.csv"
    try: cache_understat_matches(pd.DataFrame(),root,season_id="2526")
    except ValueError: pass
    else: raise AssertionError("Live acquisition wrote outside 2627")


def test_match_mapping_uses_fantrax_boundaries_and_aggregates_double_gameweek():
    periods=scoring_periods_from_league(league_payload()); mapped=map_matches_to_periods(understat_matches(),periods)
    assert mapped["period"].tolist()==[1,1]
    weekly,_=normalize_understat_matches(understat_matches(),periods,registry(),retrieved_at="now")
    row=weekly.iloc[0]; assert row.matches_in_period==2 and row.minutes==90 and row.goals==1 and row.xgi==1.4


def test_rescheduled_match_maps_by_date_not_understat_gameweek():
    match=understat_matches().iloc[:1].assign(kickoff_datetime="2026-08-30T12:00:00Z",gameweek=1)
    mapped=map_matches_to_periods(match,scoring_periods_from_league(league_payload()))
    assert mapped.iloc[0].period==2


def test_registry_exact_id_is_required_and_name_only_match_is_rejected():
    unknown=understat_matches().assign(player_id=999,player_name="Known")
    weekly,unresolved=normalize_understat_matches(unknown,scoring_periods_from_league(league_payload()),registry(),retrieved_at="now")
    assert weekly.empty and unresolved.iloc[0].reason=="No exact Understat ID in Player Registry"


def test_fantrax_wins_zero_is_not_missing_and_understat_fills_only_missing():
    ft=pd.DataFrame([{"period":1,"fantrax_player_id":"p1","player_name":"Known","fantasy_points":10,"goals":0,"assists":pd.NA,"shots":0,"key_passes":pd.NA,"minutes":90,"appearance":1,"yellow_cards":0,"red_cards":0,"clean_sheets":pd.NA,"goals_against":pd.NA,"fantrax_position":"M"}])
    fantrax=normalize_weekly_export(ft,retrieved_at="fantrax")
    understat,_=normalize_understat_matches(understat_matches(),scoring_periods_from_league(league_payload()),registry(),retrieved_at="understat")
    result=supplement_fantrax(fantrax,understat,weekly_columns=WEEKLY_COLUMNS); row=result.iloc[0]
    assert row.goals==0 and row.goals_source=="fantrax_weekly"
    assert row.shots==0 and row.shots_source=="fantrax_weekly"
    assert row.assists==1 and row.assists_source=="understat"
    assert row.key_passes==3 and row.key_passes_source=="understat"
    assert round(row.xg,3)==0.8 and row.xg_source=="understat" and row.xa_source=="understat" and row.xgi_source=="understat"
    assert pd.isna(row.ghost_points) and pd.isna(row.fantrax_key_passes)


def test_understat_only_player_never_receives_fantasy_or_ghost_points():
    understat,_=normalize_understat_matches(understat_matches(),scoring_periods_from_league(league_payload()),registry(),retrieved_at="understat")
    row=supplement_fantrax(pd.DataFrame(columns=WEEKLY_COLUMNS),understat,weekly_columns=WEEKLY_COLUMNS).iloc[0]
    assert pd.isna(row.fantasy_points) and pd.isna(row.ghost_points)
    assert row.key_passes==3 and row.key_passes_source=="understat"


def test_coverage_reports_entire_pool_and_fantasy_relevant_separately():
    understat,_=normalize_understat_matches(understat_matches(),scoring_periods_from_league(league_payload()),registry(),retrieved_at="understat")
    weekly=supplement_fantrax(pd.DataFrame(columns=WEEKLY_COLUMNS),understat,weekly_columns=WEEKLY_COLUMNS)
    players=pd.DataFrame([
        {"fantrax_player_id":"p1","registry_player_id":"r1","understat_player_id":"10","player_name":"Known","available":True,"drafted":True,"projected_minutes_percentage":50,"historical_minutes":100},
        {"fantrax_player_id":"p2","registry_player_id":"r2","player_name":"Other","available":True,"drafted":False,"projected_minutes_percentage":0,"historical_minutes":0},
    ])
    detail,summary=player_source_coverage(players,weekly)
    assert len(detail)==2 and summary.set_index("population").loc["ENTIRE_POOL","player_count"]==2
    assert summary.set_index("population").loc["FANTASY_RELEVANT","player_count"]==1
    assert detail.set_index("fantrax_player_id").loc["p1","coverage_status"]=="UNDERSTAT_SUPPLEMENTED"
