"""Polished Operations Center using the approved operations boundary."""
from __future__ import annotations

from datetime import datetime
from typing import Any
import streamlit as st

from components.presentation import SHARED_COMPONENT_CSS, metric_card, page_header, section_header
from core.models.data_result import DataStatus
from core.models.operation_result import OperationResult
from core.services.data_manager import DataManager, DatasetNotFoundError, DatasetValidationError, UnsupportedFormatError
from core.services.operations_service import OperationNotAllowedError, OperationParameterError, OperationsService
from core.services.season_manager import SeasonManager
from core.services.refresh_status import derive_refresh_status, published_period_progress
from core.services.core_refresh import CoreRefreshResult, run_core_refresh
from core.services.smart_refresh import DESKTOP_COMMAND, SmartRefreshResult, run_smart_refresh
from fantrax.live.season_state import live_period_phase,resolve_scoring_period_state

REFRESH_OPERATION="refresh_fantrax_data"
ANALYTICS_OPERATION="build_league_analytics"
LIVE_REFRESH_OPERATION="refresh_live_fantrax_sources"
LIVE_BUILD_OPERATION="build_live_season_datasets"


def render(season_id:str,*,data_manager:DataManager|None=None,season_manager:SeasonManager|None=None,operations_service:OperationsService|None=None,ui:Any=st)->None:
    seasons=season_manager or SeasonManager(); season=seasons.context(season_id); namespace=seasons.resolve_namespace(season.season_id)
    data=data_manager or DataManager(season_manager=seasons); operations=operations_service or OperationsService(season_manager=seasons)
    ui.markdown(SHARED_COMPONENT_CSS,unsafe_allow_html=True)
    page_header(ui,"Operations Center","League health, refresh status, and routine maintenance in one place.",eyebrow="Control room",badge="System operations")
    _render_data_status(ui,season.season_id)
    if season.finalized or namespace=="snapshot": _render_finalized(ui,data,season,namespace); return
    _render_live(ui,operations,data,season.season_id,namespace)


def _render_live(ui:Any,operations:OperationsService,data:DataManager,season_id:str,namespace:str)->None:
    manifest=_load_optional_json(data,"live_season_manifest",season_id,namespace,ui)
    advanced_status=_load_optional_json(data,"weekly_advanced_refresh_latest",season_id,namespace,ui)
    datasets=manifest.get("datasets",[]) if manifest else []; by_key={item.get("dataset_key"):item for item in datasets}
    scoring_periods=_load_optional_frame(data,"scoring_periods",season_id,namespace,ui);period_state=resolve_scoring_period_state(scoring_periods)
    team_matches=_load_optional_frame(data,"team_matches",season_id,namespace,ui);period_progress=published_period_progress(team_matches,period_state.current_period,_load_optional_frame(data,"whoscored_match",season_id,namespace,ui))
    healthy=bool(datasets) and all(item.get("validation_result")=="valid" for item in datasets)
    cards=ui.columns(4)
    values=(("Season","2026/27 Live","Active league","blue"),("Last Successful Build",_friendly_time(manifest.get("build_timestamp") if manifest else None),"Validated cached datasets","green"),("League Status","Healthy" if healthy else "Needs Refresh","Registered data checks","green" if healthy else "gold"),("Current Period",f"GW{period_state.current_period}" if period_state.current_period else "—",period_state.source.replace("_"," ").title(),"blue"))
    for column,item in zip(cards,values):
        with column: metric_card(ui,*item[:3],tone=item[3])

    section_header(ui,"Core Data",f"GW{period_state.current_period or '—'} · {period_progress['state'].replace('_',' ').title()} · {period_progress['completed']}/{period_progress['total']} fixture results recorded")
    ui.caption("Current-period player statistics require the separately authenticated Fantrax weekly export; missing observations remain NA.")
    section_header(ui,"Advanced Data","Commissioner-only incremental WhoScored workflow")
    if advanced_status:
        acquired=advanced_status.get('stable',0)+advanced_status.get('preliminary',0);eligible=acquired+advanced_status.get('missing_eligible',0)
        ui.write(f"Eligible completed: {eligible} · Acquired: {acquired} · Missing eligible: {advanced_status.get('missing_eligible',0)} · Stable: {advanced_status.get('stable',0)} · Preliminary: {advanced_status.get('preliminary',0)} · Provider IDs resolved: {advanced_status.get('provider_ids_resolved',0)}")
    else:ui.caption("No current-season advanced plan has been recorded.")
    ui.code(DESKTOP_COMMAND,language="text")
    section_header(ui,"Provider Lifecycle","Correction-aware current-season evidence")
    maturity=period_state.current_status if hasattr(period_state,"current_status") else period_progress['state']
    ui.write(f"Fantrax GW{period_state.current_period or 'â€”'}: {str(maturity).replace('_',' ')} · explicit commissioner finalization required")
    ui.caption("WhoScored coverage above · preliminary/stable rechecks are cache-first · Understat coverage above · SOT monitoring · clearances caveated · fantasy assists source-specific")

    section_header(ui,"Smart Refresh","Updates everything available from validated caches and identifies desktop-only acquisition.")
    if ui.button("SMART REFRESH",type="primary",use_container_width=True): _smart_refresh(ui,operations,season_id)

    section_header(ui,"Status","The datasets that power each live feature.")
    groups={"Standings":("league_standings",),"Players":("player_ownership",),"Rosters":("current_rosters",),"Managers":("league_teams","manager_week_summary"),"Analytics":("weekly_matchups","manager_week_summary"),"Ownership":("player_ownership","roster_history"),"Draft HQ":("draft_rankings",)}
    rows=[]
    for label,keys in groups.items():
        items=[by_key[key] for key in keys if key in by_key]; valid=bool(items) and all(item.get("validation_result")=="valid" for item in items)
        timestamp=max((item.get("build_timestamp") or item.get("source_timestamp") or "" for item in items),default="")
        rows.append({"Status":"✓" if valid else "—","Area":label,"Last Update":_friendly_time(timestamp),"Rows":sum(int(item.get("row_count") or 0) for item in items) if items else "—","Version":next((str(item.get("sha256",""))[:10] for item in items if item.get("sha256")),"—")})
    ui.dataframe(rows,use_container_width=True,hide_index=True)

    section_header(ui,"Recent Activity","Latest actions from this browser session.")
    activity=ui.session_state.get("_operations_activity",[])
    if activity: ui.dataframe([{key:value for key,value in item.items() if key!="_technical"} for item in activity[:8]],use_container_width=True,hide_index=True)
    else: ui.info("No refresh activity recorded in this session yet.")
    failed=next((item.get("_technical") for item in activity if item.get("_technical")),None)
    if failed:
        with ui.expander("Technical details",expanded=False):
            ui.json(failed)

    section_header(ui,"Data Health","Readiness indicators for the live platform.")
    health=ui.columns(3)
    items=(("Player Registry",by_key.get("player_ownership",{}).get("row_count",0),"Current identities"),("Roster Tracking",by_key.get("roster_snapshots_manifest",{}).get("row_count",0),"Snapshots and ownership"),("Draft HQ","Protected","Frozen baseline unchanged"))
    for column,item in zip(health,items):
        with column: metric_card(ui,*item)

    section_header(ui,"Cup Tournament","Initialize frozen seeds, build progression, or validate registered Cup artifacts.")
    probe=getattr(data,"probe",None); snapshot_exists=bool(callable(probe) and probe("cup_seed_snapshot",season_id,namespace).status is DataStatus.AVAILABLE)
    cup_actions=(("Initialize Cup","initialize_cup",snapshot_exists),("Build Cup Bracket","build_cup_bracket",False),("Rebuild Cup","rebuild_cup",False),("Validate Cup","validate_cup",False))
    columns=ui.columns(4)
    for column,(label,operation,extra_disabled) in zip(columns,cup_actions):
        if column.button(label,key=f"cup_operation_{operation}",disabled=extra_disabled or not operations.can_run(operation,season_id),use_container_width=True):
            result=_run_once(ui,operations,operation,season_id,{},f"{label}…")
            if result: _record_activity(ui,label,result); _show_result(ui,[result])

    with ui.expander("Advanced",expanded=False):
        ui.write("Read-only diagnostics, manifests, and source coverage.")
        with ui.expander("Diagnostics"): ui.json({"health":"healthy" if healthy else "review","datasets":len(datasets),"current_period":period_state.current_period,"latest_completed_period":period_state.latest_completed_period,"period_source":period_state.source})
        with ui.expander("View Source Coverage"): ui.write("Player and stat coverage is refreshed in data/quality/season_2627 after every live build.")
        with ui.expander("Manifest and checksum tools"): ui.json(manifest or {"status":"No manifest available"})
        with ui.expander("Developer Tools"): ui.code("OperationsService registered operations",language="text")

def _render_data_status(ui:Any,season_id:str)->None:
    section_header(ui,"Data Status","Can the current application data be trusted?")
    status=derive_refresh_status(season=season_id)
    ui.dataframe(status.rename(columns={'area':'Area','state':'State','last_successful_refresh':'Last successful refresh','coverage':'Coverage','detail':'Detail'}),use_container_width=True,hide_index=True)
    ui.info(f"Desktop-only provider acquisition uses one commissioner command: {DESKTOP_COMMAND}")


def _friendly_time(value:Any)->str:
    if not value: return "Never"
    try: return datetime.fromisoformat(str(value).replace("Z","+00:00")).astimezone().strftime("%b %d, %I:%M %p").replace(" 0"," ")
    except (ValueError,TypeError): return str(value)


def _record_activity(ui:Any,label:str,result:OperationResult)->None:
    entry={"Time":datetime.now().astimezone().strftime("%I:%M %p").lstrip("0"),"Action":label,"Duration":f"{result.duration_seconds:.1f}s","Result":result.status or ("Success" if result.success else "Failed"),"Message":result.message}
    if not result.success:
        entry["_technical"]={"operation_name":result.operation_key,"status":result.status or "FAILED","failed_stage":result.failed_stage or "unknown","source":result.source,"resolved_season_id":result.season_id,"resolved_league_id":result.resolved_league_id,"scoring_period":result.scoring_period,"rows_before":result.rows_before,"rows_after":result.rows_after,"command_script":result.command,"exit_code":result.return_code,"stdout":result.stdout,"stderr":result.stderr,"exception_type":result.error_type,"exception_message":result.exception_message,"elapsed_seconds":round(result.duration_seconds,3)}
    ui.session_state["_operations_activity"]=[entry,*ui.session_state.get("_operations_activity",[])][:20]


def _show_result(ui:Any,results:list[OperationResult])->None:
    if results and all(result.success for result in results): _clear_streamlit_cache(ui); ui.success("Refresh completed successfully")
    else:
        ui.error("Refresh could not be completed. Your previous valid data was retained.")
        details=" ".join(f"{result.error_type or ''} {result.exception_message or ''} {result.stderr}" for result in results)
        if "FantraxAccessError" in details or "HTTP 401" in details or "HTTP 403" in details:
            ui.warning("Fantrax denied access. Confirm that the league is public or configure the supported authenticated session credential before retrying.")


def _refresh_league(ui:Any,operations:OperationsService,season_id:str)->None:
    running_key="_operation_running_core_refresh"
    if ui.session_state.get(running_key) or ui.session_state.get("_operation_running_refresh_live_fantrax_sources"):
        ui.warning("This operation is already running.");return
    ui.session_state[running_key]=True
    progress=ui.progress(0,text="Connecting to Fantrax");started=datetime.now()
    try:
        with ui.spinner("Refreshing registered core stages…"):run=run_core_refresh(operations,season_id)
    finally:ui.session_state[running_key]=False
    for stage in run.stages:_record_activity(ui,stage.label,stage.result)
    progress.progress(100,text=run.status.title());_show_core_result(ui,run)
    ui.write(f"Core refresh {run.status.lower()} · {len(run.succeeded)}/{len(run.stages)} stages succeeded · {(datetime.now()-started).total_seconds():.1f}s")


def _show_core_result(ui:Any,run:CoreRefreshResult)->None:
    if run.status=="SUCCESS":_clear_streamlit_cache(ui);ui.success("Refresh completed successfully")
    elif run.status=="PARTIAL":ui.warning("Refresh completed with attention needed. Previous validated data was retained for failed stages.")
    else:ui.error("Refresh failed at a required stage. Previous validated data was retained.")
    if run.attention:
        ui.write("Needs attention: "+" · ".join(f"{stage.label} — {stage.result.exception_message or stage.result.failed_stage or stage.result.message}" for stage in run.attention))


def _smart_refresh(ui:Any,operations:OperationsService,season_id:str)->None:
    key="_operation_running_smart_refresh"
    if ui.session_state.get(key):ui.warning("This operation is already running.");return
    ui.session_state[key]=True
    try:
        with ui.spinner("Planning and rebuilding current products…"):
            run:SmartRefreshResult=run_smart_refresh(operations,season_id)
    finally:ui.session_state[key]=False
    plan=run.final_plan
    ui.write(f"GW{plan.current_gw or '—'} SMART REFRESH")
    ui.write(f"Fantrax: {plan.fantrax.status} · WhoScored: {plan.whoscored.status} · Understat: {plan.understat.status}")
    if plan.previous_gw:ui.write(f"GW{plan.previous_gw} recheck: {plan.previous_gw_status.replace('_',' ').title()}")
    ui.write(f"GW{plan.current_gw or '—'}: {plan.current_gw_status.replace('_',' ').title()}")
    if run.status=="DESKTOP_REQUIRED":
        ui.warning("DESKTOP DATA REQUIRED")
        ui.write("Run this on the commissioner desktop, then return here and click SMART REFRESH again.")
        ui.code(DESKTOP_COMMAND,language="text")
    elif run.status=="PASS":_clear_streamlit_cache(ui);ui.success("REFRESH COMPLETE")
    else:ui.error("Refresh failed. Previous validated data was retained.")


def _render_finalized(ui:Any,data:DataManager,season:Any,namespace:str)->None:
    ui.success(f"{season.display_name} is finalized and protected from live API refreshes.")
    columns=ui.columns(3); columns[0].metric("Season",season.display_name); columns[1].metric("Status","Finalized"); columns[2].metric("Data folder",season.season_id)
    manifest=_load_optional_json(data,"season_manifest",season.season_id,namespace,ui)
    if manifest is not None:
        with ui.expander("Season manifest"): ui.json(manifest)
    validation=_load_optional_text(data,"finalization_validation_report",season.season_id,namespace,ui)
    if validation is not None:
        with ui.expander("Finalization validation",expanded=True): ui.text(validation)


def _run_once(ui:Any,operations:OperationsService,operation_id:str,season_id:str,parameters:dict[str,Any],spinner_label:str)->OperationResult|None:
    key=f"_operation_running_{operation_id}"
    if ui.session_state.get(key,False): ui.warning("This operation is already running."); return None
    ui.session_state[key]=True
    try:
        with ui.spinner(spinner_label): return operations.run(operation_id,season_id,parameters)
    except (OperationNotAllowedError,OperationParameterError) as exc: ui.error(str(exc)); return None
    finally: ui.session_state[key]=False


def _load_optional_json(data:DataManager,key:str,season_id:str,namespace:str,ui:Any)->Any|None:
    try: result=data.load_json(key,season_id,namespace)
    except DatasetNotFoundError: return None
    except (DatasetValidationError,UnsupportedFormatError) as exc: ui.warning(str(exc)); return None
    return None if result.status in {DataStatus.MISSING,DataStatus.EMPTY} else result.data


def _load_optional_text(data:DataManager,key:str,season_id:str,namespace:str,ui:Any)->str|None:
    try: result=data.load_text(key,season_id,namespace,encoding="utf-8",errors="replace")
    except DatasetNotFoundError: return None
    except (DatasetValidationError,UnsupportedFormatError) as exc: ui.warning(str(exc)); return None
    return result.data if result.status not in {DataStatus.MISSING,DataStatus.EMPTY} and isinstance(result.data,str) else None


def _load_optional_frame(data:DataManager,key:str,season_id:str,namespace:str,ui:Any):
    import pandas as pd
    loader=getattr(data,"load",None)
    if not callable(loader):return pd.DataFrame()
    try:result=data.load(key,season_id,namespace)
    except (DatasetNotFoundError,DatasetValidationError,UnsupportedFormatError) as exc:
        if not isinstance(exc,DatasetNotFoundError):ui.warning(str(exc))
        return pd.DataFrame()
    return result.data


def _clear_streamlit_cache(ui:Any)->None:
    clear=getattr(getattr(ui,"cache_data",None),"clear",None)
    if callable(clear): clear()
