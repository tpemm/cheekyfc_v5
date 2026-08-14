"""Award Detail page backed by the foundation data services."""

from __future__ import annotations

from typing import Any

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


DATASET_KEYS: tuple[str, ...] = (
    "weekly_awards",
    "award_leaderboards",
    "manager_streaks",
    "closest_games",
    "biggest_blowouts",
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
    return result.data.copy() if isinstance(result.data, pd.DataFrame) else pd.DataFrame()


def render(
    season_id: str,
    *,
    data_manager: DataManager | None = None,
    season_manager: SeasonManager | None = None,
    ui: Any = st,
) -> None:
    """Render the existing Award Detail workflow."""

    seasons = season_manager or SeasonManager()
    season = seasons.context(season_id)
    namespace = seasons.resolve_namespace(season.season_id)
    data = data_manager or DataManager(season_manager=seasons)
    st = ui

    st.markdown('<div class="section-eyebrow">League honors</div><div class="section-title">Award Detail</div><div class="section-copy">Explore season leaderboards and weekly award history.</div>', unsafe_allow_html=True)
    frames = {
        key: _load_frame(data, key, season.season_id, namespace, ui)
        for key in DATASET_KEYS
    }
    weekly_awards = frames["weekly_awards"]
    leaderboards = frames["award_leaderboards"]
    detail_streaks = frames["manager_streaks"]
    detail_closest = frames["closest_games"]
    detail_blowouts = frames["biggest_blowouts"]

    synthetic_frames = []
    for special_name in [
        "Biggest Blowout", "Closest Game",
        "Longest Win Streak", "Longest Losing Streak",
    ]:
        special = _build_special_award_leaderboard(
            special_name,
            leaderboards,
            detail_streaks,
            detail_closest,
            detail_blowouts,
        )
        if not special.empty and (
            leaderboards.empty
            or "award_name" not in leaderboards.columns
            or not leaderboards["award_name"].eq(special_name).any()
        ):
            synthetic_frames.append(special)
    if synthetic_frames:
        leaderboards = pd.concat([leaderboards, *synthetic_frames], ignore_index=True, sort=False)

    if weekly_awards.empty or leaderboards.empty:
        st.info("No award data found.")
        st.stop()

    AWARD_EXPLANATIONS = {
        "Jester": {
            "plain": "The manager with the lowest starting lineup fantasy points in a gameweek.",
            "metric": "Ranked by weekly Jester wins. Avg starter points is shown for context.",
            "vibe": "This is the weekly shame trophy."
        },
        "Golden Boot": {
            "plain": "Season leaderboard is total goals scored by active starters.",
            "metric": "season_total = SUM(starter_goals)",
            "vibe": "Pure goal-scoring dominance."
        },
        "Golden Assist": {
            "plain": "Season leaderboard is total assists from active starters.",
            "metric": "season_total = SUM(starter_assists_total)",
            "vibe": "Creator-in-chief award."
        },
        "Golden Gloves": {
            "plain": "Season leaderboard is total clean sheets from active starters.",
            "metric": "season_total = SUM(starter_clean_sheets)",
            "vibe": "Defensive masterclass."
        },
        "Bench Merchant": {
            "plain": "Season leaderboard is total fantasy points left on the bench.",
            "metric": "season_total = SUM(bench_fantasy_points), with avg per GW shown too.",
            "vibe": "Good squad, questionable decisions."
        },
        "xG Merchant": {
            "plain": "Season leaderboard is total expected goals from active starters.",
            "metric": "season_total = SUM(starter_xg)",
            "vibe": "Underlying numbers merchant."
        },
        "Minutes Merchant": {
            "plain": "Season leaderboard is total minutes played by active starters.",
            "metric": "season_total = SUM(starter_minutes)",
            "vibe": "Everyone actually showed up."
        },
        "Closest Game": {
            "plain": "Leaderboard is closest-game appearances.",
            "metric": "weekly_award_wins = number of times involved in the closest matchup.",
            "vibe": "Sweat of the week."
        },
    }

    awards = sorted(leaderboards["award_name"].dropna().unique())
    pending_award = st.session_state.pop("pending_award", None)
    if pending_award in awards:
        st.session_state["award_detail_selection"] = pending_award
    elif "award_detail_selection" not in st.session_state:
        st.session_state["award_detail_selection"] = awards[0]
    selected_award = st.selectbox(
        "Choose award",
        awards,
        key="award_detail_selection",
    )

    expl = AWARD_EXPLANATIONS.get(selected_award, {
        "plain": "Award leaderboard calculated from manager summary tables.",
        "metric": "See the metric label below.",
        "vibe": ""
    })

    st.markdown(f"### {selected_award}")

    if selected_award not in {"Jester", "Closest Game"}:
        st.success("This leaderboard is ranked by the manager’s full-season total for the award metric. Weekly award wins are shown separately.")
    elif selected_award == "Jester":
        st.warning("Jester is ranked by weekly Jester wins. Lower average starter points are shown for context.")

    c1, c2, c3 = st.columns([1.4, 1.2, 1])
    with c1:
        st.info(expl["plain"])
    with c2:
        st.caption("Metric")
        st.code(expl["metric"], language="text")
    with c3:
        st.caption("Vibe")
        st.write(expl["vibe"])

    lb = leaderboards[leaderboards["award_name"] == selected_award].copy()
    wa = weekly_awards[weekly_awards["award_name"] == selected_award].copy() if "award_name" in weekly_awards.columns else pd.DataFrame()

    if lb.empty:
        st.warning("No leaderboard rows found for this award.")
        st.stop()

    # Sort correctly using rank from analytics builder.
    if "rank" in lb.columns:
        lb["_rank_num"] = pd.to_numeric(lb["rank"], errors="coerce")
        lb = lb.sort_values("_rank_num")
    elif "leaderboard_value" in lb.columns:
        lb = lb.sort_values("leaderboard_value", ascending=False)

    # Main leaderboard, using season values.
    st.subheader("Season Leaderboard")

    preferred_cols = [
        "rank",
        "api_team_name",
        "leaderboard_value",
        "leaderboard_value_label",
        "season_total",
        "season_avg",
        "weekly_award_wins",
        "season_best_week",
        "best_week_value",
        "weeks_won",
        "season_avg_starter_points",
    ]
    leaderboard_cols = [c for c in preferred_cols if c in lb.columns]

    lb_display = lb[leaderboard_cols].copy()
    lb_display = lb_display.rename(columns={
        "rank": "Rank",
        "api_team_name": "Manager",
        "leaderboard_value": "Leaderboard Value",
        "leaderboard_value_label": "Value Type",
        "season_total": "Season Total",
        "season_avg": "Avg / GW",
        "weekly_award_wins": "Weekly Wins",
        "season_best_week": "Best Single Week",
        "best_week_value": "Best Winning Week",
        "weeks_won": "Weeks Won",
        "season_avg_starter_points": "Avg Starter Pts",
    })

    st.dataframe(lb_display, use_container_width=True, height=420)

    # Podium, using leaderboard_value.
    st.subheader("Podium")
    top3 = lb.head(3)
    cols = st.columns(3)
    medals = ["🥇", "🥈", "🥉"]

    for idx, (_, row) in enumerate(top3.iterrows()):
        with cols[idx]:
            main_value = _format_value(row.get("leaderboard_value", row.get("season_total", row.get("weekly_award_wins", ""))))
            label = str(row.get("leaderboard_value_label", ""))
            if selected_award == "Bench Merchant":
                delta = f"avg {_format_value(row.get('season_avg'))}/GW"
            elif selected_award == "Jester":
                delta = f"avg pts {_format_value(row.get('season_avg_starter_points'))}"
            else:
                delta = f"{int(row.get('weekly_award_wins', 0))} weekly wins"
            st.metric(
                f"{medals[idx]} {row.get('api_team_name', '')}",
                main_value,
                delta if delta else label,
            )
            if label:
                st.caption(label)

    st.divider()

    # Weekly history, explicitly a separate thing.
    st.subheader("Weekly Award Winners")
    st.caption("This section shows who won the award in each individual gameweek. It is separate from the season leaderboard above.")

    if wa.empty:
        st.info("No weekly winners found for this award.")
    else:
        history_cols = [
            "fantrax_gw",
            "api_team_name",
            "metric_value",
            "winner_count_for_week",
            "opponent_team_name",
        ]
        history_cols = [c for c in history_cols if c in wa.columns]

        wa_display = wa[history_cols].copy().sort_values("fantrax_gw", ascending=False)
        wa_display = wa_display.rename(columns={
            "fantrax_gw": "GW",
            "api_team_name": "Manager",
            "metric_value": "Weekly Winning Value",
            "winner_count_for_week": "Tied Winners",
            "opponent_team_name": "Opponent",
        })

        st.dataframe(wa_display, use_container_width=True, height=380)

    st.subheader("Manager History")
    managers = sorted(lb["api_team_name"].dropna().unique())
    selected_manager = st.selectbox("Manager", managers)

    manager_lb = lb[lb["api_team_name"] == selected_manager].copy()
    if not manager_lb.empty:
        row = manager_lb.iloc[0]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Rank", _format_value(row.get("rank")))
        m2.metric("Leaderboard Value", _format_value(row.get("leaderboard_value")))
        m3.metric("Avg / GW", _format_value(row.get("season_avg")))
        m4.metric("Weekly Wins", _format_value(row.get("weekly_award_wins")))

    if not wa.empty:
        manager_history = wa[wa["api_team_name"] == selected_manager].copy().sort_values("fantrax_gw")
        st.dataframe(manager_history, use_container_width=True, height=260)



def _build_special_award_leaderboard(
    award_name: str,
    award_leaderboards: pd.DataFrame,
    streaks: pd.DataFrame,
    closest: pd.DataFrame,
    blowouts: pd.DataFrame,
) -> pd.DataFrame:
    if award_name not in {"Closest Game", "Biggest Blowout"}:
        if (
            not award_leaderboards.empty
            and "award_name" in award_leaderboards.columns
        ):
            existing = award_leaderboards[
                award_leaderboards["award_name"].eq(award_name)
            ].copy()
            if not existing.empty:
                return existing

    if (
        award_name in {"Longest Win Streak", "Longest Losing Streak"}
        and not streaks.empty
    ):
        value_col = (
            "longest_win_streak"
            if award_name == "Longest Win Streak"
            else "longest_losing_streak"
        )
        if {"api_team_name", value_col}.issubset(streaks.columns):
            out = streaks[["api_team_name", value_col]].copy()
            out["leaderboard_value"] = pd.to_numeric(
                out[value_col],
                errors="coerce",
            )
            out = out.dropna(subset=["leaderboard_value"]).sort_values(
                ["leaderboard_value", "api_team_name"],
                ascending=[False, True],
            )
            out["rank"] = range(1, len(out) + 1)
            out["award_name"] = award_name
            out["leaderboard_value_label"] = "games"
            return out[
                [
                    "award_name",
                    "rank",
                    "api_team_name",
                    "leaderboard_value",
                    "leaderboard_value_label",
                ]
            ]

    source = closest if award_name == "Closest Game" else blowouts
    if source.empty:
        return pd.DataFrame()

    work = source.copy()
    gw_col = next(
        (
            column
            for column in ["fantrax_gw", "gw", "gameweek", "week"]
            if column in work.columns
        ),
        None,
    )
    team_col = next(
        (
            column
            for column in [
                "api_team_name",
                "team_name",
                "manager_name",
                "home_team_name",
            ]
            if column in work.columns
        ),
        None,
    )
    opponent_col = next(
        (
            column
            for column in [
                "opponent_team_name",
                "opponent_name",
                "opponent_name_from_summary",
                "away_team_name",
            ]
            if column in work.columns
        ),
        None,
    )
    explicit_winner_col = next(
        (
            column
            for column in [
                "winner_team_name",
                "winner_name",
                "winning_team_name",
                "winner",
            ]
            if column in work.columns
        ),
        None,
    )
    explicit_loser_col = next(
        (
            column
            for column in [
                "loser_team_name",
                "loser_name",
                "losing_team_name",
                "loser",
            ]
            if column in work.columns
        ),
        None,
    )
    score_pairs = [
        ("starter_fantasy_points", "opponent_starter_fantasy_points"),
        ("team_points", "opponent_points"),
        ("team_score", "opponent_score"),
        ("score", "opponent_score"),
        ("home_score", "away_score"),
        ("manager_points", "opponent_manager_points"),
    ]
    score_pair = next(
        (
            (left, right)
            for left, right in score_pairs
            if left in work.columns and right in work.columns
        ),
        None,
    )
    value_col = next(
        (
            column
            for column in [
                "point_margin",
                "margin",
                "score_margin",
                "matchup_margin",
                "margin_points",
                "absolute_margin",
                "abs_margin",
                "winning_margin",
                "difference",
                "point_difference",
            ]
            if column in work.columns
        ),
        None,
    )
    if score_pair:
        team_score_col, opponent_score_col = score_pair
        work["_team_score"] = pd.to_numeric(
            work[team_score_col],
            errors="coerce",
        )
        work["_opponent_score"] = pd.to_numeric(
            work[opponent_score_col],
            errors="coerce",
        )
        work["_margin"] = (
            work["_team_score"] - work["_opponent_score"]
        ).abs()
    elif value_col:
        work["_margin"] = pd.to_numeric(
            work[value_col],
            errors="coerce",
        ).abs()
    else:
        return pd.DataFrame()
    work = work.dropna(subset=["_margin"])

    def resolve_matchup(row: pd.Series) -> tuple[str, str, str]:
        if score_pair and team_col and opponent_col:
            team = _clean_display_name(row.get(team_col, ""))
            opponent = _clean_display_name(row.get(opponent_col, ""))
            team_score = row.get("_team_score")
            opponent_score = row.get("_opponent_score")
            if pd.notna(team_score) and pd.notna(opponent_score):
                if team_score > opponent_score:
                    winner, loser = team, opponent
                elif opponent_score > team_score:
                    winner, loser = opponent, team
                else:
                    winner, loser = team, opponent
                return winner, loser, f"{winner} (W) vs {loser}"
        if explicit_winner_col and explicit_loser_col:
            winner = _clean_display_name(row.get(explicit_winner_col, ""))
            loser = _clean_display_name(row.get(explicit_loser_col, ""))
            if winner and loser:
                return winner, loser, f"{winner} (W) vs {loser}"
        if team_col and opponent_col:
            team = _clean_display_name(row.get(team_col, ""))
            opponent = _clean_display_name(row.get(opponent_col, ""))
            return team, opponent, f"{team} (W) vs {opponent}"
        return "", "", ""

    resolved = work.apply(resolve_matchup, axis=1, result_type="expand")
    resolved.columns = ["_winner", "_loser", "_matchup_name"]
    work = pd.concat([work, resolved], axis=1)
    work = work[work["_matchup_name"].astype(str).str.len() > 0].copy()
    work["_pair_key"] = work.apply(
        lambda row: "||".join(
            sorted(
                [
                    _clean_display_name(row.get("_winner", "")),
                    _clean_display_name(row.get("_loser", "")),
                ]
            )
        ),
        axis=1,
    )
    dedupe_cols = ["_pair_key"]
    if gw_col:
        dedupe_cols.append(gw_col)
    work = work.drop_duplicates(subset=dedupe_cols, keep="first")
    work = work.sort_values(
        "_margin",
        ascending=award_name == "Closest Game",
    ).reset_index(drop=True)
    work["api_team_name"] = work["_matchup_name"]
    work["leaderboard_value"] = work["_margin"]
    work["rank"] = work.index + 1
    work["award_name"] = award_name
    work["leaderboard_value_label"] = "point margin"
    return work[
        [
            "award_name",
            "rank",
            "api_team_name",
            "leaderboard_value",
            "leaderboard_value_label",
        ]
    ]


def _format_value(value: Any) -> str:
    if pd.isna(value):
        return ""
    try:
        numeric = float(value)
        if numeric.is_integer():
            return str(int(numeric))
        return f"{numeric:.1f}"
    except Exception:
        return str(value)


def _clean_display_name(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = str(value)
    text = text.replace("Ã¢â‚¬â„¢", "â€™")
    for bad in ["ðŸ¤¡", "Ã°Å¸Â¤Â¡"]:
        text = text.replace(bad, "")
    return " ".join(text.split()).strip()
