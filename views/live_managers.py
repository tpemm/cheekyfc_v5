"""Live manager directory and five-tab, preseason-aware profiles."""
from __future__ import annotations
from typing import Any
import pandas as pd
import streamlit as st

from components.presentation import SHARED_COMPONENT_CSS, page_header, section_header
from core.services.data_manager import DataManager
from core.services.season_manager import SeasonManager
from fantrax.live.current_state import get_current_state, overlay_player_state, overlay_manager_names, overlay_manager_roster_metrics, freshness_caption
from fantrax.live.analytics import expected_record
from views.live_league_hub import _load

WINDOWS={"Season":None,"Last 3":3,"Last 5":5,"Last 10":10}

def manager_squad(players:pd.DataFrame,manager_id:str)->pd.DataFrame:
    result=players[players.get("current_manager_id",pd.Series(index=players.index,dtype=object)).astype(str).eq(str(manager_id))].copy()
    return result.drop_duplicates("fantrax_player_id",keep="last") if "fantrax_player_id" in result else result

def manager_week_window(frame:pd.DataFrame,manager_id:str,window:str="Season")->tuple[pd.DataFrame,str]:
    result=frame[frame.get("manager_id",pd.Series(index=frame.index,dtype=object)).astype(str).eq(str(manager_id))].copy()
    score="fantasy_points" if "fantasy_points" in result else "total_score"
    result=result[pd.to_numeric(result.get(score),errors="coerce").notna()].sort_values("period") if score in result else result.iloc[0:0]
    requested=WINDOWS.get(window)
    if requested:result=result.tail(requested)
    label=window if requested is None or len(result)>=requested else f"{window} ({len(result)} completed)"
    return result,label

def _value(value:Any)->str:
    number=pd.to_numeric(value,errors="coerce")
    return "\u2014" if pd.isna(number) else f"{number:,.1f}"

def _metrics(ui:Any,row:pd.Series,definitions:tuple[tuple[str,str],...])->None:
    columns=ui.columns(min(4,len(definitions)))
    for i,(label,key) in enumerate(definitions):columns[i%len(columns)].metric(label,_value(row.get(key)))

def _actual_metrics(week:pd.DataFrame)->dict[str,float]:
    if week.empty:return {}
    score=pd.to_numeric(week.get("fantasy_points",week.get("total_score")),errors="coerce").dropna()
    return {"average":score.mean(),"median":score.median(),"sd":score.std(),"high":score.max(),"low":score.min()}

def selected_manager_id(managers:pd.DataFrame,state:dict)->str:
    ids=managers.get("manager_id",pd.Series(dtype=object)).astype(str).tolist();requested=str(state.get("live_manager_selected_id",""))
    return requested if requested in ids else (ids[0] if ids else "")

def render(season_id:str,*,data_manager:DataManager|None=None,season_manager:SeasonManager|None=None,ui:Any=st)->None:
    seasons=season_manager or SeasonManager();data=data_manager or DataManager(season_manager=seasons);namespace=seasons.resolve_namespace(season_id)
    ui.markdown(SHARED_COMPONENT_CSS,unsafe_allow_html=True);page_header(ui,"Managers","Live results, current squads, draft retention, and finalized historical context.",eyebrow="Manager directory",badge="2026/27 \u00b7 Live")
    keys=("live_manager_analytics","live_player_analytics","live_position_strength","manager_week_summary","manager_player_weekly","roster_change_events","cup_matchups","cup_records")
    frames={key:_load(data,key,season_id,namespace,ui) for key in keys};managers=frames["live_manager_analytics"];players=frames["live_player_analytics"];strength=frames["live_position_strength"];weeks=frames["manager_week_summary"];manager_players=frames["manager_player_weekly"];events=frames["roster_change_events"];cup_matchups=frames["cup_matchups"];cup_records=frames["cup_records"]
    historical=_load(data,"manager_profile_summary","2526",seasons.resolve_namespace("2526"),ui)
    if managers.empty:ui.info("Run Refresh League in Operations Center to build live manager analytics.");return
    live_state=get_current_state()
    ui.caption(freshness_caption(live_state))
    managers=overlay_manager_names(managers,live_state["teams"])
    ownership=_load(data,"player_ownership",season_id,namespace,ui)
    players=overlay_player_state(players,ownership,live_state)
    managers=overlay_manager_roster_metrics(managers,players,live_state)
    directory=managers.copy();directory["Record"]=directory[[c for c in ("wins","draws","losses") if c in directory]].apply(pd.to_numeric,errors="coerce").fillna(0).astype(int).astype(str).agg("-".join,axis=1)
    display=directory.rename(columns={"current_rank":"Rank","fantasy_team_name":"Team","manager_name":"Manager","points_for":"Points For","average_weekly_score":"Average Score","current_roster_projection":"Roster Projection","historical_points_per_90":"Historical Points / 90","current_roster_points_per_90":"Current Points / 90","current_roster_ghost_per_90":"Current Ghost / 90","draft_retention_pct":"Draft Retention %","latest_roster_change":"Recent Activity"})
    ui.dataframe(display[[c for c in ("Rank","Team","Manager","Record","Points For","Average Score","Roster Projection","Historical Points / 90","Current Points / 90","Current Ghost / 90","Draft Retention %","Recent Activity") if c in display]],hide_index=True,use_container_width=True)
    for start in range(0,len(directory),3):
        card_columns=ui.columns(3,gap="small")
        for column,card in zip(card_columns,directory.iloc[start:start+3].to_dict("records")):
            manager_card_id=str(card.get("manager_id"));team=str(card.get("fantasy_team_name") or card.get("manager_name"));record=card.get("Record","0-0-0")
            with column:
                ui.markdown(f'<div class="ft-card"><div class="ft-label">Rank {_value(card.get("current_rank"))}</div><div class="ft-kpi-value" style="font-size:1.05rem">{team}</div><div class="ft-detail">{card.get("manager_name")} · {record}</div></div>',unsafe_allow_html=True)
                if ui.button(f"Open {team}",key=f"open_live_manager_{manager_card_id}",use_container_width=True):ui.session_state["live_manager_selected_id"]=manager_card_id;ui.rerun()
    labels=(managers["fantasy_team_name"].fillna(managers["manager_name"])+" \u00b7 "+managers["manager_id"].astype(str)).tolist();active_id=selected_manager_id(managers,ui.session_state);index=next((i for i,label in enumerate(labels) if label.endswith(f" \u00b7 {active_id}")),0);selected=ui.selectbox("Open manager profile",labels,index=index,key="live_manager_profile_selector");manager_id=selected.rsplit(" \u00b7 ",1)[1];ui.session_state["live_manager_selected_id"]=manager_id;row=managers[managers["manager_id"].astype(str).eq(manager_id)].iloc[0];squad=manager_squad(players,manager_id)
    section_header(ui,str(row.get("fantasy_team_name")),str(row.get("manager_name")),eyebrow="Live manager profile")
    tabs=ui.tabs(["Overview","Performance","Squad","Decisions","Explorer"]);manager_weeks,_=manager_week_window(weeks,manager_id)
    with tabs[0]:
        _metrics(ui,row,(("Current Rank","current_rank"),("Points For","points_for"),("Points Against","points_against"),("Average Weekly Score","average_weekly_score"),("Roster Projection","current_roster_projection"),("Historical Points / 90","historical_points_per_90"),("Historical Ghost / 90","historical_ghost_per_90"),("Projected Minutes %","projected_minutes_percentage")))
        if manager_weeks.empty:ui.info("League-position history will appear after the first completed scoring period.")
        else:
            section_header(ui,"League Position History","Rank 1 is displayed at the top.");ui.line_chart(manager_weeks.set_index("period")[["rank_after_week"]].rename(columns={"rank_after_week":"Rank"}))
            section_header(ui,"Weekly Scoring","Completed periods only.");score="fantasy_points" if "fantasy_points" in manager_weeks else "total_score";ui.bar_chart(manager_weeks.set_index("period")[[score]])
        form=" ".join(manager_weeks.get("result",pd.Series(dtype=object)).dropna().astype(str).tail(5));ui.caption(f"Recent form: {form}" if form else "Form begins after the first completed matchup.")
        section_header(ui,"Historical Reference","Concise finalized 2025/26 context.")
        name=str(row.get("manager_name"));name_columns=[c for c in ("manager_name","api_team_name","team_name") if c in historical]
        old=historical[historical[name_columns[0]].astype(str).eq(name)].head(1) if name_columns else pd.DataFrame()
        if old.empty:ui.caption("No matching finalized 2025/26 manager profile was found. Open the 2025/26 season to view historical Managers.")
        else:_metrics(ui,old.iloc[0],(("2025/26 Final Rank","official_rank"),("2025/26 Average Score","average_weekly_score"),("2025/26 Consistency","consistency_score")))
        section_header(ui,"Cup","Compact tournament context.");record=cup_records[cup_records.get("manager_id",pd.Series(index=cup_records.index,dtype=object)).astype(str).eq(manager_id)].head(1) if not cup_records.empty else pd.DataFrame();involved=cup_matchups[(cup_matchups.get("home_manager_id",pd.Series(index=cup_matchups.index,dtype=object)).astype(str).eq(manager_id))|(cup_matchups.get("away_manager_id",pd.Series(index=cup_matchups.index,dtype=object)).astype(str).eq(manager_id))] if not cup_matchups.empty else pd.DataFrame()
        if record.empty and involved.empty:ui.caption("Cup seeding and matchup status will appear when the configured tournament begins.")
        elif not record.empty:_metrics(ui,record.iloc[0],(("Cup Wins","cup_wins"),("Cup Losses","cup_losses"),("Championships","championships")))
    with tabs[1]:
        section_header(ui,"Performance","How strong has this team's actual performance been?");window=ui.selectbox("Weekly window",list(WINDOWS),key="manager_performance_window");windowed,coverage=manager_week_window(weeks,manager_id,window)
        if windowed.empty:ui.info("Performance analytics will begin after the first completed scoring period. No preseason form, luck, or consistency is inferred.")
        else:
            values=_actual_metrics(windowed);cols=ui.columns(4);cols[0].metric("Average",_value(values["average"]));cols[1].metric("Median",_value(values["median"]));cols[2].metric("Consistency SD",_value(values["sd"]));cols[3].metric("High / Low",f'{_value(values["high"])} / {_value(values["low"])}');ui.caption(f"Coverage: {coverage}")
            luck=expected_record(windowed);luck=luck[luck["manager_id"].astype(str).eq(manager_id)]
            if not luck.empty:_metrics(ui,luck.iloc[0],(("Actual Wins","actual_wins"),("Expected Wins","expected_wins"),("Wins vs Expectation","luck_wins")))
        section_header(ui,"Position Strength","Basis is labeled; preseason uses draft/projection evidence.");own=strength[strength.get("manager_id",pd.Series(index=strength.index,dtype=object)).astype(str).eq(manager_id)].copy();ui.dataframe(own,hide_index=True,use_container_width=True)
    with tabs[2]:
        section_header(ui,"Current Squad","Authoritative current ownership; each player appears once.");basis=ui.selectbox("Rate basis",["Total","Per Game","Per Start","Per 90"],key="manager_squad_rate_basis");suffix={"Total":"","Per Game":"_per_game","Per Start":"_per_start","Per 90":"_per_90"}[basis]
        columns=["player_name","premier_league_club","fantrax_position","roster_status","lineup_status","drafted_manager","draft_round","overall_pick","draft_score","fantrax_projected_points",f"current_fantasy_points{suffix}",f"current_ghost_points{suffix}",f"current_xgi{suffix}","historical_points_per_90","historical_ghost_per_90","historical_start_percentage","projected_minutes_percentage"]
        ui.dataframe(squad[[c for c in columns if c in squad]],hide_index=True,use_container_width=True);section_header(ui,"Draft and Roster Management","Projection change is context, not a claim of actual improvement.");_metrics(ui,row,(("Drafted Retained","drafted_players_retained"),("Draft Retention %","draft_retention_pct"),("Acquired Later","current_roster_acquired_later"),("Roster Changes","roster_change_count")))
    with tabs[3]:
        proven=not manager_players.empty and manager_players.get("lineup_status",pd.Series(dtype=object)).astype(str).str.upper().isin({"ACTIVE","ACT","STARTER","STARTING"}).any()
        if not proven:ui.info("Lineup-decision analytics will begin once the first completed scoring period and historical lineup data are available.")
        else:section_header(ui,"Lineup Decisions","Actual submitted lineup state only.");ui.dataframe(manager_players[manager_players.get("manager_id",pd.Series(index=manager_players.index,dtype=object)).astype(str).eq(manager_id)],hide_index=True,use_container_width=True)
        if ui.checkbox("Review decision event history",key="manager_decision_review"):
            from views.manager_decision_review import render_review
            render_review(ui,manager_players,_load(data,"transaction_events",season_id,namespace,ui),_load(data,"lineup_events",season_id,namespace,ui),_load(data,"league_teams",season_id,namespace,ui),manager_id)
    with tabs[4]:
        section_header(ui,"Explorer","Registered manager events and weekly facts.");involved=events[(events.get("previous_manager_id",pd.Series(index=events.index,dtype=object)).astype(str).eq(manager_id))|(events.get("new_manager_id",pd.Series(index=events.index,dtype=object)).astype(str).eq(manager_id))] if not events.empty else events
        event_type=ui.selectbox("Event type",["All"]+sorted(involved.get("event_type",pd.Series(dtype=str)).dropna().astype(str).unique().tolist()))
        if event_type!="All":involved=involved[involved["event_type"].eq(event_type)]
        if involved.empty:ui.info("No verified roster changes detected since the initial snapshot.")
        else:ui.dataframe(involved.sort_values("detected_at",ascending=False),hide_index=True,use_container_width=True)
