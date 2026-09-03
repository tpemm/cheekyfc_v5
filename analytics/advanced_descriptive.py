"""Shared, transparent definitions for historical advanced descriptive analytics."""
from __future__ import annotations

import pandas as pd

SAFE_SUPPLEMENT_POLICY={
    "key_passes": {"fantrax":"mgr_kp","whoscored":"key_passes","classification":"SAFE_SUPPLEMENT","reason":"99.35% exact; 99.74% within one"},
    "aerial_wins": {"fantrax":"mgr_aer","whoscored":"aerials_won","classification":"SAFE_SUPPLEMENT","reason":"97.05% exact; 99.49% within one"},
    "interceptions": {"fantrax":"mgr_int","whoscored":"interceptions","classification":"SAFE_SUPPLEMENT","reason":"99.35% exact; 99.73% within one"},
}

SUPPLEMENT_POLICY={
    **SAFE_SUPPLEMENT_POLICY,
    "successful_dribbles":{"fantrax":"","whoscored":"dribbles_successful","classification":"SOURCE_SPECIFIC_ONLY","reason":"no season-scale overlapping Fantrax field in the exact-match dataset"},
    "clearances":{"fantrax":"mgr_clr","whoscored":"clearances","classification":"SUPPLEMENT_WITH_CAVEAT","reason":"86.38% exact; definitions differ"},
    "shots_on_target":{"fantrax":"mgr_sot","whoscored":"shots_on_target","classification":"DO_NOT_SUPPLEMENT","reason":"76.55% exact"},
    "tackles":{"fantrax":"mgr_tkw","whoscored":"tackles","classification":"SOURCE_SPECIFIC_ONLY","reason":"WhoScored tackles are not Fantrax tackles won"},
    "crosses":{"fantrax":"mgr_ac","whoscored":"crosses","classification":"SOURCE_SPECIFIC_ONLY","reason":"WhoScored raw crosses are not Fantrax accurate crosses"},
}

PITCH_LAYER_TYPES={
    "Activity Density":None,
    "Passes":{"Pass"},
    "Key Passes":{"Pass"},
    "Crosses":{"Pass"},
    "Dribbles / TakeOns":{"TakeOn"},
    "TakeOns":{"TakeOn"},  # compatibility alias for existing callers/products
    "Successful Dribbles":{"TakeOn"},
    "Shots":{"MissedShots","SavedShot","ShotOnPost","Goal"},
    "Defensive Actions":{"Tackle","Interception","Clearance","BlockedPass"},
    "Recoveries":{"BallRecovery"},
    "Aerials":{"Aerial"},
}


def reconcile_safe_metric(frame:pd.DataFrame,metric:str)->pd.DataFrame:
    """Fantrax exact non-null values—including zero—win; WhoScored fills only nulls."""
    policy=SAFE_SUPPLEMENT_POLICY[metric]; fan=pd.to_numeric(frame.get(policy["fantrax"]),errors="coerce"); ws=pd.to_numeric(frame.get(policy["whoscored"]),errors="coerce")
    exact=frame.get("fantrax_alignment",pd.Series("",index=frame.index)).eq("EXACT_SINGLE_CLUB_MATCH_IN_PERIOD")
    trusted=fan.where(exact)
    value=trusted.where(trusted.notna(),ws)
    source=pd.Series(pd.NA,index=frame.index,dtype="object"); source.loc[trusted.notna()]="FANTRAX"; source.loc[trusted.isna()&ws.notna()]="WHOSCORED_SUPPLEMENT"
    return pd.DataFrame({metric:value,f"{metric}_source":source},index=frame.index)


def filter_pitch_events(events:pd.DataFrame,layer:str)->pd.DataFrame:
    result=events.copy(); types=PITCH_LAYER_TYPES[layer]
    if types is not None: result=result[result.event_type.isin(types)]
    if layer=="Key Passes": result=result[result.is_key_pass.fillna(False).astype(bool)]
    if layer=="Crosses": result=result[result.qualifiers.str.contains('"Cross"',case=False,na=False)]
    if layer=="Successful Dribbles": result=result[result.get("outcome",pd.Series(index=result.index,dtype=object)).astype(str).eq("Successful")]
    return result


def apply_event_window(events:pd.DataFrame,matches:pd.DataFrame,window:str)->pd.DataFrame:
    ordered=matches.sort_values(["date","canonical_match_id"]).canonical_match_id.drop_duplicates()
    if window=="Last 5": ordered=ordered.tail(5)
    elif window=="Last 10": ordered=ordered.tail(10)
    elif window.startswith("Match: "): ordered=pd.Series([window.removeprefix("Match: ")])
    return events[events.canonical_match_id.isin(set(ordered))]


def dense_rank(frame:pd.DataFrame,group:list[str],value:str)->pd.Series:
    return frame.groupby(group,dropna=False)[value].rank(method="dense",ascending=False).astype("Int64")

def canonical_venue(frame: pd.DataFrame, matches: pd.DataFrame) -> pd.DataFrame:
    """Attach HOME/AWAY only when canonical match orientation proves it."""
    out = frame.copy()
    orientation = matches[["canonical_match_id", "home_club_id", "away_club_id"]].drop_duplicates("canonical_match_id")
    out = out.drop(columns=["venue"], errors="ignore").merge(orientation, on="canonical_match_id", how="left")
    out["venue"] = pd.NA
    out.loc[out["club_id"].eq(out["home_club_id"]), "venue"] = "HOME"
    out.loc[out["club_id"].eq(out["away_club_id"]), "venue"] = "AWAY"
    return out.drop(columns=["home_club_id", "away_club_id"])

def add_plot_coordinates(events: pd.DataFrame) -> pd.DataFrame:
    """Normalize WhoScored coordinates to a vertical, upward-attacking pitch.

    Provider ``x`` is attacking depth and ``y`` is lateral position.  WhoScored's
    lateral origin is the visual right after the vertical rotation, hence the
    explicit ``100-y`` correction.  Raw provider columns are never overwritten.
    """
    out = events.copy()
    out["plot_x"] = 100 - pd.to_numeric(out.get("y"), errors="coerce")
    out["plot_y"] = pd.to_numeric(out.get("x"), errors="coerce")
    out["plot_end_x"] = 100 - pd.to_numeric(out.get("end_y"), errors="coerce")
    out["plot_end_y"] = pd.to_numeric(out.get("end_x"), errors="coerce")
    return out
