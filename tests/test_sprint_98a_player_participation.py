from pathlib import Path

import pandas as pd
import pytest

from fantrax.live.player_participation import add_canonical_rates

ROOT=Path(__file__).resolve().parents[1]
MODEL=ROOT/"data/models/season_2627"
QUALITY=ROOT/"data/quality/season_2627"


@pytest.mark.parametrize("metric,total,games,starts,minutes,basis,expected",[
    (metric,total,games,starts,minutes,basis,expected)
    for metric,total,games,starts,minutes in (("points",12,1,1,90),("ghost",8,2,1,120),("xgi",.9,3,2,180))
    for basis,expected in (("per_game",total/games),("per_start",total/starts),("per_90",total/minutes*90))
    for _ in range(4)
])
def test_shared_rate_denominators(metric,total,games,starts,minutes,basis,expected):
    result=add_canonical_rates(pd.DataFrame([{metric:total,"games_played":games,"starts":starts,"minutes":minutes}]),(metric,))
    assert result.loc[0,f"{metric}_{basis}"]==pytest.approx(expected)


def test_zero_denominators_stay_missing():
    result=add_canonical_rates(pd.DataFrame([{"points":10,"games_played":0,"starts":0,"minutes":0}]),("points",))
    assert result.filter(regex="points_per").isna().all(axis=None)


def participation(): return pd.read_csv(MODEL/"player_match_participation_2627.csv")


def test_three_gameweeks_preserve_explicit_starters(): assert participation().started.sum()==658
def test_match_starter_counts_report_provider_exceptions(): assert participation()[lambda x:x.started].groupby("canonical_match_id").size().value_counts().to_dict()=={22:28,21:2}
def test_club_match_starter_counts_report_provider_exceptions(): assert participation()[lambda x:x.started].groupby(["canonical_match_id","club_id"]).size().value_counts().to_dict()=={11:58,10:2}
def test_forest_mapping_exceptions_preserve_provider_explicit_starters():
    import json
    manifest=pd.read_csv(ROOT/"data/reference/whoscored_season_manifest_2627.csv")
    p=participation()
    groups=p[p.started].groupby(["canonical_match_id","club_id"]).size()
    exceptions=groups[groups.ne(11)]
    assert set(exceptions.index)=={("soccerdata:sofascore:16363254","nottingham_forest"),("soccerdata:sofascore:16363638","nottingham_forest")}
    for match,club in exceptions.index:
        row=manifest[manifest.canonical_match_id.eq(match)].iloc[0]
        raw=json.loads((ROOT/f"data/raw/whoscored/2627/poc/match_{int(row.whoscored_match_id)}/raw_match.json").read_text())
        side="home" if row.home_club_id==club else "away"
        assert sum(player.get("isFirstEleven") is True for player in raw[side]["players"])==11
        lineups=pd.read_csv(MODEL/"advanced/whoscored_lineup_2627.csv")
        unresolved=lineups[lineups.canonical_match_id.eq(match)&lineups.club_id.eq(club)&lineups.started&lineups.canonical_player_id.isna()]
        assert unresolved.whoscored_player_name.tolist()==["Xaver Schlager"]


def test_no_duplicate_player_match(): assert not participation().duplicated(["canonical_match_id","canonical_player_id"]).any()
def test_appearance_is_start_or_sub_on():
    p=participation(); assert p.appeared.eq(p.started|p.substitute_used).all()
def test_unused_substitutes_are_not_appearances():
    p=participation(); assert not p.loc[p.unused_substitute,"appeared"].any()
def test_observed_minutes_are_nonnegative_and_complete():
    p=participation(); minutes=pd.to_numeric(p.loc[p.appeared,"minutes"],errors="coerce")
    assert minutes.notna().all() and minutes.ge(0).all()
def test_janelt_canary_is_fixed():
    s=pd.read_csv(MODEL/"current_player_season_summary_2627.csv");j=s[s.player_name.str.contains("Janelt",case=False,na=False)].iloc[0]
    assert (j.games_played,j.starts,j.minutes)==(3,3,270)
    assert j.fantasy_points_per_start==j.fantasy_points/3
def test_current_summary_has_complete_player_pool():
    s=pd.read_csv(MODEL/"current_player_season_summary_2627.csv");w=pd.read_csv(MODEL/"current_player_weekly_2627.csv")
    assert set(s.fantrax_player_id.astype(str))==set(w.fantrax_player_id.astype(str))
    assert not s.fantrax_player_id.duplicated().any()
    latest=int(w.period.max())
    raw=pd.read_csv(ROOT/f"data/raw/fantrax/2627/player_stats/period_{latest:02d}/all_players.csv",dtype=str)
    assert set(w.loc[w.period.eq(latest),"fantrax_player_id"].astype(str))==set(raw.ID.str.strip("*"))
def test_clean_sheet_reconciliation_is_exact():
    q=pd.read_csv(QUALITY/"clean_sheet_reconciliation_gw1_2627.csv"); comparable=q[q.weekly_clean_sheets.notna()]
    assert len(comparable)>=150 and comparable.exact_agreement.all()
def test_ghost_fallback_is_explicitly_partial():
    log=pd.read_csv(MODEL/"current_player_match_log_2627.csv"); waiver=log[log.current_manager_id.isna()]
    assert waiver.ghost_points_source.str.startswith("DERIVED_FROM_RETURNS").all()
    assert waiver.ghost_component_coverage.eq(1).all()
def test_match_log_is_one_row_per_observed_player_match():
    log=pd.read_csv(MODEL/"current_player_match_log_2627.csv")
    assert not log.duplicated(["canonical_match_id","canonical_player_id"]).any()
    assert len(log)==919
