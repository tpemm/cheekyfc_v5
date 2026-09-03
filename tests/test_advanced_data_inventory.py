"""Offline semantic-contract tests for the Sprint 9.5.1 inventory."""
from pathlib import Path

import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
QUALITY=ROOT/"data/quality/season_2526"
REFERENCE=ROOT/"data/reference"


def read_quality(name): return pd.read_csv(QUALITY/f"{name}_2526.csv")


def test_event_and_qualifier_dictionaries_are_complete_and_unique():
    events=read_quality("whoscored_event_type_dictionary")
    qualifiers=read_quality("whoscored_qualifier_dictionary")
    normalized=pd.read_csv(ROOT/"data/models/season_2526/advanced/whoscored_event_2526.csv",usecols=["event_type"])
    assert events.raw_event_type.is_unique and qualifiers.qualifier.is_unique
    assert set(normalized.event_type.dropna().unique())==set(events.raw_event_type)
    assert events.production_status.notna().all() and qualifiers.production_status.notna().all()


def test_metric_dictionary_has_provenance_formulas_and_unique_keys():
    metrics=pd.read_csv(REFERENCE/"advanced_metric_inventory_2526.csv")
    assert metrics.metric_key.is_unique
    assert metrics.loc[metrics.production_status.eq("PRODUCTION_READY"),["source","source_field_or_rule"]].notna().all().all()
    assert metrics.loc[metrics.observed_or_derived.eq("DERIVED"),"formula"].notna().all()
    assert not metrics.loc[metrics.production_status.eq("REJECT"),"recommended_ui"].str.contains("Player|Team",case=False,na=False).any()


def test_authority_and_role_boundaries_are_explicit():
    metrics=pd.read_csv(REFERENCE/"advanced_metric_inventory_2526.csv").set_index("metric_key")
    assert metrics.loc[["xg","xa","xgi"],"source"].eq("Understat").all()
    assert metrics.loc[["fantrax_points","fantrax_ghost_points"],"source"].eq("Fantrax").all()
    roles=read_quality("whoscored_tactical_role_dictionary")
    assert roles.notes.str.contains("separate from Fantrax eligibility",case=False).all()


def test_missing_zero_and_set_piece_semantics_remain_distinct():
    metrics=pd.read_csv(REFERENCE/"advanced_metric_inventory_2526.csv")
    assert (metrics.non_null_observations<=14677).all()
    assert (metrics.observed_zero_count<=metrics.non_null_observations).all()
    set_pieces=read_quality("whoscored_set_piece_inventory")
    assert set_pieces.metric_key.is_unique
    assert set(set_pieces.availability)<= {"DIRECTLY_OBSERVED","SAFELY_DERIVED","NOT_AVAILABLE"}


def test_inventory_is_cache_only_and_has_human_documentation():
    source=(ROOT/"scripts/build_advanced_data_inventory.py").read_text(encoding="utf-8")
    assert "requests" not in source and "selenium" not in source and "read_events(" not in source
    docs=(ROOT/"docs/advanced_data_inventory.md").read_text(encoding="utf-8")
    for heading in ("Passing","Set pieces","Goalkeeping","Fantrax integration","Understat integration"):
        assert heading in docs
