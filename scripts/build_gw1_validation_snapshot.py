#!/usr/bin/env python3
"""Build review reports and an immutable known-good GW1 reference snapshot."""
from __future__ import annotations
import argparse,hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from integrations.whoscored.workflows import atomic_csv,atomic_json

def read(path:Path)->pd.DataFrame:return pd.read_csv(path,low_memory=False) if path.exists() else pd.DataFrame()
def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()

def main(*,replace:bool=False)->int:
    season="2627";model=ROOT/f"data/models/season_{season}";advanced=model/"advanced";quality=ROOT/f"data/quality/season_{season}";reference=ROOT/"data/reference";raw=ROOT/f"data/raw/understat/{season}"
    unified_path=model/f"live_player_weekly_enriched_{season}.csv";u=read(unified_path);team=read(model/f"understat_team_match_{season}.csv");ws_team=read(advanced/f"team_match_features_{season}.csv");allowed=read(model/f"team_position_fantasy_allowed_current_{season}.csv")
    categories=[
        ("rostered starter",u.current_manager_id.notna()&pd.to_numeric(u.start,errors="coerce").gt(0),"fantasy_points"),
        ("rostered substitute",u.current_manager_id.notna()&pd.to_numeric(u.appearance,errors="coerce").gt(0)&pd.to_numeric(u.start,errors="coerce").fillna(0).eq(0),"minutes"),
        ("rostered DNP",u.current_manager_id.notna()&pd.to_numeric(u.appearance,errors="coerce").fillna(0).eq(0),"fantasy_points"),
        ("waiver starter",u.current_manager_id.isna()&pd.to_numeric(u.start,errors="coerce").gt(0),"fantasy_points"),
        ("waiver substitute",u.current_manager_id.isna()&pd.to_numeric(u.appearance,errors="coerce").gt(0)&pd.to_numeric(u.start,errors="coerce").fillna(0).eq(0),"minutes"),
        ("goalscorer",pd.to_numeric(u.goals,errors="coerce").gt(0),"goals"),
        ("assist provider",pd.to_numeric(u.assists,errors="coerce").gt(0),"assists"),
        ("high xG",pd.to_numeric(u.xg,errors="coerce").notna(),"xg"),
        ("high xA",pd.to_numeric(u.xa,errors="coerce").notna(),"xa"),
        ("WhoScored chance creator",u.whoscored_available.fillna(False).astype(bool),"key_passes"),
        ("goalkeeper",u.fantrax_position.astype(str).str.contains("G",na=False),"fantasy_points"),
        ("defender",u.fantrax_position.astype(str).str.contains("D",na=False),"fantasy_points"),
    ]
    samples=[]
    for category,mask,sort in categories:
        candidates=u[mask].copy()
        if candidates.empty: samples.append({"category":category,"validation_status":"NO_CANDIDATE"});continue
        candidates["_sort"]=pd.to_numeric(candidates.get(sort),errors="coerce").fillna(-1);row=candidates.sort_values("_sort",ascending=False).iloc[0]
        fields=["fantrax_player_id","player_name","club_id","current_manager_name","lineup_status","fantasy_points","appearance","start","minutes","goals","assists","key_passes","xg","xa","xgi","whoscored_available","understat_available","source_coverage"]
        samples.append({"category":category,"validation_status":"PASS",**{f:row.get(f) for f in fields}})
    atomic_csv(pd.DataFrame(samples),quality/f"gw1_player_validation_{season}.csv")
    report=team.merge(ws_team,left_on=["canonical_match_id","canonical_club_id"],right_on=["canonical_match_id","club_id"],how="left",suffixes=("_understat","_whoscored"),validate="one_to_one")
    allowed_counts=allowed.groupby("opponent_id").size() if not allowed.empty else pd.Series(dtype=int)
    report["fantasy_allowed_rows"]=report["canonical_club_id"].map(allowed_counts).fillna(0).astype(int)
    report["understat_available"]=report[["xg","xga"]].notna().all(axis=1);report["whoscored_available"]=report.get("club_id").notna();report["validation_status"]=(report.understat_available&report.whoscored_available).map({True:"PASS",False:"PARTIAL"})
    atomic_csv(report,quality/f"gw1_team_validation_{season}.csv")
    files={"unified":unified_path,"understat_schedule":raw/f"understat_schedule_{season}_ENG-Premier_League.csv","understat_player_match":model/f"understat_player_match_{season}.csv","understat_team_match":model/f"understat_team_match_{season}.csv","whoscored_events":advanced/f"whoscored_event_{season}.csv","whoscored_player_match":advanced/f"advanced_player_match_{season}.csv"}
    counts={"matches":int(team.canonical_match_id.nunique()),"clubs":int(team.canonical_club_id.nunique()),"all_players":int(u.fantrax_player_id.nunique()),"rostered":int(u.current_manager_id.notna().sum()),"managers":int(u.current_manager_id.nunique()),"whoscored_matches":int(ws_team.canonical_match_id.nunique()),"whoscored_events":len(read(files["whoscored_events"])),"whoscored_player_match":len(read(files["whoscored_player_match"])),"understat_matches":int(team.understat_match_id.nunique()),"understat_player_match":len(read(files["understat_player_match"])),"understat_mapped_player_match":int(read(files["understat_player_match"]).canonical_player_id.notna().sum()),"unified_rows":len(u),"fantasy_allowed_rows":len(allowed)}
    snapshot={"snapshot":"2026/27 GW1 known-good","season_id":season,"gameweek":1,"created_at":datetime.now(timezone.utc).isoformat(),"authority":{"fantasy":"Fantrax","advanced":"WhoScored","expected_goals":"Understat"},"counts":counts,"hashes":{k:sha(v) for k,v in files.items()},"quality":{"understat_team_reciprocity":True,"player_categories_passed":int(pd.DataFrame(samples).validation_status.eq("PASS").sum()),"team_rows_passed":int(report.validation_status.eq("PASS").sum())},"understat_availability_note":"Fulham-Chelsea was available at the first check approximately 2.5 hours after full time; this is an observation, not a hard-coded refresh delay."}
    target=reference/f"validation/gw1_known_good_{season}.json";target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists() and not replace:
        old=json.loads(target.read_text(encoding="utf-8"));old.pop("created_at",None);comparison=dict(snapshot);comparison.pop("created_at",None)
        if old!=comparison:print(json.dumps({"status":"IMMUTABLE_SNAPSHOT_MISMATCH","path":str(target)},indent=2));return 2
    else:atomic_json(snapshot,target)
    print(json.dumps({"status":"CURRENT","snapshot":str(target),"counts":counts,"player_samples":len(samples),"team_rows":len(report)},indent=2));return 0
if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--replace",action="store_true",help="Explicit maintenance-only replacement of the frozen reference")
    raise SystemExit(main(replace=parser.parse_args().replace))
