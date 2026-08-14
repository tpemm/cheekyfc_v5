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

import pandas as pd


MINIMUM_ALL_PLAYER_COLUMNS={"ID","Player","FPts"}
WEEKLY_RAW_NAME="weekly_player_stats.csv"
METADATA_NAME="metadata.json"


def utc_now()->str: return datetime.now(timezone.utc).isoformat()
def clean_id(value:object)->str: return str(value).strip().strip("*")
def sha256_bytes(value:bytes)->str: return hashlib.sha256(value).hexdigest()


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
    else: targets=[value for value in completed if not valid_cached_period(raw_root,value)]
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
    available=pd.read_csv(BytesIO(all_players),encoding="utf-8-sig")
    missing=MINIMUM_ALL_PLAYER_COLUMNS-set(available)
    if missing: raise ValueError(f"All-player weekly export missing columns: {sorted(missing)}")
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
    if "goals_against_outfield" in result:
        result["goals_against"]=pd.to_numeric(result.get("goals_against"),errors="coerce").combine_first(pd.to_numeric(result["goals_against_outfield"],errors="coerce"))
    result=result.drop(columns=[c for c in ("ID","fantasy_points_roster") if c in result])
    return result


def commit_period(raw_root:Path,period:int,all_players:bytes,team_exports:dict[str,tuple[str,bytes]],*,finalized:bool,retrieved_at:str|None=None)->dict:
    """Validate fully before atomically replacing any valid period cache."""
    frame=normalize_period_exports(all_players,team_exports,period=period)
    if frame.empty: raise ValueError(f"Completed period {period} returned an empty weekly dataset")
    if frame["fantrax_player_id"].isna().any() or frame.duplicated("fantrax_player_id").any(): raise ValueError("Weekly export has missing or duplicate player IDs")
    folder=period_directory(raw_root,period); folder.mkdir(parents=True,exist_ok=True)
    stage=folder/"_staging"; stage.mkdir(exist_ok=True)
    available_stage=stage/"all_players.csv"; available_stage.write_bytes(all_players)
    for team_id,(name,content) in team_exports.items(): (stage/f"team_{team_id}.csv").write_bytes(content)
    normalized_stage=stage/WEEKLY_RAW_NAME; frame.to_csv(normalized_stage,index=False); checksum=sha256_bytes(normalized_stage.read_bytes()); timestamp=retrieved_at or utc_now()
    metadata={"period":int(period),"status":"ACQUIRED","row_count":len(frame),"checksum":checksum,"retrieved_at":timestamp,"finalized":bool(finalized),"unresolved_players":0,"validation_status":"valid","source":"Fantrax authenticated weekly CSV exports"}
    (stage/METADATA_NAME).write_text(json.dumps(metadata,indent=2),encoding="utf-8")
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
    base=f"https://www.fantrax.com/fantasy/league/{league_id}"
    all_url=base+f"/players;miscDisplayType=1;pageNumber=1;timeframeTypeCode=BY_PERIOD;transactionPeriod={period};view=STATS;statusOrTeamFilter=ALL"
    def download(page,url:str)->bytes:
        error=None
        for attempt in range(retries):
            try:
                page.goto(url,wait_until="domcontentloaded",timeout=timeout_ms); page.wait_for_timeout(1400)
                if page.get_by_text("Login",exact=True).count()>0: raise RuntimeError("Fantrax authenticated session expired")
                tip=page.locator("div[role='tooltip']",has_text="Download all as CSV").first; tip.wait_for(state="attached",timeout=15_000); trigger=page.locator(f'[aria-describedby="{tip.get_attribute("id")}"]').first
                with page.expect_download(timeout=30_000) as info: trigger.click(force=True)
                return Path(info.value.path()).read_bytes()
            except Exception as exc:
                error=exc
                if attempt+1<retries: time.sleep(1.5*(attempt+1))
        raise RuntimeError(f"Fantrax weekly CSV download failed after {retries} attempts: {error}")
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True); context=browser.new_context(accept_downloads=True,storage_state=str(auth)); page=context.new_page()
        try:
            all_players=download(page,all_url); exports={}
            for team_id,item in teams.items():
                name=str(item.get("name") or team_id); url=base+f"/team/roster;teamId={team_id};scoringCategoryType=5;period={period};statsType=1;view=STATS;timeframeTypeCode=BY_PERIOD"
                exports[team_id]=(name,download(page,url))
            return all_players,exports
        finally: context.close(); browser.close()


def refresh_weekly_stats(league_payload:dict,*,league_id:str,raw_root:Path,project_root:Path,mode:str="normal",period:int|None=None,force:bool=False,fetcher:Callable|None=None,now:datetime|None=None)->dict:
    plan=plan_periods(league_payload,raw_root,mode=mode,period=period,force=force,now=now)
    if not plan["completed_periods"] and not plan["targets"]: return {**plan,"status":"PRESEASON_NO_PLAYER_STATS","periods":[]}
    fetch=fetcher or playwright_fetch_period; results=[]; completed=set(plan["completed_periods"])
    for target in plan["targets"]:
        started=time.perf_counter(); all_players,teams=fetch(league_id=league_id,period=target,teams=league_payload.get("teamInfo",{}),project_root=project_root)
        metadata=commit_period(raw_root,target,all_players,teams,finalized=target in completed); metadata["elapsed_seconds"]=round(time.perf_counter()-started,3); results.append(metadata)
    status="NO_NEW_WEEKLY_DATA" if not results else "WEEKLY_STATS_UPDATED"
    return {**plan,"status":status,"periods":results}


def weekly_period_status(raw_root:Path,league_payload:dict,*,now:datetime|None=None)->pd.DataFrame:
    current,completed=period_state(league_payload,now=now); rows=[]
    periods=sorted(set(completed+([current] if current else [])))
    for period in periods:
        metadata=read_period_metadata(raw_root,period); rows.append({"period":period,"status":metadata.get("status") or ("PERIOD_NOT_COMPLETED" if period==current else "MISSING_COMPLETED_PERIOD"),"row_count":metadata.get("row_count",0),"checksum":metadata.get("checksum"),"retrieved_at":metadata.get("retrieved_at"),"finalized":bool(metadata.get("finalized",False)),"unresolved_players":metadata.get("unresolved_players",0),"validation_status":metadata.get("validation_status","pending")})
    return pd.DataFrame(rows,columns=("period","status","row_count","checksum","retrieved_at","finalized","unresolved_players","validation_status"))
