from pathlib import Path
import pandas as pd
from analytics.teams.fixtures import build_team_fixtures,load_clubs,map_fantrax_periods
from analytics.teams.soccerdata import normalize_clubelo_current,normalize_clubelo_history,normalize_soccerdata_schedule,next_five_elo_context,schedule_quality,select_primary_schedule
from views.teams import team_elo_context

ROOT=Path(__file__).resolve().parents[1]
def clubs(): return load_clubs(ROOT/"data/reference/premier_league_clubs_2627.csv")
def sofa(): return pd.read_csv(ROOT/"data/raw/soccerdata/coverage_2627/sofascore/sofascore__read_schedule.csv")

def test_cached_sofascore_normalization_is_complete_stable_and_oriented():
    matches=normalize_soccerdata_schedule(sofa(),clubs(),retrieved_at="cached"); quality=schedule_quality(matches,clubs())
    assert quality=={"unique_matches":380,"club_count":20,"unresolved_clubs":0,"duplicate_matches":0,"all_dates":True,"all_38":True,"complete_380":True}
    assert matches.match_id.is_unique and matches.match_id.str.startswith("soccerdata:sofascore:").all()
    fixtures=build_team_fixtures(matches); assert len(fixtures)==760 and fixtures.groupby("club_id").size().eq(38).all()
    first=fixtures[fixtures.match_id.eq(matches.iloc[0].match_id)]; assert set(first.home_away)=={"H","A"}

def test_duplicate_provider_ids_are_deduplicated():
    raw=pd.concat([sofa().head(1),sofa().head(1)],ignore_index=True)
    assert len(normalize_soccerdata_schedule(raw,clubs(),retrieved_at="cached"))==1

def test_complete_primary_precedes_partial_fallback():
    complete=normalize_soccerdata_schedule(sofa(),clubs(),retrieved_at="cached"); partial=complete.head(170)
    name,selected=select_primary_schedule({"football-data.io":partial,"Sofascore":complete},clubs())
    assert name=="Sofascore" and len(selected)==380

def test_clubelo_normalization_maps_explicitly_and_ranks_pl_only():
    registry=clubs(); names={row.canonical_club_id:f"ClubElo {i}" for i,row in enumerate(registry.itertuples(),1)}
    raw=pd.DataFrame({"team":list(names.values())+["Outside"],"elo":list(range(1501,1521))+[2200],"country":["ENG"]*21})
    current,unresolved=normalize_clubelo_current(raw,registry,names,retrieved_at="now")
    assert len(current)==20 and current.elo_rank_pl.tolist()==list(range(1,21))
    assert unresolved.provider_name.tolist()==["Outside"] and current.iloc[0].elo==1520

def test_clubelo_missing_names_do_not_fuzzy_match():
    current,unresolved=normalize_clubelo_current(pd.DataFrame({"team":["Bright Town"],"elo":[1500]}),clubs(),{"brighton_hove_albion":"Brighton"},retrieved_at="now")
    assert current.empty and len(unresolved)==1

def test_clubelo_history_is_ordered_and_deduplicated():
    raw=pd.DataFrame({"from":["2026-02-01","2026-01-01","2026-01-01"],"elo":[1502,1500,1501]})
    result=normalize_clubelo_history(raw,"arsenal",retrieved_at="now")
    assert result.date.is_monotonic_increasing and result.elo.tolist()==[1501,1502]

def test_next_five_and_team_overview_use_raw_elo_context():
    matches=normalize_soccerdata_schedule(sofa(),clubs(),retrieved_at="cached"); fixtures=build_team_fixtures(matches)
    elo=pd.DataFrame({"canonical_club_id":clubs().canonical_club_id,"elo":range(1500,1520),"elo_rank_pl":range(20,0,-1)})
    context=next_five_elo_context(fixtures,elo,"brighton_hove_albion",now="2026-08-19T00:00Z")
    overview=team_elo_context("brighton_hove_albion",fixtures,elo,now="2026-08-19T00:00Z")
    assert len(context)==5 and context.opponent_elo.notna().all(); assert pd.notna(overview["next_opponent_elo_difference"])

def test_all_cached_matches_map_to_current_fantrax_windows():
    matches=normalize_soccerdata_schedule(sofa(),clubs(),retrieved_at="cached")
    periods=pd.read_csv(ROOT/"data/reference/fantrax_scoring_periods_2627.csv")
    assert map_fantrax_periods(matches,periods).fantrax_period.notna().all()
