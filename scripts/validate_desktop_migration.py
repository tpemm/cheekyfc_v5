from pathlib import Path
from hashlib import sha256
import json,sys,pandas as pd
ROOT=Path(__file__).parents[1];sys.path.insert(0,str(ROOT));CHECK=ROOT/"data/quality/season_2627/gw2_laptop_migration_checkpoint_repaired.json"
def main():
    checkpoint=json.loads(CHECK.read_text(encoding="utf-8"));fail=[]
    for relative,expected in checkpoint["artifact_sha256"].items():
        path=ROOT/relative;actual=sha256(path.read_bytes()).hexdigest() if path.exists() else None
        if actual!=expected:fail.append({"path":relative,"expected":expected,"actual":actual})
    counts=checkpoint["counts"];players=pd.read_csv(ROOT/"data/models/season_2627/live_player_analytics_2627.csv");checks={"players":len(players),"rostered":int((~players.available.fillna(True)).sum()),"available":int(players.available.fillna(False).sum()),"managers":pd.read_csv(ROOT/"data/models/season_2627/live_league_summary_2627.csv").manager_id.nunique(),"manager_weeks":len(pd.read_csv(ROOT/"data/models/season_2627/manager_week_summary_2627.csv"))}
    if checks!=counts:fail.append({"counts_expected":counts,"counts_actual":checks})
    tactical=pd.read_csv(ROOT/"data/models/season_2627/team_tactical_profile_2627.csv");assert tactical.methodology_version.eq("team_tactical_v1").all()
    print(json.dumps({"status":"PASS" if not fail else "FAIL","migration_hash_validation":"exact pre-refresh","checks":checks,"failures":fail},indent=2));return 0 if not fail else 1
if __name__=="__main__":raise SystemExit(main())
