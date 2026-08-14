from streamlit.testing.v1 import AppTest


def run_page(page):
    app=AppTest.from_file("app.py",default_timeout=30).run()
    app.sidebar.radio(key="page_nav").set_value(page).run()
    return app


def test_update_pipeline_apptest():
    app=run_page("Operations Center")
    assert not app.exception
    assert any("Refresh League" in item.value for item in app.markdown)


def test_players_apptest():
    app=run_page("Players")
    assert not app.exception
    assert app.selectbox


def test_managers_apptest():
    app=run_page("Managers")
    assert not app.exception
    assert app.selectbox


def test_live_league_hub_apptest():
    app=run_page("League Hub")
    assert not app.exception
    assert any("League Table" in item.value for item in app.markdown)
    assert any("Available Players" in item.value for item in app.markdown)
