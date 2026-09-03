from pathlib import Path

import pandas as pd

from fantrax.live.current_identity import deterministic_candidates, display_names
from fantrax.live.current_integrity import correction_diff, metric_validation
from fantrax.live.unified_weekly import build_unified_weekly
from fantrax.live.analytics import build_live_player_analytics


def test_display_name_never_overwritten_by_null_provider():
    got=display_names(pd.Series(["Mamadou Sangaré"]),pd.Series(["Mamadou Sangare"]),pd.Series([pd.NA]))
    assert got.iat[0]=="Mamadou Sangaré"


def test_display_name_falls_back_to_fantrax():
    assert display_names(pd.Series([pd.NA]),pd.Series(["Mamadou Sangare"])).iat[0]=="Mamadou Sangare"


def test_repaired_ownership_name_propagates_over_blank_preseason_pool():
    pool=pd.DataFrame({"fantrax_player_id":["07877"],"player_name":[pd.NA]})
    own=pd.DataFrame({"fantrax_player_id":["07877"],"player_name":["Mamadou Sangare"],"canonical_name":["Mamadou Sangaré"],"registry_player_id":["FTX-07877"]})
    got=build_live_player_analytics(pool,own,pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),pd.DataFrame())
    assert got.player_name.iat[0]=="Mamadou Sangaré"


def test_diacritic_name_and_club_is_deterministic():
    provider=pd.DataFrame({"provider_id":[442971],"provider_name":["Mamadou Sangaré"],"club_id":["brentford"]})
    current=pd.DataFrame({"fantrax_player_id":["07877"],"fantrax_name":["Mamadou Sangare"],"club_id":["brentford"]})
    assert deterministic_candidates(provider,current).identity_status.iat[0]=="DETERMINISTIC"


def test_ambiguous_identity_is_not_deterministic():
    provider=pd.DataFrame({"provider_id":[1],"provider_name":["John Smith"],"club_id":["x"]})
    current=pd.DataFrame({"fantrax_player_id":["a","b"],"fantrax_name":["John Smith","John Smith"],"club_id":["x","x"]})
    assert set(deterministic_candidates(provider,current).identity_status)=={"AMBIGUOUS"}


def test_correction_diff_detects_points_and_components():
    old=pd.DataFrame({"fantrax_player_id":["p"],"Player":["P"],"manager_id":["m"],"Status":["Active"],"Fantasy Points":[5],"KP":[1]})
    new=old.copy();new.loc[0,["Fantasy Points","KP"]]=[7,2]
    got=correction_diff(old,new,previous_snapshot="a",new_snapshot="b",period=1)
    assert set(got.metric)=={"Fantasy Points","KP"};assert set(got.delta)=={1,2}


def test_fantasy_assist_is_source_specific():
    policy=metric_validation(pd.DataFrame(),pd.DataFrame()).set_index("metric")
    assert policy.at["fantasy_assists","classification"]=="SOURCE_SPECIFIC"
    assert not policy.at["fantasy_assists","approved_for_waiver_supplement"]


def _unified(fan_value, ws_value, *, ws_matches=1, rostered=False):
    fan=pd.DataFrame({"fantrax_player_id":["p"],"period":[1],"player_name":["P"],"canonical_name":[pd.NA],"fantasy_points":[0],"key_passes":[fan_value],"key_passes_source":["fantrax_weekly" if rostered else "understat"],"aerials_won":[pd.NA],"interceptions":[pd.NA],"club":["X"],"current_manager_id":["m" if rostered else pd.NA]})
    adv=pd.DataFrame({"canonical_player_id":["c"]*ws_matches,"fantrax_period":[1]*ws_matches,"canonical_match_id":["m"]*ws_matches,"key_passes":[ws_value]*ws_matches,"aerial_wins":[0]*ws_matches,"interceptions":[0]*ws_matches,"club_id":["x"]*ws_matches,"opponent_id":["y"]*ws_matches,"actual_tactical_role":["CM"]*ws_matches,"formation":["4-3-3"]*ws_matches,"manager_name":["M"]*ws_matches}) if ws_matches else pd.DataFrame()
    identity=pd.DataFrame({"canonical_player_id":["c"],"fantrax_player_id":["p"]})
    clubs=pd.DataFrame({"fantrax_code":["X"],"canonical_club_id":["x"]})
    return build_unified_weekly(fan,adv,pd.DataFrame(),identity,pd.DataFrame(),clubs)


def test_safe_metric_supplements_waiver_and_preserves_observed_zero():
    got=_unified(pd.NA,0)
    assert got.key_passes.iat[0]==0 and got.key_passes_source.iat[0]=="WHOSCORED_DERIVED_VALIDATED"


def test_fantrax_explicit_zero_beats_supplement():
    got=_unified(0,4,rostered=True)
    assert got.key_passes.iat[0]==0 and got.key_passes_source.iat[0]=="FANTRAX_DETAILED"


def test_missing_observation_remains_missing():
    got=_unified(pd.NA,0,ws_matches=0)
    assert pd.isna(got.key_passes.iat[0]) and not got.whoscored_available.iat[0]


def test_all_promoted_semantics_fill_only_observed_waiver_missingness():
    fan=pd.DataFrame({"fantrax_player_id":["p"],"period":[1],"player_name":["P"],"fantasy_points":[4],"goals":[pd.NA],"key_passes":[pd.NA],"tackles_won":[pd.NA],"interceptions":[pd.NA],"aerials_won":[pd.NA],"accurate_crosses":[pd.NA],"club":["X"]})
    adv=pd.DataFrame({"canonical_player_id":["c"],"fantrax_period":[1],"canonical_match_id":["m"],"goals":[1],"key_passes":[2],"tackles_won_derived":[3],"interceptions":[4],"aerial_wins":[5],"accurate_crosses_derived":[6],"actual_tactical_role":["CM"],"formation":["4-3-3"],"manager_name":["M"],"club_id":["x"],"opponent_id":["y"]})
    identity=pd.DataFrame({"canonical_player_id":["c"],"fantrax_player_id":["p"]});clubs=pd.DataFrame({"fantrax_code":["X"],"canonical_club_id":["x"]})
    got=build_unified_weekly(fan,adv,pd.DataFrame(),identity,pd.DataFrame(),clubs).iloc[0]
    assert [got[x] for x in ("goals","key_passes","tackles_won","interceptions","aerials_won","accurate_crosses")]==[1,2,3,4,5,6]
    assert got.fantasy_points==4
