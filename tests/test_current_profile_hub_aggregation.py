from pathlib import Path
import pandas as pd
import pytest
from fantrax.live.player_participation import starter_observation_rates
from analytics.players.research_overview import overlay_current_summary
from fantrax.live.league_lineups import manager_performance_weeks, optimal_legal_xi, ACTIVE_STATUSES
from fantrax.live.league_analytics import compact_league_table, completed_manager_weeks
from views.live_league_hub import build_live_hub_model, movement_style, form_presentation, style_league_table

ROOT=Path(__file__).resolve().parents[1]
def read(name):return pd.read_csv(ROOT/f"data/models/season_2627/{name}_2627.csv",low_memory=False)


def test_cherki_starter_only_numerators_and_bruno_all_starts():
    summary=read("current_player_season_summary");log=read("current_player_match_log")
    fixed=starter_observation_rates(summary,log).set_index("fantrax_player_id")
    cherki=fixed.loc["06v07"]
    assert (cherki.games_played,cherki.starts)==(3,2)
    assert cherki.fantasy_points==60.5
    assert cherki.fantasy_points_per_start==19.75 and cherki.ghost_points_per_start==10.25
    assert cherki.fantasy_points_per_game==summary.set_index("fantrax_player_id").loc["06v07","fantasy_points_per_game"]
    assert cherki.fantasy_points_per_90==summary.set_index("fantrax_player_id").loc["06v07","fantasy_points_per_90"]
    bruno=fixed.loc["05gcr"];assert (bruno.games_played,bruno.starts)==(3,3)
    assert bruno.fantasy_points_per_start==pytest.approx(bruno.fantasy_points/3)
    assert bruno.ghost_points_per_start==pytest.approx(bruno.ghost_points/3)
    display=overlay_current_summary(read("live_player_analytics"),summary,log).set_index("fantrax_player_id")
    assert display.loc["06v07","current_points_per_start"]==19.75
    assert display.loc["06v07","current_ghost_per_start"]==10.25


def test_every_per_start_metric_excludes_subs_and_missing_stays_missing():
    summary=pd.DataFrame([dict(fantrax_player_id="p",points_per_start=100,minutes_per_start=100,key_passes_per_start=100)])
    log=pd.DataFrame([dict(fantrax_player_id="p",started=False,points=100,minutes=80,key_passes=100),dict(fantrax_player_id="p",started=True,points=6,minutes=50,key_passes=2),dict(fantrax_player_id="p",started=True,points=10,minutes=60,key_passes=None)])
    result=starter_observation_rates(summary,log).iloc[0]
    assert result.points_per_start==8 and result.minutes_per_start==55
    assert pd.isna(result.key_passes_per_start)
    assert starter_observation_rates(summary,log[~log.started]).filter(like="_per_start").isna().all().all()


def test_hub_uses_existing_active_lineup_efficiency_and_transition_products():
    weekly=read("current_player_weekly");weeks=read("manager_week_summary")
    result=manager_performance_weeks(weeks,weekly)
    model=build_live_hub_model(read("league_teams"),read("league_standings"),read("weekly_matchups"),result)
    table=compact_league_table(model["summary"],result)
    assert len(table)==12 and table[["Ghost / GW","Efficiency","Lineup Changes"]].notna().all().all()
    included=completed_manager_weeks(result)
    for manager_id,own in included.groupby("manager_id"):
        own=own.sort_values("period");active_sets=[]
        for item in own.itertuples():
            roster=weekly[weekly.current_manager_id.eq(manager_id)&weekly.period.eq(item.period)]
            active=roster[roster.lineup_status.str.upper().isin(ACTIVE_STATUSES)]
            assert item.ghost_points==pytest.approx(active.ghost_points.sum())
            optimal,_=optimal_legal_xi(roster)
            assert item.optimal_xi_points==optimal
            assert item.lineup_efficiency_pct==pytest.approx(100*active.fantasy_points.sum()/optimal)
            active_sets.append(set(active.fantrax_player_id))
        assert pd.isna(own.iloc[0].lineup_changes)
        assert own.lineup_changes.iloc[1:].tolist()==[len(b-a) for a,b in zip(active_sets,active_sets[1:])]
        summary=model["summary"][model["summary"].manager_id.eq(manager_id)]
        row=compact_league_table(summary,result).iloc[0]
        assert row["Ghost / GW"]==pytest.approx(own.ghost_points.sum()/own.period.nunique())
        assert row["Efficiency"]==pytest.approx(own.lineup_efficiency_pct.mean())
        assert row["Lineup Changes"]==own.lineup_changes.iloc[1:].sum()


def test_movement_and_form_colors_preserve_letters_and_neutral():
    assert "#16a34a" in movement_style("\u25b22")
    assert "#dc2626" in movement_style("\u25bc1")
    assert movement_style("\u2014")=="" and movement_style("0")==""
    assert form_presentation("W L D")=="\U0001f7e2 W \U0001f534 L \U0001f7e1 D"
    table=pd.DataFrame({"Movement":["\u25b22"],"Form":["W L"]})
    shown=style_league_table(table)
    assert shown.data.Movement.iloc[0]=="\u25b22" and table.Form.iloc[0]=="W L"
