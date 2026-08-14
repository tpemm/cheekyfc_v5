"""Sprint 4.2 live-draft workspace."""

from __future__ import annotations

import html
import re
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from analytics.draft.presentation import (
    AVAILABLE,
    DRAFTED_BY_ME,
    DRAFTED_BY_OTHER,
    add_draft_percentiles,
    add_advanced_context_metrics,
    add_explicit_rate_metrics,
    add_historical_playing_time,
    apply_board_action,
    apply_draft_statuses,
    build_tier_board,
    comparison_winner_data,
    draft_score_explanation,
    draft_profile_percentiles,
    explanation_reconciles,
    format_detail_value,
    model_visualization_data,
    normalize_fantrax_positions,
    position_matches,
    percentile_context,
    player_analysis_tags,
    player_strengths_and_risks,
    reset_draft_session,
    set_draft_status,
    sort_draft_board,
    stable_player_key,
    update_queue,
)
from analytics.draft.team import (
    STRATEGY_WEIGHTS,
    best_available_fits,
    draft_strategy_priorities,
    draft_turn_context,
    positional_coverage,
    position_scarcity,
    team_floor,
    team_strengths_and_risks,
    team_summary,
)
from analytics.draft.reliability import normalize_player_id
from analytics.draft.grading import best_legal_xi, position_analysis
from analytics.draft.share import build_share_summary, share_csv, share_html
from analytics.draft.poster import poster_output_bytes
from core.models.data_result import DataStatus
from core.services.data_manager import (
    DataManager,
    DatasetNotFoundError,
    DatasetValidationError,
    UnsupportedFormatError,
)
from core.services.season_manager import SeasonManager


DATASET_KEYS = (
    "draft_rankings", "draft_eligibility_overrides",
    "current_fantrax_player_pool",
)
POST_DRAFT_DATASET_KEYS = (
    "draft_manager_grades", "draft_pick_grades", "draft_category_scores",
    "draft_awards",
)


@st.cache_data(show_spinner=False)
def _poster_downloads(managers: pd.DataFrame, picks: pd.DataFrame) -> tuple[bytes, bytes]:
    return poster_output_bytes(managers, picks)


def _load(
    data: DataManager, key: str, season_id: str, namespace: str, ui: Any
) -> pd.DataFrame:
    try:
        result = data.load_frame(key, season_id, namespace)
    except (DatasetNotFoundError, KeyError):
        return pd.DataFrame()
    except (DatasetValidationError, UnsupportedFormatError) as exc:
        ui.warning(str(exc))
        return pd.DataFrame()
    if result.status in {DataStatus.MISSING, DataStatus.EMPTY}:
        return pd.DataFrame()
    if result.status is DataStatus.INVALID:
        ui.warning("; ".join((*result.validation_errors, *result.warnings)))
        return pd.DataFrame()
    return result.data.copy()


def _bool(values: pd.Series, default: bool = False) -> pd.Series:
    true_values = {"true", "1", "yes", "y", "t"}
    return values.map(
        lambda value: default if pd.isna(value)
        else bool(value) if isinstance(value, (bool, np.bool_))
        else str(value).strip().casefold() in true_values
    ).astype(bool)


@st.cache_data(show_spinner=False)
def _prepare_draft_base(frame: pd.DataFrame) -> pd.DataFrame:
    """Cache source-dependent presentation analytics, never session statuses."""
    out = frame.copy()
    numeric = (
        "overall_rank", "draft_score", "fantrax_adp", "value_vs_adp",
        "projected_minutes_share", "minutes_confidence", "data_confidence",
        "fantrax_projected_points", "fantasy_points_2526",
        "ghost_points_2526", "minutes_2526", "starts_2526",
        "weeks_available", "understat_xg_2526", "understat_xa_2526",
        "understat_minutes_2526", "xgi90_2526", "team_attack_rating",
        "team_defense_rating", "team_strength_rating",
        "fixture_ease_next_3", "fixture_ease_next_5",
        "fixture_ease_next_10", "production_score", "ghost_score",
        "attacking_score", "minutes_score", "team_context_score",
        "fixture_score",
        "start_rate_2526", "recent_start_rate_6",
        "projected_minutes_share", "minutes_confidence",
    )
    for column in numeric:
        if column in out:
            out[column] = pd.to_numeric(out[column], errors="coerce")

    name = next(
        (c for c in ("player_name", "fantrax_player_name", "historical_name") if c in out),
        None,
    )
    team = next((c for c in ("team_2627", "team", "club") if c in out), None)
    canonical = next(
        (c for c in ("current_position", "position", "position_2627") if c in out),
        None,
    )
    eligibility = next(
        (
            c for c in (
                "fantrax_position_eligibility", "fantrax_position",
                "position_2627",
            ) if c in out
        ),
        None,
    )
    out["Player"] = out[name].fillna("Unknown player").astype(str) if name else ""
    out["Team"] = out[team].fillna("UNK").astype(str) if team else "UNK"
    out["Canonical Position"] = (
        out[canonical].fillna("").astype(str) if canonical else ""
    )
    out["Position"] = (
        out[eligibility].map(normalize_fantrax_positions) if eligibility else ""
    )
    out["Identity"] = out["Team"] + " · " + out["Position"]
    out["Rank"] = pd.to_numeric(out.get("overall_rank"), errors="coerce").astype("Int64")
    out["Draft Score"] = pd.to_numeric(out.get("draft_score"), errors="coerce")
    out["ADP"] = pd.to_numeric(out.get("fantrax_adp"), errors="coerce")
    out["Value vs ADP"] = pd.to_numeric(out.get("value_vs_adp"), errors="coerce")
    out["Draft Eligible"] = (
        _bool(out["is_draft_eligible"]) if "is_draft_eligible" in out
        else ~out["Team"].str.upper().isin(["", "FA", "UNK", "NA", "N/A"])
    )
    out = add_explicit_rate_metrics(out)
    out = add_advanced_context_metrics(out)
    out = add_historical_playing_time(out)
    out = add_draft_percentiles(out)
    out["_Player Key"] = [stable_player_key(row) for _, row in out.iterrows()]
    return out


def prepare_draft_frame(frame: pd.DataFrame, statuses: dict[str, str]) -> pd.DataFrame:
    return apply_draft_statuses(_prepare_draft_base(frame), statuses)


def _column_config(ui: Any) -> dict[str, Any]:
    return {
        "Rank": ui.column_config.NumberColumn(
            "Rank", format="%d", width=55, pinned=True
        ),
        "Player": ui.column_config.TextColumn(
            "Player", width=145, pinned=True,
        ),
        "Club · Pos": ui.column_config.TextColumn("Club · Pos", width=78),
        "Tier": ui.column_config.TextColumn("Tier", width=58),
        "Position": ui.column_config.TextColumn("Position", width=65),
        "Team": ui.column_config.TextColumn("Club", width=58),
        "Draft Score": ui.column_config.NumberColumn("Draft Score", format="%.1f"),
        "ADP": ui.column_config.NumberColumn("ADP", format="%.1f"),
        "Projected Points": ui.column_config.NumberColumn(
            "Projected Points", format="%.1f"
        ),
        "Points / 90": ui.column_config.NumberColumn("Points / 90", format="%.1f"),
        "Ghost / 90": ui.column_config.NumberColumn("Ghost / 90", format="%.1f"),
        "Draft Score": ui.column_config.ProgressColumn("Draft Score", min_value=0, max_value=100, format="%.1f", width=78),
        "ADP": ui.column_config.NumberColumn("ADP", format="%.1f", width=55),
        "Projected Points": ui.column_config.NumberColumn("Proj Pts", help="Fantrax projected points.", format="%.1f", width=70),
        "Start % 25/26": ui.column_config.NumberColumn("Start %", help="Historical starts divided by available 2025/26 gameweeks.", format="%.1f", width=66),
        "Minutes % 25/26": ui.column_config.NumberColumn("Min %", help="Historical minutes divided by 38 × 90.", format="%.1f", width=62),
        "Minutes Outlook": ui.column_config.TextColumn("Outlook 26/27", width=104),
        "Points": ui.column_config.NumberColumn("Points", format="%.1f", width=60),
        "Ghost": ui.column_config.NumberColumn("Ghost", format="%.1f", width=58),
        "xGI": ui.column_config.NumberColumn("xGI", format="%.1f", width=50),
        "Value vs ADP": ui.column_config.NumberColumn("Value vs ADP", format="%+.1f"),
        "Team Strength %": ui.column_config.ProgressColumn("Team Strength %", help="Percentile among unique clubs; higher is stronger.", min_value=0, max_value=100, format="%.0f", width=82),
        "Next 5 Fixture Ease %": ui.column_config.ProgressColumn("Next 5 Fixture Ease %", help="Next-five fixture-ease percentile; higher is easier.", min_value=0, max_value=100, format="%.0f", width=90),
        "Mine": ui.column_config.CheckboxColumn(
            "Mine", help="Drafted by Me", width=68, pinned=True
        ),
        "Other": ui.column_config.CheckboxColumn(
            "Other", help="Drafted by another manager", width=72, pinned=True
        ),
    }


BOARD_GROUPS: dict[str, tuple[tuple[str, str], ...]] = {
    "Core": (
        ("Rank", "Rank"), ("Player", "Player"), ("Identity", "Club · Pos"),
        ("tier", "Tier"), ("Draft Score", "Draft Score"),
        ("ADP", "ADP"),
        ("fantrax_projected_points", "Projected Points"),
        ("historical_start_pct_2526", "Start % 25/26"),
        ("historical_minutes_pct_2526", "Minutes % 25/26"),
        ("minutes_outlook", "Minutes Outlook"),
        ("fantasy_points_2526", "Points"),
        ("ghost_points_2526", "Ghost"),
        ("xgi_2526", "xGI"),
        ("team_strength_percentile", "Team Strength %"),
        ("fixture_ease_percentile", "Next 5 Fixture Ease %"),
    ),
    "Production": (
        ("fantasy_points_2526", "Total Fantasy Points"),
        ("fantasy_per_appearance_2526", "Points / Appearance"),
        ("fantasy_per_start_2526", "Points / Start"),
        ("fantasy_per90_2526", "Points / 90"),
    ),
    "Ghost": (
        ("ghost_points_2526", "Ghost Points"),
        ("ghost_per_appearance_2526", "Ghost / Appearance"),
        ("ghost_per_start_2526", "Ghost / Start"),
        ("ghost_per90_2526", "Ghost / 90"),
    ),
    "Attacking": (
        ("xg_2526", "xG"), ("xg90_2526", "xG / 90"),
        ("xa_2526", "xA"), ("xa90_2526", "xA / 90"),
        ("xgi_2526", "xGI"), ("xgi90_2526", "xGI / 90"),
        ("attacking_score", "Attacking Score"),
    ),
    "Playing Time": (
        ("projected_minutes_share", "Projected Minutes %"),
        ("minutes_outlook", "Minutes Outlook"),
        ("minutes_confidence", "Minutes Confidence"),
        ("minutes_2526", "Historical Minutes"), ("starts_2526", "Starts"),
        ("appearances_2526", "Appearances"), ("nineties_2526", "90s"),
        ("start_rate_2526", "Historical Start Rate"),
    ),
    "Context": (
        ("team_strength_percentile", "Team Strength Percentile"),
        ("team_context_score", "Team Context Score"),
        ("fixture_ease_percentile", "Fixture Ease Percentile"),
        ("fixture_score", "Fixture Score"),
    ),
    "Draft Model": (
        ("production_score", "Production Score"),
        ("minutes_score", "Minutes Score"), ("ghost_score", "Ghost Score"),
        ("attacking_score", "Attacking Score"),
        ("team_context_score", "Team Context Score"),
        ("fixture_score", "Fixture Score"),
    ),
}


POINT_DISPLAY_FIELDS = {
    "Total": (("fantasy_points_2526", "Points"), ("ghost_points_2526", "Ghost"), ("xgi_2526", "xGI")),
    "Per Game": (("fantasy_per_appearance_2526", "Points / App"), ("ghost_per_appearance_2526", "Ghost / App"), ("xgi_per_appearance_2526", "xGI / App")),
    "Per Start": (("fantasy_per_start_2526", "Points / Start"), ("ghost_per_start_2526", "Ghost / Start"), ("xgi_per_start_2526", "xGI / Start")),
    "Per 90": (("fantasy_per90_2526", "Points / 90"), ("ghost_per90_2526", "Ghost / 90"), ("xgi90_2526", "xGI / 90")),
}


def _board_table(
    frame: pd.DataFrame, groups: list[str] | None = None, point_mode: str = "Total"
) -> pd.DataFrame:
    selected = groups or ["Core"]
    fields: list[tuple[str, str]] = []
    for group in selected:
        group_fields = list(BOARD_GROUPS.get(group, ()))
        if group == "Core":
            rate_sources = {source for mode in POINT_DISPLAY_FIELDS.values() for source, _ in mode}
            insert_at = next((i for i, (source, _) in enumerate(group_fields) if source in rate_sources), len(group_fields))
            group_fields = [(source, label) for source, label in group_fields if source not in rate_sources]
            for offset, field in enumerate(POINT_DISPLAY_FIELDS[point_mode]):
                group_fields.insert(insert_at + offset, field)
        fields.extend(group_fields)
    deduplicated = list(dict.fromkeys(fields))
    output = frame[[source for source, _ in deduplicated if source in frame]].rename(
        columns=dict(deduplicated)
    )
    if "ADP" in output:
        output["ADP"] = pd.to_numeric(output["ADP"], errors="coerce").fillna(999.0)
    position = 3 if "Club · Pos" in output else (2 if "Player" in output else len(output.columns))
    output.insert(position, "Mine", frame["Draft Status"].eq(DRAFTED_BY_ME).to_numpy())
    output.insert(
        position + 1, "Other",
        frame["Draft Status"].eq(DRAFTED_BY_OTHER).to_numpy(),
    )
    return output


def _selected_row(
    frame: pd.DataFrame, selected_key: str | None
) -> pd.Series | None:
    if not selected_key:
        return None
    match = frame[frame["_Player Key"].eq(selected_key)]
    return None if match.empty else match.iloc[0]


def _set_status(ui: Any, row: pd.Series, status: str) -> None:
    key = stable_player_key(row)
    ui.session_state["draft_player_statuses"] = set_draft_status(
        ui.session_state["draft_player_statuses"], key, status
    )
    if status != AVAILABLE:
        ui.session_state["draft_queue"] = update_queue(
            ui.session_state["draft_queue"], key, "remove"
        )
        sequence = ui.session_state["draft_sequence"]
        if key not in sequence:
            sequence.append(key)
    ui.session_state["draft_action_notice"] = f"{row.get('Player', 'Player')}: {status}"
    ui.rerun()


def _open_compare(ui: Any, row: pd.Series) -> None:
    ui.session_state["draft_compare_pending_player"] = str(row["Player"])
    ui.session_state["draft_compare_clear_player_2"] = True
    ui.session_state["draft_workspace_pending_tab"] = "Compare Players"
    ui.session_state["draft_detail_dialog_open"] = False
    ui.session_state.pop("draft_detail_player_key", None)
    ui.rerun()


def _status_actions(ui: Any, row: pd.Series, prefix: str) -> None:
    columns = ui.columns(5)
    if columns[0].button("Add to Queue", key=f"{prefix}_queue"):
        key = stable_player_key(row)
        ui.session_state["draft_queue"] = update_queue(
            ui.session_state["draft_queue"], key, "add"
        )
        ui.rerun()
    if columns[1].button("Compare", key=f"{prefix}_compare"):
        _open_compare(ui, row)
    for column, (label, status) in zip(
        columns[2:],
        (
            ("Drafted by Me", DRAFTED_BY_ME),
            ("Drafted by Other", DRAFTED_BY_OTHER),
            ("Return to Available", AVAILABLE),
        ),
    ):
        if column.button(label, key=f"{prefix}_{status}"):
            _set_status(ui, row, status)


def _apply_editor_action(
    editor_key: str, player_keys: list[str], player_names: list[str]
) -> None:
    event = st.session_state.get(editor_key, {})
    for raw_index, changes in event.get("edited_rows", {}).items():
        index = int(raw_index)
        if index < 0 or index >= len(player_keys):
            continue
        status = (
            DRAFTED_BY_ME if changes.get("Mine")
            else DRAFTED_BY_OTHER if changes.get("Other")
            else None
        )
        if status is None:
            continue
        statuses, queue, sequence = apply_board_action(
            st.session_state["draft_player_statuses"],
            st.session_state["draft_queue"],
            st.session_state["draft_sequence"],
            player_keys[index],
            status,
        )
        st.session_state["draft_player_statuses"] = statuses
        st.session_state["draft_queue"] = queue
        st.session_state["draft_sequence"] = sequence
        st.session_state["draft_action_notice"] = f"{player_names[index]}: {status}"
        break


def _apply_player_button(click_key: str, player_keys: list[str]) -> None:
    """Resolve a ButtonColumn click against this exact sorted board view."""
    click = st.session_state.get(click_key)
    if not click:
        return
    index = int(click["row"])
    if 0 <= index < len(player_keys):
        st.session_state["draft_detail_player_key"] = player_keys[index]
        st.session_state["draft_detail_dialog_open"] = True


def _render_action_board(
    ui: Any,
    source: pd.DataFrame,
    display: pd.DataFrame,
    *,
    editor_key: str,
    height: int,
) -> Any:
    config = _column_config(ui)
    if ui is not st or not hasattr(ui, "data_editor"):
        fallback = display.copy()
        if "Player" in fallback:
            fallback["Player"] = source["Player"].to_numpy()
        return ui.dataframe(
            fallback, hide_index=True, height=height, width="stretch",
            column_config=config, key=editor_key,
        )
    player_keys = source["_Player Key"].tolist()
    player_names = source["Player"].tolist()
    click_key = f"{editor_key}_player_click"
    config["Player"] = st.column_config.ButtonColumn(
        "Player", width=145, pinned=True, alignment="left", type="tertiary",
        help="Open player profile", key=click_key,
        on_click=_apply_player_button, args=(click_key, player_keys),
    )
    disabled = [
        column
        for column in display.columns
        if column not in {"Mine", "Other", "Player"}
    ]
    return ui.data_editor(
        display,
        hide_index=True,
        height=height,
        width="stretch",
        column_config=config,
        disabled=disabled,
        key=editor_key,
        on_change=_apply_editor_action,
        args=(editor_key, player_keys, player_names),
    )


def _metric_section(
    ui: Any,
    title: str,
    row: pd.Series,
    metrics: tuple[tuple[str, str, bool], ...],
    *,
    context: dict[str, str] | None = None,
) -> None:
    ui.markdown(f"#### {title}")
    columns = ui.columns(min(4, len(metrics)))
    for index, (label, field, integer) in enumerate(metrics):
        column = columns[index % len(columns)]
        column.metric(label, format_detail_value(row.get(field), integer=integer))
        if context and field in context:
            positional, league = percentile_context(row, context[field])
            if positional:
                column.caption(positional)
            if league:
                column.caption(league)


def _detail(ui: Any, row: pd.Series, prefix: str) -> None:
    player = html.escape(str(row["Player"]))
    team = html.escape(str(row.get("Team", "—")))
    position = html.escape(str(row.get("Position", "—")))
    tier = html.escape(str(row.get("tier", "—")))
    status = html.escape(str(row.get("Draft Status", AVAILABLE)))
    ui.markdown(
        f'<div style="padding:0.25rem 0 1rem">'
        f'<div style="font-size:2rem;font-weight:750;line-height:1.1">{player}</div>'
        f'<div style="margin-top:.55rem;display:flex;gap:.45rem;flex-wrap:wrap">'
        f'<span style="padding:.2rem .55rem;border-radius:999px;background:#edf2f7">{team}</span>'
        f'<span style="padding:.2rem .55rem;border-radius:999px;background:#edf2f7">{position}</span>'
        f'<span style="padding:.2rem .55rem;border-radius:999px;background:#fff3cd">{tier}</span>'
        f'<span style="padding:.2rem .55rem;border-radius:999px;background:#e7f5ec">{status}</span>'
        f'</div></div>',
        unsafe_allow_html=True,
    )
    _status_actions(ui, row, f"{prefix}_header")
    ui.markdown("#### Draft Profile Percentiles")
    ui.dataframe(
        draft_profile_percentiles(row), hide_index=True, width="stretch",
        column_config={
            "Overall %ile": ui.column_config.ProgressColumn("Overall %ile", min_value=0, max_value=100, format="%.0f"),
            "Position %ile": ui.column_config.ProgressColumn("Position %ile", min_value=0, max_value=100, format="%.0f"),
        },
    )
    _metric_section(
        ui, "Primary Decision Strip", row,
        (
            ("Draft Score", "Draft Score", False),
            ("ADP", "ADP", False),
            ("Projected Points", "fantrax_projected_points", False),
            ("Start % 25/26", "historical_start_pct_2526", False),
            ("Minutes % 25/26", "historical_minutes_pct_2526", False),
            ("Minutes Outlook", "minutes_outlook", False),
            ("Team Strength %", "team_strength_percentile", False),
            ("Fixture Ease %", "fixture_ease_percentile", False),
        ),
    )
    _metric_section(
        ui, "Production", row,
        (
            ("Fantasy Points", "fantasy_points_2526", False),
            ("Points/App", "fantasy_per_appearance_2526", False),
            ("Points/Start", "fantasy_per_start_2526", False),
            ("Points/90", "fantasy_per90_2526", False),
        ),
        context={"fantasy_per90_2526": "points_per90"},
    )
    _metric_section(
        ui, "Ghost", row,
        (
            ("Ghost Points", "ghost_points_2526", False),
            ("Ghost/App", "ghost_per_appearance_2526", False),
            ("Ghost/Start", "ghost_per_start_2526", False),
            ("Ghost/90", "ghost_per90_2526", False),
        ),
        context={"ghost_per90_2526": "ghost_per90"},
    )
    _metric_section(
        ui, "Attacking and Context", row,
        (
            ("xG", "xg_2526", False), ("xG / 90", "xg90_2526", False),
            ("xA", "xa_2526", False), ("xA / 90", "xa90_2526", False),
            ("xGI", "xgi_2526", False), ("xGI / 90", "xgi90_2526", False),
            ("Team Strength %ile", "team_strength_percentile", False),
            ("Fixture Ease %ile", "fixture_ease_percentile", False),
        ),
        context={"xgi90_2526": "xgi_per90"},
    )
    _metric_section(
        ui, "Playing Time", row,
        (
            ("Minutes", "minutes_2526", True),
            ("Starts", "starts_2526", True),
            ("Appearances", "appearances_2526", True),
            ("90s", "nineties_2526", False),
            ("Projected Minutes %", "projected_minutes_share", False),
            ("Minutes Confidence", "minutes_confidence", False),
            ("Historical Start Rate", "start_rate_2526", False),
        ),
    )
    strengths, risks = player_strengths_and_risks(row)
    summary_columns = ui.columns(2)
    summary_columns[0].markdown("#### Strengths")
    summary_columns[0].markdown(
        "\n".join(f"✓ {item}" for item in strengths)
        or "No standout threshold met."
    )
    summary_columns[1].markdown("#### Risks")
    summary_columns[1].markdown(
        "\n".join(f"⚠ {item}" for item in risks)
        or "No material threshold flagged."
    )
    ui.markdown("#### Model")
    ui.dataframe(
        model_visualization_data(row),
        hide_index=True,
        width="stretch",
        column_config={
            "Score": ui.column_config.ProgressColumn(
                "Score", min_value=0, max_value=100, format="%.1f"
            )
        },
    )
    with ui.expander("Draft Score explanation", expanded=False):
        explanation = draft_score_explanation(row)
        explanation["Normalized value"] = pd.to_numeric(
            explanation["Normalized value"], errors="coerce"
        ).round(1)
        explanation["Weighted contribution"] = pd.to_numeric(
            explanation["Weighted contribution"], errors="coerce"
        ).round(1)
        explanation["Weight"] = pd.to_numeric(
            explanation["Weight"], errors="coerce"
        ).mul(100).round()
        ui.dataframe(
            explanation,
            hide_index=True,
            width="stretch",
            column_config={
                "Normalized value": ui.column_config.NumberColumn(
                    "Normalized value", format="%.1f"
                ),
                "Weight": ui.column_config.NumberColumn(
                    "Weight", format="%.0f%%"
                ),
                "Weighted contribution": ui.column_config.NumberColumn(
                    "Weighted contribution", format="%.1f"
                ),
            },
        )
        if explanation_reconciles(row):
            ui.caption("Components reconcile with the official Draft Score.")
        else:
            ui.warning("Complete retained components are unavailable.")


def _dismiss_player_dialog() -> None:
    st.session_state["draft_detail_dialog_open"] = False
    st.session_state.pop("draft_detail_player_key", None)


@st.dialog(
    "Draft HQ Player Profile",
    width="large",
    on_dismiss=_dismiss_player_dialog,
)
def _player_dialog(row: pd.Series) -> None:
    _detail(st, row, "dialog")


def _render_filters(ui: Any, frame: pd.DataFrame) -> dict[str, Any]:
    with ui.expander("Filters", expanded=False):
        row = ui.columns(5)
        search = row[0].text_input("Search player", key="draft_player_search")
        positions = sorted({
            token for value in frame["Position"]
            for token in str(value).split("/") if token
        })
        selected_positions = row[1].multiselect(
            "Positions", positions, default=positions, key="draft_positions"
        )
        teams = sorted(frame["Team"].dropna().astype(str).unique())
        selected_teams = row[2].multiselect(
            "Clubs", teams, default=teams, key="draft_teams"
        )
        sort_by = row[3].selectbox(
            "Sort board by",
            ["Model Rank", "ADP", "Draft Score", "Projected Points"],
            key="draft_sort_by",
        )
        direction = row[4].selectbox(
            "Direction", ["Ascending", "Descending"],
            key="draft_sort_direction",
        )
        toggles = ui.columns(3)
        include_mine = toggles[0].checkbox(
            "Include Drafted by Me", key="draft_include_mine"
        )
        include_other = toggles[1].checkbox(
            "Include Drafted by Other", key="draft_include_other"
        )
        tier_view = toggles[2].checkbox(
            "Board by Tier", key="draft_tier_view"
        )
        groups = ui.multiselect(
            "Board analytics",
            list(BOARD_GROUPS),
            default=["Core"],
            key="draft_board_groups",
        )
        if ui is st and hasattr(ui, "segmented_control"):
            point_mode = ui.segmented_control(
                "Display Points", list(POINT_DISPLAY_FIELDS), default="Total",
                key="draft_point_display_mode",
                help="Per Game uses appearances as its denominator.",
            )
        else:
            point_mode = ui.selectbox(
                "Display Points", list(POINT_DISPLAY_FIELDS),
                key="draft_point_display_mode",
                help="Per Game uses appearances as its denominator.",
            )
    return {
        "search": search, "positions": selected_positions,
        "teams": selected_teams, "sort_by": sort_by,
        "ascending": direction == "Ascending",
        "include_mine": include_mine, "include_other": include_other,
        "tier_view": tier_view,
        "groups": groups or ["Core"],
        "point_mode": point_mode,
    }


def _filter_board(frame: pd.DataFrame, controls: dict[str, Any]) -> pd.DataFrame:
    statuses = [AVAILABLE]
    if controls["include_mine"]:
        statuses.append(DRAFTED_BY_ME)
    if controls["include_other"]:
        statuses.append(DRAFTED_BY_OTHER)
    out = frame[
        frame["Draft Eligible"] & frame["Draft Status"].isin(statuses)
    ].copy()
    if controls["search"].strip():
        out = out[out["Player"].str.contains(
            controls["search"].strip(), case=False, na=False, regex=False
        )]
    if controls["positions"]:
        out = out[out["Position"].map(
            lambda value: position_matches(value, controls["positions"])
        ).astype(bool)]
    else:
        out = out.iloc[0:0]
    out = out[out["Team"].isin(controls["teams"])] if controls["teams"] else out.iloc[0:0]
    sort_map = {
        "Model Rank": "Rank", "ADP": "_display_adp",
        "Draft Score": "Draft Score",
        "Projected Points": "fantrax_projected_points",
    }
    out["_display_adp"] = pd.to_numeric(
        out["ADP"], errors="coerce"
    ).fillna(999.0)
    return sort_draft_board(
        out, sort_map[controls["sort_by"]], controls["ascending"]
    ).drop(columns="_display_adp")


def _render_status(ui: Any, frame: pd.DataFrame) -> None:
    with ui.expander("Draft Status", expanded=False):
        counts = frame["Draft Status"].value_counts()
        columns = ui.columns(4)
        for column, label in zip(
            columns, (AVAILABLE, DRAFTED_BY_ME, DRAFTED_BY_OTHER, "Total Drafted")
        ):
            value = (
                counts.get(DRAFTED_BY_ME, 0) + counts.get(DRAFTED_BY_OTHER, 0)
                if label == "Total Drafted" else counts.get(label, 0)
            )
            column.metric(label, int(value))
        confirm = ui.checkbox(
            "Confirm reset of session statuses and queue",
            key="draft_reset_confirm",
        )
        if ui.button("Reset Draft Session", disabled=not confirm):
            reset_draft_session(ui.session_state)
            ui.rerun()


def _render_board(ui: Any, frame: pd.DataFrame) -> None:
    with ui.expander("How playing-time metrics are calculated", expanded=False):
        ui.markdown(
            "**Start % 25/26** is historical starts divided by available 2025/26 gameweeks.  "
            "**Minutes % 25/26** is historical minutes divided by `38 × 90` (3,420).  "
            "**Projected Minutes % 26/27** is the builder estimate: 40% full-season minutes share, "
            "30% last-six minutes share, 20% historical start rate, and 10% last-six start rate, "
            "minus 8 points for a detected transfer with history.\n\n"
            "**Minutes Outlook 26/27 thresholds:** ≤20 Bench / Unknown; >20–45 Rotation Risk; "
            ">45–68 Likely Rotation; >68–84 Likely Starter; >84 Locked Starter. Players without "
            "historical minutes are `Unknown / New Arrival`.\n\n"
            "**Minutes Confidence (0–100):** 90 for at least 2,200 historical minutes; 75 for at "
            "least 1,200; 55 for any positive minutes; otherwise 25. A detected transfer with "
            "history subtracts 15, bounded to 0–100."
        )
    controls = _render_filters(ui, frame)
    _render_status(ui, frame)
    board = _filter_board(frame, controls)
    display = _board_table(board, controls["groups"], controls["point_mode"])
    if controls["tier_view"]:
        for tier, group in build_tier_board(board):
            ui.markdown(f"#### {tier}")
            _render_action_board(
                ui,
                group,
                _board_table(group, controls["groups"], controls["point_mode"]),
                editor_key=(
                    "draft_tier_editor_"
                    + re.sub(r"[^a-z0-9]", "_", tier.casefold())
                ),
                height=360,
            )
    else:
        _render_action_board(
            ui, board, display,
            editor_key="draft_board_editor", height=650,
        )
    ui.download_button(
        "Download filtered draft board",
        data=display.assign(
            Player=board["Player"].to_numpy(),
            **({"ADP": board["ADP"].to_numpy()} if "ADP" in display else {}),
        ).to_csv(index=False).encode("utf-8-sig"),
        file_name="fantrax_draft_board_2627_filtered.csv",
        mime="text/csv",
        key="download_draft_board_2627",
    )

    if board.empty:
        ui.info("No available players match the current filters.")


def _render_compare(ui: Any, frame: pd.DataFrame) -> None:
    include_drafted = ui.checkbox(
        "Include drafted players", key="compare_include_drafted"
    )
    options = frame if include_drafted else frame[frame["Draft Status"].eq(AVAILABLE)]
    names = options["Player"].drop_duplicates().sort_values().tolist()
    pending_player = ui.session_state.pop("draft_compare_pending_player", None)
    if pending_player in names:
        ui.session_state["compare_player_1"] = pending_player
    if ui.session_state.pop("draft_compare_clear_player_2", False):
        ui.session_state["compare_player_2"] = None
    columns = ui.columns(2)
    player_1 = columns[0].selectbox("Player 1", names, key="compare_player_1")
    player_2 = columns[1].selectbox(
        "Player 2",
        [None, *names],
        index=0,
        format_func=lambda value: value or "Choose a challenger...",
        key="compare_player_2",
    )
    if player_2 is None:
        ui.info("Player 1 is ready. Choose a challenger to begin the matchup.")
        return
    if player_1 == player_2:
        ui.warning("Select two different players.")
        return
    matchup_header = ui.columns([5, 1, 5])
    matchup_header[0].markdown(f"### {player_1}")
    matchup_header[1].markdown("### VS")
    matchup_header[2].markdown(f"### {player_2}")
    indexed = options.drop_duplicates("Player").set_index("Player")
    matchup_header[0].caption(" · ".join(player_analysis_tags(indexed.loc[player_1])) or "No analysis threshold flagged")
    matchup_header[2].caption(" · ".join(player_analysis_tags(indexed.loc[player_2])) or "No analysis threshold flagged")
    percentile_columns = ui.columns(2)
    percentile_columns[0].dataframe(draft_profile_percentiles(indexed.loc[player_1]), hide_index=True, width="stretch")
    percentile_columns[1].dataframe(draft_profile_percentiles(indexed.loc[player_2]), hide_index=True, width="stretch")
    comparison = comparison_winner_data(options, player_1, player_2)
    if comparison.empty:
        ui.info("No shared Draft metrics are available for this matchup.")
        return
    comparison["Winner"] = comparison["Winner"].map(
        lambda winner: "Tie" if winner == "Tie" else f"● {winner}"
    )
    if ui is st:
        def highlight_winner(row: pd.Series) -> list[str]:
            winner = str(row["Winner"]).removeprefix("● ")
            return [
                (
                    "background-color: rgba(46, 160, 67, 0.16); "
                    "color: #1f7a3f; font-weight: 700"
                    if column == winner else ""
                )
                for column in row.index
            ]

        ui.dataframe(
            comparison.style.apply(highlight_winner, axis=1).hide(
                subset=["Winner"], axis="columns"
            ),
            hide_index=True,
            width="stretch",
        )
    else:
        ui.dataframe(
            comparison.drop(columns="Winner"), hide_index=True, width="stretch"
        )


def _queue_frame(frame: pd.DataFrame, queue: list[str]) -> pd.DataFrame:
    queued = frame[frame["_Player Key"].isin(queue)].copy()
    queued["Queue"] = queued["_Player Key"].map(
        {key: index + 1 for index, key in enumerate(queue)}
    )
    return queued.sort_values("Queue")


def _render_queue(ui: Any, frame: pd.DataFrame) -> None:
    queue = ui.session_state["draft_queue"]
    queued = _queue_frame(frame, queue)
    if queued.empty:
        ui.info("Your active Draft Queue is empty.")
        return
    ui.dataframe(
        queued[["Queue", "Player", "Position", "Team", "tier", "Rank",
                "Draft Score", "ADP", "Draft Status"]],
        hide_index=True, width="stretch",
    )
    key = ui.selectbox(
        "Queue player", queue,
        format_func=lambda value: queued.set_index("_Player Key").at[value, "Player"],
        key="queue_selected_key",
    )
    row = _selected_row(frame, key)
    controls = ui.columns(5)
    for column, (label, action) in zip(
        controls[:3], (("Move up", "up"), ("Move down", "down"), ("Remove", "remove"))
    ):
        if column.button(label, key=f"queue_{action}"):
            ui.session_state["draft_queue"] = update_queue(queue, key, action)
            ui.rerun()
    if controls[3].button("Drafted by Me", key="queue_mine"):
        _set_status(ui, row, DRAFTED_BY_ME)
    if controls[4].button("Drafted by Other", key="queue_other"):
        _set_status(ui, row, DRAFTED_BY_OTHER)
    _detail(ui, row, "queue_detail")


def _render_team(ui: Any, frame: pd.DataFrame) -> None:
    team = frame[frame["Draft Status"].eq(DRAFTED_BY_ME)].copy()
    if team.empty:
        ui.info("No players have been marked Drafted by Me.")
        return
    order = {
        key: index + 1
        for index, key in enumerate(ui.session_state["draft_sequence"])
    }
    team["Draft Sequence"] = team["_Player Key"].map(order)
    team = team.sort_values(["Draft Sequence", "Rank"], na_position="last")

    ui.markdown("### Team Overview")
    summary = team_summary(team)
    overview_fields = (
        "Players Drafted", "Average Draft Score", "Total Fantrax Projected Points",
        "Average ADP Value", "Average Projected Minutes %", "Ghost / 90",
        "Total xG", "Total xA", "xGI / 90",
    )
    cards = ui.columns(3)
    for index, label in enumerate(overview_fields):
        value = summary.get(label)
        cards[index % 3].metric(
            label, format_detail_value(value, integer=label == "Players Drafted")
        )
    ui.caption("Rate metrics are historical-minute-weighted; projected points are summed Fantrax projections.")

    ui.markdown("### Positional Coverage")
    coverage = positional_coverage(team)
    ui.dataframe(coverage, hide_index=True, width="stretch")
    open_needs = coverage[
        coverage["Position"].isin(["G", "D", "M", "F"]) & coverage["Unfilled"].gt(0)
    ]
    if not open_needs.empty:
        strongest = open_needs.sort_values(["Unfilled", "Position"], ascending=[False, True]).iloc[0]
        ui.warning(f"Strongest need: {strongest['Position']} — {int(strongest['Unfilled'])} required slot(s) open.")

    available = frame[frame["Draft Status"].eq(AVAILABLE)]
    priorities = draft_strategy_priorities(team, available)
    scarcity = position_scarcity(available)
    strategic = priorities.iloc[0]
    scarce = scarcity.sort_values("Scarcity Score", ascending=False).iloc[0]
    ui.markdown("#### Draft Strategy")
    config = ui.session_state.get("draft_strategy_config", {"league_size": 12, "draft_slot": 2, "rounds": 16})
    if ui is st:
        with ui.expander("Snake Draft Configuration", expanded=False):
            config_columns = ui.columns(3)
            league_size = int(config_columns[0].number_input("Managers", min_value=2, max_value=30, value=config["league_size"], step=1))
            draft_slot = int(config_columns[1].number_input("My Draft Slot", min_value=1, max_value=league_size, value=min(config["draft_slot"], league_size), step=1))
            rounds = int(config_columns[2].number_input("Roster Rounds", min_value=1, max_value=30, value=config["rounds"], step=1))
            config = {"league_size": league_size, "draft_slot": draft_slot, "rounds": rounds}
            ui.session_state["draft_strategy_config"] = config
    completed = int(frame["Draft Status"].ne(AVAILABLE).sum())
    turn = draft_turn_context(completed, config["league_size"], config["draft_slot"], config["rounds"])
    strategy_cards = ui.columns(5)
    strategy_cards[0].metric("Current Pick", turn["Current Pick"])
    strategy_cards[1].metric("Next Pick", turn["Next User Pick"])
    strategy_cards[2].metric("Picks Until Next Turn", turn["Picks Until Next Turn"])
    strategy_cards[3].metric("Roster Need", strongest["Position"] if not open_needs.empty else "Complete")
    strategy_cards[4].metric("Strategic Priority", strategic["Position"])
    context_cards = ui.columns(4)
    context_cards[0].metric("Scarcity", f"{scarce['Position']} · {scarce['Scarcity']}")
    context_cards[1].metric("Tier Cliff", f"{scarce['Position']} · {scarce['Tier Cliff']:.1f}")
    context_cards[2].metric("Next-Pick Risk", f"{turn['Picks Until Next Turn']} selections")
    goalkeeper = priorities[priorities["Position"].eq("G")].iloc[0]["Goalkeeper Timing"] or "Goalkeeper filled"
    context_cards[3].metric("Goalkeeper", goalkeeper)
    ui.caption(f"Suggested next position: {strategic['Position']} — priority {strategic['Strategy Priority']:.1f}.")

    strengths, risks = team_strengths_and_risks(team)
    ui.markdown("### Team Strengths and Risks")
    narrative = ui.columns(2)
    narrative[0].markdown("#### Strengths\n" + ("\n".join(f"- {item}" for item in strengths) or "- No threshold met yet"))
    narrative[1].markdown("#### Risks\n" + ("\n".join(f"- {item}" for item in risks) or "- No threshold flagged"))

    floor = team_floor(team)
    ui.markdown("### Team Profile Visualization")
    profile = pd.DataFrame({
        "Dimension": ["Projection", "Floor", "Attacking", "Minutes", "ADP Value", "Team Context", "Fixture Ease", "Positional Balance"],
        "Score": [summary["Average Draft Score"], floor["Team Floor Score"], summary["Average Attacking Score"], summary["Average Projected Minutes %"], np.clip(summary["Average ADP Value"] * 2 + 50, 0, 100), summary["Team Strength Percentile"], summary["Fixture Ease Percentile"], 100 * (1 - coverage.loc[coverage["Position"].isin(["G", "D", "M", "F"]), "Unfilled"].sum() / 7)],
    })
    ui.dataframe(profile, hide_index=True, width="stretch", column_config={"Score": ui.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.1f")})

    ui.markdown("### Best Available Fits")
    strategy = ui.selectbox("Strategy emphasis", list(STRATEGY_WEIGHTS), key="draft_fit_strategy")
    ui.dataframe(best_available_fits(frame, team, strategy, current_pick=turn["Current Pick"], next_pick=turn["Next User Pick"]), hide_index=True, width="stretch")

    ui.markdown("### Team Projection and Floor")
    projection_cards = ui.columns(4)
    projection_cards[0].metric("Projected Points", format_detail_value(summary["Total Fantrax Projected Points"]))
    projection_cards[1].metric("Team Floor Score", format_detail_value(floor["Team Floor Score"]))
    projection_cards[2].metric("Ghost / 90", format_detail_value(summary["Ghost / 90"]))
    projection_cards[3].metric("Avg Minutes %", format_detail_value(summary["Average Projected Minutes %"]))
    ui.caption("Team Floor Score is not a weekly-points prediction: 40% Ghost Score + 35% Minutes Score + 25% Minutes Confidence.")
    ui.dataframe(pd.DataFrame({"Component": list(floor), "Score": list(floor.values())}), hide_index=True, width="stretch")

    ui.markdown("### Attacking Upside")
    attack = pd.DataFrame({"Metric": [k for k in summary if k in {"Total xG", "Total xA", "Total xGI", "xG / 90", "xA / 90", "xGI / 90", "Average Attacking Score"}], "Value": [summary[k] for k in summary if k in {"Total xG", "Total xA", "Total xGI", "xG / 90", "xA / 90", "xGI / 90", "Average Attacking Score"}]})
    ui.dataframe(attack, hide_index=True, width="stretch")

    ui.markdown("### Minutes Security")
    minutes_cards = ui.columns(2)
    minutes_cards[0].metric("Average Projected Minutes %", format_detail_value(summary["Average Projected Minutes %"]))
    minutes_cards[1].metric("Average Minutes Confidence", format_detail_value(pd.to_numeric(team.get("minutes_confidence"), errors="coerce").mean()))

    ui.markdown("### Club and Fixture Context")
    context_cards = ui.columns(3)
    context_cards[0].metric("Avg Team Strength %ile", format_detail_value(summary["Team Strength Percentile"]))
    context_cards[1].metric("Avg Fixture Ease %ile", format_detail_value(summary["Fixture Ease Percentile"]))
    context_cards[2].metric("Clubs Represented", int(team["Team"].nunique()))
    club_counts = team["Team"].value_counts().rename_axis("Club").reset_index(name="Players")
    ui.dataframe(club_counts, hide_index=True, width="stretch")

    ui.markdown("### Drafted Players")
    ui.dataframe(
        team[[c for c in ["Draft Sequence", "Player", "Position", "Team", "tier", "Rank",
              "Draft Score", "ADP", "Value vs ADP", "fantrax_projected_points",
              "minutes_outlook", "ghost_per90_2526", "xgi90_2526",
              "team_strength_percentile", "fixture_ease_percentile"] if c in team]].rename(columns={
                  "fantrax_projected_points": "Projected Points",
                  "ghost_per90_2526": "Ghost / 90",
                  "xgi90_2526": "xGI / 90",
                  "team_strength_percentile": "Team Strength Percentile",
                  "fixture_ease_percentile": "Fixture Ease Percentile",
              }),
        hide_index=True, width="stretch",
    )
    key = ui.selectbox(
        "My Team player", team["_Player Key"].tolist(),
        format_func=lambda value: team.set_index("_Player Key").at[value, "Player"],
        key="team_selected_key",
    )
    row = _selected_row(frame, key)
    if ui.button("Return selected player to Available", key="team_available"):
        _set_status(ui, row, AVAILABLE)
    _detail(ui, row, "team_detail")


def _render_draft_grades(ui: Any, managers: pd.DataFrame, picks: pd.DataFrame, awards: pd.DataFrame) -> None:
    ui.markdown("### 2026/27 Draft Complete")
    ui.caption("Draft HQ Analysis — frozen draft-day projections and analytics; no hindsight results.")
    highlights = ui.columns(3)
    top = managers.sort_values(["overall_rank", "manager"]).iloc[0]
    highlights[0].metric("Best Overall Draft", f"{top['manager']} · {top['overall_grade']}")
    for column, award_name in zip(highlights[1:], ("Biggest Steal", "Biggest Reach")):
        award = awards[awards["award"].eq(award_name)]
        column.metric(award_name, award.iloc[0]["winner"] if not award.empty else "—")
    ui.markdown("#### League Rankings")
    columns = ["overall_rank", "manager", "letter_grade", "league_relative_score", "raw_analytical_score", "top_category", "main_concern"]
    ui.dataframe(managers[[c for c in columns if c in managers]], hide_index=True, width="stretch")
    with ui.expander("How grades are calculated", expanded=False):
        ui.markdown(
            "**Raw Analytical Score** is the weighted underlying draft model result from the frozen draft-day snapshot. "
            "**League-Relative Grade Score** uses `80 + 10 × z-score`, clipped to 55–98, to describe performance against the other 11 drafts. "
            "Letter grades use the calibrated score. Projected Production asks how many points the roster should score; Historical Production asks what it produced per 90; "
            "Floor asks how safe it is; Playing Time asks whether players will play; Draft Value measures value gained; Attacking Upside asks how explosive it is; "
            "and Roster Construction grades the best legal XI, bench, balance, flexibility, and goalkeeper timing. No post-draft results or hindsight are included."
        )
    ui.markdown("#### League Awards")
    ui.dataframe(awards, hide_index=True, width="stretch")
    if ui is st:
        import plotly.graph_objects as go
        category_fields = ["projected_production_score", "floor_score", "attacking_upside_score", "playing_time_security_score", "draft_value_score", "roster_construction_score"]
        labels = ["Projection", "Floor", "Upside", "Playing Time", "Value", "Construction"]
        radar = go.Figure()
        for row in managers.itertuples():
            values = [getattr(row, field) for field in category_fields]
            radar.add_trace(go.Scatterpolar(r=values + values[:1], theta=labels + labels[:1], fill="toself", name=row.manager))
        radar.update_layout(title="League Team Profiles", polar={"radialaxis":{"range":[0,100]}}, height=650)
        ui.plotly_chart(radar, width="stretch", config={"displayModeBar": False})
        scatters = (("best_xi_projected_points", "ghost_per_90", "Projection vs Floor"),
                    ("average_pick_vs_adp", "draft_value_score", "Value vs ADP"),
                    ("xgi_per_90", "average_projected_minutes_pct", "Upside vs Minutes"))
        for x, y, title in scatters:
            figure = go.Figure(go.Scatter(x=managers[x], y=managers[y], mode="markers+text", text=managers["manager"], textposition="top center"))
            figure.update_layout(title=title, xaxis_title=x.replace("_", " ").title(), yaxis_title=y.replace("_", " ").title(), height=430)
            ui.plotly_chart(figure, width="stretch", config={"displayModeBar": False})


def _render_simple_draft_grades(ui: Any, managers: pd.DataFrame, picks: pd.DataFrame, awards: pd.DataFrame) -> None:
    summary = build_share_summary(managers, picks).sort_values(["rank", "manager"])
    ui.markdown("### 2026/27 League Draft Rankings")
    ui.caption("12 managers · 180 picks")
    winner = summary.iloc[0]
    projection = summary.sort_values(["projected_starting_xi_points", "manager"], ascending=[False, True]).iloc[0]
    value = managers.sort_values(["draft_value_score", "manager"], ascending=[False, True]).iloc[0]
    floor = summary.sort_values(["ghost_points_per_90", "manager"], ascending=[False, True]).iloc[0]
    headlines = ui.columns(4)
    headlines[0].metric("1st Place", f"{winner['manager']} · {winner['grade']}")
    headlines[1].metric("Highest Projected XI", f"{projection['manager']} · {projection['projected_starting_xi_points']:,.0f}")
    headlines[2].metric("Best Value Draft", value["manager"])
    headlines[3].metric("Highest Floor", f"{floor['manager']} · {floor['ghost_points_per_90']:.1f}/90")
    ui.caption("Grades compare each draft against the other 11 league drafts using frozen draft-day projections and historical data.")
    display = summary.rename(columns={
        "rank":"Rank", "manager":"Manager", "grade":"Grade", "league_relative_score":"League-Relative Score",
        "projected_starting_xi_points":"Projected Starting XI Points", "average_player_projection":"Average Player Projection",
        "average_adp":"Average ADP", "fantasy_points_per_90":"Last-Season Fantasy Points / 90",
        "ghost_points_per_90":"Last-Season Ghost Points / 90", "historical_start_pct":"Historical Start %",
        "projected_minutes_pct":"Projected Minutes %", "main_strength":"Main Strength", "main_concern":"Main Concern",
    })
    columns = ["Rank","Manager","Grade","League-Relative Score","Projected Starting XI Points","Average Player Projection","Average ADP","Last-Season Fantasy Points / 90","Last-Season Ghost Points / 90","Historical Start %","Projected Minutes %","Main Strength","Main Concern"]
    ui.dataframe(display[columns], hide_index=True, width="stretch", column_config={
        "Projected Starting XI Points": ui.column_config.NumberColumn("Projected Starting XI Points", help="Fantrax projected points for the optimized legal starting XI.", format="%.1f"),
        "Average Player Projection": ui.column_config.NumberColumn("Average Player Projection", help="Mean Fantrax projection across all 15 drafted players.", format="%.1f"),
        "Average ADP": ui.column_config.NumberColumn("Average ADP", help="Mean numeric Fantrax ADP; missing ADP is excluded.", format="%.1f"),
        "Last-Season Fantasy Points / 90": ui.column_config.NumberColumn("Last-Season Fantasy Points / 90", help="Team fantasy points × 90 divided by team historical minutes.", format="%.1f"),
        "Last-Season Ghost Points / 90": ui.column_config.NumberColumn("Last-Season Ghost Points / 90", help="Team ghost points × 90 divided by team historical minutes.", format="%.1f"),
        "Historical Start %": ui.column_config.NumberColumn("Historical Start %", help="Total starts divided by total available player-weeks.", format="%.1f%%"),
        "Projected Minutes %": ui.column_config.NumberColumn("Projected Minutes %", help="Average projected 2026/27 minutes share across the roster.", format="%.1f%%"),
    })
    ui.markdown("#### Manager Summaries")
    card_columns = ui.columns(3)
    for index, row in enumerate(summary.itertuples()):
        accent = "#b88919" if row.rank <= 3 else "#dfe6ef"
        card_columns[index % 3].markdown(
            f"<div style='border:1px solid {accent};border-radius:12px;padding:12px;margin-bottom:10px'>"
            f"<div style='font-size:1.05rem;font-weight:750'>#{row.rank} {html.escape(row.manager)} <span style='float:right'>{row.grade}</span></div>"
            f"<div style='font-size:.82rem;line-height:1.55;margin-top:7px'>XI <b>{row.projected_starting_xi_points:,.0f}</b> · ADP <b>{row.average_adp:.1f}</b> · FP/90 <b>{row.fantasy_points_per_90:.1f}</b><br>"
            f"Ghost/90 <b>{row.ghost_points_per_90:.1f}</b> · Start <b>{row.historical_start_pct:.1f}%</b> · Proj Min <b>{row.projected_minutes_pct:.1f}%</b><br>"
            f"<span style='color:#237a3b'>Strength: {html.escape(row.main_strength)}</span><br><span style='color:#9b3d32'>Concern: {html.escape(row.main_concern)}</span></div></div>",
            unsafe_allow_html=True,
        )
    downloads = ui.columns(2)
    downloads[0].download_button("Download share CSV", data=share_csv(summary), file_name="draft_grades_2627_share.csv", mime="text/csv", key="download_draft_share_csv")
    downloads[1].download_button("Download standalone HTML", data=share_html(summary).encode("utf-8"), file_name="draft_grades_2627_share.html", mime="text/html", key="download_draft_share_html")
    if ui is st:
        ui.markdown("#### Share Poster")
        poster_png, poster_pdf = _poster_downloads(managers, picks)
        ui.image(poster_png, caption="2026/27 League Draft Rankings poster · 2400 × 3200", width="stretch")
        poster_downloads = ui.columns(2)
        poster_downloads[0].download_button("Download Poster PNG", data=poster_png, file_name="draft_grades_2627_poster.png", mime="image/png", key="download_draft_poster_png")
        poster_downloads[1].download_button("Download Poster PDF", data=poster_pdf, file_name="draft_grades_2627_poster.pdf", mime="application/pdf", key="download_draft_poster_pdf")
    with ui.expander("Detailed Analysis", expanded=False):
        ui.markdown("#### League Awards")
        ui.dataframe(awards, hide_index=True, width="stretch")
        ui.caption("Detailed category grades, charts, and manager tables remain available in League Rankings and Manager Report Cards.")


def _render_league_rankings(ui: Any, managers: pd.DataFrame, categories: pd.DataFrame) -> None:
    ui.markdown("### League Draft Rankings")
    columns = ["overall_rank", "manager", "letter_grade", "league_relative_score", "raw_analytical_score", "top_category", "main_concern"]
    ui.dataframe(managers.sort_values(["overall_rank", "manager"])[columns], hide_index=True, width="stretch")
    ui.markdown("#### Category Leaders")
    leaders = categories.sort_values(["category", "score", "manager"], ascending=[True, False, True]).groupby("category", as_index=False).first()
    ui.dataframe(leaders[["category", "manager", "score", "calibrated_category_score", "category_letter_grade"]], hide_index=True, width="stretch")


def _render_manager_reports(ui: Any, managers: pd.DataFrame, picks: pd.DataFrame, categories: pd.DataFrame) -> None:
    ui.markdown("### Manager Report Cards")
    manager = ui.selectbox("Manager report", managers.sort_values(["overall_rank", "manager"])["manager"].tolist(), key="draft_grade_manager")
    summary = managers[managers["manager"].eq(manager)].iloc[0]
    cards = ui.columns(5)
    cards[0].metric("League Rank", f"{int(summary['overall_rank'])} of {len(managers)}")
    cards[1].metric("Overall Grade", summary["letter_grade"])
    cards[2].metric("League-Relative Score", f"{summary['league_relative_score']:.1f}")
    cards[3].metric("Raw Analytical Score", f"{summary['raw_analytical_score']:.1f}")
    cards[4].metric("Draft Slot", int(summary["draft_slot"]))
    ui.caption(summary.get("draft_identity", ""))
    ui.dataframe(categories[categories["manager"].eq(manager)][["category", "score", "league_rank", "league_percentile", "calibrated_category_score", "category_letter_grade", "weight", "contribution"]], hide_index=True, width="stretch")
    ui.markdown("#### Headline Statistics")
    manager_picks = picks[picks["manager"].eq(manager)]
    headline = {
        "Projected Points": summary.get("total_projected_points"), "Average ADP": pd.to_numeric(manager_picks.get("adp", pd.Series(dtype=float)), errors="coerce").mean(),
        "Fantasy Pts / 90": summary.get("fantasy_per_90"), "Ghost / 90": summary.get("ghost_per_90"), "xGI / 90": summary.get("xgi_per_90"),
        "Average Start %": summary.get("average_historical_start_pct"), "Projected Minutes %": summary.get("average_projected_minutes_pct"),
        "Best XI Projection": summary.get("best_xi_projected_points"),
    }
    headline_cards = ui.columns(4)
    for index, (label, value) in enumerate(headline.items()): headline_cards[index % 4].metric(label, format_detail_value(value))
    selected = picks[picks["manager"].eq(manager)].sort_values("overall_pick")
    if {"fantrax_position", "projected_points", "canonical_position"}.issubset(selected):
        xi, bench = best_legal_xi(selected)
        ui.markdown("#### Projected Best Legal XI")
        ui.dataframe(xi[[c for c in ["starting_slot", "player", "fantrax_position", "club", "projected_points", "fantasy_per_90", "ghost_per_90", "xgi_per_90", "historical_start_rate", "projected_minutes_share"] if c in xi]], hide_index=True, width="stretch")
        ui.markdown("#### Bench Depth")
        ui.dataframe(bench[[c for c in ["player", "fantrax_position", "club", "projected_points", "ghost_per_90", "projected_minutes_share"] if c in bench]].sort_values("projected_points", ascending=False), hide_index=True, width="stretch")
        ui.markdown("#### Position Groups")
        positions = position_analysis(selected)
        ui.dataframe(positions, hide_index=True, width="stretch")
    ui.markdown("#### Draft Summary")
    category_view = categories[categories["manager"].eq(manager)].sort_values("calibrated_category_score", ascending=False)
    friendly = lambda value: str(value).replace("_", " ").title()
    summary_columns = ui.columns(2)
    summary_columns[0].markdown("**Strengths**\n" + "\n".join(f"- {friendly(value)}" for value in category_view.head(3)["category"]))
    summary_columns[1].markdown("**Weaknesses**\n" + "\n".join(f"- {friendly(value)}" for value in category_view.tail(2)["category"]))
    columns = ["round", "overall_pick", "player", "fantrax_position", "club", "draft_score", "adp", "pick_grade", "pick_letter_grade", "pick_labels"]
    ui.dataframe(selected[[c for c in columns if c in selected]], hide_index=True, width="stretch")


def render(
    season_id: str,
    *,
    data_manager: DataManager | None = None,
    season_manager: SeasonManager | None = None,
    ui: Any = st,
) -> None:
    seasons = season_manager or SeasonManager()
    season = seasons.context(season_id)
    namespace = seasons.resolve_namespace(season.season_id)
    data = data_manager or DataManager(season_manager=seasons)
    rankings = _load(data, "draft_rankings", season_id, namespace, ui)
    if rankings.empty:
        ui.warning("Draft rankings are missing or empty.")
        ui.stop()
    # Keep the optional registered read in the page contract. Eligibility
    # changes remain producer-owned.
    overrides = _load(
        data, "draft_eligibility_overrides", season_id, namespace, ui
    )
    if not overrides.empty:
        ids = rankings.get(
            "fantrax_player_id", pd.Series("", index=rankings.index)
        ).astype(str)
        names = rankings.get(
            "player_name", pd.Series("", index=rankings.index)
        ).astype(str).str.casefold().str.strip()
        for _, override in overrides.iterrows():
            override_id = str(override.get("fantrax_player_id", "")).strip()
            override_name = str(override.get("player_name", "")).casefold().strip()
            mask = ids.eq(override_id) if override_id else names.eq(override_name)
            if mask.any():
                rankings.loc[mask, "is_draft_eligible"] = str(
                    override.get("is_draft_eligible", "")
                ).strip().casefold() in {"true", "1", "yes", "y"}
    fantrax_source = _load(
        data, "current_fantrax_player_pool", season_id, namespace, ui
    )
    if not fantrax_source.empty and {
        "fantrax_player_id", "fantrax_position"
    }.issubset(fantrax_source):
        eligibility = fantrax_source[
            ["fantrax_player_id", "fantrax_position"]
        ].copy()
        eligibility["_fantrax_key"] = eligibility["fantrax_player_id"].map(
            normalize_player_id
        )
        eligibility = eligibility.drop_duplicates("_fantrax_key", keep="last")
        rankings["_fantrax_key"] = rankings["fantrax_player_id"].map(
            normalize_player_id
        )
        rankings = rankings.merge(
            eligibility[["_fantrax_key", "fantrax_position"]],
            on="_fantrax_key", how="left", validate="many_to_one",
        ).drop(columns="_fantrax_key")
        rankings["fantrax_position_eligibility"] = rankings[
            "fantrax_position"
        ].combine_first(rankings.get(
            "fantrax_position_eligibility",
            pd.Series(pd.NA, index=rankings.index),
        ))

    state = getattr(ui, "session_state", {})
    state.setdefault("draft_player_statuses", {})
    state.setdefault("draft_queue", [])
    state.setdefault("draft_sequence", [])
    state.setdefault("draft_strategy_config", {
        "league_size": 12, "draft_slot": 2, "rounds": 16,
    })
    frame = prepare_draft_frame(rankings, state["draft_player_statuses"])
    post_draft = {
        key: _load(data, key, season_id, namespace, ui)
        for key in POST_DRAFT_DATASET_KEYS
    }
    has_grades = not post_draft["draft_manager_grades"].empty
    notice = state.pop("draft_action_notice", "")
    if notice:
        if ui is st and hasattr(ui, "toast"):
            ui.toast(notice)
        else:
            ui.info(notice)

    ui.markdown(
        '<div class="section-eyebrow">2026/27 premium draft workspace</div>'
        '<div class="section-title">Draft HQ</div>',
        unsafe_allow_html=True,
    )
    live_tabs = ["Draft Board", "Compare Players", "My Queue", "My Team"]
    tab_labels = (["Draft Grades", "League Rankings", "Manager Report Cards"] + live_tabs) if has_grades else live_tabs
    pending_tab = state.pop("draft_workspace_pending_tab", None)
    if pending_tab in tab_labels:
        state["draft_workspace_tab"] = pending_tab
    if hasattr(ui, "tabs"):
        tabs = (
            ui.tabs(
                tab_labels,
                default=state.get("draft_workspace_tab", "Draft Board"),
                key="draft_workspace_tab",
            )
            if ui is st else ui.tabs(tab_labels)
        )
    else:
        tabs = ui.columns(4)
    offset = 3 if has_grades else 0
    if has_grades:
        with tabs[0]: _render_simple_draft_grades(ui, post_draft["draft_manager_grades"], post_draft["draft_pick_grades"], post_draft["draft_awards"])
        with tabs[1]: _render_league_rankings(ui, post_draft["draft_manager_grades"], post_draft["draft_category_scores"])
        with tabs[2]: _render_manager_reports(ui, post_draft["draft_manager_grades"], post_draft["draft_pick_grades"], post_draft["draft_category_scores"])
    with tabs[offset]: _render_board(ui, frame)
    with tabs[offset + 1]: _render_compare(ui, frame)
    with tabs[offset + 2]: _render_queue(ui, frame)
    with tabs[offset + 3]: _render_team(ui, frame)
    if ui is st and st.session_state.get("draft_detail_dialog_open"):
        detail_key = st.session_state.get("draft_detail_player_key")
        selected = _selected_row(frame, detail_key)
        if selected is not None:
            _player_dialog(selected)
