"""Initialize, build, rebuild, or validate registered Cup artifacts."""
from __future__ import annotations
import json,sys
from pathlib import Path
import pandas as pd
from analytics.cup.engine import build_tournament,create_seed_snapshot,tournament_schedule,validate_configuration

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/"data"/"models"/"season_2627"; CONFIG=ROOT/"data"/"reference"/"cup_configuration_2627.csv"
def main():
    payload=json.loads(sys.stdin.read() or '{}'); action=payload.get("action","validate"); config=pd.read_csv(CONFIG).iloc[0].to_dict(); validate_configuration(config); OUT.mkdir(parents=True,exist_ok=True)
    pd.read_csv(CONFIG).to_csv(OUT/"cup_configuration_2627.csv",index=False); tournament_schedule(config).to_csv(OUT/"cup_schedule_2627.csv",index=False)
    snapshot_path=OUT/"cup_seed_snapshot_2627.csv"; standings_path=OUT/"league_standings_2627.csv"
    if action=="initialize" and snapshot_path.exists(): raise RuntimeError("Cup seed snapshot already exists and is immutable")
    if not snapshot_path.exists() and standings_path.exists(): create_seed_snapshot(pd.read_csv(standings_path),config).to_csv(snapshot_path,index=False)
    seeds=pd.read_csv(snapshot_path) if snapshot_path.exists() else pd.DataFrame(); scores_path=OUT/"manager_week_summary_2627.csv"; scores=pd.read_csv(scores_path) if scores_path.exists() else pd.DataFrame()
    bracket=build_tournament(config,seeds,scores,current_week=int(pd.to_numeric(scores.get("period"),errors="coerce").max()) if not scores.empty and pd.to_numeric(scores.get("period"),errors="coerce").notna().any() else None)
    bracket.to_csv(OUT/"cup_matchups_2627.csv",index=False); bracket[bracket["status"].eq("Final")].to_csv(OUT/"cup_results_2627.csv",index=False)
    records=pd.DataFrame(columns=["manager_id","manager","cup_wins","cup_losses","deepest_run","championships"]); records.to_csv(OUT/"cup_records_2627.csv",index=False)
    print(json.dumps({"action":action,"seeded":not seeds.empty,"matchups":len(bracket)}))
if __name__=="__main__": main()
