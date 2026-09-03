from __future__ import annotations

import pandas as pd

from scripts.build_fantrax_whoscored_semantic_audit import metrics


def test_semantic_metrics_handles_no_comparable_observations():
    result = metrics(pd.DataFrame({"fan": [pd.NA], "provider": [pd.NA]}), "fan", "provider", "sample")
    assert result["sample_size"] == 0
    assert result["exact_agreement"] is None
    assert result["mae"] is None


def test_gw2_builders_preserve_rescheduled_exact_pair_and_fantrax_period():
    understat = open("fantrax/live/understat_live.py", encoding="utf-8").read()
    whoscored = open("scripts/build_whoscored_live_products.py", encoding="utf-8").read()
    controller = open("integrations/whoscored/controller.py", encoding="utf-8").read()
    assert "RESOLVED_EXACT_PAIR" in understat
    assert "fantrax_period','gameweek'" in whoscored
    assert "resolution_method" in controller and "rescheduled" in controller


def test_checkpoint_has_required_status_and_authority_guards():
    source = open("scripts/build_gw2_migration_checkpoint.py", encoding="utf-8").read()
    assert "GW2_POST_MATCH_REFRESH_COMPLETE" in source
    assert "COMPLETE_AWAITING_STABILITY" in source
    assert '"authority_change_performed": False' in source
    assert "team_tactical_v1" in source
