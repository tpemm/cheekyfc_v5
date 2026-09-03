"""Provider-supported WhoScored event derivations for semantic validation."""
from __future__ import annotations

import pandas as pd


def observed_event_counts(events: pd.DataFrame) -> pd.DataFrame:
    """One observed player-match row; absent players are not manufactured."""
    e=events.copy();q=e.qualifiers.astype("string")
    e["cross_attempt"]=e.event_type.eq("Pass")&q.str.contains('"Cross"',na=False)
    e["cross_successful"]=e.cross_attempt&e.outcome.eq("Successful")
    e["cross_unsuccessful"]=e.cross_attempt&e.outcome.eq("Unsuccessful")
    e["shot"]=e.event_type.isin(("Goal","SavedShot","MissedShots","ShotOnPost","BlockedShot"))
    e["sot_goal_saved"]=e.event_type.isin(("Goal","SavedShot"))
    e["sot_goal_saved_unblocked"]=e.event_type.eq("Goal")|(e.event_type.eq("SavedShot")&~q.str.contains('"Blocked"',na=False))
    e["sot_successful_shot"]=e.shot&e.outcome.eq("Successful")
    e["tackle_attempt"]=e.event_type.eq("Tackle")
    e["tackle_successful"]=e.tackle_attempt&e.outcome.eq("Successful")
    e["tackle_unsuccessful"]=e.tackle_attempt&e.outcome.eq("Unsuccessful")
    e["clearance"]=e.event_type.eq("Clearance")
    e["goal"]=e.event_type.eq("Goal")
    # WhoScored marks the credited provider assist on the supplying event.
    # ``IntentionalAssist`` is a broad shot-context qualifier; the narrower
    # ``IntentionalGoalAssist`` is the actual credited assist marker.
    e["official_assist"]=q.str.contains('"IntentionalGoalAssist"',na=False)
    keys=["canonical_match_id","canonical_player_id"]
    metrics=("cross_attempt","cross_successful","cross_unsuccessful","shot","sot_goal_saved","sot_goal_saved_unblocked","sot_successful_shot","tackle_attempt","tackle_successful","tackle_unsuccessful","clearance","goal","official_assist")
    result=e[e.canonical_player_id.notna()].groupby(keys,as_index=False).agg(**{f"ws_{x}s" if not x.endswith("successful") else f"ws_{x}":(x,"sum") for x in metrics})
    return result


def safe_fantasy_assist_delta(fantrax_assists: pd.Series, official_assists: pd.Series) -> pd.Series:
    delta=pd.to_numeric(fantrax_assists,errors="coerce")-pd.to_numeric(official_assists,errors="coerce")
    return delta.where(delta.ge(0))


def preceding_goal_events(events: pd.DataFrame, assist_rows: pd.DataFrame) -> pd.DataFrame:
    """Link an assist candidate to the next goal for the same team/match."""
    rows=[]
    ordered=events.sort_values(["canonical_match_id","expanded_minute","second","provider_sequence_event_id"])
    for candidate in assist_rows.itertuples():
        same=ordered[ordered.canonical_match_id.eq(candidate.canonical_match_id)&ordered.club_id.eq(candidate.club_id)]
        goals=same[same.event_type.eq("Goal")]
        goals=goals[(pd.to_numeric(goals.expanded_minute,errors="coerce")>candidate.expanded_minute)|((pd.to_numeric(goals.expanded_minute,errors="coerce")==candidate.expanded_minute)&(pd.to_numeric(goals.second,errors="coerce")>=candidate.second))]
        goal=goals.head(1)
        rows.append({"canonical_match_id":candidate.canonical_match_id,"assist_event_id":candidate.event_id,"goal_event_id":goal.event_id.iat[0] if len(goal) else pd.NA,"goal_scorer_id":goal.canonical_player_id.iat[0] if len(goal) else pd.NA})
    return pd.DataFrame(rows)
