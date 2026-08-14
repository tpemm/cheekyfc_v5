"""Managers page backed by the foundation data services."""

from __future__ import annotations

from typing import Any
import html

import pandas as pd
import streamlit as st

try:
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    go = None
    PLOTLY_AVAILABLE = False

from core.models.data_result import DataStatus
from core.services.data_manager import (
    DataManager,
    DatasetNotFoundError,
    DatasetValidationError,
    UnsupportedFormatError,
)
from core.services.season_manager import SeasonManager


DATASET_KEYS: tuple[str, ...] = (
    "manager_profile_summary",
    "league_table",
    "manager_week_summary",
    "matchup_week_summary",
    "lineup_decision_details",
    "roster_adds_weekly",
    "position_points_manager_season",
    "ghost_points_manager_weekly",
    "manager_behavior_weekly",
    "manager_behavior_season",
    "formation_weekly",
    "formation_manager_summary",
    "manager_streaks",
    "manager_player_weekly",
    "manager_efficiency_weekly",
    "lineup_quality_summary",
)


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


def clean_display_name(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = str(value)
    text = text.replace("â€™", "’")
    for unwanted in ["🤡", "ðŸ¤¡"]:
        text = text.replace(unwanted, "")
    return " ".join(text.split()).strip()


def metric_or_blank(container: Any, label: str, value: Any, delta: Any = None) -> None:
    container.metric(label, format_value(value), None if delta is None else str(delta))


def render_context_stat(container: Any, label: str, value: Any, detail: str | None = None) -> None:
    value_text = format_value(value) or "—"
    detail_text = str(detail).strip() if detail is not None and str(detail).strip() else "No additional context available"
    container.markdown(
        f'<div class="context-stat-card">'
        f'<div class="context-stat-label">{label}</div>'
        f'<div class="context-stat-value">{value_text}</div>'
        f'<div class="context-stat-detail">{detail_text}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _load_frame(data: DataManager, dataset_key: str, season_id: str, namespace: str, ui: Any) -> pd.DataFrame:
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
    return result.data.copy() if isinstance(result.data, pd.DataFrame) else pd.DataFrame()


def render(
    season_id: str,
    *,
    data_manager: DataManager | None = None,
    season_manager: SeasonManager | None = None,
    ui: Any = st,
) -> None:
    """Render the existing Managers workflow."""

    seasons = season_manager or SeasonManager()
    season = seasons.context(season_id)
    namespace = seasons.resolve_namespace(season.season_id)
    data = data_manager or DataManager(season_manager=seasons)
    selected_season_label = season.display_name
    CURRENT_SEASON_ID = season.season_id
    st = ui

    def _first_col(
        frame: pd.DataFrame,
        candidates: list[str],
        *,
        contains_all: list[str] | None = None,
        excludes: list[str] | None = None,
    ) -> str | None:
        for candidate in candidates:
            if candidate in frame.columns:
                return candidate
        required = [value.casefold() for value in (contains_all or [])]
        rejected = [value.casefold() for value in (excludes or [])]
        for column in frame.columns:
            normalized = str(column).casefold()
            if all(value in normalized for value in required) and not any(
                value in normalized for value in rejected
            ):
                return str(column)
        return None

    def _manager_rows(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame.copy()
        manager_col = _first_col(
            frame,
            ["api_team_name", "manager_name", "team_name", "Manager", "Team"],
        )
        if manager_col is None:
            return frame.copy()
        return frame[
            frame[manager_col].map(clean_display_name).eq(manager)
        ].copy()

    st.markdown(
        '<div class="section-eyebrow">Manager coaching</div>'
        '<div class="section-title">Managers</div>'
        '<div class="section-copy">Understand how each manager performs, where decisions help or hurt, and which habits are worth changing.</div>',
        unsafe_allow_html=True,
    )

    frames = {
        key: _load_frame(data, key, season.season_id, namespace, ui)
        for key in DATASET_KEYS
    }
    profile = frames["manager_profile_summary"]
    league_table = frames["league_table"]
    manager_week = frames["manager_week_summary"]
    matchup_week = frames["matchup_week_summary"]
    decisions = frames["lineup_decision_details"]
    roster_adds = frames["roster_adds_weekly"]
    pos_season = frames["position_points_manager_season"]
    ghost_weekly = frames["ghost_points_manager_weekly"]
    behavior_weekly = frames["manager_behavior_weekly"]
    behavior_season = frames["manager_behavior_season"]
    formation_weekly = frames["formation_weekly"]
    formation_summary = frames["formation_manager_summary"]
    streaks = frames["manager_streaks"]
    player_week = frames["manager_player_weekly"]
    efficiency_weekly = frames["manager_efficiency_weekly"]
    lineup_quality = frames["lineup_quality_summary"]

    if profile.empty:
        st.info("Manager analytics are not available yet for this season.")
        st.stop()

    if season.finalized:
        st.markdown('<div class="hub-panel-title">Historical Manager Directory</div><div class="hub-panel-copy">Final rank, record, scoring profile, consistency, form, and points context.</div>',unsafe_allow_html=True)
        directory=profile.copy().sort_values("official_rank",na_position="last")
        for start in range(0,len(directory),3):
            directory_columns=st.columns(3,gap="medium")
            for column,(_,manager_row) in zip(directory_columns,directory.iloc[start:start+3].iterrows()):
                name=clean_display_name(manager_row.get("api_team_name","Unknown")); weekly=manager_week[manager_week.get("api_team_name",pd.Series(index=manager_week.index,dtype=object)).map(clean_display_name).eq(name)]
                scores=pd.to_numeric(weekly.get("starter_fantasy_points",pd.Series(index=weekly.index,dtype=float)),errors="coerce"); average=scores.mean(); consistency=scores.std()
                matchups=matchup_week[matchup_week.get("api_team_name",pd.Series(index=matchup_week.index,dtype=object)).map(clean_display_name).eq(name)]
                if "fantrax_gw" in matchups: matchups=matchups.sort_values("fantrax_gw")
                form=" ".join(str(value).upper() for value in matchups.get("computed_result",pd.Series(dtype=object)).dropna().tolist()[-5:]) or "—"
                against=pd.to_numeric(matchups.get("opponent_starter_fantasy_points",pd.Series(index=matchups.index,dtype=float)),errors="coerce").sum(min_count=1)
                card=(f'<div class="ft-card" style="min-height:185px"><div class="ft-label">Rank #{format_value(manager_row.get("official_rank")) or "—"}</div><div class="ft-kpi-value" style="font-size:1.05rem">{html.escape(name)}</div><div class="ft-detail">{html.escape(str(manager_row.get("official_record","—")))} · Form {html.escape(form)}</div><div class="shared-manager-grid" style="margin-top:.7rem"><span><small>Average score</small><b>{format_value(average) or "—"}</b></span><span><small>Consistency SD</small><b>{format_value(consistency) or "—"}</b></span><span><small>Points for</small><b>{format_value(manager_row.get("total_starter_points")) or "—"}</b></span><span><small>Points against</small><b>{format_value(against) or "—"}</b></span></div></div>')
                with column:
                    st.markdown(card,unsafe_allow_html=True)
                    if hasattr(st,"button") and hasattr(st,"session_state") and st.button(f"Open {name}",key=f"historical_manager_{manager_row.get('api_team_id',name)}",use_container_width=True): st.session_state["manager_dashboard_selector"]=name; st.rerun()

    manager_names = sorted(profile["api_team_name"].dropna().map(clean_display_name).unique())
    manager = st.selectbox("Manager", manager_names, key="manager_dashboard_selector")

    selected_profile = profile[
        profile["api_team_name"].map(clean_display_name).eq(manager)
    ]
    if selected_profile.empty:
        st.warning(f"Manager {manager!r} is not available for this season.")
        st.stop()
        return
    row = selected_profile.iloc[0]
    league_row = league_table[league_table.get("api_team_name", pd.Series(dtype=str)).map(clean_display_name).eq(manager)]
    league_row = league_row.iloc[0] if not league_row.empty else pd.Series(dtype=object)

    manager_matchups = matchup_week[
        matchup_week.get("api_team_name", pd.Series(dtype=str)).map(clean_display_name).eq(manager)
    ].copy()
    manager_scores = manager_week[
        manager_week.get("api_team_name", pd.Series(dtype=str)).map(clean_display_name).eq(manager)
    ].copy()

    record = row.get("official_record", league_row.get("official_record", ""))
    rank = row.get("official_rank", league_row.get("official_rank", ""))
    starter_points = row.get("total_starter_points", league_row.get("total_starter_points", ""))
    efficiency = row.get("season_efficiency_pct", row.get("efficiency_pct", ""))

    # Resolve points against from the league table first, then fall back to
    # opponent scoring columns in the manager matchup history.
    points_against = pd.NA
    for c in [
        "total_points_against", "points_against", "total_opponent_points",
        "opponent_points_total", "official_points_against", "pa",
    ]:
        if c in league_row.index and pd.notna(league_row.get(c)):
            points_against = pd.to_numeric(league_row.get(c), errors="coerce")
            break
    if pd.isna(points_against) and not manager_matchups.empty:
        opponent_score_col = next(
            (c for c in [
                "opponent_starter_fantasy_points", "opponent_points",
                "opponent_score", "opponent_manager_points",
            ] if c in manager_matchups.columns),
            None,
        )
        if opponent_score_col:
            points_against = pd.to_numeric(
                manager_matchups[opponent_score_col], errors="coerce"
            ).sum(min_count=1)

    # Resolve current streak from analytics when available; otherwise calculate
    # it directly from the latest completed matchup results.
    streak_text = "—"
    if not streaks.empty and "api_team_name" in streaks.columns:
        streak_row = streaks[streaks["api_team_name"].map(clean_display_name).eq(manager)]
        if not streak_row.empty:
            streak_row = streak_row.iloc[0]
            for c in [
                "current_streak", "current_result_streak", "streak_label",
                "active_streak", "current_streak_label",
            ]:
                if c in streak_row.index and pd.notna(streak_row.get(c)):
                    streak_text = str(streak_row.get(c))
                    break
    if streak_text == "—" and not manager_matchups.empty and {"fantrax_gw", "computed_result"}.issubset(manager_matchups.columns):
        streak_source = manager_matchups[["fantrax_gw", "computed_result"]].copy()
        streak_source["fantrax_gw"] = pd.to_numeric(streak_source["fantrax_gw"], errors="coerce")
        streak_source = streak_source.dropna(subset=["fantrax_gw"]).sort_values("fantrax_gw")
        results = [r for r in streak_source["computed_result"].astype(str).str.upper() if r in {"W", "L", "T"}]
        if results:
            current = results[-1]
            length = 1
            for result in reversed(results[:-1]):
                if result != current:
                    break
                length += 1
            streak_text = f"{current}{length}"

    st.markdown(
        f"""
        <div class="manager-hero">
            <div class="manager-hero-grid">
                <div>
                    <div class="section-eyebrow">Manager dashboard</div>
                    <div class="manager-name">{manager}</div>
                    <div class="manager-meta">{selected_season_label} performance profile</div>
                </div>
                <div class="manager-hero-stat">
                    <div class="manager-hero-label">Current Rank</div>
                    <div class="manager-hero-value">{format_value(rank) or '—'}</div>
                </div>
                <div class="manager-hero-stat">
                    <div class="manager-hero-label">Record</div>
                    <div class="manager-hero-value">{record or '—'}</div>
                </div>
                <div class="manager-hero-stat">
                    <div class="manager-hero-label">Current Streak</div>
                    <div class="manager-hero-value">{streak_text}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height: 8px'></div>", unsafe_allow_html=True)

    overview_tab, performance_tab, squad_tab, decisions_tab, explorer_tab = st.tabs(
        ["Overview", "Performance", "Squad", "Decisions", "Explorer"]
    )

    with overview_tab:
        # ------------------------------
        # Overview calculations
        # ------------------------------
        score_series = pd.Series(dtype=float)
        avg_score = pd.NA
        best_week = pd.NA
        lowest_week = pd.NA
        score_sd = pd.NA
        score_cv = pd.NA

        if not manager_scores.empty and "fantrax_gw" in manager_scores.columns:
            manager_scores["fantrax_gw"] = pd.to_numeric(manager_scores["fantrax_gw"], errors="coerce")
            manager_scores = manager_scores.dropna(subset=["fantrax_gw"]).sort_values("fantrax_gw")
            score_col = next((c for c in ["starter_fantasy_points", "starter_points", "fantasy_points"] if c in manager_scores.columns), None)
            if score_col:
                score_series = pd.to_numeric(manager_scores[score_col], errors="coerce")
                avg_score = score_series.mean()
                best_week = score_series.max()
                lowest_week = score_series.min()
                score_sd = score_series.std()
                score_cv = (score_sd / avg_score * 100) if pd.notna(avg_score) and float(avg_score) != 0 else pd.NA

        # Recent form cards
        recent_form = []
        if not manager_matchups.empty and {"fantrax_gw", "computed_result"}.issubset(manager_matchups.columns):
            form = manager_matchups[["fantrax_gw", "computed_result"]].copy()
            form["fantrax_gw"] = pd.to_numeric(form["fantrax_gw"], errors="coerce")
            form["computed_result"] = form["computed_result"].astype(str).str.upper()
            form = form.dropna(subset=["fantrax_gw"]).sort_values("fantrax_gw").tail(8)
            for _, result_row in form.iterrows():
                result = result_row["computed_result"] if result_row["computed_result"] in {"W", "L", "T"} else "T"
                cls = {"W": "form-win", "L": "form-loss", "T": "form-tie"}[result]
                recent_form.append(
                    f'<div class="form-box {cls}">{result}<small>GW {int(result_row["fantrax_gw"])}</small></div>'
                )

        st.markdown('<div class="hub-panel-title">Recent Form</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="hub-panel-copy">Most recent completed league matchups.</div>',
            unsafe_allow_html=True,
        )
        if recent_form:
            st.markdown(f'<div class="form-strip">{"".join(recent_form)}</div>', unsafe_allow_html=True)
        else:
            st.info("No completed matchup form is available.")

        # KPI strip
        k1, k2, k3, k4, k5, k6 = st.columns(6)
        metric_or_blank(k1, "Points For", starter_points)
        metric_or_blank(k2, "Points Against", points_against)
        metric_or_blank(k3, "Average Score", avg_score)
        metric_or_blank(k4, "Best Week", best_week)
        metric_or_blank(k5, "Efficiency %", efficiency)
        metric_or_blank(k6, "Consistency CV %", score_cv)

        # ------------------------------
        # Trends
        # ------------------------------
        st.markdown("### Season Trends")
        chart_left, chart_right = st.columns(2, gap="large")

        with chart_left:
            st.markdown('<div class="hub-panel-title">Weekly Scoring</div>', unsafe_allow_html=True)
            st.markdown('<div class="hub-panel-copy">Selected manager weekly total points and ghost points.</div>', unsafe_allow_html=True)
            if not manager_scores.empty and not score_series.empty:
                score_chart = pd.DataFrame({
                    "Gameweek": pd.to_numeric(manager_scores["fantrax_gw"], errors="coerce"),
                    "Total Weekly Points": pd.to_numeric(score_series, errors="coerce"),
                }).dropna(subset=["Gameweek"]).sort_values("Gameweek")

                manager_ghost = ghost_weekly[
                    ghost_weekly.get("api_team_name", pd.Series(dtype=str)).map(clean_display_name).eq(manager)
                ].copy()
                ghost_gw_col = next((c for c in ["fantrax_gw", "gw", "gameweek"] if c in manager_ghost.columns), None)
                ghost_value_col = next((c for c in [
                    "ghost_points", "total_ghost_points", "weekly_ghost_points",
                    "manager_ghost_points", "ghost_fantasy_points"
                ] if c in manager_ghost.columns), None)

                if ghost_gw_col and ghost_value_col:
                    manager_ghost[ghost_gw_col] = pd.to_numeric(manager_ghost[ghost_gw_col], errors="coerce")
                    manager_ghost[ghost_value_col] = pd.to_numeric(manager_ghost[ghost_value_col], errors="coerce")
                    ghost_by_week = (
                        manager_ghost.dropna(subset=[ghost_gw_col])
                        .groupby(ghost_gw_col, as_index=False)[ghost_value_col]
                        .sum(min_count=1)
                        .rename(columns={ghost_gw_col: "Gameweek", ghost_value_col: "Ghost Points"})
                    )
                    score_chart = score_chart.merge(ghost_by_week, on="Gameweek", how="left")
                else:
                    fallback_ghost_col = next((c for c in [
                        "ghost_points", "total_ghost_points", "weekly_ghost_points"
                    ] if c in manager_scores.columns), None)
                    score_chart["Ghost Points"] = (
                        pd.to_numeric(manager_scores[fallback_ghost_col], errors="coerce").to_numpy()
                        if fallback_ghost_col else pd.NA
                    )

                if PLOTLY_AVAILABLE:
                    fig = go.Figure()
                    fig.add_trace(go.Bar(
                        x=score_chart["Gameweek"],
                        y=score_chart["Total Weekly Points"],
                        name="Total Weekly Points",
                        hovertemplate="GW %{x}<br>Total weekly points: %{y:.1f}<extra></extra>",
                    ))
                    if pd.to_numeric(score_chart["Ghost Points"], errors="coerce").notna().any():
                        fig.add_trace(go.Scatter(
                            x=score_chart["Gameweek"],
                            y=score_chart["Ghost Points"],
                            mode="lines+markers",
                            name="Ghost Points",
                            line=dict(width=3),
                            marker=dict(size=7),
                            hovertemplate="GW %{x}<br>Ghost points: %{y:.1f}<extra></extra>",
                        ))
                    fig.update_layout(
                        height=360,
                        margin=dict(l=10, r=10, t=28, b=10),
                        legend=dict(orientation="h", y=1.16, x=0),
                        xaxis=dict(title="Gameweek", dtick=1, showgrid=False),
                        yaxis=dict(title="Points", rangemode="tozero"),
                        hovermode="x unified",
                        bargap=0.28,
                    )
                    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
                else:
                    chart_cols = [c for c in ["Total Weekly Points", "Ghost Points"] if pd.to_numeric(score_chart[c], errors="coerce").notna().any()]
                    st.line_chart(score_chart.set_index("Gameweek")[chart_cols])
            else:
                st.info("No weekly scoring data found.")

        with chart_right:
            st.markdown('<div class="hub-panel-title">League Position</div>', unsafe_allow_html=True)
            st.markdown('<div class="hub-panel-copy">Official league rank after each completed gameweek.</div>', unsafe_allow_html=True)

            rank_df = pd.DataFrame()
            official_rank_col = next((c for c in ["official_rank", "league_rank", "rank"] if c in manager_scores.columns), None)
            if official_rank_col and "fantrax_gw" in manager_scores.columns:
                rank_df = manager_scores[["fantrax_gw", official_rank_col]].copy()
                rank_df["fantrax_gw"] = pd.to_numeric(rank_df["fantrax_gw"], errors="coerce")
                rank_df[official_rank_col] = pd.to_numeric(rank_df[official_rank_col], errors="coerce")
                rank_df = (
                    rank_df.dropna(subset=["fantrax_gw", official_rank_col])
                    .sort_values("fantrax_gw")
                    .drop_duplicates("fantrax_gw", keep="last")
                    .rename(columns={"fantrax_gw": "Gameweek", official_rank_col: "League Position"})
                )

            # Fallback only when the official weekly rank is unavailable.
            if rank_df.empty:
                rank_history = []
                required = {"fantrax_gw", "api_team_name", "computed_result", "starter_fantasy_points"}
                if not matchup_week.empty and required.issubset(matchup_week.columns):
                    history = matchup_week.copy()
                    history["fantrax_gw"] = pd.to_numeric(history["fantrax_gw"], errors="coerce")
                    history["starter_fantasy_points"] = pd.to_numeric(history["starter_fantasy_points"], errors="coerce").fillna(0)
                    history = history.dropna(subset=["fantrax_gw"])
                    for gw in sorted(history["fantrax_gw"].unique()):
                        upto = history[history["fantrax_gw"] <= gw].copy()
                        result_text = upto["computed_result"].astype(str).str.upper()
                        upto["Wins"] = result_text.eq("W").astype(int)
                        upto["Ties"] = result_text.eq("T").astype(int)
                        upto["Losses"] = result_text.eq("L").astype(int)
                        table = (
                            upto.groupby("api_team_name", as_index=False)
                            .agg(
                                Wins=("Wins", "sum"),
                                Ties=("Ties", "sum"),
                                Losses=("Losses", "sum"),
                                Points=("starter_fantasy_points", "sum"),
                            )
                            .sort_values(["Wins", "Ties", "Points", "api_team_name"], ascending=[False, False, False, True])
                            .reset_index(drop=True)
                        )
                        table["Rank"] = table.index + 1
                        selected = table[table["api_team_name"].map(clean_display_name).eq(manager)]
                        if not selected.empty:
                            rank_history.append({
                                "Gameweek": int(gw),
                                "League Position": int(selected.iloc[0]["Rank"]),
                            })
                if rank_history:
                    rank_df = pd.DataFrame(rank_history)

            if not rank_df.empty:
                rank_df["Gameweek"] = pd.to_numeric(rank_df["Gameweek"], errors="coerce")
                rank_df["League Position"] = pd.to_numeric(rank_df["League Position"], errors="coerce")
                rank_df = rank_df.dropna(subset=["Gameweek", "League Position"]).sort_values("Gameweek")

                # Add the selected manager's cumulative record to each gameweek hover.
                record_df = pd.DataFrame()
                record_required = {"fantrax_gw", "api_team_name", "computed_result"}
                if not matchup_week.empty and record_required.issubset(matchup_week.columns):
                    manager_results = matchup_week[
                        matchup_week["api_team_name"].map(clean_display_name).eq(manager)
                    ][["fantrax_gw", "computed_result"]].copy()
                    manager_results["fantrax_gw"] = pd.to_numeric(manager_results["fantrax_gw"], errors="coerce")
                    manager_results = manager_results.dropna(subset=["fantrax_gw"]).sort_values("fantrax_gw")
                    result_text = manager_results["computed_result"].astype(str).str.upper().str.strip()
                    manager_results["W"] = result_text.eq("W").astype(int)
                    manager_results["L"] = result_text.eq("L").astype(int)
                    manager_results["T"] = result_text.eq("T").astype(int)
                    manager_results[["W", "L", "T"]] = manager_results[["W", "L", "T"]].cumsum()
                    manager_results["Record"] = (
                        manager_results["W"].astype(str) + "-" +
                        manager_results["L"].astype(str) + "-" +
                        manager_results["T"].astype(str)
                    )
                    record_df = (
                        manager_results.groupby("fantrax_gw", as_index=False).last()
                        .rename(columns={"fantrax_gw": "Gameweek"})[["Gameweek", "Record"]]
                    )

                if not record_df.empty:
                    rank_df = rank_df.merge(record_df, on="Gameweek", how="left")
                    rank_df["Record"] = rank_df["Record"].ffill().fillna("—")
                else:
                    rank_df["Record"] = "—"

                # This league has 12 managers. Plot a transformed display value
                # instead of relying on Plotly's reversed-axis behavior. This makes
                # the axis deterministic: rank 12 is always at the bottom and rank 1
                # is always at the top, even if a Plotly version ignores a reversed
                # numeric range.
                league_size = 12
                rank_df["Display Position"] = league_size + 1 - rank_df["League Position"]

                # Render this chart with Streamlit's built-in Vega-Lite engine.
                # The app can run without Plotly installed, which is why earlier
                # Plotly-only axis fixes never appeared in the running dashboard.
                # We plot a transformed position on a normal 1-12 scale and relabel
                # the ticks, guaranteeing rank 1 at the top and rank 12 at the bottom.
                chart_data = rank_df[
                    ["Gameweek", "League Position", "Display Position", "Record"]
                ].copy()
                chart_data["Gameweek"] = chart_data["Gameweek"].astype(int)
                chart_data["League Position"] = chart_data["League Position"].astype(int)
                chart_data["Display Position"] = chart_data["Display Position"].astype(int)

                # Use an ordinal rank axis so Vega-Lite displays every league
                # position explicitly. The domain fixes 1 at the top and 12 at
                # the bottom without relying on a reversed quantitative scale.
                chart_data = rank_df[
                    ["Gameweek", "League Position", "Record"]
                ].copy()
                chart_data["Gameweek"] = chart_data["Gameweek"].astype(int)
                chart_data["League Position"] = chart_data["League Position"].astype(int)

                rank_domain = list(range(1, league_size + 1))
                rank_encoding = {
                    "field": "League Position",
                    "type": "ordinal",
                    "title": "League Position",
                    "scale": {"domain": rank_domain},
                    "axis": {
                        "values": rank_domain,
                        "labelAngle": 0,
                        "grid": True,
                        "tickSize": 4,
                    },
                }

                league_position_spec = {
                    "height": 315,
                    "data": {"values": chart_data.to_dict("records")},
                    "layer": [

                        {
                            "mark": {
                                "type": "line",
                                "interpolate": "step-after",
                                "strokeWidth": 3,
                                "color": "#1f77d0",
                            },
                            "encoding": {
                                "x": {
                                    "field": "Gameweek",
                                    "type": "quantitative",
                                    "title": "Gameweek",
                                    "axis": {"tickMinStep": 1, "grid": False},
                                    "scale": {"zero": False, "nice": False},
                                },
                                "y": rank_encoding,
                                "order": {"field": "Gameweek", "type": "quantitative"},
                            },
                        },
                        {
                            "mark": {
                                "type": "point",
                                "filled": True,
                                "size": 54,
                                "color": "#1f77d0",
                            },
                            "encoding": {
                                "x": {
                                    "field": "Gameweek",
                                    "type": "quantitative",
                                    "title": "Gameweek",
                                    "axis": {"tickMinStep": 1, "grid": False},
                                    "scale": {"zero": False, "nice": False},
                                },
                                "y": rank_encoding,
                                "tooltip": [
                                    {
                                        "field": "Gameweek",
                                        "type": "quantitative",
                                        "title": "GW",
                                        "format": ".0f",
                                    },
                                    {
                                        "field": "League Position",
                                        "type": "ordinal",
                                        "title": "League Position",
                                    },
                                    {
                                        "field": "Record",
                                        "type": "nominal",
                                        "title": "Record",
                                    },
                                ],
                            },
                        },
                    ],
                    "config": {
                        "view": {"stroke": None},
                        "axis": {
                            "labelColor": "#64748b",
                            "titleColor": "#334155",
                            "gridColor": "#e2e8f0",
                        },
                    },
                }

                st.vega_lite_chart(
                    league_position_spec,
                    use_container_width=True,
                    key=f"league_position_v340_{manager}",
                )
            else:
                st.info("League-position history could not be calculated.")

        # ------------------------------
        # Identity metrics
        # ------------------------------
        st.markdown("### Team Identity Metrics")
        st.caption("League-relative descriptive scores. Higher is not always better; each metric describes a management pattern.")

        def percentile_score(values: pd.Series, selected_value: Any, higher_is_better: bool = True) -> int:
            numeric = pd.to_numeric(values, errors="coerce").dropna()
            selected_num = pd.to_numeric(pd.Series([selected_value]), errors="coerce").iloc[0]
            if numeric.empty or pd.isna(selected_num):
                return 0
            pct = float((numeric <= selected_num).mean() * 100)
            if not higher_is_better:
                pct = 100 - pct
            return int(round(max(0, min(100, pct))))

        # Consistency: lower weekly scoring CV is more consistent.
        manager_consistency = {}
        if not manager_week.empty and {"api_team_name", "starter_fantasy_points"}.issubset(manager_week.columns):
            consistency_source = manager_week.copy()
            consistency_source["starter_fantasy_points"] = pd.to_numeric(consistency_source["starter_fantasy_points"], errors="coerce")
            grouped = consistency_source.groupby("api_team_name")["starter_fantasy_points"]
            means = grouped.mean()
            sds = grouped.std()
            cvs = (sds / means.replace(0, pd.NA) * 100).dropna()
            manager_consistency = cvs.to_dict()
        consistency_raw = manager_consistency.get(next((n for n in manager_consistency if clean_display_name(n) == manager), manager), score_cv)
        consistency_score = percentile_score(pd.Series(manager_consistency.values()), consistency_raw, higher_is_better=False)

        # Formation stability: share of weeks using the most common formation.
        formation_stability_by_manager = {}
        if not formation_weekly.empty and "api_team_name" in formation_weekly.columns:
            fcol = next((c for c in ["formation", "formation_label", "starting_formation"] if c in formation_weekly.columns), None)
            gwcol = next((c for c in ["fantrax_gw", "gw", "gameweek"] if c in formation_weekly.columns), None)
            if fcol and gwcol:
                for name, grp in formation_weekly.groupby("api_team_name"):
                    total = grp[gwcol].nunique()
                    top_usage = grp.groupby(fcol)[gwcol].nunique().max() if total else 0
                    formation_stability_by_manager[name] = (top_usage / total * 100) if total else pd.NA
        formation_raw = formation_stability_by_manager.get(next((n for n in formation_stability_by_manager if clean_display_name(n) == manager), manager), pd.NA)
        formation_score = percentile_score(pd.Series(formation_stability_by_manager.values()), formation_raw, higher_is_better=True)

        # Bench efficiency uses lineup efficiency when available.
        efficiency_by_manager = {}
        for c in ["season_efficiency_pct", "efficiency_pct"]:
            if c in profile.columns:
                efficiency_by_manager = dict(zip(profile["api_team_name"], pd.to_numeric(profile[c], errors="coerce")))
                break
        efficiency_raw = efficiency_by_manager.get(next((n for n in efficiency_by_manager if clean_display_name(n) == manager), manager), efficiency)
        bench_score = percentile_score(pd.Series(efficiency_by_manager.values()), efficiency_raw, higher_is_better=True)

        # Transfer and lineup activity are descriptive league-relative percentiles.
        transfer_counts = roster_adds.groupby("api_team_name").size() if not roster_adds.empty and "api_team_name" in roster_adds.columns else pd.Series(dtype=float)
        transfer_raw = next((v for n, v in transfer_counts.items() if clean_display_name(n) == manager), 0)
        transfer_score = percentile_score(transfer_counts, transfer_raw, higher_is_better=True)

        lineup_values = pd.Series(dtype=float)
        lineup_raw = row.get("total_starter_changes", pd.NA)
        if "total_starter_changes" in profile.columns:
            lineup_values = pd.to_numeric(profile["total_starter_changes"], errors="coerce")
        elif not behavior_season.empty:
            lineup_col = next((c for c in ["total_starter_changes", "lineup_changes", "starting_xi_changes"] if c in behavior_season.columns), None)
            if lineup_col:
                lineup_values = pd.to_numeric(behavior_season[lineup_col], errors="coerce")
                selected_behavior = behavior_season[behavior_season.get("api_team_name", pd.Series(dtype=str)).map(clean_display_name).eq(manager)]
                if not selected_behavior.empty:
                    lineup_raw = selected_behavior.iloc[0].get(lineup_col)
        lineup_score = percentile_score(lineup_values, lineup_raw, higher_is_better=True)
        aggressiveness_score = int(round((transfer_score + lineup_score + (100 - formation_score)) / 3))

        identity_specs = [
            ("Consistency", consistency_score, f"Score CV: {format_value(consistency_raw)}% · lower variation ranks higher"),
            ("Formation Stability", formation_score, f"Primary formation usage: {format_value(formation_raw)}%"),
            ("Bench Efficiency", bench_score, f"Optimal-XI efficiency: {format_value(efficiency_raw)}%"),
            ("Transfer Activity", transfer_score, f"Roster adds: {format_value(transfer_raw)}"),
            ("Lineup Activity", lineup_score, f"Starting-XI changes: {format_value(lineup_raw)}"),
            ("Aggressiveness", aggressiveness_score, "Composite of transfers, lineup changes, and formation switching"),
        ]
        id_cols = st.columns(3, gap="large")
        for idx, (label, score, note) in enumerate(identity_specs):
            with id_cols[idx % 3]:
                st.markdown(
                    f'<div class="identity-card"><div class="identity-top">'
                    f'<div class="identity-name">{label}</div><div class="identity-score">{score}</div></div>'
                    f'<div class="identity-track"><div class="identity-fill" style="width:{score}%"></div></div>'
                    f'<div class="identity-note">{note}</div></div>',
                    unsafe_allow_html=True,
                )

        with st.expander("How the identity metrics are calculated"):
            st.markdown(
                """
                **Consistency:** league percentile based on weekly scoring coefficient of variation; lower variation scores higher.  
                **Formation Stability:** percentile of the percentage of gameweeks using the manager's most common formation.  
                **Bench Efficiency:** percentile of optimal-XI efficiency.  
                **Transfer Activity:** percentile of roster-add count.  
                **Lineup Activity:** percentile of starting-XI changes.  
                **Aggressiveness:** combined transfer activity, lineup activity, and formation switching.
                """
            )

        # ------------------------------
        # Highlights and production
        # ------------------------------
        st.markdown("### Season Highlights")
        longest_win = pd.NA
        longest_loss = pd.NA
        if not streaks.empty and "api_team_name" in streaks.columns:
            selected_streak = streaks[streaks["api_team_name"].map(clean_display_name).eq(manager)]
            if not selected_streak.empty:
                sr = selected_streak.iloc[0]
                longest_win = sr.get("longest_win_streak", pd.NA)
                longest_loss = sr.get("longest_losing_streak", pd.NA)

        closest_win = pd.NA
        biggest_win = pd.NA
        closest_win_detail = None
        biggest_win_detail = None
        if not manager_matchups.empty and "computed_result" in manager_matchups.columns:
            wins = manager_matchups[
                manager_matchups["computed_result"].astype(str).str.upper().eq("W")
            ].copy()
            if not wins.empty:
                margin_col = next((c for c in [
                    "point_margin", "margin", "score_margin", "matchup_margin",
                    "margin_points", "absolute_margin", "winning_margin",
                    "difference", "point_difference"
                ] if c in wins.columns), None)
                if margin_col:
                    wins["_win_margin"] = pd.to_numeric(wins[margin_col], errors="coerce").abs()
                else:
                    score_pair = next(((a, b) for a, b in [
                        ("starter_fantasy_points", "opponent_starter_fantasy_points"),
                        ("team_points", "opponent_points"),
                        ("team_score", "opponent_score"),
                        ("score", "opponent_score"),
                        ("manager_points", "opponent_manager_points"),
                    ] if a in wins.columns and b in wins.columns), None)
                    if score_pair:
                        team_score_col, opponent_score_col = score_pair
                        wins["_win_margin"] = (
                            pd.to_numeric(wins[team_score_col], errors="coerce")
                            - pd.to_numeric(wins[opponent_score_col], errors="coerce")
                        ).abs()

                if "_win_margin" in wins.columns:
                    wins = wins.dropna(subset=["_win_margin"])
                    if not wins.empty:
                        closest_row = wins.loc[wins["_win_margin"].idxmin()]
                        biggest_row = wins.loc[wins["_win_margin"].idxmax()]
                        closest_win = closest_row["_win_margin"]
                        biggest_win = biggest_row["_win_margin"]

                        gw_col = next((c for c in ["fantrax_gw", "gw", "gameweek"] if c in wins.columns), None)
                        opponent_col = next((c for c in [
                            "opponent_team_name", "opponent_name",
                            "opponent_name_from_summary", "opponent"
                        ] if c in wins.columns), None)

                        def win_detail(win_row: pd.Series) -> str | None:
                            bits = []
                            if gw_col and pd.notna(win_row.get(gw_col)):
                                try:
                                    bits.append(f"GW {int(float(win_row.get(gw_col)))}")
                                except (TypeError, ValueError):
                                    pass
                            if opponent_col:
                                opponent = clean_display_name(win_row.get(opponent_col, ""))
                                if opponent:
                                    bits.append(f"vs {opponent}")
                            return " · ".join(bits) if bits else None

                        closest_win_detail = win_detail(closest_row)
                        biggest_win_detail = win_detail(biggest_row)

        # Add consistent context beneath every highlight card.
        highest_week_detail = "Highest single-gameweek score"
        lowest_week_detail = "Lowest single-gameweek score"
        if not manager_scores.empty and not score_series.empty:
            valid_scores = pd.DataFrame({
                "Gameweek": pd.to_numeric(manager_scores["fantrax_gw"], errors="coerce"),
                "Score": pd.to_numeric(score_series, errors="coerce"),
            }).dropna()
            if not valid_scores.empty:
                highest_gw = int(valid_scores.loc[valid_scores["Score"].idxmax(), "Gameweek"])
                lowest_gw = int(valid_scores.loc[valid_scores["Score"].idxmin(), "Gameweek"])
                highest_week_detail = f"GW {highest_gw} · highest weekly total"
                lowest_week_detail = f"GW {lowest_gw} · lowest weekly total"

        score_sd_detail = (
            f"{format_value(avg_score)} pts average · {format_value(score_cv)}% CV"
            if pd.notna(avg_score) else "Weekly scoring variability"
        )

        # Calculate the longest winning-streak gameweek span directly from results.
        longest_win_detail = "Consecutive league wins"
        if not manager_matchups.empty and {"fantrax_gw", "computed_result"}.issubset(manager_matchups.columns):
            streak_games = manager_matchups[["fantrax_gw", "computed_result"]].copy()
            streak_games["fantrax_gw"] = pd.to_numeric(streak_games["fantrax_gw"], errors="coerce")
            streak_games = streak_games.dropna(subset=["fantrax_gw"]).sort_values("fantrax_gw")
            best_run: list[int] = []
            current_run: list[int] = []
            for _, streak_game in streak_games.iterrows():
                if str(streak_game["computed_result"]).upper() == "W":
                    current_run.append(int(streak_game["fantrax_gw"]))
                    if len(current_run) > len(best_run):
                        best_run = current_run.copy()
                else:
                    current_run = []
            if best_run:
                longest_win = len(best_run)
                longest_win_detail = (
                    f"GW {best_run[0]}" if len(best_run) == 1
                    else f"GW {best_run[0]}–{best_run[-1]} · consecutive wins"
                )

        h1, h2, h3, h4, h5, h6 = st.columns(6)
        render_context_stat(h1, "Highest Week", best_week, highest_week_detail)
        render_context_stat(h2, "Lowest Week", lowest_week, lowest_week_detail)
        render_context_stat(h3, "Score Std. Dev.", score_sd, score_sd_detail)
        render_context_stat(h4, "Longest Win Streak", longest_win, longest_win_detail)
        render_context_stat(h5, "Closest Win", closest_win, closest_win_detail or "Smallest winning margin")
        render_context_stat(h6, "Biggest Win", biggest_win, biggest_win_detail or "Largest winning margin")

        st.markdown("### Season Production")
        weeks_played = 0
        if not manager_scores.empty and "fantrax_gw" in manager_scores.columns:
            weeks_played = int(pd.to_numeric(manager_scores["fantrax_gw"], errors="coerce").nunique())
        if not weeks_played:
            weeks_played_value = pd.to_numeric(row.get("weeks"), errors="coerce")
            weeks_played = int(weeks_played_value) if pd.notna(weeks_played_value) and weeks_played_value > 0 else 0

        ghost_total = pd.to_numeric(row.get("ghost_points"), errors="coerce")
        goals_total = pd.to_numeric(row.get("total_starter_goals"), errors="coerce")
        assists_total = pd.to_numeric(row.get("total_starter_assists_total"), errors="coerce")
        clean_sheets_total = pd.to_numeric(row.get("total_starter_clean_sheets"), errors="coerce")
        starter_points_num = pd.to_numeric(starter_points, errors="coerce")

        def per_gw_detail(total: Any, suffix: str = "per GW") -> str:
            numeric_total = pd.to_numeric(total, errors="coerce")
            if weeks_played and pd.notna(numeric_total):
                return f"{numeric_total / weeks_played:.1f} {suffix}"
            return "Average per gameweek unavailable"

        ghost_detail_parts = []
        if weeks_played and pd.notna(ghost_total):
            ghost_detail_parts.append(f"{ghost_total / weeks_played:.1f} per GW")
        if pd.notna(ghost_total) and pd.notna(starter_points_num) and float(starter_points_num) != 0:
            ghost_detail_parts.append(f"{ghost_total / starter_points_num * 100:.1f}% of total points")
        ghost_detail = " · ".join(ghost_detail_parts) or "Average and share unavailable"

        p1, p2, p3, p4 = st.columns(4)
        render_context_stat(p1, "Ghost Points", ghost_total, ghost_detail)
        render_context_stat(p2, "Goals", goals_total, per_gw_detail(goals_total))
        render_context_stat(p3, "Assists", assists_total, per_gw_detail(assists_total))
        render_context_stat(p4, "Clean Sheets", clean_sheets_total, per_gw_detail(clean_sheets_total))

    with performance_tab:
        st.markdown("### Performance Analytics")
        st.caption(
            "A deeper view of scoring quality, season momentum, schedule luck, "
            "position production, weekly standing, and matchup context."
        )

        perf_scores = manager_scores.copy()
        perf_score_col = next(
            (c for c in ["starter_fantasy_points", "starter_points", "fantasy_points"] if c in perf_scores.columns),
            None,
        )

        if perf_scores.empty or "fantrax_gw" not in perf_scores.columns or not perf_score_col:
            st.info("No weekly manager summary found.")
        else:
            perf_scores["fantrax_gw"] = pd.to_numeric(perf_scores["fantrax_gw"], errors="coerce")
            perf_scores["Weekly Points"] = pd.to_numeric(perf_scores[perf_score_col], errors="coerce")
            perf_scores = (
                perf_scores.dropna(subset=["fantrax_gw", "Weekly Points"])
                .sort_values("fantrax_gw")
                .drop_duplicates("fantrax_gw", keep="last")
            )

            # League weekly scoring context.
            league_weekly = pd.DataFrame()
            league_score_col = next(
                (c for c in ["starter_fantasy_points", "starter_points", "fantasy_points"] if c in manager_week.columns),
                None,
            )
            if not manager_week.empty and league_score_col and {"fantrax_gw", "api_team_name"}.issubset(manager_week.columns):
                league_weekly = manager_week[["fantrax_gw", "api_team_name", league_score_col]].copy()
                league_weekly["fantrax_gw"] = pd.to_numeric(league_weekly["fantrax_gw"], errors="coerce")
                league_weekly["Score"] = pd.to_numeric(league_weekly[league_score_col], errors="coerce")
                league_weekly = league_weekly.dropna(subset=["fantrax_gw", "Score"])

                weekly_context = (
                    league_weekly.groupby("fantrax_gw", as_index=False)
                    .agg(
                        **{
                            "League Average": ("Score", "mean"),
                            "League Median": ("Score", "median"),
                            "League Teams": ("api_team_name", "nunique"),
                        }
                    )
                )
                perf_scores = perf_scores.merge(weekly_context, on="fantrax_gw", how="left")

                def weekly_percentile(score_row: pd.Series) -> float:
                    week_scores = league_weekly.loc[
                        league_weekly["fantrax_gw"].eq(score_row["fantrax_gw"]), "Score"
                    ].dropna()
                    if week_scores.empty:
                        return float("nan")
                    return float((week_scores <= score_row["Weekly Points"]).mean() * 100)

                perf_scores["Weekly Percentile"] = perf_scores.apply(weekly_percentile, axis=1)
            else:
                perf_scores["League Average"] = pd.NA
                perf_scores["League Median"] = pd.NA
                perf_scores["Weekly Percentile"] = pd.NA

            perf_scores["5-GW Average"] = perf_scores["Weekly Points"].rolling(5, min_periods=1).mean()
            perf_scores["Vs League"] = (
                perf_scores["Weekly Points"]
                - pd.to_numeric(perf_scores["League Average"], errors="coerce")
            )

            avg_score_perf = perf_scores["Weekly Points"].mean()


            # Rank managers by average weekly score.
            avg_score_rank = pd.NA
            manager_average_table = pd.DataFrame()
            if not manager_week.empty and league_score_col and "api_team_name" in manager_week.columns:
                manager_average_table = manager_week.copy()
                manager_average_table[league_score_col] = pd.to_numeric(
                    manager_average_table[league_score_col], errors="coerce"
                )
                manager_average_table = (
                    manager_average_table.groupby("api_team_name", as_index=False)[league_score_col]
                    .mean()
                    .rename(columns={league_score_col: "Average Score"})
                    .sort_values(["Average Score", "api_team_name"], ascending=[False, True])
                    .reset_index(drop=True)
                )
                manager_average_table["Average Score Rank"] = manager_average_table.index + 1
                selected_avg_row = manager_average_table[
                    manager_average_table["api_team_name"].map(clean_display_name).eq(manager)
                ]
                if not selected_avg_row.empty:
                    avg_score_rank = int(selected_avg_row.iloc[0]["Average Score Rank"])

            # Actual record.
            actual_wins = actual_losses = actual_ties = 0
            if not manager_matchups.empty and "computed_result" in manager_matchups.columns:
                result_series = manager_matchups["computed_result"].astype(str).str.upper().str.strip()
                actual_wins = int(result_series.eq("W").sum())
                actual_losses = int(result_series.eq("L").sum())
                actual_ties = int(result_series.eq("T").sum())
            actual_record_text = f"{actual_wins}-{actual_losses}-{actual_ties}"

            # All-play expected wins: compare the selected score against every
            # other manager in every completed week. A tie counts as half a win.
            expected_wins = expected_losses = 0.0
            expected_weeks = 0
            all_play_weekly = []
            if not league_weekly.empty:
                for _, score_row in perf_scores.iterrows():
                    gw = score_row["fantrax_gw"]
                    own_score = score_row["Weekly Points"]
                    opponents = league_weekly[
                        league_weekly["fantrax_gw"].eq(gw)
                        & ~league_weekly["api_team_name"].map(clean_display_name).eq(manager)
                    ]["Score"].dropna()
                    if opponents.empty:
                        continue
                    wins_equivalent = float((own_score > opponents).sum()) + 0.5 * float((own_score == opponents).sum())
                    expected_win_share = wins_equivalent / len(opponents)
                    expected_wins += expected_win_share
                    expected_losses += 1 - expected_win_share
                    expected_weeks += 1
                    all_play_weekly.append({
                        "Gameweek": int(gw),
                        "Expected Win Share": expected_win_share,
                        "All-Play Wins": wins_equivalent,
                        "All-Play Opponents": len(opponents),
                    })

            expected_record_text = (
                f"{expected_wins:.1f}-{expected_losses:.1f}"
                if expected_weeks else "—"
            )
            luck_delta = actual_wins - expected_wins if expected_weeks else pd.NA
            if pd.isna(luck_delta):
                luck_rating = "Unavailable"
            elif luck_delta <= -3:
                luck_rating = "Very Unlucky"
            elif luck_delta <= -1:
                luck_rating = "Unlucky"
            elif luck_delta < 1:
                luck_rating = "Neutral"
            elif luck_delta < 3:
                luck_rating = "Lucky"
            else:
                luck_rating = "Very Lucky"

            # Points-against / schedule rank.
            points_against_rank = pd.NA
            average_opponent_score = pd.NA
            schedule_table = pd.DataFrame()
            matchup_opponent_col = next(
                (c for c in [
                    "opponent_starter_fantasy_points", "opponent_points",
                    "opponent_score", "opponent_manager_points",
                ] if c in matchup_week.columns),
                None,
            )
            if not matchup_week.empty and matchup_opponent_col and "api_team_name" in matchup_week.columns:
                schedule_table = matchup_week[["api_team_name", matchup_opponent_col]].copy()
                schedule_table["Opponent Average"] = pd.to_numeric(
                    schedule_table[matchup_opponent_col], errors="coerce"
                )
                schedule_table = (
                    schedule_table.groupby("api_team_name", as_index=False)["Opponent Average"]
                    .mean()
                    .sort_values(["Opponent Average", "api_team_name"], ascending=[False, True])
                    .reset_index(drop=True)
                )
                schedule_table["Points Against Rank"] = schedule_table.index + 1
                selected_schedule = schedule_table[
                    schedule_table["api_team_name"].map(clean_display_name).eq(manager)
                ]
                if not selected_schedule.empty:
                    average_opponent_score = selected_schedule.iloc[0]["Opponent Average"]
                    points_against_rank = int(selected_schedule.iloc[0]["Points Against Rank"])

            # Summary cards: avoid repeating best/worst week and raw consistency.
            s1, s2, s3, s4 = st.columns(4)
            average_detail = (
                f"#{avg_score_rank} in league"
                if pd.notna(avg_score_rank) else "League rank unavailable"
            )
            render_context_stat(s1, "Average Weekly Score", avg_score_perf, average_detail)
            render_context_stat(
                s2,
                "Actual vs Expected Record",
                actual_record_text,
                f"Expected {expected_record_text} from all-play scoring",
            )
            render_context_stat(
                s3,
                "Luck Rating",
                luck_rating,
                (
                    f"{luck_delta:+.1f} wins versus expectation"
                    if pd.notna(luck_delta) else "Expected record unavailable"
                ),
            )
            render_context_stat(
                s4,
                "Points Against Rank",
                f"#{points_against_rank}" if pd.notna(points_against_rank) else "—",
                (
                    f"{average_opponent_score:.1f} opponent points per week · #1 is hardest"
                    if pd.notna(average_opponent_score) else "Schedule context unavailable"
                ),
            )

            # --------------------------------------------------------------
            # Season momentum
            # --------------------------------------------------------------
            st.markdown("#### Season Momentum")
            st.caption("Weekly scoring, five-gameweek form, and the league scoring baseline.")
            momentum_data = perf_scores[
                ["fantrax_gw", "Weekly Points", "5-GW Average", "League Average"]
            ].rename(columns={"fantrax_gw": "Gameweek"}).copy()
            momentum_long = momentum_data.melt(
                id_vars="Gameweek",
                value_vars=["Weekly Points", "5-GW Average", "League Average"],
                var_name="Series",
                value_name="Points",
            ).dropna(subset=["Points"])
            momentum_spec = {
                "height": 360,
                "data": {"values": momentum_long.to_dict("records")},
                "mark": {"type": "line", "point": True, "strokeWidth": 2.5},
                "encoding": {
                    "x": {
                        "field": "Gameweek", "type": "quantitative", "title": "Gameweek",
                        "axis": {"tickMinStep": 1, "grid": False},
                    },
                    "y": {"field": "Points", "type": "quantitative", "title": "Fantasy Points", "scale": {"zero": False}},
                    "color": {
                        "field": "Series", "type": "nominal", "title": None,
                        "scale": {
                            "domain": ["Weekly Points", "5-GW Average", "League Average"],
                            "range": ["#1f77d0", "#0f3f75", "#94a3b8"],
                        },
                    },
                    "strokeDash": {
                        "field": "Series", "type": "nominal", "title": None,
                        "scale": {
                            "domain": ["Weekly Points", "5-GW Average", "League Average"],
                            "range": [[1, 0], [1, 0], [6, 4]],
                        },
                    },
                    "tooltip": [
                        {"field": "Gameweek", "type": "quantitative", "title": "GW", "format": ".0f"},
                        {"field": "Series", "type": "nominal"},
                        {"field": "Points", "type": "quantitative", "format": ".1f"},
                    ],
                },
                "config": {"view": {"stroke": None}, "legend": {"orient": "top"}},
            }
            st.vega_lite_chart(momentum_spec, use_container_width=True, key=f"performance_momentum_{manager}")

            # Best and worst five-week windows.
            full_windows = perf_scores["Weekly Points"].rolling(5).mean()
            stretch_cols = st.columns(4)
            if full_windows.notna().any():
                best_end_idx = full_windows.idxmax()
                worst_end_idx = full_windows.idxmin()
                best_end_gw = int(perf_scores.loc[best_end_idx, "fantrax_gw"])
                worst_end_gw = int(perf_scores.loc[worst_end_idx, "fantrax_gw"])
                best_start_gw = int(perf_scores.iloc[max(0, perf_scores.index.get_loc(best_end_idx) - 4)]["fantrax_gw"])
                worst_start_gw = int(perf_scores.iloc[max(0, perf_scores.index.get_loc(worst_end_idx) - 4)]["fantrax_gw"])
                render_context_stat(stretch_cols[0], "Best 5-GW Run", full_windows.loc[best_end_idx], f"GW {best_start_gw}–{best_end_gw}")
                render_context_stat(stretch_cols[1], "Worst 5-GW Run", full_windows.loc[worst_end_idx], f"GW {worst_start_gw}–{worst_end_gw}")
            else:
                render_context_stat(stretch_cols[0], "Best 5-GW Run", pd.NA, "Not enough weeks")
                render_context_stat(stretch_cols[1], "Worst 5-GW Run", pd.NA, "Not enough weeks")

            rolling_change = perf_scores["5-GW Average"].diff()
            if rolling_change.notna().any():
                rise_idx = rolling_change.idxmax()
                fall_idx = rolling_change.idxmin()
                render_context_stat(
                    stretch_cols[2], "Biggest Momentum Gain", rolling_change.loc[rise_idx],
                    f"Change entering GW {int(perf_scores.loc[rise_idx, 'fantrax_gw'])}",
                )
                render_context_stat(
                    stretch_cols[3], "Biggest Momentum Drop", rolling_change.loc[fall_idx],
                    f"Change entering GW {int(perf_scores.loc[fall_idx, 'fantrax_gw'])}",
                )
            else:
                render_context_stat(stretch_cols[2], "Biggest Momentum Gain", pd.NA, "Not enough weeks")
                render_context_stat(stretch_cols[3], "Biggest Momentum Drop", pd.NA, "Not enough weeks")

            # --------------------------------------------------------------
            # Luck analysis
            # --------------------------------------------------------------
            st.markdown("#### Luck and Schedule Analysis")
            st.caption("Expected results use an all-play comparison against every other manager each gameweek.")
            luck_cols = st.columns(5)
            render_context_stat(luck_cols[0], "Actual Wins", actual_wins, actual_record_text)
            render_context_stat(luck_cols[1], "Expected Wins", expected_wins, expected_record_text)
            render_context_stat(luck_cols[2], "Luck Differential", luck_delta, "Actual wins minus expected wins")
            render_context_stat(luck_cols[3], "Average Opponent Score", average_opponent_score, "Actual weekly opponents")

            close_record = "0-0-0"
            close_games_count = 0
            if not manager_matchups.empty:
                team_score_col = next(
                    (c for c in ["starter_fantasy_points", "team_points", "team_score", "score"] if c in manager_matchups.columns),
                    None,
                )
                opp_score_col = next(
                    (c for c in ["opponent_starter_fantasy_points", "opponent_points", "opponent_score"] if c in manager_matchups.columns),
                    None,
                )
                if team_score_col and opp_score_col and "computed_result" in manager_matchups.columns:
                    close_work = manager_matchups.copy()
                    close_work["Margin"] = (
                        pd.to_numeric(close_work[team_score_col], errors="coerce")
                        - pd.to_numeric(close_work[opp_score_col], errors="coerce")
                    )
                    close_work = close_work[close_work["Margin"].abs().le(5)]
                    close_games_count = len(close_work)
                    close_results = close_work["computed_result"].astype(str).str.upper()
                    close_record = f"{close_results.eq('W').sum()}-{close_results.eq('L').sum()}-{close_results.eq('T').sum()}"
            render_context_stat(luck_cols[4], "Close-Game Record", close_record, f"{close_games_count} games decided by 5 or fewer")

            # --------------------------------------------------------------
            # Position production
            # --------------------------------------------------------------
            st.markdown("#### Position Scoring Breakdown")
            st.caption("Selected-manager production compared with the league average and league rank at each position.")
            pos_all = pos_season.copy()
            pos_name_col = next((c for c in ["position_group", "position", "scored_position"] if c in pos_all.columns), None)
            pos_points_col = next((c for c in ["fantasy_points", "starter_fantasy_points", "total_fantasy_points"] if c in pos_all.columns), None)
            pos_ghost_col = next((c for c in ["ghost_points", "total_ghost_points"] if c in pos_all.columns), None)
            if pos_all.empty or not pos_name_col or not pos_points_col or "api_team_name" not in pos_all.columns:
                st.info("No position-production data found.")
            else:
                pos_all[pos_points_col] = pd.to_numeric(pos_all[pos_points_col], errors="coerce")
                if pos_ghost_col:
                    pos_all[pos_ghost_col] = pd.to_numeric(pos_all[pos_ghost_col], errors="coerce")

                pos_summary = (
                    pos_all.groupby(["api_team_name", pos_name_col], as_index=False)
                    .agg(
                        Position_Points=(pos_points_col, "sum"),
                        **({"Ghost_Points": (pos_ghost_col, "sum")} if pos_ghost_col else {}),
                    )
                )
                league_pos_context = (
                    pos_summary.groupby(pos_name_col, as_index=False)["Position_Points"]
                    .mean()
                    .rename(columns={"Position_Points": "League Average"})
                )
                pos_summary["Position Rank"] = (
                    pos_summary.groupby(pos_name_col)["Position_Points"]
                    .rank(method="min", ascending=False)
                    .astype("Int64")
                )
                selected_pos = pos_summary[
                    pos_summary["api_team_name"].map(clean_display_name).eq(manager)
                ].merge(league_pos_context, on=pos_name_col, how="left")
                selected_pos["Difference"] = selected_pos["Position_Points"] - selected_pos["League Average"]
                selected_pos = selected_pos.sort_values("Position_Points", ascending=False)

                if selected_pos.empty:
                    st.info("No position-production rows found for this manager.")
                else:
                    pos_chart = selected_pos[[pos_name_col, "Position_Points", "League Average"]].melt(
                        id_vars=pos_name_col,
                        var_name="Series",
                        value_name="Points",
                    )
                    pos_spec = {
                        "height": max(260, 58 * selected_pos[pos_name_col].nunique()),
                        "data": {"values": pos_chart.to_dict("records")},
                        "mark": {"type": "bar", "cornerRadiusEnd": 4},
                        "encoding": {
                            "y": {
                                "field": pos_name_col, "type": "nominal", "title": "Position",
                                "sort": {"field": "Points", "op": "max", "order": "descending"},
                            },
                            "x": {"field": "Points", "type": "quantitative", "title": "Season Fantasy Points"},
                            "yOffset": {"field": "Series"},
                            "color": {
                                "field": "Series", "type": "nominal", "title": None,
                                "scale": {"domain": ["Position_Points", "League Average"], "range": ["#1f77d0", "#94a3b8"]},
                            },
                            "tooltip": [
                                {"field": pos_name_col, "type": "nominal", "title": "Position"},
                                {"field": "Series", "type": "nominal"},
                                {"field": "Points", "type": "quantitative", "format": ".1f"},
                            ],
                        },
                        "config": {"view": {"stroke": None}, "legend": {"orient": "top"}},
                    }
                    st.vega_lite_chart(pos_spec, use_container_width=True, key=f"position_breakdown_{manager}")

                    position_display = selected_pos.rename(columns={
                        pos_name_col: "Position",
                        "Position_Points": "Manager Points",
                        "Ghost_Points": "Ghost Points",
                        "Position Rank": "League Rank",
                    })
                    display_cols = [
                        c for c in ["Position", "Manager Points", "League Average", "Difference", "League Rank", "Ghost Points"]
                        if c in position_display.columns
                    ]
                    for c in ["Manager Points", "League Average", "Difference", "Ghost Points"]:
                        if c in position_display.columns:
                            position_display[c] = pd.to_numeric(position_display[c], errors="coerce").round(1)
                    st.dataframe(position_display[display_cols], use_container_width=True, hide_index=True)

            # --------------------------------------------------------------
            # Weekly percentile and deeper consistency
            # --------------------------------------------------------------
            st.markdown("#### Weekly League Percentile")
            st.caption("How the manager ranked against the entire league each gameweek, independent of the actual opponent.")
            percentile_data = perf_scores[["fantrax_gw", "Weekly Percentile", "Weekly Points"]].dropna(subset=["Weekly Percentile"]).rename(columns={"fantrax_gw": "Gameweek"})
            if percentile_data.empty:
                st.info("Weekly percentile data is unavailable.")
            else:
                percentile_spec = {
                    "height": 285,
                    "data": {"values": percentile_data.to_dict("records")},
                    "mark": {"type": "bar", "cornerRadiusTopLeft": 3, "cornerRadiusTopRight": 3},
                    "encoding": {
                        "x": {"field": "Gameweek", "type": "ordinal", "title": "Gameweek"},
                        "y": {
                            "field": "Weekly Percentile", "type": "quantitative", "title": "League Percentile",
                            "scale": {"domain": [0, 100]},
                            "axis": {"labelExpr": "datum.value + '%'"},
                        },
                        "color": {
                            "condition": {"test": "datum['Weekly Percentile'] >= 50", "value": "#1f77d0"},
                            "value": "#94a3b8",
                        },
                        "tooltip": [
                            {"field": "Gameweek", "type": "ordinal", "title": "GW"},
                            {"field": "Weekly Percentile", "type": "quantitative", "format": ".0f", "title": "Percentile"},
                            {"field": "Weekly Points", "type": "quantitative", "format": ".1f"},
                        ],
                    },
                    "config": {"view": {"stroke": None}},
                }
                st.vega_lite_chart(percentile_spec, use_container_width=True, key=f"weekly_percentile_{manager}")

                percentile_cols = st.columns(4)
                average_percentile = percentile_data["Weekly Percentile"].mean()
                top_quartile_weeks = int(percentile_data["Weekly Percentile"].ge(75).sum())
                bottom_quartile_weeks = int(percentile_data["Weekly Percentile"].le(25).sum())
                above_median_streak = 0
                current_streak = 0
                for value in percentile_data.sort_values("Gameweek")["Weekly Percentile"]:
                    if value >= 50:
                        current_streak += 1
                        above_median_streak = max(above_median_streak, current_streak)
                    else:
                        current_streak = 0
                render_context_stat(percentile_cols[0], "Average Percentile", average_percentile, "Average weekly league standing")
                render_context_stat(percentile_cols[1], "Top-Quartile Weeks", top_quartile_weeks, "75th percentile or higher")
                render_context_stat(percentile_cols[2], "Bottom-Quartile Weeks", bottom_quartile_weeks, "25th percentile or lower")
                render_context_stat(percentile_cols[3], "Longest Above-Median Run", above_median_streak, "Consecutive weeks at 50th percentile or better")

            # --------------------------------------------------------------
            # Matchup context
            # --------------------------------------------------------------
            st.markdown("#### Matchup Context")
            matchup_display = manager_matchups.copy()
            matchup_gw_col = next((c for c in ["fantrax_gw", "gw", "gameweek"] if c in matchup_display.columns), None)
            team_score_col = next((c for c in ["starter_fantasy_points", "team_points", "team_score", "score"] if c in matchup_display.columns), None)
            opponent_score_col = next((c for c in ["opponent_starter_fantasy_points", "opponent_points", "opponent_score"] if c in matchup_display.columns), None)
            opponent_name_col = next((c for c in ["opponent_team_name", "opponent_name", "opponent_name_from_summary"] if c in matchup_display.columns), None)

            if matchup_display.empty or not matchup_gw_col or not team_score_col or not opponent_score_col:
                st.info("Matchup detail is unavailable.")
            else:
                matchup_display["GW"] = pd.to_numeric(matchup_display[matchup_gw_col], errors="coerce").astype("Int64")
                matchup_display["Manager Score"] = pd.to_numeric(matchup_display[team_score_col], errors="coerce")
                matchup_display["Opponent Score"] = pd.to_numeric(matchup_display[opponent_score_col], errors="coerce")
                matchup_display["Margin"] = matchup_display["Manager Score"] - matchup_display["Opponent Score"]
                matchup_display["Result"] = matchup_display.get("computed_result", "")
                matchup_display["Opponent"] = (
                    matchup_display[opponent_name_col].map(clean_display_name)
                    if opponent_name_col else ""
                )
                matchup_display = matchup_display.sort_values("GW")

                matchup_chart_long = matchup_display[["GW", "Manager Score", "Opponent Score"]].melt(
                    id_vars="GW", var_name="Series", value_name="Points"
                )
                matchup_spec = {
                    "height": 300,
                    "data": {"values": matchup_chart_long.to_dict("records")},
                    "mark": {"type": "line", "point": True, "strokeWidth": 2.5},
                    "encoding": {
                        "x": {"field": "GW", "type": "quantitative", "title": "Gameweek", "axis": {"tickMinStep": 1, "grid": False}},
                        "y": {"field": "Points", "type": "quantitative", "title": "Fantasy Points", "scale": {"zero": False}},
                        "color": {"field": "Series", "type": "nominal", "title": None, "scale": {"range": ["#1f77d0", "#94a3b8"]}},
                        "tooltip": [
                            {"field": "GW", "type": "quantitative", "title": "GW", "format": ".0f"},
                            {"field": "Series", "type": "nominal"},
                            {"field": "Points", "type": "quantitative", "format": ".1f"},
                        ],
                    },
                    "config": {"view": {"stroke": None}, "legend": {"orient": "top"}},
                }
                st.vega_lite_chart(matchup_spec, use_container_width=True, key=f"matchup_context_{manager}")
                matchup_table_cols = ["GW", "Opponent", "Manager Score", "Opponent Score", "Margin", "Result"]
                matchup_table = matchup_display[matchup_table_cols].copy()
                for c in ["Manager Score", "Opponent Score", "Margin"]:
                    matchup_table[c] = pd.to_numeric(matchup_table[c], errors="coerce").round(1)
                st.dataframe(matchup_table, use_container_width=True, hide_index=True, height=360)

            # --------------------------------------------------------------
            # Season timeline
            # --------------------------------------------------------------
            st.markdown("#### Season Timeline")
            st.caption("Major season moments across the complete gameweek schedule, shown from left to right.")
            timeline_events = []
            if not perf_scores.empty:
                high_row = perf_scores.loc[perf_scores["Weekly Points"].idxmax()]
                low_row = perf_scores.loc[perf_scores["Weekly Points"].idxmin()]
                timeline_events.append((int(high_row["fantrax_gw"]), "Highest score", f"{high_row['Weekly Points']:.1f} points"))
                timeline_events.append((int(low_row["fantrax_gw"]), "Lowest score", f"{low_row['Weekly Points']:.1f} points"))
                if full_windows.notna().any():
                    timeline_events.append((best_end_gw, "Best five-week run", f"Ended at {full_windows.loc[best_end_idx]:.1f} points per week"))
                    timeline_events.append((worst_end_gw, "Worst five-week run", f"Ended at {full_windows.loc[worst_end_idx]:.1f} points per week"))

            if 'rank_df' in locals() and isinstance(rank_df, pd.DataFrame) and not rank_df.empty:
                timeline_rank = rank_df.sort_values("Gameweek").copy()
                timeline_rank["Is First"] = pd.to_numeric(timeline_rank["League Position"], errors="coerce").eq(1)
                previous_first = False
                for _, timeline_row in timeline_rank.iterrows():
                    is_first = bool(timeline_row["Is First"])
                    gw = int(timeline_row["Gameweek"])
                    if is_first and not previous_first:
                        timeline_events.append((gw, "Entered first place", "Reached the top of the league"))
                    elif previous_first and not is_first:
                        timeline_events.append((gw, "Lost first place", f"Dropped to {int(timeline_row['League Position'])}"))
                    previous_first = is_first

            observed_gws = []
            for timeline_source, timeline_col in [
                (perf_scores, "fantrax_gw"),
                (rank_df if 'rank_df' in locals() else pd.DataFrame(), "Gameweek"),
                (manager_matchups, "fantrax_gw"),
            ]:
                if isinstance(timeline_source, pd.DataFrame) and not timeline_source.empty and timeline_col in timeline_source.columns:
                    observed_gws.extend(pd.to_numeric(timeline_source[timeline_col], errors="coerce").dropna().astype(int).tolist())
            season_end_gw = max([38] + observed_gws) if observed_gws else 38

            if timeline_events:
                timeline_events = sorted(set(timeline_events), key=lambda x: (x[0], x[1]))
                event_weeks = {event[0] for event in timeline_events}
                min_width = max(1050, season_end_gw * 31)
                timeline_html = (
                    f'<div style="overflow-x:auto;padding:120px 10px 105px 10px;margin-bottom:10px;">'
                    f'<div style="position:relative;min-width:{min_width}px;height:82px;">'
                    '<div style="position:absolute;left:0;right:0;top:40px;height:3px;background:#cbd5e1;border-radius:999px;"></div>'
                )
                for gw in range(1, season_end_gw + 1):
                    pct = ((gw - 1) / max(1, season_end_gw - 1)) * 100
                    show_label = gw == 1 or gw == season_end_gw or gw % 5 == 0
                    size = 10 if gw in event_weeks else 6
                    color = "#1f77d0" if gw in event_weeks else "#94a3b8"
                    timeline_html += (
                        f'<span style="position:absolute;left:{pct:.3f}%;top:{40-size/2:.1f}px;transform:translateX(-50%);'
                        f'width:{size}px;height:{size}px;border-radius:999px;background:{color};z-index:2;"></span>'
                    )
                    if show_label:
                        timeline_html += (
                            f'<span style="position:absolute;left:{pct:.3f}%;top:55px;transform:translateX(-50%);'
                            f'font-size:.74rem;color:#64748b;white-space:nowrap;">GW {gw}</span>'
                        )
                for idx, (gw, event_title, event_detail) in enumerate(timeline_events):
                    pct = ((gw - 1) / max(1, season_end_gw - 1)) * 100
                    above = idx % 2 == 0
                    card_top = -96 if above else 70
                    line_top = -10 if above else 42
                    line_height = 50 if above else 28
                    timeline_html += (
                        f'<div style="position:absolute;left:{pct:.3f}%;top:{card_top}px;transform:translateX(-50%);width:170px;'
                        'padding:8px 10px;border:1px solid #dbe3ec;border-radius:10px;background:white;'
                        'box-shadow:0 2px 8px rgba(15,23,42,.08);z-index:3;">'
                        f'<div style="font-size:.70rem;font-weight:800;color:#1f77d0;">GW {gw}</div>'
                        f'<div style="font-size:.82rem;font-weight:800;line-height:1.15;">{event_title}</div>'
                        f'<div style="font-size:.72rem;color:#64748b;line-height:1.2;margin-top:3px;">{event_detail}</div>'
                        '</div>'
                        f'<div style="position:absolute;left:{pct:.3f}%;top:{line_top}px;transform:translateX(-50%);width:1px;'
                        f'height:{line_height}px;background:#94a3b8;"></div>'
                    )
                timeline_html += '</div></div>'
                st.markdown(timeline_html, unsafe_allow_html=True)
            else:
                st.info("No timeline events could be calculated.")

    with decisions_tab:
        st.markdown("### Lineup Decision Analytics")
        st.caption(
            "Compare the lineup that was actually started with the highest-scoring "
            "valid lineup produced by the optimizer."
        )

        # --------------------------------------------------------------
        # Helper functions
        # --------------------------------------------------------------
        def decision_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
            return next((column for column in candidates if column in df.columns), None)

        def decision_bool(series: pd.Series) -> pd.Series:
            return (
                series.astype(str)
                .str.strip()
                .str.lower()
                .isin(["true", "1", "yes", "y", "starter", "selected"])
            )

        def decision_grade(efficiency_value: Any) -> str:
            value = pd.to_numeric(
                pd.Series([efficiency_value]),
                errors="coerce",
            ).iloc[0]

            if pd.isna(value):
                return "—"
            if value >= 97:
                return "A+"
            if value >= 94:
                return "A"
            if value >= 90:
                return "A−"
            if value >= 87:
                return "B+"
            if value >= 84:
                return "B"
            if value >= 80:
                return "B−"
            if value >= 77:
                return "C+"
            if value >= 74:
                return "C"
            if value >= 70:
                return "C−"
            if value >= 65:
                return "D"
            return "F"

        # --------------------------------------------------------------
        # Filter optimizer outputs to the selected manager
        # --------------------------------------------------------------
        manager_decisions = decisions.copy()
        manager_efficiency = efficiency_weekly.copy()

        decisions_manager_col = decision_col(
            manager_decisions,
            [
                "api_team_name",
                "manager_name",
                "team_name",
                "fantasy_team_name",
            ],
        )
        efficiency_manager_col = decision_col(
            manager_efficiency,
            [
                "api_team_name",
                "manager_name",
                "team_name",
                "fantasy_team_name",
            ],
        )

        if decisions_manager_col:
            manager_decisions = manager_decisions[
                manager_decisions[decisions_manager_col]
                .map(clean_display_name)
                .eq(manager)
            ].copy()

        if efficiency_manager_col:
            manager_efficiency = manager_efficiency[
                manager_efficiency[efficiency_manager_col]
                .map(clean_display_name)
                .eq(manager)
            ].copy()

        # --------------------------------------------------------------
        # Resolve expected columns
        # --------------------------------------------------------------
        efficiency_gw_col = decision_col(
            manager_efficiency,
            ["fantrax_gw", "gw", "gameweek"],
        )
        actual_points_col = decision_col(
            manager_efficiency,
            ["actual_starter_points", "actual_points"],
        )
        optimal_points_col = decision_col(
            manager_efficiency,
            ["optimal_lineup_points", "optimal_points"],
        )
        missed_points_col = decision_col(
            manager_efficiency,
            ["missed_points", "points_missed"],
        )
        efficiency_pct_col = decision_col(
            manager_efficiency,
            ["efficiency_pct", "lineup_efficiency_pct"],
        )
        legal_solution_col = decision_col(
            manager_efficiency,
            ["legal_solution_found"],
        )
        pool_size_col = decision_col(
            manager_efficiency,
            ["players_in_pool"],
        )
        rescorable_col = decision_col(
            manager_efficiency,
            ["position_rescorable_players"],
        )

        decision_gw_col = decision_col(
            manager_decisions,
            ["fantrax_gw", "gw", "gameweek"],
        )
        player_name_col = decision_col(
            manager_decisions,
            [
                "display_player_name",
                "player_name",
                "player_full_name",
                "full_name",
                "fantrax_player_name",
                "name",
            ],
        )
        actual_started_col = decision_col(
            manager_decisions,
            ["actual_started"],
        )
        actual_position_col = decision_col(
            manager_decisions,
            ["actual_scored_position"],
        )
        optimal_selected_col = decision_col(
            manager_decisions,
            ["optimal_selected"],
        )
        optimal_position_col = decision_col(
            manager_decisions,
            ["optimal_assigned_position"],
        )
        player_points_col = decision_col(
            manager_decisions,
            ["official_fantasy_points", "fantasy_points"],
        )
        optimal_position_points_col = decision_col(
            manager_decisions,
            ["optimal_position_points"],
        )
        decision_type_col = decision_col(
            manager_decisions,
            ["decision_type"],
        )

        # --------------------------------------------------------------
        # Prepare weekly efficiency table
        # --------------------------------------------------------------
        weekly = pd.DataFrame()

        required_weekly_columns = {
            efficiency_gw_col,
            actual_points_col,
            optimal_points_col,
        }

        if (
            not manager_efficiency.empty
            and None not in required_weekly_columns
        ):
            weekly = manager_efficiency.copy()

            weekly["GW"] = pd.to_numeric(
                weekly[efficiency_gw_col],
                errors="coerce",
            )
            weekly["Actual XI"] = pd.to_numeric(
                weekly[actual_points_col],
                errors="coerce",
            )
            weekly["Optimal XI"] = pd.to_numeric(
                weekly[optimal_points_col],
                errors="coerce",
            )

            if missed_points_col:
                weekly["Points Missed"] = pd.to_numeric(
                    weekly[missed_points_col],
                    errors="coerce",
                )
            else:
                weekly["Points Missed"] = (
                    weekly["Optimal XI"] - weekly["Actual XI"]
                )

            if efficiency_pct_col:
                weekly["Efficiency %"] = pd.to_numeric(
                    weekly[efficiency_pct_col],
                    errors="coerce",
                )
            else:
                weekly["Efficiency %"] = (
                    weekly["Actual XI"]
                    / weekly["Optimal XI"].replace(0, pd.NA)
                    * 100
                )

            weekly["Grade"] = weekly["Efficiency %"].map(decision_grade)

            if legal_solution_col:
                weekly["Valid Optimizer XI"] = weekly[
                    legal_solution_col
                ].map(
                    lambda value: (
                        "Yes"
                        if str(value).strip().lower()
                        in {"true", "1", "yes", "y"}
                        else "No"
                    )
                )
            else:
                weekly["Valid Optimizer XI"] = "—"

            if pool_size_col:
                weekly["Players Available"] = pd.to_numeric(
                    weekly[pool_size_col],
                    errors="coerce",
                )

            if rescorable_col:
                weekly["Position-Rescorable"] = pd.to_numeric(
                    weekly[rescorable_col],
                    errors="coerce",
                )

            weekly = (
                weekly.dropna(subset=["GW"])
                .sort_values("GW")
                .drop_duplicates("GW", keep="last")
            )

        if weekly.empty:
            st.warning(
                "No weekly optimizer records were found for this manager. "
                "Confirm that `manager_efficiency_weekly_v2.csv` exists in "
                "the season's `analytics_views` folder."
            )
        else:
            # ----------------------------------------------------------
            # Season summary cards
            # ----------------------------------------------------------
            actual_total = weekly["Actual XI"].sum(min_count=1)
            optimal_total = weekly["Optimal XI"].sum(min_count=1)
            missed_total = weekly["Points Missed"].sum(min_count=1)
            average_missed = weekly["Points Missed"].mean()

            season_efficiency = (
                actual_total / optimal_total * 100
                if pd.notna(optimal_total) and optimal_total > 0
                else pd.NA
            )
            perfect_weeks = int(

                weekly["Points Missed"].fillna(0).le(0.01).sum()
            )
            season_grade = decision_grade(season_efficiency)

            worst_week_row = weekly.sort_values(
                "Points Missed",
                ascending=False,
            ).iloc[0]

            k1, k2, k3, k4, k5 = st.columns(5)

            render_context_stat(
                k1,
                "Season Efficiency",
                season_efficiency,
                f"Overall grade: {season_grade}",
            )
            render_context_stat(
                k2,
                "Total Points Missed",
                missed_total,
                "Optimal XI minus actual XI",
            )
            render_context_stat(
                k3,
                "Average Missed / GW",
                average_missed,
                "Lower is better",
            )
            render_context_stat(
                k4,
                "Perfect Weeks",
                perfect_weeks,
                f"{perfect_weeks} of {len(weekly)} completed weeks",
            )
            render_context_stat(
                k5,
                "Costliest Week",
                f"GW {int(worst_week_row['GW'])}",
                f"{worst_week_row['Points Missed']:.1f} points missed",
            )

            # ----------------------------------------------------------
            # Actual versus optimal chart
            # ----------------------------------------------------------
            st.markdown("#### Actual XI vs Optimal XI")
            st.caption(
                "The gap between the two lines is the scoring cost of lineup "
                "selection and legal position assignment."
            )

            comparison_chart = weekly[
                ["GW", "Actual XI", "Optimal XI"]
            ].melt(
                id_vars="GW",
                var_name="Lineup",
                value_name="Points",
            )

            if PLOTLY_AVAILABLE:
                figure = go.Figure()

                for lineup_name in ["Actual XI", "Optimal XI"]:
                    lineup_rows = comparison_chart[
                        comparison_chart["Lineup"].eq(lineup_name)
                    ]

                    figure.add_trace(
                        go.Scatter(
                            x=lineup_rows["GW"],
                            y=lineup_rows["Points"],
                            mode="lines+markers",
                            name=lineup_name,
                            line=dict(width=3),
                            marker=dict(size=7),
                            hovertemplate=(
                                "GW %{x:.0f}<br>"
                                + lineup_name
                                + ": %{y:.1f} pts"
                                + "<extra></extra>"
                            ),
                        )
                    )

                figure.update_layout(
                    height=385,
                    margin=dict(l=10, r=10, t=25, b=10),
                    legend=dict(
                        orientation="h",
                        y=1.13,
                        x=0,
                    ),
                    xaxis=dict(
                        title="Gameweek",
                        dtick=1,
                        showgrid=False,
                    ),
                    yaxis=dict(
                        title="Fantasy Points",
                        rangemode="tozero",
                    ),
                    hovermode="x unified",
                )

                st.plotly_chart(
                    figure,
                    use_container_width=True,
                    config={"displayModeBar": False},
                    key=f"decision_actual_optimal_{manager}",
                )
            else:
                st.line_chart(
                    weekly.set_index("GW")[["Actual XI", "Optimal XI"]]
                )

            # ----------------------------------------------------------
            # Weekly decision grade report
            # ----------------------------------------------------------
            st.markdown("#### Weekly Decision Report")

            weekly_report_columns = [
                "GW",
                "Actual XI",
                "Optimal XI",
                "Points Missed",
                "Efficiency %",
                "Grade",
                "Valid Optimizer XI",
                "Players Available",
                "Position-Rescorable",
            ]
            weekly_report_columns = [
                column
                for column in weekly_report_columns
                if column in weekly.columns
            ]

            weekly_report = weekly[weekly_report_columns].copy()

            for column in [
                "Actual XI",
                "Optimal XI",
                "Points Missed",
                "Efficiency %",
            ]:
                if column in weekly_report.columns:
                    weekly_report[column] = pd.to_numeric(
                        weekly_report[column],
                        errors="coerce",
                    ).round(1)

            weekly_report["GW"] = weekly_report["GW"].astype(int)

            st.dataframe(
                weekly_report,
                use_container_width=True,
                hide_index=True,
                height=440,
                column_config={
                    "GW": st.column_config.NumberColumn(
                        "GW",
                        format="%d",
                        width="small",
                    ),
                    "Actual XI": st.column_config.NumberColumn(
                        "Actual XI",
                        format="%.1f",
                    ),
                    "Optimal XI": st.column_config.NumberColumn(
                        "Optimal XI",
                        format="%.1f",
                    ),
                    "Points Missed": st.column_config.NumberColumn(
                        "Missed",
                        format="%.1f",
                    ),
                    "Efficiency %": st.column_config.ProgressColumn(
                        "Efficiency",
                        format="%.1f%%",
                        min_value=0,
                        max_value=100,
                    ),
                    "Grade": st.column_config.TextColumn(
                        "Grade",
                        width="small",
                    ),
                },
            )

            # ----------------------------------------------------------
            # Points-missed chart
            # ----------------------------------------------------------
            st.markdown("#### Weekly Points Missed")

            missed_chart = weekly[
                ["GW", "Points Missed"]
            ].copy()

            if PLOTLY_AVAILABLE:
                missed_figure = go.Figure(
                    go.Bar(
                        x=missed_chart["GW"],
                        y=missed_chart["Points Missed"],
                        name="Points Missed",
                        hovertemplate=(
                            "GW %{x:.0f}<br>"
                            "Points missed: %{y:.1f}"
                            "<extra></extra>"
                        ),
                    )
                )

                missed_figure.update_layout(
                    height=315,
                    margin=dict(l=10, r=10, t=20, b=10),
                    xaxis=dict(
                        title="Gameweek",
                        dtick=1,
                        showgrid=False,
                    ),
                    yaxis=dict(
                        title="Points Missed",
                        rangemode="tozero",
                    ),
                    showlegend=False,
                    bargap=0.25,
                )

                st.plotly_chart(
                    missed_figure,
                    use_container_width=True,
                    config={"displayModeBar": False},
                    key=f"decision_missed_points_{manager}",
                )
            else:
                st.bar_chart(
                    missed_chart.set_index("GW")[["Points Missed"]]
                )

        # --------------------------------------------------------------
        # Player-level optimizer decisions
        # --------------------------------------------------------------
        st.markdown("#### Actual XI and Optimal XI")

        required_detail_columns = [
            decision_gw_col,
            actual_started_col,
            optimal_selected_col,
        ]

        if (
            manager_decisions.empty
            or any(column is None for column in required_detail_columns)
        ):
            st.info(
                "Player-level optimizer decisions are unavailable. Confirm that "
                "`lineup_decision_details_v2.csv` contains the manager, gameweek, "
                "`actual_started`, and `optimal_selected` fields."
            )
        else:
            detail = manager_decisions.copy()

            detail["GW"] = pd.to_numeric(
                detail[decision_gw_col],
                errors="coerce",
            )
            detail["_actual_started"] = decision_bool(
                detail[actual_started_col]
            )
            detail["_optimal_selected"] = decision_bool(
                detail[optimal_selected_col]
            )

            if player_points_col:
                detail["_player_points"] = pd.to_numeric(
                    detail[player_points_col],
                    errors="coerce",
                )
            else:
                detail["_player_points"] = pd.NA

            if optimal_position_points_col:
                detail["_optimal_points"] = pd.to_numeric(
                    detail[optimal_position_points_col],
                    errors="coerce",
                )
            else:
                detail["_optimal_points"] = detail["_player_points"]

            detail = detail.dropna(subset=["GW"]).copy()

            available_gameweeks = sorted(
                detail["GW"].dropna().astype(int).unique(),
                reverse=True,
            )

            selected_decision_gw = st.selectbox(
                "Inspect gameweek",
                available_gameweeks,
                index=0,
                key=f"decision_gameweek_{manager}",
            )

            selected_detail = detail[
                detail["GW"].eq(selected_decision_gw)
            ].copy()

            actual_xi = selected_detail[
                selected_detail["_actual_started"]
            ].copy()
            optimal_xi = selected_detail[
                selected_detail["_optimal_selected"]
            ].copy()

            actual_display = pd.DataFrame()
            optimal_display = pd.DataFrame()

            if player_name_col:
                actual_display["Player"] = actual_xi[
                    player_name_col
                ].astype(str)
                optimal_display["Player"] = optimal_xi[
                    player_name_col
                ].astype(str)
            else:
                actual_display["Player"] = actual_xi.index.astype(str)
                optimal_display["Player"] = optimal_xi.index.astype(str)

            actual_display["Position"] = (
                actual_xi[actual_position_col].astype(str).values
                if actual_position_col
                else "—"
            )
            actual_display["Points"] = (
                actual_xi["_player_points"].values
            )

            optimal_display["Position"] = (
                optimal_xi[optimal_position_col].astype(str).values
                if optimal_position_col
                else "—"
            )
            optimal_display["Points"] = (
                optimal_xi["_optimal_points"].values
            )

            actual_display["Points"] = pd.to_numeric(
                actual_display["Points"],
                errors="coerce",
            ).round(1)
            optimal_display["Points"] = pd.to_numeric(
                optimal_display["Points"],
                errors="coerce",
            ).round(1)

            xi_left, xi_right = st.columns(2, gap="large")

            with xi_left:
                st.markdown("##### Actual Starting XI")
                st.dataframe(
                    actual_display.sort_values(
                        ["Position", "Points"],
                        ascending=[True, False],
                    ),
                    use_container_width=True,
                    hide_index=True,
                    height=420,
                )
                st.metric(
                    "Actual XI points",
                    format_value(actual_display["Points"].sum()),
                )

            with xi_right:
                st.markdown("##### Optimizer Starting XI")
                st.dataframe(
                    optimal_display.sort_values(
                        ["Position", "Points"],
                        ascending=[True, False],
                    ),
                    use_container_width=True,
                    hide_index=True,
                    height=420,
                )
                st.metric(
                    "Optimal XI points",
                    format_value(optimal_display["Points"].sum()),
                )

            # ----------------------------------------------------------
            # Recommended changes
            # ----------------------------------------------------------
            st.markdown("#### Recommended Changes")
            st.caption(
                "Players marked as missed bench starts belong in the optimizer XI. "
                "Players marked should have sat were started but excluded from it."
            )

            if decision_type_col:
                decision_types = (

                    selected_detail[decision_type_col]
                    .fillna("")
                    .astype(str)
                    .str.strip()
                    .str.lower()
                )
            else:
                decision_types = pd.Series(
                    "",
                    index=selected_detail.index,
                )

            missed_bench = selected_detail[
                decision_types.eq("missed_bench_start")
                | (
                    ~selected_detail["_actual_started"]
                    & selected_detail["_optimal_selected"]
                )
            ].copy()

            should_sit = selected_detail[
                decision_types.eq("should_have_sat")
                | (
                    selected_detail["_actual_started"]
                    & ~selected_detail["_optimal_selected"]
                )
            ].copy()

            recommendation_rows = []

            position_values = set()

            if optimal_position_col and not missed_bench.empty:
                position_values.update(
                    missed_bench[optimal_position_col]
                    .dropna()
                    .astype(str)
                    .tolist()
                )

            if actual_position_col and not should_sit.empty:
                position_values.update(
                    should_sit[actual_position_col]
                    .dropna()
                    .astype(str)
                    .tolist()
                )

            for position in sorted(position_values):
                incoming = (
                    missed_bench[
                        missed_bench[optimal_position_col]
                        .astype(str)
                        .eq(position)
                    ].copy()
                    if optimal_position_col
                    else missed_bench.copy()
                )
                outgoing = (
                    should_sit[
                        should_sit[actual_position_col]
                        .astype(str)
                        .eq(position)
                    ].copy()
                    if actual_position_col
                    else should_sit.copy()
                )

                incoming = incoming.sort_values(
                    "_optimal_points",
                    ascending=False,
                )
                outgoing = outgoing.sort_values(
                    "_player_points",
                    ascending=True,
                )

                pair_count = min(len(incoming), len(outgoing))

                for pair_index in range(pair_count):
                    incoming_row = incoming.iloc[pair_index]
                    outgoing_row = outgoing.iloc[pair_index]

                    incoming_name = (
                        incoming_row.get(player_name_col, "Unknown")
                        if player_name_col
                        else "Unknown"
                    )
                    outgoing_name = (
                        outgoing_row.get(player_name_col, "Unknown")
                        if player_name_col
                        else "Unknown"
                    )

                    incoming_points = pd.to_numeric(
                        pd.Series(
                            [incoming_row.get("_optimal_points")]
                        ),
                        errors="coerce",
                    ).iloc[0]
                    outgoing_points = pd.to_numeric(
                        pd.Series(
                            [outgoing_row.get("_player_points")]
                        ),
                        errors="coerce",
                    ).iloc[0]

                    projected_gain = (
                        incoming_points - outgoing_points
                        if pd.notna(incoming_points)
                        and pd.notna(outgoing_points)
                        else pd.NA
                    )

                    recommendation_rows.append(
                        {
                            "Position": position,
                            "Start": incoming_name,
                            "Start Points": incoming_points,
                            "Sit": outgoing_name,
                            "Sit Points": outgoing_points,
                            "Projected Gain": projected_gain,
                        }
                    )

            recommendations = pd.DataFrame(recommendation_rows)

            if recommendations.empty:
                if missed_bench.empty and should_sit.empty:
                    st.success(
                        "The actual starting XI matched the optimizer XI for "
                        f"GW {selected_decision_gw}."
                    )
                else:
                    st.info(
                        "The optimizer identified differences, but they could "
                        "not be paired into direct same-position swaps."
                    )

                    detail_difference_columns = [
                        column
                        for column in [
                            player_name_col,
                            decision_type_col,
                            actual_started_col,
                            actual_position_col,
                            optimal_selected_col,
                            optimal_position_col,
                            player_points_col,
                            optimal_position_points_col,
                        ]
                        if column
                    ]

                    st.dataframe(
                        selected_detail[
                            detail_difference_columns
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )
            else:
                for numeric_column in [
                    "Start Points",
                    "Sit Points",
                    "Projected Gain",
                ]:
                    recommendations[numeric_column] = pd.to_numeric(
                        recommendations[numeric_column],
                        errors="coerce",
                    ).round(1)

                st.dataframe(
                    recommendations.sort_values(
                        "Projected Gain",
                        ascending=False,
                    ),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Projected Gain": st.column_config.NumberColumn(
                            "Projected Gain",
                            format="+%.1f",
                        ),
                    },
                )

            # ----------------------------------------------------------
            # Decision-type and position summaries
            # ----------------------------------------------------------
            summary_left, summary_right = st.columns(2, gap="large")

            with summary_left:
                st.markdown("#### Decision Breakdown")

                if decision_type_col:
                    decision_summary = (
                        detail.groupby(decision_type_col)
                        .size()
                        .reset_index(name="Player-Weeks")
                        .rename(
                            columns={
                                decision_type_col: "Decision Type"
                            }
                        )
                    )

                    decision_summary["Decision Type"] = (
                        decision_summary["Decision Type"]
                        .astype(str)
                        .str.replace("_", " ", regex=False)
                        .str.title()
                    )

                    st.dataframe(
                        decision_summary.sort_values(
                            "Player-Weeks",
                            ascending=False,
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.info("No decision-type field was found.")

            with summary_right:
                st.markdown("#### Missed Points by Position")

                position_summary_source = detail[
                    ~detail["_actual_started"]
                    & detail["_optimal_selected"]
                ].copy()

                if (
                    not position_summary_source.empty
                    and optimal_position_col
                ):
                    position_summary_source["Missed Points"] = (
                        pd.to_numeric(
                            position_summary_source[
                                "_optimal_points"
                            ],
                            errors="coerce",
                        )
                    )

                    position_summary = (
                        position_summary_source.groupby(
                            optimal_position_col,
                            as_index=False,
                        )
                        .agg(
                            Missed_Starts=(
                                optimal_position_col,
                                "size",
                            ),
                            Missed_Points=(
                                "Missed Points",
                                "sum",
                            ),
                        )
                        .rename(
                            columns={
                                optimal_position_col: "Position",
                                "Missed_Starts": "Missed Starts",
                                "Missed_Points": "Missed Points",
                            }
                        )
                        .sort_values(
                            "Missed Points",
                            ascending=False,
                        )
                    )

                    position_summary["Missed Points"] = (
                        position_summary["Missed Points"].round(1)
                    )

                    st.dataframe(
                        position_summary,
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.info(
                        "No missed bench starts were available for the "
                        "position summary."
                    )

            # ----------------------------------------------------------
            # Full player-level decision log
            # ----------------------------------------------------------
            with st.expander("Full Player-Level Decision Log"):
                log_columns = [
                    column
                    for column in [
                        decision_gw_col,
                        player_name_col,
                        actual_started_col,
                        actual_position_col,
                        optimal_selected_col,
                        optimal_position_col,
                        player_points_col,
                        optimal_position_points_col,
                        decision_type_col,
                    ]
                    if column
                ]

                decision_log = detail[log_columns].copy()

                rename_columns = {
                    decision_gw_col: "GW",
                    player_name_col: "Player",
                    actual_started_col: "Actually Started",
                    actual_position_col: "Actual Position",
                    optimal_selected_col: "Optimal XI",
                    optimal_position_col: "Optimal Position",
                    player_points_col: "Official Points",
                    optimal_position_points_col: "Optimal-Position Points",
                    decision_type_col: "Decision Type",
                }

                decision_log = decision_log.rename(
                    columns={
                        key: value
                        for key, value in rename_columns.items()
                        if key
                    }
                )

                st.dataframe(
                    decision_log.sort_values(
                        ["GW", "Decision Type"]
                        if "Decision Type" in decision_log.columns
                        else ["GW"],
                        ascending=[False, True]
                        if "Decision Type" in decision_log.columns
                        else [False],
                    ),
                    use_container_width=True,
                    hide_index=True,
                    height=600,
                )
                
    with squad_tab:
        st.markdown("### Squad")
        st.caption("Every player owned, when they were owned, and what they contributed while on the roster.")
        mpw = _manager_rows(player_week)

        def _sq_col(candidates, contains_all=None, excludes=None):
            return _first_col(mpw, candidates, contains_all=contains_all, excludes=excludes)

        if mpw.empty:
            st.info("No manager-player weekly rows were found for this manager.")
        else:
            name_col = _sq_col(["display_player_name", "player_name", "player_full_name", "full_name", "fantrax_player_name", "api_player_name", "name", "player"], contains_all=["player", "name"], excludes=["team", "manager"])
            gw_col = _sq_col(["fantrax_gw", "gw", "gameweek", "period"])
            points_col = _sq_col(["fantasy_points", "fpts", "score", "total_points", "player_fantasy_points"])
            ghost_col = _sq_col(["ghost_points", "total_ghost_points", "ghost_fantasy_points"])
            pos_col = _sq_col(["position_group", "position", "scored_position", "eligible_positions"])
            status_col = _sq_col(["roster_status", "status", "lineup_status"])
            starter_col = _sq_col(["is_starter", "starter", "actual_started"])

            if not name_col:
                st.warning("The player-week file loaded, but no player-name column could be identified.")
                with st.expander("Available columns"):
                    st.write(list(mpw.columns))
            else:
                mpw[name_col] = mpw[name_col].fillna("Unknown player").astype(str)
                if gw_col:
                    mpw[gw_col] = pd.to_numeric(mpw[gw_col], errors="coerce")
                if points_col:
                    mpw[points_col] = pd.to_numeric(mpw[points_col], errors="coerce").fillna(0)
                else:
                    mpw["_points"] = 0.0
                    points_col = "_points"
                if ghost_col:
                    mpw[ghost_col] = pd.to_numeric(mpw[ghost_col], errors="coerce").fillna(0)
                if starter_col:
                    start_mask = mpw[starter_col].astype(str).str.lower().str.strip().isin(["1", "true", "starter", "start", "active", "starting"])
                elif status_col:
                    start_mask = mpw[status_col].astype(str).str.lower().str.strip().isin(["starter", "start", "active", "starting"])
                else:
                    start_mask = pd.Series(False, index=mpw.index)
                mpw = mpw.assign(_start=start_mask.astype(int), _starter_points=mpw[points_col].where(start_mask, 0), _bench_points=mpw[points_col].where(~start_mask, 0))

                agg_spec = {
                    "Weeks Owned": (gw_col, "nunique") if gw_col else (points_col, "size"),
                    "Starts": ("_start", "sum"),
                    "Starter Points": ("_starter_points", "sum"),
                    "Bench Points": ("_bench_points", "sum"),
                    "Total Points While Owned": (points_col, "sum"),
                    "Average Points": (points_col, "mean"),
                }
                if gw_col:
                    agg_spec["First GW"] = (gw_col, "min")
                    agg_spec["Last GW"] = (gw_col, "max")
                if ghost_col:
                    agg_spec["Ghost Points"] = (ghost_col, "sum")

                squad_summary = mpw.groupby(name_col, as_index=False).agg(**agg_spec)
                if pos_col:
                    pos_lookup = mpw.groupby(name_col)[pos_col].agg(lambda x: x.dropna().astype(str).mode().iloc[0] if not x.dropna().empty else "—")
                    squad_summary.insert(1, "Position", squad_summary[name_col].map(pos_lookup))
                total_starter = squad_summary["Starter Points"].sum()
                squad_summary["Share of Team Scoring %"] = squad_summary["Starter Points"] / total_starter * 100 if total_starter else 0
                squad_summary = squad_summary.sort_values(["Starter Points", "Weeks Owned"], ascending=False)

                sh1, sh2, sh3, sh4 = st.columns(4)
                top_player = squad_summary.iloc[0] if not squad_summary.empty else pd.Series(dtype=object)
                render_context_stat(sh1, "Top Contributor", top_player.get(name_col, "—"), f"{top_player.get('Starter Points', 0):.1f} starter points" if not top_player.empty else "")
                render_context_stat(sh2, "Most Starts", squad_summary.sort_values("Starts", ascending=False).iloc[0][name_col], f"{int(squad_summary['Starts'].max())} starts")
                render_context_stat(sh3, "Players Used", squad_summary[name_col].nunique(), "Appeared on the roster")
                render_context_stat(sh4, "Top 3 Scoring Share", squad_summary.head(3)["Starter Points"].sum() / total_starter * 100 if total_starter else pd.NA, "Share of starter scoring")

                st.markdown("#### Contribution Leaderboard")
                st.bar_chart(squad_summary.head(15).set_index(name_col)[["Starter Points"]])
                st.dataframe(squad_summary.round(1), use_container_width=True, hide_index=True, height=430)

                st.markdown("#### Ownership Timeline")
                if gw_col:
                    timeline_rows = mpw[[name_col, gw_col]].dropna().drop_duplicates().sort_values([name_col, gw_col])
                    player_filter = st.multiselect("Filter timeline by player", squad_summary[name_col].tolist(), default=[], key="squad_timeline_players")
                    if player_filter:
                        timeline_rows = timeline_rows[timeline_rows[name_col].isin(player_filter)]
                    timeline_spec = {
                        "height": max(220, min(760, int(timeline_rows[name_col].nunique()) * 22)),
                        "data": {"values": timeline_rows.rename(columns={name_col: "Player", gw_col: "GW"}).to_dict("records")},
                        "mark": {"type": "tick", "thickness": 12, "size": 18},
                        "encoding": {
                            "x": {"field": "GW", "type": "quantitative", "title": "Gameweek", "axis": {"tickMinStep": 1, "grid": False}},
                            "y": {"field": "Player", "type": "nominal", "sort": "-x", "title": None},
                            "tooltip": [{"field": "Player"}, {"field": "GW", "type": "quantitative", "format": ".0f"}],
                        },
                        "config": {"view": {"stroke": None}},
                    }
                    st.vega_lite_chart(timeline_spec, use_container_width=True, key=f"ownership_timeline_{manager}")
                else:
                    st.info("A gameweek column is required for the ownership timeline.")

                st.markdown("#### Player Detail")
                selected_player = st.selectbox("Player", squad_summary[name_col].tolist(), key="manager_squad_player_detail")
                ps = mpw[mpw[name_col].eq(selected_player)].copy()
                if gw_col:
                    ps = ps.sort_values(gw_col)
                pd1, pd2, pd3, pd4 = st.columns(4)
                render_context_stat(pd1, "Weeks Owned", ps[gw_col].nunique() if gw_col else len(ps), "Rostered gameweeks")
                render_context_stat(pd2, "Starts", int(ps["_start"].sum()), "Starting lineup appearances")
                render_context_stat(pd3, "Starter Points", ps["_starter_points"].sum(), "Points counted toward team total")
                render_context_stat(pd4, "Bench Points", ps["_bench_points"].sum(), "Points scored while benched")
                if gw_col:
                    detail_chart = ps[[gw_col, points_col, "_start"]].rename(columns={gw_col: "GW", points_col: "Points", "_start": "Started"})
                    st.line_chart(detail_chart.set_index("GW")[["Points"]])
                detail_cols = list(
                    dict.fromkeys(
                        c
                        for c in [
                            gw_col,
                            name_col,
                            pos_col,
                            points_col,
                            ghost_col,
                            starter_col,
                            status_col,
                            "goals",
                            "assists",
                            "clean_sheets",
                            "minutes",
                        ]
                        if c and c in ps.columns
                    )
                )
                st.dataframe(ps[detail_cols] if detail_cols else ps, use_container_width=True, hide_index=True, height=360)

    with explorer_tab:
        st.markdown("### Explorer")
        st.caption("Build a custom manager, player, formation, matchup, or transaction query.")

        # Explorer intentionally allows league-wide comparisons rather than only the selected manager.
        level = st.selectbox("Analysis level", ["Players", "Managers", "Manager-Player Ownership", "Gameweeks", "Matchups", "Formations", "Transactions"], key="explorer_level")
        all_player_weeks = player_week.copy()
        all_manager_weeks = manager_week.copy()
        all_matchups = matchup_week.copy()
        all_formations = formation_weekly.copy()
        all_transactions = roster_adds.copy()

        level_data = {
            "Players": all_player_weeks,
            "Managers": all_manager_weeks,
            "Manager-Player Ownership": all_player_weeks,
            "Gameweeks": all_manager_weeks,
            "Matchups": all_matchups,
            "Formations": all_formations,
            "Transactions": all_transactions,
        }
        explore = level_data[level].copy()
        if explore.empty:
            st.info("No rows are available for this analysis level.")
        else:
            def _ex_col(candidates):
                return next((c for c in candidates if c in explore.columns), None)

            ex_manager = _ex_col(["api_team_name", "manager_name", "team_name"])
            ex_player = _ex_col(["display_player_name", "player_name", "name"])
            ex_pos = _ex_col(["position_group", "position", "scored_position", "eligible_positions"])
            ex_club = _ex_col(["club", "team", "epl_team", "squad"])
            ex_gw = _ex_col(["fantrax_gw", "gw", "gameweek", "period"])
            ex_formation = _ex_col(["formation", "formation_label", "starting_formation"])
            ex_status = _ex_col(["roster_status", "lineup_status", "status"])

            fcol1, fcol2, fcol3 = st.columns(3)
            with fcol1:
                if ex_manager:
                    manager_options = sorted(explore[ex_manager].dropna().map(clean_display_name).unique())
                    selected_managers = st.multiselect("Managers", manager_options, default=[manager] if manager in manager_options else [], key="explorer_managers")
                    if selected_managers:
                        explore = explore[explore[ex_manager].map(clean_display_name).isin(selected_managers)]
                if ex_pos:
                    pos_options = sorted(explore[ex_pos].dropna().astype(str).unique())
                    selected_positions = st.multiselect("Positions", pos_options, key="explorer_positions")
                    if selected_positions:
                        explore = explore[explore[ex_pos].astype(str).isin(selected_positions)]
            with fcol2:
                if ex_player:
                    player_options = sorted(explore[ex_player].dropna().astype(str).unique())
                    selected_players = st.multiselect("Players", player_options, key="explorer_players")
                    if selected_players:
                        explore = explore[explore[ex_player].astype(str).isin(selected_players)]
                if ex_club:
                    club_options = sorted(explore[ex_club].dropna().astype(str).unique())
                    selected_clubs = st.multiselect("EPL Clubs", club_options, key="explorer_clubs")
                    if selected_clubs:
                        explore = explore[explore[ex_club].astype(str).isin(selected_clubs)]
            with fcol3:
                if ex_gw:
                    explore[ex_gw] = pd.to_numeric(explore[ex_gw], errors="coerce")
                    valid_gws = explore[ex_gw].dropna()
                    if not valid_gws.empty:
                        gw_min, gw_max = int(valid_gws.min()), int(valid_gws.max())
                        chosen_range = st.slider("Gameweek range", gw_min, gw_max, (gw_min, gw_max), key="explorer_gw_range")
                        explore = explore[explore[ex_gw].between(*chosen_range)]
                if ex_formation:
                    formations = sorted(explore[ex_formation].dropna().astype(str).unique())
                    selected_forms = st.multiselect("Formations", formations, key="explorer_formations")
                    if selected_forms:
                        explore = explore[explore[ex_formation].astype(str).isin(selected_forms)]
                if ex_status:
                    statuses = sorted(explore[ex_status].dropna().astype(str).unique())
                    selected_status = st.multiselect("Lineup / Roster Status", statuses, key="explorer_status")
                    if selected_status:
                        explore = explore[explore[ex_status].astype(str).isin(selected_status)]

            numeric_candidates = []
            for c in explore.columns:
                converted = pd.to_numeric(explore[c], errors="coerce")
                if converted.notna().sum() >= max(2, int(len(explore) * 0.25)):
                    numeric_candidates.append(c)
            if not numeric_candidates:
                st.info("No numeric metrics are available after filtering.")
                metric = None
            else:
                metric = st.selectbox("Metric", numeric_candidates, key="explorer_metric")
                explore[metric] = pd.to_numeric(explore[metric], errors="coerce")

            group_candidates = [c for c in [ex_player, ex_manager, ex_pos, ex_gw, ex_formation, ex_club] if c]
            group_by = st.selectbox("Group by", ["None"] + group_candidates, key="explorer_group_by")
            aggregation = st.selectbox("Calculation", ["Total", "Average", "Median", "Maximum", "Count"], key="explorer_aggregation")

            result = explore.copy()
            if metric:
                agg_map = {"Total": "sum", "Average": "mean", "Median": "median", "Maximum": "max", "Count": "count"}
                if group_by != "None":
                    result = explore.groupby(group_by, as_index=False)[metric].agg(agg_map[aggregation])
                    result = result.sort_values(metric, ascending=False)
                else:
                    vals = explore[metric].dropna()
                    summary_value = {"Total": vals.sum(), "Average": vals.mean(), "Median": vals.median(), "Maximum": vals.max(), "Count": vals.count()}[aggregation]
                    result = pd.DataFrame({"Calculation": [aggregation], metric: [summary_value]})

                x1, x2, x3, x4 = st.columns(4)
                render_context_stat(x1, "Rows", len(explore), "After all filters")
                render_context_stat(x2, "Total", explore[metric].sum(min_count=1), metric)
                render_context_stat(x3, "Average", explore[metric].mean(), metric)
                render_context_stat(x4, "Maximum", explore[metric].max(), metric)

                if group_by != "None" and len(result) > 1:
                    chart_result = result.head(30).copy()
                    if group_by == ex_gw:
                        st.line_chart(chart_result.set_index(group_by)[[metric]])
                    else:
                        st.bar_chart(chart_result.set_index(group_by)[[metric]])

            st.markdown("#### Results")
            st.dataframe(result, use_container_width=True, hide_index=True, height=500)
            st.download_button(
                "Download Results CSV",
                data=result.to_csv(index=False).encode("utf-8-sig"),
                file_name=f"fantrax_explorer_{level.lower().replace(' ', '_')}.csv",
                mime="text/csv",
                key="manager_explorer_download_v36",
            )
