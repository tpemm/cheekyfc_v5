import pytest

from core.models.dataset_definition import DatasetDefinition
from core.services.dataset_registry import (
    CORE_DATASETS,
    DatasetRegistry,
    RegistryValidationError,
)


def definition(key: str, *, aliases: tuple[str, ...] = ()) -> DatasetDefinition:
    return DatasetDefinition(
        key=key,
        display_name=key.replace("_", " ").title(),
        description=f"Definition for {key}.",
        classification="processed",
        namespace="processed",
        filename_template=f"{key}_{{season_id}}.csv",
        aliases=aliases,
    )


def test_lookup_by_canonical_key():
    registry = DatasetRegistry()

    result = registry.get("master_player_weekly")

    assert result.key == "master_player_weekly"
    assert result.filename_template == "master_player_weekly_{season_id}.csv"


def test_alias_resolution_and_lookup():
    registry = DatasetRegistry()

    assert registry.resolve_alias("master_weekly") == "master_player_weekly"
    assert registry.get("master_weekly") is registry.get("master_player_weekly")
    assert registry.resolve_alias("unknown_dataset") == "unknown_dataset"


def test_duplicate_key_detection():
    duplicate = definition("duplicate")

    with pytest.raises(RegistryValidationError, match="Duplicate dataset key"):
        DatasetRegistry((duplicate, duplicate))


def test_validation_and_filtering():
    registry = DatasetRegistry()

    registry.validate()

    assert len(registry.list_all()) == len(CORE_DATASETS)
    assert {item.key for item in registry.find_by_classification("model")} == {
        "draft_rankings",
        "draft_player_pool",
        "draft_results",
        "draft_pick_grades",
        "draft_manager_grades",
        "draft_category_scores",
        "draft_position_grades",
        "draft_awards",
        "team_matches",
        "team_fixtures",
        "club_elo_current",
            "club_elo_history",
            "team_match_analytics",
            "team_season_profile",
            "team_manager_profile",
            "team_formation_analytics",
            "team_home_away_profile",
                "team_fantasy_allowed_match",
                "team_fantasy_allowed_position_match",
                "team_tactical_match_features",
                "team_tactical_profile",
                "team_manager_tactical_profile",
                "team_formation_tactical_profile",
                "team_venue_tactical_profile",
                "team_opponent_tactical_context",
                "team_match_observations",
        "team_position_fantasy_allowed",
        "team_attack_profile",
        "team_defense_profile",
        "team_matchup_features",
        "player_matchup_features",
        "whoscored_match_poc",
        "whoscored_lineup_poc",
        "whoscored_event_poc",
        "advanced_player_match_poc",
        "player_pitch_events",
        "team_formation_usage_poc",
            "player_role_usage_poc",
            "whoscored_match_scale",
            "whoscored_team_match_scale",
            "whoscored_lineup_scale",
            "whoscored_event_scale",
            "advanced_player_match_scale",
            "player_tactical_position_history_scale",
            "team_formation_history_scale",
            "team_event_features_scale",
            "player_event_activity_scale",
            "whoscored_match",
            "whoscored_lineup",
            "whoscored_event",
            "advanced_player_match",
            "player_match_roles",
            "player_role_profile",
            "team_formation_history",
            "team_formation_profile",
            "team_match_features",
            "player_event_data",
            "historical_position_fantasy_allowed",
            "supplemental_player_match",
            "player_advanced_profile",
            "player_role_usage",
            "player_set_piece_usage",
            "team_set_piece_hierarchy",
            "team_playstyle_profile",
            "historical_fantasy_allowed_ranked",
            "formation_player_usage",
            "historical_player_research_profile",
        }
    assert all(
        item.namespace == "reference"
        for item in registry.find_by_namespace("reference")
    )
    assert "Master Player Weekly" in registry.describe("master_weekly")


def test_duplicate_alias_detection():
    first = definition("first", aliases=("shared_alias",))
    second = definition("second", aliases=("shared_alias",))

    with pytest.raises(RegistryValidationError, match="Duplicate dataset alias"):
        DatasetRegistry((first, second))


def test_missing_key_behavior():
    registry = DatasetRegistry()

    with pytest.raises(KeyError, match="Unknown dataset key or alias"):
        registry.get("not_registered")


def test_invalid_definition_is_rejected():
    invalid = definition("Invalid Key")

    with pytest.raises(RegistryValidationError, match="lowercase snake_case"):
        DatasetRegistry((invalid,))
