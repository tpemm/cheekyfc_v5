"""Streamlit application shell.

The historical module name is retained as a compatibility entry point. All
page implementations live in ``views``; this module owns only shared shell
presentation, season selection, navigation, and renderer dispatch.
"""
from __future__ import annotations

from typing import Any

import streamlit as st

from config.project_paths import PROJECT_ROOT
from config.settings import (
    APP_NAME,
    APP_VERSION,
    DEFAULT_SEASON_ID,
    LEAGUE_NAME,
    PAGE_ICON,
    PAGE_LAYOUT,
    PAGE_TITLE,
)
from core.services import SeasonManager
from components.styles import global_css
from views.awards import render as render_awards
from views.draft_center import render as render_draft_center
from views.identity_review import render as render_identity_review
from views.key_output_health import render as render_key_output_health
from views.league_hub import render as render_league_hub
from views.live_league_hub import render as render_live_league_hub
from views.live_managers import render as render_live_managers
from views.managers import render as render_managers
from views.players import render as render_players
from views.historical_players import render as render_historical_players
from views.coming_soon import render as render_coming_soon
from views.cup_tournament import render as render_cup_tournament
from views.raw_data_browser import render as render_raw_data_browser
from views.registry import get_page, pages_for_season
from views.reports import render as render_reports
from views.update_pipeline import render as render_update_pipeline


_GLOBAL_CSS = """
<style>
:root {
    --surface: rgba(255, 255, 255, 0.92);
    --surface-soft: rgba(248, 250, 252, 0.94);
    --border: rgba(15, 23, 42, 0.10);
    --text-muted: #64748b;
    --shadow: 0 10px 30px rgba(15, 23, 42, 0.07);
}
.block-container { max-width: 1600px; padding-top: 3.75rem; padding-bottom: 3rem; }
.compact-header {
    display: flex; justify-content: space-between; align-items: center;
    gap: 18px; margin: -1.25rem 0 1.4rem; padding: 14px 18px;
    border: 1px solid var(--border); border-radius: 18px;
    background: var(--surface); box-shadow: var(--shadow);
}
.compact-kicker {
    color: var(--text-muted); font-size: .72rem; font-weight: 800;
    letter-spacing: .12em; text-transform: uppercase;
}
.compact-title { color: #0f172a; font-size: 1.25rem; font-weight: 800; }
.compact-meta { display: flex; gap: 8px; }
.compact-meta span {
    border: 1px solid var(--border); border-radius: 999px; padding: 5px 9px;
    color: #475569; background: #f8fafc; font-size: .72rem; font-weight: 700;
}
.section-title {
    color: #0f172a; font-size: 1.55rem; font-weight: 800;
    letter-spacing: -.02em; margin: .2rem 0 .3rem;
}
.section-subtitle, .section-copy, .hub-panel-copy {
    color: var(--text-muted); margin-bottom: 1.15rem;
}
.section-eyebrow {
    color: #2563eb; font-size: .72rem; font-weight: 800;
    letter-spacing: .12em; text-transform: uppercase;
}
.hub-panel-title { color: #0f172a; font-size: 1.08rem; font-weight: 800; }
.metric-card, .context-stat-card, .summary-card, .identity-card,
.reward-card, .award-podium {
    border: 1px solid var(--border); border-radius: 16px; padding: 15px 16px 14px;
    background: var(--surface); box-shadow: 0 6px 20px rgba(15,23,42,.04);
}
.context-stat-label { color: var(--text-muted); font-size: .76rem; font-weight: 700; }
.context-stat-value {
    color: #0f172a; font-size: 1.72rem; line-height: 1.05;
    font-weight: 500; letter-spacing: -.025em; margin: 8px 0 9px;
}
.context-stat-detail { color: var(--text-muted); font-size: .74rem; line-height: 1.3; }
.summary-value, .reward-metric, .award-value {
    color: #0f172a; font-size: 1.65rem; font-weight: 700; line-height: 1.1;
}
.summary-detail, .identity-note {
    color: var(--text-muted); font-size: .78rem; line-height: 1.35;
}
.reward-title-row {
    display: flex; justify-content: space-between; align-items: center; gap: 10px;
}
.reward-title, .award-name, .identity-name {
    color: #0f172a; font-size: .92rem; font-weight: 800;
}
.award-place {
    color: #2563eb; font-size: .72rem; font-weight: 800;
    letter-spacing: .1em; text-transform: uppercase;
}
.award-link { color: inherit; text-decoration: none; }
.identity-track, .form-strip { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.form-box {
    min-width: 28px; padding: 4px 7px; border-radius: 8px;
    text-align: center; color: white; font-size: .72rem; font-weight: 800;
}
.manager-hero {
    border: 1px solid var(--border); border-radius: 20px; padding: 22px;
    background: linear-gradient(135deg, rgba(255,255,255,.98), rgba(248,250,252,.94));
    box-shadow: var(--shadow); margin-bottom: 18px;
}
.manager-hero-grid {
    display: grid; grid-template-columns: 1.7fr repeat(4, 1fr); gap: 18px;
    align-items: center;
}
.manager-hero-stat { border-left: 1px solid var(--border); padding-left: 18px; }
.manager-hero-label, .manager-meta {
    color: var(--text-muted); font-size: .75rem; font-weight: 700;
}
.manager-hero-value { color: #0f172a; font-size: 1.45rem; font-weight: 700; }
.manager-name { color: #0f172a; font-size: 1.8rem; font-weight: 800; }
@media (max-width: 900px) {
    .compact-header { align-items: flex-start; flex-direction: column; }
    .manager-hero-grid { grid-template-columns: 1fr 1fr; }
    .manager-hero-stat { border-left: 0; padding-left: 0; }
}
</style>
"""


_GLOBAL_CSS = global_css()


def render_application(ui: Any = st, season_manager: SeasonManager | None = None) -> None:
    """Render the shared shell and exactly one registered page."""
    manager = season_manager or SeasonManager()
    seasons = manager.list_seasons()
    labels = [context.display_name for context in seasons]
    by_label = {context.display_name: context for context in seasons}
    default_context = manager.resolve(DEFAULT_SEASON_ID)
    default_index = labels.index(default_context.display_name)

    ui.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON, layout=PAGE_LAYOUT)
    selected_label = ui.sidebar.selectbox("Season", labels, index=default_index)
    context = by_label[selected_label]
    CURRENT_SEASON_ID = context.season_id

    ui.markdown(
        f"""
        <div class="compact-header">
            <div>
                <div class="compact-kicker">{LEAGUE_NAME} · {selected_label}</div>
                <div class="compact-title">{PAGE_ICON} {APP_NAME}</div>
            </div>
            <div class="compact-meta">
                <span>{context.status.replace('_', ' ').title()}</span>
                <span>v{APP_VERSION}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    ui.markdown(_GLOBAL_CSS, unsafe_allow_html=True)

    ui.sidebar.markdown(f"### {PAGE_ICON} {LEAGUE_NAME}")
    ui.sidebar.caption(f"{APP_NAME} · v{APP_VERSION}")
    available_pages = pages_for_season(context.season_id)
    page_options = [definition.title for definition in available_pages] or ["Reports"]

    query_page = ui.query_params.get("page")
    query_award = ui.query_params.get("award")
    if query_page in page_options:
        ui.session_state["page_nav"] = query_page
        if query_award:
            ui.session_state["pending_award"] = query_award
        ui.query_params.clear()
        ui.rerun()
    elif ui.session_state.get("page_nav") not in page_options:
        ui.session_state["page_nav"] = page_options[0]

    page = ui.sidebar.radio("Page", page_options, key="page_nav")
    definition = get_page(page)
    ui.sidebar.divider()
    ui.sidebar.write("Season data:")
    season_root = context.snapshot_root if context.finalized else context.working_root
    ui.sidebar.code(str(season_root), language="text")
    if context.finalized:
        ui.sidebar.success("Finalized historical season")
    elif not context.data_ready:
        ui.sidebar.info("Preseason tools available; league data not configured yet")
    ui.sidebar.write("Project root:")
    ui.sidebar.code(str(PROJECT_ROOT), language="text")

    if definition and definition.requires_season_data and not context.data_ready:
        ui.info(
            f"{page} requires configured league data for {selected_label}. "
            "Choose an available preseason or operations page from the sidebar."
        )
        ui.stop()

    # Keep routing explicit so each navigation branch has one obvious renderer.
    if page == "Home":
        render_live_league_hub(CURRENT_SEASON_ID)
    elif page == "League Hub":
        if CURRENT_SEASON_ID == "2627":
            render_live_league_hub(CURRENT_SEASON_ID)
        else:
            render_league_hub(CURRENT_SEASON_ID)
    elif page == "2025/26 Season Archive":
        render_league_hub(CURRENT_SEASON_ID)
    elif page == "Players":
        if CURRENT_SEASON_ID == "2526":
            render_historical_players(CURRENT_SEASON_ID)
        else:
            render_players(CURRENT_SEASON_ID)
    elif page == "Award Detail":
        render_awards(CURRENT_SEASON_ID)
    elif page == "Managers":
        if CURRENT_SEASON_ID == "2627":
            render_live_managers(CURRENT_SEASON_ID)
        else:
            render_managers(CURRENT_SEASON_ID)
    elif page == "Cup Tournament":
        render_cup_tournament(CURRENT_SEASON_ID)
    elif page in {"Trades", "Weekly Reports", "History"}:
        render_coming_soon(page, CURRENT_SEASON_ID)
    elif page == "Draft HQ":
        render_draft_center(CURRENT_SEASON_ID)
    elif page == "Identity Review":
        render_identity_review(CURRENT_SEASON_ID)
    elif page == "Operations Center":
        render_update_pipeline(CURRENT_SEASON_ID)
    elif page == "Raw Data Browser":
        render_raw_data_browser(CURRENT_SEASON_ID)
    elif page == "Key Output Health":
        render_key_output_health(CURRENT_SEASON_ID)
    elif page == "Reports":
        render_reports(CURRENT_SEASON_ID)


if __name__ == "__main__":
    render_application()
