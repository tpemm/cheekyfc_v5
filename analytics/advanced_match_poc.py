"""Cache-first WhoScored historical proof-of-concept helpers.

The module is deliberately independent of Streamlit and never performs network
I/O. Acquisition belongs to the explicit refresh script.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

ROLE_MAP = {x: x for x in (
    "GK", "LB", "LCB", "CB", "RCB", "RB", "LWB", "RWB", "DM", "LDM",
    "RDM", "LCM", "CM", "RCM", "LM", "RM", "CAM", "LAM", "RAM", "LW",
    "RW", "SS", "CF", "ST",
)}
ROLE_MAP.update({"DR":"RB","DC":"CB","DL":"LB","DMC":"DM","MC":"CM",
                 "DMR":"RWB","DML":"LWB","MR":"RM","ML":"LM","AMC":"CAM","AML":"LW","AMR":"RW","FW":"ST"})

def _display(value: Any) -> Any:
    return value.get("displayName") if isinstance(value, dict) else value

def safe_write_raw(payload: dict[str, Any], target: str | Path, *, force: bool = False) -> str:
    """Atomically preserve a non-empty payload; an empty response never wins."""
    if not isinstance(payload, dict) or not payload or not payload.get("events"):
        raise ValueError("WhoScored payload is empty or has no events")
    path = Path(target)
    if path.exists() and not force:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(encoded)
    temporary.replace(path)
    return hashlib.sha256(encoded).hexdigest()

def standardize_role(raw: Any) -> Any:
    if pd.isna(raw): return pd.NA
    value = str(raw).strip().upper().replace(" ", "")
    return ROLE_MAP.get(value, pd.NA)

def normalize_match(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    home, away = payload.get("home", {}), payload.get("away", {})
    score = str(payload.get("score") or context.get("result") or "-").replace(":", "-").split("-")
    initial = lambda side: (side.get("formations") or [{}])[0].get("formationName")
    return {
        "canonical_match_id": context.get("canonical_match_id"),
        "whoscored_match_id": context.get("whoscored_match_id"), "date": context.get("date"),
        "home_club_id": context.get("home_club_id"), "away_club_id": context.get("away_club_id"),
        "whoscored_home_team_id":home.get("teamId"), "whoscored_away_team_id":away.get("teamId"),
        "home_score": pd.to_numeric(score[0], errors="coerce") if len(score)==2 else pd.NA,
        "away_score": pd.to_numeric(score[1], errors="coerce") if len(score)==2 else pd.NA,
        "home_formation": initial(home), "away_formation": initial(away),
        "home_manager_name":home.get("managerName"), "away_manager_name":away.get("managerName"),
        "competition": context.get("competition", "Premier League"), "source": "WhoScored/Opta",
        "retrieved_at": context.get("retrieved_at"),
    }

def _players(side: dict[str, Any]) -> list[dict[str, Any]]:
    return list(side.get("players") or side.get("lineup") or [])

def normalize_lineups(payload: dict[str, Any], context: dict[str, Any]) -> pd.DataFrame:
    rows=[]
    for side_name, opp_name in (("home", "away"), ("away", "home")):
        side, opp = payload.get(side_name, {}), payload.get(opp_name, {})
        history=side.get("formations") or [{}]; initial=history[0]
        formation=initial.get("formationName"); player_ids=initial.get("playerIds") or []; slots=initial.get("formationSlots") or []
        slot_by_player=dict(zip(player_ids,slots)); captain=initial.get("captainPlayerId")
        sub_on={e.get("playerId"):e.get("expandedMinute") for e in payload.get("events",[]) if _display(e.get("type"))=="SubstitutionOn"}
        sub_off={e.get("playerId"):e.get("expandedMinute") for e in payload.get("events",[]) if _display(e.get("type"))=="SubstitutionOff"}
        for player in _players(side):
            raw_role = player.get("position") or player.get("positionText")
            ratings=player.get("stats", {}).get("ratings", {})
            rating=ratings[max(ratings,key=lambda x:int(x))] if ratings else player.get("rating")
            pid=player.get("playerId") or player.get("id")
            rows.append({
                "canonical_match_id": context.get("canonical_match_id"),
                "whoscored_player_id": pid, "whoscored_player_name":player.get("name"),
                "canonical_player_id": player.get("canonical_player_id", pd.NA),
                "club_id": context.get(f"{side_name}_club_id"), "opponent_id": context.get(f"{opp_name}_club_id"),
                "whoscored_team_id":side.get("teamId"),
                "started": bool(player.get("isFirstEleven", player.get("started", False))),
                "bench": not bool(player.get("isFirstEleven", player.get("started", False))),
                "formation": formation, "lineup_slot": slot_by_player.get(pid),
                "actual_position_raw": raw_role, "actual_position_standardized": standardize_role(raw_role),
                "shirt_number": player.get("shirtNo"), "rating": rating,
                "minutes": player.get("stats", {}).get("minutesPlayed", player.get("minutes")),
                "sub_on_minute": sub_on.get(pid), "sub_off_minute": sub_off.get(pid),
                "captain": pid==captain, "source": "WhoScored/Opta",
            })
    return pd.DataFrame(rows)

def normalize_events(payload: dict[str, Any], context: dict[str, Any], player_map: dict[int,str]|None=None) -> pd.DataFrame:
    mapped = player_map or {}; rows=[]
    home_id = payload.get("home", {}).get("teamId"); home_club=context.get("home_club_id"); away_club=context.get("away_club_id")
    seen_event_ids: dict[str, int] = {}
    for event in payload.get("events", []):
        event_type=str(_display(event.get("type")) or ""); outcome=_display(event.get("outcomeType"))
        qualifiers=event.get("qualifiers") or []
        qnames={str(_display(q.get("type")) or "") for q in qualifiers if isinstance(q,dict)}
        team_id=event.get("teamId"); club=home_club if team_id==home_id else away_club
        opponent=away_club if club==home_club else home_club
        pid=event.get("playerId")
        is_pass=event_type.casefold()=="pass"; successful=str(outcome).casefold()=="successful"
        raw_event_id=str(event.get("id")); occurrence=seen_event_ids.get(raw_event_id,0)+1;seen_event_ids[raw_event_id]=occurrence
        canonical_event_id=f"ws:{raw_event_id}:{occurrence}"
        rows.append({
            "canonical_match_id":context.get("canonical_match_id"), "whoscored_match_id":context.get("whoscored_match_id"),
            "event_id":canonical_event_id, "provider_event_id":event.get("id"), "provider_sequence_event_id":event.get("eventId"), "canonical_player_id":mapped.get(pid,pd.NA),
            "whoscored_player_id":pid, "whoscored_team_id":team_id, "club_id":club, "opponent_id":opponent,
            "minute":event.get("minute"), "second":event.get("second"), "expanded_minute":event.get("expandedMinute"),
            "period":_display(event.get("period")), "event_type":event_type, "event_subtype":event.get("event_subtype"),
            "outcome":outcome, "x":event.get("x"), "y":event.get("y"), "end_x":event.get("endX"), "end_y":event.get("endY"),
            "qualifiers":json.dumps(qualifiers,ensure_ascii=False,sort_keys=True),
            "is_key_pass": bool(event.get("isKeyPass",False) or "KeyPass" in qnames),
            "is_assist":bool(event.get("isAssist",False)), "is_shot":event_type.casefold() in {"missedshots","savedshot","shotonpost","goal"},
            "is_goal":event_type.casefold()=="goal", "pass_attempted":is_pass, "pass_completed":is_pass and successful,
            "source":"WhoScored/Opta",
        })
    return pd.DataFrame(rows)

def map_provider_players(lineups: pd.DataFrame, registry: pd.DataFrame) -> pd.DataFrame:
    """Map only explicit WhoScored IDs; never perform name/fuzzy matching."""
    out=lineups.copy()
    explicit=registry.dropna(subset=["whoscored_player_id"]).copy()
    explicit["whoscored_player_id"]=explicit["whoscored_player_id"].astype(str)
    lookup=dict(zip(explicit.whoscored_player_id,explicit.registry_player_id))
    out["canonical_player_id"]=out["whoscored_player_id"].astype("string").map(lookup)
    out["player_mapping_method"]=out["canonical_player_id"].notna().map({True:"explicit_crosswalk",False:"unresolved"})
    return out

def attach_manager(matches: pd.DataFrame, tenures: pd.DataFrame) -> pd.DataFrame:
    rows=[]
    for row in matches.to_dict("records"):
        when=pd.to_datetime(row.get("date"),errors="coerce")
        for side in ("home","away"):
            club=row.get(f"{side}_club_id")
            eligible=tenures[tenures.canonical_club_id.eq(club)].copy()
            start=pd.to_datetime(eligible.tenure_start,errors="coerce"); end=pd.to_datetime(eligible.tenure_end,errors="coerce")
            hit=eligible[start.le(when)&(end.isna()|end.ge(when))]
            row[f"{side}_manager_id"]=hit.iloc[0].manager_id if len(hit)==1 else pd.NA
        rows.append(row)
    return pd.DataFrame(rows)

def aggregate_event_metrics(events: pd.DataFrame) -> pd.DataFrame:
    if events.empty: return pd.DataFrame()
    t=events.event_type.astype(str).str.casefold(); success=events.outcome.astype(str).str.casefold().eq("successful")
    flags={"key_passes":events.is_key_pass.astype(bool),"dribbles_attempted":t.eq("takeon"),"dribbles_successful":t.eq("takeon")&success,
      "aerials_attempted":t.eq("aerial"),"aerials_won":t.eq("aerial")&success,"tackles":t.eq("tackle"),"interceptions":t.eq("interception"),
      "clearances":t.eq("clearance"),"recoveries":t.eq("ballrecovery"),"blocked_passes":t.eq("blockedpass"),
      "crosses":events.qualifiers.astype(str).str.contains('Cross',case=False,na=False),
      "through_balls":events.qualifiers.astype(str).str.contains('Throughball',case=False,na=False),
      "shots":events.is_shot.astype(bool),"shots_on_target":t.isin(["savedshot","goal"]),
      "goals":events.is_goal.astype(bool),
      "fouls":t.eq("foul"),
      "passes_attempted":events.pass_attempted.astype(bool),"passes_completed":events.pass_completed.astype(bool)}
    base=events[["canonical_match_id","canonical_player_id","club_id","opponent_id"]].copy()
    for k,v in flags.items(): base[k]=v.astype(int)
    return base.groupby(["canonical_match_id","canonical_player_id","club_id","opponent_id"],dropna=False,as_index=False)[list(flags)].sum()

def build_advanced_player_match(lineups: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    keys=["canonical_match_id","canonical_player_id","club_id","opponent_id"]
    if lineups.empty: return pd.DataFrame(columns=keys)
    metric=aggregate_event_metrics(events)
    keep=keys+[x for x in ["whoscored_player_id","rating","formation","actual_position_standardized","minutes","started"] if x in lineups]
    out=lineups[keep].drop_duplicates(keys).merge(metric,on=keys,how="left",validate="one_to_one")
    metric_columns=[c for c in metric.columns if c not in keys]
    out[metric_columns]=out[metric_columns].fillna(0).astype("Int64")
    out["feature_class"]="observed_or_derived"; out["contains_prediction"]=False
    return out
