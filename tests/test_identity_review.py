from pathlib import Path

import pandas as pd
import pytest

from analytics.player_registry.matcher import match_current_players
from analytics.player_registry.review import (
    apply_decisions_to_review,
    DECISION_COLUMNS,
    build_identity_review,
    save_review_decision,
)
from core.services.dataset_registry import DatasetRegistry


def registry(names=("Kaoru Mitoma",)):
    return pd.DataFrame(
        {
            "registry_player_id": [f"r{i}" for i, _ in enumerate(names)],
            "fantrax_player_id": [f"fx{i}" for i, _ in enumerate(names)],
            "historical_player_id": [f"fx{i}" for i, _ in enumerate(names)],
            "fantrax_name": list(names),
            "historical_name": list(names),
            "canonical_name": list(names),
            "historical_team": ["BHA"] * len(names),
            "historical_position": ["M"] * len(names),
            "historical_minutes": [1000] * len(names),
            "historical_starts": [10] * len(names),
            "historical_points": [100] * len(names),
            "current_team_code": ["BHA"] * len(names),
            "current_position": ["M"] * len(names),
            "registry_status": ["Historical Only"] * len(names),
            "match_method": ["Unresolved"] * len(names),
            "identity_confidence": [0] * len(names),
        }
    )


def current():
    return pd.DataFrame(
        {
            "provider_player_id": ["121", "999", "inactive"],
            "player_name": ["Mitoma Kaoru", "Kaoru Other", "Kaoru Mitoma"],
            "team_name": ["Brighton", "Other", "Brighton"],
            "team_code": ["BHA", "ARS", "BHA"],
            "position": ["M", "M", "M"],
            "active_epl": [True, True, False],
            "availability_status": ["a", "a", "a"],
        }
    )


def test_review_candidates_are_ranked_deterministically_and_not_approved():
    first = build_identity_review(registry(), current())
    second = build_identity_review(
        registry(), current().sample(frac=1, random_state=4)
    )
    assert first["current_candidate_fpl_id"].tolist() == second[
        "current_candidate_fpl_id"
    ].tolist()
    top = first.iloc[0]
    assert top["current_candidate_name"] == "Mitoma Kaoru"
    assert top["confidence_class"] == "High confidence"
    assert top["review_status"] == "Unreviewed"
    assert not first["current_candidate_fpl_id"].eq("inactive").any()


def test_team_compatible_candidate_is_preferred():
    review = build_identity_review(registry(), current())
    assert review.iloc[0]["current_candidate_team_code"] == "BHA"


def test_position_incompatible_candidate_is_rejected():
    candidates = current().iloc[[0]].copy()
    candidates["position"] = "G"
    assert build_identity_review(registry(), candidates).empty


def test_generic_first_name_overlap_is_not_safe():
    history = registry(("Daniel Alpha",))
    history["historical_team"] = "ARS"
    candidates = current().iloc[[0]].copy()
    candidates["player_name"] = "Daniel Beta"
    candidates["team_code"] = "ARS"
    review = build_identity_review(history, candidates)
    assert review.iloc[0]["confidence_class"] == "No safe candidate"


def test_ambiguous_candidates_are_not_high_confidence():
    candidates = pd.concat([current().iloc[[0]], current().iloc[[0]]], ignore_index=True)
    candidates.loc[1, "provider_player_id"] = "122"
    review = build_identity_review(registry(), candidates)
    assert not review["confidence_class"].eq("High confidence").any()
    assert not review["candidate_unique"].any()


def test_decisions_merge_and_ignored_remains_ignored():
    review = build_identity_review(registry(), current())
    decisions = save_review_decision(
        pd.DataFrame(columns=DECISION_COLUMNS),
        review,
        fantrax_player_id="fx0",
        current_fpl_player_id="121",
        decision="Ignored",
    )
    rebuilt = build_identity_review(registry(), current(), decisions=decisions)
    assert rebuilt.iloc[0]["review_status"] == "Ignored"


def test_approved_decision_preserves_unrelated_and_clear_is_pair_specific():
    review = build_identity_review(registry(), current())
    unrelated = pd.DataFrame(
        [
            {
                **dict.fromkeys(DECISION_COLUMNS, ""),
                "historical_fantrax_player_id": "other",
                "current_fpl_player_id": "888",
                "decision": "Ignored",
            }
        ]
    )
    approved = save_review_decision(
        unrelated,
        review,
        fantrax_player_id="fx0",
        current_fpl_player_id="121",
        decision="Approved",
    )
    assert set(approved["historical_fantrax_player_id"]) == {"other", "fx0"}
    cleared = save_review_decision(
        approved,
        review,
        fantrax_player_id="fx0",
        current_fpl_player_id="121",
        decision="Clear",
    )
    assert cleared["historical_fantrax_player_id"].tolist() == ["other"]


def test_duplicate_fpl_approval_is_rejected():
    review = build_identity_review(registry(), current())
    existing = pd.DataFrame(
        [
            {
                **dict.fromkeys(DECISION_COLUMNS, ""),
                "historical_fantrax_player_id": "other",
                "current_fpl_player_id": "121",
                "decision": "Approved",
            }
        ]
    )
    with pytest.raises(ValueError, match="already approved"):
        save_review_decision(
            existing,
            review,
            fantrax_player_id="fx0",
            current_fpl_player_id="121",
            decision="Approved",
        )


def test_fpl_identity_linked_to_another_registry_player_is_rejected():
    history = registry()
    history["fpl_player_id"] = ""
    linked = history.iloc[[0]].copy()
    linked["registry_player_id"] = "linked"
    linked["fantrax_player_id"] = "different"
    linked["historical_player_id"] = "different"
    linked["fpl_player_id"] = "121"
    linked["registry_status"] = "Confirmed"
    linked["match_method"] = "Exact Name + Club"
    review = build_identity_review(
        pd.concat([history, linked], ignore_index=True), current()
    )
    target = review[review["current_candidate_fpl_id"].eq("121")].iloc[0]
    assert bool(target["candidate_already_linked"])
    with pytest.raises(ValueError, match="already linked"):
        save_review_decision(
            pd.DataFrame(columns=DECISION_COLUMNS),
            review,
            fantrax_player_id="fx0",
            current_fpl_player_id="121",
            decision="Approved",
        )


def test_transfer_requires_acknowledgement_but_can_be_approved():
    history = registry()
    history["historical_team"] = "ARS"
    review = build_identity_review(history, current().iloc[[0]])
    with pytest.raises(ValueError, match="acknowledgement"):
        save_review_decision(
            pd.DataFrame(columns=DECISION_COLUMNS),
            review,
            fantrax_player_id="fx0",
            current_fpl_player_id="121",
            decision="Approved",
        )
    saved = save_review_decision(
        pd.DataFrame(columns=DECISION_COLUMNS),
        review,
        fantrax_player_id="fx0",
        current_fpl_player_id="121",
        decision="Approved",
        acknowledge_transfer=True,
    )
    assert saved.iloc[0]["decision"] == "Approved"


def test_stronger_existing_match_cannot_be_overridden():
    review = build_identity_review(registry(), current())
    review.loc[0, "current_match_method"] = "Exact Name"
    with pytest.raises(ValueError, match="stronger"):
        save_review_decision(
            pd.DataFrame(columns=DECISION_COLUMNS),
            review,
            fantrax_player_id="fx0",
            current_fpl_player_id="121",
            decision="Approved",
        )


def test_approved_user_alias_is_consumed_and_source_recorded():
    fantrax = pd.DataFrame(
        {
            "fantrax_player_id": ["fx0"],
            "player_name": ["Kaoru Mitoma"],
            "team_2627": ["BHA"],
            "position_2627": ["M"],
        }
    )
    decisions = pd.DataFrame(
        {
            "historical_fantrax_player_id": ["fx0"],
            "current_fpl_player_id": ["121"],
            "decision": ["Approved"],
        }
    )
    match = match_current_players(
        fantrax, current().iloc[[0]], alias_overrides=decisions
    ).iloc[0]
    assert match["match_method"] == "Explicit Player Alias"
    assert match["alias_source"] == "User-Approved Alias"
    assert match["identity_confidence"] == 92


def test_ignored_user_alias_is_not_consumed():
    decisions = pd.DataFrame(
        {
            "historical_fantrax_player_id": ["fx0"],
            "current_fpl_player_id": ["121"],
            "decision": ["Ignored"],
        }
    )
    fantrax = pd.DataFrame(
        {
            "fantrax_player_id": ["fx0"],
            "player_name": ["Kaoru Mitoma"],
            "team_2627": ["BHA"],
            "position_2627": ["M"],
        }
    )
    match = match_current_players(
        fantrax, current().iloc[[0]], alias_overrides=decisions
    ).iloc[0]
    assert match["match_method"] == "Unresolved"


def test_malformed_user_alias_rows_are_rejected():
    with pytest.raises(ValueError, match="Malformed"):
        match_current_players(
            pd.DataFrame(
                {
                    "fantrax_player_id": ["fx0"],
                    "player_name": ["Name"],
                    "team_2627": ["BHA"],
                    "position_2627": ["M"],
                }
            ),
            current(),
            alias_overrides=pd.DataFrame({"decision": ["Approved"]}),
        )


def test_review_datasets_are_registered():
    datasets = DatasetRegistry()
    assert datasets.get("player_identity_review").required is False
    assert datasets.get("player_alias_overrides").required is False


def test_identity_review_page_obeys_presentation_boundary():
    source = Path("views/identity_review.py").read_text(encoding="utf-8")
    assert "DataManager" in source
    assert "OperationsService" in source
    assert "read_csv" not in source
    assert "to_csv" not in source
    assert "analytics.player_registry" not in source


@pytest.mark.parametrize(
    ("decision", "expected"),
    [("Ignored", "Ignored"), ("Approved", "Approved"), ("Clear", "Unreviewed")],
)
def test_narrow_decision_projection_updates_pair_and_preserves_other_rows(
    decision, expected
):
    review = build_identity_review(registry(), current())
    selected = review.iloc[0]
    decisions = save_review_decision(
        pd.DataFrame(columns=DECISION_COLUMNS),
        review,
        fantrax_player_id=selected["fantrax_player_id"],
        current_fpl_player_id=selected["current_candidate_fpl_id"],
        decision="Ignored",
    )
    if decision == "Approved":
        decisions.loc[:, "decision"] = "Approved"
    elif decision == "Clear":
        decisions = decisions.iloc[0:0]
    updated = apply_decisions_to_review(review, decisions)
    pair = updated[
        updated["current_candidate_fpl_id"].eq(
            selected["current_candidate_fpl_id"]
        )
    ].iloc[0]
    assert pair["review_status"] == expected
    assert len(updated) == len(review)
    assert updated["candidate_score"].tolist() == review["candidate_score"].tolist()
