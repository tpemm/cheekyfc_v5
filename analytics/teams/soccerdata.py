"""Normalization and validation for cached soccerdata team context."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
import pandas as pd
from .fixtures import alias_map

SCHEDULE_COLUMNS=("game_id","date","home_team","away_team")

def normalize_soccerdata_schedule(raw: pd.DataFrame, clubs: pd.DataFrame, *, provider: str="Sofascore", retrieved_at: str|None=None) -> pd.DataFrame:
    missing=set(SCHEDULE_COLUMNS).difference(raw.columns)
    if missing: raise ValueError(f"{provider} schedule missing columns: {sorted(missing)}")
    aliases=alias_map(clubs); records=[]; stamp=retrieved_at or datetime.now(timezone.utc).isoformat()
    for row in raw.to_dict("records"):
        home_id=aliases.get(str(row["home_team"]).strip().casefold()); away_id=aliases.get(str(row["away_team"]).strip().casefold())
        kickoff=pd.to_datetime(row["date"],errors="coerce",utc=True)
        home_score=pd.to_numeric(row.get("home_score"),errors="coerce"); away_score=pd.to_numeric(row.get("away_score"),errors="coerce")
        completed=pd.notna(home_score) and pd.notna(away_score)
        records.append({"match_id":f"soccerdata:{provider.lower()}:{row['game_id']}","season":"2627","competition":"Premier League","competition_type":"league",
            "date":kickoff.date().isoformat() if pd.notna(kickoff) else pd.NA,"kickoff_time":kickoff.isoformat() if pd.notna(kickoff) else pd.NA,
            "home_club_id":home_id,"away_club_id":away_id,"home_club":row["home_team"],"away_club":row["away_team"],
            "status":"completed" if completed else "scheduled","round":row.get("round",row.get("week")),"provider_match_id":row["game_id"],
            "fantrax_period":pd.NA,"completed":completed,"home_score":home_score,"away_score":away_score,
            "source":f"soccerdata {provider}","retrieved_at":stamp})
    return pd.DataFrame(records).drop_duplicates("match_id",keep="last").sort_values(["kickoff_time","match_id"]).reset_index(drop=True)

def schedule_quality(matches: pd.DataFrame, clubs: pd.DataFrame) -> dict[str,Any]:
    ids=set(matches.home_club_id.dropna())|set(matches.away_club_id.dropna())
    counts=pd.concat([matches.home_club_id,matches.away_club_id]).value_counts()
    return {"unique_matches":int(matches.match_id.nunique()),"club_count":len(ids),"unresolved_clubs":int(matches.home_club_id.isna().sum()+matches.away_club_id.isna().sum()),
            "duplicate_matches":int(matches.match_id.duplicated().sum()),"all_dates":bool(matches.kickoff_time.notna().all()),
            "all_38":bool(len(counts)==len(clubs) and counts.eq(38).all()),"complete_380":bool(matches.match_id.nunique()==380 and len(ids)==20 and counts.eq(38).all())}

def select_primary_schedule(candidates: dict[str,pd.DataFrame], clubs: pd.DataFrame) -> tuple[str,pd.DataFrame]:
    """Deterministic precedence; incomplete providers never override complete ones."""
    for provider in ("Sofascore","ESPN","FBref","Understat","football-data.io"):
        frame=candidates.get(provider)
        if frame is not None and not frame.empty and schedule_quality(frame,clubs)["complete_380"]:
            return provider,frame
    raise ValueError("No evaluated schedule provider supplies 380 valid matches")

def normalize_clubelo_current(raw: pd.DataFrame, clubs: pd.DataFrame, provider_names: dict[str,str], *, retrieved_at: str) -> tuple[pd.DataFrame,pd.DataFrame]:
    """Map explicit ClubElo names and rank only the canonical EPL cohort."""
    source=raw.reset_index() if raw.index.name is not None else raw.copy(); rows=[]; unresolved=[]
    reverse={name:club_id for club_id,name in provider_names.items()}
    by_id=clubs.set_index("canonical_club_id")
    for row in source.to_dict("records"):
        name=str(row.get("team",row.get("club",""))); club_id=reverse.get(name)
        if club_id is None: unresolved.append({"provider_name":name,"reason":"no explicit canonical mapping"}); continue
        rows.append({"canonical_club_id":club_id,"club":by_id.loc[club_id,"canonical_name"],"clubelo_name":name,"elo":pd.to_numeric(row.get("elo"),errors="coerce"),
                     "country":row.get("country"),"date":row.get("date"),"source":"soccerdata ClubElo","retrieved_at":retrieved_at})
    current=pd.DataFrame(rows)
    if not current.empty:
        current["elo_rank_pl"]=current.elo.rank(method="min",ascending=False).astype("Int64")
        current=current.sort_values("elo_rank_pl").reset_index(drop=True)
    return current,pd.DataFrame(unresolved,columns=["provider_name","reason"])

def normalize_clubelo_history(raw: pd.DataFrame, club_id: str, *, retrieved_at: str) -> pd.DataFrame:
    frame=raw.reset_index(); date_col="from" if "from" in frame else "date"
    out=pd.DataFrame({"canonical_club_id":club_id,"date":pd.to_datetime(frame[date_col],errors="coerce"),"elo":pd.to_numeric(frame["elo"],errors="coerce")})
    out=out.dropna(subset=["date","elo"]).drop_duplicates("date",keep="last").sort_values("date")
    out["source"]="soccerdata ClubElo"; out["retrieved_at"]=retrieved_at
    return out.reset_index(drop=True)

def next_five_elo_context(fixtures: pd.DataFrame, elo: pd.DataFrame, club_id: str, *, now: Any=None) -> pd.DataFrame:
    from .fixtures import next_league_fixtures
    upcoming=next_league_fixtures(fixtures,club_id,now=now,limit=5)
    lookup=elo.set_index("canonical_club_id") if not elo.empty else pd.DataFrame()
    upcoming["opponent_elo"]=upcoming.opponent_id.map(lookup.elo if not lookup.empty else {})
    upcoming["opponent_elo_rank_pl"]=upcoming.opponent_id.map(lookup.elo_rank_pl if not lookup.empty else {})
    return upcoming[[c for c in ("date","opponent","opponent_id","home_away","fantrax_period","opponent_elo","opponent_elo_rank_pl") if c in upcoming]]
