import pandas as pd
import pytest

from analytics.player_registry.builder import build_player_registry, registry_id
from analytics.player_registry.matcher import match_current_players


def current():
    return pd.DataFrame(
        {
            "provider_player_id": ["1", "2", "3"],
            "player_name": ["Exact Player", "Transfer Player", "FPL Only"],
            "first_name": ["Exact", "Transfer", "FPL"],
            "last_name": ["Player", "Player", "Only"],
            "team_name": ["Arsenal", "Chelsea", "Chelsea"],
            "team_code": ["ARS", "CHE", "CHE"],
            "position": ["M", "F", "D"],
            "active_epl": [True] * 3,
            "availability_status": ["a"] * 3,
            "injury_news": [""] * 3,
            "provider": ["Official FPL API"] * 3,
            "retrieved_at": ["2026-07-29"] * 3,
            "season_id": ["2627"] * 3,
        }
    )


def fantrax():
    return pd.DataFrame(
        {
            "fantrax_player_id": ["*a*", "*b*", "*old*"],
            "player_name": ["Exact Player", "Transfer Player", "Historical Guy"],
            "team_2627": ["ARS", "CHE", "IPS"],
            "position_2627": ["M", "F", "D"],
        }
    )


def historical():
    return pd.DataFrame(
        {
            "historical_player_id": ["a", "b", "old"],
            "historical_name": ["Exact Player", "Transfer Player", "Historical Guy"],
            "historical_team": ["ARS", "MCI", "IPS"],
            "historical_position": ["M", "F", "D"],
            "historical_minutes": [1000, 1200, 900],
            "historical_starts": [10, 12, 9],
            "historical_points": [100, 120, 90],
            "understat_player_id": ["u1", "u2", "u3"],
        }
    )


def test_matcher_exact_name_club_exact_name_and_unresolved():
    decisions = match_current_players(fantrax(), current())
    methods = decisions.set_index("fantrax_player_id")["match_method"]
    assert methods["a"] == "Exact Name + Club"
    assert methods["b"] == "Exact Name + Club"
    assert methods["old"] == "Unresolved"


def test_manual_override_has_priority():
    altered = fantrax().iloc[[2]].copy()
    overrides = pd.DataFrame(
        {"fantrax_player_id": ["old"], "fpl_player_id": ["3"]}
    )
    decision = match_current_players(altered, current(), overrides).iloc[0]
    assert decision["match_method"] == "Manual Override"
    assert decision["identity_confidence"] == 100


def test_ambiguous_exact_name_is_never_accepted():
    squads = pd.concat([current(), current().iloc[[0]]], ignore_index=True)
    squads.loc[3, "provider_player_id"] = "4"
    decision = match_current_players(fantrax().iloc[[0]], squads).iloc[0]
    assert decision["match_method"] == "Unresolved"
    assert "Ambiguous" in decision["match_diagnostic"]


def test_registry_statuses_transfer_historical_only_and_fpl_only_confirmed():
    registry, quality, unresolved = build_player_registry(
        fantrax(), current(), historical()
    )
    statuses = registry.set_index("canonical_name")["registry_status"]
    assert statuses["Exact Player"] == "Confirmed"
    assert statuses["Transfer Player"] == "Transferred"
    assert statuses["Historical Guy"] == "Historical Only"
    assert statuses["FPL Only"] == "Confirmed"
    assert registry["registry_player_id"].is_unique
    assert quality.set_index("metric").loc["transferred", "value"] == 1
    assert "Historical Guy" in unresolved["canonical_name"].tolist()


def test_bridge_changes_historical_identity():
    bridge = pd.DataFrame(
        {"api_player_id": ["a"], "fantrax_player_id": ["historic-a"]}
    )
    history = historical().copy()
    history.loc[0, "historical_player_id"] = "historic-a"
    registry, _, _ = build_player_registry(
        fantrax(), current(), history, bridge
    )
    row = registry[registry["fantrax_player_id"].eq("a")].iloc[0]
    assert row["historical_player_id"] == "historica"
    assert row["historical_name"] == "Exact Player"


def test_registry_is_deterministic_under_shuffled_inputs():
    first, _, _ = build_player_registry(fantrax(), current(), historical())
    second, _, _ = build_player_registry(
        fantrax().sample(frac=1, random_state=1),
        current().sample(frac=1, random_state=2),
        historical().sample(frac=1, random_state=3),
    )
    assert first["registry_player_id"].tolist() == second["registry_player_id"].tolist()


def test_registry_id_is_stable():
    assert registry_id("1", "a", "Name") == registry_id("1", "a", "Name")


@pytest.mark.parametrize(
    ("fantrax_name", "fpl_name", "team", "fpl_id"),
    [
        ("Bruno Fernandes", "Bruno Borges Fernandes", "MUN", "426"),
        (
            "Bruno Guimaraes",
            "Bruno Guimarães Rodriguez Moura",
            "NEW",
            "452",
        ),
    ],
)
def test_ordered_token_expanded_legal_names_match(
    fantrax_name, fpl_name, team, fpl_id
):
    fantrax_frame = pd.DataFrame(
        {
            "fantrax_player_id": ["fx"],
            "player_name": [fantrax_name],
            "team_2627": [team],
            "position_2627": ["M"],
        }
    )
    current_frame = current().iloc[[0]].copy()
    current_frame["provider_player_id"] = fpl_id
    current_frame["player_name"] = fpl_name
    current_frame["team_code"] = team
    current_frame["position"] = "M"
    decision = match_current_players(fantrax_frame, current_frame).iloc[0]
    assert decision["fpl_player_id"] == fpl_id
    assert decision["match_method"] == "Ordered Token Expanded Name"
    assert decision["identity_confidence"] == 85


def test_ordered_token_does_not_accept_single_token_or_ambiguity():
    fantrax_frame = pd.DataFrame(
        {
            "fantrax_player_id": ["fx"],
            "player_name": ["Bruno"],
            "team_2627": [""],
            "position_2627": ["M"],
        }
    )
    current_frame = pd.DataFrame(
        {
            "provider_player_id": ["1", "2"],
            "player_name": ["Bruno Borges Fernandes", "Bruno Guimarães Moura"],
            "team_code": ["MUN", "NEW"],
            "position": ["M", "M"],
        }
    )
    decision = match_current_players(fantrax_frame, current_frame).iloc[0]
    assert decision["match_method"] == "Unresolved"


@pytest.mark.parametrize(
    ("fantrax_name", "fpl_name", "fantrax_team", "fpl_team", "fantrax_pos", "fpl_pos"),
    [
        ("Fernandes Bruno", "Bruno Borges Fernandes", "MUN", "MUN", "M", "M"),
        ("Bruno Fernandes", "Bruno Borges Fernandes", "NEW", "MUN", "M", "M"),
        ("Bruno Fernandes", "Bruno Borges Fernandes", "MUN", "MUN", "D", "M"),
    ],
)
def test_ordered_token_rejects_wrong_order_team_or_position(
    fantrax_name,
    fpl_name,
    fantrax_team,
    fpl_team,
    fantrax_pos,
    fpl_pos,
):
    decision = match_current_players(
        pd.DataFrame(
            {
                "fantrax_player_id": ["fx"],
                "player_name": [fantrax_name],
                "team_2627": [fantrax_team],
                "position_2627": [fantrax_pos],
            }
        ),
        pd.DataFrame(
            {
                "provider_player_id": ["1"],
                "player_name": [fpl_name],
                "team_code": [fpl_team],
                "position": [fpl_pos],
            }
        ),
    ).iloc[0]
    assert decision["match_method"] == "Unresolved"


def test_registry_marks_expanded_name_match_active_and_confirmed():
    fantrax_frame = pd.DataFrame(
        {
            "fantrax_player_id": ["bf"],
            "player_name": ["Bruno Fernandes"],
            "team_2627": ["MUN"],
            "position_2627": ["M"],
        }
    )
    current_frame = current().iloc[[0]].copy()
    current_frame["provider_player_id"] = "426"
    current_frame["player_name"] = "Bruno Borges Fernandes"
    current_frame["team_name"] = "Manchester United"
    current_frame["team_code"] = "MUN"
    current_frame["position"] = "M"
    history = historical().iloc[[0]].copy()
    history["historical_player_id"] = "bf"
    history["historical_name"] = "Bruno Fernandes"
    history["historical_team"] = "MUN"
    registry, _, _ = build_player_registry(
        fantrax_frame, current_frame, history
    )
    row = registry[registry["fantrax_player_id"].eq("bf")].iloc[0]
    assert bool(row["active_epl"])
    assert row["registry_status"] == "Confirmed"
    assert row["fpl_player_id"] == "426"
    assert row["current_team_code"] == "MUN"


@pytest.mark.parametrize(
    ("fantrax_name", "fpl_name", "team", "position", "fpl_id"),
    [
        ("Ehor Yarmolyuk", "Yehor Yarmoliuk", "BRF", "M", "102"),
        ("Valentino Livramento", "Tino Livramento", "NEW", "D", "450"),
        ("Djordje Petrovic", "Đorđe Petrović", "BOU", "G", "57"),
        ("Danny Ballard", "Daniel Ballard", "SUN", "D", "532"),
        ("Eli Kroupi", "Junior Kroupi", "BOU", "M", "78"),
        (
            "Mateus Goncalo Espanha Fernandes",
            "Mateus Fernandes",
            "TOT",
            "M",
            "525",
        ),
        ("Reinildo", "Reinildo Mandava", "SUN", "D", "536"),
        ("Alisson", "Alisson Becker", "LIV", "G", "350"),
        ("Richarlison", "Richarlison de Andrade", "TOT", "F", "527"),
    ],
)
def test_explicit_player_aliases_match_unique_active_candidate(
    fantrax_name, fpl_name, team, position, fpl_id
):
    decision = match_current_players(
        pd.DataFrame(
            {
                "fantrax_player_id": ["fx"],
                "player_name": [fantrax_name],
                "team_2627": [team],
                "position_2627": [position],
            }
        ),
        pd.DataFrame(
            {
                "provider_player_id": [fpl_id],
                "player_name": [fpl_name],
                "team_code": [team],
                "position": [position],
                "active_epl": [True],
            }
        ),
    ).iloc[0]
    assert decision["fpl_player_id"] == fpl_id
    assert decision["match_method"] == "Explicit Player Alias"
    assert decision["identity_confidence"] == 92


@pytest.mark.parametrize(
    ("fantrax_team", "fpl_team", "fantrax_position", "fpl_position", "active"),
    [
        ("NEW", "SUN", "D", "D", True),
        ("SUN", "SUN", "F", "D", True),
        ("SUN", "SUN", "D", "D", False),
    ],
)
def test_explicit_alias_rejects_team_position_or_active_conflict(
    fantrax_team, fpl_team, fantrax_position, fpl_position, active
):
    decision = match_current_players(
        pd.DataFrame(
            {
                "fantrax_player_id": ["fx"],
                "player_name": ["Danny Ballard"],
                "team_2627": [fantrax_team],
                "position_2627": [fantrax_position],
            }
        ),
        pd.DataFrame(
            {
                "provider_player_id": ["532"],
                "player_name": ["Daniel Ballard"],
                "team_code": [fpl_team],
                "position": [fpl_position],
                "active_epl": [active],
            }
        ),
    ).iloc[0]
    assert decision["match_method"] == "Unresolved"


def test_explicit_alias_rejects_multiple_active_targets():
    current_frame = pd.DataFrame(
        {
            "provider_player_id": ["532", "999"],
            "player_name": ["Daniel Ballard", "Daniel Ballard"],
            "team_code": ["SUN", "SUN"],
            "position": ["D", "D"],
            "active_epl": [True, True],
        }
    )
    decision = match_current_players(
        pd.DataFrame(
            {
                "fantrax_player_id": ["fx"],
                "player_name": ["Danny Ballard"],
                "team_2627": ["SUN"],
                "position_2627": ["D"],
            }
        ),
        current_frame,
    ).iloc[0]
    assert decision["match_method"] == "Unresolved"
    assert "Ambiguous explicit player alias" in decision["match_diagnostic"]


def test_exact_match_remains_stronger_than_explicit_alias():
    current_frame = pd.DataFrame(
        {
            "provider_player_id": ["1", "532"],
            "player_name": ["Danny Ballard", "Daniel Ballard"],
            "team_code": ["SUN", "SUN"],
            "position": ["D", "D"],
            "active_epl": [True, True],
        }
    )
    decision = match_current_players(
        pd.DataFrame(
            {
                "fantrax_player_id": ["fx"],
                "player_name": ["Danny Ballard"],
                "team_2627": ["SUN"],
                "position_2627": ["D"],
            }
        ),
        current_frame,
    ).iloc[0]
    assert decision["fpl_player_id"] == "1"
    assert decision["match_method"] == "Exact Name + Club"


def test_unlisted_nickname_does_not_trigger_explicit_alias():
    decision = match_current_players(
        pd.DataFrame(
            {
                "fantrax_player_id": ["fx"],
                "player_name": ["Bobby Example"],
                "team_2627": ["ARS"],
                "position_2627": ["M"],
            }
        ),
        pd.DataFrame(
            {
                "provider_player_id": ["1"],
                "player_name": ["Robert Example"],
                "team_code": ["ARS"],
                "position": ["M"],
                "active_epl": [True],
            }
        ),
    ).iloc[0]
    assert decision["match_method"] == "Unresolved"


@pytest.mark.parametrize(
    ("fantrax_name", "fpl_id"),
    [
        ("Ehor Yarmolyuk", "102"),
        ("Valentino Livramento", "450"),
        ("Djordje Petrovic", "57"),
        ("Danny Ballard", "532"),
        ("Eli Kroupi", "78"),
        ("Mateus Goncalo Espanha Fernandes", "525"),
        ("Reinildo", "536"),
        ("Alisson", "350"),
        ("Richarlison", "527"),
    ],
)
def test_rebuilt_registry_consolidates_explicit_aliases(fantrax_name, fpl_id):
    registry = pd.read_csv(
        "data/reference/player_registry_2627.csv",
        dtype=str,
        keep_default_na=False,
    )
    rows = registry[registry["fantrax_name"].eq(fantrax_name)]
    assert len(rows) == 1
    row = rows.iloc[0]
    assert row["fpl_player_id"] == fpl_id
    assert row["active_epl"] == "True"
    assert row["registry_status"] in {"Confirmed", "Transferred"}
    assert row["current_team_code"]
    assert row["current_position"]
    assert row["match_method"] == "Explicit Player Alias"
    assert row["identity_confidence"] == "92"
