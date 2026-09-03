import numpy as np
import pandas as pd
import pytest

from analytics.players.advanced import (
    aggregate_advanced, current_historical_comparison, fantasy_contributions,
    fantasy_reconciliation, metric_group_frame, metric_value,
    overlay_fantrax_authority, positional_context, return_points, safe_rate,
)


def observations():
    return pd.DataFrame([
        {"canonical_match_id":"m1","canonical_player_id":"p","started":True,"minutes":60,"fantrax_points":10,"ghost_points":6,"goals":1,"assists":0,"key_passes":2,"shots":2,"shots_on_target":1,"passes_attempted":20,"passes_completed":15,"cross_attempts":4,"accurate_crosses":2,"dribbles_attempted":2,"successful_dribbles":0,"tackles":3,"tackles_won":2,"interceptions":1,"clearances":2,"recoveries":4,"aerial_attempts":2,"aerial_wins":1,"rating":7},
        {"canonical_match_id":"m2","canonical_player_id":"p","started":True,"minutes":30,"fantrax_points":5,"ghost_points":3.5,"goals":0,"assists":0,"key_passes":1,"shots":0,"shots_on_target":0,"passes_attempted":10,"passes_completed":10,"cross_attempts":0,"accurate_crosses":0,"dribbles_attempted":0,"successful_dribbles":0,"tackles":1,"tackles_won":1,"interceptions":0,"clearances":0,"recoveries":1,"aerial_attempts":0,"aerial_wins":0,"rating":6},
    ])


def test_shared_total_per_start_and_per90_rate_basis():
    p=aggregate_advanced(observations())
    assert metric_value(p,"key_passes","Total")==3
    assert metric_value(p,"key_passes","Per Start")==1.5
    assert metric_value(p,"key_passes","Per 90")==3


def test_percentages_and_rating_are_not_rate_transformed():
    p=aggregate_advanced(observations())
    assert metric_value(p,"pass_completion_pct","Per 90")==pytest.approx(83.3333)
    assert metric_value(p,"rating","Per Start")==6.5


def test_missing_per90_and_success_rate_denominator_semantics():
    p=pd.Series({"key_passes":3,"minutes":np.nan,"starts":1,"dribble_success_pct":0})
    assert pd.isna(metric_value(p,"key_passes","Per 90"))
    assert safe_rate(0,2,100)==0
    assert pd.isna(safe_rate(0,0,100))


def test_fantrax_overlay_preserves_explicit_zero_and_waiver_fallback():
    supp=pd.DataFrame([{"canonical_match_id":"m1","canonical_player_id":"p","successful_dribbles":2},{"canonical_match_id":"m2","canonical_player_id":"q","successful_dribbles":3}])
    fan=pd.DataFrame([{"canonical_match_id":"m1","canonical_player_id":"p","successful_dribbles":0}])
    out=overlay_fantrax_authority(supp,fan)
    assert out.loc[out.canonical_player_id.eq("p"),"successful_dribbles"].iat[0]==0
    assert out.loc[out.canonical_player_id.eq("q"),"successful_dribbles"].iat[0]==3


def test_central_scoring_config_drives_contributions_and_return_points():
    p=pd.Series({"goals":1,"assists":1,"clean_sheets":1,"key_passes":3,"shots_on_target":2,"accurate_crosses":1,"aerial_wins":4})
    table=fantasy_contributions(p,"D").set_index("Code")
    assert table.loc["KP","Fantasy Contribution"]==6
    assert table.loc["SOT","Fantasy Contribution"]==4
    assert table.loc["AC","Fantasy Contribution"]==1
    assert table.loc["AER","Fantasy Contribution"]==4
    assert return_points(p,"D")==22  # 9 goal + 7 assist + 6 clean sheet


def test_reconciliation_exposes_difference_without_overwriting_official_fpts():
    p=pd.Series({"fantrax_points":14.5,"key_passes":2})
    contribution=fantasy_contributions(p,"M")
    result=fantasy_reconciliation(p,contribution)
    assert result=={"official_fpts":14.5,"known_component_contribution":4.0,"unreconciled_difference":10.5}


def test_all_advanced_groups_prepare_without_match_or_pitch_rows():
    p=aggregate_advanced(observations())
    for group in ("Fantasy Production","Chance Creation","Shooting / Threat","Passing / Progression","Dribbling","Defensive Activity","Aerials"):
        assert not metric_group_frame(p,group,"Per Start").empty


def test_positional_context_and_current_history_missing_delta():
    players=pd.DataFrame({"fantrax_player_id":["p","q","g"],"fantrax_position":["D","D","G"],"current_points_per_start":[10,6,20]})
    context=positional_context(players,"p","D",(("FPts / Start","current_points_per_start"),))
    assert context.iloc[0]["Position Average"]==8 and context.iloc[0]["Peers"]==2
    comparison=current_historical_comparison(pd.Series({"now":3}),pd.Series(),(("Metric","now","then"),))
    assert pd.isna(comparison.iloc[0]["Historical"]) and pd.isna(comparison.iloc[0]["Difference"])


def test_advanced_ui_has_no_pitch_or_match_log_duplication():
    source=open("views/players.py",encoding="utf-8").read();start=source.index("def _advanced_history");end=source.index("def _pitch_history")
    advanced=source[start:end]
    assert "draw_pitch" not in advanced
    assert "Observed Match Detail" not in advanced
    assert "Fantasy Component Analysis" in advanced and "Positional / League Context" in advanced


def test_historical_advanced_can_skip_pitch_loading():
    source=open("core/services/historical_advanced.py",encoding="utf-8").read()
    assert "include_pitch:bool=True" in source and "if include_pitch else pd.DataFrame()" in source
