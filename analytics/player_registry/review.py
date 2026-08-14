"""Deterministic candidate generation and review-decision validation."""

from __future__ import annotations

from datetime import datetime, timezone
from difflib import SequenceMatcher

import pandas as pd

from analytics.draft.reliability import normalize_player_id, normalize_team, normalize_text


DECISION_COLUMNS = (
    "season_id", "historical_name", "historical_fantrax_player_id",
    "current_fpl_name", "current_fpl_player_id", "historical_team_code",
    "current_team_code", "historical_position", "current_position",
    "decision", "review_note", "reviewed_at", "source",
)
GENERIC_TOKENS = {
    "bruno", "daniel", "danny", "junior", "mateus", "rodrigo", "jose",
    "mohamed", "mohammed", "alex", "joe", "john",
}


def _position_tokens(value: object) -> set[str]:
    aliases = {
        "g": "G", "gk": "G", "goalkeeper": "G",
        "d": "D", "def": "D", "defender": "D",
        "m": "M", "mid": "M", "midfielder": "M",
        "f": "F", "fw": "F", "fwd": "F", "forward": "F",
    }
    return {
        aliases[token]
        for token in normalize_text(value).split()
        if token in aliases
    }


def _active(value: object) -> bool:
    return value is True or normalize_text(value) in {"true", "1", "yes", "active"}


def _decision_key(frame: pd.DataFrame) -> pd.Series:
    return (
        frame["historical_fantrax_player_id"].map(normalize_player_id)
        + "|"
        + frame["current_fpl_player_id"].astype(str).str.removesuffix(".0")
    )


def apply_decisions_to_review(
    review: pd.DataFrame, decisions: pd.DataFrame
) -> pd.DataFrame:
    """Synchronize persisted pair decisions without rescoring candidates."""
    out = review.copy()
    if out.empty:
        return out
    out["review_status"] = "Unreviewed"
    out["review_note"] = ""
    out["reviewed_at"] = ""
    if decisions is None or decisions.empty:
        return out
    valid = decisions[
        decisions.get("decision", pd.Series("", index=decisions.index))
        .isin(["Approved", "Ignored"])
    ].copy()
    if valid.empty:
        return out
    out["_decision_key"] = (
        out["fantrax_player_id"].map(normalize_player_id)
        + "|"
        + out["current_candidate_fpl_id"].astype(str).str.removesuffix(".0")
    )
    valid["_decision_key"] = _decision_key(valid)
    values = valid.drop_duplicates("_decision_key", keep="last").set_index(
        "_decision_key"
    )
    matched = out["_decision_key"].isin(values.index)
    out.loc[matched, "review_status"] = out.loc[
        matched, "_decision_key"
    ].map(values["decision"])
    out.loc[matched, "review_note"] = out.loc[
        matched, "_decision_key"
    ].map(values["review_note"]).fillna("")
    out.loc[matched, "reviewed_at"] = out.loc[
        matched, "_decision_key"
    ].map(values["reviewed_at"]).fillna("")
    return out.drop(columns="_decision_key")


def build_identity_review(
    registry: pd.DataFrame,
    current: pd.DataFrame,
    draft: pd.DataFrame | None = None,
    decisions: pd.DataFrame | None = None,
    *,
    season_id: str = "2627",
    max_candidates: int = 3,
) -> pd.DataFrame:
    """Rank conservative suggestions without approving any identity."""
    reviewable = registry[
        registry["registry_status"].isin(["Historical Only", "Unresolved"])
    ].copy()
    candidates = current[current["active_epl"].map(_active)].copy()
    linked_fantrax_by_fpl: dict[str, set[str]] = {}
    if "fpl_player_id" in registry:
        linked = registry[["fpl_player_id"]].copy()
        linked["fantrax_player_id"] = registry.get(
            "fantrax_player_id", pd.Series("", index=registry.index)
        ).map(normalize_player_id)
        linked["_fpl_id"] = (
            linked["fpl_player_id"].astype(str).str.removesuffix(".0")
        )
        linked_fantrax_by_fpl = {
            fpl_id: set(group["fantrax_player_id"]) - {""}
            for fpl_id, group in linked.groupby("_fpl_id", sort=False)
        }
    draft_lookup = pd.DataFrame()
    if draft is not None and not draft.empty:
        draft_lookup = draft.copy()
        draft_lookup["_fantrax_id"] = draft_lookup["fantrax_player_id"].map(
            normalize_player_id
        )
        draft_lookup = draft_lookup.drop_duplicates("_fantrax_id", keep="last")

    rows: list[dict[str, object]] = []
    for _, historical in reviewable.sort_values("registry_player_id").iterrows():
        historical_name = str(
            historical.get("fantrax_name")
            or historical.get("historical_name")
            or historical.get("canonical_name")
            or ""
        )
        normalized_historical = normalize_text(historical_name)
        historical_tokens = set(normalized_historical.split())
        historical_team = normalize_team(
            historical.get("historical_team")
            or historical.get("current_team_code")
        )
        historical_positions = _position_tokens(
            historical.get("historical_position")
            or historical.get("current_position")
        )
        historical_fantrax_id = normalize_player_id(
            historical.get("fantrax_player_id")
            or historical.get("historical_player_id")
        )
        ranked: list[tuple[float, str, dict[str, object]]] = []
        for _, candidate in candidates.iterrows():
            candidate_positions = _position_tokens(candidate.get("position"))
            position_compatible = (
                not historical_positions
                or not candidate_positions
                or bool(historical_positions & candidate_positions)
            )
            if not position_compatible:
                continue
            candidate_name = str(candidate.get("player_name", ""))
            normalized_candidate = normalize_text(candidate_name)
            candidate_tokens = set(normalized_candidate.split())
            shared_tokens = historical_tokens & candidate_tokens
            meaningful_tokens = shared_tokens - GENERIC_TOKENS
            union = historical_tokens | candidate_tokens
            token_overlap = len(shared_tokens) / len(union) if union else 0.0
            similarity = SequenceMatcher(
                None, normalized_historical, normalized_candidate
            ).ratio()
            candidate_team = normalize_team(candidate.get("team_code"))
            candidate_fpl_id = str(candidate.get("provider_player_id", ""))
            linked_fantrax_ids = linked_fantrax_by_fpl.get(
                candidate_fpl_id, set()
            )
            candidate_already_linked = bool(
                linked_fantrax_ids
                and historical_fantrax_id not in linked_fantrax_ids
            )
            team_compatible = (
                not historical_team
                or not candidate_team
                or historical_team == candidate_team
            )
            meaningful_name = bool(meaningful_tokens) or similarity >= 0.75
            score = (
                similarity * 35
                + token_overlap * 20
                + (25 if team_compatible else -20)
                + 20
            )
            if not meaningful_name:
                score = min(score, 34.0)
            evidence = []
            if shared_tokens:
                evidence.append("shared tokens: " + ", ".join(sorted(shared_tokens)))
            if team_compatible:
                evidence.append("club compatible")
            else:
                evidence.append("possible transfer")
            evidence.append("position compatible")
            if candidate_already_linked:
                evidence.append("already linked to another identity")
            ranked.append(
                (
                    score,
                    str(candidate.get("provider_player_id", "")),
                    {
                        "candidate": candidate,
                        "normalized_candidate": normalized_candidate,
                        "shared_tokens": ", ".join(sorted(shared_tokens)),
                        "name_similarity": round(similarity, 4),
                        "token_overlap": round(token_overlap, 4),
                        "team_compatible": team_compatible,
                        "position_compatible": position_compatible,
                        "meaningful_name": meaningful_name,
                        "candidate_already_linked": candidate_already_linked,
                        "candidate_reason": "; ".join(evidence),
                    },
                )
            )
        ranked.sort(key=lambda item: (-item[0], item[1]))
        selected = ranked[:max_candidates]
        top_score = selected[0][0] if selected else 0.0
        runner_up = selected[1][0] if len(selected) > 1 else -1.0
        unique = bool(selected) and top_score - runner_up >= 8
        for rank, (score, _, evidence) in enumerate(selected, start=1):
            candidate = evidence["candidate"]
            candidate_unique = (
                rank == 1
                and unique
                and not evidence["candidate_already_linked"]
            )
            if (
                score >= 75
                and candidate_unique
                and evidence["team_compatible"]
                and evidence["meaningful_name"]
            ):
                confidence_class = "High confidence"
            elif score >= 58 and evidence["meaningful_name"]:
                confidence_class = "Medium confidence"
            elif score >= 35 and evidence["meaningful_name"]:
                confidence_class = "Low confidence"
            else:
                confidence_class = "No safe candidate"
            fantrax_id = historical_fantrax_id
            production: dict[str, object] = {}
            if not draft_lookup.empty:
                match = draft_lookup[draft_lookup["_fantrax_id"].eq(fantrax_id)]
                if not match.empty:
                    production = match.iloc[0].to_dict()
            rows.append(
                {
                    "season_id": season_id,
                    "registry_player_id": historical.get("registry_player_id", ""),
                    "fantrax_player_id": fantrax_id,
                    "historical_player_id": historical.get("historical_player_id", ""),
                    "historical_name": historical_name,
                    "canonical_name": historical.get("canonical_name", ""),
                    "historical_team_code": historical_team,
                    "historical_position": historical.get("historical_position", ""),
                    "historical_minutes": historical.get("historical_minutes"),
                    "historical_starts": historical.get("historical_starts"),
                    "historical_fantasy_points": historical.get("historical_points"),
                    "historical_ghost_points": production.get("ghost_points_2526"),
                    "historical_adp": production.get("fantrax_adp"),
                    "historical_projected_points": production.get(
                        "fantrax_projected_points"
                    ),
                    "current_candidate_fpl_id": str(
                        candidate.get("provider_player_id", "")
                    ),
                    "current_candidate_name": candidate.get("player_name", ""),
                    "current_candidate_team": candidate.get("team_name", ""),
                    "current_candidate_team_code": normalize_team(
                        candidate.get("team_code")
                    ),
                    "current_candidate_position": candidate.get("position", ""),
                    "candidate_active_epl": True,
                    "candidate_availability_status": candidate.get(
                        "availability_status", ""
                    ),
                    "normalized_historical_name": normalized_historical,
                    "normalized_candidate_name": evidence["normalized_candidate"],
                    "shared_tokens": evidence["shared_tokens"],
                    "candidate_reason": evidence["candidate_reason"],
                    "candidate_score": round(score, 2),
                    "candidate_rank": rank,
                    "confidence_class": confidence_class,
                    "name_similarity": evidence["name_similarity"],
                    "token_overlap": evidence["token_overlap"],
                    "team_compatible": evidence["team_compatible"],
                    "position_compatible": evidence["position_compatible"],
                    "candidate_unique": candidate_unique,
                    "candidate_already_linked": evidence[
                        "candidate_already_linked"
                    ],
                    "proposed_match_method": "Explicit Player Alias",
                    "current_registry_status": historical.get("registry_status", ""),
                    "current_match_method": historical.get("match_method", ""),
                    "current_identity_confidence": historical.get(
                        "identity_confidence", 0
                    ),
                    "current_draft_eligible": bool(
                        production.get("is_draft_eligible", False)
                    ),
                    "review_status": "Unreviewed",
                    "review_note": "",
                    "reviewed_at": "",
                }
            )
    review = pd.DataFrame(rows)
    if review.empty:
        return review
    review = apply_decisions_to_review(review, decisions)
    return review.sort_values(
        ["confidence_class", "candidate_score", "historical_name", "candidate_rank"],
        ascending=[True, False, True, True],
    ).reset_index(drop=True)


def save_review_decision(
    decisions: pd.DataFrame,
    review: pd.DataFrame,
    *,
    fantrax_player_id: str,
    current_fpl_player_id: str,
    decision: str,
    review_note: str = "",
    acknowledge_transfer: bool = False,
    season_id: str = "2627",
) -> pd.DataFrame:
    """Validate and upsert one pair-specific Approved/Ignored decision."""
    if decision not in {"Approved", "Ignored", "Clear"}:
        raise ValueError("Decision must be Approved, Ignored, or Clear")
    fantrax_id = normalize_player_id(fantrax_player_id)
    fpl_id = str(current_fpl_player_id).strip().removesuffix(".0")
    pair = review[
        review["fantrax_player_id"].map(normalize_player_id).eq(fantrax_id)
        & review["current_candidate_fpl_id"].astype(str).str.removesuffix(".0").eq(fpl_id)
    ]
    if len(pair) != 1:
        raise ValueError("Decision requires one registered historical/candidate pair")
    row = pair.iloc[0]
    existing = decisions.copy() if decisions is not None else pd.DataFrame()
    for column in DECISION_COLUMNS:
        if column not in existing:
            existing[column] = ""
    pair_mask = (
        existing["historical_fantrax_player_id"].map(normalize_player_id).eq(fantrax_id)
        & existing["current_fpl_player_id"].astype(str).str.removesuffix(".0").eq(fpl_id)
    )
    if decision == "Clear":
        return existing.loc[~pair_mask, DECISION_COLUMNS].reset_index(drop=True)
    if decision == "Approved":
        if not _active(row["candidate_active_epl"]):
            raise ValueError("Inactive FPL candidates cannot be approved")
        if bool(row.get("candidate_already_linked", False)):
            raise ValueError("FPL identity is already linked in the registry")
        if not bool(row["candidate_unique"]):
            raise ValueError("Alias candidate must be unique")
        if not bool(row["position_compatible"]):
            raise ValueError("Alias positions are incompatible")
        if not bool(row["team_compatible"]) and not acknowledge_transfer:
            raise ValueError("Transfer aliases require explicit acknowledgement")
        if row["current_match_method"] != "Unresolved":
            raise ValueError("A stronger existing identity match cannot be overridden")
        approved = existing[
            existing["decision"].eq("Approved")
            & existing["current_fpl_player_id"].astype(str).str.removesuffix(".0").eq(fpl_id)
            & ~existing["historical_fantrax_player_id"].map(normalize_player_id).eq(
                fantrax_id
            )
        ]
        if not approved.empty:
            raise ValueError("FPL identity is already approved for another player")
    updated = existing.loc[~pair_mask, DECISION_COLUMNS].copy()
    new_row = {
        "season_id": season_id,
        "historical_name": row["historical_name"],
        "historical_fantrax_player_id": fantrax_id,
        "current_fpl_name": row["current_candidate_name"],
        "current_fpl_player_id": fpl_id,
        "historical_team_code": row["historical_team_code"],
        "current_team_code": row["current_candidate_team_code"],
        "historical_position": row["historical_position"],
        "current_position": row["current_candidate_position"],
        "decision": decision,
        "review_note": str(review_note).strip(),
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "source": "Identity Review",
    }
    updated = pd.concat([updated, pd.DataFrame([new_row])], ignore_index=True)
    return updated.sort_values(
        ["historical_fantrax_player_id", "current_fpl_player_id"]
    ).reset_index(drop=True)
