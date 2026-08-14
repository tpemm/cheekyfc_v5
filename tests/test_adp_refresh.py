from pathlib import Path

import pandas as pd

from analytics.draft.adp_refresh import validate_adp_export
from scripts.build_draft_tool_v1_2_2_2627 import load_current_fantrax


def export(**overrides):
    data = {
        "ID": ["a1", "b2"], "Player": ["Alpha", "Beta"],
        "Team": ["ARS", "MUN"], "Position": ["M", "F"],
        "ADP": [2.5, None], "FPts": [300, 250],
    }
    data.update(overrides)
    return pd.DataFrame(data)


def test_valid_export_allows_missing_adp_and_distinguishes_projection():
    report = validate_adp_export(export())
    assert report["valid"]
    assert report["missing_adp"] == 1
    assert report["columns"]["adp"] == "ADP"
    assert report["columns"]["projected_points"] == "FPts"


def test_missing_required_column_fails_clearly():
    report = validate_adp_export(export().drop(columns="Position"))
    assert not report["valid"]
    assert any("Missing required position" in error for error in report["errors"])


def test_malformed_adp_fails_but_blank_adp_does_not():
    report = validate_adp_export(export(ADP=["bad", ""]))
    assert not report["valid"]
    assert report["malformed_adp"] == 1
    assert report["missing_adp"] == 1


def test_duplicate_fantrax_ids_are_reported():
    report = validate_adp_export(export(ID=["a1", "a1"]))
    assert report["valid"]
    assert report["duplicate_ids"] == 2


def test_builder_consumes_replaced_adp_in_isolated_fixture(monkeypatch):
    fresh = export(ADP=[7.5, 18.0])
    monkeypatch.setattr(
        "scripts.build_draft_tool_v1_2_2_2627.read_csv", lambda path: fresh.copy()
    )
    result = load_current_fantrax(Path("isolated/Fantrax-Players-Test.csv"))
    assert result["fantrax_adp"].tolist() == [7.5, 18.0]
    assert result["fantrax_projected_points"].tolist() == [300, 250]


def test_adp_only_build_operation_does_not_invoke_registry():
    source = Path("scripts/build_draft_outputs.py").read_text(encoding="utf-8")
    assert "analytics.draft.builder" in source
    assert "player_registry.builder" not in source
