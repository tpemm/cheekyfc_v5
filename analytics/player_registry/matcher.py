"""Deterministic, ambiguity-safe identity matching."""

from __future__ import annotations

from difflib import SequenceMatcher

import pandas as pd

from analytics.draft.reliability import normalize_player_id, normalize_team, normalize_text
from analytics.player_registry.aliases import PLAYER_ALIAS_LOOKUP_2627


CONFIDENCE = {
    "Fantrax ID": 100,
    "Manual Override": 100,
    "Historical Bridge": 98,
    "FPL ID": 97,
    "Exact Name + Club": 95,
    "Explicit Player Alias": 92,
    "Exact Name": 90,
    "Ordered Token Expanded Name": 85,
    "Unique Fuzzy": 75,
    "Unresolved": 0,
}


def _position_tokens(value: object) -> set[str]:
    """Return comparable Fantrax/FPL position codes."""
    text = normalize_text(value)
    aliases = {
        "g": "G", "gk": "G", "goalkeeper": "G",
        "d": "D", "def": "D", "defender": "D",
        "m": "M", "mid": "M", "midfielder": "M",
        "f": "F", "fw": "F", "fwd": "F", "forward": "F",
    }
    return {
        aliases[token]
        for token in text.split()
        if token in aliases
    }


def _ordered_token_subset(short_name: str, expanded_name: str) -> bool:
    """Whether every short-name token occurs in order in an expanded name."""
    short_tokens = short_name.split()
    expanded_tokens = expanded_name.split()
    if len(short_tokens) < 2 or len(expanded_tokens) <= len(short_tokens):
        return False
    position = 0
    for token in expanded_tokens:
        if position < len(short_tokens) and token == short_tokens[position]:
            position += 1
    return position == len(short_tokens)


def _is_active(value: object) -> bool:
    """Interpret current-squad active flags without treating non-empty strings as true."""
    if isinstance(value, bool):
        return value
    return normalize_text(value) in {"true", "1", "yes", "y", "active"}


def match_current_players(
    fantrax: pd.DataFrame,
    current: pd.DataFrame,
    overrides: pd.DataFrame | None = None,
    alias_overrides: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Return one explicit FPL match decision per Fantrax row."""
    current = current.reset_index(drop=True).copy()
    current["_name"] = current["player_name"].map(normalize_text)
    current["_team"] = current["team_code"].map(normalize_team)
    current["_positions"] = current["position"].map(_position_tokens)
    current["_active"] = current.get(
        "active_epl", pd.Series(True, index=current.index)
    ).map(_is_active)
    by_name: dict[str, list[int]] = {}
    by_name_team: dict[tuple[str, str], list[int]] = {}
    for idx, row in current.iterrows():
        by_name.setdefault(row["_name"], []).append(idx)
        by_name_team.setdefault((row["_name"], row["_team"]), []).append(idx)

    override_lookup = {}
    if overrides is not None and not overrides.empty:
        for _, row in overrides.iterrows():
            key = normalize_player_id(row.get("fantrax_player_id", ""))
            if key and key not in override_lookup:
                override_lookup[key] = str(row.get("fpl_player_id", "")).strip()
    user_alias_lookup: dict[str, str] = {}
    if alias_overrides is not None and not alias_overrides.empty:
        required = {
            "historical_fantrax_player_id", "current_fpl_player_id", "decision",
        }
        missing = required - set(alias_overrides.columns)
        if missing:
            raise ValueError(
                "Malformed alias overrides; missing: " + ", ".join(sorted(missing))
            )
        approved = alias_overrides[alias_overrides["decision"].eq("Approved")]
        normalized = pd.DataFrame(
            {
                "fantrax_id": approved["historical_fantrax_player_id"].map(
                    normalize_player_id
                ),
                "fpl_id": approved["current_fpl_player_id"].astype(str).str.removesuffix(
                    ".0"
                ),
            }
        )
        if normalized["fantrax_id"].eq("").any() or normalized["fpl_id"].eq("").any():
            raise ValueError("Approved alias overrides require both provider IDs")
        if normalized["fantrax_id"].duplicated().any():
            raise ValueError("One historical identity has multiple approved aliases")
        if normalized["fpl_id"].duplicated().any():
            raise ValueError("One FPL identity has multiple approved aliases")
        user_alias_lookup = dict(
            zip(normalized["fantrax_id"], normalized["fpl_id"])
        )

    results = []
    used_current: set[int] = set()
    for _, player in fantrax.iterrows():
        fantrax_id = normalize_player_id(player.get("fantrax_player_id", ""))
        name = normalize_text(player.get("player_name", ""))
        team = normalize_team(player.get("team_2627", ""))
        positions = _position_tokens(player.get("position_2627", ""))
        matched: int | None = None
        method = "Unresolved"
        alias_source = ""
        diagnostic = "No unique current-squad match"

        override_id = override_lookup.get(fantrax_id)
        if override_id:
            candidates = current.index[
                current["provider_player_id"].astype(str).eq(override_id)
            ].tolist()
            if len(candidates) == 1:
                matched, method, diagnostic = candidates[0], "Manual Override", "Curated FPL ID"
        if matched is None:
            candidates = by_name_team.get((name, team), [])
            if len(candidates) == 1:
                matched, method, diagnostic = candidates[0], "Exact Name + Club", "Unique normalized name and club"
        if matched is None:
            candidates = by_name.get(name, [])
            if len(candidates) == 1:
                matched, method, diagnostic = candidates[0], "Exact Name", "Unique normalized name"
            elif len(candidates) > 1:
                diagnostic = f"Ambiguous exact name ({len(candidates)} candidates)"
        user_alias_id = user_alias_lookup.get(fantrax_id)
        alias_target = PLAYER_ALIAS_LOOKUP_2627.get(name)
        if matched is None and (alias_target or user_alias_id):
            alias_candidates: list[int] = []
            candidate_indexes = (
                current.index[
                    current["provider_player_id"].astype(str).eq(user_alias_id)
                ].tolist()
                if user_alias_id
                else by_name.get(str(alias_target), [])
            )
            for candidate_idx in candidate_indexes:
                candidate_team = str(current.at[candidate_idx, "_team"])
                candidate_positions = current.at[candidate_idx, "_positions"]
                teams_compatible = (
                    not team
                    or not candidate_team
                    or team == candidate_team
                )
                positions_compatible = (
                    not positions
                    or not candidate_positions
                    or bool(positions & candidate_positions)
                )
                if (
                    candidate_idx not in used_current
                    and bool(current.at[candidate_idx, "_active"])
                    and teams_compatible
                    and positions_compatible
                ):
                    alias_candidates.append(candidate_idx)
            if len(alias_candidates) == 1:
                matched = alias_candidates[0]
                method = "Explicit Player Alias"
                alias_source = (
                    "User-Approved Alias" if user_alias_id else "Built-in Alias"
                )
                diagnostic = (
                    f"{alias_source}; unique active candidate with "
                    "compatible club and position"
                )
            elif len(alias_candidates) > 1:
                diagnostic = (
                    f"Ambiguous explicit player alias "
                    f"({len(alias_candidates)} active candidates)"
                )
            else:
                diagnostic = (
                    "Explicit player alias rejected: no unique active candidate "
                    "with compatible club and position"
                )
        if matched is None and name:
            expanded_candidates: list[int] = []
            for candidate_idx, candidate in current.iterrows():
                candidate_team = str(candidate["_team"])
                candidate_positions = candidate["_positions"]
                teams_compatible = (
                    not team
                    or not candidate_team
                    or team == candidate_team
                )
                positions_compatible = (
                    not positions
                    or not candidate_positions
                    or bool(positions & candidate_positions)
                )
                if (
                    candidate_idx not in used_current
                    and teams_compatible
                    and positions_compatible
                    and _ordered_token_subset(name, str(candidate["_name"]))
                ):
                    expanded_candidates.append(candidate_idx)
            if len(expanded_candidates) == 1:
                matched = expanded_candidates[0]
                method = "Ordered Token Expanded Name"
                diagnostic = "Unique ordered-token expansion with compatible club and position"
            elif len(expanded_candidates) > 1:
                diagnostic = (
                    f"Ambiguous ordered-token expansion "
                    f"({len(expanded_candidates)} candidates)"
                )
        if matched is None and name:
            scores = sorted(
                (
                    SequenceMatcher(None, name, candidate_name).ratio(),
                    idx,
                )
                for idx, candidate_name in current["_name"].items()
                if current.at[idx, "_team"] == team
                and idx not in used_current
                and (
                    not positions
                    or not current.at[idx, "_positions"]
                    or bool(positions & current.at[idx, "_positions"])
                )
            )
            if scores:
                best_score, best_idx = scores[-1]
                second = scores[-2][0] if len(scores) > 1 else 0
                if best_score >= 0.90 and best_score - second >= 0.05:
                    matched, method = best_idx, "Unique Fuzzy"
                    diagnostic = f"Unique club-constrained fuzzy match ({best_score:.3f})"

        if matched is not None and matched in used_current:
            diagnostic = "Current player already matched to another Fantrax row"
            matched, method = None, "Unresolved"
        if matched is not None:
            used_current.add(matched)
            current_row = current.loc[matched]
            fpl_id = str(current_row["provider_player_id"])
            fpl_name = current_row["player_name"]
        else:
            fpl_id = ""
            fpl_name = ""
        results.append(
            {
                "fantrax_player_id": fantrax_id,
                "fpl_player_id": fpl_id,
                "fpl_name": fpl_name,
                "match_method": method,
                "alias_source": alias_source,
                "identity_confidence": CONFIDENCE[method],
                "match_diagnostic": diagnostic,
                "matched_current_index": matched,
            }
        )
    return pd.DataFrame(results)
