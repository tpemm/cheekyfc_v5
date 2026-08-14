"""Searchable live player database, profile, comparison, and free agents."""
from __future__ import annotations

from typing import Any
import pandas as pd
import streamlit as st

from components.presentation import SHARED_COMPONENT_CSS, page_header, percentile_bar, section_header
from components.player_radar import build_player_radar, comparison_values_frame, raw_values_frame
from analytics.players.comparison_catalog import CATALOG, MODE_DEFAULTS, MODES, PERCENTILE_BASES, PRESETS, RATE_BASES, metrics_for_mode, validate_metrics
from analytics.players.comparison import COMPARE_KEY, add_compare, clear_compare, deterministic_tags, radar_records, remove_compare, stable_player_id
from fantrax.live.player_performance import aggregate_player_window
from core.services.data_manager import DataManager
from core.services.season_manager import SeasonManager
from views.live_league_hub import _load


def filter_players(frame: pd.DataFrame, *, search: str = "", club: str = "All", position: str = "All", owner: str = "All", ownership: str = "All", drafted: str = "All", minimum_minutes: float = 0) -> pd.DataFrame:
    result=frame.copy()
    if search: result=result[result["player_name"].fillna("").str.contains(search,case=False,regex=False)]
    if club != "All": result=result[result["premier_league_club"].eq(club)]
    if position != "All": result=result[result["fantrax_position"].fillna("").str.split(r"[,/]",regex=True).apply(lambda values: position in [v.strip() for v in values])]
    if owner != "All": result=result[result["current_manager_name"].fillna("Free Agent").eq(owner)]
    if ownership != "All": result=result[result["ownership_status"].eq(ownership)]
    if drafted != "All": result=result[result["drafted"].fillna(False).astype(bool).eq(drafted == "Drafted")]
    return result[pd.to_numeric(result.get("historical_minutes"),errors="coerce").fillna(0).ge(minimum_minutes)]


def sort_players(frame: pd.DataFrame, field: str, ascending: bool) -> pd.DataFrame:
    result=frame.copy(); numeric=pd.to_numeric(result.get(field),errors="coerce")
    result=result.assign(_missing=numeric.isna(),_sort=numeric if numeric.notna().any() else result.get(field))
    return result.sort_values(["_missing","_sort"],ascending=[True,ascending],kind="stable",na_position="last").drop(columns=["_missing","_sort"])


def comparison_table(frame: pd.DataFrame, player_ids: list[str]) -> pd.DataFrame:
    selected=frame[frame["fantrax_player_id"].astype(str).isin([str(x) for x in player_ids])].set_index("fantrax_player_id")
    metrics=(("Draft Score","draft_score"),("Draft Rank","draft_rank"),("ADP","adp"),("Projected Points","fantrax_projected_points"),("Historical Points / 90","historical_points_per_90"),("Historical Ghost / 90","historical_ghost_per_90"),("Historical xGI / 90","historical_xgi_per_90"),("Historical Start %","historical_start_percentage"),("Projected Minutes %","projected_minutes_percentage"),("Team Strength","team_strength_percentile"),("Fixture Ease","next_five_fixture_ease_percentile"),("Current Owner","current_manager_name"),("Position Eligibility","fantrax_position"))
    names={pid:selected.loc[pid,"player_name"] for pid in selected.index}
    return pd.DataFrame([{"Metric":label,**{names[pid]:selected.loc[pid].get(column) for pid in selected.index}} for label,column in metrics])


def profile_tags(row: pd.Series) -> list[str]:
    return deterministic_tags(row)


@st.cache_data(show_spinner=False)
def apply_live_window(frame: pd.DataFrame, weekly: pd.DataFrame, window: str) -> tuple[pd.DataFrame,str]:
    totals,label=aggregate_player_window(weekly,window)
    if totals.empty: return frame.copy(),label
    mapping={"fantasy_points":"current_fantasy_points","fantasy_points_per_game":"current_points_per_game","fantasy_points_per_start":"current_points_per_start","fantasy_points_per_90":"current_points_per_90","ghost_points":"current_ghost_points","ghost_points_per_game":"current_ghost_per_game","ghost_points_per_start":"current_ghost_per_start","ghost_points_per_90":"current_ghost_per_90","start":"current_starts","appearance":"current_appearances","minutes":"current_minutes","start_percentage":"current_start_percentage","minutes_per_game":"current_minutes_per_game","xg":"current_xg","xa":"current_xa","xgi":"current_xgi","xgi_per_game":"current_xgi_per_game","xgi_per_start":"current_xgi_per_start","xgi_per_90":"current_xgi_per_90"}
    for metric in ("goals","assists","shots","shots_on_target","key_passes","accurate_crosses","successful_dribbles","tackles_won","interceptions","clearances","blocks","aerials_won","yellow_cards","red_cards","clean_sheets","saves"):
        mapping[metric]=f"current_{metric}"
        for suffix in ("per_game","per_start","per_90"):
            if f"{metric}_{suffix}" in totals: mapping[f"{metric}_{suffix}"]=f"current_{metric}_{suffix}"
    overlay=totals[["fantrax_player_id",*[column for column in mapping if column in totals]]].rename(columns=mapping)
    base=frame.drop(columns=[column for column in mapping.values() if column in frame],errors="ignore")
    return base.merge(overlay,on="fantrax_player_id",how="left"),label


def _open_player(click_key: str, ids: list[str]) -> None:
    click=st.session_state.get(click_key)
    if click and 0 <= int(click["row"]) < len(ids): st.session_state["live_player_id"]=ids[int(click["row"])]


def _metric_grid(ui: Any, row: pd.Series, metrics: tuple[tuple[str,str],...]) -> None:
    columns=ui.columns(4)
    for index,(label,key) in enumerate(metrics):
        value=row.get(key); numeric=pd.to_numeric(value,errors="coerce")
        columns[index%4].metric(label,"—" if pd.isna(numeric) else f"{numeric:,.1f}")


def _profile_controls(ui: Any, *, prefix: str, default_mode: str = "Projection") -> tuple[str,str,str,tuple[str,...]]:
    controls=ui.columns(3)
    mode=controls[0].selectbox("Profile Mode",MODES,index=MODES.index(default_mode),key=f"{prefix}_mode")
    rate=controls[1].selectbox("Rate Basis",RATE_BASES,index=3,key=f"{prefix}_rate")
    basis=controls[2].selectbox("Percentile Basis",PERCENTILE_BASES,key=f"{prefix}_basis")
    preset_names=list(PRESETS)+["Custom"]
    preset=ui.selectbox("Radar Preset",preset_names,index=(preset_names.index("Projection") if mode=="Projection" else preset_names.index("Historical Production") if mode=="Historical" else len(preset_names)-1),key=f"{prefix}_preset")
    allowed=metrics_for_mode(mode)
    defaults=PRESETS.get(preset,MODE_DEFAULTS[mode]); defaults=tuple(key for key in defaults if key in allowed)
    if len(defaults)<4: defaults=MODE_DEFAULTS[mode]
    labels={CATALOG[key].label:key for key in allowed}
    selected_labels=ui.multiselect("Customize Metrics (4–8)",list(labels),default=[CATALOG[key].label for key in defaults if key in CATALOG],max_selections=8,key=f"{prefix}_metrics")
    keys=tuple(labels[label] for label in selected_labels)
    if len(keys)<4:
        ui.warning("Choose at least four metrics to draw a reliable profile.")
    return mode,rate,basis,keys


def _dynamic_profile(ui:Any, frame:pd.DataFrame, players:pd.DataFrame, *, prefix:str, default_mode:str="Projection") -> None:
    mode,rate,basis,keys=_profile_controls(ui,prefix=prefix,default_mode=default_mode)
    if mode=="Current Season" and not any(CATALOG[key].field_for(rate) in frame.columns and pd.to_numeric(frame[CATALOG[key].field_for(rate)],errors="coerce").notna().any() for key in keys):
        ui.info("2026/27 performance data will appear after the first completed scoring period."); return
    if not 4<=len(keys)<=8: return
    validate_metrics(keys,mode=mode)
    records=radar_records(frame,players,keys,rate,basis); figure=build_player_radar(records)
    if figure is None: ui.warning("Fewer than four selected metrics have valid data. Choose another mode or metric set."); return
    ui.plotly_chart(figure,use_container_width=True,key=f"{prefix}_radar")
    ui.dataframe(comparison_values_frame(records) if len(records)>1 else raw_values_frame(records),hide_index=True,use_container_width=True)
    if any(metric["low_peers"] for record in records for metric in record["metrics"]): ui.warning("One or more positional peer groups contain fewer than five valid players; interpret percentiles cautiously.")
    ui.caption(f"{basis} percentiles · {rate} basis · presentation-derived from registered live player analytics. Missing values are not plotted as zero.")


def _profile(ui: Any, row: pd.Series, events: pd.DataFrame, history: pd.DataFrame, frame:pd.DataFrame|None=None) -> None:
    section_header(ui,str(row.get("player_name","Player")),f"{row.get('premier_league_club','')} · {row.get('fantrax_position','')} · {row.get('current_manager_name') or 'Free Agent'}",eyebrow="Live player profile")
    ui.caption(" · ".join(profile_tags(row)) or "Current roster and draft-day context")
    if pd.notna(pd.to_numeric(row.get("current_fantasy_points"),errors="coerce")):
        section_header(ui,"Current Performance","Completed-period 2026/27 facts for the selected window.")
        _metric_grid(ui,row,(("Season Points","current_fantasy_points"),("Points / Start","current_points_per_start"),("Ghost / Start","current_ghost_per_start"),("xGI / 90","current_xgi_per_90"),("Starts","current_starts"),("Minutes","current_minutes")))
        _metric_grid(ui,row,(("Goals","current_goals"),("Assists","current_assists"),("Key Passes","current_key_passes"),("Tackles Won","current_tackles_won"),("Interceptions","current_interceptions"),("Aerials Won","current_aerials_won")))
    state=getattr(ui,"session_state",st.session_state)
    if ui.button("Add to Compare",key=f"profile_compare_{stable_player_id(row)}"):
        added,message=add_compare(state,stable_player_id(row)); (ui.success if added else ui.info)(message)
    section_header(ui,"Primary Decision Strip","Forward-looking and historical decision context.")
    _metric_grid(ui,row,(("Projection","fantrax_projected_points"),("Draft Score","draft_score"),("Points / 90","historical_points_per_90"),("Ghost / 90","historical_ghost_per_90"),("xGI / 90","historical_xgi_per_90"),("Projected Minutes %","projected_minutes_percentage")))
    mini=[]
    for label,field in (("Projected Minutes","projected_minutes_percentage"),("Club Strength","team_strength_percentile"),("Fixture Ease","next_five_fixture_ease_percentile")):
        value=pd.to_numeric(row.get(field),errors="coerce"); mini.append(percentile_bar(label,None if pd.isna(value) else value,value="Natural context"))
    ui.markdown("".join(mini),unsafe_allow_html=True)
    if frame is not None:
        section_header(ui,"Dynamic Profile","Change the analytical mode, rate basis, peer group, or controlled metric set.")
        _dynamic_profile(ui,frame,row.to_frame().T,prefix=f"profile_{stable_player_id(row)}")
    section_header(ui,"Live Ownership","Current state and verified observation history.")
    _metric_grid(ui,row,(("Ownership changes","ownership_change_count"),("Draft round","draft_round"),("Overall pick","overall_pick"),("Projected points","fantrax_projected_points")))
    section_header(ui,"Draft-Day Baseline","Frozen information from draft day.")
    _metric_grid(ui,row,(("Draft Score","draft_score"),("Draft Rank","draft_rank"),("ADP","adp"),("Value vs ADP","value_vs_adp")))
    section_header(ui,"Historical Fantasy Production","2025/26 production; not current-season performance.")
    _metric_grid(ui,row,(("Fantasy points","historical_fantasy_points"),("Points / appearance","historical_points_per_appearance"),("Points / start","historical_points_per_start"),("Points / 90","historical_points_per_90")))
    if pd.notna(pd.to_numeric(row.get("current_fantasy_points"),errors="coerce")):
        section_header(ui,"2025/26 vs 2026/27","Rate comparison; current coverage is separate from full historical totals.")
        comparison=pd.DataFrame([{"Metric":label,"2025/26":row.get(historical),"2026/27":row.get(current)} for label,historical,current in (("Points / Start","historical_points_per_start","current_points_per_start"),("Points / 90","historical_points_per_90","current_points_per_90"),("Ghost / Start","historical_ghost_per_start","current_ghost_per_start"),("Ghost / 90","historical_ghost_per_90","current_ghost_per_90"),("xGI / 90","historical_xgi_per_90","current_xgi_per_90"),("Start %","historical_start_percentage","current_start_percentage"),("Minutes / Game","historical_minutes_per_game","current_minutes_per_game"))])
        ui.dataframe(comparison,hide_index=True,use_container_width=True)
    section_header(ui,"Ghost Floor","2025/26 non-goal/assist scoring context.")
    _metric_grid(ui,row,(("Ghost points","historical_ghost_points"),("Ghost / appearance","historical_ghost_per_appearance"),("Ghost / start","historical_ghost_per_start"),("Ghost / 90","historical_ghost_per_90")))
    section_header(ui,"Attacking Output","Player-level Understat expected goals and assists.")
    _metric_grid(ui,row,(("xG","historical_xg"),("xA","historical_xa"),("xGI","historical_xgi"),("xGI / 90","historical_xgi_per_90")))
    section_header(ui,"Playing Time","Historical usage and separate 2026/27 projection.")
    _metric_grid(ui,row,(("Historical minutes","historical_minutes"),("Historical starts","historical_starts"),("Projected Minutes %","projected_minutes_percentage"),("Minutes confidence","minutes_confidence")))
    section_header(ui,"Club and Fixtures","Supported preseason context.")
    _metric_grid(ui,row,(("Club strength %","team_strength_percentile"),("Next 5 ease %","next_five_fixture_ease_percentile")))
    section_header(ui,"Current Season","2026/27 performance data will appear after Gameweek 1.")
    ui.info("Season performance data begins after Gameweek 1. Current rosters and draft-day analytics are available.")
    section_header(ui,"Ownership History","Observed manager intervals and roster-status changes.")
    pid=str(row.get("fantrax_player_id")); owned=history[history.get("fantrax_player_id",pd.Series(index=history.index)).astype(str).eq(pid)]
    changed=events[events.get("fantrax_player_id",pd.Series(index=events.index)).astype(str).eq(pid)]
    if owned.empty and changed.empty: ui.info("No ownership changes detected since the initial snapshot.")
    else:
        if not owned.empty: ui.dataframe(owned,use_container_width=True,hide_index=True)
        if not changed.empty: ui.dataframe(changed,use_container_width=True,hide_index=True)


def render(season_id: str, *, data_manager: DataManager | None = None, season_manager: SeasonManager | None = None, ui: Any = st) -> None:
    seasons=season_manager or SeasonManager(); data=data_manager or DataManager(season_manager=seasons); namespace=seasons.resolve_namespace(season_id)
    ui.markdown(SHARED_COMPONENT_CSS,unsafe_allow_html=True); page_header(ui,"Players","Search ownership, draft-day baselines, historical production, and available players.",eyebrow="Player database",badge="2026/27 · Live")
    frame=_load(data,"live_player_analytics",season_id,namespace,ui); events=_load(data,"roster_change_events",season_id,namespace,ui); history=_load(data,"roster_history",season_id,namespace,ui); weekly=_load(data,"current_player_weekly",season_id,namespace,ui)
    if frame.empty: ui.info("Run Refresh League in Operations Center to build live player analytics."); return
    if weekly.empty:
        window_label="No completed scoring periods"
    else:
        window=ui.selectbox("Performance window",["Season","Last 3","Last 5","Last 10"],key="live_player_window"); frame,window_label=apply_live_window(frame,weekly,window); ui.caption(f"Current performance coverage: {window_label}")
    tabs=ui.tabs(["Player Database","Player Profile","Player Comparison","Available Players"])
    with tabs[0]:
        a,b,c,d=ui.columns(4); search=a.text_input("Player search"); club=b.selectbox("Club",["All"]+sorted(frame["premier_league_club"].dropna().astype(str).unique())); position=c.selectbox("Fantrax position",["All","G","D","M","F"]); ownership=d.selectbox("Ownership status",["All"]+sorted(frame["ownership_status"].dropna().astype(str).unique()))
        e,f,g,h=ui.columns(4); owner=e.selectbox("Current manager",["All"]+sorted(frame["current_manager_name"].dropna().astype(str).unique())); drafted=f.selectbox("Drafted",["All","Drafted","Undrafted"]); minimum=g.number_input("Minimum historical minutes",min_value=0,value=0,step=90); sort_field=h.selectbox("Sort field",["draft_rank","draft_score","adp","fantrax_projected_points","historical_points_per_90"])
        ascending=ui.radio("Sort direction",["Descending","Ascending"],horizontal=True)=="Ascending"
        filtered=sort_players(filter_players(frame,search=search,club=club,position=position,owner=owner,ownership=ownership,drafted=drafted,minimum_minutes=minimum),sort_field,ascending)
        display=filtered.rename(columns={"player_name":"Player","premier_league_club":"Club","fantrax_position":"Fantrax Position","current_manager_name":"Owner","roster_status":"Roster Status","draft_round":"Draft Round","overall_pick":"Overall Pick","draft_rank":"Draft Rank","draft_score":"Draft Score","adp":"ADP","fantrax_projected_points":"Projected Points","historical_points_per_90":"Historical Points / 90","historical_ghost_per_90":"Historical Ghost / 90","historical_xgi_per_90":"Historical xGI / 90","historical_start_percentage":"Historical Start %","projected_minutes_percentage":"Projected Minutes %","minutes_outlook":"Minutes Outlook","team_strength_percentile":"Team Strength %","next_five_fixture_ease_percentile":"Next 5 Fixture Ease %"})
        if not weekly.empty: display=display.rename(columns={"current_fantasy_points":"Season Points","current_points_per_start":"Points / Start","current_ghost_per_start":"Ghost / Start","current_starts":"Starts","current_minutes":"Minutes","current_start_percentage":"Start %","current_xgi_per_90":"xGI / 90"})
        cols=[c for c in ("Player","Club","Fantrax Position","Owner","Roster Status","Season Points","Points / Start","Ghost / Start","Starts","Minutes","Start %","xGI / 90","Projected Points","Next 5 Fixture Ease %","Draft Round","Overall Pick","Draft Rank","Draft Score","ADP","Historical Points / 90","Historical Ghost / 90","Historical xGI / 90","Historical Start %","Projected Minutes %","Minutes Outlook","Team Strength %") if c in display]
        if ui is st:
            key="live_player_click"; config={"Player":st.column_config.ButtonColumn("Player",on_click=_open_player,args=(key,filtered["fantrax_player_id"].astype(str).tolist()),key=key)}
            ui.data_editor(display[cols],hide_index=True,use_container_width=True,disabled=[x for x in cols if x!="Player"],column_config=config,key="live_player_database")
        else: ui.dataframe(display[cols],hide_index=True,use_container_width=True)
    with tabs[1]:
        options=dict(zip(frame["player_name"].fillna("Unknown").astype(str)+" · "+frame["fantrax_player_id"].astype(str),frame["fantrax_player_id"].astype(str)))
        default=next((label for label,pid in options.items() if pid==str(st.session_state.get("live_player_id",""))),next(iter(options)))
        label=ui.selectbox("Player",list(options),index=list(options).index(default)); _profile(ui,frame[frame["fantrax_player_id"].astype(str).eq(options[label])].iloc[0],events,history,frame)
    with tabs[2]:
        state=getattr(ui,"session_state",st.session_state); state.setdefault(COMPARE_KEY,[])
        id_series=frame.apply(stable_player_id,axis=1); labels=frame["player_name"].fillna("Unknown").astype(str)+" · "+id_series
        label_to_id=dict(zip(labels,id_series)); selected_ids=[pid for pid in state.get(COMPARE_KEY,[]) if pid in set(id_series)]
        chosen=ui.multiselect("Compare 2–5 players",list(label_to_id),default=[label for label,pid in label_to_id.items() if pid in selected_ids],max_selections=5,key="player_compare_selector")
        chosen_ids=[label_to_id[label] for label in chosen]; state[COMPARE_KEY]=chosen_ids
        if chosen_ids:
            remove_cols=ui.columns(len(chosen_ids)+1)
            for column,pid in zip(remove_cols,chosen_ids):
                name=frame.loc[id_series.eq(pid),"player_name"].iat[0]
                if column.button(f"Remove {name}",key=f"remove_compare_{pid}"): remove_compare(state,pid); ui.rerun()
            if remove_cols[-1].button("Clear comparison",key="clear_player_compare"): clear_compare(state); ui.rerun()
        if len(chosen_ids)<2: ui.info("Choose at least two players to compare; up to five are supported.")
        else:
            selected=frame[id_series.isin(chosen_ids)].copy(); selected["_order"]=selected.apply(lambda row:chosen_ids.index(stable_player_id(row)),axis=1); selected=selected.sort_values("_order")
            if len(selected)==2:
                names=selected["player_name"].tolist(); section_header(ui,f"{names[0]} vs {names[1]}","Shared scale and peer distribution; no synthetic winner is declared.",eyebrow="Head-to-head")
                ui.caption(" · ".join(profile_tags(selected.iloc[0]))+"  |  "+" · ".join(profile_tags(selected.iloc[1])))
            else: section_header(ui,f"{len(selected)}-Player Comparison","One shared axis set and percentile distribution for every player.",eyebrow="Group comparison")
            _dynamic_profile(ui,frame,selected,prefix="comparison")
    with tabs[3]:
        available=frame[frame["available"].fillna(False).astype(bool)]; available=sort_players(available,"draft_score",False)
        ui.info("Available Players uses current Fantrax ownership and draft-day/historical context; it is not an in-season waiver recommendation.")
        ui.dataframe(available[[c for c in ("player_name","premier_league_club","fantrax_position","current_fantasy_points","current_points_per_start","current_ghost_per_start","current_xgi_per_90","current_goals","current_assists","current_key_passes","current_minutes","draft_rank","draft_score","fantrax_projected_points","historical_points_per_90","historical_ghost_per_90","historical_xgi_per_90","projected_minutes_percentage","next_five_fixture_ease_percentile") if c in available]],hide_index=True,use_container_width=True)
