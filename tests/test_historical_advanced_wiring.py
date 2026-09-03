"""Production regressions for cross-season historical advanced wiring."""
from pathlib import Path
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from core.services.data_manager import DataManager
from core.services.historical_advanced import get_historical_team_advanced,get_historical_player_advanced,historical_club_id,load_historical_advanced_frame

ROOT=Path(__file__).resolve().parents[1]


def test_bournemouth_identity_and_all_historical_surfaces():
    bundle=get_historical_team_advanced(DataManager(),'afc_bournemouth')
    assert bundle.current_club_id=='afc_bournemouth' and bundle.historical_club_id=='bournemouth'
    assert bundle.status=='AVAILABLE'
    assert (len(bundle.formations),len(bundle.fantasy_allowed),len(bundle.playstyle),len(bundle.role_usage),len(bundle.set_pieces))==(4,4,2,45,143)


@pytest.mark.parametrize('club_id', ['afc_bournemouth','manchester_united','arsenal','brighton_hove_albion','nottingham_forest'])
def test_historically_eligible_current_clubs_resolve_without_name_join(club_id):
    bundle=get_historical_team_advanced(DataManager(),club_id)
    assert bundle.status=='AVAILABLE' and bundle.historical_eligible
    assert all(not x.empty for x in (bundle.formations,bundle.fantasy_allowed,bundle.playstyle,bundle.role_usage,bundle.set_pieces))


@pytest.mark.parametrize('club_id',['coventry_city','hull_city','ipswich_town'])
def test_promoted_clubs_have_legitimate_no_history_state(club_id):
    bundle=get_historical_team_advanced(DataManager(),club_id)
    assert bundle.status=='NO_HISTORICAL_EPL_DATA' and not bundle.historical_eligible


def test_registered_historical_products_resolve_to_working_2526_models():
    data=DataManager()
    for key in ('team_formation_profile','supplemental_player_match','player_pitch_events','player_set_piece_usage'):
        path=data.resolve_path(key,'2526','working')
        assert path.exists() and 'models' in path.parts and 'season_2526' in path.parts
        assert not load_historical_advanced_frame(data,key).empty


def test_known_set_piece_player_has_advanced_rating_role_pitch_and_set_pieces():
    pieces=load_historical_advanced_frame(DataManager(),'player_set_piece_usage');candidate=pieces.sort_values('attempts',ascending=False).iloc[0]
    supplemental=load_historical_advanced_frame(DataManager(),'supplemental_player_match');fantrax=supplemental.loc[supplemental.canonical_player_id.eq(candidate.canonical_player_id),'fantrax_player_id'].dropna().astype(str).iloc[0]
    bundle=get_historical_player_advanced(DataManager(),fantrax)
    assert bundle['supplemental'].rating.notna().any()
    assert not bundle['profile'].empty and not bundle['roles'].empty and not bundle['set_pieces'].empty and not bundle['pitch'].empty
    assert {'ALL_CORNERS','SET_PIECE_KEY_PASSES'}&set(bundle['set_pieces'].set_piece_type)


def _run_page(page):
    app=AppTest.from_file('app.py',default_timeout=45).run();app.sidebar.radio(key='page_nav').set_value(page).run();return app


def test_bournemouth_real_apptest_renders_historical_team_data():
    app=_run_page('Teams');selector=next(x for x in app.selectbox if x.label=='Club');selector.set_value('AFC Bournemouth').run()
    next(x for x in app.toggle if x.label=='Compare to 2025/26').set_value(True).run()
    app.radio(key='team_fantasy_season').set_value('2025/26 Historical').run()
    assert not app.exception
    rendered=' '.join(x.value for x in app.markdown)
    assert 'Historical advanced lookup failed' not in rendered and 'No finalized 2025/26 Premier League advanced history' not in rendered
    assert any({'Formation','Matches','Share'}.issubset(set(getattr(x.value,'columns',[]))) for x in app.dataframe)
    captions=' '.join(x.value for x in app.caption)
    assert '2025/26 historical reference' in captions
    assert any('2025/26 comparison' in x.value for x in app.caption)


def test_real_player_apptest_renders_historical_advanced_and_pitch():
    app=_run_page('Players');app.get('button_group')[0].set_value('Player Profile').run();selector=next(x for x in app.selectbox if x.label=='Player')
    historical_names=set(load_historical_advanced_frame(DataManager(),'player_set_piece_usage').player_name.dropna().astype(str));choice=next((x for x in selector.options if str(x).split(' · ')[0] in historical_names),None)
    assert choice is not None
    selector.set_value(choice).run();season=next(x for x in app.selectbox if x.label=='Advanced data season');season.set_value('2025/26 Historical').run();assert not app.exception
    rendered=' '.join(x.value for x in app.markdown)
    assert 'Validated 2025/26 advanced observations are unavailable' not in rendered and 'Historical Event Activity is unavailable' not in rendered
    assert 'Tactical Role' in rendered
    assert [tab.label for tab in app.tabs]==['Overview','Match Analysis','Role & Tactical','Advanced']
    assert app.get('plotly_chart')
