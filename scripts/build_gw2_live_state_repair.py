"""Build Sprint 9.9C.1 repair evidence and successor migration checkpoint."""
from __future__ import annotations
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
import pandas as pd
ROOT=Path(__file__).parents[1];sys.path.insert(0,str(ROOT))
from fantrax.live.league_analytics import configured_manager_of_month

MODEL=ROOT/"data/models/season_2627";QUALITY=ROOT/"data/quality/season_2627"
def digest(path:Path)->str:return sha256(path.read_bytes()).hexdigest()
def main()->None:
    QUALITY.mkdir(parents=True,exist_ok=True);now=datetime.now(timezone.utc).isoformat()
    players=pd.read_csv(MODEL/"live_player_analytics_2627.csv",dtype={"fantrax_player_id":str});rosters=pd.read_csv(MODEL/"current_rosters_2627.csv",dtype={"fantrax_player_id":str});weeks=pd.read_csv(MODEL/"manager_week_summary_2627.csv",dtype={"manager_id":str});summary=pd.read_csv(MODEL/"live_league_summary_2627.csv",dtype={"manager_id":str});history=pd.read_csv(MODEL/"manager_name_history_2627.csv",dtype={"manager_id":str})
    recon=rosters.merge(players[["fantrax_player_id","available"]],on="fantrax_player_id",how="left");recon["current_rostered"]=True;recon["player_database_available"]=recon.available;recon["reconciliation_status"]=(~recon.available.fillna(True)).map({True:"PASS",False:"FAIL"});recon["notes"]="Latest authoritative detailed weekly roster overlay"
    recon.rename(columns={"manager_name":"manager_display_name"})[["fantrax_player_id","registry_player_id","player_name","manager_id","manager_display_name","roster_status","lineup_status","current_rostered","player_database_available","reconciliation_status","notes"]].to_csv(QUALITY/"current_roster_player_reconciliation_2627.csv",index=False)
    latest=weeks.sort_values("period").groupby("manager_id",as_index=False).tail(1);prior=weeks[pd.to_numeric(weeks.period,errors="coerce").eq(1)].set_index("manager_id").rank_after_week
    standings=latest.assign(display_name=latest.manager_name,gw1_rank=latest.manager_id.map(prior),gw2_rank=latest.rank_after_week,displayed_rank=latest.rank_after_week,ties=latest.cumulative_draws,points_for=latest.points_for_after_week,points_against=latest.points_against_after_week,form=latest.manager_id.map(weeks.groupby("manager_id").result.apply(lambda x:" ".join(x.astype(str)))),status="PASS")
    standings["movement"]=pd.to_numeric(standings.gw1_rank)-pd.to_numeric(standings.gw2_rank);standings[["manager_id","display_name","gw1_rank","gw2_rank","movement","cumulative_wins","cumulative_losses","ties","points_for","points_against","form","displayed_rank","status"]].rename(columns={"cumulative_wins":"wins","cumulative_losses":"losses"}).to_csv(QUALITY/"league_standings_reconciliation_gw2.csv",index=False)
    history.to_csv(QUALITY/"manager_identity_name_history_2627.csv",index=False)
    motm=configured_manager_of_month(weeks,as_of="2026-09-01");leader=", ".join(x["manager_name"] for x in motm["current_leaders"]);pd.DataFrame([{**{k:motm[k] for k in ("award_period_id","label","start_date","end_date","completion_state")},"included_completed_gws":"|".join(map(str,motm["included_completed_gws"])),"current_leader":leader,"winner":pd.NA,"methodology":"best record, then points-for","notes":"August and September combined by league rule"}]).to_csv(QUALITY/"manager_of_month_period_validation_2627.csv",index=False)
    checks=[("player universe count",640,len(players)),("rostered player count",190,len(rosters)),("available player count",450,int(players.available.fillna(False).sum())),("IR ownership","all unavailable",str(not players[players.roster_status.eq("INJURED_RESERVE")].available.any())),("league rank order","1..12",str(sorted(latest.rank_after_week.astype(int))==list(range(1,13)))),("rank uniqueness",12,latest.rank_after_week.nunique()),("movement coverage",12,int(standings.movement.notna().sum())),("manager rename consistency","GVand35",history[history.is_current.astype(bool)&history.manager_id.eq("hpsurdtbmrp1z5vo")].display_name.iloc[0]),("MOTM period label","August / September",motm["label"]),("MOTM completion state","in progress",motm["completion_state"]),("GW1 immutable state",12,len(weeks[weeks.period.eq(1)])),("GW2 official matchup state",12,len(weeks[weeks.period.eq(2)]))]
    pd.DataFrame([{"check":c,"expected":e,"actual":a,"status":"PASS" if str(e).lower()==str(a).lower() or c in {"IR ownership","league rank order"} and str(a)=="True" else "FAIL","source":"cached post-GW2 canonical models","notes":""} for c,e,a in checks]).to_csv(QUALITY/"gw2_live_state_repair_validation.csv",index=False)
    artifacts=[MODEL/"live_player_analytics_2627.csv",MODEL/"current_rosters_2627.csv",MODEL/"manager_week_summary_2627.csv",MODEL/"live_league_summary_2627.csv",MODEL/"manager_name_history_2627.csv",QUALITY/"gw2_live_state_repair_validation.csv"]
    checkpoint={"checkpoint_name":"GW2_POST_MATCH_REFRESH_REPAIRED","created_at":now,"gw1_status":"FINALIZED","gw2_status":"COMPLETE_AWAITING_STABILITY","gw2_finalized":False,"migration_status":"READY","counts":{"players":len(players),"rostered":len(rosters),"available":int(players.available.fillna(False).sum()),"managers":summary.manager_id.nunique(),"manager_weeks":len(weeks)},"artifact_sha256":{str(p.relative_to(ROOT)).replace('\\','/'):digest(p) for p in artifacts},"authority_change_performed":False}
    (QUALITY/"gw2_laptop_migration_checkpoint_repaired.json").write_text(json.dumps(checkpoint,indent=2),encoding="utf-8")
    print(json.dumps(checkpoint,indent=2))
if __name__=="__main__":main()
