"""Plain-language, presentation-only completed-draft summaries."""

from __future__ import annotations

import html
from typing import Any

import numpy as np
import pandas as pd


SHARE_COLUMNS = (
    "rank", "manager", "grade", "league_relative_score",
    "projected_starting_xi_points", "average_player_projection", "average_adp",
    "fantasy_points_per_90", "ghost_points_per_90", "historical_start_pct",
    "projected_minutes_pct", "main_strength", "main_concern", "best_pick",
    "biggest_reach",
)

STAT_RULES = {
    "projected_starting_xi_points": ("Highest projected starting XI", "Lowest projected starting XI", True),
    "average_player_projection": ("Strongest average player projection", "Low average player projection", True),
    "fantasy_points_per_90": ("Best last-season fantasy production", "Weak last-season production", True),
    "ghost_points_per_90": ("Highest ghost-point floor", "Low ghost-point floor", True),
    "historical_start_pct": ("Strong historical playing-time record", "Several historical playing-time risks", True),
    "projected_minutes_pct": ("Strongest projected playing-time security", "Several projected minutes risks", True),
    "average_adp": ("Most proven market profile", "Limited ADP support", False),
    "bench_projected_points": ("Strongest bench", "Thin bench", True),
}


def _weighted_rate(group: pd.DataFrame, total: str) -> float:
    values = pd.to_numeric(group.get(total), errors="coerce")
    minutes = pd.to_numeric(group.get("minutes_2526"), errors="coerce")
    valid = values.notna() & minutes.gt(0)
    return float(values[valid].sum() * 90 / minutes[valid].sum()) if valid.any() else np.nan


def build_share_summary(managers: pd.DataFrame, picks: pd.DataFrame) -> pd.DataFrame:
    """Build one row per manager without changing any grading input or score."""
    records = []
    for row in managers.sort_values(["overall_rank", "manager"]).itertuples():
        team = picks[picks["manager"].eq(row.manager)]
        starts = pd.to_numeric(team.get("starts_2526"), errors="coerce")
        opportunities = pd.to_numeric(team.get("weeks_available"), errors="coerce")
        valid_starts = starts.notna() & opportunities.gt(0)
        historical_start = float(starts[valid_starts].sum() / opportunities[valid_starts].sum() * 100) if valid_starts.any() else np.nan
        adp = pd.to_numeric(team.get("adp"), errors="coerce")
        records.append({
            "rank": int(row.overall_rank), "manager": row.manager, "grade": row.letter_grade,
            "league_relative_score": float(row.league_relative_score),
            "projected_starting_xi_points": float(row.best_xi_projected_points),
            "average_player_projection": pd.to_numeric(team.get("projected_points"), errors="coerce").mean(),
            "average_adp": adp.mean(), "fantasy_points_per_90": _weighted_rate(team, "total_fantasy_points"),
            "ghost_points_per_90": _weighted_rate(team, "ghost_points"),
            "historical_start_pct": historical_start,
            "projected_minutes_pct": pd.to_numeric(team.get("projected_minutes_share"), errors="coerce").mean(),
            "bench_projected_points": float(row.bench_projected_points),
            "best_pick": row.best_pick, "biggest_reach": row.biggest_reach,
        })
    out = pd.DataFrame(records)
    strength_rankings, concern_rankings = {}, {}
    for field, (_, _, higher_is_better) in STAT_RULES.items():
        values = pd.to_numeric(out[field], errors="coerce")
        rank = values.rank(method="min", ascending=not higher_is_better)
        percentile = values.rank(method="average", pct=True, ascending=higher_is_better).mul(100)
        out[f"{field}_league_rank"] = rank.astype("Int64")
        out[f"{field}_league_percentile"] = percentile
        strength_rankings[field] = rank
        concern_rankings[field] = values.rank(method="min", ascending=higher_is_better)
    strength_frame, concern_frame = pd.DataFrame(strength_rankings), pd.DataFrame(concern_rankings)
    out["main_strength"] = [STAT_RULES[field][0] for field in strength_frame.idxmin(axis=1)]
    out["main_concern"] = [STAT_RULES[field][1] for field in concern_frame.idxmin(axis=1)]
    return out


def share_csv(summary: pd.DataFrame) -> bytes:
    return summary[list(SHARE_COLUMNS)].to_csv(index=False).encode("utf-8-sig")


def share_html(summary: pd.DataFrame) -> str:
    ordered = summary.sort_values(["rank", "manager"])
    projection = ordered.sort_values(["projected_starting_xi_points", "manager"], ascending=[False, True]).iloc[0]
    floor = ordered.sort_values(["ghost_points_per_90", "manager"], ascending=[False, True]).iloc[0]
    value = ordered.sort_values(["average_adp", "manager"], ascending=[True, True]).iloc[0]
    winner = ordered.iloc[0]
    cards = (("Top Draft", f"{winner.manager} · {winner.grade}"), ("Highest Projected XI", f"{projection.manager} · {projection.projected_starting_xi_points:,.0f}"),
             ("Best Market Profile", f"{value.manager} · ADP {value.average_adp:.1f}"), ("Highest Floor", f"{floor.manager} · {floor.ghost_points_per_90:.1f}/90"))
    rows = "".join(f"<tr><td>{r.rank}</td><td>{html.escape(r.manager)}</td><td><b>{r.grade}</b></td><td>{r.projected_starting_xi_points:,.1f}</td><td>{r.average_player_projection:.1f}</td><td>{r.average_adp:.1f}</td><td>{r.fantasy_points_per_90:.1f}</td><td>{r.ghost_points_per_90:.1f}</td><td>{r.historical_start_pct:.1f}%</td><td>{r.projected_minutes_pct:.1f}%</td><td>{html.escape(r.main_strength)}</td><td>{html.escape(r.main_concern)}</td></tr>" for r in ordered.itertuples())
    manager_cards = "".join(f"<article class='manager top-{r.rank if r.rank <= 3 else 0}'><div class='rank'>#{r.rank}</div><h2>{html.escape(r.manager)} <span>{r.grade}</span></h2><div class='stats'><b>XI</b> {r.projected_starting_xi_points:,.0f}<b>ADP</b> {r.average_adp:.1f}<b>FP/90</b> {r.fantasy_points_per_90:.1f}<b>Ghost/90</b> {r.ghost_points_per_90:.1f}<b>Start</b> {r.historical_start_pct:.1f}%<b>Proj Min</b> {r.projected_minutes_pct:.1f}%</div><p><strong>Strength:</strong> {html.escape(r.main_strength)}<br><strong>Concern:</strong> {html.escape(r.main_concern)}</p></article>" for r in ordered.itertuples())
    return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>2026/27 League Draft Rankings</title><style>body{{font:14px system-ui;margin:0;background:#f4f7fb;color:#172033}}main{{max-width:1500px;margin:auto;padding:28px}}h1{{margin-bottom:4px}}.sub{{color:#61708a}}.headlines,.managers{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:22px 0}}.headline,.manager{{background:white;border:1px solid #dde5f0;border-radius:12px;padding:15px}}.headline b{{display:block;color:#62708a;font-size:12px;text-transform:uppercase}}.headline span{{font-size:18px;font-weight:750}}table{{width:100%;border-collapse:collapse;background:white;font-size:12px}}th,td{{padding:9px;border-bottom:1px solid #e7edf5;text-align:left}}th{{background:#172033;color:white;position:sticky;top:0}}.manager{{position:relative}}.manager h2{{font-size:17px;margin:0 0 10px}}.manager h2 span{{float:right;background:#172033;color:white;padding:3px 9px;border-radius:8px}}.rank{{position:absolute;right:14px;bottom:12px;font-size:28px;color:#e2e8f1;font-weight:800}}.stats{{display:grid;grid-template-columns:auto 1fr;gap:3px 8px;font-size:12px}}.top-1,.top-2,.top-3{{border-color:#d5aa3d}}@media(max-width:1000px){{.headlines,.managers{{grid-template-columns:repeat(2,1fr)}}.table-wrap{{overflow:auto}}}}@media(max-width:600px){{.headlines,.managers{{grid-template-columns:1fr}}}}</style></head><body><main><h1>2026/27 League Draft Rankings</h1><div class='sub'>12 managers · 180 picks</div><section class='headlines'>{''.join(f"<div class='headline'><b>{label}</b><span>{html.escape(value)}</span></div>" for label,value in cards)}</section><div class='table-wrap'><table><thead><tr><th>Rank</th><th>Manager</th><th>Grade</th><th>Projected XI</th><th>Avg Projection</th><th>Avg ADP</th><th>Fantasy/90</th><th>Ghost/90</th><th>Start %</th><th>Projected Minutes %</th><th>Main Strength</th><th>Main Concern</th></tr></thead><tbody>{rows}</tbody></table></div><section class='managers'>{manager_cards}</section><p class='sub'>Grades compare each draft against the other 11 league drafts using frozen draft-day projections and historical data. Missing ADP is excluded from averages.</p></main></body></html>"""


def group_chat_text(summary: pd.DataFrame, awards: pd.DataFrame) -> str:
    lines = ["2026/27 Draft Rankings", ""]
    for row in summary.sort_values(["rank", "manager"]).itertuples():
        lines.extend([f"{row.rank}. {row.manager} — {row.grade}", f"Projected XI: {row.projected_starting_xi_points:,.0f}",
                      f"Strength: {row.main_strength}", f"Concern: {row.main_concern}", ""])
    award_names = ("Highest Projected Team", "Highest Floor", "Best Value Draft", "Highest Ceiling", "Strongest Bench")
    lines.append("League Awards")
    for name in award_names:
        match = awards[awards["award"].eq(name)]
        if not match.empty: lines.append(f"- {name}: {match.iloc[0]['winner']}")
    return "\n".join(lines).rstrip() + "\n"
