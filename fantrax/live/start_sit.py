"""Explain the existing Efficiency optimum without changing lineup methodology."""
from __future__ import annotations

import json
import math
from pathlib import Path
import pandas as pd

from config.project_paths import PROJECT_ROOT
from fantrax.live.event_imports import atomic_write
from fantrax.live.league_lineups import ACTIVE_STATUSES, optimal_legal_xi, manager_performance_weeks, _eligible


class ReconciliationError(ValueError):
    """Stop: this outcome does not agree with the existing Efficiency authority."""


def points_left(optimal,actual):
    difference=float(optimal)-float(actual)
    if difference < -1e-7:raise ReconciliationError("Optimal XI scores below the canonical actual XI")
    return max(difference,0.0)


def unique_legal_pairing(roster,actual_ids,displaced,missed):
    """Accept only a unique perfect matching of individually legal substitutions."""
    by_id=roster.set_index("fantrax_player_id")
    edges={}
    for started in sorted(displaced):
        choices=[]
        for alternative in sorted(missed):
            swapped=(actual_ids-{started})|{alternative}
            candidate=roster[roster.fantrax_player_id.isin(swapped)]
            _,legal=optimal_legal_xi(candidate)
            if len(legal)==11 and set(legal)==swapped:choices.append(alternative)
        # Compatible eligibility first for stable inspection, never to hide ambiguity.
        choices.sort(key=lambda pid:(not bool(set(_eligible(by_id.loc[started,"fantrax_position"])) & set(_eligible(by_id.loc[pid,"fantrax_position"]))),pid))
        edges[started]=choices
    solutions=[];ordered=sorted(displaced)
    def visit(index,pairs,used):
        if len(solutions)>1:return
        if index==len(ordered):solutions.append(list(pairs));return
        started=ordered[index]
        for alternative in edges[started]:
            if alternative not in used:visit(index+1,pairs+[(started,alternative)],used|{alternative})
    visit(0,[],set())
    return solutions[0] if len(solutions)==1 else None


def analyze_start_sit(canonical,weekly,weeks):
    reference=manager_performance_weeks(weeks,weekly)
    from fantrax.live.league_analytics import completed_manager_weeks
    # Use the same included canonical result weeks as Efficiency. Provider-specific
    # completeness flags are not the Fantrax result-finalization authority.
    results=completed_manager_weeks(reference)
    summaries=[];decisions=[]
    for ref in results.to_dict("records"):
        mid=str(ref["manager_id"]);gw=int(ref["period"])
        roster=canonical[canonical.manager_id.astype(str).eq(mid) & pd.to_numeric(canonical.period,errors="coerce").eq(gw)].copy()
        if roster.empty:continue
        roster["fantrax_player_id"]=roster.fantrax_player_id.astype(str)
        roster["fantasy_points"]=pd.to_numeric(roster.fantasy_points,errors="coerce")
        if roster.fantrax_player_id.duplicated().any() or roster.fantasy_points.isna().any():
            raise ReconciliationError(f"{mid}/GW{gw}: duplicate player IDs or incomplete canonical scores")
        actual=roster[roster.lineup_status.astype(str).str.upper().isin(ACTIVE_STATUSES)]
        actual_ids=set(actual.fantrax_player_id);actual_points=float(actual.fantasy_points.sum())
        optimal_points,optimal_ids=optimal_legal_xi(roster);optimal_ids=set(optimal_ids)
        _,actual_legal=optimal_legal_xi(actual)
        if len(actual_ids)!=11 or len(actual_legal)!=11 or len(optimal_ids)!=11:
            raise ReconciliationError(f"{mid}/GW{gw}: unavailable legal canonical/optimal XI")
        missed_points=points_left(optimal_points,actual_points)
        efficiency=100*actual_points/optimal_points if optimal_points else float("nan")
        for label,value in (("starter_points",actual_points),("optimal_xi_points",optimal_points),("points_missed",missed_points),("lineup_efficiency_pct",efficiency)):
            expected=pd.to_numeric(ref.get(label),errors="coerce")
            if not ((pd.isna(value) and pd.isna(expected)) or (pd.notna(expected) and math.isclose(value,float(expected),abs_tol=1e-7,rel_tol=1e-9))):
                raise ReconciliationError(f"{mid}/GW{gw}: {label} differs: new={value}, existing={expected}")
        retained=actual_ids&optimal_ids;displaced=actual_ids-optimal_ids;missed=optimal_ids-actual_ids
        lookup=roster.set_index("fantrax_player_id")
        def player(pid):
            row=lookup.loc[pid]
            return dict(player_id=pid,player_name=row.get("player_name"),position=row.get("fantrax_position"),points=float(row.fantasy_points))
        context=dict(manager_id=mid,manager_display_name=ref.get("manager_name"),gameweek=gw,source="manager_player_weekly + existing optimal_legal_xi")
        def decision(started=None,alternative=None,kind="CORRECT_START",difference=0.0):
            record=dict(context,decision_type=kind,point_difference=difference,displaced_players=None,missed_players=None)
            for prefix,pid in (("started",started),("alternative",alternative)):
                item=player(pid) if pid else {}
                record.update({f"{prefix}_player_id":pid,f"{prefix}_player_name":item.get("player_name"),f"{prefix}_position":item.get("position"),f"{prefix}_points":item.get("points")})
            return record
        for pid in sorted(retained):decisions.append(decision(pid))
        pairing=unique_legal_pairing(roster,actual_ids,displaced,missed) if displaced else []
        if pairing is None:
            row=decision(kind="STRUCTURAL",difference=missed_points)
            row.update(displaced_players=json.dumps([player(pid) for pid in sorted(displaced)],ensure_ascii=False),
                       missed_players=json.dumps([player(pid) for pid in sorted(missed)],ensure_ascii=False))
            decisions.append(row)
        else:
            for started,alternative in pairing:
                diff=float(lookup.loc[alternative,"fantasy_points"]-lookup.loc[started,"fantasy_points"])
                decisions.append(decision(started,alternative,"EQUIVALENT" if abs(diff)<1e-7 else "MISSED_START",diff))
        summaries.append(dict(context,actual_xi_points=actual_points,optimal_xi_points=optimal_points,points_left_on_bench=missed_points,
            lineup_efficiency_pct=efficiency,actual_starter_count=len(actual_ids),eligible_roster_count=len(roster),
            bench_points_total=float(roster.loc[~roster.fantrax_player_id.isin(actual_ids),"fantasy_points"].sum()),
            decision_swap_count=len(displaced),retained_selection_count=len(retained),displaced_selection_count=len(displaced),missed_optimal_selection_count=len(missed),
            largest_single_miss_points=max([float(lookup.loc[b,"fantasy_points"]-lookup.loc[a,"fantasy_points"]) for a,b in pairing],default=0.0) if pairing is not None else None,
            actual_player_ids=json.dumps(sorted(actual_ids)),optimal_player_ids=json.dumps(sorted(optimal_ids)),
            derivation_status="STRUCTURAL_ATTRIBUTION" if pairing is None else "RECONCILED"))
    return pd.DataFrame(summaries),pd.DataFrame(decisions)


def build_products(root=PROJECT_ROOT,season="2627"):
    model=Path(root)/"data/models"/f"season_{season}"
    load=lambda key:pd.read_csv(model/f"{key}_{season}.csv",dtype={"fantrax_player_id":str,"manager_id":str,"current_manager_id":str},low_memory=False)
    summary,decisions=analyze_start_sit(load("manager_player_weekly"),load("current_player_weekly"),load("manager_week_summary"))
    if summary.empty:raise ReconciliationError("No finalized manager/week outcomes available")
    manager=summary.groupby(["manager_id","manager_display_name"],as_index=False).agg(
        average_points_left=("points_left_on_bench","mean"),total_points_left=("points_left_on_bench","sum"),
        average_efficiency=("lineup_efficiency_pct","mean"),gameweeks_analyzed=("gameweek","count"))
    report=dict(gameweeks=sorted(summary.gameweek.unique().tolist()),combinations=len(summary),
        actual_xi_points=float(summary.actual_xi_points.sum()),optimal_xi_points=float(summary.optimal_xi_points.sum()),
        total_points_left=float(summary.points_left_on_bench.sum()),average_points_left=float(summary.points_left_on_bench.mean()),
        median_points_left=float(summary.points_left_on_bench.median()),maximum_points_left=float(summary.points_left_on_bench.max()),
        efficiency_reconciliation="PASS",manager_totals=manager.to_dict("records"))
    for key,frame in (("manager_week_start_sit_summary",summary),("manager_week_start_sit_decisions",decisions)):
        atomic_write(model/f"{key}_{season}.csv",frame.to_csv(index=False))
    atomic_write(Path(root)/"data/quality"/f"season_{season}"/f"start_sit_quality_{season}.json",json.dumps(report,indent=2))
    return report


if __name__=="__main__":print(json.dumps(build_products(),indent=2))
