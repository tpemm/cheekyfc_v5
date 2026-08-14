"""Deterministic presentation model for finalized historical player data."""
from __future__ import annotations

import numpy as np
import pandas as pd


def _text(frame: pd.DataFrame, *columns: str) -> pd.Series:
    result=pd.Series("",index=frame.index,dtype=object)
    for column in columns:
        if column in frame:
            candidate=frame[column].fillna("").astype(str).str.strip()
            result=result.mask(result.eq("") & candidate.ne(""),candidate)
    return result


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(frame[column],errors="coerce") if column in frame else pd.Series(np.nan,index=frame.index)


def _safe_rate(numerator: pd.Series, denominator: pd.Series, multiplier: float = 1.0) -> pd.Series:
    denominator=pd.to_numeric(denominator,errors="coerce")
    return pd.to_numeric(numerator,errors="coerce").mul(multiplier).div(denominator.where(denominator.gt(0)))


def build_historical_player_frame(master: pd.DataFrame, draft_snapshot: pd.DataFrame | None = None) -> pd.DataFrame:
    """Aggregate finalized facts and enrich matched rows with frozen historical fields."""
    work=master.copy()
    work["fantrax_player_id"]=_text(work,"fantrax_player_id").str.strip("*")
    work["player_name"]=_text(work,"fantrax_player_name","avail_player","mgr_player")
    work["premier_league_club"]=_text(work,"fantrax_team_name","avail_team","mgr_team")
    work["fantrax_position"]=_text(work,"mgr_eligible","avail_position")
    roster_score=_numeric(work,"mgr_fantasy_points")
    work["fantasy_points"]=roster_score.fillna(_numeric(work,"avail_fpts"))
    work["detail_minutes"]=_numeric(work,"mgr_min")
    work["understat_minutes"]=_numeric(work,"minutes")
    work["week_xg"]=_numeric(work,"xg"); work["week_xa"]=_numeric(work,"xa")
    work["week_goals"]=_numeric(work,"mgr_g"); work["week_assists"]=_numeric(work,"mgr_at")
    work["appearance"]=(work["detail_minutes"].gt(0) | work["fantasy_points"].ne(0)).astype(int)
    work["started"]=_numeric(work,"mgr_gs").fillna(0).gt(0).astype(int)
    grouped=work.groupby("fantrax_player_id",dropna=False)
    out=grouped.agg(
        player_name=("player_name",lambda s: next((x for x in reversed(s.tolist()) if x),"")),
        premier_league_club=("premier_league_club",lambda s: next((x for x in reversed(s.tolist()) if x),"")),
        fantrax_position=("fantrax_position",lambda s: next((x for x in reversed(s.tolist()) if x),"")),
        historical_fantasy_points=("fantasy_points",lambda s:s.sum(min_count=1)),
        historical_appearances=("appearance","sum"), historical_starts=("started","sum"),
        historical_minutes=("detail_minutes",lambda s:s.sum(min_count=1)),
        historical_goals=("week_goals",lambda s:s.sum(min_count=1)),
        historical_assists=("week_assists",lambda s:s.sum(min_count=1)),
        historical_xg=("week_xg",lambda s:s.sum(min_count=1)), historical_xa=("week_xa",lambda s:s.sum(min_count=1)),
        understat_minutes_2526=("understat_minutes",lambda s:s.sum(min_count=1)),
    ).reset_index()
    out["season_id"]="2526"; out["canonical_position"]=out["fantrax_position"].str.split(",").str[0]

    frozen=draft_snapshot.copy() if draft_snapshot is not None else pd.DataFrame()
    if not frozen.empty:
        frozen["fantrax_player_id"]=_text(frozen,"historical_fantrax_player_id","fantrax_player_id").str.strip("*")
        frozen=frozen.drop_duplicates("fantrax_player_id")
        fields=[c for c in ("fantrax_player_id","registry_player_id","minutes_2526","starts_2526","fantasy_points_2526","ghost_points_2526_authoritative","ghost_points_2526","ghost_appearances_2526","understat_xg_2526","understat_xa_2526","understat_minutes_2526","goals_2526","assists_2526") if c in frozen]
        out=out.merge(frozen[fields],on="fantrax_player_id",how="left",suffixes=("","_frozen"))
        replacements={"historical_minutes":"minutes_2526","historical_starts":"starts_2526","historical_fantasy_points":"fantasy_points_2526","historical_appearances":"ghost_appearances_2526","historical_xg":"understat_xg_2526","historical_xa":"understat_xa_2526","understat_minutes_2526":"understat_minutes_2526_frozen","historical_goals":"goals_2526","historical_assists":"assists_2526"}
        for target,source in replacements.items():
            if source in out: out[target]=pd.to_numeric(out[source],errors="coerce").combine_first(pd.to_numeric(out[target],errors="coerce"))
        ghost_source=next((c for c in ("ghost_points_2526_authoritative","ghost_points_2526") if c in out),None)
        out["historical_ghost_points"]=pd.to_numeric(out[ghost_source],errors="coerce") if ghost_source else np.nan
    else: out["historical_ghost_points"]=np.nan

    out["historical_xgi"]=out["historical_xg"]+out["historical_xa"]
    out["historical_points_per_appearance"]=_safe_rate(out["historical_fantasy_points"],out["historical_appearances"])
    out["historical_points_per_start"]=_safe_rate(out["historical_fantasy_points"],out["historical_starts"])
    out["historical_points_per_90"]=_safe_rate(out["historical_fantasy_points"],out["historical_minutes"],90)
    out["historical_ghost_per_appearance"]=_safe_rate(out["historical_ghost_points"],out["historical_appearances"])
    out["historical_ghost_per_start"]=_safe_rate(out["historical_ghost_points"],out["historical_starts"])
    out["historical_ghost_per_90"]=_safe_rate(out["historical_ghost_points"],out["historical_minutes"],90)
    out["historical_start_percentage"]=_safe_rate(out["historical_starts"],out["historical_appearances"],100)
    out["historical_minutes_per_game"]=_safe_rate(out["historical_minutes"],out["historical_appearances"])
    for name,numerator in (("goals","historical_goals"),("assists","historical_assists"),("xgi","historical_xgi")):
        out[f"historical_{name}_per_game"]=_safe_rate(out[numerator],out["historical_appearances"])
        out[f"historical_{name}_per_start"]=_safe_rate(out[numerator],out["historical_starts"])
        out[f"historical_{name}_per_90"]=_safe_rate(out[numerator],out["historical_minutes"],90)
    out["historical_xg_per_90"]=_safe_rate(out["historical_xg"],out["understat_minutes_2526"],90)
    out["historical_xa_per_90"]=_safe_rate(out["historical_xa"],out["understat_minutes_2526"],90)
    out["historical_xgi_per_90"]=_safe_rate(out["historical_xgi"],out["understat_minutes_2526"],90)
    out["historical_data_source"]="Finalized 2025/26 master player-week data; frozen draft snapshot enrichment where matched"
    return out.sort_values(["historical_fantasy_points","player_name"],ascending=[False,True],na_position="last",kind="stable").reset_index(drop=True)


RATE_FIELDS={
    "Total":("historical_fantasy_points","historical_ghost_points","historical_goals","historical_assists","historical_xg","historical_xa","historical_xgi"),
    "Per Game":("historical_points_per_appearance","historical_ghost_per_appearance","historical_goals_per_game","historical_assists_per_game","historical_xgi_per_game"),
    "Per Start":("historical_points_per_start","historical_ghost_per_start","historical_goals_per_start","historical_assists_per_start","historical_xgi_per_start"),
    "Per 90":("historical_points_per_90","historical_ghost_per_90","historical_goals_per_90","historical_assists_per_90","historical_xg_per_90","historical_xa_per_90","historical_xgi_per_90"),
}
