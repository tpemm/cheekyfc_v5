from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from analytics.draft.model import build_rankings as build_rankings_canonical
from analytics.draft.reliability import (
    normalize_team as normalize_team_canonical,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def discover(patterns: Iterable[str]) -> Path | None:
    for pattern in patterns:
        matches = sorted(PROJECT_ROOT.glob(pattern))
        if matches:
            return matches[0]
    return None


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig", low_memory=False)


def normalize_text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    text = html.unescape(str(value))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


TEAM_ALIASES = {
    "afc bournemouth": "BOU",
    "bournemouth": "BOU",
    "arsenal": "ARS",
    "aston villa": "AVL",
    "brentford": "BRE",
    "brighton and hove albion": "BHA",
    "brighton": "BHA",
    "burnley": "BUR",
    "chelsea": "CHE",
    "coventry city": "COV",
    "crystal palace": "CRY",
    "everton": "EVE",
    "hull city": "HUL",
    "leeds united": "LEE",
    "leeds": "LEE",
    "liverpool": "LIV",
    "manchester city": "MCI",
    "man city": "MCI",
    "manchester united": "MUN",
    "man united": "MUN",
    "newcastle united": "NEW",
    "newcastle": "NEW",
    "nottingham forest": "NFO",
    "nottm forest": "NFO",
    "sunderland": "SUN",
    "tottenham hotspur": "TOT",
    "tottenham": "TOT",
    "west ham united": "WHU",
    "west ham": "WHU",
    "wolverhampton wanderers": "WOL",
    "wolves": "WOL",
}




def normalize_player_id(value: object) -> str:
    """Normalize Fantrax IDs across API, bridge, and historical files.

    Historical exports commonly wrap IDs in asterisks (for example *06fv8*)
    while API files store the same ID as 06fv8.
    """
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip().casefold()
    text = re.sub(r"[^a-z0-9]", "", text)
    return text

def normalize_team(value: object) -> str:
    return normalize_team_canonical(value)


def choose_column(frame: pd.DataFrame, candidates: Iterable[str], required: bool = False) -> str | None:
    lookup = {str(column).casefold(): str(column) for column in frame.columns}
    for candidate in candidates:
        if candidate.casefold() in lookup:
            return lookup[candidate.casefold()]
    if required:
        raise KeyError("Missing required column. Tried: " + ", ".join(candidates))
    return None


def number(frame: pd.DataFrame, candidates: Iterable[str], default=np.nan) -> pd.Series:
    column = choose_column(frame, candidates)
    if column is None:
        return pd.Series(default, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce")


def percentile(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    ranked = numeric.rank(pct=True, method="average")
    if not higher_is_better:
        ranked = 1 - ranked
    return ranked.fillna(0.0) * 100


def percent_number(series: pd.Series) -> pd.Series:
    """Convert Fantrax percentage strings such as 100% or 12.5% to numbers."""
    return pd.to_numeric(
        series.astype(str).str.replace("%", "", regex=False).str.strip(),
        errors="coerce",
    )


def load_current_fantrax(path: Path) -> pd.DataFrame:
    """Load either the API lookup or Fantrax's downloadable player export."""
    raw = read_csv(path)
    id_col = choose_column(raw, ["ID", "api_player_id", "fantrax_player_id", "player_id"], required=True)
    name_col = choose_column(raw, ["Player", "api_player_name", "fantrax_player_name", "player_name", "name"], required=True)
    team_col = choose_column(raw, ["Team", "api_team_code", "team_code", "team", "team_short_name"], required=True)
    pos_col = choose_column(raw, ["Position", "api_position", "position", "positions"], required=True)

    output = pd.DataFrame({
        "fantrax_player_id": raw[id_col].map(normalize_player_id),
        "player_name": raw[name_col].astype(str).str.strip(),
        "team_2627": raw[team_col].map(normalize_team),
        "position_2627": raw[pos_col].astype(str).str.strip(),
        # Preserve provider eligibility separately from the canonical registry
        # position used by matching and analytics.
        "fantrax_position_eligibility": raw[pos_col].astype(str).str.strip(),
    })

    adp_col = choose_column(raw, [
        "ADP", "adp", "fantrax_adp", "average_draft_position", "avg_draft_position",
        "avgdraftposition", "draft_position"
    ])
    rank_col = choose_column(raw, [
        "RkOv", "rkov", "overall_rank", "adp_rank", "fantrax_adp_rank",
        "draft_rank", "consensus_rank", "rank"
    ])
    projected_points_col = choose_column(raw, [
        "FPts", "fpts", "projected_points", "fantrax_projected_points", "proj_points"
    ])
    projected_ppg_col = choose_column(raw, [
        "FP/G", "fp/g", "projected_ppg", "fantrax_projected_ppg", "proj_ppg"
    ])
    drafted_col = choose_column(raw, ["%D", "%d", "drafted_pct", "percent_drafted"])
    rostered_col = choose_column(raw, [
        "rostered_pct", "rostered_percent", "ownership_pct", "percent_owned"
    ])
    ros_col = choose_column(raw, ["Ros", "ros", "rest_of_season", "ros_rating"])
    plus_minus_col = choose_column(raw, ["+/-", "plus_minus", "change_pct"])
    status_col = choose_column(raw, ["Status", "status"])
    opponent_col = choose_column(raw, ["Opponent", "opponent"])

    output["fantrax_adp"] = pd.to_numeric(raw[adp_col], errors="coerce") if adp_col else np.nan
    output["fantrax_overall_rank"] = pd.to_numeric(raw[rank_col], errors="coerce") if rank_col else np.nan
    # Keep a market-rank alias for the existing value-vs-ADP logic. ADP remains
    # the preferred comparison where available.
    output["fantrax_adp_rank"] = output["fantrax_adp"]
    output["fantrax_projected_points"] = pd.to_numeric(raw[projected_points_col], errors="coerce") if projected_points_col else np.nan
    output["fantrax_projected_ppg"] = pd.to_numeric(raw[projected_ppg_col], errors="coerce") if projected_ppg_col else np.nan
    output["drafted_pct"] = percent_number(raw[drafted_col]) if drafted_col else np.nan
    output["rostered_pct"] = percent_number(raw[rostered_col]) if rostered_col else np.nan
    output["fantrax_ros_pct"] = percent_number(raw[ros_col]) if ros_col else np.nan
    output["fantrax_plus_minus_pct"] = percent_number(raw[plus_minus_col]) if plus_minus_col else np.nan
    output["fantrax_status"] = raw[status_col].astype(str).str.strip() if status_col else ""
    output["opening_opponent"] = raw[opponent_col].astype(str).str.strip() if opponent_col else ""
    output["player_name_key"] = output["player_name"].map(normalize_text)
    team_status = output["team_2627"].fillna("").astype(str).str.upper().str.strip()
    output["is_free_agent"] = team_status.eq("FA")
    output["is_draft_eligible"] = ~team_status.isin(["", "FA", "UNK", "N/A", "NA"])
    output["draft_eligibility_status"] = np.where(
        output["is_draft_eligible"], "Draft eligible", "Free agent / not current EPL roster"
    )
    return output[output["fantrax_player_id"].ne("")].drop_duplicates("fantrax_player_id", keep="last")




def load_current_epl_squads(squad_root: Path, teams_path: Path | None = None) -> tuple[pd.DataFrame, set[str], set[str]]:
    """Load cached FootballData.io squads and report covered/missing EPL clubs.

    FootballData.io is authoritative for current real-world club membership.
    Fantrax team/status fields are retained only as fantasy-market metadata.
    """
    squad_root = Path(squad_root)
    rows: list[dict[str, object]] = []
    covered_codes: set[str] = set()
    expected_codes: set[str] = set()

    if teams_path and Path(teams_path).exists():
        payload = json.loads(Path(teams_path).read_text(encoding="utf-8-sig"))
        for item in payload.get("data", {}).get("teams", []):
            team = item.get("team", {})
            code = normalize_team(team.get("team_name", ""))
            if code:
                expected_codes.add(code)

    for path in sorted(squad_root.glob("team_*_players.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            continue
        data = payload.get("data", {})
        team = data.get("team", {})
        team_name = str(team.get("team_name", "")).strip()
        team_code = normalize_team(team_name)
        if not team_code:
            continue
        covered_codes.add(team_code)
        for player in data.get("players", []) or []:
            aliases = {
                str(player.get("player_name", "")).strip(),
                str(player.get("known_name", "")).strip(),
                " ".join(filter(None, [str(player.get("first_name", "")).strip(), str(player.get("last_name", "")).strip()])),
            }
            aliases = {alias for alias in aliases if alias}
            rows.append({
                "footballdata_player_id": player.get("player_id"),
                "current_epl_team": team_code,
                "current_epl_team_name": team_name,
                "footballdata_player_name": str(player.get("known_name") or player.get("player_name") or "").strip(),
                "alias_keys": tuple(sorted({normalize_text(alias) for alias in aliases if normalize_text(alias)})),
            })

    missing_codes = expected_codes - covered_codes
    return pd.DataFrame(rows), covered_codes, missing_codes


def apply_current_squad_eligibility(
    frame: pd.DataFrame,
    squad_root: Path | None,
    teams_path: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply current-EPL club confirmation from cached FootballData.io squads.

    Squad matches can always confirm/update a player. Squad absence is used to
    exclude a player only when the cache contains all expected EPL clubs and
    every club has a plausibly complete roster (15+ players). This prevents
    partial API responses from excluding hundreds of valid players.
    """
    out = frame.copy()
    out["eligibility_source"] = "Fantrax fallback"
    out["squad_match_method"] = ""
    out["footballdata_player_id"] = np.nan
    out["footballdata_player_name"] = ""
    out["current_epl_team"] = out.get("team_2627", pd.Series("", index=out.index)).astype(str)

    if squad_root is None or not Path(squad_root).exists():
        return out, pd.DataFrame()

    squads, covered_codes, missing_codes = load_current_epl_squads(Path(squad_root), teams_path)
    if squads.empty:
        return out, pd.DataFrame()

    roster_counts = squads.groupby("current_epl_team").size().to_dict()
    expected_count = len(covered_codes | missing_codes)
    complete_coverage = (
        expected_count == 20
        and not missing_codes
        and len(covered_codes) == 20
        and all(roster_counts.get(code, 0) >= 15 for code in covered_codes)
    )

    alias_map: dict[str, list[int]] = {}
    team_aliases: dict[str, list[tuple[str, int]]] = {}
    for idx, row in squads.iterrows():
        team_code = str(row["current_epl_team"])
        for alias in row["alias_keys"]:
            alias_map.setdefault(alias, []).append(idx)
            team_aliases.setdefault(team_code, []).append((alias, idx))

    report_rows: list[dict[str, object]] = []
    for idx, row in out.iterrows():
        name_key = normalize_text(row.get("player_name", ""))
        fantrax_team = normalize_team(row.get("team_2627", ""))
        match_idx: int | None = None
        method = ""
        confidence = np.nan

        candidates = list(dict.fromkeys(alias_map.get(name_key, [])))
        if len(candidates) == 1:
            match_idx = candidates[0]
            method = "exact unique name"
            confidence = 1.0
        elif fantrax_team in covered_codes and name_key:
            scored: list[tuple[float, int]] = []
            for alias, candidate_idx in team_aliases.get(fantrax_team, []):
                scored.append((SequenceMatcher(None, name_key, alias).ratio(), candidate_idx))
            scored.sort(reverse=True)
            if scored:
                best_score, best_idx = scored[0]
                second_score = scored[1][0] if len(scored) > 1 else 0.0
                if best_score >= 0.92 and (best_score - second_score) >= 0.04:
                    match_idx = best_idx
                    method = "fuzzy within listed club"
                    confidence = best_score

        if match_idx is not None:
            squad = squads.loc[match_idx]
            out.at[idx, "is_draft_eligible"] = True
            out.at[idx, "is_free_agent"] = False
            out.at[idx, "team_2627"] = squad["current_epl_team"]
            out.at[idx, "current_epl_team"] = squad["current_epl_team"]
            out.at[idx, "footballdata_player_id"] = squad["footballdata_player_id"]
            out.at[idx, "footballdata_player_name"] = squad["footballdata_player_name"]
            out.at[idx, "draft_eligibility_status"] = "Current EPL squad"
            out.at[idx, "eligibility_source"] = "FootballData.io"
            out.at[idx, "squad_match_method"] = method
        elif complete_coverage:
            out.at[idx, "is_draft_eligible"] = False
            out.at[idx, "is_free_agent"] = True
            out.at[idx, "current_epl_team"] = "FA"
            out.at[idx, "draft_eligibility_status"] = "Not found on a complete current EPL squad cache"
            out.at[idx, "eligibility_source"] = "FootballData.io"
            out.at[idx, "squad_match_method"] = "not matched in complete cache"
        else:
            # Keep the existing Fantrax-derived decision until the API cache is
            # complete. Explicit manual overrides are applied after this step.
            out.at[idx, "draft_eligibility_status"] = "Unverified: current squad cache incomplete"
            out.at[idx, "eligibility_source"] = "Fantrax fallback (incomplete squad cache)"
            out.at[idx, "squad_match_method"] = "cache incomplete"

        report_rows.append({
            "fantrax_player_id": row.get("fantrax_player_id", ""),
            "player_name": row.get("player_name", ""),
            "fantrax_team": fantrax_team,
            "current_epl_team": out.at[idx, "current_epl_team"],
            "is_draft_eligible": bool(out.at[idx, "is_draft_eligible"]),
            "eligibility_source": out.at[idx, "eligibility_source"],
            "squad_match_method": out.at[idx, "squad_match_method"],
            "match_confidence": confidence,
            "complete_squad_coverage": complete_coverage,
            "covered_clubs": len(covered_codes),
            "missing_clubs": ", ".join(sorted(missing_codes)),
        })

    return out, pd.DataFrame(report_rows)


def parse_bool(value: object) -> bool | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip().casefold()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return None


def apply_eligibility_overrides(frame: pd.DataFrame, override_path: Path | None) -> pd.DataFrame:
    """Apply explicit current-EPL eligibility decisions.

    Fantrax preseason ``Status = FA`` means fantasy free agent (undrafted),
    not that the player lacks a real-world club. Real-world eligibility is
    therefore maintained separately in a small override file.
    """
    out = frame.copy()
    if override_path is None or not Path(override_path).exists():
        return out

    overrides = read_csv(Path(override_path))
    if overrides.empty:
        return out

    id_col = choose_column(overrides, ["fantrax_player_id", "player_id", "id"])
    name_col = choose_column(overrides, ["player_name", "player", "name"])
    eligible_col = choose_column(overrides, ["is_draft_eligible", "draft_eligible", "eligible"])
    team_col = choose_column(overrides, ["current_team", "team_2627", "team"])
    reason_col = choose_column(overrides, ["reason", "eligibility_reason", "note"])

    if not eligible_col or (not id_col and not name_col):
        return out

    out_id = out.get("fantrax_player_id", pd.Series("", index=out.index)).map(normalize_player_id)
    out_name = out.get("player_name", pd.Series("", index=out.index)).map(normalize_text)

    for _, row in overrides.iterrows():
        mask = pd.Series(False, index=out.index)
        if id_col and normalize_player_id(row.get(id_col)):
            mask |= out_id.eq(normalize_player_id(row.get(id_col)))
        if name_col and normalize_text(row.get(name_col)):
            mask |= out_name.eq(normalize_text(row.get(name_col)))
        if not mask.any():
            continue

        eligible = parse_bool(row.get(eligible_col))
        if eligible is not None:
            out.loc[mask, "is_draft_eligible"] = eligible
            out.loc[mask, "is_free_agent"] = not eligible
        if team_col and pd.notna(row.get(team_col)) and str(row.get(team_col)).strip():
            out.loc[mask, "team_2627"] = str(row.get(team_col)).strip().upper()
        reason = str(row.get(reason_col)).strip() if reason_col and pd.notna(row.get(reason_col)) else "Eligibility override"
        out.loc[mask, "draft_eligibility_status"] = ("Draft eligible" if eligible else reason)
        out.loc[mask, "eligibility_override"] = True

    if "eligibility_override" not in out.columns:
        out["eligibility_override"] = False
    out["eligibility_override"] = out["eligibility_override"].fillna(False).astype(bool)
    return out


def build_historical_player_summary(master: pd.DataFrame) -> pd.DataFrame:
    id_col = choose_column(master, ["fantrax_player_id", "player_id", "api_player_id"], required=True)
    name_col = choose_column(master, ["player_name_display", "player_name", "fantrax_player_name", "name"], required=True)
    gw_col = choose_column(master, ["fantrax_gw", "gw", "gameweek"])
    team_col = choose_column(
        master,
        ["avail_team", "mgr_team", "fantrax_team_name", "team", "team_name", "fantrax_team", "club"],
    )
    pos_col = choose_column(
        master,
        ["avail_position", "mgr_position", "fantrax_position", "position", "positions"],
    )

    working = pd.DataFrame({
        "fantrax_player_id": master[id_col].map(normalize_player_id),
        "historical_name": master[name_col].where(master[name_col].notna(), "").astype(str).str.strip(),
        "historical_team": master[team_col].map(normalize_team) if team_col else "",
        "historical_position": master[pos_col].where(master[pos_col].notna(), "").astype(str).str.strip() if pos_col else "",
        "gw": number(master, ["fantrax_gw", "gw", "gameweek"]),
        "minutes": number(master, ["mgr_min", "minutes", "fantrax_minutes", "num_minutes"]),
        "fantasy_points": number(master, [
            "official_fantasy_points", "mgr_fantasy_points", "fantasy_points",
            "num_fantasy_points", "fpts"
        ]),
        "ghost_points": number(master, [
            "ghost_points", "ghost_points_total", "non_gacs_points",
            "ghost_fantasy_points"
        ]),
        "goals": number(master, ["mgr_g", "goals", "num_goals"]),
        "assists": number(master, ["mgr_at", "assists_total", "assists", "num_assists_total"]),
        "starts": number(master, ["mgr_gs", "starts", "num_starts", "started"]),
        "understat_xg": number(master, ["understat_xg", "xg"]),
        "understat_xa": number(master, ["understat_xa", "xa"]),
        "understat_npxg": number(master, ["understat_npxg", "npxg", "np_xg"]),
        "understat_key_passes": number(master, ["understat_key_passes", "key_passes"]),
        "understat_minutes": number(master, ["understat_minutes", "minutes"]),
        "understat_player_id": (
            master[choose_column(master, ["understat_player_id"])].astype(str)
            if choose_column(master, ["understat_player_id"]) else ""
        ),
    })

    # Master weekly files may repeat season totals or contain weekly values.
    # Prefer a weekly sum, but only across one row per player-week.
    working = working.sort_values(["fantrax_player_id", "gw"]).drop_duplicates(
        ["fantrax_player_id", "gw"], keep="last"
    )

    # Fallback start proxy where an explicit start field is absent.
    if working["starts"].isna().all():
        working["starts"] = (working["minutes"] >= 60).astype(float)

    max_gw = working["gw"].max()
    recent = working[working["gw"] >= max_gw - 5].copy() if pd.notna(max_gw) else working.iloc[0:0]

    def latest_nonempty(values: pd.Series) -> object:
        usable = values[
            values.notna()
            & values.astype(str).str.strip().ne("")
            & ~values.astype(str).str.casefold().isin({"nan", "none"})
        ]
        return usable.iloc[-1] if not usable.empty else pd.NA

    agg = working.groupby("fantrax_player_id", as_index=False).agg(
        historical_name=("historical_name", latest_nonempty),
        team_2526=("historical_team", latest_nonempty),
        position_2526=("historical_position", latest_nonempty),
        weeks_available=("gw", "nunique"),
        minutes_2526=("minutes", "sum"),
        starts_2526=("starts", "sum"),
        fantasy_points_2526=("fantasy_points", "sum"),
        ghost_points_2526=("ghost_points", "sum"),
        goals_2526=("goals", "sum"),
        assists_2526=("assists", "sum"),
        understat_xg_2526=("understat_xg", "sum"),
        understat_xa_2526=("understat_xa", "sum"),
        understat_npxg_2526=("understat_npxg", "sum"),
        understat_key_passes_2526=("understat_key_passes", "sum"),
        understat_minutes_2526=("understat_minutes", "sum"),
        understat_player_id=("understat_player_id", "last"),
    )

    recent_agg = recent.groupby("fantrax_player_id", as_index=False).agg(
        recent_minutes_6=("minutes", "sum"),
        recent_starts_6=("starts", "sum"),
        recent_fp_6=("fantasy_points", "sum"),
    )
    agg = agg.merge(recent_agg, on="fantrax_player_id", how="left")

    played_weeks = agg["weeks_available"].replace(0, np.nan)
    minutes = agg["minutes_2526"].replace(0, np.nan)
    agg["fantasy_ppg_2526"] = agg["fantasy_points_2526"] / played_weeks
    agg["ghost_ppg_2526"] = agg["ghost_points_2526"] / played_weeks
    agg["fantasy_fp90_2526"] = agg["fantasy_points_2526"] / minutes * 90
    agg["xgi90_2526"] = (
        agg["understat_xg_2526"].fillna(0) + agg["understat_xa_2526"].fillna(0)
    ) / agg["understat_minutes_2526"].replace(0, np.nan) * 90
    agg["start_rate_2526"] = agg["starts_2526"] / played_weeks
    agg["recent_start_rate_6"] = agg["recent_starts_6"] / 6
    agg["has_historical_identity"] = True
    agg["has_historical_data"] = True
    agg["historical_match_status"] = "matched by historical Fantrax ID"
    agg["historical_match_method"] = "normalized Fantrax ID"
    agg["historical_match_confidence"] = 1.0
    return agg


def attach_bridge(current: pd.DataFrame, bridge_path: Path | None) -> pd.DataFrame:
    if bridge_path is None or not bridge_path.exists():
        current["historical_fantrax_player_id"] = current["fantrax_player_id"]
        return current

    bridge = read_csv(bridge_path)
    api_col = choose_column(bridge, ["api_player_id", "fantrax_api_player_id"], required=True)
    historical_col = choose_column(bridge, ["fantrax_player_id", "master_player_id"], required=True)
    keep = pd.DataFrame({
        "fantrax_player_id": bridge[api_col].map(normalize_player_id),
        "historical_fantrax_player_id": bridge[historical_col].map(normalize_player_id),
    }).drop_duplicates("fantrax_player_id", keep="last")
    output = current.merge(keep, on="fantrax_player_id", how="left")
    output["historical_fantrax_player_id"] = output["historical_fantrax_player_id"].fillna(output["fantrax_player_id"])
    return output


def attach_ghost_points(players: pd.DataFrame, ghost_path: Path | None) -> pd.DataFrame:
    """Attach authoritative player ghost totals from the existing analytics view."""
    out = players.copy()
    if ghost_path is None or not ghost_path.exists():
        return out

    raw = read_csv(ghost_path)
    id_col = choose_column(raw, ["fantrax_player_id", "player_id", "api_player_id"], required=True)
    total_col = choose_column(raw, ["total_ghost_points", "ghost_points_2526", "ghost_points"])
    avg_col = choose_column(raw, ["avg_ghost_points", "ghost_ppg_2526", "ghost_ppg"])
    appearances_col = choose_column(raw, ["appearances", "weeks_available", "games_played"])
    fantasy_col = choose_column(raw, ["total_fantasy_points", "fantasy_points_2526"])

    ghost = pd.DataFrame({
        "historical_fantrax_player_id": raw[id_col].map(normalize_player_id),
        "ghost_points_2526_authoritative": pd.to_numeric(raw[total_col], errors="coerce") if total_col else np.nan,
        "ghost_ppg_2526_authoritative": pd.to_numeric(raw[avg_col], errors="coerce") if avg_col else np.nan,
        "ghost_appearances_2526": pd.to_numeric(raw[appearances_col], errors="coerce") if appearances_col else np.nan,
        "ghost_source_fantasy_points_2526": pd.to_numeric(raw[fantasy_col], errors="coerce") if fantasy_col else np.nan,
    }).drop_duplicates("historical_fantrax_player_id", keep="last")

    out = out.merge(ghost, on="historical_fantrax_player_id", how="left")
    out["ghost_points_2526"] = out["ghost_points_2526_authoritative"].combine_first(out.get("ghost_points_2526"))
    calculated_ppg = out["ghost_points_2526_authoritative"] / out["ghost_appearances_2526"].replace(0, np.nan)
    out["ghost_ppg_2526"] = (
        out["ghost_ppg_2526_authoritative"]
        .combine_first(calculated_ppg)
        .combine_first(out.get("ghost_ppg_2526"))
    )
    out["ghost_fp90_2526"] = out["ghost_points_2526"] / out["minutes_2526"].replace(0, np.nan) * 90
    fantasy_denominator = out["ghost_source_fantasy_points_2526"].combine_first(out["fantasy_points_2526"])
    out["ghost_share_pct_2526"] = out["ghost_points_2526"] / fantasy_denominator.replace(0, np.nan) * 100
    return out


def attach_team_context(players: pd.DataFrame, team_strength: pd.DataFrame, fixtures: pd.DataFrame) -> pd.DataFrame:
    ts_team = choose_column(team_strength, ["team_code", "team_short_name", "team_name", "team"], required=True)
    ts = team_strength.copy()
    ts["team_2627"] = ts[ts_team].map(normalize_team)

    attack_col = choose_column(ts, ["attack_rating", "team_attack_rating", "attack_strength", "attack_index"])
    defense_col = choose_column(ts, ["defense_rating", "team_defense_rating", "defense_strength", "defense_index"])
    overall_col = choose_column(ts, ["overall_team_rating", "overall_rating", "team_strength_rating", "team_strength", "strength_rating"])

    team_context = pd.DataFrame({"team_2627": ts["team_2627"]})
    team_context["team_attack_rating"] = pd.to_numeric(ts[attack_col], errors="coerce") if attack_col else np.nan
    team_context["team_defense_rating"] = pd.to_numeric(ts[defense_col], errors="coerce") if defense_col else np.nan
    team_context["team_strength_rating"] = pd.to_numeric(ts[overall_col], errors="coerce") if overall_col else np.nan
    team_context = team_context.drop_duplicates("team_2627", keep="last")

    fx_team = choose_column(fixtures, ["team_code", "team_name", "team", "perspective_team"], required=True)
    ease_col = choose_column(fixtures, ["overall_fixture_ease", "fixture_ease", "attacker_fixture_ease"])
    diff_col = choose_column(fixtures, ["fixture_difficulty"])
    order_col = choose_column(fixtures, ["game_week", "game_week_estimate", "fixture_order", "match_date"])

    fx = fixtures.copy()
    fx["team_2627"] = fx[fx_team].map(normalize_team)
    fx["fixture_order_value"] = (
        pd.to_numeric(fx[order_col], errors="coerce") if order_col else np.arange(len(fx))
    )
    if ease_col:
        fx["fixture_ease_value"] = pd.to_numeric(fx[ease_col], errors="coerce")
    elif diff_col:
        fx["fixture_ease_value"] = 100 - pd.to_numeric(fx[diff_col], errors="coerce")
    else:
        fx["fixture_ease_value"] = np.nan

    fx = fx.sort_values(["team_2627", "fixture_order_value"])
    fixture_context = fx.groupby("team_2627", as_index=False).agg(
        fixture_ease_next_3=("fixture_ease_value", lambda x: x.head(3).mean()),
        fixture_ease_next_5=("fixture_ease_value", lambda x: x.head(5).mean()),
        fixture_ease_next_10=("fixture_ease_value", lambda x: x.head(10).mean()),
    )

    return players.merge(team_context, on="team_2627", how="left").merge(
        fixture_context, on="team_2627", how="left"
    )


def build_minutes_outlook(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()

    season_share = (out["minutes_2526"] / (38 * 90)).clip(0, 1)
    recent_share = (out["recent_minutes_6"] / (6 * 90)).clip(0, 1)
    start_rate = out["start_rate_2526"].clip(0, 1)
    recent_start = out["recent_start_rate_6"].clip(0, 1)

    known_history = out["minutes_2526"].fillna(0) > 0
    if "registry_status" in out.columns:
        same_team = ~out["registry_status"].eq("Transferred")
    else:
        same_team = out["team_2526"].fillna("").eq(out["team_2627"].fillna(""))

    minutes_score = (
        0.40 * season_share.fillna(0)
        + 0.30 * recent_share.fillna(0)
        + 0.20 * start_rate.fillna(0)
        + 0.10 * recent_start.fillna(0)
    ) * 100

    # Small uncertainty penalty for a detected transfer.
    minutes_score = minutes_score - np.where(known_history & ~same_team, 8, 0)
    out["projected_minutes_share"] = minutes_score.clip(0, 100).round(1)

    out["minutes_outlook"] = pd.cut(
        out["projected_minutes_share"],
        bins=[-1, 20, 45, 68, 84, 101],
        labels=["Bench / Unknown", "Rotation Risk", "Likely Rotation", "Likely Starter", "Locked Starter"],
    ).astype(str)

    out.loc[~known_history, "minutes_outlook"] = "Unknown / New Arrival"
    out["minutes_confidence"] = np.select(
        [
            out["minutes_2526"].fillna(0) >= 2200,
            out["minutes_2526"].fillna(0) >= 1200,
            out["minutes_2526"].fillna(0) > 0,
        ],
        [90, 75, 55],
        default=25,
    )
    out.loc[known_history & ~same_team, "minutes_confidence"] -= 15
    out["minutes_confidence"] = out["minutes_confidence"].clip(0, 100)
    out["team_changed"] = known_history & ~same_team
    return out


def build_rankings(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()

    production = (
        0.60 * percentile(out["fantasy_ppg_2526"])
        + 0.40 * percentile(out["fantasy_fp90_2526"])
    )
    ghost = percentile(out["ghost_ppg_2526"])
    attacking = percentile(out["xgi90_2526"])
    minutes = out["projected_minutes_share"].fillna(0)
    team = (
        0.65 * percentile(out["team_attack_rating"])
        + 0.35 * percentile(out["team_strength_rating"])
    )
    fixtures = percentile(out["fixture_ease_next_5"])

    out["production_score"] = production.round(1)
    out["ghost_score"] = ghost.round(1)
    out["attacking_score"] = attacking.round(1)
    out["minutes_score"] = minutes.round(1)
    out["team_context_score"] = team.round(1)
    out["fixture_score"] = fixtures.round(1)

    out["draft_score"] = (
        0.30 * production
        + 0.20 * minutes
        + 0.15 * ghost
        + 0.15 * attacking
        + 0.10 * team
        + 0.10 * fixtures
    ).round(2)

    out["data_confidence"] = (
        0.45 * out["minutes_confidence"].fillna(0)
        + 25 * out["fantasy_points_2526"].notna().astype(int)
        + 20 * out["understat_player_id"].replace("", np.nan).notna().astype(int)
        + 10 * out["team_strength_rating"].notna().astype(int)
    ).clip(0, 100).round(1)

    if "is_draft_eligible" not in out.columns:
        team_status = out["team_2627"].fillna("").astype(str).str.upper().str.strip()
        out["is_free_agent"] = team_status.eq("FA")
        out["is_draft_eligible"] = ~team_status.isin(["", "FA", "UNK", "N/A", "NA"])
        out["draft_eligibility_status"] = np.where(
            out["is_draft_eligible"], "Draft eligible", "Free agent / not current EPL roster"
        )

    out = out.sort_values(
        ["is_draft_eligible", "draft_score", "data_confidence", "fantasy_ppg_2526"],
        ascending=[False, False, False, False],
    ).reset_index(drop=True)

    eligible_mask = out["is_draft_eligible"].fillna(False)
    out["overall_rank"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
    out.loc[eligible_mask, "overall_rank"] = np.arange(1, int(eligible_mask.sum()) + 1)

    out["tier"] = pd.Series(pd.NA, index=out.index, dtype="object")
    out.loc[eligible_mask, "tier"] = pd.cut(
        pd.to_numeric(out.loc[eligible_mask, "overall_rank"], errors="coerce"),
        bins=[0, 12, 36, 72, 120, 180, 300, np.inf],
        labels=["Tier 1", "Tier 2", "Tier 3", "Tier 4", "Tier 5", "Tier 6", "Deep"],
    ).astype(str).values

    adp_reference = out["fantrax_adp"]
    out["value_vs_adp"] = np.where(
        eligible_mask & adp_reference.notna(),
        adp_reference - pd.to_numeric(out["overall_rank"], errors="coerce"),
        np.nan,
    )
    out["adp_status"] = np.select(
        [
            ~eligible_mask,
            adp_reference.isna(),
            out["value_vs_adp"] >= 20,
            out["value_vs_adp"] >= 8,
            out["value_vs_adp"] <= -20,
            out["value_vs_adp"] <= -8,
        ],
        ["Not draft eligible", "ADP unavailable", "Strong value", "Value", "Major reach", "Reach"],
        default="Near market",
    )
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fantrax-pool", type=Path)
    parser.add_argument("--master", type=Path)
    parser.add_argument("--bridge", type=Path)
    parser.add_argument("--team-strength", type=Path)
    parser.add_argument("--fixtures", type=Path)
    parser.add_argument("--fantrax-export", type=Path)
    parser.add_argument("--ghost-leaders", type=Path)
    parser.add_argument("--eligibility-overrides", type=Path)
    parser.add_argument("--squad-root", type=Path)
    parser.add_argument("--teams-file", type=Path)
    parser.add_argument("--player-registry", type=Path)
    args = parser.parse_args()

    fantrax_path = args.fantrax_pool or discover([
        "processed_data/fantrax_api/api_player_lookup.csv",
        "data/**/api_player_lookup.csv",
        "**/api_player_lookup.csv",
    ])
    fantrax_export_path = args.fantrax_export or discover([
        "data/imports/draft/Fantrax-Players*.csv",
        "data/raw/draft/Fantrax-Players*.csv",
        "Fantrax-Players*.csv",
    ])
    master_path = args.master or discover([
        "data/**/master_player_weekly_2526.csv",
        "**/master_player_weekly_2526.csv",
    ])
    bridge_path = args.bridge or discover([
        "data/reference/api_to_master_player_id_bridge_2526.csv",
        "**/api_to_master_player_id_bridge_2526.csv",
    ])
    ghost_path = args.ghost_leaders or discover([
        "data/seasons/2526/analytics_views/ghost_points_player_leaders.csv",
        "data/analytics_views/ghost_points_player_leaders.csv",
        "**/ghost_points_player_leaders.csv",
    ])
    team_strength_path = args.team_strength or discover([
        "data/analytics/draft/team_strength_2526.csv",
        "**/team_strength_2526.csv",
    ])
    fixtures_path = args.fixtures or discover([
        "data/analytics/draft/fixture_difficulty_2627.csv",
        "**/fixture_difficulty_2627.csv",
    ])
    squad_root = args.squad_root or (PROJECT_ROOT / "data" / "raw" / "footballdata_io" / "full_refresh" / "players")
    teams_file = args.teams_file or discover([
        "data/raw/footballdata_io/coverage_test/teams_2627.json",
        "**/teams_2627.json",
    ])
    eligibility_override_path = args.eligibility_overrides or discover([
        "data/imports/draft/draft_eligibility_overrides_2627.csv",
        "**/draft_eligibility_overrides_2627.csv",
    ])
    player_registry_path = args.player_registry or discover([
        "data/reference/player_registry_2627.csv",
        "**/player_registry_2627.csv",
    ])

    required = {
        "2026/27 Fantrax player pool": fantrax_path,
        "2025/26 master weekly": master_path,
        "team strength": team_strength_path,
        "2026/27 fixture difficulty": fixtures_path,
        "2026/27 player registry": player_registry_path,
    }
    missing = [f"{label}: {path}" for label, path in required.items() if path is None or not Path(path).exists()]
    if missing:
        raise FileNotFoundError("Missing required inputs:\n  - " + "\n  - ".join(missing))

    print(f"Fantrax target pool: {fantrax_path}")
    print(f"Fantrax preseason export: {fantrax_export_path or 'not found; API pool only'}")
    print(f"Historical master: {master_path}")
    print(f"Historical bridge: {bridge_path or 'not found; direct IDs will be used'}")
    print(f"Ghost leaders: {ghost_path or 'not found; master columns only'}")
    print(f"Team strength: {team_strength_path}")
    print(f"Fixtures: {fixtures_path}")
    print(f"Current EPL squads: {squad_root if Path(squad_root).exists() else 'not found'}")
    print(f"Current EPL teams file: {teams_file or 'not found'}")
    print(f"Eligibility overrides: {eligibility_override_path or 'not found'}")
    print(f"Player registry: {player_registry_path}")

    current = load_current_fantrax(fantrax_export_path or fantrax_path)
    registry = read_csv(player_registry_path)
    registry = registry[registry["fantrax_player_id"].fillna("").astype(str).str.strip().ne("")].copy()
    registry["fantrax_player_id"] = registry["fantrax_player_id"].map(normalize_player_id)
    registry_fields = [
        "fantrax_player_id", "registry_player_id", "fpl_player_id",
        "historical_player_id", "canonical_name", "fpl_name",
        "current_team", "current_team_code", "current_position", "active_epl",
        "availability_status", "injury_news", "historical_team",
        "historical_position", "registry_status", "match_method",
        "identity_confidence", "source", "last_verified",
    ]
    current = current.merge(
        registry[[c for c in registry_fields if c in registry.columns]],
        on="fantrax_player_id",
        how="left",
        validate="one_to_one",
    )
    current["historical_fantrax_player_id"] = current["historical_player_id"].fillna(
        current["fantrax_player_id"]
    ).map(normalize_player_id)
    current["team_2627"] = current["current_team_code"].combine_first(
        current["team_2627"]
    ).map(normalize_team)
    current["position_2627"] = current["current_position"].combine_first(
        current["position_2627"]
    )
    unresolved_registry = current["registry_status"].fillna("Unresolved").eq("Unresolved")
    current["is_draft_eligible"] = (
        current["active_epl"].fillna(False).astype(bool) | unresolved_registry
    )
    current["is_free_agent"] = ~current["is_draft_eligible"]
    current["draft_eligibility_status"] = np.select(
        [
            current["active_epl"].fillna(False).astype(bool),
            unresolved_registry,
        ],
        ["Matched eligible", "Unresolved: no current FPL identity"],
        default="Inactive / historical only",
    )
    current["eligibility_source"] = "Player Registry"
    current["squad_match_method"] = current["match_method"].fillna("Unresolved")
    current["current_epl_team"] = current["current_team_code"].fillna(current["team_2627"])
    current["eligibility_reason"] = current["registry_status"].fillna("Unresolved")
    current["eligibility_override"] = current["registry_status"].eq("Confirmed Override")
    history = build_historical_player_summary(read_csv(master_path))

    current_ids = set(current["historical_fantrax_player_id"].dropna())
    historical_ids = set(history["fantrax_player_id"].dropna())
    print(f"Normalized current IDs: {len(current_ids):,}")
    print(f"Normalized historical IDs: {len(historical_ids):,}")
    print(f"Direct historical ID overlap: {len(current_ids & historical_ids):,}")

    pool = current.merge(
        history,
        left_on="historical_fantrax_player_id",
        right_on="fantrax_player_id",
        how="left",
        suffixes=("", "_historical"),
    )
    pool = pool.drop(columns=["fantrax_player_id_historical"], errors="ignore")
    pool["has_historical_identity"] = pool["has_historical_identity"].fillna(False).astype(bool)
    pool["has_historical_data"] = pool["has_historical_data"].fillna(False).astype(bool)
    pool["historical_match_status"] = pool["historical_match_status"].fillna(
        "no 2025/26 record for bridged ID"
    )
    pool["historical_match_method"] = pool["historical_match_method"].fillna("none")
    pool["historical_match_confidence"] = pool["historical_match_confidence"].fillna(0.0)
    historical_columns = [
        "weeks_available", "minutes_2526", "starts_2526", "fantasy_points_2526",
        "ghost_points_2526", "goals_2526", "assists_2526", "understat_xg_2526",
        "understat_xa_2526", "understat_npxg_2526", "understat_key_passes_2526",
        "understat_minutes_2526", "recent_minutes_6", "recent_starts_6",
        "recent_fp_6", "fantasy_ppg_2526", "ghost_ppg_2526",
        "fantasy_fp90_2526", "xgi90_2526", "start_rate_2526",
        "recent_start_rate_6",
    ]
    no_history = ~pool["has_historical_data"]
    pool.loc[no_history, [c for c in historical_columns if c in pool.columns]] = np.nan
    pool = attach_ghost_points(pool, ghost_path)
    pool = attach_team_context(pool, read_csv(team_strength_path), read_csv(fixtures_path))
    pool = build_minutes_outlook(pool)
    eligibility_report = pool[
        [
            "fantrax_player_id", "player_name", "team_2627",
            "current_epl_team", "is_draft_eligible",
            "draft_eligibility_status", "eligibility_source",
            "squad_match_method", "fpl_player_id", "fpl_name",
            "eligibility_override", "eligibility_reason",
        ]
    ].rename(
        columns={
            "team_2627": "fantrax_team",
            "current_epl_team": "matched_current_team",
            "fpl_player_id": "matched_external_player_id",
            "fpl_name": "matched_external_player_name",
            "eligibility_reason": "diagnostic_reason",
        }
    )
    squad_coverage = (
        registry.groupby("current_team_code", as_index=False)
        .agg(player_count=("registry_player_id", "count"))
        .rename(columns={"current_team_code": "team_code"})
    )
    squad_coverage["source_system"] = "Player Registry / Official FPL API"
    override_report = pd.DataFrame(
        columns=["override_row", "status", "reason", "matched_rows"]
    )
    rankings = build_rankings_canonical(pool)

    out_dir = PROJECT_ROOT / "data" / "models" / "draft_2627"
    out_dir.mkdir(parents=True, exist_ok=True)
    quality_dir = PROJECT_ROOT / "data" / "quality" / "draft_2627"
    quality_dir.mkdir(parents=True, exist_ok=True)

    pool_path = out_dir / "draft_player_pool_2627.csv"
    ranking_path = out_dir / "draft_rankings_2627.csv"
    quality_path = quality_dir / "draft_data_quality_2627.csv"
    eligibility_path = quality_dir / "draft_eligibility_report_2627.csv"
    identity_path = quality_dir / "draft_identity_report_2627.csv"
    squad_coverage_path = quality_dir / "draft_squad_coverage_2627.csv"
    override_report_path = quality_dir / "draft_override_report_2627.csv"

    pool.to_csv(pool_path, index=False, encoding="utf-8-sig")
    rankings.to_csv(ranking_path, index=False, encoding="utf-8-sig")

    quality = rankings[
        rankings["historical_name"].isna()
        | rankings["team_strength_rating"].isna()
        | rankings["fixture_ease_next_5"].isna()
        | rankings["data_confidence"].lt(60)
    ].copy()
    quality.to_csv(quality_path, index=False, encoding="utf-8-sig")
    eligibility_report.to_csv(eligibility_path, index=False, encoding="utf-8-sig")
    identity_columns = [
        "fantrax_player_id", "player_name", "team_2627",
        "historical_fantrax_player_id", "historical_name", "team_2526",
        "position_2526", "has_historical_identity", "has_historical_data",
        "historical_match_status", "historical_match_method",
        "historical_match_confidence",
    ]
    rankings[[c for c in identity_columns if c in rankings.columns]].to_csv(
        identity_path, index=False, encoding="utf-8-sig"
    )
    squad_coverage.to_csv(squad_coverage_path, index=False, encoding="utf-8-sig")
    override_report.to_csv(override_report_path, index=False, encoding="utf-8-sig")

    print("\nDraft Tool v1.2.1 data build complete.")
    print(f"Current Fantrax players: {len(rankings):,}")
    print(f"With historical Fantrax data: {rankings['has_historical_data'].fillna(False).sum():,}")
    print(f"With Understat identity: {rankings['understat_player_id'].replace('', np.nan).notna().sum():,}")
    print(f"With team context: {rankings['team_strength_rating'].notna().sum():,}")
    print(f"With fixture context: {rankings['fixture_ease_next_5'].notna().sum():,}")
    print(f"With ghost-point history: {rankings['ghost_points_2526'].notna().sum():,}")
    print(f"With ADP: {rankings['fantrax_adp'].notna().sum():,}")
    print(f"With Fantrax projections: {rankings['fantrax_projected_points'].notna().sum():,}")
    print(f"Draft eligible from current squads: {rankings['is_draft_eligible'].fillna(False).sum():,}")
    print(f"\nSaved: {pool_path}")
    print(f"Saved: {ranking_path}")
    print(f"Saved: {quality_path}")
    print(f"Saved: {eligibility_path}")
    print(f"Saved: {identity_path}")
    print(f"Saved: {squad_coverage_path}")
    print(f"Saved: {override_report_path}")


if __name__ == "__main__":
    main()
