"""Season-aware Fantrax scoring-period semantics."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd


@dataclass(frozen=True, slots=True)
class ScoringPeriodState:
    current_period: int | None
    latest_completed_period: int | None
    next_period: int | None
    available_periods: tuple[int, ...]
    source: str


def live_period_phase(fixtures:pd.DataFrame,current_period:int|None,*,now:Any=None)->dict[str,Any]:
    """Describe fixture progress without treating elapsed scheduled games as results."""
    if current_period is None or fixtures.empty:return {"state":"UPCOMING","completed":0,"total":0}
    rows=fixtures[pd.to_numeric(fixtures.get("fantrax_period"),errors="coerce").eq(current_period)].drop_duplicates("match_id")
    total=len(rows);completed=int(rows.get("completed",pd.Series(False,index=rows.index)).fillna(False).astype(bool).sum())
    instant=pd.Timestamp(now or datetime.now(timezone.utc));instant=instant.tz_localize("UTC") if instant.tzinfo is None else instant.tz_convert("UTC")
    kickoff=pd.to_datetime(rows.get("kickoff_time"),errors="coerce",utc=True)
    if completed==total and total:state="COMPLETE_PENDING_CORRECTIONS"
    elif completed>0:state="ACTIVE_PARTIAL"
    elif kickoff.notna().any() and kickoff.min()<=instant:state="ACTIVE_AWAITING_RESULT_EVIDENCE"
    else:state="UPCOMING"
    return {"state":state,"completed":completed,"total":total}


def _explicit_period(payload: Any) -> int | None:
    if isinstance(payload, dict):
        for key in ("currentPeriod", "currentScoringPeriod", "scoringPeriod", "current_period"):
            value=pd.to_numeric(payload.get(key),errors="coerce")
            if pd.notna(value):return int(value)
        for value in payload.values():
            found=_explicit_period(value)
            if found is not None:return found
    elif isinstance(payload,list):
        for value in payload:
            found=_explicit_period(value)
            if found is not None:return found
    return None


def resolve_scoring_period_state(periods: pd.DataFrame, *, league_payload: Any=None, now: Any=None) -> ScoringPeriodState:
    """Resolve current/completed/next without treating the configured maximum as current."""
    frame=periods.copy()
    period_col="period" if "period" in frame else "fantrax_gw"
    start_col="period_start" if "period_start" in frame else "start_datetime"
    end_col="period_end" if "period_end" in frame else "end_datetime"
    if frame.empty or period_col not in frame:
        return ScoringPeriodState(None,None,None,(),"unavailable")
    frame[period_col]=pd.to_numeric(frame[period_col],errors="coerce")
    frame[start_col]=pd.to_datetime(frame.get(start_col),errors="coerce",utc=True)
    frame[end_col]=pd.to_datetime(frame.get(end_col),errors="coerce",utc=True)
    frame=frame.dropna(subset=[period_col]).sort_values(period_col)
    available=tuple(frame[period_col].astype(int).unique())
    explicit=_explicit_period(league_payload)
    if explicit in available:
        current=explicit;source="league_explicit_field"
    else:
        instant=pd.Timestamp(now or datetime.now(timezone.utc))
        if instant.tzinfo is None:instant=instant.tz_localize("UTC")
        active=frame[frame[start_col].le(instant)&frame[end_col].ge(instant)]
        if not active.empty:current=int(active.iloc[0][period_col]);source="league_period_window"
        elif frame[start_col].notna().any() and instant<frame[start_col].min():current=int(frame.iloc[0][period_col]);source="preseason_first_period"
        elif frame[end_col].notna().any() and instant>frame[end_col].max():current=int(frame.iloc[-1][period_col]);source="season_complete"
        else:current=None;source="unavailable"
    completed=frame[frame[end_col].lt(pd.Timestamp(now or datetime.now(timezone.utc)))] if end_col in frame else pd.DataFrame()
    latest=int(completed[period_col].max()) if not completed.empty else None
    later=[period for period in available if current is not None and period>current]
    return ScoringPeriodState(current,latest,min(later) if later else None,available,source)
