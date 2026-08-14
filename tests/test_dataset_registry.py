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
