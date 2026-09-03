#!/usr/bin/env python3
"""Cache-first incremental Understat refresh for the live 2026/27 season."""
from __future__ import annotations
import argparse,json,os,subprocess,sys
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.services.machine_role import require_commissioner_writer

def refresh_plan(season:str="2627")->dict:
    raw=ROOT/f"data/raw/understat/{season}";path=raw/f"understat_schedule_{season}_ENG-Premier_League.csv"
    cached=pd.read_csv(path) if path.exists() else pd.DataFrame()
    manifest_path=ROOT/f"data/reference/whoscored_season_manifest_{season}.csv";manifest=pd.read_csv(manifest_path) if manifest_path.exists() else pd.DataFrame()
    eligible=manifest[manifest.get("planner_status",pd.Series(index=manifest.index,dtype=object)).isin(["ELIGIBLE_MISSING","ELIGIBLE_PRELIMINARY","FAILED_RETRYABLE","STABLE"])]
    expected=len(eligible);available=int(cached.get("has_data",pd.Series(index=cached.index,dtype=bool)).fillna(False).astype(bool).sum())
    fixtures_path=ROOT/f"data/models/season_{season}/team_matches_{season}.csv"
    fixtures=pd.read_csv(fixtures_path) if fixtures_path.exists() else pd.DataFrame()
    fixture_periods=dict(zip(fixtures.get("match_id",pd.Series(dtype=object)).astype(str),pd.to_numeric(fixtures.get("fantrax_period",pd.Series(dtype=float)),errors="coerce")))
    eligible_periods=eligible.get("canonical_match_id",pd.Series(dtype=object)).astype(str).map(fixture_periods).dropna()
    cached_periods=pd.to_numeric(cached.get("gameweek",pd.Series(dtype=float)),errors="coerce").dropna()
    current_period=int(eligible_periods.max()) if len(eligible_periods) else int(cached_periods.max()) if len(cached_periods) else 1
    return {"expected_completed_matches":expected,"cached_completed_matches":available,"missing_matches":max(expected-available,0),"gameweeks":f"1-{max(current_period,1)}","would_acquire":max(expected-available,0),"cache_state":"STABLE" if expected and available>=expected else "PARTIAL" if available else "MISSING"}

def main()->int:
    p=argparse.ArgumentParser();p.add_argument("--season",default="2627");p.add_argument("--plan",action="store_true");p.add_argument("--force",action="store_true");a=p.parse_args()
    if a.season!="2627":raise SystemExit("Live Understat refresh supports season 2627 only")
    state=refresh_plan(a.season)
    if a.plan or (not a.force and not state["would_acquire"]):print(json.dumps({"status":"PLAN_ONLY" if a.plan else "CACHE_HIT",**state},indent=2));return 0
    require_commissioner_writer("Understat live acquisition")
    env=os.environ.copy();env["SOCCERDATA_DIR"]=str(ROOT/"data/raw/soccerdata/runtime")
    cmd=[sys.executable,str(ROOT/"fantrax/scraping/scrape_understat_to_csv.py"),"--season","2026/27","--league","ENG-Premier League","--out_dir",str(ROOT/f"data/raw/understat/{a.season}"),"--gws",state["gameweeks"],"--mode","upsert"]
    done=subprocess.run(cmd,cwd=ROOT,env=env,check=False);print(json.dumps({"status":"ACQUIRED" if done.returncode==0 else "FAILED",**refresh_plan(a.season)},indent=2));return done.returncode
if __name__=="__main__":raise SystemExit(main())
