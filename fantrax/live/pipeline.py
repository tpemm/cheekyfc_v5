"""Cache-only live-season build, validation, quality, and manifest pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
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
}


def _latest_metadata(path: Path) -> str:
    metadata=path.with_suffix(path.suffix+".metadata.json")
    if metadata.exists(): return str(json.loads(metadata.read_text(encoding="utf-8")).get("retrieved_at") or "")
    return datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat()


def _atomic_csv(frame: pd.DataFrame,path: Path)->None:
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+".tmp"); frame.to_csv(tmp,index=False); tmp.replace(path)


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
    explicit = _explicit_period(league_payload)
    if explicit in available: return explicit
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
        if pd.isna(standing.get("period")):continue
        name=standing.get("manager") or team_names.get(str(standing.get("manager_id")))
        rank_lookup[(standing.get("period"),name)]=standing.get("rank")
    identities={str(row.manager_name):row for row in teams.itertuples()};period_dates={int(item["number"]):item.get("endDate") for item in (league_payload or {}).get("scoringPeriods",[]) if isinstance(item,dict) and pd.notna(pd.to_numeric(item.get("number"),errors="coerce"))}
    records={}
    for row in matchups.itertuples():
        if pd.isna(row.home_score) or pd.isna(row.away_score): continue
        for manager,score,opponent,opponent_score in ((row.home_manager,row.home_score,row.away_manager,row.away_score),(row.away_manager,row.away_score,row.home_manager,row.home_score)):
            result="D" if score==opponent_score else "W" if score>opponent_score else "L"
            identity=identities.get(str(manager)); opponent_identity=identities.get(str(opponent)); record=records.setdefault(str(manager),{"W":0,"D":0,"L":0,"pf":0.0,"pa":0.0}); record[result]+=1; record["pf"]+=float(score); record["pa"]+=float(opponent_score)
            rows.append({"season_id":row.season_id,"period":row.period,"manager_id":getattr(identity,"manager_id",pd.NA),"manager_name":manager,"fantasy_team_id":getattr(identity,"fantasy_team_id",pd.NA),"fantasy_team_name":getattr(identity,"fantasy_team_name",manager),"opponent_manager_id":getattr(opponent_identity,"manager_id",pd.NA),"opponent_manager_name":opponent,"fantasy_points":score,"opponent_points":opponent_score,"result":result,"cumulative_wins":record["W"],"cumulative_draws":record["D"],"cumulative_losses":record["L"],"league_points_after_week":record["W"]*3+record["D"],"rank_after_week":rank_lookup.get((row.period,manager),pd.NA),"points_for_after_week":record["pf"],"points_against_after_week":record["pa"],
                "manager":manager,"total_score":score,"opponent":opponent,"opponent_score":opponent_score,"record_after_week":f'{record["W"]}-{record["D"]}-{record["L"]}',"optimal_xi_score":pd.NA,
                "source_coverage":"matchup scores only; advanced lineup metrics pending","source":"Fantrax cached matchups","last_refreshed":refreshed_at})
    result=pd.DataFrame(rows);result["period_completed_at"]=pd.to_numeric(result.get("period"),errors="coerce").map(period_dates) if not result.empty else pd.Series(dtype=object)
    return result.reindex(columns=DATASET_COLUMNS["manager_week_summary"])


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
    ownership=_ownership(current,transactions,events,now,pool=pool,draft=draft,teams=teams); manager_week=_manager_week_summary(matchups,standings,teams,now,league_payload)
    rankings_path=config.model_root.parents[0]/f"draft_{config.season_id}"/f"draft_rankings_{config.season_id}.csv"
    rankings=pd.read_csv(rankings_path,dtype={"fantrax_player_id":str}) if rankings_path.exists() else pd.DataFrame()
    live_players=build_live_player_analytics(pool,ownership,current,rankings,draft,events,season_id=config.season_id)
    periods=scoring_periods_from_league(league_payload)
    understat_root=config.raw_root.parents[1]/"understat"/config.season_id
    understat_weekly,unresolved_understat=load_cached_understat(understat_root,periods,registry,season_id=config.season_id)
    combined_weekly=supplement_fantrax(load_cached_weekly_exports(config.raw_root),understat_weekly,weekly_columns=WEEKLY_COLUMNS)
    current_weekly=enrich_weekly(combined_weekly,registry,ownership,pd.concat(joined_parts,ignore_index=True) if joined_parts else current)
    current_totals,_=aggregate_player_window(current_weekly,"Season")
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
        "current_player_weekly":current_weekly,"understat_player_weekly":understat_weekly,"manager_player_weekly":manager_players}
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
