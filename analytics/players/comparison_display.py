"""Presentation preparation for the live 2–5 player comparison surface."""
from __future__ import annotations

import html
import re

import numpy as np
import pandas as pd

from analytics.players.comparison import stable_player_id
from analytics.players.comparison_catalog import CATALOG
from analytics.players.match_analysis import calculate_home_away_split, prepare_player_gameweek_frame
from components.design_tokens import COLORS

RATE_SUFFIX = {"Per Game": "per_game", "Per Start": "per_start", "Per 90": "per_90"}
CORE_ROWS = (
    ("season_points", "Season Points", "fantasy_points", True),
    ("points_game", "Points / Game", "points_per_game", True),
    ("points_start", "Points / Start", "points_per_start", True),
    ("points_90", "Points / 90", "points_per_90", True),
    ("ghost_game", "Ghost / Game", "ghost_per_game", True),
    ("ghost_start", "Ghost / Start", "ghost_per_start", True),
    ("ghost_90", "Ghost / 90", "ghost_per_90", True),
    ("goals", "Goals", "goals", True),
    ("assists", "Assists", "assists", True),
    ("xgi_90", "xGI / 90", "xgi_per_90", True),
    ("home_avg", "Home Avg", "__home_avg", True),
    ("away_avg", "Away Avg", "__away_avg", True),
    ("minutes_outlook", "Minutes Outlook", "projected_minutes_percentage", True),
    ("fixture_ease", "Next 5 Fixture Ease", "next_five_fixture_ease_percentile", True),
)


def season_field(mode: str, stem: str) -> str:
    if stem.startswith("projected_") or stem.startswith("next_five_"):
        return stem
    prefix = "historical" if mode == "Historical" else "current"
    aliases = {("historical", "points_per_game"): "historical_points_per_appearance"}
    return aliases.get((prefix, stem), f"{prefix}_{stem}")


def format_next_fixture(row: pd.Series) -> str:
    value = row.get("opening_opponent")
    if pd.isna(value) or not str(value).strip():
        return "\u2014"
    text = str(value).strip()
    venue = str(row.get("opening_venue", "")).strip().upper()
    away = text.startswith("@")
    clean = text[1:].strip() if away else text
    parts=clean.split(); day_index=next((index for index,part in enumerate(parts) if re.fullmatch(r"Mon|Tue|Wed|Thu|Fri|Sat|Sun",part,re.I)),len(parts))
    opponent=" ".join(parts[:day_index]).strip()
    if not opponent:
        return "\u2014"
    if venue in {"H", "HOME"}:
        suffix = "H"
    elif venue in {"A", "AWAY"} or away:
        suffix = "A"
    elif day_index < len(parts):
        suffix = "H"
    else:
        suffix = ""
    return f"{opponent} ({suffix})" if suffix else opponent


def home_away_values(row: pd.Series, mode: str, rate_basis: str, current_weekly: pd.DataFrame, historical_weekly: pd.DataFrame) -> tuple[float, float]:
    historical = mode == "Historical"
    player_id = row.get("historical_fantrax_player_id") if historical else row.get("fantrax_player_id")
    weekly = historical_weekly if historical else current_weekly
    season = "2025/26" if historical else "2026/27"
    prepared = prepare_player_gameweek_frame(weekly, str(player_id), season=season)
    split = calculate_home_away_split(prepared, rate_basis).set_index("Venue")
    return split.at["Home", "Average"], split.at["Away", "Average"]


def comparison_cards(selected: pd.DataFrame, mode: str, rate_basis: str, current_weekly: pd.DataFrame, historical_weekly: pd.DataFrame) -> list[dict]:
    suffix = RATE_SUFFIX[rate_basis]
    cards = []
    for _, row in selected.iterrows():
        home, away = home_away_values(row, mode, rate_basis, current_weekly, historical_weekly)
        available_value=row.get("available",False); available=bool(available_value) if pd.notna(available_value) else False
        owner="Available"
        if not available:
            owner=next((str(row.get(field)).strip() for field in ("current_fantasy_team","current_manager_name") if pd.notna(row.get(field)) and str(row.get(field)).strip()),"Available")
        cards.append({
            "player_id": stable_player_id(row), "player_name": row.get("player_name", "Unknown"),
            "club": row.get("premier_league_club", ""), "position": row.get("fantrax_position", ""),
            "points": row.get(season_field(mode, f"points_{suffix}")),
            "ghost": row.get(season_field(mode, f"ghost_{suffix}")),
            "xgi": row.get(season_field(mode, f"xgi_{suffix}")),
            "basis": rate_basis.replace("Per ", ""), "minutes_outlook": row.get("projected_minutes_percentage"),
            "next_fixture": format_next_fixture(row), "home_avg": home, "away_avg": away, "owner": owner,
        })
    return cards


def _number(value, digits=1) -> str:
    numeric = pd.to_numeric(value, errors="coerce")
    return "\u2014" if pd.isna(numeric) else f"{numeric:,.{digits}f}"


def comparison_card_html(card: dict) -> str:
    metrics = ((f"Points / {card['basis']}", card["points"]), (f"Ghost / {card['basis']}", card["ghost"]), (f"xGI / {card['basis']}", card["xgi"]), ("Minutes Outlook", card["minutes_outlook"]), ("Next Fixture", card["next_fixture"]), ("Home Avg", card["home_avg"]), ("Away Avg", card["away_avg"]), ("Owner / Available", card["owner"]))
    cells = "".join(f'<span class="ft-compare-label">{html.escape(label)}</span><b>{html.escape(str(value) if isinstance(value, str) else _number(value, 2 if label.startswith("xGI") else 1))}</b>' for label, value in metrics)
    return f'<div class="ft-compare-card"><h4>{html.escape(str(card["player_name"]))}</h4><p>{html.escape(str(card["club"]))} \u00b7 {html.escape(str(card["position"]))}</p><div class="ft-compare-grid">{cells}</div></div>'


def comparison_exact_table(selected: pd.DataFrame, mode: str, rate_basis: str, metric_keys: tuple[str, ...], current_weekly: pd.DataFrame, historical_weekly: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, bool]]:
    players=[]; seen={}
    for _,row in selected.iterrows():
        base=str(row.get("player_name","Unknown")); seen[base]=seen.get(base,0)+1
        players.append(base if seen[base]==1 else f"{base} ({seen[base]})")
    values_by_id = {}
    for _, row in selected.iterrows():
        home, away = home_away_values(row, mode, rate_basis, current_weekly, historical_weekly)
        values_by_id[stable_player_id(row)] = (row, home, away)
    definitions = list(CORE_ROWS)
    existing_fields = {season_field(mode,item[2]) for item in definitions if not item[2].startswith("__")}
    for key in metric_keys:
        metric = CATALOG[key]; field = metric.field_for(rate_basis)
        if field not in existing_fields:
            definitions.append((f"metric_{key}", metric.label_for(rate_basis), field, metric.higher_is_better)); existing_fields.add(field)
    rows=[]; directions={}
    for key, label, stem, higher in definitions:
        output={"Stat":label}
        for name, (_, (row, home, away)) in zip(players, values_by_id.items()):
            if stem == "__home_avg": value=home
            elif stem == "__away_avg": value=away
            elif key.startswith("metric_"): value=row.get(stem)
            else: value=row.get(season_field(mode,stem))
            output[name]=pd.to_numeric(value,errors="coerce")
        if any(pd.notna(output[name]) for name in players): rows.append(output); directions[label]=higher
    return pd.DataFrame(rows), directions


def comparison_table_styler(table: pd.DataFrame, directions: dict[str, bool]):
    players=[column for column in table.columns if column!="Stat"]
    styles=pd.DataFrame("",index=table.index,columns=table.columns)
    for index,row in table.iterrows():
        numeric=pd.to_numeric(row[players],errors="coerce"); valid=numeric.dropna()
        if valid.empty: continue
        best=valid.max() if directions.get(row["Stat"],True) else valid.min()
        for player in valid.index[valid.eq(best)]: styles.at[index,player]=f"color: {COLORS['positive']}; font-weight: 700"
    return table.style.format({column:lambda value: "\u2014" if pd.isna(value) else f"{value:,.2f}" for column in players}).apply(lambda _:styles,axis=None)


COMPARE_CARD_CSS = """
<style>
.ft-compare-card{background:var(--ft-card-background);border:1px solid var(--ft-border);border-radius:12px;padding:.85rem;box-shadow:0 2px 8px rgba(23,33,43,.05);min-height:190px}
.ft-compare-card h4{margin:0;font-size:1rem}.ft-compare-card p{margin:.15rem 0 .65rem;color:var(--ft-text-muted);font-size:.78rem}
.ft-compare-grid{display:grid;grid-template-columns:1fr auto;gap:.3rem .65rem;font-size:.78rem}.ft-compare-label{color:var(--ft-text-secondary)}.ft-compare-grid b{text-align:right;color:var(--ft-text-primary)}
</style>
"""
