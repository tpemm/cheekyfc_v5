"""Incremental authenticated Fantrax weekly CSV acquisition for 2026/27."""
from __future__ import annotations

from datetime import datetime, timezone
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Callable
from uuid import uuid4

import pandas as pd


MINIMUM_ALL_PLAYER_COLUMNS={"ID","Player","FPts"}
WEEKLY_RAW_NAME="weekly_player_stats.csv"
METADATA_NAME="metadata.json"
SEASON_PERIOD_CODE="SEASON_926_BY_PERIOD"


def utc_now()->str: return datetime.now(timezone.utc).isoformat(timespec="seconds")
def clean_id(value:object)->str: return str(value).strip().strip("*")
def sha256_bytes(value:bytes)->str: return hashlib.sha256(value).hexdigest()

def all_player_url(league_id:str,period:int,*,start_date:str="2026-08-21",end_date:str|None=None)->str:
    end_date=end_date or datetime.now().astimezone().date().isoformat()
    return (f"https://www.fantrax.com/fantasy/league/{league_id}/players;"
            f"seasonOrProjection={SEASON_PERIOD_CODE};timeframeTypeCode=BY_PERIOD;"
            f"startDate={start_date};endDate={end_date};transactionPeriod={int(period)};"
            f"pageNumber=1;view=STATS;statusOrTeamFilter=ALL")

def roster_url(league_id:str,period:int,team_id:str)->str:
    if not str(team_id).strip():raise ValueError("Registered Fantrax team ID is required")
    return (f"https://www.fantrax.com/fantasy/league/{league_id}/team/roster;"
            f"period={int(period)};statsType=1;teamId={team_id};"
            f"seasonOrProjection={SEASON_PERIOD_CODE};timeframeTypeCode=BY_PERIOD")


def validate_csv_response(content:bytes,*,required:set[str],label:str)->pd.DataFrame:
    """Reject login/HTML bodies and malformed exports before promotion."""
    from io import BytesIO
    prefix=content.lstrip()[:200].lower()
    if not content or prefix.startswith((b"<!doctype html",b"<html")) or b"<form" in prefix and b"login" in prefix:
        raise ValueError(f"{label} returned HTML/login content instead of CSV")
    try:frame=pd.read_csv(BytesIO(content),encoding="utf-8-sig")
    except Exception as exc:raise ValueError(f"{label} is not a complete CSV: {exc}") from exc
    missing=required-set(frame.columns)
    if missing:raise ValueError(f"{label} missing columns: {sorted(missing)}")
    return frame


def period_state(league_payload:dict, *, now:datetime|None=None)->tuple[int|None,list[int]]:
    """Return current and completed periods from authoritative Fantrax boundaries."""
    moment=pd.Timestamp(now or datetime.now(timezone.utc)); moment=moment.tz_localize("UTC") if moment.tzinfo is None else moment.tz_convert("UTC")
    current=None; completed=[]
    for item in league_payload.get("scoringPeriods",[]):
        period=int(item["number"]); start=pd.to_datetime(item.get("startDate"),errors="coerce",utc=True); end=pd.to_datetime(item.get("endDate"),errors="coerce",utc=True)
        if pd.isna(start) or pd.isna(end): continue
        if start<=moment<=end: current=period
        if end<moment: completed.append(period)
    return current,sorted(completed)


def period_directory(raw_root:Path,period:int)->Path: return raw_root/"player_stats"/f"period_{int(period):02d}"


def read_period_metadata(raw_root:Path,period:int)->dict:
    path=period_directory(raw_root,period)/METADATA_NAME
    try:return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError,json.JSONDecodeError):return {}


def valid_cached_period(raw_root:Path,period:int)->bool:
    folder=period_directory(raw_root,period); metadata=read_period_metadata(raw_root,period); path=folder/WEEKLY_RAW_NAME
    if metadata.get("validation_status")!="valid" or not path.exists(): return False
    return bool(metadata.get("checksum")) and metadata["checksum"]==sha256_bytes(path.read_bytes())


def plan_periods(league_payload:dict,raw_root:Path,*,mode:str="normal",period:int|None=None,force:bool=False,now:datetime|None=None)->dict:
    current,completed=period_state(league_payload,now=now)
    if mode=="force_current": targets=[period or current] if period or current else []
    elif mode=="backfill": targets=completed
    else:
        targets=[value for value in completed if not valid_cached_period(raw_root,value)]
        if current is not None:targets.append(current)
    if not force: targets=[value for value in targets if value is not None and not (valid_cached_period(raw_root,value) and read_period_metadata(raw_root,value).get("finalized"))]
    return {"current_period":current,"completed_periods":completed,"targets":sorted(set(int(x) for x in targets if x is not None))}


def _parse_team_export(content:bytes,team_id:str,team_name:str)->pd.DataFrame:
    lines=content.decode("utf-8-sig",errors="replace").splitlines(); markers={'"","Goalkeeper"':'goalkeeper','"","Outfielder"':'outfielder'}; sections=[]; index=0
    while index<len(lines):
        marker=lines[index].strip()
        if marker not in markers: index+=1; continue
        section=markers[marker]; index+=1
        if index>=len(lines): break
        header=next(csv.reader([lines[index]])); index+=1; rows=[]
        while index<len(lines) and lines[index].strip() and lines[index].strip() not in markers:
            row=next(csv.reader([lines[index]])); rows.append(row[:len(header)]+[""]*max(0,len(header)-len(row))); index+=1
        if rows:
            frame=pd.DataFrame(rows,columns=header); frame["section"]=section; sections.append(frame)
    if not sections: raise ValueError(f"Team export {team_name} contains no Goalkeeper/Outfielder sections")
    frame=pd.concat(sections,ignore_index=True); frame=frame[~frame.get("Player",pd.Series(index=frame.index,dtype=str)).astype(str).str.contains("Totals",case=False,na=False)]
    if "ID" not in frame: raise ValueError(f"Team export {team_name} is missing ID")
    frame=frame[frame["ID"].notna()&frame["ID"].astype(str).str.strip().ne("")].copy(); frame["fantrax_player_id"]=frame["ID"].map(clean_id); frame["manager_id"]=team_id; frame["manager_name"]=team_name
    return frame


def normalize_period_exports(all_players:bytes,team_exports:dict[str,tuple[str,bytes]],*,period:int)->pd.DataFrame:
    """Combine the proven all-player score export with roster advanced-event exports."""
    from io import BytesIO
    available=validate_csv_response(all_players,required=MINIMUM_ALL_PLAYER_COLUMNS,label="All-player weekly export")
    if available.empty: return pd.DataFrame()
    available["fantrax_player_id"]=available["ID"].map(clean_id)
    base=available.rename(columns={"Player":"player_name","Team":"club","Position":"fantrax_position","Opponent":"opponent","FPts":"fantasy_points"})
    teams=[]
    for team_id,(team_name,content) in team_exports.items(): teams.append(_parse_team_export(content,team_id,team_name))
    rostered=pd.concat(teams,ignore_index=True) if teams else pd.DataFrame(columns=["fantrax_player_id"])
    aliases={"Pos":"started_position","Eligible":"fantrax_position_roster","Status":"lineup_status","Fantasy Points":"fantasy_points_roster","GP":"appearance","GS":"start","Min":"minutes","CS":"clean_sheets","GA":"goals_against","Sv":"saves","YC":"yellow_cards","RC":"red_cards","PKS":"penalties_saved","SBON":"successful_dribbles_on","SBOF":"successful_dribbles_off","TkW":"tackles_won","DIS":"dispossessions","G":"goals","KP":"key_passes","AT":"assists","Int":"interceptions","CLR":"clearances","CoS":"successful_dribbles","AER":"aerials_won","HCS":"high_claims","Sm":"smothers","OG":"own_goals","SOT":"shots_on_target","AC":"accurate_crosses","BS":"blocks","PKM":"penalties_missed","PKD":"penalties_drawn","GAO":"goals_against_outfield"}
    keep=["fantrax_player_id","manager_id","manager_name",*aliases]
    rostered=rostered[[c for c in keep if c in rostered]].rename(columns=aliases)
    result=base.merge(rostered,on="fantrax_player_id",how="left",suffixes=("","_roster")); result["period"]=int(period)
    if "fantasy_points_roster" in result: result["fantasy_points"]=pd.to_numeric(result["fantasy_points_roster"],errors="coerce").combine_first(pd.to_numeric(result["fantasy_points"],errors="coerce"))
    for column in ("fantasy_points","appearance","start","minutes","clean_sheets","goals_against","saves","yellow_cards","red_cards","penalties_saved","tackles_won","dispossessions","goals","key_passes","assists","interceptions","clearances","successful_dribbles","aerials_won","own_goals","shots_on_target","accurate_crosses","blocks","penalties_missed"):
        if column in result: result[column]=pd.to_numeric(result[column],errors="coerce")
    # A zero-filled export for a club that has not played is availability, not
    # an observed zero-stat player performance. Preserve that distinction.
    if "club" in result and "appearance" in result:
        played_clubs=set(result.loc[pd.to_numeric(result.appearance,errors="coerce").gt(0),"club"].dropna().astype(str))
        unobserved=~result.club.astype(str).isin(played_clubs)
        observed_fields=[column for column in ("fantasy_points","appearance","start","minutes","clean_sheets","goals_against","saves","yellow_cards","red_cards","penalties_saved","tackles_won","dispossessions","goals","key_passes","assists","interceptions","clearances","successful_dribbles","aerials_won","own_goals","shots_on_target","accurate_crosses","blocks","penalties_missed") if column in result]
        result.loc[unobserved,observed_fields]=pd.NA
    if "goals_against_outfield" in result:
        result["goals_against"]=pd.to_numeric(result.get("goals_against"),errors="coerce").combine_first(pd.to_numeric(result["goals_against_outfield"],errors="coerce"))
    result=result.drop(columns=[c for c in ("ID","fantasy_points_roster") if c in result])
    return result


def commit_period(raw_root:Path,period:int,all_players:bytes,team_exports:dict[str,tuple[str,bytes]],*,finalized:bool,retrieved_at:str|None=None,expected_team_ids:set[str]|None=None,team_failures:dict[str,str]|None=None)->dict:
    """Validate fully before atomically replacing any valid period cache."""
    frame=normalize_period_exports(all_players,team_exports,period=period)
    if frame.empty: raise ValueError(f"Completed period {period} returned an empty weekly dataset")
    if frame["fantrax_player_id"].isna().any() or frame.duplicated("fantrax_player_id").any(): raise ValueError("Weekly export has missing or duplicate player IDs")
    expected=set(expected_team_ids or team_exports);acquired=set(team_exports);missing=sorted(expected-acquired);failures=dict(team_failures or {})
    folder=period_directory(raw_root,period); folder.mkdir(parents=True,exist_ok=True)
    # Keep the transactional suffix short enough for Windows workspaces whose
    # project root is already close to MAX_PATH (notably OneDrive roots).
    stage=raw_root/f".weekly_stage_{uuid4().hex[:8]}"; stage.mkdir()
    available_stage=stage/"all_players.csv"; available_stage.write_bytes(all_players)
    for team_id,(name,content) in team_exports.items(): (stage/f"team_{team_id}.csv").write_bytes(content)
    normalized_stage=stage/WEEKLY_RAW_NAME; frame.to_csv(normalized_stage,index=False); checksum=sha256_bytes(normalized_stage.read_bytes()); timestamp=retrieved_at or utc_now()
    maturity="FINALIZED" if finalized else "LIVE";status="ACQUIRED" if not missing else "PARTIAL_MANAGER_COVERAGE"
    metadata={"period":int(period),"status":status,"maturity":maturity,"row_count":len(frame),"all_player_rows":len(validate_csv_response(all_players,required=MINIMUM_ALL_PLAYER_COLUMNS,label="All-player weekly export")),"manager_exports_acquired":len(acquired),"manager_exports_expected":len(expected),"missing_team_ids":missing,"team_failures":failures,"checksum":checksum,"retrieved_at":timestamp,"finalized":bool(finalized),"unresolved_players":0,"validation_status":"valid" if not missing else "partial","source":"Fantrax authenticated weekly CSV exports"}
    (stage/METADATA_NAME).write_text(json.dumps(metadata,indent=2),encoding="utf-8")
    stamp=timestamp.replace(":","").replace("+","").replace("-","")
    snapshot=folder/"snapshots"/stamp
    # Test/OneDrive roots can exceed the legacy Windows 260-character limit.
    # Preserve the public per-period layout whenever it is addressable.
    if os.name=="nt" and len(str(snapshot.resolve()))>240:snapshot=raw_root/"snapshots"/f"p{int(period):02d}_{stamp}"
    snapshot.mkdir(parents=True,exist_ok=True)
    for staged in stage.iterdir():
        if staged.name!=WEEKLY_RAW_NAME:(snapshot/staged.name).write_bytes(staged.read_bytes())
    for staged in stage.iterdir(): staged.replace(folder/staged.name)
    stage.rmdir(); return metadata


def _auth_path(project_root:Path)->Path:
    supplied=os.environ.get("FANTRAX_AUTH_STATE_PATH","").strip()
    if supplied:return Path(supplied)
    scoped=project_root/"data"/"raw"/"fantrax"/"2627"/"fantrax_auth_state.json"
    legacy=project_root/"data"/"raw"/"fantrax"/"fantrax_auth_state.json"
    return scoped if scoped.exists() else legacy


def playwright_fetch_period(*,league_id:str,period:int,teams:dict[str,dict],project_root:Path,retries:int=3,timeout_ms:int=60_000)->tuple[bytes,dict[str,tuple[str,bytes]]]:
    """Reuse the proven authenticated Download all as CSV interaction."""
    try: from playwright.sync_api import sync_playwright
    except ImportError as exc: raise RuntimeError("Playwright is required for Fantrax weekly CSV acquisition") from exc
    auth=_auth_path(project_root)
    if not auth.exists(): raise RuntimeError(f"Authenticated Fantrax browser state is required: {auth}. Log in once and save the Playwright storage state.")
    all_url=all_player_url(league_id,period)
    download_root=project_root/"data"/"raw"/"fantrax"/"2627"/"_browser_downloads"/uuid4().hex[:8]
    download_root.mkdir(parents=True,exist_ok=True)
    def download(page,url:str,*,expected_team_name:str|None=None)->bytes:
        error=None
        for attempt in range(retries):
            try:
                page.goto(url,wait_until="domcontentloaded",timeout=timeout_ms); page.wait_for_timeout(1400)
                if page.get_by_text("Login",exact=True).count()>0: raise RuntimeError("Fantrax authenticated session expired")
                if expected_team_name and expected_team_name.casefold() not in page.locator("body").inner_text().casefold():raise RuntimeError(f"Wrong Fantrax team page: expected {expected_team_name}")
                # The current Angular UI renders an icon-only `get_app` button.
                # `mattooltip` is present on the button itself and is more stable
                # than the generated tooltip/aria-describedby relationship.
                trigger=page.locator('button[mattooltip="Download all as CSV"]').first
                if not trigger.count():trigger=page.locator('button:has(mat-icon:text-is("get_app"))').first
                trigger.wait_for(state="visible",timeout=15_000)
                dismiss=page.get_by_role("button",name="Never",exact=True)
                if dismiss.count():dismiss.click()
                before={path.name for path in download_root.iterdir() if path.is_file()}
                trigger.click()
                deadline=time.monotonic()+30
                while time.monotonic()<deadline:
                    candidates=[path for path in download_root.iterdir() if path.is_file() and path.name not in before and not path.name.endswith(".crdownload")]
                    if candidates:
                        candidate=max(candidates,key=lambda path:path.stat().st_mtime_ns);page.wait_for_timeout(300);return candidate.read_bytes()
                    page.wait_for_timeout(200)
                raise RuntimeError("Fantrax export control produced no file in the controlled download directory")
            except Exception as exc:
                error=exc
                if attempt+1<retries: time.sleep(1.5*(attempt+1))
        raise RuntimeError(f"Fantrax weekly CSV download failed after {retries} attempts: {error}")
    executable=os.environ.get("FANTRAX_BROWSER_EXECUTABLE","").strip()
    if not executable and os.name=="nt":
        candidates=(Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"))
        executable=str(next((path for path in candidates if path.exists()),""))
    with sync_playwright() as playwright:
        launch={"headless":os.environ.get("FANTRAX_HEADLESS","1").strip().lower() not in {"0","false","no"}}
        if executable:launch["executable_path"]=executable
        launch["downloads_path"]=str(download_root)
        browser=playwright.chromium.launch(**launch); context=browser.new_context(accept_downloads=True,storage_state=str(auth)); page=context.new_page()
        try:
            all_players=download(page,all_url); exports={};failures={}
            for team_id,item in teams.items():
                name=str(item.get("name") or team_id); url=roster_url(league_id,period,team_id)
                try:exports[team_id]=(name,download(page,url,expected_team_name=name))
                except Exception as exc:failures[team_id]=f"{type(exc).__name__}: {exc}"
            return all_players,exports,failures
        finally: context.close(); browser.close()


def refresh_weekly_stats(league_payload:dict,*,league_id:str,raw_root:Path,project_root:Path,mode:str="normal",period:int|None=None,force:bool=False,fetcher:Callable|None=None,now:datetime|None=None)->dict:
    plan=plan_periods(league_payload,raw_root,mode=mode,period=period,force=force,now=now)
    if not plan["completed_periods"] and not plan["targets"]: return {**plan,"status":"PRESEASON_NO_PLAYER_STATS","periods":[]}
    fetch=fetcher or playwright_fetch_period; results=[]; completed=set(plan["completed_periods"])
    for target in plan["targets"]:
        started=time.perf_counter(); fetched=fetch(league_id=league_id,period=target,teams=league_payload.get("teamInfo",{}),project_root=project_root);all_players,teams=fetched[:2];failures=fetched[2] if len(fetched)>2 else {}
        metadata=commit_period(raw_root,target,all_players,teams,finalized=target in completed,expected_team_ids=set(league_payload.get("teamInfo",{})),team_failures=failures); metadata["elapsed_seconds"]=round(time.perf_counter()-started,3); results.append(metadata)
    status="NO_NEW_WEEKLY_DATA" if not results else "PARTIAL_MANAGER_COVERAGE" if any(x["status"]!="ACQUIRED" for x in results) else "WEEKLY_STATS_UPDATED"
    return {**plan,"status":status,"periods":results}


def weekly_period_status(raw_root:Path,league_payload:dict,*,now:datetime|None=None)->pd.DataFrame:
    current,completed=period_state(league_payload,now=now); rows=[]
    periods=sorted(set(completed+([current] if current else [])))
    for period in periods:
        metadata=read_period_metadata(raw_root,period); rows.append({"period":period,"status":metadata.get("status") or ("PERIOD_NOT_COMPLETED" if period==current else "MISSING_COMPLETED_PERIOD"),"row_count":metadata.get("row_count",0),"checksum":metadata.get("checksum"),"retrieved_at":metadata.get("retrieved_at"),"finalized":bool(metadata.get("finalized",False)),"unresolved_players":metadata.get("unresolved_players",0),"validation_status":metadata.get("validation_status","pending")})
    return pd.DataFrame(rows,columns=("period","status","row_count","checksum","retrieved_at","finalized","unresolved_players","validation_status"))
