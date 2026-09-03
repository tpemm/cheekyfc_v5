"""Incremental current-season WhoScored planning and cache maturity."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

POST_MATCH_DELAY_MINUTES=90
EXPECTED_MATCH_MINUTES=120
STABILIZATION_INTERVAL_HOURS=18
MANIFEST_COLUMNS=("canonical_match_id","whoscored_match_id","date","kickoff","home_club_id","away_club_id","resolution_status","resolution_method","fixture_status","acquisition_status","cache_status","first_acquired_at","last_checked_at","payload_hash","event_count","lineup_count","ratings_count","quality_status","planner_status")

WHOSCORED_TEAM_NAMES={
    "arsenal":"arsenal","aston villa":"aston_villa","bournemouth":"afc_bournemouth",
    "brentford":"brentford","brighton":"brighton_hove_albion","chelsea":"chelsea",
    "coventry":"coventry_city","coventry city":"coventry_city",
    "crystal palace":"crystal_palace","everton":"everton","fulham":"fulham",
    "hull":"hull_city","hull city":"hull_city","ipswich":"ipswich_town",
    "ipswich town":"ipswich_town","leeds":"leeds_united","leeds united":"leeds_united",
    "liverpool":"liverpool","manchester city":"manchester_city","man city":"manchester_city",
    "manchester united":"manchester_united","man utd":"manchester_united",
    "newcastle":"newcastle_united","newcastle united":"newcastle_united",
    "nottingham forest":"nottingham_forest","sunderland":"sunderland",
    "tottenham":"tottenham_hotspur","tottenham hotspur":"tottenham_hotspur",
}


def _now(value:Any=None)->pd.Timestamp:
    result=pd.Timestamp(value or datetime.now(timezone.utc))
    return result.tz_localize("UTC") if result.tzinfo is None else result.tz_convert("UTC")


def canonical_2627_fixtures(frame:pd.DataFrame)->pd.DataFrame:
    """Collapse the registered two-perspective team fixture model to 380 matches."""
    source=frame.drop_duplicates("match_id").copy()
    result=pd.DataFrame({"canonical_match_id":source.match_id.astype(str),"kickoff":source.kickoff_time,
                         "fixture_status":source.status,"completed":source.completed.fillna(False).astype(bool)})
    if {"home_club_id","away_club_id"}.issubset(source):
        result["home_club_id"]=source.home_club_id;result["away_club_id"]=source.away_club_id
    else:
        result["home_club_id"]=source.apply(lambda r:r.club_id if r.home_away=="H" else r.opponent_id,axis=1)
        result["away_club_id"]=source.apply(lambda r:r.opponent_id if r.home_away=="H" else r.club_id,axis=1)
    result["date"]=pd.to_datetime(result["kickoff"],utc=True,errors="coerce").dt.strftime("%Y-%m-%d")
    return result.sort_values(["kickoff","canonical_match_id"]).reset_index(drop=True)


def cached_provider_schedule(cache_root:Path)->pd.DataFrame:
    """Read the permanent soccerdata calendar cache without opening a browser."""
    import json
    rows=[]
    for path in sorted(cache_root.glob("matches/ENG-Premier League_2627_*.json")):
        payload=json.loads(path.read_text(encoding="utf-8"))
        for tournament in payload.get("tournaments",[]):
            for match in tournament.get("matches",[]):
                home=WHOSCORED_TEAM_NAMES.get(str(match.get("homeTeamName","")).casefold())
                away=WHOSCORED_TEAM_NAMES.get(str(match.get("awayTeamName","")).casefold())
                rows.append({"whoscored_match_id":match.get("id"),"kickoff":match.get("startTimeUtc") or match.get("startTime"),"home_club_id":home,"away_club_id":away})
    return pd.DataFrame(rows).drop_duplicates("whoscored_match_id") if rows else pd.DataFrame(columns=["whoscored_match_id","kickoff","home_club_id","away_club_id"])


def exact_provider_resolution(fixtures:pd.DataFrame,provider_schedule:pd.DataFrame)->pd.DataFrame:
    """Resolve only one exact UTC date plus canonical home/away identity."""
    out=fixtures.copy();out["whoscored_match_id"]=pd.NA;out["resolution_status"]="UNRESOLVED";out["resolution_method"]=pd.NA
    if provider_schedule.empty:return out
    provider=provider_schedule.copy();provider["_date"]=pd.to_datetime(provider.kickoff,utc=True,errors="coerce").dt.date
    for index,row in out.iterrows():
        date=pd.to_datetime(row.kickoff,utc=True,errors="coerce").date()
        hit=provider[provider._date.eq(date)&provider.home_club_id.eq(row.home_club_id)&provider.away_club_id.eq(row.away_club_id)]
        if len(hit)==1:out.at[index,"whoscored_match_id"]=hit.iloc[0].whoscored_match_id;out.at[index,"resolution_status"]="RESOLVED_EXACT";out.at[index,"resolution_method"]="exact UTC date + canonical home/away"
        elif len(hit)>1:out.at[index,"resolution_status"]="AMBIGUOUS_REJECTED"
        else:
            # A league club pair occurs once per home venue. This remains an exact
            # identity join and safely tolerates kickoff rescheduling in a stale
            # canonical fixture snapshot; duplicate pairs are rejected.
            pair=provider[provider.home_club_id.eq(row.home_club_id)&provider.away_club_id.eq(row.away_club_id)]
            if len(pair)==1:out.at[index,"whoscored_match_id"]=pair.iloc[0].whoscored_match_id;out.at[index,"resolution_status"]="RESOLVED_EXACT_PAIR";out.at[index,"resolution_method"]="exact canonical home/away (provider kickoff rescheduled)"
            elif len(pair)>1:out.at[index,"resolution_status"]="AMBIGUOUS_REJECTED"
    return out


def fixture_eligibility(row:pd.Series,*,now:Any=None,post_match_delay_minutes:int=POST_MATCH_DELAY_MINUTES)->str:
    instant=_now(now);kickoff=pd.to_datetime(row.get("kickoff"),utc=True,errors="coerce")
    if pd.isna(kickoff) or kickoff>instant:return "FUTURE"
    eligible_at=kickoff+pd.Timedelta(minutes=EXPECTED_MATCH_MINUTES+post_match_delay_minutes)
    if instant<eligible_at:return "IN_PROGRESS_OR_TOO_RECENT"
    cache_value=row.get("cache_status");acquisition_value=row.get("acquisition_status")
    cache="MISSING" if pd.isna(cache_value) else str(cache_value).upper();acquisition="" if pd.isna(acquisition_value) else str(acquisition_value).upper()
    if cache=="STABLE":return "STABLE"
    if cache=="PRELIMINARY":return "ELIGIBLE_PRELIMINARY"
    if acquisition in {"FAILED","TIMEOUT"}:return "FAILED_RETRYABLE"
    return "ELIGIBLE_MISSING"


def build_live_manifest(fixtures:pd.DataFrame,*,existing:pd.DataFrame|None=None,provider_schedule:pd.DataFrame|None=None,now:Any=None)->pd.DataFrame:
    base=exact_provider_resolution(canonical_2627_fixtures(fixtures),provider_schedule if provider_schedule is not None else pd.DataFrame())
    prior=existing.copy() if existing is not None else pd.DataFrame()
    retained=[c for c in MANIFEST_COLUMNS if c not in {"canonical_match_id","date","kickoff","home_club_id","away_club_id","resolution_status","resolution_method","fixture_status","planner_status"}]
    if not prior.empty:
        base=base.merge(prior[["canonical_match_id",*[c for c in retained if c in prior]]].drop_duplicates("canonical_match_id"),on="canonical_match_id",how="left",suffixes=("","_prior"))
        for column in retained:
            prior_column=column+"_prior"
            if prior_column in base:base[column]=base[prior_column].combine_first(base.get(column));base=base.drop(columns=prior_column)
    for column in MANIFEST_COLUMNS:
        if column not in base:base[column]=pd.NA
    base["planner_status"]=base.apply(lambda row:fixture_eligibility(row,now=now),axis=1)
    return base.reindex(columns=MANIFEST_COLUMNS).sort_values(["kickoff","canonical_match_id"]).reset_index(drop=True)


def acquisition_plan(manifest:pd.DataFrame)->dict[str,Any]:
    counts=manifest.planner_status.value_counts().to_dict();resolved=manifest.whoscored_match_id.notna()
    acquire=manifest.planner_status.isin(["ELIGIBLE_MISSING","FAILED_RETRYABLE"])&resolved
    recheck=manifest.planner_status.eq("ELIGIBLE_PRELIMINARY")&resolved
    return {"fixtures_scheduled":len(manifest),"future":counts.get("FUTURE",0),"too_recent":counts.get("IN_PROGRESS_OR_TOO_RECENT",0),
            "stable":counts.get("STABLE",0),"preliminary":counts.get("ELIGIBLE_PRELIMINARY",0),"missing_eligible":counts.get("ELIGIBLE_MISSING",0),
            "failed_retryable":counts.get("FAILED_RETRYABLE",0),"provider_ids_resolved":int(resolved.sum()),"would_acquire":int(acquire.sum()),"would_recheck":int(recheck.sum())}


def maturity_after_recheck(previous:pd.Series,current:dict[str,Any],*,checked_at:Any=None,stabilization_hours:int=STABILIZATION_INTERVAL_HOURS)->str:
    checked=_now(checked_at);prior_time=pd.to_datetime(previous.get("last_checked_at"),utc=True,errors="coerce")
    unchanged=(str(previous.get("payload_hash"))==str(current.get("payload_hash")) and pd.to_numeric(previous.get("event_count"),errors="coerce")==pd.to_numeric(current.get("event_count"),errors="coerce") and pd.to_numeric(previous.get("lineup_count"),errors="coerce")==pd.to_numeric(current.get("lineup_count"),errors="coerce") and pd.to_numeric(previous.get("ratings_count"),errors="coerce")==pd.to_numeric(current.get("ratings_count"),errors="coerce"))
    old_enough=pd.notna(prior_time) and checked-prior_time>=pd.Timedelta(hours=stabilization_hours)
    return "STABLE" if unchanged and old_enough else "PRELIMINARY"
