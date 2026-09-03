from pathlib import Path
import pandas as pd

from fantrax.live.league_analytics import LIVE_TABLE_COLUMNS,player_leaderboards
from views.live_league_hub import HEADLINE_CARD_CSS,build_live_hub_model


SOURCE=Path("views/live_league_hub.py").read_text(encoding="utf-8")


def test_header_is_simple_and_clipping_offset_is_removed():
    assert 'page_header(ui,"League Hub",badge=' in SOURCE
    assert "League overview" not in SOURCE and "Live standings, form, scoring" not in SOURCE
    shell=Path("core/legacy_renderer.py").read_text(encoding="utf-8")
    assert "gap: 18px; margin: 0 0 1.4rem" in shell
    assert "margin: -1.25rem 0 1.4rem" not in shell


def test_exact_four_equal_headline_cards_and_compact_preseason_values():
    assert "min-height:112px;height:100%" in HEADLINE_CARD_CSS
    for label in ("Latest Jester","Jester Leader","Manager of the Month","Cup Status"):assert label in SOURCE
    assert SOURCE.count('with column:_headline(ui,*item)')==1
    assert SOURCE.count('"Not awarded yet"')>=3
    assert 'cup_value="Seeding"' in SOURCE
    assert 'Top {byes} get byes' in SOURCE and 'opening_round_week' in SOURCE
    assert "Live scoring, form, luck" not in SOURCE


def test_table_contract_is_unchanged():
    assert LIVE_TABLE_COLUMNS==("Rank","Team","Movement","Record","Form","Pts / GW","Ghost / GW","Efficiency","Lineup Changes")


def test_only_approved_highlights_are_presented():
    weeks=pd.DataFrame([{"period":1,"manager_id":"m1","manager_name":"A","fantasy_points":10,"rank_after_week":1},{"period":1,"manager_id":"m2","manager_name":"B","fantasy_points":5,"rank_after_week":2}])
    games=pd.DataFrame([{"period":1,"status":"completed","home_manager":"A","away_manager":"B","home_score":10,"away_score":5}])
    model=build_live_hub_model(pd.DataFrame(),pd.DataFrame(),games,weeks)
    assert {item[0] for item in model["highlights"]}=={"Highest Score","Lowest Score","Closest Match","Biggest Blowout"}


def test_player_leaderboards_are_top_three_and_completed_only():
    rows=[]
    for index in range(5):rows.append({"period":1,"period_complete":True,"player_name":f"P{index}","goals":index,"assists":4-index,"clean_sheets":index%2,"fantasy_points":index*10})
    rows.append({"period":2,"period_complete":False,"player_name":"Future","goals":99,"assists":99,"clean_sheets":99,"fantasy_points":999})
    boards=player_leaderboards(pd.DataFrame(rows))
    assert set(boards)=={"Golden Boot","Playmaker","Golden Glove","Highest Weekly Points"}
    assert all(frame.get("Rank",pd.Series([1])).max()<=3 for frame in boards.values())
    assert all("Future" not in frame.get("Player",pd.Series(dtype=str)).tolist() for frame in boards.values())


def test_final_hierarchy_and_removed_sections():
    rendered=SOURCE.split("def render(",1)[1]
    ordered=("League Table","League Highlights","Season Trends","Weekly Scoring","League Position History","Manager Awards","Golden Boot","Playmaker","Golden Glove","Ghost King")
    positions=[rendered.index(label) for label in ordered]
    assert positions==sorted(positions)
    for removed in ("Recent Roster Activity","Current Roster Projections","Strongest Current Position Groups","Available Players","Manager Cards"):assert removed not in rendered
