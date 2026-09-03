"""Cache-first soccerdata schedule and ClubElo acquisition."""
from __future__ import annotations
import argparse,json,os,sys,time
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT)); os.environ.setdefault("SOCCERDATA_DIR",str(ROOT/"data/raw/soccerdata/runtime"))
from analytics.teams.fixtures import load_clubs
from analytics.teams.soccerdata import normalize_clubelo_current,normalize_soccerdata_schedule,schedule_quality

RAW=ROOT/"data/raw/soccerdata"; QUALITY=ROOT/"data/quality/season_2627"; MODEL=ROOT/"data/models/season_2627"

def schedule(cache_only: bool=True):
    cache=RAW/"coverage_2627/sofascore/sofascore__read_schedule.csv"
    if not cache.exists() and cache_only: raise FileNotFoundError("No cached Sofascore schedule; rerun without --cache-only")
    if cache.exists(): raw=pd.read_csv(cache)
    else:
        import soccerdata as sd
        raw=sd.Sofascore(leagues="ENG-Premier League",seasons="2627",no_cache=False,data_dir=RAW/"sofascore").read_schedule().reset_index()
        if raw.empty: raise ValueError("Sofascore returned an empty schedule")
        cache.parent.mkdir(parents=True,exist_ok=True); raw.to_csv(cache,index=False)
    clubs=load_clubs(ROOT/"data/reference/premier_league_clubs_2627.csv"); matches=normalize_soccerdata_schedule(raw,clubs,retrieved_at=datetime.fromtimestamp(cache.stat().st_mtime,timezone.utc).isoformat())
    quality=schedule_quality(matches,clubs)
    if not quality["complete_380"]: raise ValueError(f"Sofascore schedule failed completeness: {quality}")
    return matches,quality,cache

def clubelo(cache_only: bool=True):
    cache=RAW/"clubelo/2026-08-19.csv"
    if not cache.exists() and cache_only: raise FileNotFoundError("No valid ClubElo cache is available")
    if cache.exists(): raw=pd.read_csv(cache).set_index("team")
    else:
        import soccerdata as sd
        raw=sd.ClubElo(no_cache=False,data_dir=RAW/"clubelo").read_by_date("2026-08-19")
        if raw.empty: raise ValueError("ClubElo returned empty current ratings")
    return raw,cache

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--mode",choices=("schedule","clubelo","all"),default="all"); parser.add_argument("--cache-only",action="store_true"); args=parser.parse_args(); start=time.perf_counter(); result={"mode":args.mode,"cache_only":args.cache_only,"started_at":datetime.now(timezone.utc).isoformat(),"outputs":{}}
    if args.mode in ("schedule","all"):
        matches,quality,cache=schedule(args.cache_only); result["outputs"]["schedule"]={"rows":len(matches),"cache":str(cache),**quality}
    if args.mode in ("clubelo","all"):
        raw,cache=clubelo(args.cache_only); result["outputs"]["clubelo"]={"rows":len(raw),"cache":str(cache)}
    result["elapsed_seconds"]=round(time.perf_counter()-start,3); print(json.dumps(result,indent=2,default=str))
if __name__=="__main__": main()
