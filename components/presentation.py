"""Accessible reusable presentation primitives."""
from __future__ import annotations
import html
from typing import Any
from components.styles import global_css

SHARED_COMPONENT_CSS = global_css()
MISSING = "—"

def _safe(value: Any) -> str: return html.escape(str(value))
def page_header(ui: Any, title: str, subtitle: str = "", *, eyebrow: str = "", badge: str = "", last_refreshed: str = "") -> None:
    meta = " · ".join(x for x in (badge, last_refreshed) if x)
    ui.markdown(f'<header class="ft-page-header"><div><div class="ft-eyebrow">{_safe(eyebrow)}</div><div class="ft-page-title">{_safe(title)}</div><div class="ft-page-subtitle">{_safe(subtitle)}</div></div><div class="ft-meta">{_safe(meta)}</div></header>', unsafe_allow_html=True)

def section_header(ui: Any, title: str, copy: str = "", *, eyebrow: str = "", badge: str = "") -> None:
    ui.markdown(f'<div class="section-eyebrow">{_safe(eyebrow)}</div><div class="section-title">{_safe(title)} {status_badge(badge) if badge else ""}</div><div class="section-copy">{_safe(copy)}</div>', unsafe_allow_html=True)

def metric_card(ui: Any, label: str, value: Any, detail: str = "", *, tone: str = "neutral", trend: str = "", rank: str = "", compact: bool = False) -> None:
    shown = MISSING if value is None or str(value) in {"nan", "None", "<NA>"} else value
    suffix = " · ".join(x for x in (detail, trend, rank) if x)
    ui.markdown(f'<div class="ft-card"><div class="ft-label">{_safe(label)}</div><div class="ft-kpi-value">{_safe(shown)}</div><div class="ft-detail">{_safe(suffix)}</div></div>', unsafe_allow_html=True)

def status_badge(text: str, *, tone: str = "neutral") -> str:
    tone_map={"good":"positive","green":"positive","risk":"negative","red":"negative","gold":"warning","blue":"accent"}
    return f'<span class="ft-badge ft-badge-{tone_map.get(tone,tone)}">{_safe(text)}</span>'
status_pill = status_badge

def empty_state(ui: Any, title: str, copy: str, *, action: str = "", compact: bool = False) -> None:
    next_step=f'<div class="ft-detail">Next: {_safe(action)}</div>' if action else ""
    ui.markdown(f'<div class="ft-empty"><div class="ft-empty-title">{_safe(title)}</div><div class="ft-empty-copy">{_safe(copy)}</div>{next_step}</div>', unsafe_allow_html=True)

def notice_card(ui: Any, title: str, copy: str, *, tone: str = "neutral") -> None:
    ui.markdown(f'<div class="ft-notice"><div class="ft-empty-title">{status_badge(tone.title(), tone=tone)} {_safe(title)}</div><div class="ft-empty-copy">{_safe(copy)}</div></div>', unsafe_allow_html=True)

def percentile_bar(label: str, percentile: float | None, *, rank: str = "", value: str = "") -> str:
    numeric=0 if percentile is None else max(0,min(100,float(percentile))); shown=MISSING if percentile is None else f"{numeric:.0f}%"
    context=" · ".join(x for x in (shown, rank, value) if x)
    return f'<div class="ft-percentile"><span>{_safe(label)}</span><span class="ft-percentile-track"><i class="ft-percentile-fill" style="width:{numeric:.1f}%"></i></span><b>{_safe(context)}</b></div>'

def manager_card_html(row: dict[str, Any]) -> str:
    return f'<div class="ft-card"><div class="ft-label">Rank {_safe(row.get("rank",MISSING))}</div><div class="ft-kpi-value" style="font-size:1rem">{_safe(row.get("team") or row.get("manager","Unknown"))}</div><div class="ft-detail">{_safe(row.get("manager",""))} · {_safe(row.get("record",MISSING))} · {_safe(row.get("form","No form yet"))}</div><div class="ft-detail" style="margin-top:.55rem">PF {_safe(row.get("points_for",MISSING))} · PA {_safe(row.get("points_against",MISSING))} · Avg {_safe(row.get("average_score",MISSING))}</div></div>'

def format_value(value: Any, *, digits: int = 1, percent: bool = False) -> str:
    try:
        if value is None or value != value: return MISSING
        suffix="%" if percent else ""
        return f"{float(value):,.{digits}f}{suffix}"
    except (TypeError, ValueError): return MISSING if value is None else str(value)
