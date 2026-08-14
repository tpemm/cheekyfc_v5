"""Finalized 2025/26 historical player encyclopedia."""
from __future__ import annotations
from typing import Any

import pandas as pd
import streamlit as st

from analytics.players.comparison import radar_records, stable_player_id
from analytics.players.comparison_catalog import CATALOG, PRESETS, RATE_BASES, validate_metrics
from analytics.players.historical import RATE_FIELDS, build_historical_player_frame
from components.player_radar import build_player_radar, comparison_values_frame, raw_values_frame
from components.presentation import SHARED_COMPONENT_CSS, page_header, section_header
from core.services.data_manager import DataManager
from core.services.season_manager import SeasonManager
from views.live_league_hub import _load


HISTORICAL_CSS="""<style>
.historical-player-card{background:var(--ft-card-background);border:1px solid var(--ft-border);border-radius:12px;padding:13px 14px;box-shadow:0 3px 12px rgba(23,33,43,.04)}
.historical-player-card .name{font-size:.95rem;font-weight:800}.historical-player-card .meta{font-size:.72rem;color:var(--ft-text-muted);margin:.18rem 0 .55rem}.historical-player-card .stats{display:grid;grid-template-columns:repeat(2,1fr);gap:.32rem .7rem;font-size:.73rem}.historical-player-card .stats b{text-align:right;font-variant-numeric:tabular-nums}
</style>"""

HISTORICAL_PRESETS={
    "Balanced Profile":PRESETS["Historical Balanced"],
    "Historical Production":PRESETS["Historical Production"],
    "Floor & Minutes":PRESETS["Historical Floor & Minutes"],
    "Attacking Upside":PRESETS["Historical Attacking Upside"],
}


@st.cache_data(show_spinner=False)
def prepare_historical_players(master: pd.DataFrame, draft_snapshot: pd.DataFrame) -> pd.DataFrame:
    return build_historical_player_frame(master,draft_snapshot)


def filter_historical_players(frame: pd.DataFrame, *, search: str="", club: str="All", position: str="All", minimum_minutes: float=0, minimum_starts: float=0) -> pd.DataFrame:
    result=frame.copy()
    if search: result=result[result["player_name"].fillna("").str.contains(search,case=False,regex=False)]
    if club!="All": result=result[result["premier_league_club"].eq(club)]
    if position!="All": result=result[result["fantrax_position"].fillna("").str.split(r"[,/]",regex=True).apply(lambda values:position in [value.strip() for value in values])]
    minutes=pd.to_numeric(result["historical_minutes"],errors="coerce"); starts=pd.to_numeric(result["historical_starts"],errors="coerce")
    return result[minutes.fillna(0).ge(minimum_minutes) & starts.fillna(0).ge(minimum_starts)]


def historical_database_columns(rate_basis: str) -> tuple[str,...]:
    return ("player_name","premier_league_club","fantrax_position",*RATE_FIELDS[rate_basis],"historical_appearances","historical_starts","historical_minutes","historical_start_percentage","historical_minutes_per_game")


def historical_comparison_table(frame: pd.DataFrame, player_ids: list[str]) -> pd.DataFrame:
    selected=frame[frame.apply(stable_player_id,axis=1).isin(player_ids)].copy()
    metrics=(("Season Points","historical_fantasy_points"),("Points / Game","historical_points_per_appearance"),("Points / Start","historical_points_per_start"),("Points / 90","historical_points_per_90"),("Ghost / Start","historical_ghost_per_start"),("Ghost / 90","historical_ghost_per_90"),("Start %","historical_start_percentage"),("xGI / 90","historical_xgi_per_90"))
    return pd.DataFrame([{"Stat":label,**{row["player_name"]:row.get(field) for _,row in selected.iterrows()}} for label,field in metrics])


def _number(value: Any, digits: int=1) -> str:
    numeric=pd.to_numeric(value,errors="coerce")
    return "—" if pd.isna(numeric) else f"{numeric:,.{digits}f}"


def _metrics(ui: Any, row: pd.Series, specs: tuple[tuple[str,str],...]) -> None:
    columns=ui.columns(4)
    for index,(label,field) in enumerate(specs): columns[index%4].metric(label,_number(row.get(field)))


def _radar_controls(ui: Any, prefix: str) -> tuple[tuple[str,...],str,str]:
    controls=ui.columns(3)
    preset=controls[0].selectbox("Radar preset",[*HISTORICAL_PRESETS,"Custom"],key=f"{prefix}_preset")
    rate=controls[1].selectbox("Rate basis",RATE_BASES,index=3,key=f"{prefix}_rate")
    peer=controls[2].selectbox("Comparison basis",["League","Position"],key=f"{prefix}_peer")
    allowed=tuple(key for key,metric in CATALOG.items() if "Historical" in metric.modes)
    defaults=HISTORICAL_PRESETS.get(preset,HISTORICAL_PRESETS["Balanced Profile"])
    labels={CATALOG[key].label:key for key in allowed}
    chosen=ui.multiselect("Radar metrics (4–8)",list(labels),default=[CATALOG[key].label for key in defaults],max_selections=8,key=f"{prefix}_metrics")
    return tuple(labels[label] for label in chosen),rate,peer


def _radar(ui: Any, frame: pd.DataFrame, selected: pd.DataFrame, prefix: str) -> None:
    keys,rate,peer=_radar_controls(ui,prefix)
    if not 4<=len(keys)<=8: ui.info("Choose between four and eight supported historical metrics."); return
    validate_metrics(keys,mode="Historical"); records=radar_records(frame,selected,keys,rate,peer); figure=build_player_radar(records)
    if figure is None: ui.info("Insufficient finalized data for four valid radar axes."); return
    ui.plotly_chart(figure,use_container_width=True,key=f"{prefix}_radar")
    ui.dataframe(comparison_values_frame(records) if len(selected)>1 else raw_values_frame(records),hide_index=True,use_container_width=True)
    ui.caption(f"{peer} percentiles · {rate} basis · finalized 2025/26 facts. Missing values are excluded, never converted to zero.")


def _player_card(row: pd.Series) -> str:
    return (f'<div class="historical-player-card"><div class="name">{row.get("player_name","")}</div><div class="meta">{row.get("premier_league_club","")} · {row.get("fantrax_position","")}</div><div class="stats">'
        f'<span>Season Points</span><b>{_number(row.get("historical_fantasy_points"))}</b><span>Points / Start</span><b>{_number(row.get("historical_points_per_start"))}</b><span>Ghost / Start</span><b>{_number(row.get("historical_ghost_per_start"))}</b><span>Start %</span><b>{_number(row.get("historical_start_percentage"))}</b><span>xGI / 90</span><b>{_number(row.get("historical_xgi_per_90"),2)}</b></div></div>')


def _profile(ui: Any, frame: pd.DataFrame, row: pd.Series, draft: pd.DataFrame) -> None:
    section_header(ui,str(row.get("player_name")),f'{row.get("premier_league_club","")} · {row.get("fantrax_position","")}',eyebrow="2025/26 finalized historical player")
    _metrics(ui,row,(("Season Points","historical_fantasy_points"),("Points / Start","historical_points_per_start"),("Ghost / Start","historical_ghost_per_start"),("Starts","historical_starts"),("Start %","historical_start_percentage"),("Minutes","historical_minutes"),("xGI / 90","historical_xgi_per_90")))
    section_header(ui,"Fantasy Profile","Percentile profile with exact finalized values below the chart."); _radar(ui,frame,row.to_frame().T,f"historical_profile_{stable_player_id(row)}")
    section_header(ui,"Fantasy Production","Totals and valid-denominator rates."); _metrics(ui,row,(("Points","historical_fantasy_points"),("Points / Game","historical_points_per_appearance"),("Points / Start","historical_points_per_start"),("Points / 90","historical_points_per_90"),("Ghost Points","historical_ghost_points"),("Ghost / Game","historical_ghost_per_appearance"),("Ghost / Start","historical_ghost_per_start"),("Ghost / 90","historical_ghost_per_90")))
    section_header(ui,"Attacking Profile","Finalized goals, assists, and Understat expected output."); _metrics(ui,row,(("Goals","historical_goals"),("Assists","historical_assists"),("xG","historical_xg"),("xA","historical_xa"),("xGI","historical_xgi"),("xG / 90","historical_xg_per_90"),("xA / 90","historical_xa_per_90"),("xGI / 90","historical_xgi_per_90")))
    section_header(ui,"Playing Time / Reliability","Historical participation only."); _metrics(ui,row,(("Games","historical_appearances"),("Starts","historical_starts"),("Minutes","historical_minutes"),("Start %","historical_start_percentage"),("Minutes / Game","historical_minutes_per_game")))
    section_header(ui,"2026/27 Draft-Day Context","Frozen preseason context; not 2025/26 performance.")
    pid=str(row.get("fantrax_player_id")); context=draft[draft.get("historical_fantrax_player_id",draft.get("fantrax_player_id",pd.Series(index=draft.index))).astype(str).str.strip("*").eq(pid)] if not draft.empty else draft
    if context.empty: ui.info("No matched frozen draft-day context is available for this historical player.")
    else:
        d=context.iloc[0]; _metrics(ui,d,(("Draft Rank","overall_rank"),("Draft Score","draft_score"),("Draft-Day Projection","fantrax_projected_points"),("Draft-Day ADP","fantrax_adp"),("Projected Minutes %","projected_minutes_share")))


def render(season_id: str="2526", *, data_manager: DataManager|None=None, season_manager: SeasonManager|None=None, ui: Any=st) -> None:
    seasons=season_manager or SeasonManager(); data=data_manager or DataManager(season_manager=seasons); namespace=seasons.resolve_namespace(season_id)
    ui.markdown(SHARED_COMPONENT_CSS+HISTORICAL_CSS,unsafe_allow_html=True); page_header(ui,"Players","Finalized fantasy production, floor, playing time, and attacking output.",eyebrow="Historical player encyclopedia",badge="2025/26 · Finalized Historical Data")
    master=_load(data,"master_player_weekly",season_id,namespace,ui); draft=_load(data,"draft_day_rankings_snapshot","2627","working",ui)
    if master.empty: ui.info("Finalized historical player data is unavailable."); return
    frame=prepare_historical_players(master,draft)
    tabs=ui.tabs(["Player Database","Player Profile","Compare Players"])
    with tabs[0]:
        a,b,c=ui.columns(3); search=a.text_input("Search player",key="historical_search"); club=b.selectbox("Club",["All"]+sorted(frame["premier_league_club"].dropna().astype(str).unique()),key="historical_club"); position=c.selectbox("Position",["All","G","D","M","F"],key="historical_position")
        d,e,f=ui.columns(3); minimum_minutes=d.number_input("Minimum minutes",min_value=0,value=0,step=90,key="historical_minutes"); minimum_starts=e.number_input("Minimum starts",min_value=0,value=0,step=1,key="historical_starts"); rate=f.radio("Rate basis",RATE_BASES,horizontal=True,key="historical_rate")
        filtered=filter_historical_players(frame,search=search,club=club,position=position,minimum_minutes=minimum_minutes,minimum_starts=minimum_starts)
        display=filtered[list(historical_database_columns(rate))].rename(columns={"player_name":"Player","premier_league_club":"Club","fantrax_position":"Position","historical_fantasy_points":"Season Points","historical_ghost_points":"Ghost Points","historical_points_per_appearance":"Points / Game","historical_ghost_per_appearance":"Ghost / Game","historical_points_per_start":"Points / Start","historical_ghost_per_start":"Ghost / Start","historical_points_per_90":"Points / 90","historical_ghost_per_90":"Ghost / 90","historical_appearances":"Games","historical_starts":"Starts","historical_minutes":"Minutes","historical_start_percentage":"Start %","historical_minutes_per_game":"Minutes / Game"})
        ui.dataframe(display,hide_index=True,use_container_width=True)
    labels=frame["player_name"].fillna("Unknown").astype(str)+" · "+frame.apply(stable_player_id,axis=1); mapping=dict(zip(labels,frame.apply(stable_player_id,axis=1)))
    with tabs[1]:
        selected_label=ui.selectbox("Player",list(mapping),key="historical_profile_player"); row=frame[frame.apply(stable_player_id,axis=1).eq(mapping[selected_label])].iloc[0]; _profile(ui,frame,row,draft)
    with tabs[2]:
        chosen=ui.multiselect("Compare 2–5 players",list(mapping),max_selections=5,key="historical_compare")
        if len(chosen)<2: ui.info("Choose between two and five historical players.")
        else:
            ids=[mapping[label] for label in chosen]; selected=frame[frame.apply(stable_player_id,axis=1).isin(ids)].copy(); selected["_order"]=selected.apply(lambda row:ids.index(stable_player_id(row)),axis=1); selected=selected.sort_values("_order")
            cards=ui.columns(len(selected));
            for column,(_,player) in zip(cards,selected.iterrows()):
                with column: ui.markdown(_player_card(player),unsafe_allow_html=True)
            section_header(ui,"Shared Historical Profile","One percentile scale for every selected player."); _radar(ui,frame,selected,"historical_compare")
            section_header(ui,"Exact Statistical Comparison","Raw finalized values; no synthetic Winner column."); ui.dataframe(historical_comparison_table(frame,ids),hide_index=True,use_container_width=True)
