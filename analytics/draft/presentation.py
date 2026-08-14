"""Draft HQ presentation analytics.

These helpers derive explainable display values from the frozen ranking output.
They do not change or duplicate the Draft Score formula.
"""

from __future__ import annotations

import re
from typing import Any, Iterable

import numpy as np
import pandas as pd


AVAILABLE = "Available"
DRAFTED_BY_ME = "Drafted by Me"
DRAFTED_BY_OTHER = "Drafted by Other"
DRAFT_STATUSES = (AVAILABLE, DRAFTED_BY_ME, DRAFTED_BY_OTHER)

DRAFT_SCORE_COMPONENTS: tuple[tuple[str, str, float], ...] = (
    ("Historical Production", "production_score", 0.30),
    ("Projected Minutes", "minutes_score", 0.20),
    ("Ghost Production", "ghost_score", 0.15),
    ("Attacking Profile", "attacking_score", 0.15),
    ("Team Context", "team_context_score", 0.10),
    ("Opening Fixtures", "fixture_score", 0.10),
)

COMPONENT_RAW_FIELDS: dict[str, tuple[str, ...]] = {
    "Historical Production": (
        "fantasy_per_appearance_2526", "fantasy_per90_2526"
    ),
    "Projected Minutes": ("projected_minutes_share",),
    "Ghost Production": ("ghost_per_appearance_2526",),
    "Attacking Profile": ("xgi90_2526",),
    "Team Context": ("team_attack_rating", "team_strength_rating"),
    "Opening Fixtures": ("fixture_ease_next_5",),
}


def _positive_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Divide only where the denominator is positive, returning blank otherwise."""
    top = pd.to_numeric(numerator, errors="coerce")
    bottom = pd.to_numeric(denominator, errors="coerce")
    return top.div(bottom.where(bottom.gt(0)))


def normalize_fantrax_positions(value: Any) -> str:
    """Normalize delimiters only; never infer position eligibility."""
    if pd.isna(value):
        return ""
    tokens = [
        token.strip().upper()
        for token in re.split(r"[,/|;]+", str(value))
        if token.strip()
    ]
    return "/".join(dict.fromkeys(tokens))


def position_matches(value: Any, selected: Iterable[str]) -> bool:
    eligible = set(normalize_fantrax_positions(value).split("/")) - {""}
    return bool(eligible.intersection(str(item).upper() for item in selected))


def stable_player_key(row: pd.Series) -> str:
    for field in ("registry_player_id", "fantrax_player_id", "Player"):
        value = row.get(field)
        if pd.notna(value) and str(value).strip():
            return f"{field}:{str(value).strip()}"
    return ""


def apply_draft_statuses(
    frame: pd.DataFrame, statuses: dict[str, str]
) -> pd.DataFrame:
    out = frame.copy()
    out["Draft Status"] = [
        statuses.get(stable_player_key(row), AVAILABLE)
        for _, row in out.iterrows()
    ]
    return out


def set_draft_status(
    statuses: dict[str, str], player_key: str, status: str
) -> dict[str, str]:
    if status not in DRAFT_STATUSES:
        raise ValueError(f"Unsupported draft status: {status}")
    result = dict(statuses)
    if status == AVAILABLE:
        result.pop(player_key, None)
    elif player_key:
        result[player_key] = status
    return result


def reset_draft_session(session_state: Any) -> None:
    """Clear only ephemeral Draft HQ state."""
    session_state["draft_player_statuses"] = {}
    session_state["draft_queue"] = []
    session_state["draft_sequence"] = []


def apply_board_action(
    statuses: dict[str, str],
    queue: Iterable[str],
    sequence: Iterable[str],
    player_key: str,
    status: str,
) -> tuple[dict[str, str], list[str], list[str]]:
    """Apply a one-click board action using only stable identity state."""
    updated_statuses = set_draft_status(statuses, player_key, status)
    updated_queue = list(queue)
    updated_sequence = list(sequence)
    if status != AVAILABLE:
        updated_queue = update_queue(updated_queue, player_key, "remove")
        if player_key not in updated_sequence:
            updated_sequence.append(player_key)
    return updated_statuses, updated_queue, updated_sequence


def add_explicit_rate_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    """Add consistently-denominated historical rates when source data exists."""
    out = frame.copy()
    index = out.index

    def series(name: str) -> pd.Series:
        value = out[name] if name in out else pd.Series(np.nan, index=index)
        return pd.to_numeric(value, errors="coerce")

    minutes = series("minutes_2526")
    starts = series("starts_2526")
    appearances = series("appearances_2526")
    if appearances.isna().all():
        appearances = series("weeks_available")
    nineties = minutes.div(90).where(minutes.gt(0))

    out["appearances_2526"] = appearances
    out["nineties_2526"] = nineties
    for prefix, total_col in (
        ("fantasy", "fantasy_points_2526"),
        ("ghost", "ghost_points_2526"),
    ):
        total = series(total_col)
        out[f"{prefix}_per_appearance_2526"] = _positive_divide(total, appearances)
        out[f"{prefix}_per_start_2526"] = _positive_divide(total, starts)
        out[f"{prefix}_per90_2526"] = _positive_divide(total, nineties)
    return out


def sort_draft_board(
    frame: pd.DataFrame,
    primary: str,
    ascending: bool,
) -> pd.DataFrame:
    """Stable board sort with missing primary values last in both directions."""
    if primary == "ADP":
        adp_numeric = pd.to_numeric(frame[primary], errors="coerce")
        return (
            frame.assign(
                _adp_missing=adp_numeric.isna(),
                _adp_sort=adp_numeric,
            )
            .sort_values(
                ["_adp_missing", "_adp_sort"],
                ascending=[True, ascending],
                kind="stable",
                na_position="last",
            )
            .drop(columns=["_adp_missing", "_adp_sort"])
        )

    keys = [primary]
    directions = [ascending]
    for column, direction in (("Rank", True), ("Draft Score", False)):
        if column in frame and column not in keys:
            keys.append(column)
            directions.append(direction)
    return frame.sort_values(
        keys, ascending=directions, na_position="last", kind="mergesort"
    )


def tier_number(value: Any) -> float:
    match = re.search(r"\d+", str(value))
    return float(match.group()) if match else float("inf")


def build_tier_board(frame: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    """Return tiers in numeric order and players in Draft Rank order."""
    if "tier" not in frame:
        return []
    tiers = frame[frame["tier"].notna()].copy()
    if tiers.empty:
        return []
    tiers["_tier_order"] = tiers["tier"].map(tier_number)
    tiers = tiers.sort_values(
        ["_tier_order", "Rank"], ascending=[True, True], na_position="last"
    )
    return [
        (str(tier), group.drop(columns="_tier_order"))
        for tier, group in tiers.groupby("tier", sort=False)
    ]


def draft_score_explanation(row: pd.Series) -> pd.DataFrame:
    """Explain the official score using retained normalized components."""
    records: list[dict[str, Any]] = []
    for label, field, weight in DRAFT_SCORE_COMPONENTS:
        normalized = pd.to_numeric(pd.Series([row.get(field)]), errors="coerce").iloc[0]
        raw_values = [
            row.get(raw_field) for raw_field in COMPONENT_RAW_FIELDS[label]
            if pd.notna(row.get(raw_field))
        ]
        records.append(
            {
                "Component": label,
                "Raw value": " / ".join(f"{float(value):.1f}" for value in raw_values)
                if raw_values else pd.NA,
                "Normalized value": normalized,
                "Weight": weight,
                "Weighted contribution": (
                    normalized * weight if pd.notna(normalized) else np.nan
                ),
            }
        )
    return pd.DataFrame(records)


def explanation_reconciles(row: pd.Series, tolerance: float = 0.06) -> bool:
    score = pd.to_numeric(pd.Series([row.get("Draft Score", row.get("draft_score"))]), errors="coerce").iloc[0]
    contributions = draft_score_explanation(row)["Weighted contribution"]
    return bool(
        pd.notna(score)
        and contributions.notna().all()
        and abs(float(contributions.sum()) - float(score)) <= tolerance
    )


def update_queue(
    queue: Iterable[str],
    player: str,
    action: str,
) -> list[str]:
    """Apply a deterministic session-only queue action."""
    result = list(dict.fromkeys(str(item) for item in queue))
    if action == "add" and player not in result:
        result.append(player)
    elif action == "remove":
        result = [item for item in result if item != player]
    elif action == "up" and player in result:
        position = result.index(player)
        if position > 0:
            result[position - 1], result[position] = result[position], result[position - 1]
    elif action == "down" and player in result:
        position = result.index(player)
        if position < len(result) - 1:
            result[position + 1], result[position] = result[position], result[position + 1]
    return result


def comparison_table(frame: pd.DataFrame, players: Iterable[str]) -> pd.DataFrame:
    selected = list(players)[:2]
    if len(selected) != 2:
        return pd.DataFrame()
    rows = frame[frame["Player"].isin(selected)].drop_duplicates("Player")
    metrics = [
        ("Club", "Team"), ("Canonical Position", "Position"),
        ("Fantrax Positions", "Fantrax Positions"), ("Status", "Draft Status"),
        ("Tier", "tier"),
        ("Draft Rank", "Rank"), ("Draft Score", "Draft Score"), ("ADP", "ADP"),
        ("Value vs ADP", "Value vs ADP"),
        ("Projected Points", "fantrax_projected_points"),
        ("Projected Minutes %", "projected_minutes_share"),
        ("Minutes Outlook", "minutes_outlook"),
        ("Minutes Confidence", "minutes_confidence"),
        ("Minutes", "minutes_2526"),
        ("Appearances", "appearances_2526"), ("Starts", "starts_2526"),
        ("Points / Appearance", "fantasy_per_appearance_2526"),
        ("Points / Start", "fantasy_per_start_2526"),
        ("Points / 90", "fantasy_per90_2526"),
        ("Ghost / Appearance", "ghost_per_appearance_2526"),
        ("Ghost / Start", "ghost_per_start_2526"),
        ("Ghost / 90", "ghost_per90_2526"),
        ("Production Score", "production_score"),
        ("Minutes Score", "minutes_score"),
        ("Ghost Score", "ghost_score"),
        ("Attacking Score", "attacking_score"),
        ("Team Context Score", "team_context_score"),
        ("Fixture Score", "fixture_score"),
    ]
    data = {"Metric": [label for label, _ in metrics]}
    indexed = rows.set_index("Player")
    for player in selected:
        data[player] = [
            indexed.at[player, field] if player in indexed.index and field in indexed else pd.NA
            for _, field in metrics
        ]
    result = pd.DataFrame(data)
    player_columns = selected
    return result[
        result[player_columns].notna().any(axis=1)
        & ~result[player_columns].eq("").all(axis=1)
    ].reset_index(drop=True)


COMPARISON_METRICS: tuple[tuple[str, str, bool], ...] = (
    ("Draft Score", "Draft Score", True),
    ("Draft Rank", "Rank", False),
    ("ADP", "ADP", False),
    ("ADP Value", "Value vs ADP", True),
    ("Projection", "fantrax_projected_points", True),
    ("Projected Minutes %", "projected_minutes_share", True),
    ("Points / 90", "fantasy_per90_2526", True),
    ("Ghost / 90", "ghost_per90_2526", True),
    ("xG / 90", "xg90_2526", True),
    ("xA / 90", "xa90_2526", True),
    ("xGI / 90", "xgi90_2526", True),
    ("Team Strength Percentile", "team_strength_percentile", True),
    ("Fixture Ease Percentile", "fixture_ease_percentile", True),
    ("Production Score", "production_score", True),
    ("Minutes Score", "minutes_score", True),
    ("Ghost Score", "ghost_score", True),
    ("Attacking Score", "attacking_score", True),
)


def comparison_winner_data(
    frame: pd.DataFrame, player_1: str, player_2: str
) -> pd.DataFrame:
    """Build deterministic head-to-head values and winners from Draft metrics."""
    selected = frame[frame["Player"].isin([player_1, player_2])].drop_duplicates(
        "Player"
    ).set_index("Player")
    if player_1 not in selected.index or player_2 not in selected.index:
        return pd.DataFrame()
    records: list[dict[str, Any]] = []
    for label, field, higher_is_better in COMPARISON_METRICS:
        if field not in selected:
            continue
        left = pd.to_numeric(
            pd.Series([selected.at[player_1, field]]), errors="coerce"
        ).iloc[0]
        right = pd.to_numeric(
            pd.Series([selected.at[player_2, field]]), errors="coerce"
        ).iloc[0]
        if pd.isna(left) and pd.isna(right):
            continue
        winner = "Tie"
        if pd.isna(left) or pd.isna(right):
            winner = "—"
        elif not np.isclose(float(left), float(right)):
            left_wins = left > right if higher_is_better else left < right
            winner = player_1 if left_wins else player_2
        records.append(
            {
                "Metric": label,
                player_1: format_detail_value(left),
                player_2: format_detail_value(right),
                "Winner": winner,
            }
        )
    return pd.DataFrame(records)


DETAIL_PERCENTILE_FIELDS: dict[str, str] = {
    "draft_score": "Draft Score",
    "projected_points": "fantrax_projected_points",
    "points_per90": "fantasy_per90_2526",
    "ghost_per90": "ghost_per90_2526",
    "projected_minutes": "projected_minutes_share",
    "xgi_per90": "xgi90_2526",
    "production": "production_score",
    "ghost_floor": "ghost_score",
    "player_attack": "attacking_score",
    "playing_time": "minutes_score",
}

MODEL_DISPLAY_LABELS = {
    "production_score": "Historical Fantasy Production",
    "minutes_score": "Playing-Time Reliability",
    "ghost_score": "Ghost-Point Floor",
    "attacking_score": "Player Attacking Output",
    "team_context_score": "Club Strength Context",
    "fixture_score": "Next-5 Fixture Ease",
}


def add_advanced_context_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    """Expose authoritative attacking fields and directional context percentiles.

    xG and xA are retained Understat 2025/26 totals.  xGI and all rates are
    presentation analytics and are blank unless the authoritative denominator
    is positive.  Club percentiles rank unique club ratings so clubs with more
    players do not receive extra weight.
    """
    out = frame.copy()
    index = out.index

    def numeric(name: str) -> pd.Series:
        return pd.to_numeric(
            out.get(name, pd.Series(np.nan, index=index)), errors="coerce"
        )

    xg = numeric("understat_xg_2526")
    xa = numeric("understat_xa_2526")
    minutes = numeric("understat_minutes_2526")
    out["xg_2526"] = xg
    out["xa_2526"] = xa
    out["xgi_2526"] = (xg + xa).where(xg.notna() & xa.notna())
    nineties = minutes.div(90).where(minutes.gt(0))
    out["xg90_2526"] = _positive_divide(xg, nineties)
    out["xa90_2526"] = _positive_divide(xa, nineties)
    calculated_xgi90 = _positive_divide(out["xgi_2526"], nineties)
    out["xgi90_2526"] = numeric("xgi90_2526").combine_first(calculated_xgi90)
    appearances = numeric("appearances_2526")
    if appearances.isna().all():
        appearances = numeric("weeks_available")
    starts = numeric("starts_2526")
    out["xgi_per_appearance_2526"] = _positive_divide(out["xgi_2526"], appearances)
    out["xgi_per_start_2526"] = _positive_divide(out["xgi_2526"], starts)

    for source, target in (
        ("team_strength_rating", "team_strength_percentile"),
        ("fixture_ease_next_5", "fixture_ease_percentile"),
    ):
        values = numeric(source)
        if "Team" in out:
            clubs = pd.DataFrame({"club": out["Team"], "value": values}).dropna()
            club_values = clubs.groupby("club", sort=False)["value"].first()
            club_pct = club_values.rank(pct=True, method="average").mul(100)
            out[target] = out["Team"].map(club_pct)
        else:
            out[target] = values.rank(pct=True, method="average").mul(100)
    return out


def add_historical_playing_time(frame: pd.DataFrame) -> pd.DataFrame:
    """Add explicitly historical shares using the 38-match PL maximum."""
    out = frame.copy()
    index = out.index
    start_rate = pd.to_numeric(out.get("start_rate_2526", pd.Series(np.nan, index=index)), errors="coerce")
    minutes = pd.to_numeric(out.get("minutes_2526", pd.Series(np.nan, index=index)), errors="coerce")
    out["historical_start_pct_2526"] = start_rate.mul(100)
    out["historical_minutes_pct_2526"] = minutes.div(38 * 90).mul(100).clip(upper=100)
    return out


def add_draft_percentiles(frame: pd.DataFrame) -> pd.DataFrame:
    """Add deterministic league and canonical-position percentile context."""
    out = frame.copy()
    position = out.get(
        "Canonical Position", pd.Series("", index=out.index)
    ).fillna("").astype(str)
    for label, field in DETAIL_PERCENTILE_FIELDS.items():
        values = pd.to_numeric(
            out.get(field, pd.Series(np.nan, index=out.index)),
            errors="coerce",
        )
        out[f"{label}_league_percentile"] = values.rank(
            pct=True, method="average"
        ).mul(100)
        out[f"{label}_position_percentile"] = values.groupby(position).rank(
            pct=True, method="average"
        ).mul(100)
    return out


def format_detail_value(value: Any, *, integer: bool = False) -> str:
    """Format detail values without leaking raw floating-point representations."""
    if value is None or pd.isna(value):
        return "—"
    if integer:
        return f"{float(value):.0f}"
    if isinstance(value, (int, float, np.integer, np.floating)):
        return f"{float(value):.1f}"
    return str(value)


def percentile_context(row: pd.Series, metric: str) -> tuple[str, str]:
    """Return concise position and league context for a retained metric."""
    raw_position = str(
        row.get("Canonical Position") or row.get("Position") or "position"
    )
    position = {
        "G": "Goalkeepers",
        "GK": "Goalkeepers",
        "D": "Defenders",
        "DEF": "Defenders",
        "M": "Midfielders",
        "MID": "Midfielders",
        "F": "Forwards",
        "FWD": "Forwards",
    }.get(raw_position.upper(), f"{raw_position}s")
    positional = row.get(f"{metric}_position_percentile")
    league = row.get(f"{metric}_league_percentile")
    position_text = (
        f"Top {max(1, round(100 - float(positional))):d}% among {position}"
        if pd.notna(positional) and float(positional) >= 50
        else (
            f"{float(positional):.0f}th percentile among {position}"
            if pd.notna(positional) else ""
        )
    )
    league_text = (
        f"{float(league):.0f}th percentile league-wide"
        if pd.notna(league) else ""
    )
    return position_text, league_text


def player_strengths_and_risks(row: pd.Series) -> tuple[list[str], list[str]]:
    """Generate deterministic summaries from existing model metrics only."""
    def number(field: str, default: float) -> float:
        value = pd.to_numeric(
            pd.Series([row.get(field)]), errors="coerce"
        ).iloc[0]
        return default if pd.isna(value) else float(value)

    strengths: list[str] = []
    risks: list[str] = []
    if number("projected_minutes_position_percentile", 0) >= 90:
        strengths.append("Elite projected minutes")
    if number("points_per90_position_percentile", 0) >= 85:
        strengths.append("Excellent fantasy production")
    if number("ghost_per90_position_percentile", 0) >= 85:
        strengths.append("Strong ghost-point floor")
    if number("attacking_score", 0) >= 75:
        strengths.append("Strong attacking contribution")
    if number("xgi_per90_position_percentile", 0) >= 85:
        strengths.append("Strong xGI/90")
    if number("team_strength_percentile", 0) >= 75:
        strengths.append("Strong team context")
    if number("fixture_ease_percentile", 0) >= 75:
        strengths.append("Favorable early fixtures")
    if number("draft_score_league_percentile", 0) >= 90:
        strengths.append("Elite overall Draft Score")

    value = number("Value vs ADP", np.nan)
    if pd.notna(value) and value < -5:
        risks.append("Reach versus current ADP")
    if number("projected_minutes_position_percentile", 100) <= 35:
        risks.append("Lower projected minutes than positional peers")
    if number("ghost_per90_position_percentile", 100) <= 35:
        risks.append("Lower ghost floor than positional peers")
    if pd.notna(row.get("fixture_ease_percentile")) and number("fixture_ease_percentile", 100) <= 25:
        risks.append("Difficult early fixture context")
    if pd.notna(row.get("team_strength_percentile")) and number("team_strength_percentile", 100) <= 25:
        risks.append("Weak team context")
    confidence = number("data_confidence", np.nan)
    if pd.notna(confidence) and confidence < 60:
        risks.append("Lower underlying data confidence")
    return strengths[:3], risks[:3]


def player_analysis_tags(row: pd.Series, limit: int = 5) -> list[str]:
    """Compact tags backed by the profile's deterministic metrics."""
    strengths, risks = player_strengths_and_risks(row)
    labels = {
        "Elite projected minutes": "Elite Minutes",
        "Excellent fantasy production": "Strong Projection",
        "Strong ghost-point floor": "High Floor",
        "Strong attacking contribution": "Strong xGI",
        "Strong xGI/90": "Strong xGI",
        "Strong team context": "Strong Team Context",
        "Favorable early fixtures": "Fixture Boost",
        "Reach versus current ADP": "ADP Reach",
        "Lower projected minutes than positional peers": "Rotation Risk",
        "Lower ghost floor than positional peers": "Low Ghost Floor",
        "Lower underlying data confidence": "Low Confidence",
    }
    tags = [labels[item] for item in [*strengths, *risks] if item in labels]
    value = pd.to_numeric(pd.Series([row.get("Value vs ADP")]), errors="coerce").iloc[0]
    if pd.notna(value) and value >= 5:
        tags.append("Good Value")
    return list(dict.fromkeys(tags))[:limit]


def draft_profile_percentiles(row: pd.Series) -> pd.DataFrame:
    """Compact actual-percentile profile for detail and comparison views."""
    metrics = (
        ("Draft Score", "draft_score_league_percentile", "draft_score_position_percentile"),
        (MODEL_DISPLAY_LABELS["production_score"], "production_score", "production_position_percentile"),
        (MODEL_DISPLAY_LABELS["ghost_score"], "ghost_score", "ghost_floor_position_percentile"),
        (MODEL_DISPLAY_LABELS["attacking_score"], "attacking_score", "player_attack_position_percentile"),
        (MODEL_DISPLAY_LABELS["minutes_score"], "minutes_score", "playing_time_position_percentile"),
        ("Club Strength", "team_strength_percentile", None),
        ("Next-5 Fixture Ease", "fixture_ease_percentile", None),
    )
    records = []
    for label, league_field, position_field in metrics:
        league = pd.to_numeric(pd.Series([row.get(league_field)]), errors="coerce").iloc[0]
        positional = pd.to_numeric(pd.Series([row.get(position_field)]), errors="coerce").iloc[0] if position_field else np.nan
        if pd.notna(league) or pd.notna(positional):
            records.append({"Profile": label, "Overall %ile": league, "Position %ile": positional})
    return pd.DataFrame(records)


def model_visualization_data(row: pd.Series) -> pd.DataFrame:
    """Return bounded model-component scores for progress visualization."""
    fields = (
        (MODEL_DISPLAY_LABELS["production_score"], "production_score"),
        (MODEL_DISPLAY_LABELS["minutes_score"], "minutes_score"),
        (MODEL_DISPLAY_LABELS["ghost_score"], "ghost_score"),
        (MODEL_DISPLAY_LABELS["attacking_score"], "attacking_score"),
        (MODEL_DISPLAY_LABELS["team_context_score"], "team_context_score"),
        (MODEL_DISPLAY_LABELS["fixture_score"], "fixture_score"),
    )
    records = []
    for label, field in fields:
        value = pd.to_numeric(pd.Series([row.get(field)]), errors="coerce").iloc[0]
        if pd.notna(value):
            records.append({"Component": label, "Score": round(float(np.clip(value, 0, 100)), 1)})
    return pd.DataFrame(records)
