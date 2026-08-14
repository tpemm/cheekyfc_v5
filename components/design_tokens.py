"""Semantic design tokens for the Fantrax application UI.

Views should reference these names (or the CSS variables generated from them)
instead of introducing page-specific palette values.
"""
from __future__ import annotations

COLORS = {
    "app_background": "#f4f6f8", "card_background": "#ffffff",
    "elevated_surface": "#f8fafc", "border": "#d9e0e8",
    "muted_border": "#e8edf2", "text_primary": "#17212b",
    "text_secondary": "#526171", "text_muted": "#748190",
    "accent": "#176b87", "accent_hover": "#10556c",
    "positive": "#287a5b", "above_average": "#4d7298",
    "neutral": "#667788", "warning": "#a66a18", "negative": "#b34d4a",
    "missing_data": "#8a96a3", "chart_grid": "#e6ebf0",
    "table_header": "#eef3f6", "selected_row": "#e7f1f5",
}

SPACING = {
    "page_padding": "1.5rem", "section_gap": "1.5rem", "card_gap": "0.75rem",
    "card_padding": "1rem", "control_gap": "0.5rem", "metric_gap": "0.625rem",
}

SIZING = {
    "page_max_width": "1480px", "compact_content_width": "1120px",
    "card_radius": "12px", "control_radius": "8px", "table_row_height": 36,
    "chart_height": 350, "compact_chart_height": 280, "modal_width": "1050px",
}

TYPOGRAPHY = {
    "page_eyebrow": "0.72rem", "page_title": "2rem", "section_title": "1.18rem",
    "card_title": "0.9rem", "metric_label": "0.72rem", "metric_value": "1.45rem",
    "annotation": "0.78rem", "table_text": "0.82rem", "badge_text": "0.68rem",
}

def css_variables() -> str:
    values = {**COLORS, **SPACING, **{k: v for k, v in SIZING.items() if isinstance(v, str)}, **TYPOGRAPHY}
    return ";\n".join(f"--ft-{key.replace('_', '-')}: {value}" for key, value in values.items())
