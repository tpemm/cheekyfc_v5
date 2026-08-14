from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st


# =============================================================================
# CONFIG
# =============================================================================

PROJECT_ROOT = Path(r"C:\Users\Tommy\fantrax_data")
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
REFRESH_SCRIPT = SCRIPTS_DIR / "refresh_all_fantrax_data.py"
BUILD_AWARDS_SCRIPT = SCRIPTS_DIR / "build_league_awards_views.py"

VENV_PY = PROJECT_ROOT / ".venv311" / "Scripts" / "python.exe"
PYTHON_EXE = VENV_PY if VENV_PY.exists() else Path(sys.executable)

DATA_DIRS = [
    PROJECT_ROOT / "data" / "raw",
    PROJECT_ROOT / "raw_data",
    PROJECT_ROOT / "data" / "processed",
    PROJECT_ROOT / "processed_data",
    PROJECT_ROOT / "data" / "reference",
    PROJECT_ROOT / "data" / "analytics_views",
]

ANALYTICS_DIR = PROJECT_ROOT / "data" / "analytics_views"

ANALYTICS_FILES = {
    "league_table": ANALYTICS_DIR / "league_table.csv",
    "weekly_awards": ANALYTICS_DIR / "weekly_awards.csv",
    "award_leaderboards": ANALYTICS_DIR / "award_leaderboards.csv",
    "manager_streaks": ANALYTICS_DIR / "manager_streaks.csv",
    "lineup_changes": ANALYTICS_DIR / "lineup_changes.csv",
    "closest_games": ANALYTICS_DIR / "closest_games.csv",
    "biggest_blowouts": ANALYTICS_DIR / "biggest_blowouts.csv",
    "league_hub_cards": ANALYTICS_DIR / "league_hub_cards.csv",
    "manager_awards_dynamic": ANALYTICS_DIR / "manager_awards_dynamic.csv",
    "manager_profile_summary": ANALYTICS_DIR / "manager_profile_summary.csv",
    "manager_efficiency_weekly": ANALYTICS_DIR / "manager_efficiency_weekly.csv",
    "manager_efficiency_season": ANALYTICS_DIR / "manager_efficiency_season.csv",
    "lineup_decision_details": ANALYTICS_DIR / "lineup_decision_details.csv",
    "ghost_points_player_leaders": ANALYTICS_DIR / "ghost_points_player_leaders.csv",
    "ghost_points_manager_weekly": ANALYTICS_DIR / "ghost_points_manager_weekly.csv",
    "ghost_points_manager_season": ANALYTICS_DIR / "ghost_points_manager_season.csv",
    "position_points_manager_season": ANALYTICS_DIR / "position_points_manager_season.csv",
    "roster_adds_weekly": ANALYTICS_DIR / "roster_adds_weekly.csv",
    "roster_adds_leaders": ANALYTICS_DIR / "roster_adds_leaders.csv",
}

IMPORTANT_OUTPUTS = [
    PROJECT_ROOT / "data" / "processed" / "master_player_weekly_2526.csv",
    PROJECT_ROOT / "data" / "processed" / "manager_player_weekly_2526.csv",
    PROJECT_ROOT / "data" / "processed" / "manager_week_summary_2526.csv",
    PROJECT_ROOT / "data" / "processed" / "manager_season_summary_2526.csv",
    PROJECT_ROOT / "data" / "processed" / "lineup_quality_summary_2526.csv",
    PROJECT_ROOT / "data" / "processed" / "matchup_week_summary_2526.csv",
    PROJECT_ROOT / "processed_data" / "fantrax_api" / "rosters_by_week.csv",
    PROJECT_ROOT / "processed_data" / "fantrax_api" / "standings.csv",
    PROJECT_ROOT / "processed_data" / "fantrax_api" / "matchups_by_week.csv",
    PROJECT_ROOT / "processed_data" / "fantrax_api" / "validation_report.txt",
    PROJECT_ROOT / "data" / "processed" / "api_merge_validation_report_2526.txt",
    *ANALYTICS_FILES.values(),
]


# =============================================================================
# PAGE SETUP
# =============================================================================

st.set_page_config(
    page_title="Fantrax Data App",
    page_icon="⚽",
    layout="wide",
)

st.title("⚽ Fantrax Data App")
st.caption("League hub, update controls, and raw data inspection for the Fantrax analytics pipeline.")


# =============================================================================
# STYLE
# =============================================================================

st.markdown(
    """
    <style>
    .metric-card {
        border: 1px solid rgba(49, 51, 63, 0.18);
        border-radius: 16px;
        padding: 14px 16px;
        margin-bottom: 12px;
        background: rgba(250, 250, 250, 0.65);
        min-height: 135px;
    }
    .metric-card h4 {
        margin: 0 0 4px 0;
        font-size: 1.0rem;
    }
    .metric-card .subtitle {
        color: #666;
        font-size: 0.82rem;
        margin-bottom: 8px;
    }
    .metric-card .team {
        font-weight: 700;
        font-size: 1.02rem;
        margin-bottom: 6px;
    }
    .metric-card .value {
        font-size: 1.45rem;
        font-weight: 800;
        margin-bottom: 2px;
    }
    .metric-card .detail {
        color: #666;
        font-size: 0.8rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =============================================================================
# HELPERS
# =============================================================================

def file_info(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "status": "MISSING",
            "path": str(path),
            "relative_path": str(path),
            "size_mb": None,
            "modified": None,
            "type": path.suffix.lower().replace(".", ""),
        }

    stat = path.stat()
    try:
        rel = path.relative_to(PROJECT_ROOT)
    except ValueError:
        rel = path

    return {
        "status": "OK",
        "path": str(path),
        "relative_path": str(rel),
        "size_mb": round(stat.st_size / (1024 * 1024), 3),
        "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "type": path.suffix.lower().replace(".", ""),
    }


def scan_data_files() -> pd.DataFrame:
    rows = []
    for root in DATA_DIRS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".csv", ".json", ".txt", ".parquet"}:
                rows.append(file_info(path))

    df = pd.DataFrame(rows)
    if len(df):
        df = df.sort_values(["modified", "relative_path"], ascending=[False, True])
    return df


@st.cache_data(show_spinner=False)
def load_preview(path_text: str, max_rows: int = 5000) -> tuple[pd.DataFrame | None, str | None]:
    path = Path(path_text)
    suffix = path.suffix.lower()

    try:
        if suffix == ".csv":
            return pd.read_csv(path, nrows=max_rows, encoding="utf-8-sig"), None

        if suffix == ".parquet":
            df = pd.read_parquet(path)
            return df.head(max_rows), None

        if suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return pd.json_normalize(data).head(max_rows), None
            if isinstance(data, dict):
                if all(isinstance(v, dict) for v in data.values()):
                    return pd.DataFrame.from_dict(data, orient="index").reset_index(names="key").head(max_rows), None
                return pd.json_normalize(data).head(max_rows), None
            return pd.DataFrame({"value": [str(data)]}), None

        if suffix == ".txt":
            text = path.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()
            return pd.DataFrame({"line_number": range(1, len(lines[:max_rows]) + 1), "text": lines[:max_rows]}), None

        return None, f"Unsupported file type: {suffix}"

    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


@st.cache_data(show_spinner=False)
def load_csv_cached(path_text: str) -> pd.DataFrame:
    path = Path(path_text)
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, encoding="utf-8-sig")
    return clean_df_display_names(df)


def filter_dataframe(df: pd.DataFrame, search_text: str, selected_cols: list[str]) -> pd.DataFrame:
    out = df.copy()

    if selected_cols:
        keep_cols = [c for c in selected_cols if c in out.columns]
        if keep_cols:
            out = out[keep_cols]

    if search_text.strip():
        query = search_text.strip().lower()
        mask = pd.Series(False, index=out.index)
        for col in out.columns:
            mask = mask | out[col].astype(str).str.lower().str.contains(query, na=False, regex=False)
        out = out[mask]

    return out


def run_script(script_path: Path, input_text: str | None = None) -> str:
    if not script_path.exists():
        return f"ERROR: script not found: {script_path}"

    cmd = [str(PYTHON_EXE), str(script_path)]

    try:
        proc = subprocess.run(
            cmd,
            input=input_text,
            text=True,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
        )
    except Exception as exc:
        return f"ERROR running script: {type(exc).__name__}: {exc}"

    output = []
    output.append("$ " + " ".join(cmd))
    output.append(f"Exit code: {proc.returncode}")
    output.append("")
    if proc.stdout:
        output.append(proc.stdout)
    if proc.stderr:
        output.append("\n--- STDERR ---")
        output.append(proc.stderr)

    return "\n".join(output)


def run_refresh(mode: str, specific_weeks: str | None = None) -> str:
    mode_clean = mode.strip().upper()

    if mode_clean == "AUTO":
        input_text = "AUTO\n"
    elif mode_clean == "REBUILD":
        input_text = "REBUILD\n"
    elif mode_clean == "SPECIFIC":
        if not specific_weeks:
            return "ERROR: Specific mode requires weeks, like 35 or 34-36."
        input_text = f"SPECIFIC\n{specific_weeks}\n"
    elif mode_clean == "FULL":
        input_text = "FULL\nAUTO\n"
    else:
        return f"ERROR: Unknown mode: {mode}"

    return run_script(REFRESH_SCRIPT, input_text=input_text)


def build_awards_views() -> str:
    return run_script(BUILD_AWARDS_SCRIPT)


def format_value(value: Any) -> str:
    if pd.isna(value):
        return ""
    try:
        f = float(value)
        if f.is_integer():
            return str(int(f))
        return f"{f:.1f}"
    except Exception:
        return str(value)


def clean_display_name(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = str(value)
    text = text.replace("â€™", "’")
    for bad in ["🤡", "ðŸ¤¡"]:
        text = text.replace(bad, "")
    return " ".join(text.split()).strip()


def clean_df_display_names(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ["api_team_name", "team_name", "opponent_team_name", "opponent_name_from_summary", "Manager", "Team"]:
        if col in out.columns:
            out[col] = out[col].map(clean_display_name)
    return out


def render_card(row: pd.Series) -> None:
    st.markdown(
        f"""
        <div class="metric-card">
            <h4>{row.get('title', '')}</h4>
            <div class="subtitle">{row.get('subtitle', '')}</div>
            <div class="team">{row.get('team_name', '')}</div>
            <div class="value">{format_value(row.get('value', ''))}</div>
            <div class="detail">{row.get('detail', '')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_missing_analytics_warning() -> None:
    missing = [name for name, path in ANALYTICS_FILES.items() if not path.exists()]
    if missing:
        st.warning(
            "Analytics views are missing. Run `build_league_awards_views.py` first, or use the button below.",
            icon="⚠️",
        )
        if st.button("Build analytics views now", type="primary"):
            with st.spinner("Building analytics views..."):
                out = build_awards_views()
            st.text_area("Build output", out, height=500)
            st.cache_data.clear()
            st.rerun()


def require_csv(path: Path, label: str) -> pd.DataFrame:
    df = load_csv_cached(str(path))
    if df.empty:
        st.warning(f"Missing or empty: {label} — expected `{path}`")
    return df


def nice_col_name(col: str) -> str:
    return str(col).replace("_", " ").title()


def show_table_with_search(df: pd.DataFrame, default_cols: list[str] | None = None, height: int = 480) -> None:
    if df.empty:
        st.info("No rows found.")
        return

    default_cols = [c for c in (default_cols or list(df.columns)) if c in df.columns]
    with st.expander("Table controls", expanded=False):
        search = st.text_input("Search this table", key=f"search_{hash(tuple(df.columns))}_{len(df)}")
        selected_cols = st.multiselect(
            "Columns",
            list(df.columns),
            default=default_cols if default_cols else list(df.columns),
            key=f"cols_{hash(tuple(df.columns))}_{len(df)}",
        )

    display = filter_dataframe(df, search, selected_cols)
    st.dataframe(display, use_container_width=True, height=height)


def metric_or_blank(container, label: str, value: Any, delta: Any = None) -> None:
    container.metric(label, format_value(value), None if delta is None else str(delta))



# =============================================================================
# SIDEBAR
# =============================================================================

page = st.sidebar.radio(
    "Page",
    [
        "League Hub",
        "Award Detail",
        "Manager Awards",
        "Manager Profile",
        "Manager Detail",
        "Update Pipeline",
        "Raw Data Browser",
        "Key Output Health",
        "Reports",
    ],
)

st.sidebar.divider()
st.sidebar.write("Project root:")
st.sidebar.code(str(PROJECT_ROOT), language="text")


# =============================================================================
# PAGE: LEAGUE HUB
# =============================================================================

if page == "League Hub":
    st.header("🏆 League Hub")
    show_missing_analytics_warning()

    league_table = load_csv_cached(str(ANALYTICS_FILES["league_table"]))
    cards = load_csv_cached(str(ANALYTICS_FILES["league_hub_cards"]))
    streaks = load_csv_cached(str(ANALYTICS_FILES["manager_streaks"]))
    lineup_changes = load_csv_cached(str(ANALYTICS_FILES["lineup_changes"]))
    closest = load_csv_cached(str(ANALYTICS_FILES["closest_games"]))
    blowouts = load_csv_cached(str(ANALYTICS_FILES["biggest_blowouts"]))

    if league_table.empty:
        st.stop()

    top_cols = st.columns([1, 1, 1, 1])
    max_gw = int(pd.to_numeric(league_table.get("weeks", pd.Series([0])), errors="coerce").max())
    top_cols[0].metric("Weeks loaded", max_gw)
    top_cols[1].metric("Managers", len(league_table))
    top_cols[2].metric("Top score", format_value(pd.to_numeric(league_table.get("total_starter_points"), errors="coerce").max()))
    if "official_rank" in league_table.columns:
        leader_table = league_table.copy()
        leader_table["_rank_num"] = pd.to_numeric(leader_table["official_rank"], errors="coerce")
        leader = leader_table.sort_values("_rank_num").iloc[0]["api_team_name"]
    else:
        leader = league_table.iloc[0]["api_team_name"]
    top_cols[3].metric("Current leader", leader)

    st.divider()

    left, center, right = st.columns([1.05, 2.4, 1.05])

    if not cards.empty:
        left_cards = cards.iloc[::2].head(6)
        right_cards = cards.iloc[1::2].head(6)

        with left:
            for _, row in left_cards.iterrows():
                render_card(row)

        with right:
            for _, row in right_cards.iterrows():
                render_card(row)

    with center:
        st.subheader("League Table")

        preferred_cols = [
            "official_rank",
            "api_team_name",
            "official_record",
            "official_total_points_for",
            "total_starter_points",
            "avg_starter_points",
            "best_week_points",
            "total_starter_goals",
            "total_starter_assists_total",
            "total_starter_clean_sheets",
            "longest_win_streak",
            "current_streak_type",
            "current_streak_len",
        ]
        show_cols = [c for c in preferred_cols if c in league_table.columns]

        display_table = league_table[show_cols].copy()
        display_table = display_table.rename(columns={
            "official_rank": "Rank",
            "api_team_name": "Team",
            "official_record": "Record",
            "official_total_points_for": "Official PF",
            "total_starter_points": "Starter Pts",
            "avg_starter_points": "Avg Pts",
            "best_week_points": "Best Week",
            "total_starter_goals": "Goals",
            "total_starter_assists_total": "Assists",
            "total_starter_clean_sheets": "CS",
            "longest_win_streak": "Best W Streak",
            "current_streak_type": "Current",
            "current_streak_len": "Len",
        })

        st.dataframe(display_table, use_container_width=True, height=540)

    st.divider()

    tab1, tab2, tab3, tab4 = st.tabs(["🔥 Streaks", "🔄 Lineup Changes", "😬 Closest Games", "💀 Blowouts"])

    with tab1:
        st.subheader("Manager Streaks")
        st.dataframe(streaks, use_container_width=True, height=420)

    with tab2:
        st.subheader("Lineup Change Leaderboard")
        if not lineup_changes.empty and "view_type" in lineup_changes.columns:
            season_lineups = lineup_changes[lineup_changes["view_type"] == "season_summary"].copy()
            season_lineups = season_lineups.sort_values("total_starter_changes", ascending=False)
            st.dataframe(season_lineups, use_container_width=True, height=420)
        else:
            st.info("No lineup change data found.")

    with tab3:
        st.subheader("Closest Games")
        st.dataframe(closest.head(50), use_container_width=True, height=420)

    with tab4:
        st.subheader("Biggest Blowouts")
        st.dataframe(blowouts.head(50), use_container_width=True, height=420)


# =============================================================================
# PAGE: AWARD DETAIL
# =============================================================================

elif page == "Award Detail":
    st.header("🏅 Award Detail")
    show_missing_analytics_warning()

    weekly_awards = load_csv_cached(str(ANALYTICS_FILES["weekly_awards"]))
    leaderboards = load_csv_cached(str(ANALYTICS_FILES["award_leaderboards"]))

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
    selected_award = st.selectbox("Choose award", awards)

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
            main_value = format_value(row.get("leaderboard_value", row.get("season_total", row.get("weekly_award_wins", ""))))
            label = str(row.get("leaderboard_value_label", ""))
            if selected_award == "Bench Merchant":
                delta = f"avg {format_value(row.get('season_avg'))}/GW"
            elif selected_award == "Jester":
                delta = f"avg pts {format_value(row.get('season_avg_starter_points'))}"
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
        m1.metric("Rank", format_value(row.get("rank")))
        m2.metric("Leaderboard Value", format_value(row.get("leaderboard_value")))
        m3.metric("Avg / GW", format_value(row.get("season_avg")))
        m4.metric("Weekly Wins", format_value(row.get("weekly_award_wins")))

    if not wa.empty:
        manager_history = wa[wa["api_team_name"] == selected_manager].copy().sort_values("fantrax_gw")
        st.dataframe(manager_history, use_container_width=True, height=260)



# =============================================================================
# PAGE: MANAGER AWARDS
# =============================================================================

elif page == "Manager Awards":
    st.header("🏆 Manager Awards")
    st.caption("Dynamic leaderboards. Use Season for all-year awards or Weekly to inspect one gameweek.")

    awards = require_csv(ANALYTICS_FILES["manager_awards_dynamic"], "manager_awards_dynamic.csv")
    roster_adds = load_csv_cached(str(ANALYTICS_FILES["roster_adds_weekly"]))

    if awards.empty:
        st.info("Run `build_efficiency_ghost_awards_views.py` first.")
        st.stop()

    awards = awards.copy()
    if "fantrax_gw" in awards.columns:
        awards["fantrax_gw"] = pd.to_numeric(awards["fantrax_gw"], errors="coerce")

    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        scope = st.radio("Scope", ["Season", "Weekly"], horizontal=True)
    with c2:
        if scope == "Weekly":
            weeks = sorted([int(x) for x in awards["fantrax_gw"].dropna().unique()])
            selected_gw = st.selectbox("Gameweek", weeks, index=len(weeks) - 1 if weeks else 0)
        else:
            selected_gw = None
    with c3:
        available = awards[awards["scope"].str.lower() == scope.lower()].copy()
        if selected_gw is not None:
            available = available[available["fantrax_gw"] == selected_gw]
        award_names = sorted(available["award_name"].dropna().unique())
        selected_award = st.selectbox("Leaderboard", award_names)

    sub = awards[(awards["scope"].str.lower() == scope.lower()) & (awards["award_name"] == selected_award)].copy()
    if selected_gw is not None:
        sub = sub[sub["fantrax_gw"] == selected_gw]

    if sub.empty:
        st.info("No leaderboard rows for that selection.")
        st.stop()

    sub = sub.sort_values("rank")
    description = sub["description"].dropna().iloc[0] if "description" in sub.columns and sub["description"].notna().any() else ""
    if description:
        st.info(description)

    top = sub.head(3)
    medals = ["🥇", "🥈", "🥉"]
    cols = st.columns(3)
    for i, (_, row) in enumerate(top.iterrows()):
        with cols[i]:
            detail_bits = []
            for c in ["total_xg", "total_xa", "starter_xg", "starter_xa", "missed_points", "efficiency_pct", "season_efficiency_pct", "ghost_points_share_pct"]:
                if c in row.index and pd.notna(row.get(c)):
                    detail_bits.append(f"{nice_col_name(c)}: {format_value(row.get(c))}")
            st.metric(f"{medals[i]} {row.get('api_team_name', '')}", format_value(row.get("value")))
            if detail_bits:
                st.caption(" | ".join(detail_bits[:2]))

    st.divider()

    default_cols = [
        "rank", "api_team_name", "value", "total_xg", "total_xa", "starter_xg", "starter_xa",
        "season_efficiency_pct", "efficiency_pct", "missed_points", "actual_starter_points",
        "optimal_lineup_points", "fantasy_points", "major_event_points", "ghost_points_share_pct",
        "roster_adds", "total_points_after_adds", "avg_points_per_add",
        "total_starter_changes", "avg_starter_changes",
    ]
    default_cols = [c for c in default_cols if c in sub.columns and sub[c].notna().any()]
    show_table_with_search(sub, default_cols=default_cols, height=470)

    if selected_award in {"Roster Add Value", "Roster Adds"} and not roster_adds.empty:
        st.subheader("Roster Add Details")
        add_cols = [
            "api_team_name", "player_name", "added_gw", "points_after_add", "avg_points_after_add",
            "starts_after_add", "weeks_rostered_after_add", "points_in_added_gw", "started_in_added_gw",
        ]
        show_table_with_search(
            roster_adds.sort_values("points_after_add", ascending=False),
            default_cols=[c for c in add_cols if c in roster_adds.columns],
            height=360,
        )


# =============================================================================
# PAGE: MANAGER PROFILE
# =============================================================================

elif page == "Manager Profile":
    st.header("👤 Manager Profile")
    st.caption("One-page manager summary: standings, efficiency, ghost points, roster adds, position scoring, and decisions.")

    profile = require_csv(ANALYTICS_FILES["manager_profile_summary"], "manager_profile_summary.csv")
    manager_week = load_csv_cached(str(PROJECT_ROOT / "data" / "processed" / "manager_week_summary_2526.csv"))
    matchup_week = load_csv_cached(str(PROJECT_ROOT / "data" / "processed" / "matchup_week_summary_2526.csv"))
    decisions = load_csv_cached(str(ANALYTICS_FILES["lineup_decision_details"]))
    player_leaders = load_csv_cached(str(ANALYTICS_FILES["ghost_points_player_leaders"]))
    roster_adds = load_csv_cached(str(ANALYTICS_FILES["roster_adds_weekly"]))
    pos_season = load_csv_cached(str(ANALYTICS_FILES["position_points_manager_season"]))

    if profile.empty:
        st.info("Run `build_efficiency_ghost_awards_views.py` first.")
        st.stop()

    manager_names = sorted(profile["api_team_name"].dropna().unique())
    manager = st.selectbox("Manager", manager_names)
    row = profile[profile["api_team_name"] == manager].iloc[0]

    top1, top2, top3, top4, top5 = st.columns(5)
    metric_or_blank(top1, "Rank", row.get("official_rank"), row.get("official_record"))
    metric_or_blank(top2, "Starter Points", row.get("total_starter_points"), f"avg {format_value(row.get('avg_starter_points'))}")
    metric_or_blank(top3, "Efficiency", row.get("season_efficiency_pct"), f"rank {format_value(row.get('efficiency_rank'))}")
    metric_or_blank(top4, "Missed Pts", row.get("missed_points"))
    metric_or_blank(top5, "Ghost Pts", row.get("ghost_points"), f"rank {format_value(row.get('ghost_points_rank'))}")

    top6, top7, top8, top9, top10 = st.columns(5)
    metric_or_blank(top6, "Goals", row.get("total_starter_goals"), f"xG {format_value(row.get('total_xg'))}")
    metric_or_blank(top7, "Assists", row.get("total_starter_assists_total"), f"xA {format_value(row.get('total_xa'))}")
    metric_or_blank(top8, "Clean Sheets", row.get("total_starter_clean_sheets"))
    metric_or_blank(top9, "Roster Adds", row.get("roster_adds"), f"pts {format_value(row.get('total_points_after_adds'))}")
    metric_or_blank(top10, "Lineup Changes", row.get("total_starter_changes"), f"avg {format_value(row.get('avg_starter_changes'))}/GW")

    st.divider()

    tabs = st.tabs([
        "Weekly Trend",
        "Position Scoring",
        "Lineup Decisions",
        "Roster Adds",
        "Players",
        "Raw Profile",
    ])

    with tabs[0]:
        sub = manager_week[manager_week["api_team_name"] == manager].copy()
        if sub.empty:
            st.info("No weekly data found.")
        else:
            sub = sub.sort_values("fantrax_gw")
            chart_cols = [c for c in ["starter_fantasy_points", "bench_fantasy_points", "starter_goals", "starter_assists_total", "starter_clean_sheets"] if c in sub.columns]
            if chart_cols:
                st.line_chart(sub.set_index("fantrax_gw")[chart_cols])
            display_cols = ["fantrax_gw", "starter_fantasy_points", "bench_fantasy_points", "starter_goals", "starter_assists_total", "starter_clean_sheets", "starter_xg", "starter_xa", "opponent_team_name"]
            show_table_with_search(sub.sort_values("fantrax_gw", ascending=False), [c for c in display_cols if c in sub.columns], height=360)

    with tabs[1]:
        pos = pos_season[pos_season["api_team_name"] == manager].copy()
        if pos.empty:
            st.info("No position data found.")
        else:
            chart = pos.set_index("position_group")[[c for c in ["fantasy_points", "ghost_points", "starts", "goals", "assists", "clean_sheets"] if c in pos.columns]]
            st.bar_chart(chart[[c for c in ["fantasy_points", "ghost_points"] if c in chart.columns]])
            st.dataframe(pos, use_container_width=True, height=280)

    with tabs[2]:
        d = decisions[decisions["api_team_name"] == manager].copy()
        if d.empty:
            st.info("No decision details found.")
        else:
            c1, c2 = st.columns(2)
            with c1:
                dtype = st.multiselect(
                    "Decision type",
                    sorted(d["decision_type"].dropna().unique()),
                    default=[x for x in ["missed_bench_start", "should_have_sat"] if x in set(d["decision_type"].dropna())],
                )
            with c2:
                weeks = sorted([int(x) for x in d["fantrax_gw"].dropna().unique()])
                week_filter = st.multiselect("Gameweeks", weeks, default=[])
            if dtype:
                d = d[d["decision_type"].isin(dtype)]
            if week_filter:
                d = d[d["fantrax_gw"].isin(week_filter)]
            cols = ["fantrax_gw", "player_name", "decision_type", "fantasy_points", "actual_started", "optimal_selected", "actual_scored_position", "optimal_assigned_position", "eligible_positions"]
            show_table_with_search(d.sort_values(["fantrax_gw", "fantasy_points"], ascending=[False, False]), [c for c in cols if c in d.columns], height=430)

    with tabs[3]:
        adds = roster_adds[roster_adds["api_team_name"] == manager].copy()
        if adds.empty:
            st.info("No roster-add data found.")
        else:
            cols = ["player_name", "added_gw", "points_after_add", "avg_points_after_add", "starts_after_add", "weeks_rostered_after_add", "points_in_added_gw", "started_in_added_gw"]
            show_table_with_search(adds.sort_values("points_after_add", ascending=False), [c for c in cols if c in adds.columns], height=430)

    with tabs[4]:
        # Current player leader table is league-wide, so use roster-add/player names for manager-specific context where available.
        st.write("League-wide ghost points leaders for reference.")
        cols = ["ghost_points_rank", "display_player_name", "appearances", "starts", "total_fantasy_points", "total_ghost_points", "avg_ghost_points", "total_goals", "total_assists", "total_clean_sheets"]
        show_table_with_search(player_leaders.head(100), [c for c in cols if c in player_leaders.columns], height=430)

    with tabs[5]:
        st.dataframe(profile[profile["api_team_name"] == manager].T.rename(columns={row.name: manager}), use_container_width=True, height=700)

# =============================================================================
# PAGE: MANAGER DETAIL
# =============================================================================

elif page == "Manager Detail":
    st.header("👤 Manager Detail")
    show_missing_analytics_warning()

    league_table = load_csv_cached(str(ANALYTICS_FILES["league_table"]))
    weekly_awards = load_csv_cached(str(ANALYTICS_FILES["weekly_awards"]))
    matchup_week = load_csv_cached(str(PROJECT_ROOT / "data" / "processed" / "matchup_week_summary_2526.csv"))
    manager_week = load_csv_cached(str(PROJECT_ROOT / "data" / "processed" / "manager_week_summary_2526.csv"))
    lineup_changes = load_csv_cached(str(ANALYTICS_FILES["lineup_changes"]))

    if league_table.empty:
        st.stop()

    manager_names = sorted(league_table["api_team_name"].dropna().unique())
    manager = st.selectbox("Manager", manager_names)

    team_row = league_table[league_table["api_team_name"] == manager].iloc[0]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Record", str(team_row.get("official_record", "")))
    c2.metric("Starter Points", format_value(team_row.get("total_starter_points")))
    c3.metric("Best Week", format_value(team_row.get("best_week_points")))
    c4.metric("Longest W Streak", format_value(team_row.get("longest_win_streak")))

    st.divider()

    tabs = st.tabs(["Weekly Scores", "Awards", "Lineup Changes", "Matchups"])

    with tabs[0]:
        sub = manager_week[manager_week["api_team_name"] == manager].copy()
        if not sub.empty:
            chart_cols = [c for c in ["fantrax_gw", "starter_fantasy_points", "bench_fantasy_points", "starter_goals", "starter_assists_total", "starter_clean_sheets"] if c in sub.columns]
            st.line_chart(sub.set_index("fantrax_gw")[[c for c in chart_cols if c != "fantrax_gw"]])
            st.dataframe(sub, use_container_width=True, height=360)

    with tabs[1]:
        sub = weekly_awards[weekly_awards["api_team_name"] == manager].copy()
        st.dataframe(sub.sort_values(["award_name", "fantrax_gw"]), use_container_width=True, height=460)

    with tabs[2]:
        sub = lineup_changes[lineup_changes["api_team_name"] == manager].copy()
        st.dataframe(sub, use_container_width=True, height=460)

    with tabs[3]:
        sub = matchup_week[matchup_week["api_team_name"] == manager].copy()
        st.dataframe(sub.sort_values("fantrax_gw", ascending=False), use_container_width=True, height=460)


# =============================================================================
# PAGE: UPDATE
# =============================================================================

elif page == "Update Pipeline":
    st.header("🔄 Update Pipeline")
    st.write("Run the one-click refresh script and rebuild the analytics views.")

    col1, col2 = st.columns([1, 2])

    with col1:
        mode = st.selectbox(
            "Refresh mode",
            ["AUTO", "REBUILD", "SPECIFIC", "FULL"],
            index=0,
            help=(
                "AUTO = normal weekly update. "
                "REBUILD = rebuild from existing raw data. "
                "SPECIFIC = refresh selected gameweek(s). "
                "FULL = aggressive refresh."
            ),
        )

        specific_weeks = None
        if mode == "SPECIFIC":
            specific_weeks = st.text_input("Weeks to refresh", placeholder="35 or 34-36")

        rebuild_awards_after = st.checkbox("Rebuild League Hub analytics after refresh", value=True)

        st.warning(
            "This runs local scripts and can take a few minutes. Do not close the terminal while it runs.",
            icon="⚠️",
        )

        run_clicked = st.button("Run refresh", type="primary", use_container_width=True)
        build_clicked = st.button("Only rebuild League Hub analytics", use_container_width=True)

    with col2:
        st.subheader("Expected command")
        st.code(f"{PYTHON_EXE} {REFRESH_SCRIPT}", language="powershell")

        if run_clicked:
            with st.spinner("Running refresh pipeline..."):
                result = run_refresh(mode, specific_weeks)

            if rebuild_awards_after and "Exit code: 0" in result:
                with st.spinner("Rebuilding League Hub analytics..."):
                    result += "\n\n" + build_awards_views()

            st.subheader("Output")
            st.text_area("Output log", result, height=650)

            st.cache_data.clear()

            if "Exit code: 0" in result:
                st.success("Refresh completed.")
            else:
                st.error("Refresh did not finish cleanly. Check the log above.")

        if build_clicked:
            with st.spinner("Building analytics views..."):
                result = build_awards_views()
            st.text_area("Build output", result, height=650)
            st.cache_data.clear()
            if "Exit code: 0" in result:
                st.success("League Hub analytics rebuilt.")
            else:
                st.error("Analytics build did not finish cleanly.")

    st.divider()
    st.subheader("Latest refresh reports")

    reports_dir = PROJECT_ROOT / "data" / "processed" / "refresh_reports"
    if reports_dir.exists():
        reports = sorted(reports_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)
        for report in reports[:5]:
            info = file_info(report)
            with st.expander(f"{info['modified']} — {report.name}"):
                st.text(report.read_text(encoding="utf-8", errors="replace"))
    else:
        st.info("No refresh reports directory found yet.")


# =============================================================================
# PAGE: RAW DATA BROWSER
# =============================================================================

elif page == "Raw Data Browser":
    st.header("🗂️ Raw Data Browser")
    st.write("Browse CSV, JSON, TXT, and Parquet files from the project data folders.")

    files_df = scan_data_files()

    if files_df.empty:
        st.warning("No data files found.")
        st.stop()

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        file_search = st.text_input("Search file paths", placeholder="fantrax, understat, rosters, manager_week...")
    with col2:
        type_filter = st.multiselect("File type", sorted(files_df["type"].dropna().unique()), default=[])
    with col3:
        status_filter = st.multiselect("Status", sorted(files_df["status"].dropna().unique()), default=[])

    filtered_files = files_df.copy()
    if file_search.strip():
        filtered_files = filtered_files[
            filtered_files["relative_path"].astype(str).str.lower().str.contains(file_search.lower(), na=False)
        ]
    if type_filter:
        filtered_files = filtered_files[filtered_files["type"].isin(type_filter)]
    if status_filter:
        filtered_files = filtered_files[filtered_files["status"].isin(status_filter)]

    st.subheader("Files")
    st.dataframe(
        filtered_files[["status", "relative_path", "type", "size_mb", "modified"]],
        use_container_width=True,
        height=280,
    )

    selected_rel = st.selectbox("Open file", filtered_files["relative_path"].tolist())

    selected_path = PROJECT_ROOT / selected_rel
    st.caption(str(selected_path))

    max_rows = st.slider("Preview row limit", 100, 20000, 5000, step=100)

    df, err = load_preview(str(selected_path), max_rows=max_rows)
    if err:
        st.error(err)
        st.stop()

    if df is None:
        st.warning("Could not load file preview.")
        st.stop()

    st.subheader("Preview / Filter")

    col1, col2 = st.columns([1, 2])
    with col1:
        search_text = st.text_input("Search within loaded rows")
    with col2:
        selected_cols = st.multiselect("Columns to show", df.columns.tolist(), default=[])

    display_df = filter_dataframe(df, search_text, selected_cols)

    st.write(f"Loaded rows: {len(df):,} | Displayed rows: {len(display_df):,} | Columns: {len(display_df.columns):,}")
    st.dataframe(display_df, use_container_width=True, height=600)

    csv_bytes = display_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "Download displayed rows as CSV",
        data=csv_bytes,
        file_name=f"filtered_{selected_path.stem}.csv",
        mime="text/csv",
    )


# =============================================================================
# PAGE: KEY OUTPUT HEALTH
# =============================================================================

elif page == "Key Output Health":
    st.header("✅ Key Output Health")
    st.write("Quick status check for the files the dashboard depends on.")

    health_df = pd.DataFrame([file_info(p) for p in IMPORTANT_OUTPUTS])
    st.dataframe(health_df[["status", "relative_path", "type", "size_mb", "modified"]], use_container_width=True)

    st.subheader("Quick summaries")

    summary_files = [
        PROJECT_ROOT / "data" / "processed" / "manager_week_summary_2526.csv",
        PROJECT_ROOT / "data" / "processed" / "manager_season_summary_2526.csv",
        PROJECT_ROOT / "data" / "processed" / "lineup_quality_summary_2526.csv",
        PROJECT_ROOT / "data" / "processed" / "matchup_week_summary_2526.csv",
        *ANALYTICS_FILES.values(),
    ]

    for path in summary_files:
        with st.expander(path.name, expanded=False):
            if not path.exists():
                st.error("Missing")
                continue

            df, err = load_preview(str(path), max_rows=100000)
            if err or df is None:
                st.error(err or "Could not load")
                continue

            c1, c2, c3 = st.columns(3)
            c1.metric("Rows", f"{len(df):,}")
            c2.metric("Columns", f"{len(df.columns):,}")
            if "fantrax_gw" in df.columns:
                c3.metric("Max GW", str(pd.to_numeric(df["fantrax_gw"], errors="coerce").max()))
            else:
                c3.metric("Size MB", file_info(path)["size_mb"])

            st.dataframe(df.head(20), use_container_width=True)


# =============================================================================
# PAGE: REPORTS
# =============================================================================

elif page == "Reports":
    st.header("📄 Reports")
    st.write("View validation, refresh, and analytics reports.")

    report_paths = [
        PROJECT_ROOT / "processed_data" / "fantrax_api" / "validation_report.txt",
        PROJECT_ROOT / "data" / "processed" / "api_merge_validation_report_2526.txt",
        PROJECT_ROOT / "data" / "analytics_views" / "league_awards_report.txt",
    ]

    refresh_reports = PROJECT_ROOT / "data" / "processed" / "refresh_reports"
    if refresh_reports.exists():
        report_paths.extend(sorted(refresh_reports.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)[:10])

    existing = [p for p in report_paths if p.exists()]
    if not existing:
        st.warning("No reports found yet.")
        st.stop()

    selected = st.selectbox("Report", [str(p.relative_to(PROJECT_ROOT)) for p in existing])

    path = PROJECT_ROOT / selected
    st.caption(str(path))
    st.text_area("Report contents", path.read_text(encoding="utf-8", errors="replace"), height=750)
