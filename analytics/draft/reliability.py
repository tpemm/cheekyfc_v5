"""Eligibility and identity reliability helpers for the Draft producer."""

from __future__ import annotations

import html
import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import pandas as pd


TEAM_ALIASES = {
    "afc bournemouth": "BOU", "afc bournemouth fc": "BOU", "bournemouth": "BOU",
    "arsenal": "ARS", "arsenal fc": "ARS",
    "aston villa": "AVL", "aston villa fc": "AVL",
    "brentford": "BRF", "brentford fc": "BRF",
    "brighton": "BHA", "brighton and hove albion": "BHA",
    "brighton hove albion fc": "BHA",
    "burnley": "BUR", "burnley fc": "BUR",
    "chelsea": "CHE", "chelsea fc": "CHE",
    "coventry city": "COV", "coventry city fc": "COV",
    "crystal palace": "CRY", "crystal palace fc": "CRY",
    "everton": "EVE", "everton fc": "EVE",
    "fulham": "FUL", "fulham fc": "FUL",
    "hull city": "HUL", "hull city afc": "HUL",
    "ipswich town": "IPS", "ipswich town fc": "IPS",
    "leeds": "LEE", "leeds united": "LEE", "leeds united fc": "LEE",
    "liverpool": "LIV", "liverpool fc": "LIV",
    "manchester city": "MCI", "manchester city fc": "MCI", "man city": "MCI",
    "manchester united": "MUN", "manchester united fc": "MUN", "man united": "MUN",
    "newcastle": "NEW", "newcastle united": "NEW", "newcastle united fc": "NEW",
    "nottingham forest": "NOT", "nottingham forest fc": "NOT", "nottm forest": "NOT",
    "sunderland": "SUN", "sunderland afc": "SUN",
    "tottenham": "TOT", "tottenham hotspur": "TOT", "tottenham hotspur fc": "TOT",
    "west ham": "WHU", "west ham united": "WHU", "west ham united fc": "WHU",
    "wolves": "WOL", "wolverhampton wanderers": "WOL",
    "wolverhampton wanderers fc": "WOL",
}
TEAM_CODES = set(TEAM_ALIASES.values())


def normalize_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKD", html.unescape(str(value)))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.casefold())).strip()


def normalize_player_id(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return re.sub(r"[^a-z0-9]", "", str(value).strip().casefold())


def normalize_team(value: object) -> str:
    clean = normalize_text(value)
    provider_code_aliases = {"BRE": "BRF", "NFO": "NOT"}
    raw_code = str(value).strip().upper()
    if raw_code in provider_code_aliases:
        return provider_code_aliases[raw_code]
    if clean.upper() in TEAM_CODES:
        return clean.upper()
    return TEAM_ALIASES.get(clean, str(value).strip().upper())


def load_current_epl_squads(
    squad_root: Path,
    teams_path: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return normalized players and one explicit coverage row per expected club."""
    expected: dict[str, dict[str, object]] = {}
    if teams_path and Path(teams_path).exists():
        payload = json.loads(Path(teams_path).read_text(encoding="utf-8-sig"))
        for item in payload.get("data", {}).get("teams", []):
            team = item.get("team", {})
            code = normalize_team(team.get("team_name", ""))
            if code:
                expected[code] = {
                    "team_code": code,
                    "team_name": team.get("team_name", ""),
                    "team_id": team.get("team_id"),
                }

    rows: list[dict[str, object]] = []
    file_clubs: set[str] = set()
    timestamps: dict[str, str] = {}
    for path in sorted(Path(squad_root).glob("team_*_players.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        data = payload.get("data", {})
        team = data.get("team", {})
        code = normalize_team(team.get("team_name", ""))
        if not code:
            continue
        file_clubs.add(code)
        timestamps[code] = pd.Timestamp(path.stat().st_mtime, unit="s", tz="UTC").isoformat()
        for player in data.get("players", []) or []:
            aliases = {
                str(player.get("player_name", "")).strip(),
                str(player.get("known_name", "")).strip(),
                " ".join(
                    filter(
                        None,
                        [
                            str(player.get("first_name", "")).strip(),
                            str(player.get("last_name", "")).strip(),
                        ],
                    )
                ),
            }
            rows.append(
                {
                    "footballdata_player_id": player.get("player_id"),
                    "current_epl_team": code,
                    "footballdata_player_name": str(
                        player.get("known_name") or player.get("player_name") or ""
                    ).strip(),
                    "alias_keys": tuple(
                        sorted({normalize_text(alias) for alias in aliases if normalize_text(alias)})
                    ),
                    "squad_source": "FootballData.io",
                    "squad_retrieved_at": timestamps[code],
                }
            )

    squads = pd.DataFrame(rows)
    counts = (
        squads.groupby("current_epl_team").size().to_dict()
        if not squads.empty
        else {}
    )
    club_codes = sorted(set(expected) | file_clubs)
    coverage = pd.DataFrame(
        [
            {
                **expected.get(code, {"team_code": code, "team_name": "", "team_id": np.nan}),
                "cache_file_present": code in file_clubs,
                "player_count": int(counts.get(code, 0)),
                "coverage_complete": int(counts.get(code, 0)) >= 15,
                "source_system": "FootballData.io",
                "retrieved_at": timestamps.get(code, ""),
            }
            for code in club_codes
        ]
    )
    return squads, coverage


def apply_current_squad_eligibility(
    frame: pd.DataFrame,
    squad_root: Path | None,
    teams_path: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Classify every row without treating an incomplete source as confirmation."""
    out = frame.copy()
    out["eligibility_source"] = "Current squad source unavailable"
    out["squad_match_method"] = "unresolved"
    out["footballdata_player_id"] = pd.NA
    out["footballdata_player_name"] = ""
    out["current_epl_team"] = out.get("team_2627", pd.Series("", index=out.index)).map(normalize_team)
    out["eligibility_reason"] = "Current squad source unavailable"
    out["eligibility_override"] = False

    squads = pd.DataFrame()
    coverage = pd.DataFrame()
    if squad_root is not None and Path(squad_root).exists():
        squads, coverage = load_current_epl_squads(Path(squad_root), teams_path)

    complete = (
        len(coverage) == 20
        and bool(coverage["coverage_complete"].all())
        if not coverage.empty
        else False
    )
    covered_codes = set(coverage.loc[coverage["coverage_complete"], "team_code"]) if not coverage.empty else set()

    alias_map: dict[str, list[int]] = {}
    team_aliases: dict[str, list[tuple[str, int]]] = {}
    for squad_idx, squad in squads.iterrows():
        for alias in squad["alias_keys"]:
            alias_map.setdefault(alias, []).append(squad_idx)
            team_aliases.setdefault(str(squad["current_epl_team"]), []).append((alias, squad_idx))

    report: list[dict[str, object]] = []
    for idx, row in out.iterrows():
        name_key = normalize_text(row.get("player_name", ""))
        team = normalize_team(row.get("team_2627", ""))
        candidates = list(dict.fromkeys(alias_map.get(name_key, [])))
        match_idx: int | None = None
        method = ""
        confidence = np.nan
        if len(candidates) == 1:
            match_idx, method, confidence = candidates[0], "exact unique name", 1.0
        elif team in covered_codes and name_key:
            scores = sorted(
                (
                    (SequenceMatcher(None, name_key, alias).ratio(), candidate_idx)
                    for alias, candidate_idx in team_aliases.get(team, [])
                ),
                reverse=True,
            )
            if scores and scores[0][0] >= 0.92 and (
                len(scores) == 1 or scores[0][0] - scores[1][0] >= 0.04
            ):
                confidence, match_idx = scores[0]
                method = "fuzzy within listed club"

        if match_idx is not None:
            squad = squads.loc[match_idx]
            out.at[idx, "is_draft_eligible"] = True
            out.at[idx, "is_free_agent"] = False
            out.at[idx, "team_2627"] = squad["current_epl_team"]
            out.at[idx, "current_epl_team"] = squad["current_epl_team"]
            out.at[idx, "footballdata_player_id"] = squad["footballdata_player_id"]
            out.at[idx, "footballdata_player_name"] = squad["footballdata_player_name"]
            out.at[idx, "draft_eligibility_status"] = "Matched eligible"
            out.at[idx, "eligibility_source"] = "FootballData.io"
            out.at[idx, "squad_match_method"] = method
            out.at[idx, "eligibility_reason"] = "Matched to current EPL squad"
        elif complete:
            out.at[idx, "is_draft_eligible"] = False
            out.at[idx, "is_free_agent"] = True
            out.at[idx, "draft_eligibility_status"] = "Confirmed no longer EPL eligible"
            out.at[idx, "eligibility_source"] = "FootballData.io"
            out.at[idx, "squad_match_method"] = "not matched in complete cache"
            out.at[idx, "eligibility_reason"] = "Absent from complete 20-club squad source"
        else:
            # Preserve browsing inclusion, but never call this a confirmed match.
            out.at[idx, "is_draft_eligible"] = True
            out.at[idx, "is_free_agent"] = False
            out.at[idx, "draft_eligibility_status"] = "Unresolved: squad source incomplete"
            out.at[idx, "eligibility_source"] = "FootballData.io incomplete cache"
            out.at[idx, "squad_match_method"] = "unresolved"
            out.at[idx, "eligibility_reason"] = (
                f"Squad source incomplete: {len(covered_codes)}/20 clubs have 15+ players"
            )

        report.append(
            {
                "fantrax_player_id": row.get("fantrax_player_id", ""),
                "player_name": row.get("player_name", ""),
                "fantrax_team": team,
                "matched_current_team": out.at[idx, "current_epl_team"],
                "is_draft_eligible": bool(out.at[idx, "is_draft_eligible"]),
                "draft_eligibility_status": out.at[idx, "draft_eligibility_status"],
                "eligibility_source": out.at[idx, "eligibility_source"],
                "squad_match_method": out.at[idx, "squad_match_method"],
                "footballdata_player_id": out.at[idx, "footballdata_player_id"],
                "footballdata_player_name": out.at[idx, "footballdata_player_name"],
                "eligibility_override": False,
                "diagnostic_reason": out.at[idx, "eligibility_reason"],
                "match_confidence": confidence,
                "complete_squad_coverage": complete,
            }
        )
    return out, pd.DataFrame(report), coverage


def apply_eligibility_overrides(
    frame: pd.DataFrame,
    overrides: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply unambiguous overrides with ID precedence over name fallback."""
    out = frame.copy()
    diagnostics: list[dict[str, object]] = []
    diagnostic_columns = ["override_row", "status", "reason", "matched_rows"]
    if "eligibility_override" not in out:
        out["eligibility_override"] = False
    if overrides.empty:
        return out, pd.DataFrame(diagnostics, columns=diagnostic_columns)

    out_ids = out["fantrax_player_id"].map(normalize_player_id)
    out_names = out["player_name"].map(normalize_text)
    for override_idx, row in overrides.iterrows():
        override_id = normalize_player_id(row.get("fantrax_player_id", ""))
        override_name = normalize_text(row.get("player_name", ""))
        id_mask = out_ids.eq(override_id) if override_id else pd.Series(False, index=out.index)
        name_mask = out_names.eq(override_name) if override_name else pd.Series(False, index=out.index)
        mask = id_mask if override_id else name_mask
        conflict = bool(override_id and override_name and id_mask.any() and not (id_mask & name_mask).any())
        ambiguous = bool(not override_id and int(name_mask.sum()) != 1)
        if conflict or ambiguous or int(mask.sum()) != 1:
            diagnostics.append(
                {
                    "override_row": override_idx,
                    "status": "not applied",
                    "reason": "conflicting ID/name" if conflict else "ambiguous or unmatched identity",
                    "matched_rows": int(mask.sum()),
                }
            )
            continue

        target = out.index[mask][0]
        eligible_text = str(row.get("is_draft_eligible", "")).strip().casefold()
        eligible = eligible_text in {"true", "1", "yes", "y"}
        reason = str(row.get("reason", "")).strip() or "Eligibility override"
        out.at[target, "is_draft_eligible"] = eligible
        out.at[target, "is_free_agent"] = not eligible
        out.at[target, "draft_eligibility_status"] = (
            "Override eligible" if eligible else "Override ineligible"
        )
        out.at[target, "eligibility_source"] = "Curated override"
        out.at[target, "squad_match_method"] = "override by ID" if override_id else "override by unique name"
        out.at[target, "eligibility_reason"] = reason
        out.at[target, "eligibility_override"] = True
        team = normalize_team(row.get("current_team", ""))
        if team:
            out.at[target, "team_2627"] = team
            out.at[target, "current_epl_team"] = team
        diagnostics.append(
            {"override_row": override_idx, "status": "applied", "reason": reason, "matched_rows": 1}
        )
    out["eligibility_override"] = out["eligibility_override"].fillna(False).astype(bool)
    return out, pd.DataFrame(diagnostics, columns=diagnostic_columns)
