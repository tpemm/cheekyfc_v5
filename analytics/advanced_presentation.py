"""Pure presentation models for the historical advanced analytics screens.

These helpers reshape registered descriptive products for display only.  They do
not infer missing observations, change provider authority, or create predictions.
"""
from __future__ import annotations

import pandas as pd

RATE_SUFFIXES = {"Total": "", "Per Start": "_per_start", "Per 90": "_per90"}

PLAYER_GROUPS = {
    "Chance Creation": (("Key Passes", "key_passes"), ("xA", "xa"), ("Through Balls", "through_balls"), ("Crosses", "raw_crosses")),
    "Shooting": (("Goals", "goals"), ("Shots", "shots"), ("Shots on Target", "shots_on_target"), ("xG", "xg")),
    "Dribbling": (("TakeOns", "dribbles_attempted"), ("Successful TakeOns", "dribbles_successful")),
    "Passing": (("Passes Attempted", "passes_attempted"), ("Passes Completed", "passes_completed")),
    "Defense": (("Tackles", "tackles"), ("Interceptions", "interceptions"), ("Clearances", "clearances"), ("Recoveries", "recoveries"), ("Blocked Passes", "blocked_passes")),
    "Aerials": (("Attempts", "aerial_attempts"), ("Wins", "aerial_wins")),
}


def rate_field(metric: str, basis: str) -> str:
    return f"{metric}{RATE_SUFFIXES[basis]}"


def player_snapshot(profile: pd.Series, basis: str) -> pd.DataFrame:
    fields = (("Rating", "average_rating"), ("Goals", rate_field("goals", basis)),
              ("Assists", rate_field("assists", basis)), ("Key Passes", rate_field("key_passes", basis)),
              ("xG", rate_field("xg", basis)), ("xA", rate_field("xa", basis)),
              ("Successful TakeOns", rate_field("dribbles_successful", basis)),
              ("Aerial Wins", rate_field("aerial_wins", basis)))
    return pd.DataFrame({"Metric": [x[0] for x in fields], "Value": [pd.to_numeric(profile.get(x[1]), errors="coerce") for x in fields]})


def player_metric_group(profile: pd.Series, group: str, basis: str) -> pd.DataFrame:
    fields = PLAYER_GROUPS[group]
    return pd.DataFrame({"Metric": [x[0] for x in fields], "Value": [pd.to_numeric(profile.get(rate_field(x[1], basis)), errors="coerce") for x in fields]}).dropna(subset=["Value"])


def role_share_frame(roles: pd.DataFrame, manager: str = "All") -> pd.DataFrame:
    shown = roles if manager == "All" else roles[roles.manager_name.astype(str).eq(manager)]
    if shown.empty:
        return pd.DataFrame(columns=["Observed Role", "Starts", "Share"])
    return (shown.groupby("actual_tactical_role", as_index=False)
            .agg(Starts=("role_starts", "sum"), Share=("role_share", "mean"))
            .rename(columns={"actual_tactical_role": "Observed Role"})
            .sort_values(["Starts", "Share"], ascending=False))


def pitch_layer_summary(events: pd.DataFrame, matches: pd.DataFrame) -> dict[str, float]:
    outcomes = events.get("outcome", pd.Series(index=events.index, dtype=object)).astype(str)
    successful = int(outcomes.eq("Successful").sum())
    total = len(events)
    return {"actions": total, "successful": successful,
            "success_rate": (100 * successful / total) if total else float("nan"),
            "matches": int(events.get("canonical_match_id", pd.Series(index=events.index)).nunique()),
            "available_matches": int(matches.get("canonical_match_id", pd.Series(index=matches.index)).nunique())}


def formation_summary(formations: pd.DataFrame) -> dict[str, object]:
    if formations.empty:
        return {}
    grouped = formations.groupby("formation", as_index=False).agg(Matches=("matches", "sum"))
    grouped = grouped.sort_values("Matches", ascending=False)
    total = float(grouped.Matches.sum())
    top = grouped.iloc[0]
    return {"formation": str(top.formation), "matches": int(top.Matches),
            "share": (float(top.Matches) / total) if total else float("nan"),
            "formations": int(grouped.formation.nunique())}


def playstyle_league_relative(selected: pd.DataFrame, league: pd.DataFrame, metrics: tuple[tuple[str, str], ...]) -> pd.DataFrame:
    """Rank selected observed rates against club-level means; rank 1 is highest."""
    if selected.empty or league.empty:
        return pd.DataFrame(columns=["Group", "Metric", "Value", "League Average", "Rank"])
    club = league.groupby("club_id", as_index=False).agg({key: "mean" for _, key in metrics if key in league})
    rows = []
    for label, key in metrics:
        if key not in club:
            continue
        values = pd.to_numeric(club[key], errors="coerce")
        value = pd.to_numeric(selected.get(key), errors="coerce").mean()
        rows.append({"Metric": label, "Value": value, "League Average": values.mean(),
                     "Rank": int(values.rank(method="min", ascending=False).loc[(club.club_id == selected.club_id.iloc[0])].min()) if (club.club_id == selected.club_id.iloc[0]).any() else pd.NA})
    return pd.DataFrame(rows)
