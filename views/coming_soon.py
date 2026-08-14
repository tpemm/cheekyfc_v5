"""Purposeful placeholders for planned live-season surfaces."""
from __future__ import annotations

from typing import Any
import streamlit as st

from components.presentation import SHARED_COMPONENT_CSS, empty_state, page_header


def render(title: str, season_id: str, *, ui: Any = st) -> None:
    ui.markdown(SHARED_COMPONENT_CSS, unsafe_allow_html=True)
    page_header(
        ui, title, "This live-season workspace is prepared for a future sprint.",
        eyebrow="Product roadmap", badge=f"{season_id} · Coming Soon",
    )
    empty_state(
        ui, f"{title} is coming soon",
        "The page is reserved, but no provisional analytics are being substituted for unavailable models.",
        action="Return to League Hub or choose another available page.",
    )
