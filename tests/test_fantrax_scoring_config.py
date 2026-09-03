import pytest

from fantrax.analytics.core.fantrax_scoring import get_rule, load_scoring_config, score_stat

def test_season_specific_config_loading_and_missing_season():
    assert load_scoring_config("2627")["season"] == "2627"
    with pytest.raises(KeyError): load_scoring_config("2728")

@pytest.mark.parametrize("goals,expected",[(1,9),(2,18),(3,30),(4,42)])
def test_default_outfield_cumulative_goal_rule(goals,expected):
    assert score_stat("2627","MID","G",goals)==expected

@pytest.mark.parametrize("position,stat,value,expected",[
    ("GK","Sv",3,6),("FWD","KP",2,4),("DEF","AER",4,4),("FWD","AER",4,2),
    ("DEF","AT",1,7),("MID","AT",1,6),("MID","CS",1,1),("FWD","CS",1,0),
])
def test_flat_and_override_resolution(position,stat,value,expected):
    assert score_stat("2627",position,stat,value)==expected

@pytest.mark.parametrize("position",["GK","DEF"])
@pytest.mark.parametrize("against,expected",[(1,0),(2,-2),(3,-4)])
def test_goals_against_cumulative_rule(position,against,expected):
    assert score_stat("2627",position,"GA",against)==expected

def test_missing_rule_fails_loudly():
    with pytest.raises(KeyError): get_rule("2627","MID","NOT_A_STAT")

def test_defender_goal_override_was_not_invented():
    assert score_stat("2627","DEF","G",1)==9
