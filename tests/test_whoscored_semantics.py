import pandas as pd
from fantrax.live.whoscored_semantics import observed_event_counts,safe_fantasy_assist_delta,preceding_goal_events

def _events():
    return pd.DataFrame({"canonical_match_id":["m"]*8,"canonical_player_id":["p"]*8,"club_id":["c"]*8,"event_id":[str(x) for x in range(8)],"provider_sequence_event_id":range(8),"expanded_minute":[1,2,3,4,5,6,7,8],"second":[0]*8,"event_type":["Pass","Pass","Goal","SavedShot","MissedShots","ShotOnPost","Tackle","Tackle"],"outcome":["Successful","Unsuccessful","Successful","Successful","Unsuccessful","Unsuccessful","Successful","Unsuccessful"],"qualifiers":['[{"type":{"displayName":"Cross"}}]','[{"type":{"displayName":"Cross"}}]','[]','[{"type":{"displayName":"Blocked"}}]','[]','[]','[]','[]'],"is_assist":[False]*8})

def test_cross_partition_and_explicit_zero():
    got=observed_event_counts(_events()).iloc[0]
    assert got.ws_cross_attempts==got.ws_cross_successful+got.ws_cross_unsuccessful==2

def test_missing_cross_observation_is_not_manufactured():
    assert observed_event_counts(pd.DataFrame(columns=_events().columns)).empty

def test_sot_excludes_blocked_saved_shot_and_post_but_includes_goal():
    got=observed_event_counts(_events()).iloc[0]
    assert got.ws_sot_goal_saved_unblockeds==1

def test_tackle_attempts_and_successes_are_distinct_and_zero_preserved():
    got=observed_event_counts(_events()).iloc[0]
    assert got.ws_tackle_attempts==2 and got.ws_tackle_successful==1

def test_fantasy_assist_negative_delta_is_invalid_not_zero():
    got=safe_fantasy_assist_delta(pd.Series([0,1]),pd.Series([1,0]))
    assert pd.isna(got.iat[0]) and got.iat[1]==1

def test_event_sequence_links_next_goal_in_same_match_and_team():
    e=_events();candidate=e.iloc[[0]]
    got=preceding_goal_events(e,candidate)
    assert got.goal_event_id.iat[0]=="2"
