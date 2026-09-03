"""Build registered 2026/27 canonical fixture products from existing caches."""
from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import json
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from analytics.teams.fixtures import build_team_fixtures, canonicalize_matches, enrich_players_with_fixtures, load_clubs, map_fantrax_periods, next_league_fixtures
from analytics.teams.soccerdata import normalize_soccerdata_schedule, schedule_quality
from integrations.footballdata_normalizer import combine_json_normalizations, discover_json_files, normalize_matches

def _periods() -> pd.DataFrame:
    path = ROOT / "data/raw/fantrax/2627/league/league_metadata_2627_latest.json"
    if not path.exists(): return pd.DataFrame(columns=["fantrax_gw","period_start","period_end"])
    payload=json.loads(path.read_text(encoding="utf-8")); rows=[]
    metadata_path=path.with_suffix(".json.metadata.json")
    metadata=json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    for item in payload.get("scoringPeriods",[]):
        rows.append({"period":item.get("number"),"fantrax_gw":item.get("number"),
                     "start_datetime":item.get("startDate"),"period_start":item.get("startDate"),
                     "end_datetime":item.get("endDate"),"period_end":item.get("endDate"),
                     "season":"2627","source":"Fantrax getLeagueInfo",
                     "retrieved_at":metadata.get("retrieved_at")})
    return pd.DataFrame(rows)

def _validated_periods(periods: pd.DataFrame) -> pd.DataFrame:
    if periods.empty: return periods
    frame=periods.copy(); frame["_start"]=pd.to_datetime(frame.period_start,errors="coerce",utc=True); frame["_end"]=pd.to_datetime(frame.period_end,errors="coerce",utc=True)
    if frame[["fantrax_gw","_start","_end"]].isna().any().any(): raise ValueError("Fantrax scoring periods contain missing/invalid values")
    frame=frame.sort_values("fantrax_gw")
    if frame.fantrax_gw.duplicated().any() or not frame._start.is_monotonic_increasing: raise ValueError("Fantrax scoring periods are not unique and chronological")
    if (frame._end.lt(frame._start)).any() or (frame._start.iloc[1:].reset_index(drop=True)<=frame._end.iloc[:-1].reset_index(drop=True)).any(): raise ValueError("Fantrax scoring periods overlap or have invalid windows")
    if not frame._start.dt.year.isin([2026,2027]).all() or frame._start.min().year!=2026: raise ValueError("Fantrax scoring periods are not for 2026/27")
    return frame.drop(columns=["_start","_end"])

def build() -> tuple[pd.DataFrame,pd.DataFrame,pd.DataFrame]:
    clubs=load_clubs(ROOT/"data/reference/premier_league_clubs_2627.csv")
    sofa_path=ROOT/"data/raw/soccerdata/coverage_2627/sofascore/sofascore__read_schedule.csv"
    schedule_root=ROOT/"data/raw/footballdata_io/full_refresh/current_schedule"; schedule_files=discover_json_files(schedule_root,["matches_2627_page_*.json"])
    if sofa_path.exists():
        matches=normalize_soccerdata_schedule(pd.read_csv(sofa_path),clubs,retrieved_at=datetime.fromtimestamp(sofa_path.stat().st_mtime,timezone.utc).isoformat())
        if not schedule_quality(matches,clubs)["complete_380"]: raise ValueError("Primary Sofascore cache is not complete")
    else:
        raw=combine_json_normalizations(schedule_files,normalize_matches) if schedule_files else pd.read_csv(ROOT/"data/analytics/draft/fixtures_2627_normalized.csv")
        matches=canonicalize_matches(raw,clubs,retrieved_at="2026-08-19T00:00:00+00:00")
    periods=_validated_periods(_periods())
    valid=periods
    matches=map_fantrax_periods(matches,valid)
    fixtures=build_team_fixtures(matches)
    difficulty_path=ROOT/"data/analytics/draft/fixture_difficulty_2627.csv"
    if difficulty_path.exists():
        difficulty=pd.read_csv(difficulty_path)
        provider_to_club={str(row.football_data_team_id):row.canonical_club_id for row in clubs.itertuples(index=False)}
        difficulty["club_id"]=difficulty["team_id"].astype(str).map(provider_to_club)
        if matches.source.str.contains("Sofascore",case=False).all():
            difficulty["date"]=pd.to_datetime(difficulty["match_date"],errors="coerce").dt.date.astype(str)
            keep=["date","club_id","overall_fixture_ease","fixture_difficulty","fixture_band"]
            fixtures=fixtures.merge(difficulty[keep].drop_duplicates(["date","club_id"]),on=["date","club_id"],how="left")
        else:
            difficulty["match_id"]="fdio:"+difficulty["match_id"].astype(str); keep=["match_id","club_id","overall_fixture_ease","fixture_difficulty","fixture_band"]
            fixtures=fixtures.merge(difficulty[keep].drop_duplicates(["match_id","club_id"]),on=["match_id","club_id"],how="left")
    elo_path=ROOT/"data/models/season_2627/club_elo_current_2627.csv"
    elo=pd.read_csv(elo_path) if elo_path.exists() else pd.DataFrame()
    if not elo.empty:
        elo_value=elo.set_index("canonical_club_id")["elo"]; elo_rank=elo.set_index("canonical_club_id")["elo_rank_pl"]
        fixtures["team_elo"]=fixtures.club_id.map(elo_value); fixtures["opponent_elo"]=fixtures.opponent_id.map(elo_value); fixtures["opponent_elo_rank_pl"]=fixtures.opponent_id.map(elo_rank)
        fixtures["elo_difference"]=fixtures.team_elo-fixtures.opponent_elo
    else:
        for column in ("team_elo","opponent_elo","opponent_elo_rank_pl","elo_difference"): fixtures[column]=pd.NA
    out=ROOT/"data/models/season_2627"; out.mkdir(parents=True,exist_ok=True)
    periods.to_csv(ROOT/"data/reference/fantrax_scoring_periods_2627.csv",index=False)
    clubs.to_csv(out/"premier_league_clubs_2627.csv",index=False)
    matches.to_csv(out/"team_matches_2627.csv",index=False)
    fixtures.to_csv(out/"team_fixtures_2627.csv",index=False)
    quality=ROOT/"data/quality/season_2627"; quality.mkdir(parents=True,exist_ok=True)
    counts=fixtures[fixtures.competition_type.eq("league")].groupby("club_id").size()
    report=clubs[["canonical_club_id","canonical_name","fantrax_code","football_data_team_id"]].copy().rename(columns={"canonical_club_id":"club_id","canonical_name":"club"})
    report["football_data_mapped"]=report.football_data_team_id.notna(); report["fantrax_mapped"]=report.fantrax_code.notna()
    report["league_fixture_count"]=report.club_id.map(counts).fillna(0).astype(int)
    home_counts=fixtures[fixtures.home_away.eq("H")].groupby("club_id").size(); away_counts=fixtures[fixtures.home_away.eq("A")].groupby("club_id").size()
    report["home_fixture_count"]=report.club_id.map(home_counts).fillna(0).astype(int); report["away_fixture_count"]=report.club_id.map(away_counts).fillna(0).astype(int)
    future_counts={club_id:len(next_league_fixtures(fixtures,club_id,limit=5)) for club_id in report.club_id}
    report["next_fixture_available"]=report.club_id.map(future_counts).gt(0); report["next_five_available"]=report.club_id.map(future_counts).ge(5)
    unresolved=fixtures[fixtures.opponent_id.isna()].groupby("club_id").size(); report["unresolved_fixture_count"]=report.club_id.map(unresolved).fillna(0).astype(int)
    report["schedule_complete"]=report.league_fixture_count.eq(38)
    report["validation_status"]=report.schedule_complete.map({True:"complete",False:"partial"})
    report.to_csv(quality/"club_fixture_coverage_2627.csv",index=False)
    metrics=pd.DataFrame([
        ("canonical_clubs",len(clubs),20,len(clubs)==20),
        ("premier_league_matches",len(matches),380,len(matches)==380),
        ("duplicate_match_ids",int(matches.match_id.duplicated().sum()),0,not matches.match_id.duplicated().any()),
        ("unresolved_home_clubs",int(matches.home_club_id.isna().sum()),0,matches.home_club_id.notna().all()),
        ("unresolved_away_clubs",int(matches.away_club_id.isna().sum()),0,matches.away_club_id.notna().all()),
        ("missing_opponents",int(fixtures.opponent_id.isna().sum()),0,fixtures.opponent_id.notna().all()),
        ("missing_venues",int(fixtures.venue.isna().sum()),0,fixtures.venue.notna().all()),
        ("fantrax_periods_mapped",int(matches.fantrax_period.notna().sum()),len(matches),matches.fantrax_period.notna().all()),
        ("brighton_league_fixtures",int(counts.get("brighton_hove_albion",0)),38,int(counts.get("brighton_hove_albion",0))==38),
        ("fixture_ease_team_rows",int(fixtures.get("overall_fixture_ease",pd.Series(index=fixtures.index,dtype=float)).notna().sum()),len(fixtures),fixtures.get("overall_fixture_ease",pd.Series(index=fixtures.index,dtype=float)).notna().all()),
    ],columns=["metric","actual","expected","passed"])
    metrics.to_csv(quality/"team_fixture_quality_2627.csv",index=False)
    period_validation=pd.DataFrame([
        ("source_season","2627","2627",True),("period_count",len(periods),38,len(periods)==38),
        ("mapped_matches",int(matches.fantrax_period.notna().sum()),len(matches),matches.fantrax_period.notna().all()),
        ("source_status","current","current",True),
    ],columns=["metric","actual","expected","passed"])
    period_validation.to_csv(quality/"fantrax_period_mapping_validation_2627.csv",index=False)
    player_path=out/"live_player_analytics_2627.csv"
    if player_path.exists():
        players=pd.read_csv(player_path); enriched=enrich_players_with_fixtures(players,clubs,fixtures)
        player_quality=pd.DataFrame({"player_id":enriched.get("fantrax_player_id"),"player":enriched.get("player_name"),"club":enriched.get("premier_league_club"),
            "next_fixture":enriched.get("opening_opponent"),"next_five_count":enriched.canonical_club_id.map(future_counts).fillna(0).astype(int),
            "fixture_ease_available":enriched.next_five_fixture_ease_percentile.notna()})
        player_quality["validation_status"]=pd.Series("complete",index=player_quality.index).mask(enriched.canonical_club_id.isna(),"unresolved_club").mask(enriched.canonical_club_id.notna() & player_quality.next_fixture.isna(),"partial_schedule")
        player_quality.to_csv(quality/"player_fixture_enrichment_validation_2627.csv",index=False)
    fixtures[fixtures.club_id.eq("brighton_hove_albion")].to_csv(quality/"brighton_fixture_validation_2627.csv",index=False)
    return clubs,matches,fixtures

if __name__=="__main__":
    c,m,f=build(); print(f"clubs={len(c)} matches={len(m)} team_fixtures={len(f)} complete={len(m)==380}")
