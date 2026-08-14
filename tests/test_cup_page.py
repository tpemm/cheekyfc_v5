from pathlib import Path
from core.services.dataset_registry import DatasetRegistry
from core.services.operations_service import OperationsService
from core.services.season_manager import SeasonManager

def test_cup_datasets_are_registered():
    registry=DatasetRegistry()
    for key in ("cup_configuration","cup_seed_snapshot","cup_schedule","cup_matchups","cup_results","cup_records"): assert registry.get(key).key==key
    assert registry.get("cup_seed_snapshot").mutable is False

def test_cup_operations_are_registered_and_network_free():
    service=OperationsService(season_manager=SeasonManager())
    for key in ("initialize_cup","build_cup_bracket","rebuild_cup","validate_cup"):
        assert service.inspect_operation(key).key==key and service.can_run(key,"2627")
    source=Path("analytics/cup/engine.py").read_text(encoding="utf-8")+Path("scripts/manage_cup.py").read_text(encoding="utf-8")
    assert all(token not in source for token in ("requests.","httpx.","urllib.request"))

def test_navigation_exposes_archive_and_primary_cup_page():
    from views.registry import pages_for_season
    assert "2025/26 Season Archive" in [p.title for p in pages_for_season("2526")]
    assert "League Hub" not in [p.title for p in pages_for_season("2526")]
    assert "Cup Tournament" in [p.title for p in pages_for_season("2627")]
