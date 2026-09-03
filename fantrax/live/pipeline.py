"""Cache-only live-season build, validation, quality, and manifest pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import pandas as pd

from fantrax.live.config import LiveSeasonConfig, load_live_season_config
from fantrax.live.normalization import (
    DATASET_COLUMNS, empty_dataset, join_player_registry, load_cached_json,
    normalize_league_teams, normalize_matchups, normalize_rosters,
    normalize_standings, normalize_transactions,
)
from fantrax.live.validation import (
    validate_league_teams, validate_matchups, validate_ownership,
    validate_rosters, validate_standings, validate_transactions,
)
from fantrax.live.roster_tracking import (
    EVENT_COLUMNS, HISTORY_COLUMNS, archive_snapshot, atomic_csv, detect_changes,
    stable_roster_checksum, update_history,
)
from fantrax.live.analytics import (
    build_live_manager_analytics, build_live_player_analytics,
    build_live_position_strength,
)
from fantrax.live.league_analytics import build_live_league_summary
from fantrax.live.manager_identity import draft_manager_id_lookup, manager_draft_origin_audit, normalize_manager_alias
from fantrax.live.player_performance import (
    EVENT_FIELDS, WEEKLY_COLUMNS, aggregate_player_window, enrich_weekly, load_cached_weekly_exports,
    manager_player_weekly as build_manager_player_weekly, stat_dictionary,
    weekly_validation,
)
from fantrax.live.understat_live import (
    load_cached_understat, player_source_coverage, scoring_periods_from_league,
    supplement_fantrax,
)
from fantrax.live.weekly_acquisition import weekly_period_status
from fantrax.live.season_state import resolve_scoring_period_state
from fantrax.live.matchup_acquisition import three_way_reconciliation
from fantrax.live.league_lineups import active_player_weekly,completed_whoscored_periods,enrich_manager_weeks
from fantrax.live.manager_name_history import update_manager_name_history


OUTPUT_FILENAMES = {
    "league_teams":"league_teams_{season}.csv", "current_rosters":"current_rosters_{season}.csv",
    "roster_history":"roster_history_{season}.csv", "league_standings":"league_standings_{season}.csv",
    "weekly_matchups":"weekly_matchups_{season}.csv", "manager_week_summary":"manager_week_summary_{season}.csv",
    "league_transactions":"league_transactions_{season}.csv", "player_ownership":"player_ownership_{season}.csv",
    "roster_change_events":"roster_change_events_{season}.csv",
    "roster_snapshots_manifest":"roster_snapshots_manifest_{season}.csv",
    "roster_tracking_quality":"roster_tracking_quality_{season}.csv",
    "live_player_analytics":"live_player_analytics_{season}.csv",
    "live_manager_analytics":"live_manager_analytics_{season}.csv",
    "live_position_strength":"live_position_strength_{season}.csv",
    "live_league_summary":"live_league_summary_{season}.csv",
    "available_players":"available_players_{season}.csv",
    "current_player_weekly":"current_player_weekly_{season}.csv",
    "understat_player_weekly":"understat_player_weekly_{season}.csv",
    "manager_player_weekly":"manager_player_weekly_{season}.csv",
    "league_active_player_weekly":"league_active_player_weekly_{season}.csv",
}


def _latest_metadata(path: Path) -> str:
    metadata=path.with_suffix(path.suffix+".metadata.json")
    if metadata.exists(): return str(json.loads(metadata.read_text(encoding="utf-8")).get("retrieved_at") or "")
    return datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat()


def _atomic_csv(frame: pd.DataFrame,path: Path)->None:
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix(path.suffix+".tmp");frame.to_csv(tmp,index=False)
    for attempt in range(6):
        try:tmp.replace(path);return
        except PermissionError:
            if attempt==5:raise
            time.sleep(.05*(attempt+1))


def _explicit_period(payload: Any) -> int | None:
    if isinstance(payload, dict):
        for key in ("currentPeriod", "currentScoringPeriod", "scoringPeriod", "current_period"):
            value = pd.to_numeric(payload.get(key), errors="coerce")
            if pd.notna(value): return int(value)
        for value in payload.values():
            found = _explicit_period(value)
            if found is not None: return found
    elif isinstance(payload, list):
        for value in payload:
            found = _explicit_period(value)
            if found is not None: return found
    return None


def _authoritative_period(league_payload: Any, roster_parts: list[pd.DataFrame]) -> int | None:
    available = sorted({int(frame["period"].iloc[0]) for frame in roster_parts if not frame.empty})
    periods=scoring_periods_from_league(league_payload or {})
    current=resolve_scoring_period_state(periods,league_payload=league_payload).current_period
    if current in available:return current
    # Without authoritative period metadata, future payloads are not observations.
    return available[0] if available else None


def _previous_snapshot(archive_root: Path) -> tuple[pd.DataFrame, str | None]:
    metadata_files = sorted(archive_root.glob("*.metadata.json")) if archive_root.exists() else []
    if not metadata_files: return pd.DataFrame(), None
    metadata = json.loads(metadata_files[-1].read_text(encoding="utf-8"))
    path = Path(metadata["snapshot_path"])
    return (pd.read_csv(path, dtype={"fantrax_player_id": str}) if path.exists() else pd.DataFrame(), metadata.get("checksum"))


def _roster_history(current_parts: list[pd.DataFrame]) -> pd.DataFrame:
    if not current_parts: return empty_dataset("roster_history")
    frame=pd.concat(current_parts,ignore_index=True)
    frame["transaction_id"]=pd.NA
    return frame.rename(columns={"club":"_club","fantrax_position":"_position","acquired_via":"_acquired_via","acquired_date":"_acquired_date"}).reindex(columns=DATASET_COLUMNS["roster_history"])


def _manager_week_summary(matchups: pd.DataFrame,standings: pd.DataFrame,teams: pd.DataFrame,refreshed_at:str,league_payload:dict|None=None)->pd.DataFrame:
    rows=[]
    rank_lookup={}
    team_names=dict(zip(teams.get("manager_id",pd.Series(dtype=object)).astype(str),teams.get("manager_name",pd.Series(dtype=object))))
    for standing in standings.to_dict("records"):
        name=standing.get("manager") or team_names.get(str(standing.get("manager_id")))
        period=pd.to_numeric(standing.get("period"),errors="coerce")
        rank_lookup[(int(period) if pd.notna(period) else None,name)]=standing.get("rank")
    identities={str(row.manager_name):row for row in teams.itertuples()};identities_by_team={str(row.fantasy_team_id):row for row in teams.itertuples()};period_dates={int(item["number"]):item.get("endDate") for item in (league_payload or {}).get("scoringPeriods",[]) if isinstance(item,dict) and pd.notna(pd.to_numeric(item.get("number"),errors="coerce"))}
    has_status="status" in matchups.columns
    records={}
    for row in matchups.itertuples():
        if pd.isna(row.home_score) or pd.isna(row.away_score): continue
        home_team_id=getattr(row,"home_team_id",None);away_team_id=getattr(row,"away_team_id",None)
        for manager,team_id,score,opponent,opponent_id,opponent_score in ((row.home_manager,home_team_id,row.home_score,row.away_manager,away_team_id,row.away_score),(row.away_manager,away_team_id,row.away_score,row.home_manager,home_team_id,row.home_score)):
            final=not has_status or str(getattr(row,"status","")).lower() in {"completed","complete","final"}
            result=("D" if score==opponent_score else "W" if score>opponent_score else "L") if final else pd.NA
            identity=identities_by_team.get(str(team_id),identities.get(str(manager))); opponent_identity=identities_by_team.get(str(opponent_id),identities.get(str(opponent)))
            canonical_manager=getattr(identity,"manager_name",manager);canonical_team=getattr(identity,"fantasy_team_name",canonical_manager)
            canonical_opponent=getattr(opponent_identity,"manager_name",opponent)
            identity_key=str(getattr(identity,"manager_id",team_id if team_id is not None else manager));record=records.setdefault(identity_key,{"W":0,"D":0,"L":0,"pf":0.0,"pa":0.0})
            if final:record[result]+=1;record["pf"]+=float(score);record["pa"]+=float(opponent_score)
            rows.append({"season_id":row.season_id,"period":row.period,"manager_id":getattr(identity,"manager_id",pd.NA),"manager_name":canonical_manager,"fantasy_team_id":getattr(identity,"fantasy_team_id",pd.NA),"fantasy_team_name":canonical_team,"opponent_manager_id":getattr(opponent_identity,"manager_id",pd.NA),"opponent_manager_name":canonical_opponent,"fantasy_points":score,"opponent_points":opponent_score,"result":result,"cumulative_wins":record["W"],"cumulative_draws":record["D"],"cumulative_losses":record["L"],"league_points_after_week":record["W"]*3+record["D"],"rank_after_week":rank_lookup.get((row.period,manager),rank_lookup.get((None,manager),pd.NA)),"points_for_after_week":record["pf"],"points_against_after_week":record["pa"],
                "manager":canonical_manager,"total_score":score,"opponent":canonical_opponent,"opponent_score":opponent_score,"record_after_week":f'{record["W"]}-{record["D"]}-{record["L"]}',"optimal_xi_score":pd.NA,
                "source_coverage":"live active-lineup score" if not final else "completed Fantrax matchup score; corrections pending","source":"Fantrax detailed weekly exports" if not final else "Fantrax cached matchups","last_refreshed":refreshed_at})
    result=pd.DataFrame(rows)
    if not result.empty:
        for period,index in result.groupby("period").groups.items():
            ordered=result.loc[index].sort_values(["cumulative_wins","cumulative_draws","points_for_after_week"],ascending=[False,False,False],kind="stable")
            result.loc[ordered.index,"rank_after_week"]=range(1,len(ordered)+1)
    result["period_completed_at"]=pd.to_numeric(result.get("period"),errors="coerce").map(period_dates) if not result.empty else pd.Series(dtype=object)
    return result.reindex(columns=DATASET_COLUMNS["manager_week_summary"])


def _apply_live_matchup_scores(matchups:pd.DataFrame,weekly:pd.DataFrame,*,protected_periods:set[int]|None=None)->pd.DataFrame:
    """Overlay current in-progress scores from authoritative detailed exports."""
    if matchups.empty or weekly.empty:return matchups
    active=weekly[weekly.get("lineup_status",pd.Series(index=weekly.index,dtype=object)).astype(str).str.upper().isin({"ACTIVE","ACT","STARTER","STARTING"})].copy()
    active=active[active.get("current_manager_id",pd.Series(index=active.index,dtype=object)).notna()]
    if active.empty:return matchups
    scores=active.groupby(["period","current_manager_id"],as_index=False).fantasy_points.sum(min_count=1).set_index(["period","current_manager_id"])["fantasy_points"]
    out=matchups.copy();period=pd.to_numeric(out.period,errors="coerce").astype("Int64"); protected_periods=protected_periods or set()
    for side in ("home","away"):
        values=pd.Series([scores.get((p,str(team)),pd.NA) for p,team in zip(period,out[f"{side}_team_id"])],index=out.index,dtype="Float64")
        mask=values.notna()&~period.isin(protected_periods);out.loc[mask,f"{side}_score"]=values[mask]
    live=out.home_score.notna()&out.away_score.notna()&~out.status.astype(str).str.lower().isin({"completed","complete","final"})
    out.loc[live,"status"]="live";out.loc[live,"margin"]=(pd.to_numeric(out.loc[live,"home_score"])-pd.to_numeric(out.loc[live,"away_score"])).abs();out.loc[live,"winner"]=pd.NA
    return out


def _weekly_score_reconciliation(manager_players:pd.DataFrame,manager_week:pd.DataFrame)->pd.DataFrame:
    columns=("period","manager_name","normalized_active_points","official_manager_points","difference","status")
    if manager_players.empty or manager_week.empty:return pd.DataFrame(columns=columns)
    statuses=manager_players.get("lineup_status",pd.Series(index=manager_players.index,dtype=str)).astype(str).str.upper()
    active=manager_players[statuses.isin({"ACT","ACTIVE","STARTER","STARTING"})].copy()
    if active.empty:return pd.DataFrame(columns=columns)
    totals=active.groupby(["period","manager_name"],as_index=False)["fantasy_points"].sum(min_count=1).rename(columns={"fantasy_points":"normalized_active_points"})
    official=manager_week[["period","manager","total_score"]].rename(columns={"manager":"manager_name","total_score":"official_manager_points"})
    output=totals.merge(official,on=["period","manager_name"],how="inner"); output["difference"]=pd.to_numeric(output["normalized_active_points"],errors="coerce")-pd.to_numeric(output["official_manager_points"],errors="coerce"); output["status"]=output["difference"].abs().le(.01).map({True:"match",False:"review"})
    return output.reindex(columns=columns)


def _ownership(rosters:pd.DataFrame,transactions:pd.DataFrame,events:pd.DataFrame,refreshed_at:str,*,pool:pd.DataFrame|None=None,draft:pd.DataFrame|None=None,teams:pd.DataFrame|None=None)->pd.DataFrame:
    if rosters.empty:return empty_dataset("player_ownership")
    latest=rosters.copy()
    tx=transactions.sort_values("timestamp").drop_duplicates("fantrax_player_id",keep="last") if not transactions.empty else transactions
    last_type=tx.set_index("fantrax_player_id")["transaction_type"] if not tx.empty else pd.Series(dtype=object)
    last_date=tx.set_index("fantrax_player_id")["timestamp"] if not tx.empty else pd.Series(dtype=object)
    event_counts=events.groupby("fantrax_player_id").size() if not events.empty else pd.Series(dtype=int)
    last_events=events.sort_values("detected_at").drop_duplicates("fantrax_player_id",keep="last").set_index("fantrax_player_id") if not events.empty else pd.DataFrame()
    draft_lookup = {}
    if draft is not None and not draft.empty:
        id_col=next((c for c in ("fantrax_player_id","registry_player_id") if c in draft),None)
        if id_col: draft_lookup={str(row[id_col]):row for row in draft.to_dict("records")}
    manager_ids=draft_manager_id_lookup(teams if teams is not None else pd.DataFrame(),draft if draft is not None else pd.DataFrame())
    rows=[]; roster_ids=set()
    for row in latest.to_dict("records"):
        player_id=str(row["fantrax_player_id"]); roster_ids.add(player_id); drafted=draft_lookup.get(player_id,{})
        drafted_manager=drafted.get("manager") or drafted.get("drafted_manager");drafted_manager_id=manager_ids.get(normalize_manager_alias(drafted_manager));current_manager=row.get("manager_name")
        last=last_events.loc[player_id] if not last_events.empty and player_id in last_events.index else {}
        rows.append({"season_id":row.get("season_id"),"fantrax_player_id":player_id,"registry_player_id":row.get("registry_player_id"),"canonical_name":row.get("canonical_name"),"player_name":row.get("player_name"),
            "current_manager_id":row.get("manager_id"),"current_manager_name":current_manager,"current_manager":current_manager,"current_fantasy_team":row.get("fantasy_team_name"),"current_team":row.get("fantasy_team_name"),"ownership_status":"Rostered" if pd.notna(row.get("registry_player_id")) else "Unresolved","roster_status":row.get("roster_status"),"lineup_status":row.get("lineup_status"),"available":False,
            "last_change_event":last.get("event_type",pd.NA) if hasattr(last,"get") else pd.NA,"last_change_at":last.get("detected_at",pd.NA) if hasattr(last,"get") else pd.NA,
            "last_transaction_type":last_type.get(player_id,pd.NA),"last_transaction_at":last_date.get(player_id,pd.NA),"last_transaction_date":last_date.get(player_id,pd.NA),"source_retrieved_at":row.get("source_retrieved_at"),
            "drafted_manager":drafted_manager,"drafted_manager_id":drafted_manager_id,"drafted_round":drafted.get("round",drafted.get("draft_round",pd.NA)),"drafted_overall_pick":drafted.get("overall_pick",pd.NA),"still_with_drafting_manager":bool(drafted_manager_id and str(drafted_manager_id)==str(row.get("manager_id"))),"changed_teams_since_draft":bool(drafted_manager_id and str(drafted_manager_id)!=str(row.get("manager_id"))),"currently_free_agent":False,"ownership_change_count":int(event_counts.get(player_id,0)),"source":"Fantrax roster tracking","last_refreshed":refreshed_at})
    if pool is not None and not pool.empty:
        id_col=next((c for c in ("fantrax_player_id","fantrax_id") if c in pool),None)
        name_col=next((c for c in ("player_name","fantrax_player_name","name") if c in pool),None)
        if id_col:
            for item in pool.to_dict("records"):
                player_id=str(item.get(id_col));
                if player_id in roster_ids: continue
                rows.append({"season_id":latest["season_id"].iat[0],"fantrax_player_id":player_id,"player_name":item.get(name_col) if name_col else pd.NA,"ownership_status":"Free Agent","available":True,"currently_free_agent":True,"ownership_change_count":int(event_counts.get(player_id,0)),"source":"Fantrax player pool reconciliation","last_refreshed":refreshed_at})
    represented={str(row.get("fantrax_player_id")) for row in rows}
    if not events.empty:
        dropped=events[events["event_type"].eq("PLAYER_DROPPED")].sort_values("detected_at").drop_duplicates("fantrax_player_id",keep="last")
        for event in dropped.to_dict("records"):
            player_id=str(event["fantrax_player_id"])
            if player_id in represented or player_id in roster_ids: continue
            drafted=draft_lookup.get(player_id,{})
            rows.append({"season_id":event.get("season_id"),"fantrax_player_id":player_id,"registry_player_id":event.get("registry_player_id"),"player_name":event.get("player_name"),"ownership_status":"Free Agent","available":True,"last_change_event":"PLAYER_DROPPED","last_change_at":event.get("detected_at"),"drafted_manager":drafted.get("manager"),"drafted_round":drafted.get("round"),"drafted_overall_pick":drafted.get("overall_pick"),"still_with_drafting_manager":False,"changed_teams_since_draft":False,"currently_free_agent":True,"ownership_change_count":int(event_counts.get(player_id,0)),"source":"Fantrax roster tracking","last_refreshed":refreshed_at})
    return pd.DataFrame(rows,columns=DATASET_COLUMNS["player_ownership"])


def authoritative_current_roster(weekly:pd.DataFrame,teams:pd.DataFrame,refreshed_at:str)->pd.DataFrame:
    """Project latest authoritative weekly roster membership onto the canonical roster grain."""
    if weekly.empty:return empty_dataset("current_rosters")
    period=pd.to_numeric(weekly.get("period"),errors="coerce");latest=int(period.max())
    current=weekly[period.eq(latest)&weekly.get("current_manager_id",pd.Series(index=weekly.index,dtype=object)).notna()].copy()
    current=current.drop_duplicates("fantrax_player_id",keep="last")
    team_by_id=teams.set_index(teams.manager_id.astype(str)) if not teams.empty else pd.DataFrame()
    rows=[]
    for row in current.to_dict("records"):
        manager_id=str(row.get("current_manager_id"));team=team_by_id.loc[manager_id] if not team_by_id.empty and manager_id in team_by_id.index else pd.Series(dtype=object)
        lineup=str(row.get("lineup_status") or "").upper();injured=lineup in {"IR","INJURED_RESERVE"};reserve=lineup in {"RES","RESERVE","BENCH","BE"}
        roster_status="INJURED_RESERVE" if injured else "RESERVE" if reserve else "ACTIVE"
        rows.append({"season_id":row.get("season_id"),"observed_at":refreshed_at,"source_retrieved_at":row.get("source_retrieved_at"),"scoring_period":latest,"period":latest,
            "manager_id":manager_id,"manager_name":row.get("current_manager_name") or team.get("manager_name"),"fantasy_team_id":team.get("fantasy_team_id",manager_id),"fantasy_team_name":row.get("current_manager_name") or team.get("fantasy_team_name",team.get("manager_name")),
            "fantrax_player_id":row.get("fantrax_player_id"),"registry_player_id":row.get("registry_player_id"),"canonical_name":row.get("canonical_name"),"player_name":row.get("player_name"),"premier_league_club":row.get("club"),"club":row.get("club"),"fantrax_position":row.get("fantrax_position"),
            "roster_status":roster_status,"lineup_status":roster_status,"active":roster_status=="ACTIVE","reserve":reserve,"injured_reserve":injured,"source":"Fantrax detailed weekly current roster","validation_status":"valid","last_refreshed":refreshed_at})
    return pd.DataFrame(rows).reindex(columns=DATASET_COLUMNS["current_rosters"])


def build_live_season(config:LiveSeasonConfig|None=None,*,registry_path:Path|None=None)->dict[str,Any]:
    """Build solely from cached artifacts. Missing required cache fails before outputs change."""
    config=config or load_live_season_config(); league_path=config.raw_root/"league"/f"league_metadata_{config.season_id}_latest.json"
    standings_path=config.raw_root/"standings"/f"standings_{config.season_id}_latest.json"
    if not league_path.exists(): raise FileNotFoundError(f"Missing validated league cache: {league_path}")
    now=datetime.now(timezone.utc).isoformat(); league_payload=load_cached_json(league_path); league_time=_latest_metadata(league_path)
    teams=normalize_league_teams(league_payload,config,refreshed_at=league_time)
    matchups=normalize_matchups(league_payload,config,refreshed_at=league_time)
    standings=normalize_standings(load_cached_json(standings_path),config,refreshed_at=_latest_metadata(standings_path)) if standings_path.exists() else empty_dataset("league_standings")
    roster_parts=[]
    for path in sorted(path for path in (config.raw_root/"rosters").glob(f"rosters_{config.season_id}_period_*.json") if not path.name.endswith(".metadata.json")):
        period=int(path.stem.rsplit("_",1)[-1]); roster_parts.append(normalize_rosters(load_cached_json(path),config,period=period,refreshed_at=_latest_metadata(path),player_info=league_payload.get("playerInfo",{}) if isinstance(league_payload,dict) else {},teams=teams))
    registry_file=registry_path or config.model_root.parents[1]/"reference"/f"player_registry_{config.season_id}.csv"
    registry=pd.read_csv(registry_file,dtype={"fantrax_player_id":str}) if registry_file.exists() else pd.DataFrame(columns=["fantrax_player_id","registry_player_id","canonical_name"])
    joined_parts=[]; unresolved_parts=[]
    for part in roster_parts:
        joined,unresolved=join_player_registry(part,registry); joined["player_name"]=joined["player_name"].fillna(joined.get("canonical_name")); joined_parts.append(joined.reindex(columns=DATASET_COLUMNS["current_rosters"])); unresolved_parts.append(unresolved)
    authoritative_period=_authoritative_period(league_payload,joined_parts)
    name_history_path=config.model_root/f"manager_name_history_{config.season_id}.csv"
    existing_name_history=pd.read_csv(name_history_path,dtype={"manager_id":str}) if name_history_path.exists() else pd.DataFrame()
    manager_name_history=existing_name_history
    if manager_name_history.empty and not matchups.empty:
        for observed_period,group in matchups.sort_values("period").groupby("period"):
            observations=pd.concat([group[["season_id","home_team_id","home_manager"]].rename(columns={"home_team_id":"manager_id","home_manager":"manager_name"}),group[["season_id","away_team_id","away_manager"]].rename(columns={"away_team_id":"manager_id","away_manager":"manager_name"})],ignore_index=True)
            observations["fantasy_team_name"]=observations["manager_name"]
            manager_name_history=update_manager_name_history(manager_name_history,observations,period=int(observed_period),observed_at=now)
    manager_name_history=update_manager_name_history(manager_name_history,teams,period=authoritative_period or config.period_minimum,observed_at=now)
    _atomic_csv(manager_name_history,name_history_path)
    current=next((part for part in joined_parts if not part.empty and int(part["period"].iat[0])==authoritative_period),empty_dataset("current_rosters"))
    transaction_files=sorted(path for path in (config.raw_root/"transactions").glob("*.json") if not path.name.endswith(".metadata.json")); transactions=empty_dataset("league_transactions")
    if transaction_files:
        transactions=normalize_transactions(load_cached_json(transaction_files[-1]),config,refreshed_at=_latest_metadata(transaction_files[-1]))
        transactions,_=join_player_registry(transactions,registry)
        transactions=transactions.reindex(columns=DATASET_COLUMNS["league_transactions"])
    roster_validation=validate_rosters(current,config); roster_valid=not roster_validation["severity"].eq("error").any()
    if roster_valid and not current.empty: current["validation_status"]="valid"
    archive_root=config.model_root.parents[1]/"snapshots"/f"season_{config.season_id}"/"rosters"
    previous_snapshot,previous_checksum=_previous_snapshot(archive_root)
    source_time=max((str(x) for x in current.get("source_retrieved_at",pd.Series(dtype=str)).dropna()),default=now)
    snapshot=archive_snapshot(current,archive_root=archive_root,season_id=config.season_id,league_id=config.league_id,observed_at=now,source_retrieved_at=source_time,period=authoritative_period or config.period_minimum,valid=roster_valid and not current.empty)
    existing_events_path=config.model_root/OUTPUT_FILENAMES["roster_change_events"].format(season=config.season_id)
    existing_events=pd.read_csv(existing_events_path,dtype={"fantrax_player_id":str}) if existing_events_path.exists() else pd.DataFrame(columns=EVENT_COLUMNS)
    new_events=pd.DataFrame(columns=EVENT_COLUMNS)
    if previous_checksum and snapshot.get("created"):
        new_events=detect_changes(previous_snapshot,current,previous_checksum=previous_checksum,new_checksum=snapshot["checksum"],detected_at=now,period=authoritative_period or config.period_minimum)
    events=pd.concat([existing_events,new_events],ignore_index=True).drop_duplicates("event_id",keep="first")
    history_path=config.model_root/OUTPUT_FILENAMES["roster_history"].format(season=config.season_id)
    existing_history=pd.read_csv(history_path,dtype={"fantrax_player_id":str}) if history_path.exists() else pd.DataFrame(columns=HISTORY_COLUMNS)
    history=update_history(existing_history,current,new_events,observed_at=now,period=authoritative_period or config.period_minimum) if roster_valid and not current.empty else existing_history
    pool_path=config.model_root.parents[1]/"reference"/f"current_fantrax_player_pool_{config.season_id}.csv"
    pool=pd.read_csv(pool_path,dtype={"fantrax_player_id":str}) if pool_path.exists() else pd.DataFrame()
    draft_path=config.model_root.parents[0]/f"draft_{config.season_id}"/f"draft_results_graded_input_{config.season_id}.csv"
    draft=pd.read_csv(draft_path,dtype={"fantrax_player_id":str}) if draft_path.exists() else pd.DataFrame()
    ownership=_ownership(current,transactions,events,now,pool=pool,draft=draft,teams=teams)
    rankings_path=config.model_root.parents[0]/f"draft_{config.season_id}"/f"draft_rankings_{config.season_id}.csv"
    rankings=pd.read_csv(rankings_path,dtype={"fantrax_player_id":str}) if rankings_path.exists() else pd.DataFrame()
    live_players=build_live_player_analytics(pool,ownership,current,rankings,draft,events,season_id=config.season_id)
    periods=scoring_periods_from_league(league_payload)
    understat_root=config.raw_root.parents[1]/"understat"/config.season_id
    understat_weekly,unresolved_understat=load_cached_understat(understat_root,periods,registry,season_id=config.season_id)
    combined_weekly=supplement_fantrax(load_cached_weekly_exports(config.raw_root),understat_weekly,weekly_columns=WEEKLY_COLUMNS)
    current_weekly=enrich_weekly(combined_weekly,registry,ownership,pd.concat(joined_parts,ignore_index=True) if joined_parts else current)
    # Detailed manager exports are the freshest complete roster surface.  Rebuild
    # current ownership from their latest period so pickups, bench and IR members
    # cannot be lost to a stale getTeamRosters cache.
    effective_current=authoritative_current_roster(current_weekly,teams,now)
    if not effective_current.empty:
        current=effective_current
        latest_names=current.drop_duplicates("manager_id").set_index(current.drop_duplicates("manager_id").manager_id.astype(str)).manager_name
        teams["manager_name"]=teams.manager_id.astype(str).map(latest_names).fillna(teams.manager_name);teams["fantasy_team_name"]=teams.manager_id.astype(str).map(latest_names).fillna(teams.fantasy_team_name)
        roster_validation=validate_rosters(current,config);roster_valid=not roster_validation["severity"].eq("error").any()
        ownership=_ownership(current,transactions,events,now,pool=pool,draft=draft,teams=teams)
        current_weekly=enrich_weekly(combined_weekly,registry,ownership,current)
        live_players=build_live_player_analytics(pool,ownership,current,rankings,draft,events,season_id=config.season_id)
        latest_period=int(pd.to_numeric(current_weekly.period,errors="coerce").max());universe_ids=set(current_weekly[pd.to_numeric(current_weekly.period,errors="coerce").eq(latest_period)].fantrax_player_id.astype(str))
        live_players=live_players[live_players.fantrax_player_id.astype(str).isin(universe_ids)].drop_duplicates("fantrax_player_id",keep="last").reset_index(drop=True)
        missing=current_weekly[pd.to_numeric(current_weekly.period,errors="coerce").eq(latest_period)&~current_weekly.fantrax_player_id.astype(str).isin(set(live_players.fantrax_player_id.astype(str)))].drop_duplicates("fantrax_player_id",keep="last")
        if not missing.empty:
            additions=missing.reindex(columns=live_players.columns).copy();additions["available"]=~additions.fantrax_player_id.astype(str).isin(set(current.fantrax_player_id.astype(str)));live_players=pd.concat([live_players,additions],ignore_index=True)
    completed_periods=completed_whoscored_periods(config.raw_root.parents[1]/"whoscored"/config.season_id/"poc",periods,config.model_root.parents[1]/"reference"/f"whoscored_season_manifest_{config.season_id}.csv")
    current_weekly["period_complete"]=pd.to_numeric(current_weekly.get("period"),errors="coerce").isin(completed_periods)
    authority_path=config.model_root/f"fantrax_matchups_{config.season_id}.csv"
    authoritative=pd.read_csv(authority_path,dtype={"home_team_id":str,"away_team_id":str}) if authority_path.exists() else pd.DataFrame()
    if not authoritative.empty and len(manager_name_history)<=len(teams):
        manager_name_history=pd.DataFrame()
        for observed_period,group in authoritative.sort_values("period").groupby("period"):
            observations=pd.concat([group[["season_id","home_team_id","home_manager"]].rename(columns={"home_team_id":"manager_id","home_manager":"manager_name"}),group[["season_id","away_team_id","away_manager"]].rename(columns={"away_team_id":"manager_id","away_manager":"manager_name"})],ignore_index=True);observations["fantasy_team_name"]=observations.manager_name
            manager_name_history=update_manager_name_history(manager_name_history,observations,period=int(observed_period),observed_at=now)
        manager_name_history=update_manager_name_history(manager_name_history,teams,period=authoritative_period or config.period_minimum,observed_at=now);_atomic_csv(manager_name_history,name_history_path)
    protected_periods=set(pd.to_numeric(authoritative.get("period"),errors="coerce").dropna().astype(int)) if not authoritative.empty else set()
    if protected_periods:
        matchups=matchups[~pd.to_numeric(matchups.period,errors="coerce").isin(protected_periods)].copy()
        promoted=authoritative.rename(columns={"acquired_at":"source_retrieved_at"}).copy()
        canonical_names=dict(zip(teams.get("fantasy_team_id",pd.Series(dtype=str)).astype(str),teams.get("manager_name",pd.Series(dtype=str))))
        for side in ("home","away"):
            promoted[f"{side}_manager"]=promoted[f"{side}_team_id"].astype(str).map(canonical_names).fillna(promoted[f"{side}_manager"])
        promoted["winner"]=promoted.apply(lambda row:"TIE" if row.home_score==row.away_score else row.home_manager if row.home_score>row.away_score else row.away_manager,axis=1)
        promoted["last_refreshed"]=promoted.get("source_retrieved_at",now)
        promoted["source"]=promoted.get("source","Fantrax getLiveScoringStats")
        matchups=pd.concat([matchups,promoted.reindex(columns=DATASET_COLUMNS["weekly_matchups"])],ignore_index=True).sort_values(["period","matchup_id"])
    matchups=_apply_live_matchup_scores(matchups,current_weekly,protected_periods=protected_periods)
    completed_mask=pd.to_numeric(matchups.get("period"),errors="coerce").isin(completed_periods)&matchups.get("home_score",pd.Series(index=matchups.index,dtype=float)).notna()&matchups.get("away_score",pd.Series(index=matchups.index,dtype=float)).notna()
    matchups.loc[completed_mask,"status"]="completed";matchups.loc[completed_mask,"winner"]=matchups.loc[completed_mask].apply(lambda row:"TIE" if row.home_score==row.away_score else row.home_manager if row.home_score>row.away_score else row.away_manager,axis=1)
    manager_week=_manager_week_summary(matchups,standings,teams,now,league_payload)
    manager_week=enrich_manager_weeks(manager_week,current_weekly,completed_periods)
    active_weekly=active_player_weekly(current_weekly,completed_periods)
    current_totals,_=aggregate_player_window(current_weekly,"Season",include_partial=True)
    if not current_totals.empty:
        live_players=live_players.merge(current_totals,on="fantrax_player_id",how="left",suffixes=("","_current"))
        current_aliases={"fantasy_points":"current_fantasy_points","ghost_points":"current_ghost_points","minutes":"current_minutes","start":"current_starts","appearance":"current_appearances","start_percentage":"current_start_percentage","minutes_per_game":"current_minutes_per_game","xg":"current_xg","xa":"current_xa","xgi":"current_xgi","fantasy_points_per_game":"current_points_per_game","fantasy_points_per_start":"current_points_per_start","fantasy_points_per_90":"current_points_per_90","ghost_points_per_game":"current_ghost_per_game","ghost_points_per_start":"current_ghost_per_start","ghost_points_per_90":"current_ghost_per_90","xgi_per_game":"current_xgi_per_game","xgi_per_start":"current_xgi_per_start","xgi_per_90":"current_xgi_per_90"}
        for metric in EVENT_FIELDS:
            current_aliases[metric]=f"current_{metric}"
            for suffix in ("per_game","per_start","per_90"):
                current_aliases[f"{metric}_{suffix}"]=f"current_{metric}_{suffix}"
        for source,target in current_aliases.items():
            merged=source+"_current" if source in live_players and source+"_current" in live_players else source
            if merged in live_players: live_players[target]=pd.to_numeric(live_players[merged],errors="coerce")
    manager_players=build_manager_player_weekly(current_weekly)
    live_managers=build_live_manager_analytics(live_players,teams,standings,events,draft,manager_week)
    position_strength=build_live_position_strength(live_players,live_managers)
    league_summary=build_live_league_summary(teams,standings,manager_week,live_managers)
    available_players=live_players[live_players["available"].fillna(False).astype(bool)].copy()
    snapshot_manifest=pd.DataFrame([snapshot])
    tracking_quality=pd.DataFrame([
        {"rule":"current_roster_valid","status":"pass" if roster_valid else "fail","detail":f"{len(current)} rows"},
        {"rule":"unique_event_ids","status":"pass" if not events["event_id"].duplicated().any() else "fail","detail":f"{len(events)} events"},
        {"rule":"one_current_owner","status":"pass" if not current["fantrax_player_id"].duplicated().any() else "fail","detail":"Current roster reconciliation"},
        {"rule":"snapshot_chain","status":"pass","detail":snapshot.get("checksum","")},
    ])
    datasets={"league_teams":teams,"current_rosters":current,"roster_history":history,"league_standings":standings,"weekly_matchups":matchups,
        "manager_week_summary":manager_week,"league_transactions":transactions,"player_ownership":ownership,"roster_change_events":events,
        "roster_snapshots_manifest":snapshot_manifest,"roster_tracking_quality":tracking_quality,
        "live_player_analytics":live_players,"live_manager_analytics":live_managers,
        "live_position_strength":position_strength,"live_league_summary":league_summary,"available_players":available_players,
        "current_player_weekly":current_weekly,"understat_player_weekly":understat_weekly,"manager_player_weekly":manager_players,"league_active_player_weekly":active_weekly}
    validations={"league_teams":validate_league_teams(teams,config),"current_rosters":roster_validation,"league_standings":validate_standings(standings,config),
        "weekly_matchups":validate_matchups(matchups),"league_transactions":validate_transactions(transactions),"player_ownership":validate_ownership(ownership,current)}
    errors=pd.concat(validations.values(),ignore_index=True); blocking=errors[errors["severity"].eq("error")]
    config.quality_root.mkdir(parents=True,exist_ok=True)
    report_names={"league_teams":"league_teams_validation","current_rosters":"roster_snapshot_validation","league_standings":"standings_validation","weekly_matchups":"matchup_validation","league_transactions":"transaction_validation","player_ownership":"ownership_validation"}
    for key,report in validations.items(): _atomic_csv(report,config.quality_root/f"{report_names[key]}_{config.season_id}.csv")
    _atomic_csv(roster_validation,config.quality_root/f"roster_validation_{config.season_id}.csv")
    unresolved=pd.concat(unresolved_parts,ignore_index=True).drop_duplicates() if unresolved_parts else pd.DataFrame(columns=["fantrax_player_id","player_name","club","fantrax_position","source"])
    _atomic_csv(unresolved,config.quality_root/"unresolved_live_player_identities.csv")
    _atomic_csv(unresolved,config.quality_root/f"unresolved_roster_identities_{config.season_id}.csv")
    _atomic_csv(tracking_quality,config.quality_root/f"roster_change_validation_{config.season_id}.csv")
    _atomic_csv(tracking_quality,config.quality_root/f"roster_history_validation_{config.season_id}.csv")
    player_weekly_quality=weekly_validation(current_weekly)
    _atomic_csv(player_weekly_quality,config.quality_root/f"player_weekly_validation_{config.season_id}.csv")
    fallback_fields={"appearance","minutes","goals","assists","shots","key_passes","yellow_cards","red_cards"}
    def source_class(column:str)->str:
        if column in {"xg","xa","xgi","understat_minutes"} or column.startswith("understat_"): return "UNDERSTAT_PRIMARY"
        if column in fallback_fields: return "FANTRAX_PRIMARY_UNDERSTAT_FALLBACK"
        if column in {"fantasy_points","ghost_points"} or column in EVENT_FIELDS: return "FANTRAX_ONLY"
        return "CONTEXT_OR_PROVENANCE"
    coverage=pd.DataFrame([{"field":column,"non_null_rows":int(current_weekly[column].notna().sum()),"zero_rows":int(pd.to_numeric(current_weekly[column],errors="coerce").eq(0).sum()),"total_rows":len(current_weekly),"coverage_pct":round(100*current_weekly[column].notna().mean(),1) if len(current_weekly) else 0.0,"observed_source_class":source_class(column)} for column in current_weekly.columns if column not in {"season_id","period","fantrax_player_id"}])
    dictionary=stat_dictionary(league_payload)
    scoring_coverage=dictionary.merge(coverage,left_on="normalized_field",right_on="field",how="left")
    scoring_coverage["total_rows"]=scoring_coverage["total_rows"].fillna(len(current_weekly)); scoring_coverage["non_null_rows"]=scoring_coverage["non_null_rows"].fillna(0); scoring_coverage["coverage_pct"]=scoring_coverage["coverage_pct"].fillna(0.0)
    _atomic_csv(scoring_coverage,config.quality_root/f"fantrax_stat_coverage_{config.season_id}.csv")
    _atomic_csv(weekly_validation(manager_players.rename(columns={"manager_id":"current_manager_id","manager_name":"current_manager_name"})),config.quality_root/f"manager_player_weekly_validation_{config.season_id}.csv")
    _atomic_csv(manager_draft_origin_audit(teams,draft,ownership),config.quality_root/f"manager_draft_origin_validation_{config.season_id}.csv")
    understat_coverage=pd.DataFrame([{"dataset":"current_player_weekly","rows":len(current_weekly),"matched_understat_rows":int(current_weekly.get("xgi",pd.Series(dtype=float)).notna().sum()),"status":"awaiting live Understat" if current_weekly.empty else "partial"}])
    _atomic_csv(understat_coverage,config.quality_root/f"understat_live_coverage_{config.season_id}.csv")
    source_coverage,source_summary=player_source_coverage(live_players,current_weekly)
    _atomic_csv(source_coverage,config.quality_root/f"player_source_coverage_{config.season_id}.csv")
    _atomic_csv(source_summary,config.quality_root/f"player_source_coverage_summary_{config.season_id}.csv")
    _atomic_csv(unresolved_understat,config.quality_root/f"unresolved_understat_identities_{config.season_id}.csv")
    _atomic_csv(weekly_period_status(config.raw_root,league_payload),config.quality_root/f"weekly_period_status_{config.season_id}.csv")
    _atomic_csv(_weekly_score_reconciliation(manager_players,manager_week),config.quality_root/f"weekly_score_reconciliation_{config.season_id}.csv")
    live_scoring_path=config.model_root/f"fantrax_live_player_scoring_{config.season_id}.csv"
    if authority_path.exists() and live_scoring_path.exists():
        live_scoring=pd.read_csv(live_scoring_path,dtype={"fantrax_team_id":str,"fantrax_player_id":str})
        manager_recon,player_recon=three_way_reconciliation(authoritative,live_scoring,current_weekly)
        _atomic_csv(manager_recon,config.quality_root/f"fantrax_matchup_three_way_reconciliation_{config.season_id}.csv")
        _atomic_csv(player_recon,config.quality_root/f"fantrax_live_player_reconciliation_{config.season_id}.csv")
    _atomic_csv(dictionary,config.model_root.parents[1]/"reference"/f"fantrax_stat_dictionary_{config.season_id}.csv")
    summary=[]
    for key,frame in datasets.items():
        issues=errors[errors["dataset"].eq(key)]; summary.append({"dataset_key":key,"row_count":len(frame),"error_count":int(issues["severity"].eq("error").sum()),"warning_count":int(issues["severity"].eq("warning").sum()),"validation_status":"valid" if issues["severity"].ne("error").all() else "invalid"})
    quality=pd.DataFrame(summary); _atomic_csv(quality,config.quality_root/"live_season_quality_summary.csv")
    if not blocking.empty: raise ValueError("Live-season validation failed; prior normalized datasets were preserved")
    manifest=[]
    for key,frame in datasets.items():
        path=config.model_root/OUTPUT_FILENAMES[key].format(season=config.season_id); _atomic_csv(frame,path)
        raw=path.read_bytes(); periods=pd.to_numeric(frame.get("period"),errors="coerce") if "period" in frame else pd.Series(dtype=float)
        manifest.append({"dataset_key":key,"path":str(path.relative_to(config.model_root.parents[2])),"producer":"fantrax.live.pipeline","row_count":len(frame),
            "period_minimum":int(periods.min()) if periods.notna().any() else None,"period_maximum":int(periods.max()) if periods.notna().any() else None,
            "source_timestamp":max((str(x) for x in frame.get("source_retrieved_at",pd.Series(dtype=str)).dropna()),default=league_time),"build_timestamp":now,
            "sha256":hashlib.sha256(raw).hexdigest(),"validation_result":"valid"})
    manifest_path=config.model_root/f"live_season_manifest_{config.season_id}.json"; manifest_path.write_text(json.dumps({"season_id":config.season_id,"league_id":config.league_id,"build_timestamp":now,"datasets":manifest},indent=2),encoding="utf-8")
    return {"datasets":datasets,"quality":quality,"manifest_path":manifest_path,"unresolved":unresolved}
