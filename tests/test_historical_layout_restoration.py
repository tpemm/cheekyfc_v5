import pandas as pd
import plotly.graph_objects as go
from components.charts import position_rank_axis
from views.league_hub import historical_chart_frames,historical_highlights

def weekly():
    return pd.DataFrame({"fantrax_gw":[1,1,2,2],"api_team_name":["Alpha","Beta","Alpha","Beta"],"starter_fantasy_points":[100,90,80,110],"computed_result":["W","L","L","W"],"opponent_team_name":["Beta","Alpha","Beta","Alpha"]})

def test_historical_weekly_scoring_and_position_values_are_retained():
    scoring,position=historical_chart_frames(weekly())
    assert scoring.loc[1,"Alpha"]==100 and scoring.loc[2,"Beta"]==110
    assert position.loc[1,"Alpha"]==1 and position.loc[2,"Alpha"] in (1,2)

def test_historical_highlights_keep_scores_streaks_and_records():
    streaks=pd.DataFrame({"api_team_name":["Alpha","Beta"],"longest_win_streak":[3,1],"longest_losing_streak":[1,4]})
    games=weekly().assign(abs_margin=[10,10,30,30])
    labels=[item[0] for item in historical_highlights(weekly(),streaks,games,games)]
    assert labels==["Highest Weekly Score","Lowest Weekly Score","Hottest Manager","Coldest Manager","Closest Match","Biggest Blowout"]

def test_rank_axis_remains_reversed():
    figure=position_rank_axis(go.Figure())
    assert figure.layout.yaxis.autorange=="reversed"

def test_archive_and_manager_source_protect_restored_hierarchy():
    archive=open("views/league_hub.py",encoding="utf-8").read(); managers=open("views/managers.py",encoding="utf-8").read()
    for label in ("Final League Table","League Highlights","Weekly Scoring","League-Position History","Season Awards"):
        assert label in archive
    assert '["Overview", "Performance", "Squad", "Decisions", "Explorer"]' in managers
    for label in ("Actual XI vs Optimal XI","Season Momentum","Formation","Squad","Explorer"):
        assert label in managers

def test_approved_hub_order_and_three_summary_cards_are_protected():
    source=open("views/league_hub.py",encoding="utf-8").read()
    summary=source.index('summary_items = ['); table=source.index('Final League Table'); awards=source.index('Season Awards</div>',table); charts=source.index('Season Trends',awards)
    assert summary<table<awards<charts
    assert all(label in source[summary:table] for label in ("Next Gameweek","Manager of the Month","Latest Jester"))
    assert "Archive contents" not in source

def test_table_columns_award_grid_and_clean_form_markers_are_protected():
    source=open("views/league_hub.py",encoding="utf-8").read()
    for column in ("Rank","Team","Move","Record","Form","Points / GW","Ghost / GW","Efficiency","Lineup Changes"):
        assert f'"{column}"' in source
    for award in ("Golden Boot","Playmaker","Golden Glove","Jester","Biggest Blowout","Closest Game","Longest Win Streak","Longest Losing Streak"):
        assert award in source
    assert all(marker in source for marker in ("\\U0001f7e2","\\U0001f534","\\U0001f7e1","\\u25b2","\\u25bc"))
