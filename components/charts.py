"""Shared Plotly presentation helpers; calculations remain in views."""
from __future__ import annotations
from typing import Any
from components.design_tokens import COLORS, SIZING

def apply_chart_theme(figure: Any, *, height: int | None = None) -> Any:
    figure.update_layout(template="plotly_white", height=height or SIZING["chart_height"],
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor=COLORS["card_background"],
        font={"color": COLORS["text_secondary"], "size": 12}, margin={"l":40,"r":20,"t":35,"b":40},
        legend={"orientation":"h","yanchor":"bottom","y":1.02,"xanchor":"right","x":1})
    figure.update_xaxes(gridcolor=COLORS["chart_grid"], zerolinecolor=COLORS["border"])
    figure.update_yaxes(gridcolor=COLORS["chart_grid"], zerolinecolor=COLORS["border"])
    return figure

def position_rank_axis(figure: Any) -> Any:
    figure.update_yaxes(autorange="reversed", dtick=1)
    return figure

def compact_legend(figure: Any) -> Any:
    figure.update_layout(legend={"orientation":"h","y":1.02,"x":0})
    return figure

def add_average_reference(figure: Any, value: float, *, label: str = "League average") -> Any:
    figure.add_hline(y=value, line_dash="dot", line_color=COLORS["neutral"], annotation_text=label)
    return figure
