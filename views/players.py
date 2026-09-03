"""Searchable live player database, profile, and comparison."""
from __future__ import annotations

from typing import Any
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.presentation import SHARED_COMPONENT_CSS, page_header, section_header
from components.player_radar import build_player_radar, comparison_values_frame, raw_values_frame
from analytics.players.comparison_catalog import CATALOG, MODE_DEFAULTS, MODES, PERCENTILE_BASES, PRESETS, RATE_BASES, metrics_for_mode, validate_metrics
from analytics.players.comparison import COMPARE_KEY, add_compare, clear_compare, deterministic_tags, primary_position, radar_records, remove_compare, stable_player_id
from analytics.players.comparison_display import COMPARE_CARD_CSS, comparison_card_html, comparison_cards, comparison_exact_table, comparison_table_styler
from analytics.players.match_analysis import calculate_home_away_split, calculate_points_breakdown, match_research_summary, prepare_gameweek_table, prepare_last_n_periods, prepare_match_research_frame, prepare_match_research_table, prepare_player_gameweek_frame, production_distribution, supported_optional_columns
from analytics.players.profile_overview import DEFAULT_RADAR_KEYS, OVERVIEW_METRICS, exact_stats_frame, overview_radar_records, valid_radar_records
from analytics.players.research_overview import ATTACKING_AXES, DEFENSIVE_AXES, FANTASY_AXES, fixed_radar_records, fixture_cards_html, format_overview_value, historical_profile_availability, next_fixtures, overview_gameweek_table, overview_kpis, overlay_current_ownership, overlay_current_summary, overlay_historical_advanced, ownership_text, set_piece_chips
from analytics.players.ranking import sort_by_metric
from analytics.advanced_descriptive import filter_pitch_events,apply_event_window,add_plot_coordinates
from analytics.advanced_presentation import PLAYER_GROUPS, player_metric_group, player_snapshot, pitch_layer_summary, role_share_frame
from analytics.players.role_tactical import event_activity_by_zone, filter_role_scope, role_snapshot
from analytics.players.advanced import METRIC_GROUPS, aggregate_advanced, component_sources, current_historical_comparison, fantasy_contributions, fantasy_reconciliation, metric_group_frame, metric_value, overlay_fantrax_authority, positional_context, return_points
from components.player_pitch import add_lines, add_points, draw_pitch
from analytics.teams.fixtures import enrich_players_with_fixtures
from components.charts import apply_chart_theme
from fantrax.live.player_performance import aggregate_player_window
from core.services.data_manager import DataManager
from core.services.season_manager import SeasonManager
from core.services.historical_advanced import get_historical_player_advanced,load_historical_advanced_frame
from views.live_league_hub import _load

LIVE_RATE_BASES=("Per Game","Per Start","Per 90")
LIVE_RATE_FIELDS={
    "Per Game":("current_points_per_game","current_ghost_per_game","current_xgi_per_game","Pts / Game","Ghost / Game","xGI / Game"),
    "Per Start":("current_points_per_start","current_ghost_per_start","current_xgi_per_start","Pts / Start","Ghost / Start","xGI / Start"),
    "Per 90":("current_points_per_90","current_ghost_per_90","current_xgi_per_90","Pts / 90","Ghost / 90","xGI / 90"),
}
SORT_OPTIONS=("Points","Ghost","xGI","Minutes Outlook","Next 5 Fixture Ease","Projected Points")
RADAR_METRICS={
    "points":("Points","current_points","fantasy_production"),
    "ghost":("Ghost","current_ghost","ghost_floor"),
    "xgi":("xGI","current_xgi","xgi"),
    "start_rate":("Start %","current_start_rate","start_rate"),
}
RADAR_PRESETS={
    "Balanced Profile":("points","ghost","xgi","start_rate"),
    "Fantasy Production":("points","ghost","xgi"),
    "Floor & Minutes":("ghost","points","start_rate"),
    "Attacking Output":("xgi","points","start_rate"),
}


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
    return sort_by_metric(frame,field,ascending)


def _live_database_frame_legacy(frame: pd.DataFrame, rate_basis: str) -> pd.DataFrame:
    """Build the compact presentation frame without altering authoritative fields."""
    points,ghost,xgi,points_label,ghost_label,xgi_label=LIVE_RATE_FIELDS[rate_basis]
    available=frame.get("available",pd.Series(False,index=frame.index)).fillna(False).astype(bool)
    owner=frame.get("current_manager_name",pd.Series(index=frame.index,dtype=object)).fillna("").astype(str).str.strip()
    result=pd.DataFrame(index=frame.index)
    result["Player"]=frame.get("player_name")
    result["Club / Position"]=frame.get("premier_league_club",pd.Series("",index=frame.index)).fillna("").astype(str)+" · "+frame.get("fantrax_position",pd.Series("",index=frame.index)).fillna("").astype(str)
    result["Owner / Availability"]=owner.mask(available,"Available").replace("","Available")
    for label,field in ((points_label,points),(ghost_label,ghost),(xgi_label,xgi)):
        result[label]=pd.to_numeric(frame.get(field,pd.Series(pd.NA,index=frame.index)),errors="coerce")
    for label,field in (("Goals","current_goals"),("Fantrax Assists","current_assists"),("KP","current_key_passes"),("TkW","current_tackles_won"),("Int","current_interceptions"),("AER","current_aerials_won"),("Accurate Crosses","current_accurate_crosses"),("xG","current_xg"),("xA","current_xa")):
        result[label]=pd.to_numeric(frame.get(field,pd.Series(pd.NA,index=frame.index)),errors="coerce")
    result["Minutes Outlook"]=pd.to_numeric(frame.get("projected_minutes_percentage",pd.Series(pd.NA,index=frame.index)),errors="coerce")
    result["Next 5 Fixture Ease"]=pd.to_numeric(frame.get("next_five_fixture_ease_percentile",pd.Series(pd.NA,index=frame.index)),errors="coerce")
    return result


def live_database_frame(frame:pd.DataFrame,rate_basis:str)->pd.DataFrame:
    """Current-first discovery and waiver-research contract."""
    available=frame.get("available",pd.Series(False,index=frame.index)).fillna(False).astype(bool);owner=frame.get("current_manager_name",pd.Series(index=frame.index,dtype=object)).fillna("").astype(str).str.strip()
    result=pd.DataFrame(index=frame.index);result["Player"]=frame.get("player_name");result["Club"]=frame.get("premier_league_club");result["Position"]=frame.get("fantrax_position");result["Fantasy Manager / Available"]=owner.mask(available,"Available").replace("","Available");result["Ownership %"]=pd.to_numeric(frame.get("rostered_pct",pd.Series(pd.NA,index=frame.index)),errors="coerce")
    for label,field in (("FPts","current_fantasy_points"),("FPts/Game","current_points_per_game"),("FPts/Start","current_points_per_start"),("Ghost/Start","current_ghost_per_start"),("GP","current_appearances"),("Starts","current_starts"),("Minutes","current_minutes"),("Goals","current_goals"),("Assists","current_assists"),("KP","current_key_passes"),("TkW","current_tackles_won"),("Interceptions","current_interceptions"),("Aerial Wins","current_aerials_won"),("Accurate Crosses","current_accurate_crosses"),("Clean Sheets","current_clean_sheets"),("xG","current_xg"),("xA","current_xa"),("xG/90","current_xg_per_90"),("xA/90","current_xa_per_90")):
        result[label]=pd.to_numeric(frame.get(field,pd.Series(pd.NA,index=frame.index)),errors="coerce")
    return result


def live_sort_field(frame: pd.DataFrame, rate_basis: str, sort_by: str | None = None) -> str:
    points,ghost,xgi,*_=LIVE_RATE_FIELDS[rate_basis]
    mapping={"Points":points,"Ghost":ghost,"xGI":xgi,"Minutes Outlook":"projected_minutes_percentage","Next 5 Fixture Ease":"next_five_fixture_ease_percentile","Projected Points":"fantrax_projected_points"}
    if sort_by: return mapping[sort_by]
    return points if pd.to_numeric(frame.get(points,pd.Series(dtype=float)),errors="coerce").notna().any() else "fantrax_projected_points"


def historical_comparison_frame(row: pd.Series, rate_basis: str) -> pd.DataFrame:
    suffix={"Per Game":"per_game","Per Start":"per_start","Per 90":"per_90"}[rate_basis]
    historical_points="historical_points_per_appearance" if rate_basis=="Per Game" else f"historical_points_{suffix}"
    historical_ghost="historical_ghost_per_appearance" if rate_basis=="Per Game" else f"historical_ghost_{suffix}"
    pairs=((f"Points / {rate_basis.split()[-1]}",f"current_points_{suffix}",historical_points),(f"Ghost / {rate_basis.split()[-1]}",f"current_ghost_{suffix}",historical_ghost),(f"xGI / {rate_basis.split()[-1]}",f"current_xgi_{suffix}",f"historical_xgi_{suffix}"),("Start %","current_start_percentage","historical_start_percentage"),("Minutes / Game","current_minutes_per_game","historical_minutes_per_game"))
    return pd.DataFrame([{"Metric":label,"2026/27":row.get(current),"2025/26":row.get(historical)} for label,current,historical in pairs])


def season_radar_records(frame: pd.DataFrame, row: pd.Series, rate_basis: str, percentile_basis: str, metric_keys: tuple[str,...] | None = None) -> list[dict]:
    """Prepare matched-axis current/historical percentiles; missing values remain missing."""
    suffix={"Per Game":"per_game","Per Start":"per_start","Per 90":"per_90"}[rate_basis]
    hist_points="historical_points_per_appearance" if rate_basis=="Per Game" else f"historical_points_{suffix}"
    hist_ghost="historical_ghost_per_appearance" if rate_basis=="Per Game" else f"historical_ghost_{suffix}"
    fields={}
    for key,(label,current_key,historical_key) in RADAR_METRICS.items():
        current_metric=CATALOG[current_key]; historical_metric=CATALOG[historical_key]
        current_supported=rate_basis in current_metric.fields or "Natural" in current_metric.fields
        historical_supported=rate_basis in historical_metric.fields or "Natural" in historical_metric.fields
        if current_supported and historical_supported:
            fields[key]=(label,current_metric.field_for(rate_basis),historical_metric.field_for(rate_basis))
    axes=tuple(fields[key] for key in (metric_keys or tuple(RADAR_METRICS)) if key in fields)
    position=frame.apply(primary_position,axis=1)
    universe=frame if percentile_basis=="League" else frame[position.eq(primary_position(row))]
    records=[]
    for season,column_index in (("2026/27 Current",1),("2025/26 Historical",2)):
        metrics=[]
        for label,*fields in axes:
            field=fields[column_index-1]; values=pd.to_numeric(universe.get(field,pd.Series(pd.NA,index=universe.index)),errors="coerce")
            raw=pd.to_numeric(row.get(field),errors="coerce"); percentile=values.rank(method="average",pct=True).loc[row.name]*100 if row.name in values.index and pd.notna(raw) else pd.NA
            rank=values.rank(method="min",ascending=False).loc[row.name] if row.name in values.index and pd.notna(raw) else pd.NA
            metrics.append({"key":label,"label":label,"raw":raw,"formatted":"—" if pd.isna(raw) else f"{raw:,.2f}","percentile":percentile,"rank":rank,"peer_count":int(values.count()),"peer_group":percentile_basis,"source":"2026/27 live" if column_index==1 else "Finalized 2025/26","low_peers":percentile_basis=="Position" and values.count()<5})
        records.append({"player_id":stable_player_id(row),"player_name":season,"metrics":metrics})
    return records


def shared_radar_records(records: list[dict]) -> list[dict]:
    """Keep only axes with valid values in every season record."""
    if len(records)<2: return records
    valid={metric["key"] for metric in records[0]["metrics"] if pd.notna(metric["percentile"])}
    for record in records[1:]: valid&={metric["key"] for metric in record["metrics"] if pd.notna(metric["percentile"])}
    return [{**record,"metrics":[metric for metric in record["metrics"] if metric["key"] in valid]} for record in records]


def radar_diagnostics(records: list[dict]) -> dict:
    """Development/test visibility for radar eligibility without public UI noise."""
    shared=shared_radar_records(records)
    return {
        "selected_metrics":[metric["key"] for metric in records[0]["metrics"]] if records else [],
        "raw_available":{record["player_name"]:sum(pd.notna(metric["raw"]) for metric in record["metrics"]) for record in records},
        "percentiles_available":{record["player_name"]:sum(pd.notna(metric["percentile"]) for metric in record["metrics"]) for record in records},
        "shared_metric_count":len(shared[0]["metrics"]) if shared else 0,
        "peer_group_sizes":{record["player_name"]:[metric["peer_count"] for metric in record["metrics"]] for record in records},
    }


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
    if click and 0 <= int(click["row"]) < len(ids):
        st.session_state["live_player_id"]=ids[int(click["row"])]
        st.session_state["players_subview"]="Player Profile"


def _metric_grid(ui: Any, row: pd.Series, metrics: tuple[tuple[str,str],...]) -> None:
    columns=ui.columns(4)
    for index,(label,key) in enumerate(metrics):
        value=row.get(key); numeric=pd.to_numeric(value,errors="coerce")
        columns[index%4].metric(label,"—" if pd.isna(numeric) else f"{numeric:,.1f}")


def _advanced_history(ui:Any,row:pd.Series,supp:pd.DataFrame,profiles:pd.DataFrame,roles:pd.DataFrame,set_pieces:pd.DataFrame,players:pd.DataFrame=pd.DataFrame(),historical_row:pd.Series|None=None)->str|None:
    fantrax_id=str(row.get("fantrax_player_id",""));matches=supp[supp.get("fantrax_player_id",pd.Series(index=supp.index,dtype=object)).astype(str).eq(fantrax_id)].copy()
    if matches.empty: ui.info("Validated advanced observations are unavailable for this player.");return None
    canonical=str(matches.canonical_player_id.iloc[0]);profile=profiles[profiles.canonical_player_id.astype(str).eq(canonical)]
    current_observation=pd.to_datetime(matches.get('date'),errors='coerce').dt.year.max()>=2026
    rate=ui.selectbox("Rate Basis",["Total","Per Start","Per 90"],index=0 if current_observation else 2,key=f"advanced_rate_{fantrax_id}_{'current' if current_observation else 'historical'}")
    p=aggregate_advanced(matches);observed_positions=matches.get('ghost_scoring_position',pd.Series(index=matches.index,dtype=object)).dropna().astype(str);scoring_position=observed_positions.mode().iat[0] if len(observed_positions) else primary_position(row);season_label="2026/27 current" if current_observation else "2025/26 historical";section_header(ui,"Advanced Player Analytics",f"{season_label} · {rate} · {p.appearances:g} appearance(s), {p.starts:g} start(s), {'—' if pd.isna(p.minutes) else f'{p.minutes:g}'} minutes")
    production=ui.columns(4);shown=lambda value:"—" if pd.isna(value) else f"{value:,.2f}"
    basis_suffix={"Total":"","Per Start":" / Start","Per 90":" / 90"}[rate]
    for card,(label,field) in zip(production,(("FPts","fantrax_points"),("Ghost","ghost_points"),("Return Points","return_points"),("Rating","rating"))):
        raw=return_points(p,scoring_position) if field=="return_points" else p.get(field)
        value=raw if field=="rating" or rate=="Total" else (raw/p.starts if rate=="Per Start" and p.starts else raw*90/p.minutes if rate=="Per 90" and pd.notna(p.minutes) and p.minutes>0 else pd.NA);card.metric(label+(basis_suffix if field!="rating" else ""),shown(value))
    underlying=ui.columns(4)
    for card,(label,field) in zip(underlying,(("xG","xg"),("xA","xa"),("Key Passes","key_passes"),("Successful Dribbles","successful_dribbles"))):card.metric(label+basis_suffix,shown(metric_value(p,field,rate)))
    role=roles[roles.canonical_player_id.astype(str).eq(canonical)].sort_values(["manager_name","role_rank"])
    if not role.empty:
        section_header(ui,"Tactical Role","Observed starts and share; Fantrax eligibility remains separate.")
        managers=sorted(role.manager_name.dropna().astype(str).unique());manager=ui.selectbox("Manager Context",["All",*managers],key=f"advanced_manager_{fantrax_id}") if len(managers)>1 else "All"
        chart=role_share_frame(role,manager)
        if not chart.empty:ui.bar_chart(chart.set_index("Observed Role")[["Starts"]],horizontal=True)
        ui.dataframe(role.rename(columns={"manager_name":"Manager","formation":"Formation","actual_tactical_role":"Observed Role","role_starts":"Starts","role_share":"Manager Share"})[["Manager","Formation","Observed Role","Starts","Manager Share"]],hide_index=True,use_container_width=True)
    section_header(ui,"Statistical Components",f"All compatible groups use the shared {rate} denominator; percentages and rating remain fixed.")
    group_columns=ui.columns(2)
    for index,group in enumerate(METRIC_GROUPS):
        with group_columns[index%2]:
            ui.markdown(f"#### {group}");values=metric_group_frame(p,group,rate).dropna(subset=["Value"])
            if not values.empty:ui.dataframe(values[["Metric","Value"]],hide_index=True,use_container_width=True)
    pieces=set_pieces[set_pieces.canonical_player_id.astype(str).eq(canonical)&set_pieces.window.eq("SEASON")].sort_values(["set_piece_type","rank"])
    if not pieces.empty:
        section_header(ui,"Set-Piece Role","Observed hierarchy with attempt, share, and sample evidence.")
        ui.dataframe(pieces.rename(columns={"set_piece_type":"Type","rank":"Rank","attempts":"Attempts","player_share":"Share","sample_size":"Club Sample"})[["Type","Rank","Attempts","Share","Club Sample"]],hide_index=True,use_container_width=True)
    if current_observation:
        section_header(ui,"Fantasy Component Analysis","Official FPts remains authoritative; known components use the centralized 2026/27 scoring configuration.")
        contributions=fantasy_contributions(p,scoring_position,sources=component_sources(matches));recon=fantasy_reconciliation(p,contributions)
        if not contributions.empty:ui.dataframe(contributions[["Component","Stat","Scoring Weight","Fantasy Contribution","Source"]],hide_index=True,use_container_width=True)
        reconcile_cards=ui.columns(3)
        for card,(label,value) in zip(reconcile_cards,(("Observed FPts",recon["official_fpts"]),("Known Components",recon["known_component_contribution"]),("Unreconciled Difference",recon["unreconciled_difference"]))):card.metric(label,shown(value))
        ui.caption(f"Fantrax scoring position: {scoring_position} · eligibility: {row.get('fantrax_position','—')} · observed tactical role is not used as a scoring-position substitute.")
    if not players.empty and current_observation:
        metrics=(("FPts / Start","current_points_per_start"),("Ghost / Start","current_ghost_per_start"),("KP / Start","current_key_passes_per_start"),("xG / 90","current_xg_per_90"),("xA / 90","current_xa_per_90"),("CoS / Start","current_successful_dribbles_per_start"))
        context=positional_context(players,fantrax_id,row.get("fantrax_position"),metrics)
        if not context.empty:section_header(ui,"Positional / League Context","Deterministic primary Fantrax position cohort; current sample shown above.");ui.dataframe(context,hide_index=True,use_container_width=True)
    if historical_row is not None and current_observation:
        comparison=current_historical_comparison(row,historical_row,(("FPts / Start","current_points_per_start","historical_points_per_start"),("Ghost / Start","current_ghost_per_start","historical_ghost_per_start"),("xG / 90","current_xg_per_90","historical_xg_per_90"),("xA / 90","current_xa_per_90","historical_xa_per_90")))
        section_header(ui,"Current vs Historical","Absolute differences only; missing historical /90 remains missing.");ui.dataframe(comparison,hide_index=True,use_container_width=True)
    with ui.expander("Metric provenance and semantics"):
        provenance=pd.DataFrame([{"Metric":label,"Canonical Field":field,"Source":"Fantrax > validated provider observation > source-specific observation > missing","Semantics":"Rate-compatible" if field not in {"rating","pass_completion_pct","cross_success_pct","dribble_success_pct","aerial_win_pct"} else "Fixed / not rate-transformed"} for group in METRIC_GROUPS.values() for label,field in group])
        ui.dataframe(provenance.drop_duplicates(),hide_index=True,use_container_width=True)
    return canonical


def _pitch_history(ui:Any,canonical:str|None,event_data:pd.DataFrame,supp:pd.DataFrame)->None:
    if canonical is None or event_data.empty:ui.info("Event Activity is unavailable for this player and selected season.");return
    events=add_plot_coordinates(event_data[event_data.canonical_player_id.astype(str).eq(str(canonical))].copy());matches=supp[supp.canonical_player_id.astype(str).eq(str(canonical))].copy()
    if events.empty:ui.info("No recorded player events are available.");return
    controls=ui.columns(4);layer=controls[0].selectbox("Layer",["Activity Density","Passes","Key Passes","Crosses","Dribbles / TakeOns","Successful Dribbles","Shots","Defensive Actions","Recoveries","Aerials"],key=f"pitch_layer_{canonical}");window=controls[1].selectbox("Window",["Season","Last 10","Last 5",*[f"Match: {x}" for x in matches.sort_values('date').canonical_match_id.drop_duplicates().tail(10)]],key=f"pitch_window_{canonical}")
    context=controls[2].selectbox("Context",["All","Home","Away"],key=f"pitch_context_{canonical}");start_status=controls[3].selectbox("Start status",["All appearances","Starts","Subs"],key=f"pitch_starts_{canonical}")
    roles=sorted(matches.get("actual_tactical_role",pd.Series(dtype=object)).dropna().astype(str).unique());formations=sorted(matches.get("formation",pd.Series(dtype=object)).dropna().astype(str).unique())
    filters=ui.columns(2);role=filters[0].selectbox("Observed role",["All Roles",*roles],key=f"pitch_role_{canonical}") if len(roles)>1 else "All Roles";formation=filters[1].selectbox("Formation",["All Formations",*formations],key=f"pitch_formation_{canonical}") if len(formations)>1 else "All Formations"
    scoped_matches,scoped_events=filter_role_scope(matches,events,context=context,start_status=start_status,role=role,formation=formation)
    snapshot=role_snapshot(scoped_matches);cards=ui.columns(6)
    shown_value=lambda value:"—" if pd.isna(value) else str(value)
    items=(("Primary Observed Role",shown_value(snapshot["primary_role"])),("Role Share",f"{snapshot['role_share']:.0%}" if pd.notna(snapshot['role_share']) else "—"),("Starts",snapshot["starts"]),("Appearances",snapshot["appearances"]),("Min / Start",f"{snapshot['minutes_per_start']:.0f}" if pd.notna(snapshot['minutes_per_start']) else "—"),("Primary Formation",shown_value(snapshot["primary_formation"])))
    for card,(label,value) in zip(cards,items):card.metric(label,value,help=(f"Primary role share among {snapshot['role_sample']} observed starts." if label=="Role Share" else None))
    shown=apply_event_window(filter_pitch_events(scoped_events,layer),scoped_matches,window);success=shown.outcome.astype(str).eq("Successful");fig=draw_pitch()
    if layer in {"Passes","Key Passes","Crosses"}:
        add_lines(fig,shown)
    add_points(fig,shown,colors=["#2f9e44" if value else "#c92a2a" for value in success])
    ui.plotly_chart(fig,use_container_width=True,key=f"event_activity_{canonical}_{layer}_{window}");ui.caption(f"{len(shown):,} recorded actions · opponent goal at top · Event Activity, not tracking.")
    _pitch_detail(ui,shown,scoped_matches,layer)
    zones=event_activity_by_zone(shown);ui.markdown("#### Event Activity by Zone");ui.caption("Shares describe recorded player events, not touches, tracking, or position occupancy.")
    zone_cards=ui.columns(5)
    for card,(label,value) in zip(zone_cards,(("Final Third",zones["final_third_share"]),("Left",zones["left_share"]),("Center",zones["center_share"]),("Right",zones["right_share"]),("Box Events",zones["box_count"]))):card.metric(label,str(value) if label=="Box Events" else (f"{value:.1f}%" if pd.notna(value) else "—"))
    detail=[c for c in ("fantrax_period","date","opponent_id","venue","started","minutes","actual_tactical_role","formation","rating","fantrax_points","ghost_points","xg","xa") if c in scoped_matches]
    if detail:ui.markdown("#### Match-by-Match Role History");ui.dataframe(scoped_matches.sort_values("date",ascending=False).reindex(columns=detail).drop_duplicates(),hide_index=True,use_container_width=True)


def _pitch_detail(ui:Any,shown:pd.DataFrame,matches:pd.DataFrame,layer:str="Activity Density")->None:
    summary=pitch_layer_summary(shown,matches);cards=ui.columns(4)
    labels={"Passes":("Attempts","Completed","Completion %"),"Key Passes":("Key Passes","Completed","Completion %"),"Crosses":("Cross Attempts","Successful","Success %"),"Dribbles / TakeOns":("Attempts","Successful","Success %"),"Successful Dribbles":("Selected Actions","Successful","Success Rate"),"Aerials":("Contests","Won","Win %"),"Shots":("Shots","Goals / Successful","Rate")}.get(layer,("Selected Actions","Successful","Success Rate"))
    cards[0].metric(labels[0],f"{summary['actions']:,}");cards[1].metric(labels[1],f"{summary['successful']:,}")
    cards[2].metric(labels[2],"—" if pd.isna(summary['success_rate']) else f"{summary['success_rate']:.1f}%");cards[3].metric("Matches",f"{summary['matches']:,}")
    ui.caption("Summary and map use the same selected rows; missing endpoints are not invented.")
    detail=[column for column in ("date","opponent_id","event_type","outcome","x","y","end_x","end_y") if column in shown]
    if detail:ui.dataframe(shown.reindex(columns=detail),hide_index=True,use_container_width=True)


def _profile_controls(ui: Any, *, prefix: str, default_mode: str = "Projection") -> tuple[str,str,str,tuple[str,...]]:
    controls=ui.columns(3)
    display_modes=("Projection","2025/26 Historical","Current Season","Draft Profile","Custom")
    display_default="2025/26 Historical" if default_mode=="Historical" else default_mode
    chosen_mode=controls[0].selectbox("Mode",display_modes,index=display_modes.index(display_default),key=f"{prefix}_mode")
    mode="Historical" if chosen_mode=="2025/26 Historical" else chosen_mode
    rate=controls[1].selectbox("Rate Basis",LIVE_RATE_BASES,index=1,key=f"{prefix}_rate")
    basis=controls[2].selectbox("Percentile Basis",PERCENTILE_BASES,key=f"{prefix}_basis")
    allowed=metrics_for_mode(mode)
    defaults=tuple(key for key in MODE_DEFAULTS[mode] if key in allowed)
    labels={CATALOG[key].label:key for key in allowed}
    selected_labels=ui.multiselect("Edit Metrics (3–8)",list(labels),default=[CATALOG[key].label for key in defaults if key in CATALOG],max_selections=8,key=f"{prefix}_metrics")
    keys=tuple(labels[label] for label in selected_labels)
    if len(keys)<3: ui.warning("Choose at least three metrics to draw the comparison radar.")
    return mode,rate,basis,keys


def _dynamic_profile(ui:Any, frame:pd.DataFrame, players:pd.DataFrame, current_weekly:pd.DataFrame, historical_weekly:pd.DataFrame, *, prefix:str, default_mode:str="Projection") -> None:
    mode,rate,basis,keys=_profile_controls(ui,prefix=prefix,default_mode=default_mode)
    cards=comparison_cards(players,mode,rate,current_weekly,historical_weekly)
    ui.markdown(COMPARE_CARD_CSS,unsafe_allow_html=True)
    for column,card in zip(ui.columns(len(cards)),cards): column.markdown(comparison_card_html(card),unsafe_allow_html=True)
    if not 3<=len(keys)<=8: return
    validate_metrics(keys,mode=mode)
    records=radar_records(frame,players,keys,rate,basis); figure=build_player_radar(records,minimum_metrics=3)
    exact,directions=comparison_exact_table(players,mode,rate,keys,current_weekly,historical_weekly)
    radar_column,table_column=ui.columns([3,2])
    with radar_column:
        if figure is None: ui.warning("Fewer than three selected metrics have valid data. Choose another mode or metric set.")
        else: ui.plotly_chart(figure,use_container_width=True,key=f"{prefix}_radar")
    with table_column:
        section_header(ui,"Exact Comparison","Core decision metrics and selected radar additions.")
        ui.dataframe(comparison_table_styler(exact,directions),hide_index=True,use_container_width=True)
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
    section_header(ui,"Playing Time & Fixtures","Forward-looking context for the live season.")
    _metric_grid(ui,row,(("Projected Minutes %","projected_minutes_percentage"),("Minutes confidence","minutes_confidence"),("Club strength %","team_strength_percentile"),("Next 5 fixture ease %","next_five_fixture_ease_percentile")))
    mini=[]
    for label,field in (("Projected Minutes","projected_minutes_percentage"),("Club Strength","team_strength_percentile"),("Fixture Ease","next_five_fixture_ease_percentile")):
        value=pd.to_numeric(row.get(field),errors="coerce"); mini.append(percentile_bar(label,None if pd.isna(value) else value,value="Natural context"))
    ui.markdown("".join(mini),unsafe_allow_html=True)
    section_header(ui,"2025/26 Historical","Finalized historical production for context; never substituted into current-season fields.")
    historical_basis=ui.selectbox("Historical Rate Basis",LIVE_RATE_BASES,index=1,key=f"historical_rate_{stable_player_id(row)}")
    ui.dataframe(historical_comparison_frame(row,historical_basis),hide_index=True,use_container_width=True)
    _metric_grid(ui,row,(("Appearances","historical_appearances"),("Starts","historical_starts"),("Minutes","historical_minutes"),("Start %","historical_start_percentage"),("Historical xG","historical_xg"),("Historical xA","historical_xa")))
    if frame is not None:
        section_header(ui,"Current vs Historical Radar","Matched axes on a shared 0–100 percentile scale.")
        radar_controls=ui.columns(2)
        radar_view=radar_controls[0].selectbox("Radar Season",["Current Season","2025/26 Historical","Overlay Both"],key=f"season_radar_{stable_player_id(row)}")
        radar_basis=radar_controls[1].selectbox("Radar Percentile Basis",PERCENTILE_BASES,key=f"season_radar_basis_{stable_player_id(row)}")
        preset=ui.selectbox("Radar Preset",[*RADAR_PRESETS,"Custom"],key=f"season_radar_preset_{stable_player_id(row)}")
        metric_keys=RADAR_PRESETS.get(preset,RADAR_PRESETS["Balanced Profile"])
        if preset=="Custom":
            labels={value[0]:key for key,value in RADAR_METRICS.items()}
            chosen=ui.multiselect("Radar Metrics (3–8)",list(labels),default=[RADAR_METRICS[key][0] for key in metric_keys],max_selections=8,key=f"season_radar_metrics_{stable_player_id(row)}")
            metric_keys=tuple(labels[label] for label in chosen)
        records=season_radar_records(frame,row,historical_basis,radar_basis,metric_keys)
        shown=records[:1] if radar_view=="Current Season" else records[1:] if radar_view=="2025/26 Historical" else shared_radar_records(records)
        figure=build_player_radar(shown,minimum_metrics=3)
        if len(metric_keys)<3 or figure is None: ui.info("Insufficient data: choose at least three metrics valid for the selected season view.")
        else:
            ui.plotly_chart(figure,use_container_width=True,key=f"season_overlay_{stable_player_id(row)}")
            ui.dataframe(comparison_values_frame(shown) if len(shown)>1 else raw_values_frame(shown),hide_index=True,use_container_width=True)
        ui.caption("Current values are percentiles among current peers; historical values are percentiles among finalized 2025/26 peers. Axes are identical and missing values are not plotted as zero.")
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


def _performance_match_analysis_legacy(ui:Any,row:pd.Series,basis:str,current_weekly:pd.DataFrame,historical_weekly:pd.DataFrame)->None:
    player_id=str(row.get("fantrax_player_id","")); historical_value=row.get("historical_fantrax_player_id")
    historical_id=str(historical_value) if pd.notna(historical_value) and str(historical_value).strip() else player_id
    current=prepare_player_gameweek_frame(current_weekly,player_id,season="2026/27",include_live=True)
    historical=prepare_player_gameweek_frame(historical_weekly,historical_id,season="2025/26")
    available=[label for label,data in (("2026/27 Current",current),("2025/26 Historical",historical)) if not data.empty]
    if not available: ui.info("No completed current or finalized historical gameweek records are available for this player."); return
    default=0 if "2026/27 Current" in available else available.index("2025/26 Historical")
    season=ui.selectbox("Match Analysis Season",available,index=default,key=f"match_season_{stable_player_id(row)}")
    selected=current if season.startswith("2026/27") else historical
    left,right=ui.columns(2)
    with left:
        section_header(ui,"Points by Gameweek","Completed Fantrax scoring periods; negative scores remain visible.")
        figure=go.Figure(go.Bar(x=selected["period"],y=selected["fantasy_points"],name="Fantrax Points")); figure.update_layout(xaxis_title="Gameweek",yaxis_title="Points")
        ui.plotly_chart(apply_chart_theme(figure,height=300),use_container_width=True,key=f"points_by_gw_{player_id}_{season}")
    with right:
        recent=prepare_last_n_periods(selected,5); label=f"Last 5 Gameweeks ({len(recent)} available)" if len(recent)<5 else "Last 5 Gameweeks"
        section_header(ui,label,"Latest completed periods only; missing weeks are not padded.")
        figure=go.Figure(go.Scatter(x=recent["period"],y=recent["fantasy_points"],mode="lines+markers+text",text=recent["fantasy_points"].map(lambda value:"" if pd.isna(value) else f"{value:g}"),textposition="top center",name="Fantrax Points")); figure.update_layout(xaxis_title="Gameweek",yaxis_title="Points")
        ui.plotly_chart(apply_chart_theme(figure,height=300),use_container_width=True,key=f"last_five_{player_id}_{season}")
    split=calculate_home_away_split(selected,basis); breakdown=calculate_points_breakdown(selected)
    left,right=ui.columns(2)
    with left:
        section_header(ui,"Home vs Away Average",f"{basis} production; unavailable denominators stay blank.")
        hover=[f"{venue}: {'—' if pd.isna(value) else f'{value:.1f}'} · sample {sample:g}" for venue,value,sample in split[["Venue","Average","Sample"]].itertuples(index=False,name=None)]
        figure=go.Figure(go.Bar(x=split["Venue"],y=split["Average"],text=hover,hovertemplate="%{text}<extra></extra>")); figure.update_layout(yaxis_title=f"Points {basis}")
        ui.plotly_chart(apply_chart_theme(figure,height=280),use_container_width=True,key=f"home_away_{player_id}_{season}")
    with right:
        section_header(ui,"Points Breakdown","Ghost Points and the reconciled remainder of Fantrax points.")
        if pd.isna(breakdown["ghost"]): ui.info("Authoritative player-gameweek Ghost Points are unavailable for this season.")
        else:
            labels=["Ghost Points","Non-Ghost Points"]; values=[breakdown["ghost"],breakdown["non_ghost"]]
            figure=go.Figure(go.Pie(labels=labels,values=values,hole=.55)) if breakdown["pie_safe"] else go.Figure(go.Bar(x=labels,y=values))
            ui.plotly_chart(apply_chart_theme(figure,height=280),use_container_width=True,key=f"breakdown_{player_id}_{season}")
    section_header(ui,"Full Gameweek Stats","Fantrax-period detail; optional columns appear only when supported.")
    controls=ui.columns(3); venue=controls[0].selectbox("Home / Away",["All","Home","Away"],key=f"match_venue_{player_id}")
    appearances=["All","Started","Sub"]+(["DNP"] if selected["appearance_type"].eq("DNP").any() else [])
    appearance=controls[1].selectbox("Appearance",appearances,key=f"match_appearance_{player_id}")
    supported=supported_optional_columns(selected); extras=controls[2].multiselect("Add / Remove Columns",supported,key=f"match_columns_{player_id}")
    fdr_range=None
    if pd.to_numeric(selected.get("fdr"),errors="coerce").notna().any():
        low=float(pd.to_numeric(selected["fdr"],errors="coerce").min()); high=float(pd.to_numeric(selected["fdr"],errors="coerce").max()); fdr_range=ui.slider("FDR range",low,high,(low,high),key=f"match_fdr_{player_id}")
    table=prepare_gameweek_table(selected,home_away=venue,appearance=appearance,fdr_range=fdr_range,extra_columns=tuple(extras)); ui.dataframe(table,hide_index=True,use_container_width=True,height=min(520,38+35*max(len(table),1)))
    ui.caption("Rows are aggregated at the Fantrax scoring-period level. Opponent and H/A come from the registered Fantrax opponent field; FDR remains blank where no registered player-week value exists.")


def _performance_match_analysis(ui:Any,row:pd.Series,basis:str,current_matches:pd.DataFrame,historical_matches:pd.DataFrame)->None:
    player_id=str(row.get("fantrax_player_id",""));historical_value=row.get("historical_fantrax_player_id");historical_id=str(historical_value) if pd.notna(historical_value) and str(historical_value).strip() else player_id
    current=prepare_match_research_frame(current_matches,player_id,season="2026/27");historical=prepare_match_research_frame(historical_matches,historical_id,season="2025/26")
    available=[label for label,data in (("2026/27 Current",current),("2025/26 Historical",historical)) if not data.empty]
    if not available:ui.info("No observed current or finalized historical matches are available for this player.");return
    season=ui.selectbox("Match Analysis Season",available,index=0 if "2026/27 Current" in available else available.index("2025/26 Historical"),key=f"match_season_{stable_player_id(row)}");selected=current if season.startswith("2026/27") else historical
    summary=match_research_summary(selected);show=lambda value,digits=1:"—" if pd.isna(value) else f"{value:,.{digits}f}"
    primary=ui.columns(4)
    for column,(label,key,help_text) in zip(primary,(("FPts / Start","fpts_per_start","Observed Fantrax points among starts."),("Ghost / Start","ghost_per_start","Exact Fantrax Ghost where available; partial derivations retain provenance."),("FPts / 90","fpts_per_90","Uses observed match minutes only."),("Min / Start","minutes_per_start","Mean observed minutes among starts."))):column.metric(label,show(summary[key]),help=help_text)
    secondary=ui.columns(5);dependency="—" if pd.isna(summary["return_dependency"]) else f"{summary['return_dependency']:.0f}%"
    for column,(label,value,help_text) in zip(secondary,(("Median",show(summary["median"]),"P50 FPts among starts."),("Floor",show(summary["floor"]),"P10 FPts among starts; suppressed below 10 starts."),("Ceiling",show(summary["ceiling"]),"P90 FPts among starts; suppressed below 10 starts."),("Consistency",show(summary["std_dev"]),"FPts standard deviation among starts; lower is steadier."),("Return Dependency",dependency,"Non-Ghost share of fantasy production; unavailable unless Ghost is exact."))):column.metric(label,value,help=help_text)
    distribution=production_distribution(selected);section_header(ui,"Production Distribution",f"{summary['starts']} starts · substitute cameos excluded.")
    figure=go.Figure(go.Bar(x=distribution["Share"],y=distribution["Band"],orientation="h",text=distribution["Starts"],marker_color="#176b87"));figure.update_layout(xaxis_title="Share of starts (%)",yaxis_title=None,showlegend=False);ui.plotly_chart(apply_chart_theme(figure,height=230),use_container_width=True,key=f"distribution_{player_id}_{season}")
    section_header(ui,"Match Performance","Chronological observed matches · Fantrax points authoritative.")
    hover=selected.apply(lambda x:f"GW {x.get('period','—')} · {x.get('opponent','—')} ({x.get('venue','—')})<br>FPts {show(x.get('fantasy_points'))} · Ghost {show(x.get('ghost_points'))}<br>{x.get('appearance_type','—')} · {show(x.get('minutes'),0)} min · {x.get('role','—')} · {x.get('formation','—')}<br>Rating {show(x.get('rating'),2)} · xG {show(x.get('xg'),2)} · xA {show(x.get('xa'),2)}",axis=1)
    starts=pd.to_numeric(selected["started"],errors="coerce").gt(0);figure=go.Figure();figure.add_trace(go.Scatter(x=selected["period"],y=selected["fantasy_points"],mode="lines+markers",name="FPts",marker={"size":selected["appearance_type"].map({"Started":9,"Sub":6}).fillna(0),"symbol":starts.map({True:"circle",False:"diamond"})},text=hover,hovertemplate="%{text}<extra></extra>",connectgaps=False));figure.add_trace(go.Scatter(x=selected["period"],y=selected["ghost_points"],mode="lines+markers",name="Ghost",line={"dash":"dot","width":1.5},opacity=.65,connectgaps=False));figure.update_layout(xaxis_title="Gameweek",yaxis_title="Fantasy Points",legend={"orientation":"h"});ui.plotly_chart(apply_chart_theme(figure,height=360),use_container_width=True,key=f"match_performance_{player_id}_{season}")
    section_header(ui,"Match History","Canonical role, provider, and fantasy facts; missing observations remain blank.")
    controls=ui.columns(2);venue=controls[0].selectbox("Home / Away",["All","Home","Away"],key=f"match_venue_{player_id}");appearance=controls[1].selectbox("Appearance",["All","Started","Sub"],key=f"match_appearance_{player_id}");filtered=selected
    if venue!="All":filtered=filtered[filtered.venue.eq("H" if venue=="Home" else "A")]
    if appearance!="All":filtered=filtered[filtered.appearance_type.eq(appearance)]
    table=prepare_match_research_table(filtered);ui.dataframe(table,hide_index=True,use_container_width=True,height=min(560,38+35*max(len(table),1)));ui.caption("One row per observed player-match. Future fixtures and unsupported DNPs are never emitted as zero-point performances.")


def _compact_profile_legacy(ui: Any, row: pd.Series, events: pd.DataFrame, history: pd.DataFrame, frame: pd.DataFrame, weekly: pd.DataFrame, historical_weekly:pd.DataFrame, supplemental:pd.DataFrame=pd.DataFrame(),advanced_profiles:pd.DataFrame=pd.DataFrame(),role_usage:pd.DataFrame=pd.DataFrame(),set_pieces:pd.DataFrame=pd.DataFrame(),event_data:pd.DataFrame=pd.DataFrame(),advanced_season:str="2026/27 Current") -> None:
    """Compact live scouting profile; all values come from registered presentation data."""
    player_id=stable_player_id(row)
    owner=row.get("current_manager_name") if pd.notna(row.get("current_manager_name")) else "Available"
    section_header(ui,str(row.get("player_name","Player")),f"{row.get('premier_league_club','')} · {row.get('fantrax_position','')} · {owner} · {row.get('roster_status') or 'Not rostered'}",eyebrow="Player profile")
    basis=ui.selectbox("Profile Rate Basis",LIVE_RATE_BASES,index=1,key=f"profile_rate_{player_id}")
    points,ghost,xgi,points_label,ghost_label,xgi_label=LIVE_RATE_FIELDS[basis]
    _metric_grid(ui,row,((points_label,points),(ghost_label,ghost),(xgi_label,xgi),("Start %","current_start_percentage"),("Minutes Outlook","projected_minutes_percentage"),("Next 5 Fixture Ease","next_five_fixture_ease_percentile")))

    tabs=ui.tabs(["Overview","Performance","Playing Time","Advanced","Pitch","Fixtures","History","Ownership / Draft"])
    with tabs[0]:
        section_header(ui,"Fantasy Profile","Profile shape and exact values.")
        controls=ui.columns(2)
        initial=overview_radar_records(frame,row,DEFAULT_RADAR_KEYS,"League")
        current_valid=sum(pd.notna(metric["percentile"]) for metric in initial[0]["metrics"])
        modes=["Current Season","2025/26 Historical","Overlay Both"]
        mode=controls[0].selectbox("Mode",modes,index=0 if current_valid>=3 else 1,key=f"overview_mode_{player_id}")
        peer_basis=controls[1].selectbox("Percentile Basis",PERCENTILE_BASES,key=f"overview_peer_{player_id}")
        metric_keys=DEFAULT_RADAR_KEYS
        labels={value[0]:key for key,value in OVERVIEW_METRICS.items()}
        selected=ui.multiselect("Edit Metrics (3–8)",list(labels),default=[OVERVIEW_METRICS[key][0] for key in metric_keys],max_selections=8,key=f"overview_metrics_{player_id}")
        metric_keys=tuple(labels[label] for label in selected)
        records=overview_radar_records(frame,row,metric_keys,peer_basis); shown=valid_radar_records(records,mode)
        figure=build_player_radar(shown,minimum_metrics=3,simple_hover=True)
        radar_column,stats_column=ui.columns([3,2])
        with radar_column:
            if len(metric_keys)<3 or figure is None: ui.info("Insufficient data for three valid metrics in this view.")
            else: ui.plotly_chart(figure,use_container_width=True,key=f"overview_radar_{player_id}")
        with stats_column:
            section_header(ui,"Exact Statistics","Established values for the selected mode.")
            ui.dataframe(exact_stats_frame(row,mode),hide_index=True,use_container_width=True)
        ui.caption("Current percentiles use current peers; historical percentiles use finalized 2025/26 peers. Invalid axes are omitted rather than zero-filled, preserving a closed polygon.")

    pid=str(row.get("fantrax_player_id",""))
    player_weekly=weekly[weekly.get("fantrax_player_id",pd.Series(index=weekly.index,dtype=object)).astype(str).eq(pid)].copy() if not weekly.empty else pd.DataFrame()
    with tabs[1]:
        _performance_match_analysis(ui,row,basis,weekly,historical_weekly)
    with tabs[2]:
        section_header(ui,"Actual","Completed 2026/27 playing time.")
        _metric_grid(ui,row,(("Appearances","current_appearances"),("Starts","current_starts"),("Minutes","current_minutes"),("Start %","current_start_percentage"),("Minutes / Game","current_minutes_per_game")))
        if not player_weekly.empty and {"period","minutes"}.issubset(player_weekly): ui.bar_chart(player_weekly.set_index("period")[["minutes"]])
        section_header(ui,"Outlook","Projection context, kept separate from actual minutes.")
        _metric_grid(ui,row,(("Minutes Outlook","projected_minutes_percentage"),("Minutes confidence","minutes_confidence")))
        section_header(ui,"2025/26 Reference")
        _metric_grid(ui,row,(("Appearances","historical_appearances"),("Starts","historical_starts"),("Minutes","historical_minutes"),("Start %","historical_start_percentage"),("Minutes / Game","historical_minutes_per_game")))
    with tabs[3]:
        section_header(ui,"Attacking","Supported current Fantrax event rates.")
        suffix={"Per Game":"per_game","Per Start":"per_start","Per 90":"per_90"}[basis]
        _metric_grid(ui,row,tuple((label,f"current_{field}_{suffix}") for label,field in (("Shots","shots"),("Shots on target","shots_on_target"),("Key passes","key_passes"),("Accurate crosses","accurate_crosses"),("Dribbles","successful_dribbles"))))
        section_header(ui,"Defensive","Supported current defensive-event rates.")
        _metric_grid(ui,row,tuple((label,f"current_{field}_{suffix}") for label,field in (("Tackles won","tackles_won"),("Interceptions","interceptions"),("Clearances","clearances"),("Blocks","blocks"),("Aerials won","aerials_won"))))
        section_header(ui,advanced_season,"Current provider observations." if advanced_season.startswith("2026/27") else "Finalized historical reference; never substituted into current fields.")
        if advanced_season.startswith("2025/26"):_metric_grid(ui,row,(("Goals","historical_goals"),("Assists","historical_assists"),("xG","historical_xg"),("xA","historical_xa"),("Key passes","understat_key_passes_2526")))
        _advanced_history(ui,row,supplemental,advanced_profiles,role_usage,set_pieces)
    with tabs[4]:
        section_header(ui,"Event Activity Map",f"Recorded actions · {advanced_season}.")
        candidates=supplemental[supplemental.get("fantrax_player_id",pd.Series(index=supplemental.index,dtype=object)).astype(str).eq(str(row.get("fantrax_player_id","")))]
        _pitch_history(ui,None if candidates.empty else str(candidates.canonical_player_id.iloc[0]),event_data,supplemental)
    with tabs[5]:
        section_header(ui,"Upcoming Schedule","Existing fixture context; no match prediction layer.")
        _metric_grid(ui,row,(("Next 5 Fixture Ease","next_five_fixture_ease_percentile"),("Next 3 Ease","fixture_ease_next_3"),("Next 10 Ease","fixture_ease_next_10"),("Team Strength","team_strength_percentile")))
        if pd.notna(row.get("opening_opponent")): ui.dataframe(pd.DataFrame([{"Opponent":row.get("opening_opponent"),"Window":"Opening fixture"}]),hide_index=True,use_container_width=True)
    with tabs[6]:
        section_header(ui,"2025/26 Finalized History","Rate context from the existing historical methodology.")
        ui.dataframe(historical_comparison_frame(row,basis),hide_index=True,use_container_width=True)
        _metric_grid(ui,row,(("Historical Points","historical_fantasy_points"),("Historical Ghost","historical_ghost_points"),("Historical xGI","historical_xgi"),("Starts","historical_starts"),("Minutes","historical_minutes"),("Start %","historical_start_percentage")))
    with tabs[7]:
        section_header(ui,"Current Ownership","Authoritative roster state and observed changes.")
        _metric_grid(ui,row,(("Ownership changes","ownership_change_count"),("Draft round","draft_round"),("Overall pick","overall_pick")))
        section_header(ui,"Draft-Day Context","Secondary frozen context.")
        _metric_grid(ui,row,(("Projection","fantrax_projected_points"),("ADP","adp"),("Draft Rank","draft_rank"),("Draft Score","draft_score")))
        owned=history[history.get("fantrax_player_id",pd.Series(index=history.index,dtype=object)).astype(str).eq(pid)]
        changed=events[events.get("fantrax_player_id",pd.Series(index=events.index,dtype=object)).astype(str).eq(pid)]
        if owned.empty and changed.empty: ui.info("No ownership changes detected since the initial snapshot.")
        else:
            if not owned.empty: ui.dataframe(owned,use_container_width=True,hide_index=True)
            if not changed.empty: ui.dataframe(changed,use_container_width=True,hide_index=True)


def _compact_profile(ui: Any,row:pd.Series,events:pd.DataFrame,history:pd.DataFrame,frame:pd.DataFrame,weekly:pd.DataFrame,historical_weekly:pd.DataFrame,supplemental:pd.DataFrame=pd.DataFrame(),advanced_profiles:pd.DataFrame=pd.DataFrame(),role_usage:pd.DataFrame=pd.DataFrame(),set_pieces:pd.DataFrame=pd.DataFrame(),event_data:pd.DataFrame=pd.DataFrame(),advanced_season:str="2026/27 Current",match_log:pd.DataFrame=pd.DataFrame(),fixtures:pd.DataFrame=pd.DataFrame(),data_manager:DataManager|None=None,historical_match_log:pd.DataFrame=pd.DataFrame())->None:
    """Draft-Academical-style, fixed current-season research hierarchy."""
    player_id=stable_player_id(row);fantrax_id=str(row.get("fantrax_player_id",""));owner=ownership_text(row);status="Rostered" if owner!="Available" else "Available / Waiver"
    ui.markdown(f'<div class="player-identity"><div><div class="ft-eyebrow">2026/27 Player Research</div><div class="player-name">{row.get("player_name","Player")}</div><div class="player-club">{row.get("premier_league_club","")} · <span class="ft-badge ft-badge-accent">{row.get("fantrax_position","")}</span></div></div><div class="player-owner"><span>{status}</span><b>{owner}</b></div></div>',unsafe_allow_html=True)
    kpis=overview_kpis(row);primary=ui.columns(6)
    for column,item in zip(primary,kpis[:6]):
        column.metric(item["label"],format_overview_value(item["key"],item["value"]),help="Fantrax" if "ghost" not in item["key"] else "Fantrax when observed; otherwise a provenance-retaining partial derived estimate.")
    secondary=ui.columns(2)
    for column,item in zip(secondary,kpis[6:]):
        column.metric(item["label"],format_overview_value(item["key"],item["value"]),help="Current-season Understat observation; historical values never fill this card.")
    candidates=supplemental[supplemental.get("fantrax_player_id",pd.Series(index=supplemental.index,dtype=object)).astype(str).eq(fantrax_id)]
    canonical=None if candidates.empty else str(candidates.canonical_player_id.iloc[0])
    pieces=set_pieces[set_pieces.get("canonical_player_id",pd.Series(index=set_pieces.index,dtype=object)).astype(str).eq(str(canonical))&set_pieces.get("window",pd.Series(index=set_pieces.index,dtype=object)).eq("SEASON")].copy() if canonical else pd.DataFrame()
    if not pieces.empty:
        labels=set_piece_chips(pieces);ui.markdown('<div class="chip-row">'+''.join(f'<span class="research-chip">{label}</span>' for label in labels[:6])+'</div>',unsafe_allow_html=True)
    tabs=ui.tabs(["Overview","Match Analysis","Role & Tactical","Advanced"])
    ownlog=match_log[match_log.get("fantrax_player_id",pd.Series(index=match_log.index,dtype=object)).astype(str).eq(fantrax_id)].copy()
    with tabs[0]:
        availability=historical_profile_availability(row)
        has_history=any(section["available"] for section in availability.values())
        historical=ui.toggle("Compare to 2025/26",value=False,disabled=not has_history,key=f"overview_history_{player_id}",help="Historical profiles use best-available Fantrax, WhoScored, and Understat observations.")
        if not has_history:ui.caption("No defensible 2025/26 Premier League profile is available for this player.")
        profile_columns=ui.columns(4)
        for column,(title,axes) in zip(profile_columns[:3],(("Fantasy Profile",FANTASY_AXES),("Attacking Profile",ATTACKING_AXES),("Defensive Profile",DEFENSIVE_AXES))):
            records,cohort=fixed_radar_records(frame,row,axes,historical);figure=build_player_radar(records,minimum_metrics=3,simple_hover=True)
            with column:
                ui.markdown(f'<div class="profile-card-title">{title}</div><div class="profile-card-copy">Percentile among Fantrax-eligible {cohort}</div>',unsafe_allow_html=True)
                if figure is None:ui.info("Insufficient observed metrics for this profile.")
                else:ui.plotly_chart(figure,use_container_width=True,key=f"{title.lower().replace(' ','_')}_{player_id}_{historical}")
                starts=pd.to_numeric(row.get("current_starts"),errors="coerce");ui.caption(f"Current sample · {int(starts) if pd.notna(starts) else 0} start(s)")
        with profile_columns[3]:
            ui.markdown('<div class="profile-card-title">Season Trend</div><div class="profile-card-copy">Current Fantrax observations</div>',unsafe_allow_html=True)
            if ownlog.empty:ui.info("No current appearance observation.")
            else:
                recent=ownlog.sort_values(["fantrax_period","date"]).tail(5);scores=" · ".join(f"GW{int(g)} {p:g}" for g,p in recent[["fantrax_period","fantrax_points"]].itertuples(index=False,name=None))
                venue=ownlog.groupby("venue").fantrax_points.mean();home=venue.get("H",pd.NA);away=venue.get("A",pd.NA);total=pd.to_numeric(ownlog.fantrax_points,errors="coerce").sum(min_count=1);ghost=pd.to_numeric(ownlog.ghost_points,errors="coerce").sum(min_count=1)
                shown=lambda value:"—" if pd.isna(value) else f"{value:.1f}"
                ui.markdown(f'<div class="trend-stack"><div class="trend-item"><span>Last 5 Gameweeks</span><b>{scores}</b></div><div class="trend-item"><span>Home vs Away</span><b>H {shown(home)} · A {shown(away)}</b></div><div class="trend-item"><span>Points Breakdown ⓘ</span><b>Ghost {shown(ghost)} · Major {shown(total-ghost)}</b></div></div><div class="trend-note">{"Limited sample · " if len(ownlog)<3 else ""}Ghost may be a partial derived estimate.</div>',unsafe_allow_html=True)
        if historical:ui.dataframe(historical_comparison_frame(row,"Per Start"),hide_index=True,use_container_width=True)
        club_id=ownlog.club_id.iloc[0] if not ownlog.empty else "";section_header(ui,"Next Fixtures","Next five · established FDR methodology.");ui.markdown(fixture_cards_html(next_fixtures(fixtures,str(club_id))),unsafe_allow_html=True)
        section_header(ui,"Full Gameweek Stats","Canonical participation and best-available current metrics.");gameweek=overview_gameweek_table(match_log,fantrax_id,fixtures).rename(columns={"FPts":"Pts","Start":"GS","Minutes":"Min","Goals":"G","Assists":"A","Accurate Crosses":"AC","Successful Dribbles":"CoS","Tackles Won":"TkW","Interceptions":"Int","Clearances":"CLR","Aerial Wins":"AER","Clean Sheets":"CS"});ui.dataframe(gameweek,hide_index=True,use_container_width=True,column_config={**{c:ui.column_config.NumberColumn(c,format="%.1f") for c in ("Pts","Ghost") if c in gameweek},**({"CoS":ui.column_config.NumberColumn("CoS",help="Successful Dribbles")} if "CoS" in gameweek else {})})
        ui.caption("Fantrax detail wins; validated provider fallback remains provenance-labeled in the model. Rendering is cache-only.")
    with tabs[1]:_performance_match_analysis(ui,row,"Per Start",match_log,historical_match_log)
    with tabs[2]:
        available=(["2026/27 Current"] if not supplemental.empty else [])+["2025/26 Historical"]
        advanced_season=ui.selectbox("Advanced data season",available,index=0,key=f"player_advanced_season_{fantrax_id}")
        if advanced_season=="2025/26 Historical" and data_manager is not None:selected_advanced=get_historical_player_advanced(data_manager,fantrax_id,ui=ui)
        else:selected_advanced={"supplemental":supplemental,"profile":advanced_profiles,"roles":role_usage,"set_pieces":set_pieces,"pitch":event_data}
        section_header(ui,"Role & Tactical",f"Where and how the player is used · {advanced_season}.");_pitch_history(ui,canonical,selected_advanced["pitch"],selected_advanced["supplemental"])
        if not selected_advanced["set_pieces"].empty:section_header(ui,"Set-Piece Usage","Observed rank, attempts, share, and sample.");ui.dataframe(selected_advanced["set_pieces"],hide_index=True,use_container_width=True)
    with tabs[3]:
        advanced_options=(['2026/27 Current'] if not supplemental.empty else [])+['2025/26 Historical'];analysis_season=ui.selectbox('Advanced Season',advanced_options,index=0,key=f'advanced_analysis_season_{fantrax_id}')
        if analysis_season=='2025/26 Historical' and data_manager is not None:analysis_data=get_historical_player_advanced(data_manager,fantrax_id,ui=ui,include_pitch=False)
        else:analysis_data={'supplemental':overlay_fantrax_authority(supplemental,ownlog),'profile':advanced_profiles,'roles':role_usage,'set_pieces':set_pieces}
        section_header(ui,analysis_season,"Deep statistical components, fantasy contribution, peer context, and provenance.");_advanced_history(ui,row,analysis_data['supplemental'],analysis_data['profile'],analysis_data['roles'],analysis_data['set_pieces'],frame,row)


def render(season_id: str, *, data_manager: DataManager | None = None, season_manager: SeasonManager | None = None, ui: Any = st) -> None:
    seasons=season_manager or SeasonManager(); data=data_manager or DataManager(season_manager=seasons); namespace=seasons.resolve_namespace(season_id)
    ui.markdown(SHARED_COMPONENT_CSS,unsafe_allow_html=True); page_header(ui,"Players",badge="2026/27 · Live")
    frame=_load(data,"live_player_analytics",season_id,namespace,ui); events=_load(data,"roster_change_events",season_id,namespace,ui); history=_load(data,"roster_history",season_id,namespace,ui); ownership=_load(data,"player_ownership",season_id,namespace,ui); weekly=_load(data,"live_player_weekly_enriched",season_id,namespace,ui); summary=_load(data,"current_player_season_summary",season_id,namespace,ui); match_log=_load(data,"current_player_match_log",season_id,namespace,ui);historical_profile=_load(data,"historical_player_research_profile",season_id,namespace,ui)
    if weekly.empty:weekly=_load(data,"current_player_weekly",season_id,namespace,ui)
    clubs=_load(data,"premier_league_clubs",season_id,namespace,ui); fixtures=_load(data,"team_fixtures",season_id,namespace,ui)
    if not frame.empty and not clubs.empty and not fixtures.empty:
        frame=enrich_players_with_fixtures(frame,clubs,fixtures)
    if frame.empty: ui.info("Run Refresh League in Operations Center to build live player analytics."); return
    if weekly.empty:
        window_label="No completed scoring periods"
    else:
        window=ui.selectbox("Performance window",["Season","Last 3","Last 5","Last 10"],key="live_player_window"); frame,window_label=apply_live_window(frame,weekly,window); ui.caption(f"Current performance coverage: {window_label}")
    if not summary.empty:frame=overlay_current_summary(frame,summary)
    if not ownership.empty:frame=overlay_current_ownership(frame,ownership)
    if not historical_profile.empty:frame=overlay_historical_advanced(frame,historical_profile)
    state=getattr(ui,"session_state",st.session_state)
    subview=ui.segmented_control("Players view",["Player Database","Player Profile","Player Comparison"],default="Player Database",key="players_subview",label_visibility="collapsed",width="stretch")
    if subview=="Player Database":
        a,b,c,d,e=ui.columns(5)
        search=a.text_input("Search"); availability=b.selectbox("Availability",["All Players","Available Only"]); rate_basis=c.selectbox("Rate Basis",LIVE_RATE_BASES,index=1,key="live_database_rate"); position=d.selectbox("Position",["All","G","D","M","F"])
        default_sort="Points" if live_sort_field(frame,rate_basis)!="fantrax_projected_points" else "Projected Points"
        sort_by=e.selectbox("Sort By",SORT_OPTIONS,index=SORT_OPTIONS.index(default_sort))
        filtered=filter_players(frame,search=search,position=position)
        if availability=="Available Only": filtered=filtered[filtered.get("available",pd.Series(False,index=filtered.index)).fillna(False).astype(bool)]
        filtered=sort_players(filtered,live_sort_field(frame,rate_basis,sort_by),False)
        display=live_database_frame(filtered,rate_basis); cols=list(display.columns)
        if ui is st:
            key="live_player_click"; config={"Player":st.column_config.ButtonColumn("Player",type="tertiary",on_click=_open_player,args=(key,filtered["fantrax_player_id"].astype(str).tolist()),key=key)}
            ui.data_editor(display[cols],hide_index=True,use_container_width=True,disabled=[x for x in cols if x!="Player"],column_config=config,key="live_player_database")
        else: ui.dataframe(display[cols],hide_index=True,use_container_width=True)
    elif subview=="Player Profile":
        historical_weekly=_load(data,"master_player_weekly","2526",seasons.resolve_namespace("2526"),ui)
        historical_match_log=load_historical_advanced_frame(data,"supplemental_player_match",ui=ui)
        options=dict(zip(frame["player_name"].fillna("Unknown").astype(str)+" · "+frame["fantrax_player_id"].astype(str),frame["fantrax_player_id"].astype(str)))
        labels=[]; seen={}
        for _,player in frame.iterrows():
            base=f"{player.get('player_name','Unknown')} · {player.get('premier_league_club','')} · {player.get('fantrax_position','')}"
            seen[base]=seen.get(base,0)+1; labels.append(base if seen[base]==1 else f"{base} ({seen[base]})")
        options=dict(zip(labels,frame["fantrax_player_id"].astype(str)))
        default=next((label for label,pid in options.items() if pid==str(state.get("live_player_id",""))),next(iter(options)))
        label=ui.selectbox("Player",list(options),index=list(options).index(default),key="profile_player_selector")
        state["live_player_id"]=options[label]
        advanced=get_historical_player_advanced(data,options[label],season="2627",ui=ui)
        _compact_profile(ui,frame[frame["fantrax_player_id"].astype(str).eq(options[label])].iloc[0],events,history,frame,weekly,historical_weekly,advanced["supplemental"],advanced["profile"],advanced["roles"],advanced["set_pieces"],advanced["pitch"],"2026/27 Current",match_log,fixtures,data,historical_match_log)
    else:
        state.setdefault(COMPARE_KEY,[])
        section_header(ui,"Compare Players","Select two to five players, then compare context, profile shape, and exact values.")
        id_series=frame.apply(stable_player_id,axis=1); labels=[]; seen={}
        for _,player in frame.iterrows():
            base=f"{player.get('player_name','Unknown')} · {player.get('premier_league_club','')} · {player.get('fantrax_position','')}"
            seen[base]=seen.get(base,0)+1; labels.append(base if seen[base]==1 else f"{base} ({seen[base]})")
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
            historical_weekly=_load(data,"master_player_weekly","2526",seasons.resolve_namespace("2526"),ui)
            selected=frame[id_series.isin(chosen_ids)].copy(); selected["_order"]=selected.apply(lambda row:chosen_ids.index(stable_player_id(row)),axis=1); selected=selected.sort_values("_order")
            _dynamic_profile(ui,frame,selected,weekly,historical_weekly,prefix="comparison")
