"""Validation rules for normalized live-season datasets."""

from __future__ import annotations

from typing import Any

import pandas as pd

from fantrax.live.config import LiveSeasonConfig


VALID_LINEUP_STATUSES = {"active", "starter", "starting", "bench", "reserve", "ir", "injured reserve", "injured_reserve", "rostered", "locked", "out"}
VALID_TRANSACTION_TYPES = {"draft", "add", "drop", "waiver", "trade", "commissioner action", "unknown"}


def _issue(dataset: str, rule: str, message: str, *, severity: str = "error", row_reference: Any = "") -> dict[str, Any]:
    return {"dataset": dataset, "rule": rule, "severity": severity, "message": message, "row_reference": row_reference}


def validate_league_teams(frame: pd.DataFrame, config: LiveSeasonConfig) -> pd.DataFrame:
    issues=[]; active=frame[frame.get("active", pd.Series(False,index=frame.index)).fillna(False).astype(bool)]
    if len(active)!=config.manager_count: issues.append(_issue("league_teams","active_manager_count",f"Expected {config.manager_count} active managers; found {len(active)}"))
    for column,rule in (("manager_id","unique_manager_id"),("fantasy_team_id","unique_fantasy_team_id")):
        if column not in active or active[column].isna().any() or active[column].astype(str).str.strip().eq("").any(): issues.append(_issue("league_teams",rule,f"{column} must be nonblank"))
        elif active[column].duplicated().any(): issues.append(_issue("league_teams",rule,f"Duplicate {column} values found"))
    for column in ("manager_name","fantasy_team_name"):
        if column not in active or active[column].isna().any() or active[column].astype(str).str.strip().eq("").any(): issues.append(_issue("league_teams","nonblank_names",f"{column} must be nonblank"))
    return pd.DataFrame(issues,columns=("dataset","rule","severity","message","row_reference"))


def validate_rosters(frame: pd.DataFrame, config: LiveSeasonConfig) -> pd.DataFrame:
    issues=[]
    if frame.empty: return pd.DataFrame([_issue("current_rosters","source_available","No roster data available",severity="warning")])
    ids=frame["fantrax_player_id"].astype(str).str.strip()
    if ids.eq("").any() or frame["fantrax_player_id"].isna().any(): issues.append(_issue("current_rosters","valid_player_ids","Blank Fantrax player IDs found"))
    duplicates=frame.duplicated(["period","fantrax_player_id"],keep=False)
    if duplicates.any(): issues.append(_issue("current_rosters","one_owner_per_period",f"{int(duplicates.sum())} duplicate player-period ownership rows"))
    counts=frame.groupby(["period","fantasy_team_id"],dropna=False).size()
    manager_count=frame["manager_id"].nunique(dropna=True) if "manager_id" in frame else frame["fantasy_team_id"].nunique(dropna=True)
    if manager_count!=config.manager_count: issues.append(_issue("current_rosters","manager_count",f"Expected {config.manager_count} managers; found {manager_count}",severity="warning"))
    if counts.lt(config.roster_limits["drafted"]).any(): issues.append(_issue("current_rosters","expected_roster_size","One or more rosters are below the drafted roster size",severity="warning"))
    if counts.gt(config.roster_limits["maximum"]).any(): issues.append(_issue("current_rosters","roster_limit","One or more rosters exceed the configured maximum"))
    statuses=frame["lineup_status"].fillna("").astype(str).str.lower()
    invalid=statuses[~statuses.isin(VALID_LINEUP_STATUSES)]
    if not invalid.empty: issues.append(_issue("current_rosters","lineup_status",f"Unknown lineup statuses: {', '.join(sorted(invalid.unique()))}"))
    positions=frame["fantrax_position"].dropna().astype(str)
    if positions.str.contains(r"[^A-Za-z/, ]",regex=True).any(): issues.append(_issue("current_rosters","position_eligibility","Invalid multi-position eligibility text"))
    return pd.DataFrame(issues,columns=("dataset","rule","severity","message","row_reference"))


def validate_standings(frame: pd.DataFrame, config: LiveSeasonConfig) -> pd.DataFrame:
    issues=[]
    if frame.empty: return pd.DataFrame([_issue("league_standings","source_available","No standings data available",severity="warning")])
    latest=frame[frame["period"].eq(frame["period"].max())] if frame["period"].notna().any() else frame
    if len(latest)!=config.manager_count: issues.append(_issue("league_standings","team_count",f"Expected {config.manager_count} standings rows; found {len(latest)}"))
    if latest["rank"].duplicated().any() or pd.to_numeric(latest["rank"],errors="coerce").isna().any(): issues.append(_issue("league_standings","unique_rank","Standings ranks must be unique numeric values"))
    for column in ("wins","draws","losses","fantasy_points_for"):
        values=pd.to_numeric(latest[column],errors="coerce")
        if values.isna().any() or values.lt(0).any(): issues.append(_issue("league_standings","valid_numeric",f"{column} must be nonnegative numeric data"))
    return pd.DataFrame(issues,columns=("dataset","rule","severity","message","row_reference"))


def validate_matchups(frame: pd.DataFrame) -> pd.DataFrame:
    issues=[]
    if frame.empty: return pd.DataFrame([_issue("weekly_matchups","source_available","No matchup data available",severity="warning")])
    if frame["matchup_id"].duplicated().any(): issues.append(_issue("weekly_matchups","unique_matchup_id","Duplicate matchup IDs found"))
    appearances=pd.concat([frame[["period","home_team_id"]].rename(columns={"home_team_id":"team"}),frame[["period","away_team_id"]].rename(columns={"away_team_id":"team"})])
    if appearances.duplicated(["period","team"]).any(): issues.append(_issue("weekly_matchups","one_matchup_per_period","A team appears more than once in a period"))
    completed=frame[frame["status"].astype(str).str.lower().eq("completed")]
    for row in completed.itertuples():
        expected="Draw" if row.home_score==row.away_score else row.home_manager if row.home_score>row.away_score else row.away_manager
        if str(row.winner)!=str(expected): issues.append(_issue("weekly_matchups","winner_consistency",f"Winner disagrees with score for {row.matchup_id}",row_reference=row.matchup_id))
    return pd.DataFrame(issues,columns=("dataset","rule","severity","message","row_reference"))


def validate_transactions(frame: pd.DataFrame) -> pd.DataFrame:
    issues=[]
    if frame.empty: return pd.DataFrame([_issue("league_transactions","source_available","No proven transaction source is configured",severity="warning")])
    if frame["transaction_id"].duplicated().any(): issues.append(_issue("league_transactions","unique_transaction_id","Duplicate transaction IDs found"))
    invalid=set(frame["transaction_type"].dropna())-VALID_TRANSACTION_TYPES
    if invalid: issues.append(_issue("league_transactions","transaction_type",f"Invalid transaction types: {sorted(invalid)}"))
    if pd.to_datetime(frame["timestamp"],errors="coerce",utc=True).isna().any(): issues.append(_issue("league_transactions","timestamp","One or more transaction timestamps are invalid"))
    return pd.DataFrame(issues,columns=("dataset","rule","severity","message","row_reference"))


def validate_ownership(ownership: pd.DataFrame, rosters: pd.DataFrame) -> pd.DataFrame:
    issues=[]
    if ownership.empty: return pd.DataFrame([_issue("player_ownership","source_available","No ownership data available",severity="warning")])
    if ownership["fantrax_player_id"].duplicated().any(): issues.append(_issue("player_ownership","one_current_status","Duplicate current player ownership rows"))
    conflict=ownership["available"].fillna(False).astype(bool)&ownership["current_manager"].notna()
    if conflict.any(): issues.append(_issue("player_ownership","availability_exclusive","Rostered players cannot also be available"))
    roster_ids=set(rosters["fantrax_player_id"].dropna().astype(str)); owned_ids=set(ownership.loc[ownership["current_manager"].notna(),"fantrax_player_id"].astype(str))
    if roster_ids!=owned_ids: issues.append(_issue("player_ownership","owner_matches_roster","Ownership does not match the current roster dataset"))
    return pd.DataFrame(issues,columns=("dataset","rule","severity","message","row_reference"))
