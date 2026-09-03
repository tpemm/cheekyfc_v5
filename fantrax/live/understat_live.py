"""Cache-only Understat supplementation for the 2026/27 live season."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re

import numpy as np
import pandas as pd


UNDERSTAT_METRICS = ("minutes", "goals", "assists", "shots", "key_passes", "yellow_cards", "red_cards", "xg", "xa")
FALLBACK_METRICS = ("appearance", "minutes", "goals", "assists", "shots", "key_passes", "yellow_cards", "red_cards")
UNDERSTAT_WEEKLY_COLUMNS = (
    "season_id", "period", "registry_player_id", "fantrax_player_id", "understat_player_id",
    "player_name", "club", "appearance", "minutes", "goals", "assists", "shots",
    "key_passes", "yellow_cards", "red_cards", "xg", "xa", "xgi",
    "understat_minutes", "matches_in_period", "source", "retrieved_at",
)

UNDERSTAT_PLAYER_MATCH_COLUMNS = (
    "season_id", "period", "canonical_match_id", "understat_match_id",
    "canonical_player_id", "fantrax_player_id", "understat_player_id",
    "player_name", "canonical_club_id", "opponent_id", "date", "venue",
    "minutes", "goals", "assists", "shots", "key_passes", "xg", "xa", "xgi",
    "identity_status", "source", "retrieved_at",
)


def _team_key(value: object) -> str:
    text=re.sub(r"[^a-z0-9]+", "", str(value).lower())
    return {"bournemouth":"afcbournemouth", "brighton":"brightonhovealbion",
            "coventry":"coventrycity", "hull":"hullcity", "ipswich":"ipswichtown",
            "leeds":"leedsunited", "manchesterunited":"manchesterunited",
            "manchestercity":"manchestercity", "nottinghamforest":"nottinghamforest",
            "tottenham":"tottenhamhotspur"}.get(text,text)


def build_understat_match_products(
    schedule: pd.DataFrame, player_matches: pd.DataFrame, clubs: pd.DataFrame,
    fixture_manifest: pd.DataFrame, registry: pd.DataFrame, *, retrieved_at: str,
    season_id: str="2627",
) -> tuple[pd.DataFrame,pd.DataFrame,pd.DataFrame,pd.DataFrame]:
    """Create exact current-season match identity and player/team match products."""
    aliases={}
    for row in clubs.to_dict("records"):
        club_id=row["canonical_club_id"]
        values=[row.get(c) for c in ("canonical_name","short_name","fantrax_team_name","understat_name")]
        values += str(row.get("aliases") or "").split("|")
        for value in values:
            if pd.notna(value) and str(value).strip(): aliases[_team_key(value)]=club_id
    sched=schedule.copy()
    sched["home_club_id"]=sched["home_team"].map(lambda x: aliases.get(_team_key(x)))
    sched["away_club_id"]=sched["away_team"].map(lambda x: aliases.get(_team_key(x)))
    sched["date"]=pd.to_datetime(sched["kickoff_datetime"],errors="coerce",utc=True).dt.strftime("%Y-%m-%d")
    fixtures=fixture_manifest[["canonical_match_id","date","home_club_id","away_club_id"]].copy()
    fixtures["date"]=pd.to_datetime(fixtures["date"],errors="coerce").dt.strftime("%Y-%m-%d")
    identity=sched.merge(fixtures,on=["date","home_club_id","away_club_id"],how="left",validate="one_to_one")
    unresolved=identity["canonical_match_id"].isna()
    if unresolved.any():
        pair_map=fixtures.drop_duplicates(["home_club_id","away_club_id"],keep=False).set_index(["home_club_id","away_club_id"])["canonical_match_id"]
        identity.loc[unresolved,"canonical_match_id"]=[pair_map.get((home,away),pd.NA) for home,away in identity.loc[unresolved,["home_club_id","away_club_id"]].itertuples(index=False,name=None)]
    identity["understat_match_id"]=pd.to_numeric(identity["game_id"],errors="coerce").astype("Int64")
    identity["resolution_status"]=identity["canonical_match_id"].notna().map({True:"RESOLVED_EXACT",False:"UNRESOLVED"})
    pair_resolved=unresolved&identity["canonical_match_id"].notna();identity.loc[pair_resolved,"resolution_status"]="RESOLVED_EXACT_PAIR"
    identity["resolution_method"]="exact UTC date + canonical home/away";identity.loc[pair_resolved,"resolution_method"]="unique canonical home/away pair (provider kickoff rescheduled)"
    identity=identity[["canonical_match_id","understat_match_id","date","home_club_id","away_club_id","resolution_status","resolution_method"]]

    home=sched[["game_id","gameweek","date","home_club_id","away_club_id","home_xg","away_xg"]].rename(columns={"home_club_id":"canonical_club_id","away_club_id":"opponent_id","home_xg":"xg","away_xg":"xga"}).assign(venue="HOME")
    away=sched[["game_id","gameweek","date","home_club_id","away_club_id","home_xg","away_xg"]].rename(columns={"away_club_id":"canonical_club_id","home_club_id":"opponent_id","away_xg":"xg","home_xg":"xga"}).assign(venue="AWAY")
    team=pd.concat([home,away],ignore_index=True).merge(identity[["understat_match_id","canonical_match_id"]],left_on="game_id",right_on="understat_match_id",how="left",validate="many_to_one")
    team["season_id"]=season_id;team["period"]=pd.to_numeric(team["gameweek"],errors="coerce").astype("Int64");team["source"]="understat";team["retrieved_at"]=retrieved_at
    team=team[["season_id","period","canonical_match_id","understat_match_id","canonical_club_id","opponent_id","date","venue","xg","xga","source","retrieved_at"]]

    players=player_matches.copy()
    players["understat_match_id"]=pd.to_numeric(players["game_id"],errors="coerce").astype("Int64")
    players["understat_player_id"]=pd.to_numeric(players["player_id"],errors="coerce").astype("Int64").astype("string")
    reg=registry[["understat_player_id","registry_player_id","fantrax_player_id"]].copy()
    reg["understat_player_id"]=pd.to_numeric(reg["understat_player_id"],errors="coerce").astype("Int64").astype("string")
    reg=reg.dropna(subset=["understat_player_id"]).drop_duplicates("understat_player_id",keep=False)
    players=players.merge(reg,on="understat_player_id",how="left",validate="many_to_one")
    players=players.merge(team[["understat_match_id","canonical_match_id","canonical_club_id","opponent_id","date","venue","period"]],left_on=["understat_match_id",players["team_name"].map(lambda x: aliases.get(_team_key(x)))],right_on=["understat_match_id","canonical_club_id"],how="left",validate="many_to_one")
    players["canonical_player_id"]=players["registry_player_id"]
    players["identity_status"]=players["canonical_player_id"].notna().map({True:"RESOLVED_EXACT_ID",False:"UNRESOLVED"})
    for metric in ("minutes","goals","assists","shots","key_passes","xg","xa"): players[metric]=pd.to_numeric(players.get(metric),errors="coerce")
    players["xgi"]=players["xg"]+players["xa"];players["season_id"]=season_id;players["source"]="understat";players["retrieved_at"]=retrieved_at
    players=players.reindex(columns=UNDERSTAT_PLAYER_MATCH_COLUMNS)
    unresolved=players.loc[players.identity_status.eq("UNRESOLVED"),["understat_player_id","player_name","canonical_club_id"]].drop_duplicates()
    unresolved["reason"]="No exact Understat ID in Player Registry"
    return identity,players,team,unresolved


def empty_understat_weekly() -> pd.DataFrame:
    return pd.DataFrame(columns=UNDERSTAT_WEEKLY_COLUMNS)


def scoring_periods_from_league(payload: dict) -> pd.DataFrame:
    """Normalize authoritative Fantrax boundaries; never infer from EPL GW."""
    rows=[]
    for item in payload.get("scoringPeriods", []):
        rows.append({
            "period": pd.to_numeric(item.get("number"), errors="coerce"),
            "period_start": pd.to_datetime(item.get("startDate"), errors="coerce", utc=True),
            "period_end": pd.to_datetime(item.get("endDate"), errors="coerce", utc=True),
        })
    result=pd.DataFrame(rows, columns=("period", "period_start", "period_end")).dropna()
    if result.empty: return result
    result["period"]=result["period"].astype("Int64")
    ordered=result.sort_values("period_start")
    if ordered["period_start"].duplicated().any() or (ordered["period_start"].iloc[1:].reset_index(drop=True) <= ordered["period_end"].iloc[:-1].reset_index(drop=True)).any():
        raise ValueError("Fantrax scoring-period boundaries overlap")
    return ordered.reset_index(drop=True)


def map_matches_to_periods(matches: pd.DataFrame, periods: pd.DataFrame) -> pd.DataFrame:
    """Map each match timestamp to exactly one authoritative Fantrax period."""
    if matches.empty: return matches.assign(period=pd.Series(dtype="Int64"))
    if periods.empty: raise ValueError("Authoritative Fantrax scoring periods are required")
    out=matches.copy(); out["_kickoff"]=pd.to_datetime(out.get("kickoff_datetime"), errors="coerce", utc=True)
    candidates=out.assign(_join=1).merge(periods.assign(_join=1), on="_join", how="left").drop(columns="_join")
    candidates=candidates[candidates["_kickoff"].ge(candidates["period_start"]) & candidates["_kickoff"].le(candidates["period_end"])]
    identity=[column for column in ("game_id", "player_id") if column in candidates]
    if identity and candidates.duplicated(identity, keep=False).any(): raise ValueError("An Understat player-match mapped to multiple Fantrax periods")
    return candidates.drop(columns=["_kickoff", "period_start", "period_end"])


def normalize_understat_matches(matches: pd.DataFrame, periods: pd.DataFrame, registry: pd.DataFrame, *, retrieved_at: str, season_id: str="2627") -> tuple[pd.DataFrame,pd.DataFrame]:
    """Build player-period facts using only an exact curated Understat ID join."""
    if matches.empty: return empty_understat_weekly(), pd.DataFrame(columns=("understat_player_id", "player_name", "club", "reason"))
    frame=matches.copy()
    rename={"understat_player_id":"player_id", "team_name":"club", "team":"club"}
    for old,new in rename.items():
        if old in frame and new not in frame: frame=frame.rename(columns={old:new})
    required={"player_id", "game_id", "kickoff_datetime"}; missing=required-set(frame)
    if missing: raise ValueError(f"Understat match cache missing required columns: {sorted(missing)}")
    frame["understat_player_id"]=frame["player_id"].astype("string").str.replace(r"\.0$","",regex=True)
    frame=map_matches_to_periods(frame, periods)
    reg=registry[[c for c in ("understat_player_id","registry_player_id","fantrax_player_id","canonical_name","current_team") if c in registry]].copy()
    if "understat_player_id" not in reg: reg["understat_player_id"]=pd.Series(dtype="string")
    reg["understat_player_id"]=reg["understat_player_id"].astype("string").str.replace(r"\.0$","",regex=True)
    reg=reg.dropna(subset=["understat_player_id"]).drop_duplicates("understat_player_id",keep=False)
    frame=frame.merge(reg,on="understat_player_id",how="left",validate="many_to_one")
    unresolved=frame[frame["fantrax_player_id"].isna()][[c for c in ("understat_player_id","player_name","club") if c in frame]].drop_duplicates()
    unresolved["reason"]="No exact Understat ID in Player Registry"
    frame=frame[frame["fantrax_player_id"].notna()].copy()
    if frame.empty: return empty_understat_weekly(),unresolved
    for metric in UNDERSTAT_METRICS: frame[metric]=pd.to_numeric(frame.get(metric),errors="coerce")
    frame["appearance"]=1
    sums={metric:(metric,lambda values:pd.to_numeric(values,errors="coerce").sum(min_count=1)) for metric in ("appearance",*UNDERSTAT_METRICS)}
    grouped=frame.groupby(["period","understat_player_id","registry_player_id","fantrax_player_id"],as_index=False,dropna=False).agg(
        **sums, player_name=("player_name","last"), club=("club","last"), matches_in_period=("game_id","nunique"),
    )
    grouped["season_id"]=season_id; grouped["xgi"]=grouped["xg"]+grouped["xa"]; grouped["understat_minutes"]=grouped["minutes"]
    grouped["source"]="understat"; grouped["retrieved_at"]=retrieved_at
    return grouped.reindex(columns=UNDERSTAT_WEEKLY_COLUMNS),unresolved


def load_cached_understat(raw_root: Path, periods: pd.DataFrame, registry: pd.DataFrame, *, season_id: str="2627") -> tuple[pd.DataFrame,pd.DataFrame]:
    """Read canonical raw cache only. Empty/missing preseason caches are valid."""
    candidates=(raw_root/f"understat_player_match_stats_{season_id}_ENG-Premier_League.csv",raw_root/f"understat_player_match_stats_{season_id}.csv", raw_root/"player_match_stats.csv")
    path=next((item for item in candidates if item.exists() and item.stat().st_size>0),None)
    if path is None: return empty_understat_weekly(),pd.DataFrame(columns=("understat_player_id","player_name","club","reason"))
    try: frame=pd.read_csv(path)
    except pd.errors.EmptyDataError: return empty_understat_weekly(),pd.DataFrame(columns=("understat_player_id","player_name","club","reason"))
    retrieved=datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat()
    return normalize_understat_matches(frame,periods,registry,retrieved_at=retrieved,season_id=season_id)


def cache_understat_matches(frame: pd.DataFrame, raw_root: Path, *, season_id: str="2627") -> Path:
    """Atomically cache an acquired response under its season-scoped namespace."""
    if str(season_id)!="2627": raise ValueError("Live Understat acquisition is restricted to season 2627")
    raw_root.mkdir(parents=True,exist_ok=True); path=raw_root/f"understat_player_match_stats_{season_id}.csv"; tmp=path.with_suffix(".csv.tmp")
    frame.to_csv(tmp,index=False); tmp.replace(path); return path


def supplement_fantrax(fantrax: pd.DataFrame, understat: pd.DataFrame, *, weekly_columns: tuple[str,...]) -> pd.DataFrame:
    """Apply approved analytical fallbacks while keeping source-specific values."""
    if fantrax.empty and understat.empty: return pd.DataFrame(columns=weekly_columns)
    ft=fantrax.copy()
    for metric in FALLBACK_METRICS:
        ft[f"fantrax_{metric}"]=pd.to_numeric(ft.get(metric),errors="coerce")
    supplemental_columns=[f"understat_{metric}" for metric in FALLBACK_METRICS]+["xg","xa","xgi","xg_source","xa_source","xgi_source"]
    ft=ft.drop(columns=[column for column in supplemental_columns if column in ft],errors="ignore")
    us=understat.copy()
    keep=["fantrax_player_id","period","registry_player_id","player_name","club",*FALLBACK_METRICS,"xg","xa","xgi","retrieved_at"]
    us=us.reindex(columns=keep).rename(columns={metric:f"understat_{metric}" for metric in FALLBACK_METRICS}|{"player_name":"understat_player_name","club":"understat_club","retrieved_at":"understat_retrieved_at"})
    out=ft.merge(us,on=["fantrax_player_id","period"],how="outer",suffixes=("","_us"))
    for context,source in (("registry_player_id","registry_player_id_us"),("player_name","understat_player_name"),("club","understat_club")):
        if source in out: out[context]=out.get(context).combine_first(out[source]) if context in out else out[source]
    for metric in FALLBACK_METRICS:
        fantrax_values=pd.to_numeric(out[f"fantrax_{metric}"],errors="coerce"); understat_values=pd.to_numeric(out[f"understat_{metric}"],errors="coerce")
        out[metric]=fantrax_values.combine_first(understat_values)
        out[f"{metric}_source"]=np.select([fantrax_values.notna(),understat_values.notna()],["fantrax_weekly","understat"],default=pd.NA)
    for metric in ("xg","xa","xgi"):
        out[metric]=pd.to_numeric(out.get(metric),errors="coerce"); out[f"{metric}_source"]=out[metric].notna().map({True:"understat",False:pd.NA})
    out["understat_minutes"]=pd.to_numeric(out.get("understat_minutes"),errors="coerce")
    out["season_id"]=out.get("season_id").fillna("2627") if "season_id" in out else "2627"
    out["source"]=np.select([out.get("fantasy_points",pd.Series(index=out.index)).notna(),out["xgi"].notna()],["fantrax_weekly+understat","understat"],default="fantrax_weekly")
    out["source_retrieved_at"]=out.get("source_retrieved_at").combine_first(out.get("understat_retrieved_at")) if "source_retrieved_at" in out else out.get("understat_retrieved_at")
    out["period_complete"]=out.get("period_complete").fillna(True) if "period_complete" in out else True
    return out.reindex(columns=weekly_columns)


def player_source_coverage(players: pd.DataFrame, weekly: pd.DataFrame) -> tuple[pd.DataFrame,pd.DataFrame]:
    """Report whole-pool and evidence-based fantasy-relevant source coverage."""
    base=players.copy()
    if "fantrax_player_id" not in base: return pd.DataFrame(),pd.DataFrame()
    base["fantrax_player_id"]=base["fantrax_player_id"].astype("string")
    if weekly.empty: facts=pd.DataFrame({"fantrax_player_id":pd.Series(dtype="string")})
    else:
        work=weekly.copy(); work["fantrax_player_id"]=work["fantrax_player_id"].astype("string")
        aggregations={
            "has_fantrax_weekly":("fantasy_points",lambda s:s.notna().any()),
            "has_understat_stats":("xgi",lambda s:s.notna().any()),
            "has_fantasy_points":("fantasy_points",lambda s:s.notna().any()),
            "has_ghost_components":("ghost_points",lambda s:s.notna().any()),
            "has_defensive_events":("tackles_won",lambda s:s.notna().any()),
        }
        for metric in ("goals","assists","shots","key_passes","xg","xa","xgi"):
            aggregations[f"has_{metric}"]=(metric,lambda s:s.notna().any())
            source=f"{metric}_source"
            if source in work: aggregations[f"{metric}_source"]=(source,lambda s:next((str(x) for x in s.dropna() if str(x)),pd.NA))
        facts=work.groupby("fantrax_player_id",as_index=False).agg(**aggregations)
    out=base.merge(facts,on="fantrax_player_id",how="left")
    out["has_fantrax_identity"]=out["fantrax_player_id"].notna()
    out["has_understat_identity"]=out.get("understat_player_id",pd.Series(index=out.index,dtype=object)).notna()
    required_flags=("has_fantrax_weekly","has_understat_stats","has_fantasy_points","has_ghost_components","has_goals","has_assists","has_shots","has_key_passes","has_xg","has_xa","has_xgi","has_defensive_events")
    for flag in required_flags:
        if flag not in out: out[flag]=False
    flag_columns=["has_fantrax_identity","has_understat_identity",*required_flags]
    out[flag_columns]=out[flag_columns].fillna(False).astype(bool)
    rostered=out.get("available",pd.Series(True,index=out.index)).fillna(True).eq(False)
    drafted=out.get("drafted",pd.Series(False,index=out.index)).fillna(False).astype(bool)
    projected=pd.to_numeric(out.get("projected_minutes_percentage"),errors="coerce").fillna(0).gt(0)
    historical=pd.to_numeric(out.get("historical_minutes"),errors="coerce").fillna(0).gt(0)
    out["fantasy_relevant"]=rostered|drafted|projected|historical
    out["coverage_status"]=np.select(
        [~out["has_fantrax_identity"],out["has_fantasy_points"]&out["has_understat_stats"],out["has_fantasy_points"],out["has_understat_stats"]],
        ["IDENTITY_UNRESOLVED","FANTRAX_PLUS_UNDERSTAT","FULL_FANTRAX","UNDERSTAT_SUPPLEMENTED"],default="LIMITED",
    )
    detail_columns=[c for c in ("fantrax_player_id","registry_player_id","player_name","premier_league_club","fantasy_relevant",*flag_columns,"goals_source","assists_source","shots_source","key_passes_source","coverage_status") if c in out]
    detail=out[detail_columns].copy()
    summaries=[]
    for population,frame in (("ENTIRE_POOL",detail),("FANTASY_RELEVANT",detail[detail["fantasy_relevant"]])):
        row={"population":population,"player_count":len(frame)}
        for flag in flag_columns: row[f"{flag}_count"]=int(frame[flag].sum()); row[f"{flag}_pct"]=round(100*frame[flag].mean(),1) if len(frame) else 0.0
        summaries.append(row)
    return detail,pd.DataFrame(summaries)
