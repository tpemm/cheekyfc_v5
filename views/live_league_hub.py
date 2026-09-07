"""Concise 2026/27 League Hub using registered live datasets only."""
from __future__ import annotations
from typing import Any
import numpy as np
import pandas as pd
import streamlit as st

from components.presentation import SHARED_COMPONENT_CSS, page_header, section_header
from core.models.data_result import DataStatus
from core.services.data_manager import DataManager,DatasetNotFoundError,DatasetValidationError,UnsupportedFormatError
from core.services.season_manager import SeasonManager
from fantrax.live.league_analytics import (
    build_live_league_summary,compact_league_table,jester_history,
    configured_manager_of_month,league_highlights,manager_active_season_totals,manager_award_leaderboards,scoring_frames,
)
from fantrax.live.league_lineups import manager_performance_weeks
from fantrax.live.current_state import get_current_state, freshness_caption, overlay_current_standings

LIVE_DATASET_KEYS=("league_teams","league_standings","weekly_matchups","manager_week_summary","cup_configuration","cup_matchups","league_active_player_weekly","current_player_weekly")
HEADLINE_CARD_CSS="""<style>.hub-headline-card{min-height:112px;height:100%;display:flex;flex-direction:column;justify-content:flex-start}.hub-headline-card .ft-kpi-value{font-size:1.15rem}.hub-leaderboard{min-height:165px}.hub-leader-row{display:grid;grid-template-columns:1.2rem 1fr auto;gap:.35rem;padding:.3rem 0;border-bottom:1px solid var(--ft-border);font-size:.78rem}.hub-leader-row:first-of-type{font-weight:800}</style>"""

def movement_style(value:Any)->str:
    text=str(value)
    if text.startswith("\u25b2"):return "color: #16a34a; font-weight: 700"
    if text.startswith("\u25bc"):return "color: #dc2626; font-weight: 700"
    return ""


def form_presentation(value:Any)->str:
    if pd.isna(value):return ""
    colors={"W":"\U0001f7e2", "L":"\U0001f534", "D":"\U0001f7e1", "T":"\U0001f7e1"}
    return " ".join(f"{colors[token]} {token}" if token in colors else token for token in str(value).split())


def style_league_table(table:pd.DataFrame):
    # Streamlit tables cannot color characters within a cell; retain each letter
    # with its colored result marker without changing the table layout.
    shown=table.copy();shown["Form"]=shown.Form.map(form_presentation)
    return shown.style.map(movement_style,subset=["Movement"])


def _load(data:DataManager,key:str,season_id:str,namespace:str,ui:Any)->pd.DataFrame:
    try:result=data.load_frame(key,season_id,namespace)
    except DatasetNotFoundError:return pd.DataFrame()
    except (DatasetValidationError,UnsupportedFormatError) as exc:ui.warning(str(exc));return pd.DataFrame()
    if result.status in {DataStatus.MISSING,DataStatus.EMPTY}:return pd.DataFrame()
    return result.data.copy() if isinstance(result.data,pd.DataFrame) else pd.DataFrame()

def _number(value:Any,digits:int=1)->str:
    numeric=pd.to_numeric(pd.Series([value]),errors="coerce").iat[0]
    return "\u2014" if pd.isna(numeric) else f"{numeric:,.{digits}f}"

def _numeric_column(frame:pd.DataFrame,column:str)->pd.Series:
    return pd.to_numeric(frame[column] if column in frame else pd.Series(index=frame.index,dtype=float),errors="coerce")

@st.cache_data(show_spinner=False)
def build_live_hub_model(teams:pd.DataFrame,standings:pd.DataFrame,matchups:pd.DataFrame,weeks:pd.DataFrame)->dict[str,Any]:
    periods=_numeric_column(standings,"period");latest_period=periods.max() if periods.notna().any() else np.nan
    latest=standings[periods.eq(latest_period)].copy() if pd.notna(latest_period) else standings.copy()
    if latest.empty and not teams.empty:latest=teams.rename(columns={"manager_name":"manager","fantasy_team_name":"team"}).copy();latest["rank"]=pd.NA
    identities=teams.copy()
    if identities.empty:identities=latest.rename(columns={"manager":"manager_name","team":"fantasy_team_name","rank":"current_rank"})
    seed=latest.rename(columns={"rank":"current_rank","manager":"manager_name","team":"fantasy_team_name","fantasy_points_for":"points_for","fantasy_points_against":"points_against"})
    summary=build_live_league_summary(identities,latest,weeks,seed);scoring,history=scoring_frames(weeks)
    highlights=[(item["label"],item["value"],item["detail"]) for item in league_highlights(weeks,matchups) if item["label"] in {"Highest Score","Lowest Score","Closest Match","Biggest Blowout"}]
    managers=pd.DataFrame({"manager":summary.get("manager_name",pd.Series(dtype=object)),"average_score_numeric":summary.get("average_weekly_score",pd.Series(dtype=float))})
    return {"standings":latest,"summary":summary,"managers":managers,"highlights":highlights,"position_history":history,"weekly_scoring":scoring}

def _headline(ui:Any,label:str,value:str,detail:str)->None:
    ui.markdown(f'<div class="ft-card hub-headline-card"><div class="ft-label">{label}</div><div class="ft-kpi-value">{value}</div><div class="ft-detail">{detail}</div></div>',unsafe_allow_html=True)

def _manager_award(ui:Any,label:str,frame:pd.DataFrame)->None:
    rows=[]
    for _,row in frame.iterrows():
        metric=next(column for column in frame.columns if column not in {"Rank","manager_id","Manager","Fantasy Team","Tie Count","Hidden Ties"});detail=f"{_number(row[metric],1 if metric=='Ghost Points' else 0)} {metric.lower()}"
        rows.append(f'<div class="hub-leader-row"><span>{int(row["Rank"])}.</span><span>{row["Manager"]}</span><span>{detail}</span></div>')
    hidden=int(pd.to_numeric(frame.get("Hidden Ties"),errors="coerce").max()) if not frame.empty else 0
    if hidden:rows.append(f'<div class="ft-detail">+{hidden} tied</div>')
    body="".join(rows) if rows else '<div class="ft-detail">Not available yet</div>'
    ui.markdown(f'<div class="ft-card hub-leaderboard"><div class="ft-label">{label}</div>{body}</div>',unsafe_allow_html=True)

def render(season_id:str,*,data_manager:DataManager|None=None,season_manager:SeasonManager|None=None,ui:Any=st)->None:
    seasons=season_manager or SeasonManager();namespace=seasons.resolve_namespace(season_id);data=data_manager or DataManager(season_manager=seasons)
    ui.markdown(SHARED_COMPONENT_CSS+HEADLINE_CARD_CSS,unsafe_allow_html=True);page_header(ui,"League Hub",badge="2026/27 \u00b7 Live")
    frames={key:_load(data,key,season_id,namespace,ui) for key in LIVE_DATASET_KEYS}
    if frames["league_standings"].empty and frames["league_teams"].empty:ui.info("Live league data is not available yet.");return
    live_state=get_current_state()
    ui.caption(freshness_caption(live_state))
    if not live_state["teams"].empty:frames["league_teams"]=live_state["teams"].copy()
    if not live_state["standings"].empty:frames["league_standings"]=live_state["standings"].copy()
    weeks=manager_performance_weeks(frames["manager_week_summary"],frames["current_player_weekly"])
    model=build_live_hub_model(frames["league_teams"],frames["league_standings"],frames["weekly_matchups"],weeks)
    model["summary"]=overlay_current_standings(model["summary"],live_state["standings"])
    final_weeks=weeks[~weeks.get("source_coverage",pd.Series(index=weeks.index,dtype=object)).astype(str).str.contains("live",case=False,na=False)]
    jesters=jester_history(final_weeks);latest=jesters.sort_values("period").tail(1);counts=jesters.groupby(["manager_id","manager_name"],dropna=False).size().reset_index(name="count") if not jesters.empty else pd.DataFrame()
    latest_value="Not awarded yet" if latest.empty else str(latest.iloc[0]["manager_name"]);latest_detail="" if latest.empty else f"GW {int(latest.iloc[0]['period'])} \u00b7 {_number(latest.iloc[0]['weekly_score'])} pts"
    leader_value="Not awarded yet" if counts.empty else ", ".join(counts[counts["count"].eq(counts["count"].max())]["manager_name"].astype(str));leader_detail="" if counts.empty else f"{int(counts['count'].max())} Jesters"
    motm=configured_manager_of_month(weeks);leaders=[] if motm is None else motm["current_leaders"]
    motm_label="Manager of the Month" if motm is None else f"{motm['label']} Manager of the Month"
    motm_value="In Progress" if motm and motm["completion_state"]=="in progress" else "Not awarded yet" if not leaders else ", ".join(str(row["manager_name"]) for row in leaders)
    motm_detail="" if not leaders else ("Current Leader: " if motm["completion_state"]=="in progress" else "Winner: ")+", ".join(str(row["manager_name"]) for row in leaders)
    cfg=frames["cup_configuration"].iloc[0] if not frames["cup_configuration"].empty else pd.Series(dtype=object);cup_value="Seeding" if frames["cup_matchups"].empty else "Opening Round";opening=int(cfg.get("opening_round_week")) if pd.notna(cfg.get("opening_round_week")) else 22;byes=int(cfg.get("byes")) if pd.notna(cfg.get("byes")) else 4;cup_detail=f"1st Round: GW{opening} \u00b7 Top {byes} get byes"
    cards=ui.columns(4,gap="small")
    for column,item in zip(cards,(("Latest Jester",latest_value,latest_detail),("Jester Leader",leader_value,leader_detail),(motm_label,motm_value,motm_detail),("Cup Status",cup_value,cup_detail))):
        with column:_headline(ui,*item)
    section_header(ui,"League Table");table=compact_league_table(model["summary"],weeks);ui.dataframe(style_league_table(table),use_container_width=True,hide_index=True,height=38+35*len(table))
    current_period=int(pd.to_numeric(weeks.get("period"),errors="coerce").max()) if not weeks.empty else None
    current_matchups=frames["weekly_matchups"][pd.to_numeric(frames["weekly_matchups"].get("period"),errors="coerce").eq(current_period)].copy() if current_period else pd.DataFrame()
    completed=not current_matchups.empty and current_matchups.get("status",pd.Series(index=current_matchups.index,dtype=object)).astype(str).str.lower().isin({"completed","complete","final"}).all()
    section_header(ui,f"GW{current_period} Results" if completed else f"GW{current_period} Live Matchups" if current_period else "Current GW","Completed Fantrax results." if completed else "Current Fantrax active-lineup scores; results remain provisional until the period finalizes.")
    if current_matchups.empty:ui.info("Current matchup scores are not available yet.")
    else:
        games=current_matchups.rename(columns={"home_manager":"Home","away_manager":"Away","home_score":"Home Score","away_score":"Away Score","status":"Status"})
        if completed:
            games["Home"]=games.apply(lambda row:f'{row.Home} ({"T" if row["Home Score"]==row["Away Score"] else "W" if row["Home Score"]>row["Away Score"] else "L"})',axis=1);games["Away"]=games.apply(lambda row:f'{row.Away} ({"T" if row["Home Score"]==row["Away Score"] else "W" if row["Away Score"]>row["Home Score"] else "L"})',axis=1)
        ui.dataframe(games[["Home","Home Score","Away Score","Away","Status"]],use_container_width=True,hide_index=True)
    section_header(ui,"League Highlights")
    ui.caption("Completed current-season matchup results." if completed else "Current scores are provisional; result-based awards are withheld.")
    highlight_columns=ui.columns(4,gap="small");by_label={label:(value,detail) for label,value,detail in model["highlights"]}
    for column,label in zip(highlight_columns,("Highest Score","Lowest Score","Closest Match","Biggest Blowout")):
        with column:_headline(ui,label,*by_label.get(label,("Not available yet","")))
    section_header(ui,"Season Trends")
    scoring_column,position_column=ui.columns(2,gap="large")
    with scoring_column:
        section_header(ui,"Weekly Scoring")
        if not model["weekly_scoring"].empty:ui.line_chart(model["weekly_scoring"],use_container_width=True)
    with position_column:
        section_header(ui,"League Position History")
        if not model["position_history"].empty:
            history=model["position_history"].reset_index().melt("period",var_name="Manager",value_name="Rank").dropna();ui.vega_lite_chart(history,{"mark":{"type":"line","point":True},"encoding":{"x":{"field":"period","type":"ordinal"},"y":{"field":"Rank","type":"quantitative","scale":{"reverse":True}},"color":{"field":"Manager","type":"nominal"},"tooltip":[{"field":"Manager"},{"field":"period"},{"field":"Rank"}]}},use_container_width=True)
    section_header(ui,"Manager Awards","Active XI season totals")
    boards=manager_award_leaderboards(manager_active_season_totals(frames["league_active_player_weekly"]));columns=ui.columns(4,gap="small")
    for column,label in zip(columns,("Golden Boot","Playmaker","Golden Glove","Ghost King")):
        with column:_manager_award(ui,label,boards[label])
