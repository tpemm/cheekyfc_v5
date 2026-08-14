"""Fantrax Data v5 Streamlit entry point.

Run from the project root with:
    streamlit run app.py

The application shell owns shared layout and delegates each navigation branch
to an independent page module.
"""
from __future__ import annotations

from core.legacy_renderer import render_application


render_application()
