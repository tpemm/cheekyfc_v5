#!/usr/bin/env python3
"""Cache-first incremental Understat refresh for the live 2026/27 season."""
from __future__ import annotations
import argparse,json,os,subprocess,sys
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.services.machine_role import require_commissioner_writer
from integrations.whoscored.live_refresh import build_live_manifest
from fantrax.live.understat_live import _team_key
from fantrax.live.provider_maturity import provider_plan

def refresh_plan(season:str="2627")->dict:
    raw=ROOT/f"data/raw/understat/{season}";path=raw/f"understat_schedule_{season}_ENG-Premier_League.csv"
    cached=pd.read_csv(path) if path.exists() else pd.DataFrame()
    manifest_path=ROOT/f"data/reference/whoscored_season_manifest_{season}.csv";manifest=pd.read_csv(manifest_path) if manifest_path.exists() else pd.DataFrame()
    fixtures_path=ROOT/f"data/models/season_{season}/team_matches_{season}.csv"
    fixtures=pd.read_csv(fixtures_path) if fixtures_path.exists() else pd.DataFrame()
    # Recompute time eligibility now; WhoScored's saved plan can be a week old.
    if not fixtures.empty:
        manifest=build_live_manifest(fixtures,existing=manifest)
    eligible=manifest[manifest.get("planner_status",pd.Series(index=manifest.index,dtype=object)).isin(["ELIGIBLE_MISSING","ELIGIBLE_PRELIMINARY","FAILED_RETRYABLE","STABLE"])]
    players_path=raw/f"understat_player_match_stats_{season}_ENG-Premier_League.csv"
    players=pd.read_csv(players_path) if players_path.exists() else pd.DataFrame()
    player_ids=set(pd.to_numeric(players.get("game_id",pd.Series(dtype=float)),errors="coerce").dropna())
    usable=cached[cached.get("has_data",pd.Series(False,index=cached.index)).astype(str).str.lower().eq("true")
                  & pd.to_numeric(cached.get("game_id",pd.Series(index=cached.index,dtype=float)),errors="coerce").isin(player_ids)].copy()
    for metric in ("home_xg","away_xg"):
        usable=usable[pd.to_numeric(usable.get(metric,pd.Series(index=usable.index,dtype=float)),errors="coerce").notna()]
    # Same unique canonical home/away identity rule as the Understat builder.
    pairs={( _team_key(r.home_team),_team_key(r.away_team)) for r in usable.itertuples()}
    present=eligible.apply(lambda r:(_team_key(r.home_club_id),_team_key(r.away_club_id)) in pairs,axis=1) if len(eligible) else pd.Series(dtype=bool)
    expected=len(eligible);available=int(present.sum())
    fixture_periods=dict(zip(fixtures.get("match_id",pd.Series(dtype=object)).astype(str),pd.to_numeric(fixtures.get("fantrax_period",pd.Series(dtype=float)),errors="coerce")))
    eligible_periods=eligible.get("canonical_match_id",pd.Series(dtype=object)).astype(str).map(fixture_periods).dropna()
    cached_periods=pd.to_numeric(cached.get("gameweek",pd.Series(dtype=float)),errors="coerce").dropna()
    current_period=int(eligible_periods.max()) if len(eligible_periods) else int(cached_periods.max()) if len(cached_periods) else 1
    retrieved=datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat() if path.exists() else None
    metadata=[]
    for row in eligible.loc[present].itertuples():
        hit=usable[usable.home_team.map(_team_key).eq(_team_key(row.home_club_id)) & usable.away_team.map(_team_key).eq(_team_key(row.away_club_id))]
        item=hit.iloc[0]
        metadata.append({"maturity":item.get("maturity","PRELIMINARY"),"retrieved_at":item.get("retrieved_at",retrieved)})
    return {"expected_completed_matches":expected,"cached_completed_matches":available,"missing_matches":max(expected-available,0),"gameweeks":f"1-{max(current_period,1)}","would_acquire":max(expected-available,0),"cache_state":"COMPLETE" if expected and available>=expected else "PARTIAL" if available else "MISSING","maturity":provider_plan("understat",metadata,expected)}

def main()->int:
    p=argparse.ArgumentParser();p.add_argument("--season",default="2627");p.add_argument("--plan",action="store_true");p.add_argument("--force",action="store_true");a=p.parse_args()
    if a.season!="2627":raise SystemExit("Live Understat refresh supports season 2627 only")
    state=refresh_plan(a.season)
    if a.plan or (not a.force and not state["would_acquire"]):print(json.dumps({"status":"PLAN_ONLY" if a.plan else ("CACHE_HIT" if state["expected_completed_matches"] else "NO_ACTION_REQUIRED"),**state},indent=2));return 0
    require_commissioner_writer("Understat live acquisition")
    env=os.environ.copy();env["SOCCERDATA_DIR"]=str(ROOT/"data/raw/soccerdata/runtime")
    cmd=[sys.executable,str(ROOT/"fantrax/scraping/scrape_understat_to_csv.py"),"--season","2026/27","--league","ENG-Premier League","--out_dir",str(ROOT/f"data/raw/understat/{a.season}"),"--gws",state["gameweeks"],"--mode","upsert"]
    if not a.force:cmd.append("--missing-only")
    done=subprocess.run(cmd,cwd=ROOT,env=env,check=False)
    final=refresh_plan(a.season)
    status="FAIL" if done.returncode else "PARTIAL" if final["missing_matches"] else "PASS"
    print(json.dumps({"status":status,**final},indent=2))
    return done.returncode or (2 if final["missing_matches"] else 0)
if __name__=="__main__":raise SystemExit(main())
