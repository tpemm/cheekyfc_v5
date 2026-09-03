from pathlib import Path
import pandas as pd
from analytics.teams.fixtures import alias_map, build_team_fixtures, canonicalize_matches, enrich_players_with_fixtures, load_clubs, map_fantrax_periods, next_league_fixtures, resolve_club
from views.teams import directory_frame, fixture_frame, squad_frame
from scripts.build_team_fixture_foundation import _validated_periods

ROOT=Path(__file__).resolve().parents[1]

def clubs(): return load_clubs(ROOT/"data/reference/premier_league_clubs_2627.csv")

def test_registry_has_all_20_unique_clubs_and_provider_mappings():
    frame=clubs(); assert len(frame)==20; assert frame.canonical_club_id.nunique()==20
    assert frame.fantrax_code.notna().all() and frame.football_data_team_id.notna().all()

def test_brighton_aliases_resolve_deterministically():
    frame=clubs(); expected="brighton_hove_albion"
    assert {resolve_club(value,frame) for value in ("BHA","Brighton","Brighton & Hove Albion")}=={expected}
    assert "bha" in alias_map(frame)

def sample_matches():
    return pd.DataFrame([{"match_id":1,"match_date":"2026-08-22T14:00:00Z","status":"incomplete","game_week":1,"home_team_id":180,"home_team":"Brighton & Hove Albion","away_team_id":57,"away_team":"Arsenal","home_score":0,"away_score":0}])

def test_match_normalization_and_orientation_prevent_duplicates():
    matches=canonicalize_matches(sample_matches(),clubs(),retrieved_at="now")
    assert len(matches)==1 and matches.iloc[0].home_club_id=="brighton_hove_albion"
    fixtures=build_team_fixtures(matches); assert len(fixtures)==2
    assert set(fixtures.home_away)=={"H","A"}; assert set(fixtures.opponent_id)=={"arsenal","brighton_hove_albion"}

def test_period_mapping_supports_double_gameweek_and_rescheduled_match():
    matches=pd.DataFrame({"kickoff_time":["2026-09-01T12:00Z","2026-09-04T12:00Z","2026-09-10T12:00Z"]})
    periods=pd.DataFrame({"fantrax_gw":[3],"period_start":["2026-08-31T00:00Z"],"period_end":["2026-09-06T23:59Z"]})
    result=map_fantrax_periods(matches,periods)
    assert result.fantrax_period.tolist()[:2]==[3,3] and pd.isna(result.fantrax_period.iloc[2])

def test_future_selection_excludes_completed_and_cups_and_orders_postponed():
    frame=pd.DataFrame([
        {"club_id":"arsenal","competition_type":"cup","completed":False,"kickoff_time":"2026-08-20T12:00Z","match_id":"cup"},
        {"club_id":"arsenal","competition_type":"league","completed":True,"kickoff_time":"2026-08-21T12:00Z","match_id":"done"},
        {"club_id":"arsenal","competition_type":"league","completed":False,"kickoff_time":"2026-09-03T12:00Z","match_id":"late","status":"postponed"},
        {"club_id":"arsenal","competition_type":"league","completed":False,"kickoff_time":"2026-08-23T12:00Z","match_id":"next","status":"scheduled"},
    ])
    assert next_league_fixtures(frame,"arsenal",now="2026-08-19T00:00Z").match_id.tolist()==["next","late"]

def test_brighton_player_fixture_regression_and_next_five():
    clubs_frame=clubs(); matches=canonicalize_matches(sample_matches(),clubs_frame,retrieved_at="now")
    fixtures=build_team_fixtures(matches); fixtures["overall_fixture_ease"]=61.0
    players=pd.DataFrame({"premier_league_club":["BHA"],"player_name":["Brighton Player"]})
    result=enrich_players_with_fixtures(players,clubs_frame,fixtures,now="2026-08-19T00:00Z").iloc[0]
    assert result.canonical_club_id=="brighton_hove_albion" and result.opening_opponent=="Arsenal"
    assert result.opening_venue=="H" and result.next_five_fixture_ease_percentile==61

def test_team_page_preparation_isolated_and_complete():
    matches=canonicalize_matches(sample_matches(),clubs(),retrieved_at="now"); fixtures=build_team_fixtures(matches)
    assert len(directory_frame(clubs(),fixtures,now="2026-08-19T00:00Z"))==20
    assert len(fixture_frame(fixtures,"brighton_hove_albion"))==1
    players=pd.DataFrame({"premier_league_club":["BHA","ARS"],"player_name":["B","A"],"fantrax_position":["M","D"]})
    assert squad_frame(players,"BHA").Player.tolist()==["B"]

def test_complete_schedule_input_builds_380_matches_760_rows_and_38_per_club():
    registry=clubs(); rows=[]; match_id=0
    values=list(registry.itertuples(index=False))
    for i,home in enumerate(values):
        for away in values[i+1:]:
            for first,second in ((home,away),(away,home)):
                match_id+=1; rows.append({"match_id":match_id,"match_date":f"2026-08-{20+(match_id%8):02d}T12:00:00Z","status":"incomplete","game_week":1,
                    "home_team_id":first.football_data_team_id,"home_team":first.canonical_name,"away_team_id":second.football_data_team_id,"away_team":second.canonical_name,"home_score":0,"away_score":0})
    matches=canonicalize_matches(pd.DataFrame(rows),registry,retrieved_at="now"); fixtures=build_team_fixtures(matches)
    assert len(matches)==380 and len(fixtures)==760 and fixtures.groupby("club_id").size().eq(38).all()
    assert matches.match_id.is_unique and set(matches.home_club_id).union(matches.away_club_id)==set(registry.canonical_club_id)

def test_current_scoring_periods_are_valid_and_distinct_from_2526():
    periods=pd.DataFrame({"fantrax_gw":[1,2],"period_start":["2026-08-21T19:00Z","2026-08-28T19:00Z"],"period_end":["2026-08-28T18:59Z","2026-09-04T18:59Z"]})
    assert len(_validated_periods(periods))==2
    stale=periods.copy(); stale[["period_start","period_end"]]=stale[["period_start","period_end"]].replace("2026","2025",regex=True)
    import pytest
    with pytest.raises(ValueError,match="not for 2026/27"): _validated_periods(stale)

def test_unresolved_club_is_reported_without_guessing():
    assert resolve_club("Bright Town",clubs()) is None
