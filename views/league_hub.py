"""League Hub page backed by the foundation data services."""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from components.charts import apply_chart_theme, position_rank_axis
from components.presentation import metric_card, section_header

from core.models.data_result import DataStatus
from core.services.data_manager import (
    DataManager,
    DatasetNotFoundError,
    DatasetValidationError,
    UnsupportedFormatError,
)
from core.services.season_manager import SeasonManager


DATASET_KEYS: tuple[str, ...] = (
    "league_table",
    "league_hub_cards",
    "manager_profile_summary",
    "manager_streaks",
    "lineup_changes",
    "closest_games",
    "biggest_blowouts",
    "weekly_awards",
    "award_leaderboards",
    "matchup_week_summary",
    "scoring_periods",
)

HISTORICAL_HUB_CSS="""<style>
.summary-card,.reward-card{background:var(--ft-card-background);border:1px solid var(--ft-border);border-radius:12px;box-shadow:0 4px 14px rgba(23,33,43,.045)}
.summary-card{padding:14px 16px;min-height:108px}.summary-label{color:var(--ft-text-secondary);font-size:.7rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase}.summary-value{color:var(--ft-text-primary);font-size:1.35rem;font-weight:800;line-height:1.15;margin:.35rem 0}.summary-detail{color:var(--ft-text-muted);font-size:.76rem}
.reward-card{padding:15px 16px;min-height:185px}.reward-title-row{display:flex;justify-content:space-between;align-items:flex-start;gap:.65rem;border-bottom:1px solid var(--ft-muted-border);padding-bottom:.58rem;margin-bottom:.68rem}.reward-title{font-size:.94rem;font-weight:800;line-height:1.2;text-align:left}.reward-metric{font-size:.62rem;color:var(--ft-text-muted);font-weight:700;letter-spacing:.055em;line-height:1.25;text-align:right;text-transform:uppercase}.award-podium{display:grid;grid-template-columns:minmax(0,1fr) 4.5rem;gap:.52rem .75rem;align-items:baseline}.award-name{font-size:.77rem;color:var(--ft-text-secondary);font-weight:550;line-height:1.25}.award-value{font-size:.78rem;color:var(--ft-text-secondary);font-weight:750;text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.award-first{color:var(--ft-text-primary);font-size:.84rem;font-weight:850}.award-place{display:inline-block;width:1.35rem;color:var(--ft-text-muted);font-size:.68rem;font-weight:700}.award-link{text-decoration:none;color:inherit}
.stDataFrame [data-testid="stDataFrameResizable"]{border-color:var(--ft-border)}.stDataFrame thead th{font-weight:800!important}.stDataFrame tbody tr:hover{background:rgba(148,163,184,.07)}.stDataFrame th,.stDataFrame td{padding-top:.42rem!important;padding-bottom:.42rem!important;font-variant-numeric:tabular-nums}
.hub-panel-title{font-size:1.08rem;font-weight:800;color:var(--ft-text-primary);margin-top:1.2rem}.hub-panel-copy{font-size:.78rem;color:var(--ft-text-secondary);margin:.1rem 0 .65rem}
@media(max-width:900px){.summary-card{min-height:96px}.reward-card{min-height:172px}}
</style>"""

def historical_chart_frames(matchup_week:pd.DataFrame)->tuple[pd.DataFrame,pd.DataFrame]:
    """Presentation-only weekly scoring and cumulative league-position history."""
    required={"fantrax_gw","api_team_name","starter_fantasy_points","computed_result"}
    if matchup_week.empty or not required.issubset(matchup_week.columns): return pd.DataFrame(),pd.DataFrame()
    work=matchup_week[list(required)].copy(); work["fantrax_gw"]=pd.to_numeric(work["fantrax_gw"],errors="coerce"); work["starter_fantasy_points"]=pd.to_numeric(work["starter_fantasy_points"],errors="coerce"); work=work.dropna(subset=["fantrax_gw"])
    scoring=work.pivot_table(index="fantrax_gw",columns="api_team_name",values="starter_fantasy_points",aggfunc="last").sort_index()
    ranks=[]
    for week in sorted(work["fantrax_gw"].unique()):
        upto=work[work["fantrax_gw"].le(week)].copy(); result=upto["computed_result"].astype(str).str.upper(); upto["Wins"]=result.eq("W").astype(int); upto["Ties"]=result.eq("T").astype(int)
        table=upto.groupby("api_team_name",as_index=False).agg(Wins=("Wins","sum"),Ties=("Ties","sum"),Points=("starter_fantasy_points","sum")).sort_values(["Wins","Ties","Points","api_team_name"],ascending=[False,False,False,True],kind="stable"); table["Rank"]=range(1,len(table)+1)
        ranks.extend({"Gameweek":int(week),"Manager":row.api_team_name,"Rank":int(row.Rank)} for row in table.itertuples())
    position=pd.DataFrame(ranks).pivot(index="Gameweek",columns="Manager",values="Rank") if ranks else pd.DataFrame()
    return scoring,position

def historical_highlights(matchup_week:pd.DataFrame,streaks:pd.DataFrame,closest:pd.DataFrame,blowouts:pd.DataFrame)->list[tuple[str,str,str,str]]:
    items=[]
    if not matchup_week.empty:
        scores=pd.to_numeric(matchup_week.get("starter_fantasy_points"),errors="coerce")
        if scores.notna().any():
            high=matchup_week.loc[scores.idxmax()]; low=matchup_week.loc[scores.idxmin()]
            items.extend([("Highest Weekly Score",_clean_display_name(high.get("api_team_name")),f"GW {int(high.get('fantrax_gw'))} · {scores.max():.1f} pts","positive"),("Lowest Weekly Score",_clean_display_name(low.get("api_team_name")),f"GW {int(low.get('fantrax_gw'))} · {scores.min():.1f} pts","negative")])
    if not streaks.empty:
        wins=pd.to_numeric(streaks.get("longest_win_streak"),errors="coerce"); losses=pd.to_numeric(streaks.get("longest_losing_streak"),errors="coerce")
        if wins.notna().any(): items.append(("Hottest Manager",_clean_display_name(streaks.loc[wins.idxmax()].get("api_team_name")),f"{int(wins.max())}-match win streak","positive"))
        if losses.notna().any(): items.append(("Coldest Manager",_clean_display_name(streaks.loc[losses.idxmax()].get("api_team_name")),f"{int(losses.max())}-match losing streak","negative"))
    for label,source,tone,ascending in (("Closest Match",closest,"warning",True),("Biggest Blowout",blowouts,"accent",False)):
        if not source.empty:
            margin_col=next((column for column in ("abs_margin","point_margin_vs_opponent","margin") if column in source),None)
            margins=pd.to_numeric(source[margin_col],errors="coerce").abs() if margin_col else pd.Series(index=source.index,dtype=float)
            if margins.notna().any():
                row=source.loc[margins.idxmin() if ascending else margins.idxmax()]; opponent=_clean_display_name(row.get("opponent_team_name")); matchup=_clean_display_name(row.get("api_team_name"))+(f" vs {opponent}" if opponent else ""); week=pd.to_numeric(row.get("fantrax_gw"),errors="coerce"); detail=(f"GW {int(week)} · " if pd.notna(week) else "")+f"{float(margins.loc[row.name]):.1f}-point margin"; items.append((label,matchup,detail,tone))
    return items


def historical_previous_rank_lookup(matchup_week: pd.DataFrame) -> dict[str, int]:
    """Rank teams after the gameweek before the finalized completed period."""
    required={"fantrax_gw","api_team_name","computed_result","starter_fantasy_points"}
    if matchup_week.empty or not required.issubset(matchup_week.columns): return {}
    work=matchup_week[list(required)].copy()
    work["fantrax_gw"]=pd.to_numeric(work["fantrax_gw"],errors="coerce")
    result_text=work["computed_result"].astype("string").str.upper()
    completed_weeks=work.loc[result_text.isin(["W","L","T"]),"fantrax_gw"].dropna()
    if completed_weeks.empty: return {}
    prior=work[work["fantrax_gw"].lt(completed_weeks.max())].copy()
    if prior.empty: return {}
    prior_result=prior["computed_result"].astype("string").str.upper()
    prior=prior[prior_result.isin(["W","L","T"])].copy()
    prior["Wins"]=prior["computed_result"].astype(str).str.upper().eq("W").astype(int)
    prior["Ties"]=prior["computed_result"].astype(str).str.upper().eq("T").astype(int)
    prior["Points"]=pd.to_numeric(prior["starter_fantasy_points"],errors="coerce").fillna(0)
    table=prior.groupby("api_team_name",as_index=False).agg(Wins=("Wins","sum"),Ties=("Ties","sum"),Points=("Points","sum"))
    table["Team"]=table["api_team_name"].map(_clean_display_name)
    table=table.sort_values(["Wins","Ties","Points","Team"],ascending=[False,False,False,True],kind="stable").reset_index(drop=True)
    table["Previous Rank"]=table.index+1
    return dict(zip(table["Team"],table["Previous Rank"]))


def format_historical_movement(current: Any, previous: Any) -> str:
    if pd.isna(current) or previous is None or pd.isna(previous): return "\u2014"
    movement=int(previous)-int(current)
    return f"\u25b2{movement}" if movement>0 else f"\u25bc{abs(movement)}" if movement<0 else "\u2014"


def render(
    season_id: str,
    *,
    data_manager: DataManager | None = None,
    season_manager: SeasonManager | None = None,
    ui: Any = st,
) -> None:
    """Render the existing League Hub workflow."""

    seasons = season_manager or SeasonManager()
    season = seasons.context(season_id)
    namespace = seasons.resolve_namespace(season.season_id)
    data = data_manager or DataManager(season_manager=seasons)
    if season.finalized: ui.markdown(HISTORICAL_HUB_CSS,unsafe_allow_html=True)

    ui.markdown(
        '<div class="section-eyebrow">Season Overview · Finalized Historical Season</div>' if season.finalized else '<div class="section-eyebrow">Season overview</div>',
        unsafe_allow_html=True,
    )
    ui.markdown(
        '<div class="section-title">League Hub</div>',
        unsafe_allow_html=True,
    )
    ui.markdown(
        '<div class="section-copy">Standings, weekly form, lineup decisions, '
        "and the seasonâ€™s leading awards.</div>",
        unsafe_allow_html=True,
    )

    frames = {
        key: _load_frame(data, key, season.season_id, namespace, ui)
        for key in DATASET_KEYS
    }
    league_table = frames["league_table"]
    cards = frames["league_hub_cards"]
    profile = frames["manager_profile_summary"]
    streaks = frames["manager_streaks"]
    lineup_changes = frames["lineup_changes"]
    closest = frames["closest_games"]
    blowouts = frames["biggest_blowouts"]
    weekly_awards = frames["weekly_awards"]
    award_leaderboards = frames["award_leaderboards"]
    matchup_week = frames["matchup_week_summary"]
    scoring_periods = frames["scoring_periods"]

    # Retain the existing data dependency even though the current renderer's
    # headline cards are calculated from the other League Hub datasets.
    _ = cards

    if league_table.empty:
        ui.warning("The league table is missing for this season.")
        ui.stop()
        return

    standings = league_table.copy()
    if not profile.empty and "api_team_name" in profile.columns:
        profile_cols = [
            column
            for column in [
                "api_team_name",
                "season_efficiency_pct",
                "efficiency_pct",
                "ghost_points",
                "weeks",
            ]
            if column in profile.columns
        ]
        if profile_cols:
            standings = standings.merge(
                profile[profile_cols].drop_duplicates("api_team_name"),
                on="api_team_name",
                how="left",
                suffixes=("", "_profile"),
            )

    if not lineup_changes.empty and "view_type" in lineup_changes.columns:
        season_lineups = lineup_changes[
            lineup_changes["view_type"] == "season_summary"
        ].copy()
        if not season_lineups.empty:
            season_lineups["Lineup Changes"] = (
                pd.to_numeric(
                    season_lineups["total_starter_changes"],
                    errors="coerce",
                )
                / 2
            )
            standings = standings.merge(
                season_lineups[["api_team_name", "Lineup Changes"]],
                on="api_team_name",
                how="left",
            )
    if "Lineup Changes" not in standings.columns:
        standings["Lineup Changes"] = pd.NA

    weeks = pd.to_numeric(standings.get("weeks"), errors="coerce")
    if weeks.isna().all() or (weeks <= 0).all():
        weeks = pd.Series(1, index=standings.index, dtype=float)

    starter_points = pd.to_numeric(
        standings.get("total_starter_points"),
        errors="coerce",
    )
    standings["Points / GW"] = pd.to_numeric(
        standings.get("avg_starter_points"),
        errors="coerce",
    )
    standings["Points / GW"] = standings["Points / GW"].fillna(
        starter_points / weeks
    )
    standings["Ghost / GW"] = (
        pd.to_numeric(standings.get("ghost_points"), errors="coerce") / weeks
    )

    efficiency_col = next(
        (
            column
            for column in ["season_efficiency_pct", "efficiency_pct"]
            if column in standings.columns
        ),
        None,
    )
    standings["Efficiency"] = (
        pd.to_numeric(standings[efficiency_col], errors="coerce")
        if efficiency_col
        else pd.Series(pd.NA, index=standings.index)
    )

    standings["Current Rank"] = pd.to_numeric(
        standings.get("official_rank"),
        errors="coerce",
    )
    standings["Team"] = standings.get("api_team_name", "")
    standings["Record"] = standings.get("official_record", "")

    previous_rank_lookup = historical_previous_rank_lookup(matchup_week)

    def format_movement(row: pd.Series) -> str:
        current = row.get("Current Rank")
        previous = previous_rank_lookup.get(row.get("Team"))
        if pd.isna(current) or previous is None:
            return "â€”"
        movement = int(previous) - int(current)
        if movement > 0:
            return f"â–² {movement}"
        if movement < 0:
            return f"â–¼ {abs(movement)}"
        return "â€”"

    standings["Rank"] = standings["Current Rank"].round().astype("Int64")
    standings["Move"] = standings.apply(format_movement, axis=1)
    if not streaks.empty and "result_sequence" in streaks.columns:
        form_lookup = {}
        for _, row in streaks.iterrows():
            results = "".join(
                character
                for character in str(row.get("result_sequence", ""))
                if character in "WLT"
            )[-5:]
            form_lookup[row.get("api_team_name", "")] = " ".join(
                {"W": "ðŸŸ¢", "L": "ðŸ”´", "T": "ðŸŸ¡"}.get(
                    character,
                    character,
                )
                for character in results
            )
        standings["Form"] = standings["Team"].map(form_lookup).fillna("")
    else:
        standings["Form"] = ""

    # Normalize legacy mojibake-prone glyphs with explicit Unicode escapes.
    def clean_movement(row: pd.Series) -> str:
        current=row.get("Current Rank"); previous=previous_rank_lookup.get(row.get("Team"))
        if pd.isna(current) or previous is None: return "\u2014"
        movement=int(previous)-int(current)
        return f"\u25b2 {movement}" if movement>0 else f"\u25bc {abs(movement)}" if movement<0 else "\u2014"
    standings["Move"]=standings.apply(
        lambda row: format_historical_movement(
            row.get("Current Rank"),
            previous_rank_lookup.get(_clean_display_name(row.get("Team"))),
        ),
        axis=1,
    )
    if not streaks.empty and "result_sequence" in streaks:
        clean_form={row.get("api_team_name",""):" ".join({"W":"\U0001f7e2","L":"\U0001f534","T":"\U0001f7e1"}[result] for result in str(row.get("result_sequence", "")) if result in "WLT")[-9:] for _,row in streaks.iterrows()}
        standings["Form"]=standings["Team"].map(clean_form).fillna("")

    standings = standings.sort_values(
        ["Current Rank", "Team"],
        na_position="last",
    )
    table = standings[
        [
            "Rank",
            "Team",
            "Move",
            "Record",
            "Form",
            "Points / GW",
            "Ghost / GW",
            "Efficiency",
            "Lineup Changes",
        ]
    ].copy()
    table["Points / GW"] = table["Points / GW"].round(1)
    table["Ghost / GW"] = table["Ghost / GW"].round(1)
    table["Efficiency"] = pd.to_numeric(
        table["Efficiency"],
        errors="coerce",
    ).round(1)
    table["Lineup Changes"] = (
        pd.to_numeric(table["Lineup Changes"], errors="coerce")
        .round()
        .astype("Int64")
    )

    champion = standings.iloc[0]["Team"] if len(standings) else "â€”"
    max_week = 0
    if not weekly_awards.empty and "fantrax_gw" in weekly_awards.columns:
        max_week_value = pd.to_numeric(
            weekly_awards["fantrax_gw"],
            errors="coerce",
        ).max()
        max_week = int(max_week_value) if pd.notna(max_week_value) else 0

    if season.finalized:
        next_gameweek_value = "Season complete"
        next_gameweek_detail = f"Champion Â· {champion}"
    else:
        next_gameweek_value = f"GW {max_week + 1}" if max_week else "Upcoming"
        next_gameweek_detail = "Next league matchup period"

    month_manager_name = "Not enough data"
    month_manager_detail = "Best monthly record Â· fantasy points tiebreaker"

    required_matchup_cols = {
        "fantrax_gw",
        "api_team_name",
        "computed_result",
        "starter_fantasy_points",
    }
    if (
        not matchup_week.empty
        and not scoring_periods.empty
        and required_matchup_cols.issubset(matchup_week.columns)
        and {"fantrax_gw", "period_start"}.issubset(scoring_periods.columns)
    ):
        month_map = scoring_periods[["fantrax_gw", "period_start"]].copy()
        month_map["fantrax_gw"] = pd.to_numeric(
            month_map["fantrax_gw"],
            errors="coerce",
        )
        month_map["period_start"] = pd.to_datetime(
            month_map["period_start"],
            errors="coerce",
        )
        month_map = month_map.dropna(subset=["fantrax_gw", "period_start"])
        month_map["month_key"] = (
            month_map["period_start"].dt.to_period("M").astype(str)
        )
        month_map["month_label"] = month_map["period_start"].dt.strftime(
            "%B %Y"
        )

        monthly = matchup_week.copy()
        monthly["fantrax_gw"] = pd.to_numeric(
            monthly["fantrax_gw"],
            errors="coerce",
        )
        monthly["starter_fantasy_points"] = pd.to_numeric(
            monthly["starter_fantasy_points"],
            errors="coerce",
        ).fillna(0)
        monthly = monthly.merge(
            month_map[["fantrax_gw", "month_key", "month_label"]],
            on="fantrax_gw",
            how="left",
        ).dropna(subset=["month_key"])

        if not monthly.empty:
            monthly["Win"] = (
                monthly["computed_result"].astype(str).str.upper().eq("W").astype(int)
            )
            monthly["Tie"] = (
                monthly["computed_result"].astype(str).str.upper().eq("T").astype(int)
            )
            monthly["Loss"] = (
                monthly["computed_result"].astype(str).str.upper().eq("L").astype(int)
            )
            monthly_summary = (
                monthly.groupby(
                    ["month_key", "month_label", "api_team_name"],
                    as_index=False,
                )
                .agg(
                    Wins=("Win", "sum"),
                    Ties=("Tie", "sum"),
                    Losses=("Loss", "sum"),
                    Points=("starter_fantasy_points", "sum"),
                    Gameweeks=("fantrax_gw", "nunique"),
                )
            )
            latest_month_key = monthly_summary["month_key"].max()
            latest_month = monthly_summary[
                monthly_summary["month_key"].eq(latest_month_key)
            ].copy()
            latest_month = latest_month.sort_values(
                ["Wins", "Ties", "Points", "api_team_name"],
                ascending=[False, False, False, True],
            )
            if not latest_month.empty:
                motm = latest_month.iloc[0]
                month_manager_name = _clean_display_name(motm["api_team_name"])
                record_bits = [f"{int(motm['Wins'])}W"]
                if int(motm["Ties"]):
                    record_bits.append(f"{int(motm['Ties'])}T")
                record_bits.append(f"{int(motm['Losses'])}L")
                month_manager_detail = (
                    f"{motm['month_label']} Â· {'â€“'.join(record_bits)} Â· "
                    f"{motm['Points']:.1f} pts"
                )

    latest_jester_name = "â€”"
    latest_jester_detail = "No weekly Jester available"
    if not weekly_awards.empty and "award_name" in weekly_awards.columns:
        jesters = weekly_awards[
            weekly_awards["award_name"].astype(str).str.casefold().eq("jester")
        ].copy()
        if not jesters.empty and "fantrax_gw" in jesters.columns:
            jester_gw = pd.to_numeric(jesters["fantrax_gw"], errors="coerce")
            latest_gw_value = jester_gw.max()
            if pd.notna(latest_gw_value):
                latest_gw = int(latest_gw_value)
                latest = jesters[jester_gw.eq(latest_gw)]
                latest_jester_name = " / ".join(
                    latest["api_team_name"]
                    .map(_clean_display_name)
                    .astype(str)
                    .tolist()
                )
                if "metric_value" in latest.columns:
                    score = pd.to_numeric(
                        latest["metric_value"],
                        errors="coerce",
                    ).min()
                    latest_jester_detail = (
                        f"GW {latest_gw} Â· {score:.1f} starter points"
                        if pd.notna(score)
                        else f"GW {latest_gw}"
                    )
                else:
                    latest_jester_detail = f"GW {latest_gw}"

    summary_cols = ui.columns(3, gap="large")
    summary_items = [
        ("Next Gameweek", next_gameweek_value, next_gameweek_detail),
        ("Manager of the Month", month_manager_name, month_manager_detail),
        ("Latest Jester", latest_jester_name, latest_jester_detail),
    ]
    for column, (label, value, detail) in zip(summary_cols, summary_items):
        with column:
            summary_html = (
                f'<div class="summary-card"><div class="summary-label">{label}</div>'
                f'<div class="summary-value">{value}</div>'
                f'<div class="summary-detail">{detail}</div></div>'
            )
            ui.markdown(summary_html, unsafe_allow_html=True)

    ui.markdown(
        '<div class="hub-panel-title">Final League Table</div>' if season.finalized else '<div class="hub-panel-title">League Table</div>',
        unsafe_allow_html=True,
    )
    ui.markdown(
        '<div class="hub-panel-copy">Form shows the last five completed matchups. '
        "Lineup Changes counts starting-XI swaps between consecutive gameweeks; "
        "bench-only moves do not count.</div>",
        unsafe_allow_html=True,
    )

    def style_movement(value: Any) -> str:
        text_value = str(value)
        base = "font-size: 0.76rem; font-weight: 750;"
        if text_value.startswith("\u25b2"):
            return base + " color: #4f9d69;"
        if text_value.startswith("\u25bc"):
            return base + " color: #d66b6b;"
        return base + " color: #94a3b8;"

    styled_table = table.style.map(style_movement, subset=["Move"])
    ui.dataframe(
        styled_table,
        use_container_width=True,
        hide_index=True,
        height=520,
        column_config={
            "Rank": ui.column_config.NumberColumn(
                "Rank",
                width="small",
                format="%d",
            ),
            "Team": ui.column_config.TextColumn("Team", width="large"),
            "Move": ui.column_config.TextColumn(
                "",
                width="small",
                help="Movement from the previous completed gameweek.",
            ),
            "Record": ui.column_config.TextColumn("Record", width="medium"),
            "Form": ui.column_config.TextColumn(
                "Form",
                width="medium",
                help="â— win Â· â—‹ loss Â· â€“ tie",
            ),
            "Form": ui.column_config.TextColumn(
                "Form", width="medium", help="Green dot: win · red dot: loss · yellow dot: tie",
            ),
            "Points / GW": ui.column_config.NumberColumn(
                "Pts / GW",
                width="small",
                format="%.1f",
            ),
            "Ghost / GW": ui.column_config.NumberColumn(
                "Ghost / GW",
                width="small",
                format="%.1f",
            ),
            "Efficiency": ui.column_config.NumberColumn(
                "Efficiency %",
                width="small",
                format="%.1f%%",
            ),
            "Lineup Changes": ui.column_config.NumberColumn(
                "Lineup Changes",
                width="medium",
                format="%d",
                help=(
                    "Starting-XI swaps between consecutive gameweeks. Bench-only "
                    "changes and adds/drops that do not alter the XI are excluded."
                ),
            ),
        },
    )

    ui.markdown('<div class="hub-panel-title">Season Awards</div>',unsafe_allow_html=True)
    ui.markdown('<div class="hub-panel-copy">Headline season leaders and league records.</div>',unsafe_allow_html=True)
    if award_leaderboards.empty: ui.info("No season award leaderboards are available yet.")
    else: _render_awards(ui,award_leaderboards,streaks,closest,blowouts)

    if season.finalized:
        section_header(ui,"League Highlights","The defining weekly scores, streaks, and matchups from the finalized season.")
        highlights=historical_highlights(matchup_week,streaks,closest,blowouts)
        for start in range(0,len(highlights),3):
            highlight_columns=ui.columns(3,gap="medium")
            for column,(label,value,detail,tone) in zip(highlight_columns,highlights[start:start+3]):
                with column: metric_card(ui,label,value,detail,tone=tone)

        scoring_history,position_history=historical_chart_frames(matchup_week)
        section_header(ui,"Season Trends","Final weekly scoring and league-position history.")
        chart_columns=ui.columns(2,gap="large")
        with chart_columns[0]:
            ui.markdown('<div class="hub-panel-title">Weekly Scoring</div><div class="hub-panel-copy">Official starter fantasy points by manager and gameweek.</div>',unsafe_allow_html=True)
            if scoring_history.empty: ui.info("Weekly scoring history is unavailable.")
            else:
                figure=go.Figure()
                for manager in scoring_history.columns: figure.add_trace(go.Scatter(x=scoring_history.index,y=scoring_history[manager],mode="lines",name=_clean_display_name(manager),hovertemplate=f"{_clean_display_name(manager)}<br>GW %{{x}} · %{{y:.1f}} pts<extra></extra>"))
                ui.plotly_chart(apply_chart_theme(figure,height=380),use_container_width=True,config={"displayModeBar":False})
        with chart_columns[1]:
            ui.markdown('<div class="hub-panel-title">League-Position History</div><div class="hub-panel-copy">Cumulative record ranking after each completed gameweek; rank one is highest.</div>',unsafe_allow_html=True)
            if position_history.empty: ui.info("League-position history is unavailable.")
            else:
                figure=go.Figure()
                for manager in position_history.columns: figure.add_trace(go.Scatter(x=position_history.index,y=position_history[manager],mode="lines",line_shape="hv",name=_clean_display_name(manager),hovertemplate=f"{_clean_display_name(manager)}<br>GW %{{x}} · Rank %{{y:.0f}}<extra></extra>"))
                ui.plotly_chart(position_rank_axis(apply_chart_theme(figure,height=380)),use_container_width=True,config={"displayModeBar":False})

    ui.markdown("<div style='height: 20px'></div>", unsafe_allow_html=True)


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
        ui.warning(
            "; ".join(messages) if messages else "Dataset validation failed."
        )
    return (
        result.data.copy()
        if isinstance(result.data, pd.DataFrame)
        else pd.DataFrame()
    )


def _render_awards(
    ui: Any,
    award_leaderboards: pd.DataFrame,
    streaks: pd.DataFrame,
    closest: pd.DataFrame,
    blowouts: pd.DataFrame,
) -> None:
    award_specs = [
        ("Golden Boot", "Golden Boot", "Starter Goals"),
        ("Golden Assist", "Playmaker", "Starter Assists"),
        ("Golden Gloves", "Golden Glove", "Starter Clean Sheets"),
        ("Jester", "Jester", "Weekly Jester Wins"),
        ("Biggest Blowout", "Biggest Blowout", "Largest Winning Margin"),
        ("Closest Game", "Closest Game", "Smallest Winning Margin"),
        ("Longest Win Streak", "Longest Win Streak", "Consecutive Wins"),
        ("Longest Losing Streak", "Longest Losing Streak", "Consecutive Losses"),
    ]

    def award_value(row: pd.Series, award_name: str = "") -> str:
        for column in [
            "leaderboard_value",
            "season_total",
            "weekly_award_wins",
            "best_week_value",
        ]:
            if column in row.index and pd.notna(row.get(column)):
                value = _format_value(row.get(column))
                if award_name in {"Closest Game", "Biggest Blowout"}:
                    return f"({value} pts)"
                return value
        return "â€”"

    for start_idx in range(0, len(award_specs), 4):
        reward_cols = ui.columns(4, gap="medium")
        for offset, column in enumerate(reward_cols):
            idx = start_idx + offset
            if idx >= len(award_specs):
                continue
            source_award, display_title, metric_label = award_specs[idx]
            leaderboard = _build_special_award_leaderboard(
                source_award,
                award_leaderboards,
                streaks,
                closest,
                blowouts,
            )
            if "rank" in leaderboard.columns:
                leaderboard["_rank"] = pd.to_numeric(
                    leaderboard["rank"],
                    errors="coerce",
                )
                leaderboard = leaderboard.sort_values("_rank")
            elif "leaderboard_value" in leaderboard.columns:
                leaderboard = leaderboard.sort_values(
                    "leaderboard_value",
                    ascending=False,
                )
            rows_html = []
            for place, (_, row) in enumerate(
                leaderboard.head(3).iterrows(),
                start=1,
            ):
                css_class = " award-first" if place == 1 else ""
                name_text = _clean_display_name(row.get("api_team_name", ""))
                rows_html.append(
                    f'<div class="award-name{css_class}">'
                    f'<span class="award-place">{place}.</span>{name_text}</div>'
                    f'<div class="award-value{css_class}">'
                    f"{award_value(row, source_award)}</div>"
                )
            if not rows_html:
                rows_html = [
                    '<div class="award-name">No results</div>'
                    '<div class="award-value">â€”</div>'
                ]
            award_url = (
                f'?page=Award%20Detail&award={source_award.replace(" ", "%20")}'
            )
            html = (
                f'<a class="award-link" href="{award_url}" target="_self">'
                '<div class="reward-card">'
                '<div class="reward-title-row">'
                f'<div class="reward-title">{display_title}</div>'
                f'<div class="reward-metric">{metric_label}</div>'
                "</div>"
                f'<div class="award-podium">{"".join(rows_html)}</div>'
                "</div></a>"
            )
            with column:
                ui.markdown(html, unsafe_allow_html=True)


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
