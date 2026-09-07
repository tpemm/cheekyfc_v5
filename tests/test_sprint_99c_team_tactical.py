from pathlib import Path
import json
import numpy as np
import pandas as pd
from streamlit.testing.v1 import AppTest

from analytics.teams.tactical import DEFAULT_METHODOLOGY_PATH,METHODOLOGY_VERSION,apply_dimensions,confidence_state,join_fantasy_allowed_tactical,join_player_opponent_context,load_methodology,spatial_match_features
from core.services.dataset_registry import DatasetRegistry

ROOT=Path(__file__).resolve().parents[1]
def read(key,season="2526"):return pd.read_csv(ROOT/f"data/models/season_{season}/{key}_{season}.csv",low_memory=False)

def test_match_product_grain_current_and_historical():
    h=read("team_tactical_match_features");c=read("team_tactical_match_features","2627")
    assert (len(h),h.canonical_match_id.nunique(),h.club_id.nunique())==(760,380,20)
    assert (len(c),c.canonical_match_id.nunique(),c.club_id.nunique())==(60,30,20)
    assert not h.duplicated(["canonical_match_id","club_id"]).any() and not c.duplicated(["canonical_match_id","club_id"]).any()
    assert h.opponent_id.notna().all() and c.opponent_id.notna().all()

def test_accepted_features_complete_and_semantically_distinct():
    d=read("team_tactical_match_features")
    fields=("crosses_per_match","cross_success_pct","take_ons_per_match","take_on_success_pct","final_third_entries_per_match","box_entries_per_match","final_third_event_share","box_event_share","wide_attacking_activity_share","central_creation_share","key_passes_per_match","shots_per_match","shots_on_target_per_match","xg_per_match","defensive_event_activity_depth","advanced_defensive_action_share","recoveries_per_match","aerials_per_match","aerial_win_pct")
    assert all(d[x].notna().all() for x in fields)
    assert d.wide_attacking_activity_share.between(0,100).all() and d.central_creation_share.between(0,100).all()
    assert not np.allclose(d.crosses_per_match,d.get("successful_crosses_per_match",-1))

def test_spatial_orientation_left_right_and_raw_immutability():
    raw=pd.DataFrame([{"canonical_match_id":"m","club_id":"a","event_type":"Pass","is_key_pass":True,"qualifiers":"[]","x":80.,"y":10.,"end_x":90.,"end_y":20.,"outcome":"Successful"},{"canonical_match_id":"m","club_id":"a","event_type":"Tackle","is_key_pass":False,"qualifiers":"[]","x":75.,"y":90.,"end_x":np.nan,"end_y":np.nan,"outcome":"Successful"}]);before=raw.copy(deep=True);out=spatial_match_features(raw)
    pd.testing.assert_frame_equal(raw,before);assert len(out)==1
    # y=10 is the right-side channel after 100-y; it remains wide, while x=80 stays advanced.
    assert out.iloc[0].wide_attacking_activity_share==100 and out.iloc[0].advanced_defensive_action_share==100

def test_methodology_config_thresholds_and_no_primary_archetype():
    m=load_methodology(DEFAULT_METHODOLOGY_PATH);assert m["methodology_version"]==METHODOLOGY_VERSION
    assert m["thresholds"]=={"high_percentile":80,"low_percentile":20} and all(t["minimum_sample"]==5 for t in m["traits"])
    assert len({t["dimension"] for t in m["traits"]})==10 and "primary_archetype" not in json.dumps(m)

def test_current_is_observation_only_and_history_established():
    h=read("team_tactical_profile");c=read("team_tactical_profile","2627");traits=[x for x in c if x.endswith("_trait")]
    assert h.matches.eq(38).all() and h.confidence.eq("Established").all()
    assert c.matches.eq(3).all() and c.confidence.eq("Emerging").all()
    assert all(c[x].eq("Observation only").all() for x in traits)
    assert all(~h[x].eq("Observation only").any() for x in traits)

def test_threshold_high_low_balanced_missing_and_zero():
    method={"methodology_version":"x","thresholds":{"high_percentile":80,"low_percentile":20},"traits":[{"dimension":"test","features":{"metric":1},"minimum_sample":5,"high_name":"High","balanced_name":"Balanced","low_name":"Low"}]}
    d=pd.DataFrame({"club_id":["a","b","c","d","e","f"],"matches":[10]*6,"metric":[0.,1.,2.,3.,4.,np.nan]});out=apply_dimensions(d,method)
    assert out.test_trait.tolist()==["Low","Balanced","Balanced","High","High","—"] and pd.notna(out.loc[0,"test_percentile"])
    assert confidence_state(1)=="Very Early" and confidence_state(3)=="Emerging" and confidence_state(5)=="Developing" and confidence_state(10)=="Established"

def test_manager_formation_and_venue_profiles_sample_gating():
    for key,column in (("team_manager_tactical_profile","manager_id"),("team_formation_tactical_profile","formation"),("team_venue_tactical_profile","home_away")):
        d=read(key);assert d.club_id.nunique()==20 and d[column].notna().all() and d.matches.gt(0).all()
        trait=next(c for c in d if c.endswith("_trait"));assert d.loc[d.matches.lt(5),trait].eq("Observation only").all()
    venue=read("team_venue_tactical_profile");assert set(venue.home_away)=={"H","A"}

def test_bournemouth_bridge_and_coventry_no_history():
    h=read("team_tactical_profile");c=read("team_tactical_profile","2627")
    assert len(h[h.club_id.eq("bournemouth")])==1 and len(c[c.club_id.eq("afc_bournemouth")])==1
    assert "coventry_city" not in set(h.club_id) and len(c[c.club_id.eq("coventry_city")])==1

def test_correlation_stability_and_sample_size_evidence():
    q=ROOT/"data/quality/season_2627";corr=pd.read_csv(q/"team_tactical_feature_correlation_99c.csv");stability=pd.read_csv(q/"team_tactical_stability_99c.csv");sample=pd.read_csv(q/"team_tactical_sample_size_99c.csv")
    redundant=corr[corr.redundant_candidate]
    assert ((redundant.feature_a.eq("key_passes_per_match")&redundant.feature_b.eq("shots_per_match"))|(redundant.feature_b.eq("key_passes_per_match")&redundant.feature_a.eq("shots_per_match"))).any()
    assert set(stability.stability_status)<={"STRONG","MODERATE","WEAK"} and stability.split_half_spearman.notna().all()
    assert set(sample.matches)=={1,3,5,8,10,15,19,38} and sample[sample.matches.eq(38)].spearman_to_full.eq(1).all()
    assert sample.groupby("matches").spearman_to_full.median().loc[1]<sample.groupby("matches").spearman_to_full.median().loc[10]

def test_opponent_player_and_fantasy_join_hooks():
    context=read("team_opponent_tactical_context");players=pd.read_csv(ROOT/"data/models/season_2627/current_player_match_log_2627.csv",low_memory=False);current=read("team_opponent_tactical_context","2627");joined=join_player_opponent_context(players,current)
    assert len(context)==760 and len(current)==60 and joined.filter(like="opponent_").notna().any().any()
    fantasy=pd.read_csv(ROOT/"data/models/season_2627/team_fantasy_allowed_match_2627.csv");fj=join_fantasy_allowed_tactical(fantasy,current);assert len(fj)==60 and fj.filter(like="opponent_").notna().any().any()

def test_registry_refresh_and_cache_only_contract():
    keys={x.key for x in DatasetRegistry().list_all()};assert {"team_tactical_match_features","team_tactical_profile","team_manager_tactical_profile","team_formation_tactical_profile","team_venue_tactical_profile","team_opponent_tactical_context"}<=keys
    source=(ROOT/"scripts/build_team_tactical_99c.py").read_text(encoding="utf-8");weekly=(ROOT/"scripts/weekly_commissioner_refresh.py").read_text(encoding="utf-8")
    assert "build_team_tactical_99c.py" in weekly and "tactical_methodology_version" in weekly
    assert all(x not in source for x in ("selenium","requests.","subprocess","http://","https://"))

def test_no_predictions_possession_directness_or_high_press_traits():
    for season in ("2526","2627"):
        d=read("team_tactical_profile",season);assert not d.contains_prediction.any();traits=d[[c for c in d if c.endswith("_trait")]].astype(str).stack()
        assert not traits.str.contains("High Press|Possession|Direct",case=False).any()
    inventory=pd.read_csv(ROOT/"data/quality/season_2627/team_tactical_methodology_99c.csv").set_index("feature")
    assert not inventory.loc[["possession_pct","forward_progressing_pass_rate","high_press"],"included"].any()

def test_teams_fingerprint_apptest_and_promoted_state():
    app=AppTest.from_file(str(ROOT/"app.py"),default_timeout=60).run();app.sidebar.radio(key="page_nav").set_value("Teams").run();assert not app.exception
    rendered=" ".join(x.value for x in app.markdown);assert "Tactical Fingerprint" in rendered and "team_tactical_v1" in " ".join(x.value for x in app.caption)
    tables=[x.value for x in app.dataframe if {"Season","Dimension","Trait","Percentile","Underlying Metric","Value","Confidence","Why","Caveat"}<=set(getattr(x.value,"columns",[]))];assert len(tables)>=2 and tables[0][tables[0].Season.eq("2026/27 Current")].Trait.eq("Observation only").all()
    selector=next(x for x in app.selectbox if x.label=="Club");selector.set_value("Coventry City").run();assert not app.exception
    tables=[x.value for x in app.dataframe if {"Season","Dimension","Trait"}<=set(getattr(x.value,"columns",[]))];assert all("2025/26 Reference" not in set(x.Season) for x in tables)
