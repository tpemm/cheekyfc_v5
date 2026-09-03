"""Canonical current-season Ghost derivation from official FPts and returns."""
from __future__ import annotations
import math
import pandas as pd
from fantrax.analytics.core.fantrax_scoring import score_stat
from fantrax.analytics.core.scoring_engine import parse_eligible_positions

def _number(value):
    try:
        result=float(value);return result if math.isfinite(result) else None
    except (TypeError,ValueError):return None

def derive_return_ghost(*,fantasy_points,position,goals,assists,clean_sheets,exact_ghost=pd.NA,assist_semantics="FANTRAX_FANTASY_ASSIST",appeared=True,season="2627")->dict:
    """Component-derived Ghost wins; otherwise subtract configured G/A/CS awards."""
    exact=_number(exact_ghost)
    if exact is not None:return {"ghost_points":exact,"ghost_points_source":"FANTRAX_COMPONENT_DERIVED","ghost_return_completeness":1.0,"ghost_goal_points_removed":pd.NA,"ghost_assist_points_removed":pd.NA,"ghost_cs_points_removed":pd.NA,"ghost_scoring_position":pd.NA}
    fpts=_number(fantasy_points);g=_number(goals);a=_number(assists);cs=_number(clean_sheets);positions=parse_eligible_positions(position);pos=positions[0] if positions else ""
    known=[fpts,g,a,cs]
    if not appeared or fpts is None:return {"ghost_points":pd.NA,"ghost_points_source":"MISSING","ghost_return_completeness":0.0,"ghost_goal_points_removed":pd.NA,"ghost_assist_points_removed":pd.NA,"ghost_cs_points_removed":pd.NA,"ghost_scoring_position":pos or pd.NA}
    completeness=sum(value is not None for value in known[1:])/3
    if completeness<1 or not pos:return {"ghost_points":pd.NA,"ghost_points_source":"PARTIAL_DERIVED","ghost_return_completeness":completeness,"ghost_goal_points_removed":pd.NA,"ghost_assist_points_removed":pd.NA,"ghost_cs_points_removed":pd.NA,"ghost_scoring_position":pos or pd.NA}
    goal_points=score_stat(season,pos,"G",g);assist_points=score_stat(season,pos,"AT",a);cs_points=score_stat(season,pos,"CS",cs)
    fallback=str(assist_semantics).upper()!="FANTRAX_FANTASY_ASSIST"
    return {"ghost_points":fpts-goal_points-assist_points-cs_points,"ghost_points_source":"DERIVED_FROM_RETURNS_OFFICIAL_ASSIST_FALLBACK" if fallback else "DERIVED_FROM_RETURNS_EXACT_ASSIST","ghost_return_completeness":1.0,"ghost_goal_points_removed":goal_points,"ghost_assist_points_removed":assist_points,"ghost_cs_points_removed":cs_points,"ghost_scoring_position":pos}
