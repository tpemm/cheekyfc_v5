from dataclasses import replace
from datetime import datetime, timezone

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from fantrax.live import current_state as live
from fantrax.live.config import load_live_season_config
from analytics.players.research_overview import ownership_text, preserve_canonical_club
from views.players import live_database_frame

TEAM = "h1vdt8ynmrp1z5vp"
OTHER = "2dxfjlk0mrp1z5vo"
PLAYER = "02lm7"
NOW = datetime(2026, 9, 7, tzinfo=timezone.utc)


def config():
    return replace(load_live_season_config(environ={"FANTRAX_LEAGUE_ID_2627": "test"}), league_id="test", manager_count=2)


def responses(name="nhauptma 🤡", owned=True):
    return {
        "league_metadata": {"teamInfo": {TEAM: {"name": "Pot Splashers"}, OTHER: {"name": "nhauptma"}},
                            "scoringPeriods": [{"number": 3, "startDate": "2026-09-04T00:00:00Z", "endDate": "2026-09-11T00:00:00Z"}]},
        "rosters": {"period": 3, "rosters": {TEAM: {"teamName": "Pot Splashers", "rosterItems": []},
                     OTHER: {"teamName": name, "rosterItems": [{"id": PLAYER, "status": "ACTIVE"}] if owned else []}}},
        "standings": [{"teamId": TEAM, "rank": 1}, {"teamId": OTHER, "rank": 2}],
    }


def acquire(payload=None):
    payload = responses() if payload is None else payload
    def fetch(kind, league_id, **kwargs):
        if kind == "rosters":assert kwargs == {"period": 3}
        value = payload[kind]
        if isinstance(value, Exception):raise value
        return value
    return live.acquire_current_state(config(), fetch=fetch, now=NOW)


def players():
    return pd.DataFrame({"fantrax_player_id": [PLAYER, "05abc"], "player_name": ["Jack Grealish", "Other"],
                         "canonical_player_id": ["pr_9b41dca09396d8c0", None], "fantasy_points": [10., 20.]})


def snapshot():
    return pd.DataFrame({"fantrax_player_id": [PLAYER, "05abc"], "current_manager_id": [TEAM, None],
                         "current_manager_name": ["Pot Splashers", None], "ownership_status": ["Rostered", "Available"],
                         "available": [False, True], "source_retrieved_at": ["2026-09-01", "2026-09-01"]})


def test_live_rosters_authority_and_shared_database_profile():
    state = acquire()
    assert state["healthy"] and state["current_period"] == 3
    result = live.overlay_player_state(players(), snapshot(), state)
    assert result.is_available.tolist() == [False, True]
    assert result.current_manager_id.iloc[0] == OTHER
    assert ownership_text(result.iloc[0]) == "nhauptma 🤡"
    shown = live_database_frame(result, "Per Start")
    assert shown["Fantasy Manager / Available"].tolist() == [ownership_text(row) for _, row in result.iterrows()]
    assert live.filter_roster_status(result).fantrax_player_id.tolist() == ["05abc"]
    assert live.filter_roster_status(result, "Rostered").fantrax_player_id.tolist() == [PLAYER]
    assert len(live.filter_roster_status(result, "All")) == 2
    assert live.ROSTER_STATUS_OPTIONS == ("Available", "Rostered", "All")
    assert {"canonical_player_id", "ownership_state", "current_manager_display_name", "retrieved_at", "source", "freshness_state"} <= set(result)


@pytest.mark.parametrize("kind", ["league_metadata", "rosters"])
def test_failure_preserves_published_values_and_timestamp(kind):
    payload = responses();payload[kind] = PermissionError("HTTP 403")
    state = acquire(payload)
    result = live.overlay_player_state(players(), snapshot(), state)
    assert not state["healthy"]
    assert result.available.tolist() == [False, True]
    assert result.current_manager_id.iloc[0] == TEAM
    assert result.current_manager_name.iloc[0] == "Pot Splashers"
    assert result.retrieved_at.iloc[0] == "2026-09-01"
    assert result.freshness_state.eq("stale").all()
    assert "cached/stale" in live.freshness_caption(state)


def test_failure_without_snapshot_is_unknown_never_free_agent():
    payload = responses();payload["rosters"] = OSError("offline")
    result = live.overlay_player_state(players(), pd.DataFrame(), acquire(payload))
    assert not result.available.any()
    assert result.ownership_state.eq("Unknown").all()
    assert ownership_text(result.iloc[0]) == "Ownership unknown"


@pytest.mark.parametrize("damage", ["missing_team", "missing_items", "wrong_period", "duplicate_player", "missing_id"])
def test_partial_or_malformed_response_cannot_prove_availability(damage):
    payload = responses();roster = payload["rosters"]
    if damage == "missing_team":del roster["rosters"][TEAM]
    if damage == "missing_items":del roster["rosters"][TEAM]["rosterItems"]
    if damage == "wrong_period":roster["period"] = 2
    if damage == "duplicate_player":roster["rosters"][TEAM]["rosterItems"] = [{"id": PLAYER}]
    if damage == "missing_id":roster["rosters"][TEAM]["rosterItems"] = [{}]
    state = acquire(payload)
    assert not state["healthy"]
    assert not live.overlay_player_state(players(), snapshot(), state).available.iloc[0]


def test_drop_and_mutable_name_do_not_change_identity_or_observations():
    original = players();before = original.copy(deep=True);published = snapshot();published_before = published.copy(deep=True)
    first = live.overlay_player_state(original, published, acquire(responses(name="Old name")))
    renamed = live.overlay_player_state(original, published, acquire(responses(name="New 🤡")))
    dropped = live.overlay_player_state(original, published, acquire(responses(owned=False)))
    assert first.current_manager_id.iloc[0] == renamed.current_manager_id.iloc[0] == OTHER
    assert renamed.current_manager_name.iloc[0] == "New 🤡"
    assert dropped.available.iloc[0] and ownership_text(dropped.iloc[0]) == "Available"
    assert_frame_equal(original, before);assert_frame_equal(published, published_before)
    assert renamed.fantasy_points.tolist() == before.fantasy_points.tolist()


def test_current_name_overlay_copies_historical_input():
    historical = pd.DataFrame({"manager_id": [OTHER], "manager_name": ["Historical name"], "fantasy_points": [10]})
    before = historical.copy(deep=True)
    current = live.overlay_manager_names(historical, acquire()["teams"])
    assert current.manager_name.iloc[0] == "nhauptma 🤡"
    assert_frame_equal(historical, before)


def test_standings_failure_does_not_discard_rosters():
    payload = responses();payload["standings"] = PermissionError("HTTP 403")
    state = acquire(payload)
    assert state["healthy"] and state["standings"].empty
    assert "getStandings" in state["errors"]


def test_current_manager_squad_metrics_follow_live_transfer():
    state = acquire()
    pool = players();pool["fantrax_projected_points"] = [100., 50.];pool["historical_minutes"] = [90., 90.]
    pool["drafted_manager_id"] = [TEAM, None]
    current = live.overlay_player_state(pool, snapshot(), state)
    managers = state["teams"].copy()
    managers["average_weekly_score"] = [123., 456.]
    managers["drafted_players_total"] = [1, 1]
    before = managers.copy(deep=True)
    result = live.overlay_manager_roster_metrics(managers, current, state).set_index("manager_id")
    assert result.loc[OTHER, "roster_count"] == 1
    assert result.loc[TEAM, "roster_count"] == 0
    assert result.loc[OTHER, "current_roster_projection"] == 100
    assert result.loc[OTHER, "current_rank"] == 2
    assert result.loc[TEAM, "average_weekly_score"] == 123
    assert_frame_equal(managers, before)


def test_cache_and_force_refresh(monkeypatch):
    calls = []
    monkeypatch.setattr(live, "load_live_season_config", config)
    def fetch(config):
        calls.append(1)
        return {"healthy": True, "version": len(calls)}
    monkeypatch.setattr(live, "acquire_current_state", fetch)
    live._cached_state.clear()
    try:
        assert live.get_current_state()["version"] == 1
        assert live.get_current_state()["version"] == 1
        assert live.get_current_state(force=True)["version"] == 2
    finally:live._cached_state.clear()


def test_refresh_league_forces_shared_cache_even_if_core_fails(monkeypatch):
    from views import update_pipeline
    from types import SimpleNamespace
    forced = []
    monkeypatch.setattr(live, "get_current_state", lambda **kwargs: forced.append(kwargs) or {"healthy": False})
    class Spinner:
        def __enter__(self):return self
        def __exit__(self, *args):return False
    ui = SimpleNamespace(session_state={}, caption=lambda text: None, progress=lambda *a, **k: None, spinner=lambda *a: Spinner())
    def fail(*args):raise RuntimeError("core failed")
    monkeypatch.setattr(update_pipeline, "run_core_refresh", fail)
    with pytest.raises(RuntimeError, match="core failed"):
        update_pipeline._refresh_league(ui, None, "2627")
    assert forced == [{"force": True}]


def test_database_render_defaults_to_available_and_uses_live_drop(monkeypatch):
    from unittest.mock import MagicMock
    from views import players as page
    pool = players();pool["fantrax_projected_points"] = [100., 50.];pool["historical_minutes"] = [90., 90.]
    pool["premier_league_club"] = None;pool["club"] = ["AVL", "LEE"]
    published = snapshot();published["available"] = False;published["ownership_status"] = "Rostered"
    monkeypatch.setattr(page, "_load", lambda data, key, *args: pool.copy() if key == "live_player_analytics" else published.copy() if key == "player_ownership" else pd.DataFrame())
    monkeypatch.setattr(page, "get_current_state", lambda: acquire(responses(owned=False)))
    ui = MagicMock();ui.session_state = {}
    ui.columns.side_effect = lambda n, **kwargs: [ui] * (n if isinstance(n, int) else len(n))
    ui.segmented_control.return_value = "Player Database"
    ui.text_input.return_value = ""
    ui.selectbox.side_effect = lambda label, options, **kwargs: options[kwargs.get("index", 0)]
    page.render("2627", data_manager=MagicMock(), season_manager=MagicMock(), ui=ui)
    shown = ui.dataframe.call_args.args[0]
    assert len(shown) == 2
    assert shown["Fantasy Manager / Available"].eq("Available").all()
    assert shown["Club"].tolist() == ["AVL", "LEE"]
    ui.selectbox.assert_any_call("Roster Status", ("Available", "Rostered", "All"), index=0)


def test_canonical_clubs_survive_null_live_metadata_by_player_id():
    ids = ["078i7", "078mm", "078wo", "06ew2"]
    clubs = ["LIV", "HUL", "LEE", "CRY"]
    canonical = pd.DataFrame({"fantrax_player_id": ids, "player_name": ["Same name"] * 4,
                              "club": clubs, "premier_league_club": [None, "None", "", pd.NA]})
    before = canonical.copy(deep=True)
    state = acquire(responses(owned=False))
    # Neither null roster club fields nor conflicting display names are metadata authority.
    state["rosters"]["club"] = None
    published = pd.DataFrame({"fantrax_player_id": ids[::-1], "player_name": ["Other name"] * 4,
                              "club": [None] * 4, "available": [False] * 4})
    result = live.overlay_player_state(preserve_canonical_club(canonical), published, state)
    assert result.premier_league_club.tolist() == clubs
    assert result.fantrax_player_id.tolist() == ids
    assert result.player_name.tolist() == ["Same name"] * 4
    assert result.available.all()
    assert live_database_frame(result, "Per Start")["Club"].tolist() == clubs
    assert [ownership_text(row) for _, row in result.iterrows()] == ["Available"] * 4
    assert_frame_equal(canonical, before)
    canonical["premier_league_club"] = "Existing"
    assert preserve_canonical_club(canonical).premier_league_club.eq("Existing").all()


def test_buendia_period_response_is_not_overruled_by_unvalidated_metadata():
    payload = responses()
    team_id = "aup99ojzmrp1z5vp"
    payload["league_metadata"]["teamInfo"][team_id] = payload["league_metadata"]["teamInfo"].pop(OTHER)
    payload["rosters"]["rosters"][team_id] = payload["rosters"]["rosters"].pop(OTHER)
    payload["rosters"]["rosters"][team_id]["teamName"] = "The Facerockers"
    payload["standings"][1]["teamId"] = team_id
    payload["rosters"]["rosters"][team_id]["rosterItems"] = [{"id": "051kl", "position": "M", "status": "ACTIVE"}]
    payload["league_metadata"]["playerInfo"] = {"051kl": {"eligiblePos": "M", "status": "WW"}}
    pool = pd.DataFrame({"fantrax_player_id": ["051kl"], "player_name": ["Emiliano Buendia"], "club": ["AVL"]})
    result = live.overlay_player_state(pool, pd.DataFrame(), acquire(payload))
    assert not result.available.iloc[0]
    assert result.current_manager_id.iloc[0] == team_id


def test_force_refresh_applies_returned_roster_change_immediately(monkeypatch):
    calls = []
    monkeypatch.setattr(live, "load_live_season_config", config)
    original_acquire = live.acquire_current_state
    def acquire_fixture(config):
        calls.append(1)
        payload = responses(owned=len(calls) == 1)
        return original_acquire(config, fetch=lambda kind, *args, **kwargs: payload[kind], now=NOW)
    monkeypatch.setattr(live, "acquire_current_state", acquire_fixture)
    live._cached_state.clear()
    try:
        first = live.overlay_player_state(players(), snapshot(), live.get_current_state())
        cached = live.overlay_player_state(players(), snapshot(), live.get_current_state())
        changed = live.overlay_player_state(players(), snapshot(), live.get_current_state(force=True))
        assert not first.available.iloc[0] and not cached.available.iloc[0]
        assert changed.available.iloc[0] and len(calls) == 2
    finally:live._cached_state.clear()
