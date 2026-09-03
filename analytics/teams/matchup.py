"""Observed and derived team/positional matchup foundations.

No function in this module produces a prediction. Missing observations remain
missing, and multi-position players are assigned to exactly one primary group.
"""
from __future__ import annotations
from typing import Any
import pandas as pd
import numpy as np

POSITION_GROUPS=("GK","DEF","MID","FWD")
EVENT_FIELDS=("goals","assists","key_passes","shots","shots_on_target","tackles_won","interceptions","clearances","aerials_won","xg","xa","xgi")

def primary_position(value: Any) -> str|None:
    if pd.isna(value): return None
    first=str(value).upper().replace("/",",").split(",")[0].strip()
    return {"G":"GK","GK":"GK","D":"DEF","DEF":"DEF","M":"MID","MID":"MID","F":"FWD","FWD":"FWD"}.get(first)

def assign_position_groups(frame: pd.DataFrame) -> pd.DataFrame:
    out=frame.copy(); canonical=out.get("canonical_position",pd.Series(index=out.index,dtype=object))
    fallback=out.get("fantrax_position",pd.Series(index=out.index,dtype=object))
    out["position_group"]=[primary_position(c) or primary_position(f) for c,f in zip(canonical,fallback)]
    out["position_assignment_source"]=np.where(canonical.map(primary_position).notna(),"canonical primary position",np.where(out.position_group.notna(),"first valid Fantrax position","unresolved"))
    return out

def completed_weekly(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty: return frame.copy()
    mask=frame.get("period_complete",pd.Series(False,index=frame.index)).fillna(False).astype(bool)
    return frame[mask].copy()

def window_periods(frame: pd.DataFrame, window: str) -> tuple[list[int],str]:
    periods=sorted(pd.to_numeric(frame.get("period"),errors="coerce").dropna().astype(int).unique())
    if window=="Season": return periods,"Season"
    requested=int(window.split()[-1]); selected=periods[-requested:]
    return selected,window if len(selected)==requested else f"{window} ({len(selected)} available)"

def _club_maps(clubs: pd.DataFrame) -> tuple[dict[str,str],dict[str,str]]:
    code=dict(zip(clubs.fantrax_code,clubs.canonical_club_id)); name=dict(zip(clubs.canonical_club_id,clubs.canonical_name)); return code,name

def build_team_match_observations(fixtures: pd.DataFrame, weekly: pd.DataFrame, clubs: pd.DataFrame) -> pd.DataFrame:
    columns=("match_id","fantrax_period","date","club_id","opponent_id","home_away","goals_for","goals_against","fantasy_points_for","fantasy_points_allowed","ghost_points_for","ghost_points_allowed","xg","xga","shots","shots_allowed","shots_on_target","shots_on_target_allowed","key_passes","key_passes_allowed","aerials_won","aerials_allowed","tackles","interceptions","clearances","source_coverage","feature_class")
    done=fixtures[fixtures.completed.fillna(False).astype(bool)].copy()
    facts=completed_weekly(assign_position_groups(weekly))
    if done.empty or facts.empty: return pd.DataFrame(columns=columns)
    codes,_=_club_maps(clubs); facts["club_id"]=facts.get("club").map(codes)
    # Player-period facts cannot be split safely across a double gameweek.
    unique=done.groupby(["club_id","fantrax_period"]).filter(lambda x:len(x)==1)
    agg_fields=["fantasy_points","ghost_points",*EVENT_FIELDS]
    for field in agg_fields: facts[field]=pd.to_numeric(facts.get(field),errors="coerce")
    agg=facts.groupby(["club_id","period"],as_index=False)[agg_fields].sum(min_count=1)
    joined=unique.merge(agg,left_on=["club_id","fantrax_period"],right_on=["club_id","period"],how="left")
    opponent=agg.rename(columns={"club_id":"opponent_id",**{c:f"{c}_allowed" for c in agg_fields}})
    joined=joined.merge(opponent,left_on=["opponent_id","fantrax_period"],right_on=["opponent_id","period"],how="left",suffixes=("","_op"))
    out=pd.DataFrame({"match_id":joined.match_id,"fantrax_period":joined.fantrax_period,"date":joined.date,"club_id":joined.club_id,"opponent_id":joined.opponent_id,"home_away":joined.home_away,"goals_for":joined.goals_for,"goals_against":joined.goals_against,
        "fantasy_points_for":joined.fantasy_points,"fantasy_points_allowed":joined.fantasy_points_allowed,"ghost_points_for":joined.ghost_points,"ghost_points_allowed":joined.ghost_points_allowed,
        "xg":joined.xg,"xga":joined.xg_allowed,"shots":joined.shots,"shots_allowed":joined.shots_allowed,"shots_on_target":joined.shots_on_target,"shots_on_target_allowed":joined.shots_on_target_allowed,
        "key_passes":joined.key_passes,"key_passes_allowed":joined.key_passes_allowed,"aerials_won":joined.aerials_won,"aerials_allowed":joined.aerials_won_allowed,
        "tackles":joined.tackles_won,"interceptions":joined.interceptions,"clearances":joined.clearances,"source_coverage":"Fantrax weekly + canonical fixtures","feature_class":"observed"})
    return out.reindex(columns=columns)

def build_position_fantasy_allowed(weekly: pd.DataFrame, fixtures: pd.DataFrame, clubs: pd.DataFrame) -> pd.DataFrame:
    columns=("club_id","club","position_group","window","window_label","venue_split","matches_observed","player_appearances","player_starts","minutes","fantrax_points_allowed","points_allowed_per_match","points_allowed_per_start","points_allowed_per_90","ghost_points_allowed","ghost_allowed_per_match","ghost_allowed_per_start","ghost_allowed_per_90",*EVENT_FIELDS,"ease_rank","feature_class","source")
    facts=completed_weekly(assign_position_groups(weekly)); codes,names=_club_maps(clubs)
    if facts.empty: return pd.DataFrame(columns=columns)
    facts["player_club_id"]=facts.get("club").map(codes)
    facts["opponent_id"]=facts.get("opponent").map(codes)
    # Fill opponent/venue only when club-period has exactly one canonical fixture.
    unique=fixtures.groupby(["club_id","fantrax_period"]).filter(lambda x:len(x)==1)[["club_id","fantrax_period","opponent_id","home_away"]]
    facts=facts.merge(unique,left_on=["player_club_id","period"],right_on=["club_id","fantrax_period"],how="left",suffixes=("_reported",""))
    facts["opponent_id"]=facts.opponent_id_reported.fillna(facts.opponent_id)
    facts=facts[facts.position_group.notna() & facts.opponent_id.notna()].copy()
    for field in ("fantasy_points","ghost_points","appearance","start","minutes",*EVENT_FIELDS): facts[field]=pd.to_numeric(facts.get(field),errors="coerce")
    rows=[]
    for window in ("Season","Last 3","Last 5","Last 10"):
        periods,label=window_periods(facts,window); selected=facts[facts.period.isin(periods)]
        for venue,part in (("All",selected),("Home",selected[selected.home_away.eq("A")]),("Away",selected[selected.home_away.eq("H")])):
            # Venue is from the defending/opponent club's perspective.
            for (opponent_id,position),group in part.groupby(["opponent_id","position_group"]):
                matches=group[["player_club_id","period"]].drop_duplicates().shape[0]; starts=group.start.sum(min_count=1); minutes=group.minutes.sum(min_count=1); points=group.fantasy_points.sum(min_count=1); ghost=group.ghost_points.sum(min_count=1)
                row={"club_id":opponent_id,"club":names.get(opponent_id),"position_group":position,"window":window,"window_label":label,"venue_split":venue,"matches_observed":matches,"player_appearances":group.appearance.sum(min_count=1),"player_starts":starts,"minutes":minutes,"fantrax_points_allowed":points,
                     "points_allowed_per_match":points/matches if matches else np.nan,"points_allowed_per_start":points/starts if pd.notna(starts) and starts else np.nan,"points_allowed_per_90":points*90/minutes if pd.notna(minutes) and minutes else np.nan,
                     "ghost_points_allowed":ghost,"ghost_allowed_per_match":ghost/matches if matches else np.nan,"ghost_allowed_per_start":ghost/starts if pd.notna(starts) and starts else np.nan,"ghost_allowed_per_90":ghost*90/minutes if pd.notna(minutes) and minutes else np.nan,
                     "feature_class":"derived","source":"Fantrax completed player-period facts"}
                for field in EVENT_FIELDS: row[field]=group[field].sum(min_count=1)
                rows.append(row)
    out=pd.DataFrame(rows).reindex(columns=columns)
    if not out.empty: out["ease_rank"]=out.groupby(["position_group","window","venue_split"])["points_allowed_per_match"].rank(method="min",ascending=False).astype("Int64")
    return out

def build_team_profiles(observations: pd.DataFrame) -> tuple[pd.DataFrame,pd.DataFrame]:
    attack_cols=("club_id","matches_observed","goals_per_match","xg_per_match","shots_per_match","shots_on_target_per_match","key_passes_per_match","fantasy_points_per_match","feature_class")
    defense_cols=("club_id","matches_observed","goals_conceded_per_match","xga_per_match","shots_allowed_per_match","shots_on_target_allowed_per_match","key_passes_allowed_per_match","fantasy_points_allowed_per_match","ghost_allowed_per_match","feature_class")
    if observations.empty: return pd.DataFrame(columns=attack_cols),pd.DataFrame(columns=defense_cols)
    g=observations.groupby("club_id"); count=g.size()
    def means(mapping):
        out=pd.DataFrame({"club_id":count.index,"matches_observed":count.values})
        for target,source in mapping.items(): out[target]=g[source].mean().values
        out["feature_class"]="derived"; return out
    return means({"goals_per_match":"goals_for","xg_per_match":"xg","shots_per_match":"shots","shots_on_target_per_match":"shots_on_target","key_passes_per_match":"key_passes","fantasy_points_per_match":"fantasy_points_for"}),means({"goals_conceded_per_match":"goals_against","xga_per_match":"xga","shots_allowed_per_match":"shots_allowed","shots_on_target_allowed_per_match":"shots_on_target_allowed","key_passes_allowed_per_match":"key_passes_allowed","fantasy_points_allowed_per_match":"fantasy_points_allowed","ghost_allowed_per_match":"ghost_points_allowed"})

def add_congestion(fixtures: pd.DataFrame) -> pd.DataFrame:
    out=fixtures.copy(); dates=pd.to_datetime(out.kickoff_time,errors="coerce",utc=True); out["_date"]=dates
    out["days_since_previous_pl_match"]=np.nan; out["days_until_next_pl_match"]=np.nan; out["pl_matches_next_7_days"]=0; out["pl_matches_next_14_days"]=0
    for club_id,index in out.groupby("club_id").groups.items():
        part=out.loc[index].sort_values("_date"); d=part._date
        out.loc[part.index,"days_since_previous_pl_match"]=d.diff().dt.total_seconds().div(86400).values
        out.loc[part.index,"days_until_next_pl_match"]=d.shift(-1).sub(d).dt.total_seconds().div(86400).values
        out.loc[part.index,"pl_matches_next_7_days"]=[int(((d>x)&(d<=x+pd.Timedelta(days=7))).sum()) for x in d]
        out.loc[part.index,"pl_matches_next_14_days"]=[int(((d>x)&(d<=x+pd.Timedelta(days=14))).sum()) for x in d]
    out["congestion_scope"]="Premier League only"; return out.drop(columns="_date")

def build_team_matchup_features(fixtures: pd.DataFrame, attack: pd.DataFrame, defense: pd.DataFrame, *, now: Any=None) -> pd.DataFrame:
    current=pd.Timestamp.now(tz="UTC") if now is None else pd.to_datetime(now,utc=True); frame=add_congestion(fixtures); dates=pd.to_datetime(frame.kickoff_time,errors="coerce",utc=True)
    frame=frame[~frame.completed.fillna(False).astype(bool)&dates.ge(current)].copy()
    if not attack.empty: frame=frame.merge(attack.add_prefix("team_attack_"),left_on="club_id",right_on="team_attack_club_id",how="left")
    if not defense.empty: frame=frame.merge(defense.add_prefix("opponent_defense_"),left_on="opponent_id",right_on="opponent_defense_club_id",how="left")
    frame["feature_class"]="derived feature frame"; frame["source_coverage"]="canonical Sofascore schedule; observations where available"
    return frame

def build_player_matchup_features(players: pd.DataFrame, fixtures: pd.DataFrame, allowed: pd.DataFrame, clubs: pd.DataFrame, weekly: pd.DataFrame, *, now: Any=None) -> pd.DataFrame:
    codes,_=_club_maps(clubs); out=assign_position_groups(players); out["club_id"]=out.get("premier_league_club").map(codes)
    next_rows=[]
    from .fixtures import next_league_fixtures
    for club_id in out.club_id.dropna().unique():
        first=next_league_fixtures(fixtures,club_id,now=now,limit=1)
        if not first.empty: next_rows.append(first.iloc[0])
    next_frame=pd.DataFrame(next_rows).add_prefix("fixture_") if next_rows else pd.DataFrame()
    if not next_frame.empty: out=out.merge(next_frame,left_on="club_id",right_on="fixture_club_id",how="left")
    current=completed_weekly(assign_position_groups(weekly)); recent=current.sort_values("period").groupby("fantrax_player_id").tail(5) if not current.empty else current
    if not recent.empty:
        playing=recent.groupby("fantrax_player_id",as_index=False).agg(recent_starts=("start","sum"),recent_appearances=("appearance","sum"),recent_minutes=("minutes","sum")); out=out.merge(playing,on="fantrax_player_id",how="left")
    season_allowed=allowed[(allowed.window.eq("Season"))&(allowed.venue_split.eq("All"))] if not allowed.empty else allowed
    if not season_allowed.empty:
        keep=season_allowed[["club_id","position_group","points_allowed_per_match","ghost_allowed_per_match","matches_observed"]].add_prefix("opponent_")
        out=out.merge(keep,left_on=["fixture_opponent_id","position_group"],right_on=["opponent_club_id","opponent_position_group"],how="left")
    out["feature_class"]="derived feature frame"; out["contains_prediction"]=False
    return out
