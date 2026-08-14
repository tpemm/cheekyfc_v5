import pandas as pd
import pytest
from analytics.cup.engine import build_tournament,create_seed_snapshot,matchup_state,tournament_schedule,validate_configuration

def config(): return {"season":"2627","tournament_name":"Cheeky FC Cup","enabled":True,"teams":12,"byes":4,"seeding_week":20,"opening_round_week":22,"quarterfinal_week":26,"semifinal_week":31,"championship_week":38,"reseed_after_round":True,"score_source":"manager_week_summary","tie_break_method":"fantasy_score_then_higher_seed"}
def standings(): return pd.DataFrame({"period":[20]*12,"manager_id":[f"m{i}" for i in range(1,13)],"manager_name":[f"Manager {i}" for i in range(1,13)],"rank":range(1,13),"points":range(120,108,-1),"fantasy_points_for":range(1200,1080,-10)})
def scores(weeks=(22,26,31,38)):
    rows=[]
    for week in weeks:
        for seed in range(1,13): rows.append({"period":week,"manager_id":f"m{seed}","total_score":200-seed})
    return pd.DataFrame(rows)

def test_configuration_and_schedule_are_driven_by_fields():
    validate_configuration(config()); schedule=tournament_schedule(config())
    assert schedule.week.tolist()==[20,22,26,31,38]
    bad=config(); bad["quarterfinal_week"]=21
    with pytest.raises(ValueError): validate_configuration(bad)

def test_seed_snapshot_freezes_rank_points_week_and_timestamp():
    snapshot=create_seed_snapshot(standings(),config(),timestamp="2026-12-01T00:00:00Z")
    assert snapshot.seed.tolist()==list(range(1,13)); assert snapshot.snapshot_week.nunique()==1
    changed=standings().assign(rank=list(reversed(range(1,13))))
    assert snapshot.seed.tolist()!=create_seed_snapshot(changed,config(),timestamp="later").seed.tolist() or snapshot.manager_id.tolist()!=create_seed_snapshot(changed,config(),timestamp="later").manager_id.tolist()

def test_opening_round_assigns_byes_and_seed_pairings():
    snapshot=create_seed_snapshot(standings(),config(),timestamp="now"); bracket=build_tournament(config(),snapshot,pd.DataFrame(),current_week=10)
    opening=bracket[bracket["round"].eq("Opening Round")]
    assert list(zip(opening.home_seed,opening.away_seed))==[(5,12),(6,11),(7,10),(8,9)]
    assert set(opening.home_seed)|set(opening.away_seed)==set(range(5,13)); assert opening.status.eq("Waiting for week").all()

def test_reseeding_progression_and_champion_path():
    snapshot=create_seed_snapshot(standings(),config(),timestamp="now"); bracket=build_tournament(config(),snapshot,scores(),current_week=38)
    assert bracket.groupby("round").size().to_dict()=={"Opening Round":4,"Quarterfinals":4,"Semifinals":2,"Championship":1}
    quarters=bracket[bracket["round"].eq("Quarterfinals")]
    assert list(zip(quarters.home_seed,quarters.away_seed))==[(1,8),(2,7),(3,6),(4,5)]
    championship=bracket[bracket["round"].eq("Championship")].iloc[0]
    assert championship.status=="Final" and championship.winner_seed==1 and championship.winner_path=="Champion"
    assert bracket[bracket["round"].eq("Opening Round")].next_matchup_id.ne("").all()

def test_states_and_higher_seed_tiebreak():
    assert matchup_state(22,21,0)=="Waiting for week"; assert matchup_state(22,22,0)=="Live"; assert matchup_state(22,22,2)=="Final"
    tied=scores((22,)); tied["total_score"]=100
    bracket=build_tournament(config(),create_seed_snapshot(standings(),config(),timestamp="now"),tied,current_week=22)
    assert bracket.iloc[0].winner_seed==5

def test_preseason_has_no_projected_bracket_without_snapshot():
    assert build_tournament(config(),pd.DataFrame(),pd.DataFrame(),current_week=None).empty
