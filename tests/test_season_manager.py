from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from core.services.season_manager import (
    SeasonCatalogError,
    SeasonManager,
    SeasonMutationError,
)


SEASONS = {
    "2526": {
        "label": "2025/26",
        "league": "Cheeky FC",
        "status": "finalized",
        "enabled": True,
        "data_ready": True,
    },
    "2627": {
        "label": "2026/27",
        "league": "Cheeky FC",
        "status": "preseason",
        "enabled": True,
        "data_ready": False,
    },
    "all_time": {
        "label": "All Time",
        "league": "Cheeky FC",
        "status": "not_built",
        "enabled": False,
        "data_ready": False,
    },
}


def manager(definitions=SEASONS, default_season_id="2526") -> SeasonManager:
    return SeasonManager(
        definitions=definitions,
        default_season_id=default_season_id,
        project_root=Path("project"),
    )


def test_season_lookup_and_context_are_immutable():
    context = manager().get("2526")

    assert context.season_id == "2526"
    assert context.display_name == "2025/26"
    assert context.snapshot_root == Path("project/data/seasons/2526")

    with pytest.raises(FrozenInstanceError):
        context.status = "active"


def test_invalid_season_handling():
    seasons = manager()

    with pytest.raises(KeyError, match="Unknown season ID"):
        seasons.get("9999")
    with pytest.raises(KeyError, match="Unknown season ID or display name"):
        seasons.resolve("2099/00")


def test_default_and_display_name_resolution():
    seasons = manager()

    assert seasons.default_viewing_season().season_id == "2526"
    assert seasons.resolve().season_id == "2526"
    assert seasons.resolve("2026/27").season_id == "2627"


def test_active_ingestion_falls_back_to_mutable_enabled_season():
    assert manager().active_ingestion_season().season_id == "2627"


def test_namespace_finalized_and_mutability_rules():
    seasons = manager()

    assert seasons.resolve_namespace("2526") == "snapshot"
    assert seasons.resolve_namespace("2627") == "working"
    assert seasons.resolve_namespace("2627", "snapshot") == "snapshot"
    assert seasons.get("2526").finalized
    assert not seasons.get("2526").mutable
    assert seasons.get("2627").mutable

    with pytest.raises(SeasonMutationError, match="snapshot data is immutable"):
        seasons.assert_mutable("2526")
    with pytest.raises(SeasonMutationError, match="snapshot data is immutable"):
        seasons.assert_mutable("2627", "snapshot")
    seasons.assert_mutable("2627")


def test_supported_pages_match_existing_availability():
    seasons = manager()

    assert seasons.supports_page("2526", "2025/26 Season Archive")
    assert seasons.supports_page("2627", "League Hub")
    assert seasons.supports_page("2627", "Players")
    assert seasons.supports_page("2627", "Draft HQ")
    assert seasons.supports_page("all_time", "Reports")


def test_supported_operations_follow_lifecycle():
    seasons = manager()

    assert seasons.supports_operation("2627", "refresh")
    assert seasons.supports_operation("2627", "finalize")
    assert not seasons.supports_operation("2526", "refresh")
    assert seasons.supports_operation("2526", "validate_snapshot")
    assert not seasons.supports_operation("all_time", "refresh")


def test_configuration_validation_rejects_missing_fields():
    invalid = {"2526": {"label": "2025/26", "status": "finalized"}}

    with pytest.raises(SeasonCatalogError, match="missing required fields"):
        manager(invalid)


def test_configuration_validation_rejects_multiple_active_seasons():
    invalid = {
        "one": {
            "label": "One",
            "status": "active",
            "enabled": True,
            "data_ready": True,
        },
        "two": {
            "label": "Two",
            "status": "active",
            "enabled": True,
            "data_ready": True,
        },
    }

    with pytest.raises(SeasonCatalogError, match="More than one"):
        manager(invalid, default_season_id="one")


def test_catalog_from_existing_configuration_is_valid():
    seasons = SeasonManager()

    seasons.validate_catalog()
    assert [context.season_id for context in seasons.list_seasons()] == [
        "2526",
        "2627",
        "all_time",
    ]
    assert [context.season_id for context in seasons.list_seasons(enabled_only=True)] == [
        "2526",
        "2627",
    ]
