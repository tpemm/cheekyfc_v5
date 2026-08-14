"""Draft HQ page backed by the foundation data services."""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from core.models.data_result import DataStatus
from core.services.data_manager import (
    DataManager,
    DatasetNotFoundError,
    DatasetValidationError,
    UnsupportedFormatError,
)
from core.services.season_manager import SeasonManager
from analytics.draft.presentation import (
    AVAILABLE,
    DRAFTED_BY_ME,
    DRAFTED_BY_OTHER,
    add_explicit_rate_metrics,
    apply_draft_statuses,
    build_tier_board,
    comparison_table,
    draft_score_explanation,
    explanation_reconciles,
    normalize_fantrax_positions,
    position_matches,
    reset_draft_session,
    set_draft_status,
    stable_player_key,
    sort_draft_board,
    update_queue,
)
from analytics.players.comparison import add_compare, stable_player_id


DATASET_KEYS: tuple[str, ...] = (
    "draft_rankings",
    "draft_eligibility_overrides",
)


def _load_frame(
    data: DataManager,
    dataset_key: str,
    season_id: str,
    namespace: str,
    ui: Any,
) -> pd.DataFrame:
    try:
        result = data.load_frame(dataset_key, season_id, namespace)
    except DatasetNotFoundError:
        return pd.DataFrame()
    except (DatasetValidationError, UnsupportedFormatError) as exc:
        ui.warning(str(exc))
        return pd.DataFrame()
    if result.status in {DataStatus.MISSING, DataStatus.EMPTY}:
        return pd.DataFrame()
    if result.status is DataStatus.INVALID:
        messages = (*result.validation_errors, *result.warnings)
        ui.warning("; ".join(messages) if messages else "Dataset validation failed.")
        return pd.DataFrame()
    return result.data.copy() if isinstance(result.data, pd.DataFrame) else pd.DataFrame()


def coerce_boolean_series(values: pd.Series, default: bool = False) -> pd.Series:
    true_values = {"true", "1", "yes", "y", "t"}
    false_values = {"false", "0", "no", "n", "f", "", "none", "nan", "null"}

    def convert(value: Any) -> bool:
        if pd.isna(value):
            return default
        if isinstance(value, (bool, np.bool_)):
            return bool(value)
        if isinstance(value, (int, float, np.integer, np.floating)):
            return bool(value)
        text = str(value).strip().casefold()
        if text in true_values:
            return True
        if text in false_values:
            return False
        return default

    return values.map(convert).astype(bool)


def format_value(value: Any) -> str:
    if pd.isna(value):
        return ""
    try:
        number = float(value)
        if number.is_integer():
            return str(int(number))
        return f"{number:.1f}"
    except Exception:
        return str(value)


def render_context_stat(
    container: Any,
    label: str,
    value: Any,
    detail: str | None = None,
) -> None:
    value_text = format_value(value) or "—"
    detail_text = (
        str(detail).strip()
        if detail is not None and str(detail).strip()
        else "No additional context available"
    )
    container.markdown(
        f'<div class="context-stat-card">'
        f'<div class="context-stat-label">{label}</div>'
        f'<div class="context-stat-value">{value_text}</div>'
        f'<div class="context-stat-detail">{detail_text}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render(
    season_id: str,
    *,
    data_manager: DataManager | None = None,
    season_manager: SeasonManager | None = None,
    ui: Any = st,
) -> None:
    """Render the existing Draft HQ workflow."""

    seasons = season_manager or SeasonManager()
    season = seasons.context(season_id)
    namespace = seasons.resolve_namespace(season.season_id)
    data = data_manager or DataManager(season_manager=seasons)
    st = ui

    st.markdown(
        '<div class="section-eyebrow">2026/27 preparation</div>'
        '<div class="section-title">Draft HQ</div>'
        '<div class="section-copy">Current Fantrax player rankings built from historical production, minutes outlook, underlying attacking data, team strength, and opening fixtures.</div>',
        unsafe_allow_html=True,
    )

    draft_df = _load_frame(data, "draft_rankings", season.season_id, namespace, ui)

    if draft_df.empty:
        st.warning(
            "Draft rankings are missing or empty. Run "
            "`python scripts\\build_draft_tool_v1_1_2627.py` first."
        )
        st.caption("Expected registered dataset: draft_rankings")
        st.stop()

    unresolved_eligibility = (
        draft_df.get("draft_eligibility_status", pd.Series("", index=draft_df.index))
        .astype(str)
        .str.startswith("Unresolved")
    )
    unresolved_count = int(unresolved_eligibility.sum())
    if unresolved_count:
        st.warning(
            f"Current EPL squad confirmation is incomplete for {unresolved_count} players; "
            "they remain visible pending source verification. Fantrax FA means undrafted."
        )

    # Normalize common numeric fields for filtering and display.
    numeric_draft_cols = [
        "overall_rank", "draft_score", "fantrax_adp", "fantrax_adp_rank",
        "value_vs_adp", "projected_minutes_share", "minutes_confidence",
        "fantasy_ppg_2526", "ghost_ppg_2526", "fantasy_fp90_2526",
        "xgi90_2526", "team_attack_rating", "team_defense_rating",
        "team_strength_rating", "fixture_ease_next_3",
        "fixture_ease_next_5", "fixture_ease_next_10",
        "data_confidence",
        "fantrax_projected_points", "fantrax_projected_ppg",
    ]
    for column in numeric_draft_cols:
        if column in draft_df.columns:
            draft_df[column] = pd.to_numeric(draft_df[column], errors="coerce")

    # Resolve display columns defensively so the page survives small builder changes.
    draft_name_col = next(
        (c for c in ["player_name", "fantrax_player_name", "historical_name"] if c in draft_df.columns),
        None,
    )
    draft_team_col = next(
        (c for c in ["team_2627", "team", "club"] if c in draft_df.columns),
        None,
    )
    draft_position_col = next(
        (c for c in ["position_2627", "position", "positions"] if c in draft_df.columns),
        None,
    )

    if not draft_name_col:
        st.error("The draft rankings file does not contain a recognizable player-name column.")
        st.write(list(draft_df.columns))
        st.stop()

    draft_df["Player"] = draft_df[draft_name_col].fillna("Unknown player").astype(str)
    draft_df["Team"] = (
        draft_df[draft_team_col].fillna("UNK").astype(str)
        if draft_team_col else "UNK"
    )
    draft_df["Position"] = (
        draft_df[draft_position_col].fillna("Unknown").astype(str)
        if draft_position_col else "Unknown"
    )
    fantrax_position_col = next(
        (
            c for c in [
                "fantrax_position_eligibility", "fantrax_position",
                "position_2627",
            ] if c in draft_df.columns
        ),
        None,
    )
    draft_df["Fantrax Positions"] = (
        draft_df[fantrax_position_col].map(normalize_fantrax_positions)
        if fantrax_position_col else draft_df["Position"]
    )

    rank_series = pd.to_numeric(draft_df.get("overall_rank"), errors="coerce")
    draft_df["Rank"] = rank_series.astype("Int64")
    draft_df["Draft Score"] = pd.to_numeric(draft_df.get("draft_score"), errors="coerce")
    # Fantrax ADP is the decimal market value from the preseason export.
    # RkOv / fantrax_overall_rank is a separate Fantrax projection ranking.
    draft_df["ADP"] = pd.to_numeric(draft_df.get("fantrax_adp"), errors="coerce")
    draft_df["Value vs ADP"] = pd.to_numeric(draft_df.get("value_vs_adp"), errors="coerce")
    draft_df["Minutes %"] = pd.to_numeric(draft_df.get("projected_minutes_share"), errors="coerce")
    draft_df["Minutes Confidence"] = pd.to_numeric(draft_df.get("minutes_confidence"), errors="coerce")
    draft_df["Data Confidence"] = pd.to_numeric(draft_df.get("data_confidence"), errors="coerce")
    draft_df = add_explicit_rate_metrics(draft_df)
    session_state = getattr(st, "session_state", {})
    if "draft_player_statuses" not in session_state:
        session_state["draft_player_statuses"] = {}
    if "draft_sequence" not in session_state:
        session_state["draft_sequence"] = []
    draft_df = apply_draft_statuses(
        draft_df, session_state.get("draft_player_statuses", {})
    )

    team_status = draft_df["Team"].fillna("").astype(str).str.upper().str.strip()
    if "is_free_agent" in draft_df.columns:
        draft_df["Is Free Agent"] = coerce_boolean_series(draft_df["is_free_agent"], default=False)
    else:
        draft_df["Is Free Agent"] = team_status.eq("FA")
    if "is_draft_eligible" in draft_df.columns:
        draft_df["Draft Eligible"] = coerce_boolean_series(draft_df["is_draft_eligible"], default=False)
    else:
        draft_df["Draft Eligible"] = ~team_status.isin(["", "FA", "UNK", "N/A", "NA"])
    draft_df["Roster Status"] = np.where(
        draft_df["Draft Eligible"], "Draft eligible", "FA / not current EPL roster"
    )

    # Fantrax preseason Status=FA means undrafted fantasy free agent for every
    # player. Apply separate real-world EPL eligibility overrides instead.
    eligibility_overrides = _load_frame(
        data,
        "draft_eligibility_overrides",
        season.season_id,
        namespace,
        ui,
    )
    if not eligibility_overrides.empty:
        draft_ids = draft_df.get("fantrax_player_id", pd.Series("", index=draft_df.index)).astype(str).str.lower().str.replace(r"[^a-z0-9]", "", regex=True)
        draft_names = draft_df["Player"].astype(str).str.casefold().str.strip()
        for _, override in eligibility_overrides.iterrows():
            mask = pd.Series(False, index=draft_df.index)
            override_id = re.sub(r"[^a-z0-9]", "", str(override.get("fantrax_player_id", "")).casefold())
            override_name = str(override.get("player_name", "")).casefold().strip()
            if override_id:
                mask = draft_ids.eq(override_id)
                if override_name and mask.any() and not (
                    mask & draft_names.eq(override_name)
                ).any():
                    continue
            elif override_name:
                name_mask = draft_names.eq(override_name)
                if int(name_mask.sum()) != 1:
                    continue
                mask = name_mask
            if not mask.any():
                continue
            eligible_text = str(override.get("is_draft_eligible", "")).strip().casefold()
            eligible = eligible_text in {"true", "1", "yes", "y"}
            draft_df.loc[mask, "Draft Eligible"] = eligible
            draft_df.loc[mask, "Is Free Agent"] = not eligible
            current_team = str(override.get("current_team", "")).strip().upper()
            if current_team:
                draft_df.loc[mask, "Team"] = current_team
            reason = str(override.get("reason", "Eligibility override")).strip()
            draft_df.loc[mask, "Roster Status"] = "Draft eligible" if eligible else reason

    # -------------------------------------------------------------------------
    # Controls
    # -------------------------------------------------------------------------
    st.markdown('<div class="hub-panel-title">Draft Board</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="hub-panel-copy">Filter the complete current Fantrax player pool. Rankings update from the generated draft model file.</div>',
        unsafe_allow_html=True,
    )

    filters_panel = st.expander("Filters", expanded=False)
    filter_row_1 = filters_panel.columns([1.3, 1.1, 1.1, 1.1, 1.2])
    with filter_row_1[0]:
        draft_search = st.text_input(
            "Search player",
            placeholder="Player name",
            key="draft_player_search",
        )
    with filter_row_1[1]:
        position_options = sorted({
            position
            for value in draft_df["Fantrax Positions"]
            for position in str(value).split("/")
            if position
        })
        selected_draft_positions = st.multiselect(
            "Positions",
            position_options,
            default=position_options,
            key="draft_positions",
        )
    with filter_row_1[2]:
        team_options = sorted(draft_df["Team"].dropna().astype(str).unique())
        selected_draft_teams = st.multiselect(
            "Teams",
            team_options,
            default=team_options,
            key="draft_teams",
        )
    with filter_row_1[3]:
        tier_options = sorted(
            draft_df.get("tier", pd.Series(dtype=str)).dropna().astype(str).unique(),
            key=lambda value: int(re.search(r"\d+", value).group())
            if re.search(r"\d+", value) else 999,
        )
        selected_tiers = st.multiselect(
            "Tiers", tier_options, default=tier_options, key="draft_tiers"
        )
    with filter_row_1[4]:
        minutes_options = sorted(
            draft_df.get("minutes_outlook", pd.Series(dtype=str))
            .dropna().astype(str).unique()
        )
        selected_minutes_outlooks = st.multiselect(
            "Minutes outlook", minutes_options, default=minutes_options,
            key="draft_minutes_outlook",
        )

    filter_row_2 = filters_panel.columns([1, 1, 1, 1])
    with filter_row_2[0]:
        max_minutes = int(max(0, pd.to_numeric(
            draft_df.get("minutes_2526", pd.Series([0])), errors="coerce"
        ).max() or 0))
        minimum_minutes = st.slider(
            "Minimum minutes", 0, max(max_minutes, 1), 0, key="draft_min_minutes"
        )
    with filter_row_2[1]:
        max_starts = int(max(0, pd.to_numeric(
            draft_df.get("starts_2526", pd.Series([0])), errors="coerce"
        ).max() or 0))
        minimum_starts = st.slider(
            "Minimum starts", 0, max(max_starts, 1), 0, key="draft_min_starts"
        )
    with filter_row_2[2]:
        adp_values = draft_df["ADP"].dropna()
        adp_bounds = (
            float(adp_values.min()), float(adp_values.max())
        ) if not adp_values.empty else (0.0, 500.0)
        adp_range = st.slider(
            "ADP range", adp_bounds[0], adp_bounds[1], adp_bounds,
            key="draft_adp_range",
        )
    with filter_row_2[3]:
        score_values = draft_df["Draft Score"].dropna()
        score_bounds = (
            float(score_values.min()), float(score_values.max())
        ) if not score_values.empty else (0.0, 100.0)
        score_range = st.slider(
            "Draft Score range", score_bounds[0], score_bounds[1], score_bounds,
            key="draft_score_range",
        )

    filter_row_3 = filters_panel.columns([1, 1, 1, 1])
    with filter_row_3[0]:
        minimum_confidence = st.slider(
            "Minimum confidence", 0, 100, 25, key="draft_min_confidence",
        )
    with filter_row_3[1]:
        rank_limit = st.selectbox(
            "Rank range", [50, 100, 150, 200, 300, "All"],
            index=3, key="draft_rank_limit",
        )
    with filter_row_3[2]:
        history_only = st.checkbox(
            "2025/26 history only", value=False, key="draft_history_only",
        )
    with filter_row_3[3]:
        include_free_agents = st.checkbox(
            "Include ineligible players",
            value=False,
            key="draft_include_free_agents",
            help="Players excluded by the current-EPL eligibility file are hidden by default. Fantrax Status=FA only means undrafted.",
        )
    status_filters = filters_panel.columns(2)
    with status_filters[0]:
        include_drafted_by_me = st.checkbox(
            "Include Drafted by Me", value=False, key="draft_include_mine"
        )
    with status_filters[1]:
        include_drafted_by_other = st.checkbox(
            "Include Drafted by Other", value=False, key="draft_include_other"
        )

    sort_row = filters_panel.columns([1.2, 1, 1, 1.8])
    with sort_row[0]:
        draft_sort_by = st.selectbox(
            "Sort board by",
            ["Model Rank", "ADP", "Value vs ADP", "Draft Score", "Ghost / Appearance"],
            index=0,
            key="draft_sort_by",
        )
    with sort_row[1]:
        draft_sort_direction = st.selectbox(
            "Direction",

            ["Ascending", "Descending"],
            index=0,
            key="draft_sort_direction",
        )
    with sort_row[2]:
        board_view = st.selectbox(
            "Board view", ["Rankings", "Board by Tier"],
            key="draft_board_view",
        )
    with sort_row[3]:
        st.caption("The board sort always places missing ADP values last. Fantrax ADP can be refreshed by replacing the preseason export and rebuilding.")

    filtered_draft = draft_df.copy()

    if not include_free_agents:
        filtered_draft = filtered_draft[filtered_draft["Draft Eligible"]].copy()
    visible_statuses = [AVAILABLE]
    if include_drafted_by_me:
        visible_statuses.append(DRAFTED_BY_ME)
    if include_drafted_by_other:
        visible_statuses.append(DRAFTED_BY_OTHER)
    filtered_draft = filtered_draft[
        filtered_draft["Draft Status"].isin(visible_statuses)
    ]

    if draft_search.strip():
        filtered_draft = filtered_draft[
            filtered_draft["Player"].str.contains(
                draft_search.strip(),
                case=False,
                na=False,
                regex=False,
            )
        ]

    if selected_draft_positions:
        filtered_draft = filtered_draft[
            filtered_draft["Fantrax Positions"].map(
                lambda value: position_matches(value, selected_draft_positions)
            ).astype(bool)
        ]
    else:
        filtered_draft = filtered_draft.iloc[0:0]

    if selected_draft_teams:
        filtered_draft = filtered_draft[
            filtered_draft["Team"].isin(selected_draft_teams)
        ]
    else:
        filtered_draft = filtered_draft.iloc[0:0]

    if tier_options:
        if selected_tiers:
            filtered_draft = filtered_draft[
                filtered_draft["tier"].astype(str).isin(selected_tiers)
            ]
        else:
            filtered_draft = filtered_draft.iloc[0:0]
    if minutes_options:
        if selected_minutes_outlooks:
            filtered_draft = filtered_draft[
                filtered_draft["minutes_outlook"].astype(str).isin(
                    selected_minutes_outlooks
                )
            ]
        else:
            filtered_draft = filtered_draft.iloc[0:0]

    filtered_draft = filtered_draft[
        pd.to_numeric(filtered_draft.get(
            "minutes_2526", pd.Series(np.nan, index=filtered_draft.index)
        ), errors="coerce")
        .fillna(0).ge(minimum_minutes)
        & pd.to_numeric(filtered_draft.get(
            "starts_2526", pd.Series(np.nan, index=filtered_draft.index)
        ), errors="coerce")
        .fillna(0).ge(minimum_starts)
    ]
    filtered_draft = filtered_draft[
        filtered_draft["Data Confidence"].fillna(0).ge(minimum_confidence)
    ]
    filtered_draft = filtered_draft[
        filtered_draft["Draft Score"].between(*score_range, inclusive="both")
    ]
    # Missing ADP remains visible; when present it must satisfy the selected range.
    filtered_draft = filtered_draft[
        filtered_draft["ADP"].isna()
        | filtered_draft["ADP"].between(*adp_range, inclusive="both")
    ]

    if rank_limit != "All":
        filtered_draft = filtered_draft[
            filtered_draft["Rank"].fillna(9999).le(int(rank_limit))
        ]

    if history_only:
        history_col = next(
            (c for c in ["historical_name", "fantasy_points_2526", "minutes_2526"] if c in filtered_draft.columns),
            None,
        )
        if history_col == "historical_name":
            filtered_draft = filtered_draft[filtered_draft[history_col].notna()]
        elif history_col:
            filtered_draft = filtered_draft[
                pd.to_numeric(filtered_draft[history_col], errors="coerce").notna()
            ]

    sort_column_map = {
        "Model Rank": "Rank",
        "ADP": "ADP",
        "Value vs ADP": "Value vs ADP",
        "Draft Score": "Draft Score",
        "Ghost / Appearance": "ghost_per_appearance_2526",
    }
    primary_sort_col = sort_column_map[draft_sort_by]
    ascending_sort = draft_sort_direction == "Ascending"
    filtered_draft = sort_draft_board(
        filtered_draft, primary_sort_col, ascending_sort
    )

    # -------------------------------------------------------------------------
    # Headline metrics
    # -------------------------------------------------------------------------
    with st.expander("Draft Status", expanded=False):
        status_counts = draft_df["Draft Status"].value_counts()
        status_columns = st.columns(4)
        render_context_stat(
            status_columns[0], AVAILABLE, status_counts.get(AVAILABLE, 0)
        )
        render_context_stat(
            status_columns[1], DRAFTED_BY_ME,
            status_counts.get(DRAFTED_BY_ME, 0),
        )
        render_context_stat(
            status_columns[2], DRAFTED_BY_OTHER,
            status_counts.get(DRAFTED_BY_OTHER, 0),
        )
        drafted_count = status_counts.get(DRAFTED_BY_ME, 0) + status_counts.get(
            DRAFTED_BY_OTHER, 0
        )
        render_context_stat(
            status_columns[3], "Total Marked Drafted", drafted_count
        )
        if hasattr(st, "button"):
            confirm_reset = st.checkbox(
                "Confirm reset of session statuses and queue",
                key="draft_reset_confirm",
            )
            if st.button(
                "Reset Draft Session",
                disabled=not confirm_reset,
                key="draft_reset_session",
            ):
                reset_draft_session(st.session_state)
                st.rerun()

    total_players = len(draft_df)
    history_count = (
        int(draft_df["historical_name"].notna().sum())
        if "historical_name" in draft_df.columns else 0
    )
    understat_count = (
        int(
            draft_df["understat_player_id"]
            .replace("", pd.NA)
            .notna()
            .sum()
        )
        if "understat_player_id" in draft_df.columns else 0
    )
    adp_count = int(draft_df["ADP"].notna().sum())
    average_confidence = filtered_draft["Data Confidence"].mean()

    metric_cols = st.columns(5)
    render_context_stat(metric_cols[0], "Players Shown", len(filtered_draft), f"{total_players:,} in current Fantrax pool")
    render_context_stat(metric_cols[1], "Historical Matches", history_count, "Players linked to 2025/26 Fantrax data")
    render_context_stat(metric_cols[2], "Understat Matches", understat_count, "Players with underlying attacking data")
    render_context_stat(metric_cols[3], "ADP Available", adp_count, "Current Fantrax market data")
    render_context_stat(metric_cols[4], "Average Confidence", average_confidence, "For currently filtered players")

    fa_count = int(draft_df["Is Free Agent"].sum())
    if fa_count:
        st.caption(f"{fa_count} players are marked ineligible for the current EPL season and are excluded from rankings by default.")

    # -------------------------------------------------------------------------
    # Decision panels
    # -------------------------------------------------------------------------
    eligible_with_adp = filtered_draft[
        filtered_draft["Draft Eligible"] & filtered_draft["ADP"].notna()
    ].copy()
    value_panel, reach_panel, ghost_panel = st.columns(3, gap="large")

    with value_panel:
        st.markdown("#### Best ADP Values")
        best_values = eligible_with_adp.sort_values(
            ["Value vs ADP", "Draft Score"], ascending=[False, False], na_position="last"
        ).head(8)
        value_cols = [c for c in ["Player", "Team", "Position", "Rank", "ADP", "Value vs ADP"] if c in best_values.columns]
        if best_values.empty:
            st.info("No players with ADP match the current filters.")
        else:
            st.dataframe(best_values[value_cols], width="stretch", hide_index=True, height=315)

    with reach_panel:
        st.markdown("#### Market Reaches")
        reaches = eligible_with_adp.sort_values(
            ["Value vs ADP", "Draft Score"], ascending=[True, False], na_position="last"
        ).head(8)
        reach_cols = [c for c in ["Player", "Team", "Position", "Rank", "ADP", "Value vs ADP"] if c in reaches.columns]
        if reaches.empty:
            st.info("No players with ADP match the current filters.")
        else:
            st.dataframe(reaches[reach_cols], width="stretch", hide_index=True, height=315)

    with ghost_panel:
        st.markdown("#### Ghost-Point Leaders")
        ghost_leaders = filtered_draft[filtered_draft["Draft Eligible"]].sort_values(
            ["ghost_per_appearance_2526", "Draft Score"],
            ascending=[False, False], na_position="last"
        ).head(8)
        ghost_cols = [c for c in ["Player", "Team", "Position", "Rank", "ghost_per_appearance_2526", "fantasy_per_appearance_2526"] if c in ghost_leaders.columns]
        ghost_table = ghost_leaders[ghost_cols].rename(columns={"ghost_per_appearance_2526": "Ghost / Appearance", "fantasy_per_appearance_2526": "Points / Appearance"})
        if ghost_table.empty:
            st.info("No ghost-point history matches the current filters.")
        else:
            st.dataframe(ghost_table, width="stretch", hide_index=True, height=315)

    # -------------------------------------------------------------------------
    # Main rankings table
    # -------------------------------------------------------------------------
    draft_display_map = {
        "Rank": "Rank",
        "Player": "Player",
        "Team": "Team",
        "Position": "Pos",
        "Fantrax Positions": "Fantrax Pos",
        "Draft Status": "Status",
        "Roster Status": "Roster Status",
        "tier": "Tier",
        "Draft Score": "Draft Score",
        "ADP": "ADP",
        "fantrax_projected_points": "Projected Points",
        "Value vs ADP": "Value vs ADP",
        "adp_status": "ADP Signal",
        "minutes_outlook": "Minutes Outlook",
        "Minutes %": "Minutes %",
        "Minutes Confidence": "Minutes Confidence",
        "fantasy_points_2526": "Fantasy Points",
        "fantasy_per_appearance_2526": "Points / Appearance",
        "fantasy_per_start_2526": "Points / Start",
        "fantasy_per90_2526": "Points / 90",
        "ghost_points_2526": "Ghost Points",
        "ghost_per_appearance_2526": "Ghost / Appearance",
        "ghost_per_start_2526": "Ghost / Start",
        "ghost_per90_2526": "Ghost / 90",
        "minutes_2526": "Minutes",
        "appearances_2526": "Appearances",
        "starts_2526": "Starts",
        "nineties_2526": "90s",
        "xgi90_2526": "xG+xA / 90",
        "team_attack_rating": "Team Attack",
        "team_strength_rating": "Team Strength",
        "fixture_ease_next_5": "Fixtures N5",
        "fixture_ease_next_10": "Fixtures N10",
        "Data Confidence": "Confidence",
    }
    display_source_cols = [
        source for source in draft_display_map if source in filtered_draft.columns
    ]
    draft_table = filtered_draft[display_source_cols].rename(
        columns=draft_display_map
    ).copy()

    numeric_round_cols = [
        "Draft Score", "ADP", "Projected Points", "Value vs ADP", "Minutes %", "Minutes Confidence",
        "Fantasy Points", "Points / Appearance", "Points / Start", "Points / 90",
        "Ghost Points", "Ghost / Appearance", "Ghost / Start", "Ghost / 90",
        "Minutes", "Appearances", "Starts", "90s", "xG+xA / 90",
        "Team Attack", "Team Strength", "Fixtures N5", "Fixtures N10",
        "Confidence",
    ]
    for column in numeric_round_cols:
        if column in draft_table.columns:
            draft_table[column] = pd.to_numeric(
                draft_table[column], errors="coerce"

            ).round(1)

    board_config = {
            "Rank": st.column_config.NumberColumn("Rank", format="%d", width="small"),
            "Player": st.column_config.TextColumn(
                "Player", width="large", pinned=True
            ),
            "Team": st.column_config.TextColumn(
                "Team", width="small", pinned=True
            ),
            "Pos": st.column_config.TextColumn("Pos", width="small"),
            "Fantrax Pos": st.column_config.TextColumn(
                "Fantrax Pos", width="small", pinned=True
            ),
            "Draft Score": st.column_config.NumberColumn("Draft Score", format="%.1f"),
            "ADP": st.column_config.NumberColumn("ADP", format="%.1f"),
            "Projected Points": st.column_config.NumberColumn(
                "Projected Points", format="%.1f"
            ),
            "Value vs ADP": st.column_config.NumberColumn("Value vs ADP", format="%+.1f"),
            "Minutes %": st.column_config.ProgressColumn(
                "Minutes %", min_value=0, max_value=100, format="%.0f%%"
            ),
            "Minutes Confidence": st.column_config.ProgressColumn(
                "Minutes Confidence", min_value=0, max_value=100, format="%.0f%%"
            ),
            "Confidence": st.column_config.ProgressColumn(
                "Confidence", min_value=0, max_value=100, format="%.0f%%"
            ),
    }
    if board_view == "Board by Tier":
        tier_groups = build_tier_board(filtered_draft)
        if not tier_groups:
            st.info("No tier data is available.")
        for tier_name, tier_players in tier_groups:
            st.markdown(f"#### {tier_name}")
            tier_table = tier_players[display_source_cols].rename(
                columns=draft_display_map
            )
            st.dataframe(
                tier_table, width="stretch", hide_index=True,
                column_config=board_config,
            )
    else:
        st.dataframe(
            draft_table,
            width="stretch",
            hide_index=True,
            height=620,
            column_config=board_config,
        )

    st.download_button(
        "Download filtered draft board",
        data=draft_table.to_csv(index=False).encode("utf-8-sig"),
        file_name="fantrax_draft_board_2627_filtered.csv",
        mime="text/csv",
        key="download_draft_board_2627",
    )

    # -------------------------------------------------------------------------
    # Draft tiers and team context
    # -------------------------------------------------------------------------
    left_panel, right_panel = st.columns(2, gap="large")

    with left_panel:
        st.markdown("#### Draft Tiers")
        if "tier" not in filtered_draft.columns or filtered_draft.empty:
            st.info("No tier data is available.")
        else:
            tier_summary = (
                filtered_draft.groupby("tier", as_index=False, dropna=False)
                .agg(
                    Players=("Player", "count"),
                    Average_Rank=("Rank", "mean"),
                    Average_Draft_Score=("Draft Score", "mean"),
                    Average_Minutes=("Minutes %", "mean"),
                    Average_Confidence=("Data Confidence", "mean"),
                )
            )
            tier_summary = tier_summary.rename(columns={
                "tier": "Tier",
                "Average_Rank": "Avg Rank",
                "Average_Draft_Score": "Avg Draft Score",
                "Average_Minutes": "Avg Minutes %",
                "Average_Confidence": "Avg Confidence",
            })
            for col in ["Avg Rank", "Avg Draft Score", "Avg Minutes %", "Avg Confidence"]:
                tier_summary[col] = pd.to_numeric(tier_summary[col], errors="coerce").round(1)
            st.dataframe(tier_summary, width="stretch", hide_index=True)

    with right_panel:
        st.markdown("#### Team Draft Context")
        team_context_cols = [
            c for c in [
                "team_attack_rating", "team_defense_rating",
                "team_strength_rating", "fixture_ease_next_5",
                "fixture_ease_next_10",
            ] if c in draft_df.columns
        ]
        if not team_context_cols:
            st.info("No team-context columns are available.")
        else:
            team_context = (
                draft_df.groupby("Team", as_index=False)[team_context_cols]
                .mean()
                .rename(columns={
                    "team_attack_rating": "Attack",
                    "team_defense_rating": "Defense",
                    "team_strength_rating": "Overall",
                    "fixture_ease_next_5": "Fixtures N5",
                    "fixture_ease_next_10": "Fixtures N10",
                })
            )
            context_sort = "Overall" if "Overall" in team_context.columns else team_context.columns[1]
            team_context = team_context.sort_values(context_sort, ascending=False)
            for col in team_context.columns[1:]:
                team_context[col] = pd.to_numeric(team_context[col], errors="coerce").round(1)
            st.dataframe(team_context, width="stretch", hide_index=True, height=410)

    # -------------------------------------------------------------------------
    # Player detail
    # -------------------------------------------------------------------------
    st.markdown("#### Player Detail")

    detail_options = filtered_draft["Player"].dropna().astype(str).tolist()
    if not detail_options:
        st.info("No players match the current filters.")
    else:
        selected_draft_player = st.selectbox(
            "Select player",
            detail_options,
            key="draft_player_detail",
        )
        player_row = filtered_draft[
            filtered_draft["Player"].eq(selected_draft_player)
        ].iloc[0]

        if st.button("Add to Player Comparison", key="draft_add_player_compare"):
            added, message = add_compare(st.session_state, stable_player_id(player_row))
            (st.success if added else st.info)(message)

        detail_metrics = st.columns(6)
        render_context_stat(detail_metrics[0], "Overall Rank", player_row.get("Rank"), player_row.get("tier", ""))
        render_context_stat(detail_metrics[1], "Draft Score", player_row.get("Draft Score"), player_row.get("adp_status", ""))
        render_context_stat(detail_metrics[2], "Minutes Outlook", player_row.get("minutes_outlook", "—"), f"{format_value(player_row.get('Minutes %'))}% projected share")
        render_context_stat(detail_metrics[3], "Points / Appearance", player_row.get("fantasy_per_appearance_2526"), f"{format_value(player_row.get('fantasy_per90_2526'))} points / 90")
        render_context_stat(detail_metrics[4], "Ghost / Appearance", player_row.get("ghost_per_appearance_2526"), f"{format_value(player_row.get('ghost_per90_2526'))} ghost / 90")
        render_context_stat(detail_metrics[5], "xG+xA / 90", player_row.get("xgi90_2526"), "Understat attacking involvement")

        profile_left, profile_right = st.columns(2, gap="large")
        with profile_left:
            st.markdown("##### Player and Minutes Profile")
            profile_rows = {
                "Player": player_row.get("Player"),
                "Team": player_row.get("Team"),
                "Position": player_row.get("Position"),
                "Fantrax eligibility": player_row.get("Fantrax Positions"),
                "Minutes outlook": player_row.get("minutes_outlook"),
                "Projected minutes share": player_row.get("Minutes %"),
                "Minutes confidence": player_row.get("Minutes Confidence"),
                "2025/26 minutes": player_row.get("minutes_2526"),
                "2025/26 appearances": player_row.get("appearances_2526"),
                "2025/26 starts": player_row.get("starts_2526"),
                "2025/26 90s": player_row.get("nineties_2526"),
                "Historical fantasy total": player_row.get("fantasy_points_2526"),
                "Points / appearance": player_row.get("fantasy_per_appearance_2526"),
                "Points / start": player_row.get("fantasy_per_start_2526"),
                "Points / 90": player_row.get("fantasy_per90_2526"),
                "Ghost / appearance": player_row.get("ghost_per_appearance_2526"),
                "Ghost / start": player_row.get("ghost_per_start_2526"),
                "Ghost / 90": player_row.get("ghost_per90_2526"),
                "Recent six-GW minutes": player_row.get("recent_minutes_6"),
                "Team changed": player_row.get("team_changed"),
            }
            st.dataframe(
                pd.DataFrame(
                    {"Metric": list(profile_rows.keys()), "Value": list(profile_rows.values())}
                ),
                width="stretch",
                hide_index=True,
            )

        with profile_right:
            st.markdown("##### Team and Draft Context")
            context_rows = {
                "ADP": player_row.get("ADP"),
                "Projected points": player_row.get("fantrax_projected_points"),
                "Value vs ADP": player_row.get("Value vs ADP"),
                "Team attack rating": player_row.get("team_attack_rating"),
                "Team defense rating": player_row.get("team_defense_rating"),
                "Overall team rating": player_row.get("team_strength_rating"),
                "Fixture ease next 3": player_row.get("fixture_ease_next_3"),
                "Fixture ease next 5": player_row.get("fixture_ease_next_5"),
                "Fixture ease next 10": player_row.get("fixture_ease_next_10"),
                "Data confidence": player_row.get("Data Confidence"),
            }
            st.dataframe(
                pd.DataFrame(
                    {"Metric": list(context_rows.keys()), "Value": list(context_rows.values())}
                ),
                width="stretch",
                hide_index=True,
            )

        with st.expander("Draft Score explanation", expanded=True):
            explanation = draft_score_explanation(player_row)
            explanation["Normalized value"] = pd.to_numeric(
                explanation["Normalized value"], errors="coerce"
            ).round(1)
            explanation["Weight"] = explanation["Weight"].map(
                lambda value: f"{value:.0%}"
            )
            explanation["Weighted contribution"] = pd.to_numeric(
                explanation["Weighted contribution"], errors="coerce"
            ).round(2)
            st.markdown(f"**Official Draft Score: {format_value(player_row.get('Draft Score'))}**")
            st.dataframe(explanation, width="stretch", hide_index=True)
            if explanation_reconciles(player_row):
                st.caption("Component contributions reconcile with the official Draft Score.")
            else:
                st.warning(
                    "A complete component reconciliation is unavailable for this row. "
                    "The official Draft Score is shown unchanged."
                )
            interpretations = []
            if pd.to_numeric(pd.Series([player_row.get("production_score")]), errors="coerce").iloc[0] >= 75:
                interpretations.append("Strong historical production")
            if pd.to_numeric(pd.Series([player_row.get("ghost_score")]), errors="coerce").iloc[0] >= 75:
                interpretations.append("Excellent ghost floor")
            if pd.to_numeric(pd.Series([player_row.get("minutes_score")]), errors="coerce").iloc[0] >= 75:
                interpretations.append("High projected minutes")
            if pd.to_numeric(pd.Series([player_row.get("minutes_score")]), errors="coerce").iloc[0] < 40:
                interpretations.append("Limited projected playing time")
            if pd.to_numeric(pd.Series([player_row.get("Value vs ADP")]), errors="coerce").iloc[0] >= 8:
                interpretations.append("Strong value versus ADP")
            if interpretations:
                st.caption(" · ".join(interpretations))

        st.markdown("#### Compare Players")
        comparison_players = st.multiselect(
            "Select exactly two players",
            detail_options,
            default=detail_options[:2],
            max_selections=2,
            key="draft_comparison_players",
        )
        comparison = comparison_table(filtered_draft, comparison_players)
        if comparison.empty:
            st.info("Select two players to compare.")
        else:
            st.dataframe(comparison, width="stretch", hide_index=True)

        # Queue state is deliberately session-only and never written to disk.
        if hasattr(st, "session_state") and hasattr(st, "button"):
            if "draft_queue" not in st.session_state:
                st.session_state["draft_queue"] = []
            queue_actions = st.columns(2)
            with queue_actions[0]:
                if st.button("Add selected player to queue", key="draft_queue_add"):
                    st.session_state["draft_queue"] = update_queue(
                        st.session_state["draft_queue"], selected_draft_player, "add"
                    )
            with queue_actions[1]:
                if st.button("Remove selected player from queue", key="draft_queue_remove"):
                    st.session_state["draft_queue"] = update_queue(
                        st.session_state["draft_queue"], selected_draft_player, "remove"
                    )
            status_actions = st.columns(3)
            player_key = stable_player_key(player_row)
            for status_column, (label, status) in zip(
                status_actions,
                (
                    ("Drafted by Me", DRAFTED_BY_ME),
                    ("Drafted by Other", DRAFTED_BY_OTHER),
                    ("Return to Available", AVAILABLE),
                ),
            ):
                with status_column:
                    if st.button(label, key=f"draft_status_{status}"):
                        st.session_state["draft_player_statuses"] = set_draft_status(
                            st.session_state["draft_player_statuses"],
                            player_key,
                            status,
                        )
                        if status != AVAILABLE:
                            st.session_state["draft_queue"] = update_queue(
                                st.session_state.get("draft_queue", []),
                                selected_draft_player,
                                "remove",
                            )
                            sequence = st.session_state.get("draft_sequence", [])
                            if player_key not in sequence:
                                sequence.append(player_key)
                            st.session_state["draft_sequence"] = sequence
                        st.rerun()

    st.markdown("#### Draft Queue")
    if hasattr(st, "session_state"):
        queue = st.session_state.get("draft_queue", [])
        if queue:
            if hasattr(st, "button"):
                queue_controls = st.columns([2, 1, 1])
                with queue_controls[0]:
                    queued_player = st.selectbox(
                        "Reorder queued player", queue, key="draft_queue_reorder_player"
                    )
                with queue_controls[1]:
                    if st.button("Move up", key="draft_queue_up"):
                        st.session_state["draft_queue"] = update_queue(
                            queue, queued_player, "up"
                        )
                        queue = st.session_state["draft_queue"]
                with queue_controls[2]:
                    if st.button("Move down", key="draft_queue_down"):
                        st.session_state["draft_queue"] = update_queue(
                            queue, queued_player, "down"
                        )
                        queue = st.session_state["draft_queue"]
            queue_frame = draft_df[draft_df["Player"].isin(queue)].copy()
            queue_frame["_queue_order"] = queue_frame["Player"].map(
                {player: index + 1 for index, player in enumerate(queue)}
            )
            queue_frame = queue_frame.sort_values("_queue_order")
            st.dataframe(
                queue_frame[["_queue_order", "Player", "Fantrax Positions", "Team", "tier", "Rank", "ADP", "Draft Score", "Draft Status"]]
                .rename(columns={"_queue_order": "Queue"}),
                width="stretch", hide_index=True,
            )
        else:
            st.caption("Your session queue is empty.")

    st.markdown("#### Drafted Teams")
    drafted_tabs = (
        st.tabs(["My Team", "Drafted by Other"])
        if hasattr(st, "tabs") else st.columns(2)
    )
    for drafted_tab, status in zip(
        drafted_tabs, (DRAFTED_BY_ME, DRAFTED_BY_OTHER)
    ):
        with drafted_tab:
            drafted = draft_df[draft_df["Draft Status"].eq(status)].copy()
            if drafted.empty:
                st.caption(f"No players are marked {status.lower()}.")
            else:
                sequence_order = {
                    key: index + 1
                    for index, key in enumerate(
                        session_state.get("draft_sequence", [])
                    )
                }
                drafted["Draft Sequence"] = [
                    sequence_order.get(stable_player_key(row), pd.NA)
                    for _, row in drafted.iterrows()
                ]
                drafted = drafted.sort_values(
                    ["Draft Sequence", "Rank"], na_position="last"
                )
                drafted_columns = [
                    "Draft Sequence", "Player", "Fantrax Positions", "Team",
                    "tier", "Rank", "Draft Score", "ADP",
                    "fantasy_per_appearance_2526", "ghost_per_appearance_2526",
                ]
                st.dataframe(
                    drafted[[c for c in drafted_columns if c in drafted]],
                    width="stretch",
                    hide_index=True,
                )


# Sprint 4.2 replaces the accumulated linear layout with the focused four-tab
# workspace while preserving this module as the stable navigation entry point.
from views.draft_workspace import DATASET_KEYS, render  # noqa: E402,F401
