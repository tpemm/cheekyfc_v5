"""Canonical final lineups plus descriptive event context. No event replay."""
from __future__ import annotations

import json
from pathlib import Path
import pandas as pd

from config.project_paths import PROJECT_ROOT
from fantrax.live.event_imports import read_optional, atomic_write
from fantrax.live.league_lineups import ACTIVE_STATUSES

RESERVE_STATUSES=frozenset({"RESERVE","RES","BENCH"})
IR_STATUSES=frozenset({"IR","INJ_RES","INJURED_RESERVE","INJ RES"})

TIMELINE_COLUMNS = ("manager_id", "manager_display_name", "gameweek", "event_timestamp", "event_category",
    "event_type", "player_id", "player_name", "club", "position", "from_state", "to_state", "from_slot", "to_slot",
    "transaction_group_id", "raw_event_type", "source_event_id", "source", "identity_status")


def timeline(transactions, lineups):
    rows=[]
    for category,frame in (("TRANSACTION",transactions),("LINEUP",lineups)):
        for event in frame.to_dict("records"):
            rows.append(dict(manager_id=event.get("manager_id"),manager_display_name=event.get("raw_manager_name"),
                gameweek=event.get("gameweek"),event_timestamp=event.get("event_timestamp"),event_category=category,
                event_type=event.get("normalized_transaction_type") if category=="TRANSACTION" else "LINEUP_CHANGE",
                raw_event_type=event.get("raw_transaction_type") if category=="TRANSACTION" else "Lineup Change",
                player_id=event.get("player_id"),player_name=event.get("raw_player_name"),club=event.get("club"),position=event.get("position"),
                from_state=event.get("from_roster_state"),to_state=event.get("to_roster_state"),from_slot=event.get("from_slot"),to_slot=event.get("to_slot"),
                transaction_group_id=event.get("transaction_group_id"),source_event_id=event.get("transaction_event_id") if category=="TRANSACTION" else event.get("lineup_event_id"),
                source=event.get("source"),identity_status=event.get("identity_status")))
    out=pd.DataFrame(rows,columns=TIMELINE_COLUMNS)
    out["_time"]=pd.to_datetime(out.event_timestamp,utc=True,errors="coerce")
    return out.sort_values(["_time","source_event_id"],kind="stable",na_position="last").drop(columns="_time").reset_index(drop=True)


def select_window(frame, manager_id, gameweek, *, week_column="gameweek"):
    if frame.empty:return frame.copy()
    return frame[frame.manager_id.astype(str).eq(str(manager_id)) & pd.to_numeric(frame[week_column],errors="coerce").eq(int(gameweek))].copy()


def final_lineup(canonical, manager_id, gameweek):
    """Direct canonical selection. Events are deliberately not an input."""
    return select_window(canonical,manager_id,gameweek,week_column="period")


def coverage_status(events, manager_id, gameweek, kind, coverage):
    explicit=select_window(coverage,manager_id,gameweek) if not coverage.empty else coverage
    complete=not explicit.empty and explicit.get(f"{kind}_complete",pd.Series(dtype=object)).astype(str).str.lower().eq("true").any()
    return ("ACTIVITY" if len(events) else "NO_ACTIVITY") if complete else "OBSERVED_ACTIVITY_PARTIAL_COVERAGE" if len(events) else "NO_EVENT_COVERAGE"


def decision_summary(canonical, transactions, lineups, teams, *, coverage=None):
    coverage=pd.DataFrame() if coverage is None else coverage
    events=timeline(transactions,lineups)
    managers=set(teams.get("manager_id",pd.Series(dtype=str)).dropna().astype(str))
    managers.update(canonical.get("manager_id",pd.Series(dtype=str)).dropna().astype(str))
    managers.update(events.manager_id.dropna().astype(str));managers.discard("")
    weeks=set(pd.to_numeric(canonical.get("period",pd.Series(dtype=float)),errors="coerce").dropna().astype(int))
    weeks.update(pd.to_numeric(events.gameweek,errors="coerce").dropna().astype(int))
    names=dict(zip(teams.get("manager_id",[]),teams.get("manager_name",[])))
    rows=[]
    for mid in sorted(managers):
        for gw in sorted(weeks):
            final=final_lineup(canonical,mid,gw);part=select_window(events,mid,gw)
            moves=part[part.event_category.eq("LINEUP")];tx=part[part.event_category.eq("TRANSACTION")]
            counts=moves.player_id.replace("",pd.NA).dropna().value_counts()
            claims=tx[tx.event_type.eq("CLAIM")];drops=tx[tx.event_type.eq("DROP")]
            states=final.get("lineup_status",pd.Series(dtype=str)).astype(str).str.upper()
            lc=coverage_status(moves,mid,gw,"lineup",coverage);tc=coverage_status(tx,mid,gw,"transaction",coverage)
            def players(frame):return json.dumps(frame[["player_id","player_name"]].to_dict("records"),ensure_ascii=False)
            rows.append(dict(manager_id=mid,manager_display_name=names.get(mid,part.manager_display_name.iloc[-1] if len(part) else mid),gameweek=gw,
                final_active_count=int(states.isin(ACTIVE_STATUSES).sum()) if len(final) else None,
                final_reserve_count=int(states.isin(RESERVE_STATUSES).sum()) if len(final) else None,
                final_ir_count=int(states.isin(IR_STATUSES).sum()) if len(final) else None,
                lineup_event_count=len(moves),unique_players_tinkered=len(counts),repeated_tinkers=int(counts.gt(1).sum()),
                first_lineup_event_timestamp=moves.event_timestamp.iloc[0] if len(moves) else None,
                last_lineup_event_timestamp=moves.event_timestamp.iloc[-1] if len(moves) else None,
                claim_count=len(claims),drop_count=len(drops),transaction_event_count=len(tx),
                transaction_group_count=tx.transaction_group_id.replace("",pd.NA).nunique(),players_claimed=players(claims),players_dropped=players(drops),
                has_lineup_activity=bool(len(moves)),has_transaction_activity=bool(len(tx)),
                canonical_lineup_source="manager_player_weekly" if len(final) else None,
                canonical_lineup_status="AVAILABLE" if len(final) else "NO_CANONICAL_LINEUP",
                lineup_coverage_status=lc,transaction_coverage_status=tc,event_coverage_status=f"lineup:{lc};transaction:{tc}"))
    return pd.DataFrame(rows),events


def build_products(root=PROJECT_ROOT,season="2627"):
    model=Path(root)/"data/models"/f"season_{season}"
    load=lambda key:read_optional(model/f"{key}_{season}.csv")
    summary,events=decision_summary(load("manager_player_weekly"),load("transaction_events"),load("lineup_events"),load("league_teams"))
    for key,frame in (("manager_week_decision_summary",summary),("manager_event_timeline",events)):
        atomic_write(model/f"{key}_{season}.csv",frame.to_csv(index=False))
    leaders=summary.groupby(["manager_id","manager_display_name"]).lineup_event_count.sum().sort_values(ascending=False).head(5)
    report=dict(manager_gameweeks=len(summary),with_lineup_activity=int(summary.has_lineup_activity.sum()),
        without_recorded_lineup_activity=int((~summary.has_lineup_activity).sum()),lineup_events=int(summary.lineup_event_count.sum()),
        average_lineup_events=float(summary.lineup_event_count.mean()),maximum_lineup_events=int(summary.lineup_event_count.max()),
        unique_tinkered_players=int(events.loc[events.event_category.eq("LINEUP"),"player_id"].replace("",pd.NA).nunique()),
        claims=int(summary.claim_count.sum()),drops=int(summary.drop_count.sum()),
        candidate_groups=int(events.transaction_group_id.replace("",pd.NA).nunique()),timeline_events=len(events),
        top_managers=[dict(manager_id=key[0],manager_name=key[1],lineup_events=int(value)) for key,value in leaders.items()])
    atomic_write(Path(root)/"data/quality"/f"season_{season}"/f"manager_decisions_quality_{season}.json",json.dumps(report,indent=2))
    return report


if __name__=="__main__":print(json.dumps(build_products(),indent=2))
