"""Deterministic completed-draft ingestion and grading from a frozen snapshot."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from analytics.draft.presentation import normalize_fantrax_positions
from analytics.draft.team import RosterSlot, assign_roster_slots


EXPECTED_PICKS = 180
EXPECTED_MANAGERS = 12
PICKS_PER_MANAGER = 15
ROUND_WEIGHTS = {**dict.fromkeys(range(1, 4), 1.50), **dict.fromkeys(range(4, 7), 1.25),
                 **dict.fromkeys(range(7, 11), 1.00), **dict.fromkeys(range(11, 14), .80),
                 **dict.fromkeys(range(14, 16), .65)}
PICK_WEIGHTS = {"draft_quality": .30, "market_value": .25, "model_value": .15,
                "tier_value": .10, "roster_fit": .10, "minutes_security": .05,
                "data_confidence": .05}
MANAGER_WEIGHTS = {"projected_production": .20, "historical_production": .15,
                   "floor": .15, "playing_time_security": .15, "draft_value": .15,
                   "attacking_upside": .10, "roster_construction": .10}
LETTER_THRESHOLDS = ((97, "A+"), (93, "A"), (90, "A-"), (87, "B+"), (83, "B"),
                     (80, "B-"), (77, "C+"), (73, "C"), (70, "C-"), (67, "D+"),
                     (63, "D"), (60, "D-"), (0, "F"))
DRAFT_RESULT_ALIASES = {
    "r schade": "kevin schade",
    "d jacquet": "jeremy jacquet",
}


class DraftValidationError(ValueError):
    pass


@dataclass(frozen=True)
class DraftBuildResult:
    validation: pd.DataFrame
    matches: pd.DataFrame
    canonical: pd.DataFrame
    picks: pd.DataFrame
    managers: pd.DataFrame
    categories: pd.DataFrame
    awards: pd.DataFrame


def normalize_name(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char)).casefold()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def validate_draft_results(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"Overall Pick", "Round", "Pick in Round", "Draft Slot", "Manager", "Player", "Position", "Club"}
    checks: list[tuple[str, bool, str]] = []
    missing = sorted(required - set(frame))
    checks.append(("required_columns", not missing, ", ".join(missing)))
    if missing:
        return pd.DataFrame(checks, columns=["check", "passed", "detail"])
    numeric = frame[["Overall Pick", "Round", "Pick in Round", "Draft Slot"]].apply(pd.to_numeric, errors="coerce")
    checks.extend([
        ("row_count", len(frame) == EXPECTED_PICKS, f"actual={len(frame)} expected={EXPECTED_PICKS}"),
        ("manager_count", frame["Manager"].nunique() == EXPECTED_MANAGERS, f"actual={frame['Manager'].nunique()} expected={EXPECTED_MANAGERS}"),
        ("manager_pick_count", bool(frame.groupby("Manager").size().eq(PICKS_PER_MANAGER).all()), str(frame.groupby("Manager").size().to_dict())),
        ("overall_pick_unique", not numeric["Overall Pick"].duplicated().any(), ""),
        ("overall_pick_range", set(numeric["Overall Pick"].dropna().astype(int)) == set(range(1, 181)), "expected 1-180"),
        ("round_range", set(numeric["Round"].dropna().astype(int)) == set(range(1, 16)), "expected 1-15"),
        ("pick_in_round_range", set(numeric["Pick in Round"].dropna().astype(int)) == set(range(1, 13)), "expected 1-12"),
        ("draft_slot_range", set(numeric["Draft Slot"].dropna().astype(int)) == set(range(1, 13)), "expected 1-12"),
        ("manager_nonblank", frame["Manager"].fillna("").astype(str).str.strip().ne("").all(), ""),
        ("player_nonblank", frame["Player"].fillna("").astype(str).str.strip().ne("").all(), ""),
        ("manager_pick_unique", not frame.assign(_pick=numeric["Overall Pick"]).duplicated(["Manager", "_pick"]).any(), ""),
    ])
    ordered = frame.assign(**{c: numeric[c] for c in numeric}).sort_values("Overall Pick")
    expected_round = ((ordered["Overall Pick"] - 1) // 12 + 1).astype(int)
    expected_pick = ((ordered["Overall Pick"] - 1) % 12 + 1).astype(int)
    expected_slot = np.where(expected_round % 2 == 1, expected_pick, 13 - expected_pick)
    snake = ordered["Round"].eq(expected_round) & ordered["Pick in Round"].eq(expected_pick) & ordered["Draft Slot"].eq(expected_slot)
    checks.append(("snake_order", bool(snake.all()), f"invalid_rows={int((~snake).sum())}"))
    return pd.DataFrame(checks, columns=["check", "passed", "detail"])


def require_valid_draft(frame: pd.DataFrame) -> pd.DataFrame:
    report = validate_draft_results(frame)
    failures = report[~report["passed"]]
    if not failures.empty:
        raise DraftValidationError("; ".join(f"{r.check}: {r.detail}" for r in failures.itertuples()))
    return report


def _aliases(row: pd.Series) -> set[str]:
    return {name for field in ("player_name", "canonical_name", "fpl_name", "historical_name")
            if (name := normalize_name(row.get(field))) }


def match_draft_players(draft: pd.DataFrame, rankings: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    aliases = {idx: _aliases(row) for idx, row in rankings.iterrows()}
    records, target_ids = [], []
    for _, pick in draft.sort_values("Overall Pick").iterrows():
        name, club = normalize_name(pick["Player"]), str(pick.get("Club", "")).strip().upper()
        position = set(normalize_fantrax_positions(pick.get("Position", "")).split("/")) - {""}
        approved_alias = DRAFT_RESULT_ALIASES.get(name)
        candidates = [idx for idx, values in aliases.items() if (approved_alias or name) in values]
        method, confidence, note = "Exact normalized name + club", 100.0, ""
        if approved_alias:
            method, confidence, note = "Approved draft-results alias", 95.0, f"{pick['Player']} -> {approved_alias}"
        club_candidates = [idx for idx in candidates if str(rankings.at[idx, "team_2627"]).upper() == club]
        if len(club_candidates) == 1:
            candidates = club_candidates
        elif len(candidates) == 1:
            method, confidence = "Unique exact normalized name", 95.0
        else:
            parts = name.split()
            initial, surname = (parts[0][0], parts[-1]) if len(parts) >= 2 else ("", parts[-1] if parts else "")
            abbreviated = []
            for idx, values in aliases.items():
                for value in values:
                    tokens = value.split()
                    if tokens and tokens[-1] == surname and tokens[0].startswith(initial):
                        abbreviated.append(idx); break
            abbreviated = list(dict.fromkeys(abbreviated))
            constrained = [idx for idx in abbreviated if str(rankings.at[idx, "team_2627"]).upper() == club]
            if len(constrained) > 1 and position:
                constrained = [idx for idx in constrained if position.intersection(set(normalize_fantrax_positions(rankings.at[idx, "fantrax_position_eligibility"]).split("/")))]
            if len(constrained) == 1:
                candidates, method, confidence = constrained, "Club-assisted abbreviated name", 90.0
            elif len(abbreviated) == 1:
                candidates, method, confidence = abbreviated, "Unique abbreviated name", 80.0
                note = "Drafted club differs from frozen snapshot" if str(rankings.at[abbreviated[0], "team_2627"]).upper() != club else ""
            else:
                candidates = constrained or abbreviated
                method, confidence = "Unresolved review candidate", 0.0
        status = "Matched" if len(candidates) == 1 else "Ambiguous" if candidates else "Unresolved"
        idx = candidates[0] if status == "Matched" else None
        row = rankings.loc[idx] if idx is not None else pd.Series(dtype=object)
        registry_id = row.get("registry_player_id")
        fantrax_id = row.get("fantrax_player_id")
        target = str(registry_id if pd.notna(registry_id) and str(registry_id).strip() else fantrax_id if pd.notna(fantrax_id) else "") if idx is not None else ""
        target_ids.append(target or None)
        records.append({"Overall Pick": pick["Overall Pick"], "Manager": pick["Manager"], "Drafted Player": pick["Player"],
                        "Drafted Club": club, "Drafted Position": pick["Position"], "Matched Player": row.get("player_name", ""),
                        "Fantrax ID": row.get("fantrax_player_id", ""), "Registry ID": row.get("registry_player_id", ""),
                        "Match Method": method, "Match Confidence": confidence, "Match Status": status,
                        "Review Note": note or (f"{len(candidates)} candidates" if status != "Matched" else ""), "_ranking_index": idx})
    report = pd.DataFrame(records)
    duplicates = pd.Series([x for x in target_ids if x]).duplicated(keep=False)
    if duplicates.any():
        dup_ids = set(pd.Series([x for x in target_ids if x])[duplicates])
        mask = report.apply(lambda r: str(r["Registry ID"] or r["Fantrax ID"]) in dup_ids, axis=1)
        report.loc[mask, ["Match Status", "Review Note"]] = ["Duplicate Target", "Multiple picks resolve to one identity"]
    matched = report[report["Match Status"].eq("Matched")]
    canonical = draft.merge(matched[["Overall Pick", "_ranking_index"]], on="Overall Pick", how="left", validate="one_to_one")
    canonical = canonical.merge(rankings, left_on="_ranking_index", right_index=True, how="left", suffixes=("_draft", ""), validate="many_to_one")
    return report.drop(columns="_ranking_index"), canonical.drop(columns="_ranking_index")


def letter_grade(score: float) -> str:
    return next(letter for threshold, letter in LETTER_THRESHOLDS if score >= threshold)


def calibrate_league_scores(values: pd.Series, method: str = "standard") -> pd.DataFrame:
    """Map raw scores to a transparent small-league presentation scale."""
    raw = pd.to_numeric(values, errors="coerce")
    valid = raw.dropna()
    result = pd.DataFrame(index=raw.index, columns=["z_score", "calibrated_score"], dtype=float)
    if valid.empty:
        return result
    if method == "standard":
        center, spread = float(valid.mean()), float(valid.std(ddof=0))
        z = (raw - center).div(spread) if spread > 1e-12 else pd.Series(0.0, index=raw.index).where(raw.notna())
        score = 80 + 10 * z
    elif method == "robust":
        center = float(valid.median())
        mad = float((valid - center).abs().median())
        z = .67448975 * (raw - center).div(mad) if mad > 1e-12 else pd.Series(0.0, index=raw.index).where(raw.notna())
        score = 80 + 10 * z
    elif method == "percentile":
        percentile = raw.rank(method="average", pct=True)
        z = pd.Series(np.nan, index=raw.index)
        score = 65 + 30 * percentile
    else:
        raise ValueError(f"Unsupported calibration method: {method}")
    result["z_score"] = z
    result["calibrated_score"] = score.clip(55, 98)
    return result


def calibration_audit(managers: pd.DataFrame, categories: pd.DataFrame) -> pd.DataFrame:
    """Return reconciled category distributions and calibration alternatives."""
    records = []
    for category, group in categories.groupby("category", sort=True):
        scores = pd.to_numeric(group["score"], errors="coerce")
        alternatives = {
            method: calibrate_league_scores(scores, method)["calibrated_score"]
            for method in ("standard", "robust", "percentile")
        }
        for position, (_, row) in enumerate(group.iterrows()):
            effective_weight = float(row["contribution"] / row["score"]) if pd.notna(row["score"]) and row["score"] else 0.0
            records.append({
                "manager": row["manager"], "category": category,
                "raw_category_value": row["score"], "effective_weight": effective_weight,
                "weighted_contribution": row["contribution"], "category_min": scores.min(),
                "category_mean": scores.mean(), "category_median": scores.median(),
                "category_max": scores.max(), "category_std_dev": scores.std(ddof=0),
                "category_leader": group.loc[scores.idxmax(), "manager"],
                "category_lowest_manager": group.loc[scores.idxmin(), "manager"],
                "league_percentile": scores.rank(method="average", pct=True).iloc[position] * 100,
                "standard_calibrated_score": alternatives["standard"].iloc[position],
                "robust_calibrated_score": alternatives["robust"].iloc[position],
                "percentile_calibrated_score": alternatives["percentile"].iloc[position],
                "theoretical_scale": "0-100",
                "actual_observed_scale": f"{scores.min():.2f}-{scores.max():.2f}",
                "audit_status": "non_discriminating" if scores.std(ddof=0) < 1e-12 else "valid",
                "audit_note": "Composite of fantasy-facing metrics converted to within-league percentiles; 50 is league-average performance",
            })
    return pd.DataFrame(records).sort_values(["manager", "category"])


def _percentile(values: pd.Series, higher: bool = True) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    return numeric.rank(pct=True, method="average", ascending=higher).mul(100)


def _weighted_score(values: dict[str, float], weights: dict[str, float]) -> tuple[float, dict[str, float]]:
    valid = {key: float(value) for key, value in values.items() if pd.notna(value)}
    denominator = sum(weights[key] for key in valid)
    contributions = {key: valid[key] * weights[key] / denominator for key in valid}
    return float(np.clip(sum(contributions.values()), 0, 100)), contributions


def _draft_slots_15() -> tuple[RosterSlot, ...]:
    return (RosterSlot("G1", ("G",), "G"), *(RosterSlot(f"D{i}", ("D",), "D") for i in range(1, 4)),
            *(RosterSlot(f"M{i}", ("M",), "M") for i in range(1, 3)), RosterSlot("F1", ("F",), "F"),
            *(RosterSlot(f"FLEX{i}", ("D", "M", "F"), "Flex") for i in range(1, 5)),
            *(RosterSlot(f"BENCH{i}", ("G", "D", "M", "F"), "Bench") for i in range(1, 5)))


def build_canonical(canonical: pd.DataFrame) -> pd.DataFrame:
    mapping = {"Overall Pick": "overall_pick", "Round": "round", "Pick in Round": "pick_in_round", "Draft Slot": "draft_slot",
               "Manager": "manager", "Player": "drafted_player", "Position": "drafted_position", "Club": "drafted_club",
               "overall_rank": "draft_rank", "fantrax_adp": "adp", "fantrax_projected_points": "projected_points",
               "start_rate_2526": "historical_start_rate", "fantasy_points_2526": "total_fantasy_points",
               "ghost_points_2526": "ghost_points", "understat_xg_2526": "xg", "understat_xa_2526": "xa"}
    out = canonical.rename(columns=mapping).copy()
    out["player"] = out["player_name"]
    out["club"] = out["team_2627"]
    out["fantrax_position"] = out["fantrax_position_eligibility"]
    out["canonical_position"] = out["current_position"].fillna(out["position_2627"])
    minutes = pd.to_numeric(out.get("minutes_2526"), errors="coerce")
    apps = pd.to_numeric(out.get("weeks_available"), errors="coerce")
    starts = pd.to_numeric(out.get("starts_2526"), errors="coerce")
    fantasy, ghost = pd.to_numeric(out.get("total_fantasy_points"), errors="coerce"), pd.to_numeric(out.get("ghost_points"), errors="coerce")
    nineties = minutes.div(90).where(minutes.gt(0))
    for name, values in (("points_per_appearance", fantasy.div(apps.where(apps.gt(0)))), ("points_per_start", fantasy.div(starts.where(starts.gt(0)))),
                         ("points_per_90", fantasy.div(nineties)), ("ghost_per_appearance", ghost.div(apps.where(apps.gt(0)))),
                         ("ghost_per_start", ghost.div(starts.where(starts.gt(0)))), ("ghost_per_90", ghost.div(nineties))): out[name] = values
    out["historical_minutes_share"] = minutes.div(3420).mul(100)
    out["xgi"] = pd.to_numeric(out["xg"], errors="coerce") + pd.to_numeric(out["xa"], errors="coerce")
    for src, dest in (("xg", "xg_per_90"), ("xa", "xa_per_90"), ("xgi", "xgi_per_90")): out[dest] = pd.to_numeric(out[src], errors="coerce").div(nineties)
    out["team_strength_percentile"] = _percentile(out["team_strength_rating"])
    out["fixture_ease_percentile"] = _percentile(out["fixture_ease_next_5"])
    out["pick_vs_adp"] = pd.to_numeric(out["adp"], errors="coerce") - out["overall_pick"]
    out["pick_vs_draft_rank"] = pd.to_numeric(out["draft_rank"], errors="coerce") - out["overall_pick"]
    out["rounds_ahead_of_adp"] = (-out["pick_vs_adp"].clip(upper=0) / 12).where(out["adp"].notna(), 0)
    out["rounds_after_adp"] = (out["pick_vs_adp"].clip(lower=0) / 12).where(out["adp"].notna(), 0)
    out["draft_value_label"] = pd.cut(out["pick_vs_adp"], [-np.inf, -24, -6, 6, 24, np.inf], labels=["Major Reach", "Slight Reach", "Fair Value", "Strong Value", "Elite Value"])
    out["position_group"] = out["canonical_position"]
    out["manager_pick_number"] = out.groupby("manager").cumcount() + 1
    out["manager_round"] = out["round"]
    return out


def grade_picks(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["_market"] = np.clip(50 + pd.to_numeric(out["pick_vs_adp"], errors="coerce") * 2, 0, 100)
    out.loc[pd.to_numeric(out["adp"], errors="coerce").isna(), "_market"] = np.nan
    out["_model"] = np.clip(50 + pd.to_numeric(out["pick_vs_draft_rank"], errors="coerce") * 2, 0, 100)
    tier_num = out["tier"].astype(str).str.extract(r"(\d+)")[0].astype(float)
    out["_tier"] = np.clip(105 - tier_num * 10 + out["round"] * 2, 0, 100)
    out["_minutes"] = pd.concat([pd.to_numeric(out.get("minutes_score"), errors="coerce"), pd.to_numeric(out.get("projected_minutes_share"), errors="coerce"), pd.to_numeric(out.get("minutes_confidence"), errors="coerce")], axis=1).mean(axis=1)
    roster_fit = pd.Series(index=out.index, dtype=float)
    for manager, group in out.groupby("manager", sort=False):
        drafted = []
        for idx, row in group.sort_values("overall_pick").iterrows():
            before = pd.DataFrame(drafted)
            assignment_before = assign_roster_slots(before, _draft_slots_15()) if drafted else pd.DataFrame()
            candidate = {"Player": row["player"], "Position": row["fantrax_position"]}
            after = pd.concat([before, pd.DataFrame([candidate])], ignore_index=True)
            assignment_after = assign_roster_slots(after, _draft_slots_15())
            gain = assignment_after["Slot"].notna().sum() - (assignment_before["Slot"].notna().sum() if not assignment_before.empty else 0)
            flexibility = max(0, len(normalize_fantrax_positions(row["fantrax_position"]).split("/")) - 1)
            roster_fit.at[idx] = min(100, 70 * gain + 15 * flexibility)
            drafted.append(candidate)
    out["_roster"] = roster_fit
    scores, components = [], []
    for _, row in out.iterrows():
        values = {"draft_quality": row.get("draft_score"), "market_value": row.get("_market"), "model_value": row.get("_model"),
                  "tier_value": row.get("_tier"), "roster_fit": row.get("_roster"), "minutes_security": row.get("_minutes"),
                  "data_confidence": row.get("data_confidence")}
        score, contribution = _weighted_score(values, PICK_WEIGHTS); scores.append(round(score, 2)); components.append(json.dumps({k: round(v, 4) for k, v in contribution.items()}, sort_keys=True))
    out["pick_grade"] = scores; out["pick_letter_grade"] = [letter_grade(x) for x in scores]; out["pick_grade_components"] = components
    out["round_weight"] = out["round"].map(ROUND_WEIGHTS)
    def labels(row: pd.Series) -> str:
        items = []
        if row.get("pick_vs_adp", 0) >= 24: items.append("Elite Value")
        elif row.get("pick_vs_adp", 0) >= 8: items.append("Strong Value")
        elif row.get("pick_vs_adp", 0) <= -24: items.append("Major Reach")
        elif row.get("pick_vs_adp", 0) <= -8: items.append("Slight Reach")
        if row.get("_roster", 0) >= 85: items.append("Multi-Position Value")
        if row.get("_minutes", 100) < 55: items.append("Minutes Risk")
        if row.get("data_confidence", 100) < 55: items.append("Low Confidence")
        if row["round"] >= 10 and row["pick_grade"] >= 80: items.append("Late-Round Flyer")
        return " | ".join(items[:4] or ["Fair Value"])
    out["pick_labels"] = out.apply(labels, axis=1)
    return out.drop(columns=["_market", "_model", "_tier", "_minutes", "_roster"])


ACTIVE_SLOTS = _draft_slots_15()[:11]


def best_legal_xi(team: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Maximum-projection legal XI with each player assigned at most once."""
    rows = list(team.iterrows())
    states: dict[int, tuple[float, tuple[tuple[int, int], ...]]] = {0: (0.0, ())}
    for index, row in rows:
        updated = dict(states)
        eligible = set(normalize_fantrax_positions(row.get("fantrax_position", "")).split("/")) - {""}
        points = pd.to_numeric(pd.Series([row.get("projected_points")]), errors="coerce").iloc[0]
        points = float(points) if pd.notna(points) else 0.0
        for mask, (score, assignments) in states.items():
            for slot_index, slot in enumerate(ACTIVE_SLOTS):
                bit = 1 << slot_index
                if mask & bit or not eligible.intersection(slot.eligible):
                    continue
                candidate = (score + points, assignments + ((index, slot_index),))
                if candidate[0] > updated.get(mask | bit, (-np.inf, ()))[0]:
                    updated[mask | bit] = candidate
        states = updated
    full = (1 << len(ACTIVE_SLOTS)) - 1
    _, assignments = states.get(full, max(states.values(), key=lambda item: (len(item[1]), item[0])))
    assignment_map = {index: ACTIVE_SLOTS[slot].name for index, slot in assignments}
    xi = team.loc[list(assignment_map)].copy() if assignment_map else team.iloc[0:0].copy()
    xi["starting_slot"] = [assignment_map[index] for index in xi.index]
    bench = team.drop(index=list(assignment_map)).copy()
    return xi, bench


def _weighted_rate(frame: pd.DataFrame, total: str) -> float:
    values = pd.to_numeric(frame.get(total), errors="coerce")
    minutes = pd.to_numeric(frame.get("minutes_2526"), errors="coerce")
    valid = values.notna() & minutes.gt(0)
    return float(values[valid].sum() * 90 / minutes[valid].sum()) if valid.any() else np.nan


def position_analysis(picks: pd.DataFrame) -> pd.DataFrame:
    records = []
    for (manager, position), group in picks.groupby(["manager", "canonical_position"], dropna=False):
        records.append({"manager": manager, "position": position, "players": len(group),
                        "projected_points": pd.to_numeric(group["projected_points"], errors="coerce").sum(min_count=1),
                        "fantasy_per_90": _weighted_rate(group, "total_fantasy_points"),
                        "ghost_per_90": _weighted_rate(group, "ghost_points"), "xgi_per_90": _weighted_rate(group, "xgi"),
                        "historical_minutes_pct": pd.to_numeric(group["historical_minutes_share"], errors="coerce").mean(),
                        "historical_start_pct": pd.to_numeric(group["historical_start_rate"], errors="coerce").mean() * 100})
    out = pd.DataFrame(records)
    out["position_score"] = out.groupby("position")["projected_points"].rank(method="average", pct=True).mul(100)
    out["position_grade_score"] = out.groupby("position", group_keys=False)["position_score"].apply(lambda values: calibrate_league_scores(values)["calibrated_score"])
    out["position_letter_grade"] = out["position_grade_score"].map(letter_grade)
    return out.sort_values(["manager", "position"])


def grade_managers(picks: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    player_ghost_pct = pd.to_numeric(picks["ghost_per_90"], errors="coerce").rank(pct=True).mul(100)
    player_xgi_pct = pd.to_numeric(picks["xgi_per_90"], errors="coerce").rank(pct=True).mul(100)
    player_attack_pct = pd.to_numeric(picks["attacking_score"], errors="coerce").rank(pct=True).mul(100)
    base_records = []
    for manager, team in picks.groupby("manager", sort=True):
        xi, bench = best_legal_xi(team)
        outlook = team["minutes_outlook"].fillna("").astype(str).str.casefold()
        locked = int(outlook.str.contains("locked").sum()); likely = int(outlook.str.contains("likely starter").sum())
        rotation = int(outlook.str.contains("rotation").sum()); unknown = int(outlook.str.contains("unknown").sum())
        positions = team["canonical_position"].value_counts()
        balance = float(np.clip(100 - 12 * abs(positions.get("G", 0) - 1) - 5 * max(0, positions.get("D", 0) - 5)
                                - 5 * max(0, positions.get("M", 0) - 6) - 7 * max(0, positions.get("F", 0) - 4), 0, 100))
        elig_count = team["fantrax_position"].map(lambda value: len(set(normalize_fantrax_positions(value).split("/")) - {""}))
        goalkeeper = team[team["canonical_position"].eq("G")]
        gk_timing = float(np.clip(100 - abs((pd.to_numeric(goalkeeper["round"], errors="coerce").min() if not goalkeeper.empty else 1) - 12) * 7, 0, 100))
        values_adp = pd.to_numeric(team["pick_vs_adp"], errors="coerce")
        values_rank = pd.to_numeric(team["pick_vs_draft_rank"], errors="coerce")
        projected = pd.to_numeric(team["projected_points"], errors="coerce")
        xi_projected = pd.to_numeric(xi["projected_points"], errors="coerce")
        bench_projected = pd.to_numeric(bench["projected_points"], errors="coerce")
        base_records.append({"manager": manager, "draft_slot": int(team["draft_slot"].iloc[0]),
            "total_projected_points": projected.sum(min_count=1), "average_projected_points": projected.mean(),
            "best_xi_projected_points": xi_projected.sum(min_count=1), "bench_projected_points": bench_projected.sum(min_count=1),
            "fantasy_per_90": _weighted_rate(team, "total_fantasy_points"), "ghost_per_90": _weighted_rate(team, "ghost_points"),
            "average_ghost_percentile": player_ghost_pct.loc[team.index].mean(), "average_minutes_confidence": pd.to_numeric(team["minutes_confidence"], errors="coerce").mean(),
            "average_historical_start_pct": pd.to_numeric(team["historical_start_rate"], errors="coerce").mean() * 100,
            "average_historical_minutes_pct": pd.to_numeric(team["historical_minutes_share"], errors="coerce").mean(),
            "average_projected_minutes_pct": pd.to_numeric(team["projected_minutes_share"], errors="coerce").mean(),
            "locked_starters": locked, "likely_starters": likely, "rotation_players": rotation, "unknown_minutes_players": unknown,
            "starter_security_index": 100 * (locked + .75 * likely + .3 * rotation) / len(team),
            "average_pick_vs_adp": values_adp.mean(), "average_pick_vs_draft_rank": values_rank.mean(),
            "steals": int(values_adp.ge(12).sum()), "reaches": int(values_adp.le(-12).sum()),
            "average_value_gained": pd.concat([values_adp, values_rank], axis=1).mean(axis=1).mean(),
            "xgi_per_90": _weighted_rate(team, "xgi"), "average_xgi_percentile": player_xgi_pct.loc[team.index].mean(),
            "average_attacking_percentile": player_attack_pct.loc[team.index].mean(),
            "positional_balance": balance, "multi_position_flexibility": elig_count.mean(),
            "starter_quality": xi_projected.mean(), "weakest_starter": xi_projected.min(),
            "first_bench_strength": bench_projected.max(), "goalkeeper_timing": gk_timing,
            "best_pick": team.sort_values(["pick_grade", "overall_pick"], ascending=[False, True]).iloc[0]["player"],
            "worst_pick": team.sort_values(["pick_grade", "overall_pick"]).iloc[0]["player"],
            "biggest_value": team.loc[values_adp.idxmax(), "player"] if values_adp.notna().any() else "No ADP",
            "biggest_reach": team.loc[values_adp.idxmin(), "player"] if values_adp.notna().any() else team.loc[values_rank.idxmin(), "player"]})
    metrics = pd.DataFrame(base_records).set_index("manager")
    category_metrics = {
        "projected_production": (("total_projected_points", 1), ("average_projected_points", 1), ("best_xi_projected_points", 1), ("bench_projected_points", 1)),
        "historical_production": (("fantasy_per_90", 1),),
        "floor": (("ghost_per_90", 1), ("average_ghost_percentile", 1), ("average_minutes_confidence", 1)),
        "playing_time_security": (("average_historical_start_pct", 1), ("average_historical_minutes_pct", 1), ("average_projected_minutes_pct", 1), ("average_minutes_confidence", 1), ("starter_security_index", 1), ("rotation_players", -1), ("unknown_minutes_players", -1)),
        "draft_value": (("average_pick_vs_adp", 1), ("average_pick_vs_draft_rank", 1), ("steals", 1), ("reaches", -1), ("average_value_gained", 1)),
        "attacking_upside": (("xgi_per_90", 1), ("average_xgi_percentile", 1), ("average_attacking_percentile", 1)),
        "roster_construction": (("best_xi_projected_points", 1), ("bench_projected_points", 1), ("positional_balance", 1), ("multi_position_flexibility", 1), ("starter_quality", 1), ("weakest_starter", 1), ("first_bench_strength", 1), ("goalkeeper_timing", 1)),
    }
    category_rows = []
    for category, fields in category_metrics.items():
        percentile_inputs = []
        for field, direction in fields:
            percentile_inputs.append(metrics[field].rank(method="average", pct=True, ascending=direction > 0).mul(100).rename(field))
        scores = pd.concat(percentile_inputs, axis=1).mean(axis=1)
        for manager, score in scores.items():
            category_rows.append({"manager": manager, "category": category, "score": score,
                                  "weight": MANAGER_WEIGHTS[category], "metric_summary": json.dumps({field: round(float(metrics.at[manager, field]), 3) if pd.notna(metrics.at[manager, field]) else None for field, _ in fields}, sort_keys=True)})
    categories = pd.DataFrame(category_rows)
    categories["contribution"] = categories["score"] * categories["weight"]
    raw = categories.groupby("manager")["contribution"].sum()
    managers = metrics.copy(); managers["raw_analytical_score"] = raw; managers["overall_score"] = raw
    managers["overall_rank"] = raw.rank(method="min", ascending=False).astype(int)
    calibration = calibrate_league_scores(raw)
    managers["z_score"] = calibration["z_score"]; managers["league_relative_score"] = calibration["calibrated_score"]
    managers["letter_grade"] = managers["league_relative_score"].map(letter_grade); managers["overall_grade"] = managers["letter_grade"]
    managers["calibration_method"] = "standard_z_80_plus_10z_clip_55_98"
    calibrated_groups=[]
    for category, group in categories.groupby("category", sort=True):
        group=group.copy(); group["league_rank"]=group["score"].rank(method="min",ascending=False).astype("Int64")
        group["league_percentile"]=group["score"].rank(method="average",pct=True).mul(100)
        group["calibrated_category_score"]=calibrate_league_scores(group["score"])["calibrated_score"]
        group["category_letter_grade"]=group["calibrated_category_score"].map(letter_grade); calibrated_groups.append(group)
    categories=pd.concat(calibrated_groups)
    pivot=categories.pivot(index="manager",columns="category",values="calibrated_category_score")
    managers["top_category"]=pivot.idxmax(axis=1); managers["main_concern"]=pivot.idxmin(axis=1)
    managers["draft_identity"]=managers["top_category"].map({"projected_production":"Projection Powerhouse","historical_production":"Proven Producers","floor":"High Floor","playing_time_security":"Minutes Secure","draft_value":"Value Hunters","attacking_upside":"High Upside","roster_construction":"Well Constructed"})
    for category in MANAGER_WEIGHTS:
        managers[f"{category}_score"] = categories[categories["category"].eq(category)].set_index("manager")["score"]
    return managers.reset_index().sort_values(["overall_rank","manager"]), categories.sort_values(["category","league_rank","manager"])


def build_awards(managers: pd.DataFrame, picks: pd.DataFrame) -> pd.DataFrame:
    awards=[]
    def team_award(name: str, field: str, reason: str):
        row=managers.sort_values([field, "manager"], ascending=[False, True]).iloc[0]; awards.append({"award": name, "winner": row.manager, "value": row[field], "reason": reason})
    for args in (("Best Overall Draft", "raw_analytical_score", "Highest reconciled next-generation team grade"),
                 ("Best Value Draft", "draft_value_score", "Highest Draft Value score"),
                 ("Highest Projected Team", "projected_production_score", "Highest Projected Production score"),
                 ("Highest Floor", "floor_score", "Highest Floor score"), ("Safest Team", "playing_time_security_score", "Highest Playing Time Security score"),
                 ("Highest Ceiling", "attacking_upside_score", "Highest Attacking Upside score"),
                 ("Best Roster Construction", "roster_construction_score", "Highest redesigned construction score"),
                 ("Strongest Bench", "bench_projected_points", "Highest projected bench points"),
                 ("Most Balanced Draft", "raw_analytical_score", "Highest weighted result across fantasy-facing categories")): team_award(*args)
    steal=picks[picks["pick_vs_adp"].notna()].sort_values(["pick_vs_adp", "overall_pick"], ascending=[False, True]).iloc[0]
    reach=picks.sort_values(["pick_vs_draft_rank", "overall_pick"]).iloc[0]
    late=picks[picks["round"].ge(10)].sort_values(["pick_grade", "overall_pick"], ascending=[False, True]).iloc[0]
    for name,row,value,reason in (("Biggest Steal",steal,steal.pick_vs_adp,"Largest positive pick-versus-ADP value"),("Biggest Reach",reach,reach.pick_vs_draft_rank,"Largest negative pick-versus-Draft-Rank value"),("Best Late-Round Pick",late,late.pick_grade,"Highest Pick Grade in rounds 10-15")):
        awards.append({"award":name,"winner":f"{row.manager} — {row.player}","value":round(float(value),2),"reason":reason})
    positions = position_analysis(picks)
    for pos,label in (("G","Best Goalkeeper"),("D","Best Defender Group"),("M","Best Midfield"),("F","Best Forward Group")):
        subset=positions[positions["position"].eq(pos)].sort_values(["position_score","manager"],ascending=[False,True])
        if not subset.empty: awards.append({"award":label,"winner":subset.iloc[0]["manager"],"value":round(subset.iloc[0]["position_score"],2),"reason":f"Highest projected {pos} position-group score"})
    flexibility = picks.assign(_flex=picks["fantrax_position"].map(lambda value: len(normalize_fantrax_positions(value).split("/")))).groupby("manager")["_flex"].mean().sort_values(ascending=False)
    awards.append({"award":"Most Flexible Roster","winner":flexibility.index[0],"value":round(flexibility.iloc[0],2),"reason":"Highest mean Fantrax position eligibility count"})
    risk = managers.assign(_boom=managers["attacking_upside_score"]-managers["floor_score"]).sort_values(["_boom", "manager"], ascending=[False, True]).iloc[0]
    awards.append({"award":"Most Boom-or-Bust","winner":risk.manager,"value":round(risk._boom,2),"reason":"Largest Upside-minus-Floor category gap"})
    tendencies = picks[picks["adp"].notna()].groupby("manager")["pick_vs_adp"].mean().sort_values()
    awards.append({"award":"Most Aggressive Drafter","winner":tendencies.index[0],"value":round(tendencies.iloc[0],2),"reason":"Lowest mean pick-versus-ADP value"})
    awards.append({"award":"Most Patient Drafter","winner":tendencies.index[-1],"value":round(tendencies.iloc[-1],2),"reason":"Highest mean pick-versus-ADP value"})
    return pd.DataFrame(awards)


def build_all(draft: pd.DataFrame, rankings: pd.DataFrame) -> DraftBuildResult:
    validation=require_valid_draft(draft); matches, joined=match_draft_players(draft, rankings)
    if not matches["Match Status"].eq("Matched").all(): raise DraftValidationError(f"Matching incomplete: {(~matches['Match Status'].eq('Matched')).sum()} unresolved/ambiguous")
    canonical=build_canonical(joined); picks=grade_picks(canonical); managers,categories=grade_managers(picks); awards=build_awards(managers,picks)
    return DraftBuildResult(validation,matches,canonical,picks,managers,categories,awards)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze_snapshot(source: Path, snapshot: Path, metadata: Path) -> dict[str, Any]:
    source_hash=sha256(source)
    if snapshot.exists():
        if sha256(snapshot) != source_hash and metadata.exists() and json.loads(metadata.read_text(encoding="utf-8")).get("sha256") != sha256(snapshot):
            raise DraftValidationError("Frozen draft-day snapshot integrity check failed")
        return json.loads(metadata.read_text(encoding="utf-8"))
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_bytes(source.read_bytes())
    payload={"season_id":"2627","created_at":datetime.now(timezone.utc).isoformat(),"source":str(source.as_posix()),"sha256":source_hash,"immutable":True}
    metadata.write_text(json.dumps(payload, indent=2)+"\n",encoding="utf-8")
    return payload
