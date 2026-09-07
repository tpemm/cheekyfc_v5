from pathlib import Path
import re

import pandas as pd
from pandas.testing import assert_frame_equal
from streamlit.testing.v1 import AppTest

from fantrax.live.league_analytics import league_highlights, format_movement
from views.live_league_hub import form_presentation, league_table_html, movement_style, TABLE_HELP, TABLE_WIDTHS


def test_season_records_and_latest_week_awards_have_distinct_scopes():
    weeks=pd.DataFrame([
        {"period":2,"manager":"tpem","total_score":167.5,"result":"W"},
        {"period":3,"manager":"KindComet","total_score":139.,"result":"W"},
        {"period":4,"manager":"Provisional","total_score":999.,"result":None},
    ])
    games=pd.DataFrame([
        {"period":1,"home_manager":"A","away_manager":"B","home_score":91.5,"away_score":91.,"status":"completed"},
        {"period":2,"home_manager":"tpem","away_manager":"B","home_score":167.5,"away_score":110.5,"status":"completed"},
        {"period":3,"home_manager":"KindComet","away_manager":"B","home_score":139.,"away_score":100.,"status":"completed"},
        {"period":4,"home_manager":"A","away_manager":"B","home_score":999.,"away_score":0.,"status":"live"},
    ])
    before=weeks.copy(deep=True);before_games=games.copy(deep=True)
    result={x["label"]:x for x in league_highlights(weeks,games)}
    assert result["Highest Score"]["value"]=="tpem"
    assert "GW2" in result["Highest Score"]["detail"] and "167.5" in result["Highest Score"]["detail"]
    assert result["Manager of the Week"]["value"]=="KindComet"
    assert "GW2" in result["Biggest Blowout"]["detail"] and "57.0-point" in result["Biggest Blowout"]["detail"]
    assert "GW1" in result["Closest Match"]["detail"] and "0.5-point" in result["Closest Match"]["detail"]
    assert_frame_equal(weeks,before);assert_frame_equal(games,before_games)


def test_table_badges_formatting_help_and_widths_preserve_values():
    table=pd.DataFrame({"Rank":[1],"Team":["Example & Club"],"Movement":[format_movement(1,3)],
        "Record":["2-1-0"],"Form":["W L T W D"],"Pts / GW":[101.333333],"Ghost / GW":[73.833333],
        "Efficiency":[93.79],"Lineup Changes":[8]})
    before=table.copy(deep=True);html=league_table_html(table)
    assert re.findall(r'class="hub-form hub-form-[wld]">([WLD])</span>',html)==["W","L","D","W","D"]
    for displayed in ("101.3","73.8","93.8%","8.0"):assert f'>{displayed}</td>' in html
    assert "101.333333" not in html and "Example &amp; Club" in html
    assert len(TABLE_HELP)==6 and html.count('title="')==6
    assert "#16a34a" in html and "▲2" in html
    assert int(TABLE_WIDTHS["Rank"][:-2])<int(TABLE_WIDTHS["Team"][:-2])
    assert 'width:auto' in html and 'overflow-x:auto' in html
    assert_frame_equal(table,before)
    assert form_presentation(None)==""
    assert "#dc2626" in movement_style(format_movement(3,2))
    assert movement_style(format_movement(2,2))==""


def test_current_gw3_hub_renders():
    def app():
        from pathlib import Path
        from unittest.mock import patch
        import pandas as pd
        from views import live_league_hub as hub
        root=Path("data/models/season_2627")
        def load(data,key,*args):
            path=root/f"{key}_2627.csv"
            return pd.read_csv(path,low_memory=False) if path.exists() else pd.DataFrame()
        # Isolate the presentation test from all live acquisition and resolution.
        state={"healthy":False,"teams":pd.DataFrame(),"standings":pd.DataFrame()}
        with patch.object(hub,"_load",load),patch.object(hub,"get_current_state",return_value=state):
            hub.render("2627")
    app_test=AppTest.from_function(app).run(timeout=30)
    assert not app_test.exception
    markup="\n".join(x.value for x in app_test.markdown)
    assert 'hub-form-w' in markup and 'hub-table-wrap' in markup
    assert "GW3 Results" in markup
    assert "167.5 pts" in markup
