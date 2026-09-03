#!/usr/bin/env python3
"""Build season-scoped Understat player/team match facts from the raw cache."""
from __future__ import annotations
import json,sys
from datetime import datetime,timezone
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from fantrax.live.understat_live import build_understat_match_products
from integrations.whoscored.workflows import atomic_csv,atomic_json

def main()->int:
    season="2627";raw=ROOT/f"data/raw/understat/{season}";model=ROOT/f"data/models/season_{season}";quality=ROOT/f"data/quality/season_{season}";reference=ROOT/"data/reference"
    schedule_path=raw/f"understat_schedule_{season}_ENG-Premier_League.csv";player_path=raw/f"understat_player_match_stats_{season}_ENG-Premier_League.csv"
    required=[schedule_path,player_path,model/f"premier_league_clubs_{season}.csv",reference/f"whoscored_season_manifest_{season}.csv",reference/f"player_registry_{season}.csv"]
    missing=[str(p.relative_to(ROOT)) for p in required if not p.exists()]
    if missing: print(json.dumps({"status":"BLOCKED","missing":missing},indent=2));return 2
    retrieved=datetime.fromtimestamp(max(schedule_path.stat().st_mtime,player_path.stat().st_mtime),timezone.utc).isoformat()
    identity,players,teams,unresolved=build_understat_match_products(*(pd.read_csv(p) for p in required),retrieved_at=retrieved,season_id=season)
    reciprocal=all(len(g)==2 and abs(float(g.xg.iloc[0])-float(g.xga.iloc[1]))<1e-9 and abs(float(g.xga.iloc[0])-float(g.xg.iloc[1]))<1e-9 for _,g in teams.groupby("canonical_match_id"))
    expected_matches=len(identity);expected_team_rows=expected_matches*2
    exact_statuses={"RESOLVED_EXACT","RESOLVED_EXACT_PAIR"};exact_identity=identity.resolution_status.isin(exact_statuses)
    gates=pd.DataFrame([
        {"gate":"exact_match_identity","passed":expected_matches>0 and exact_identity.all(),"observed":f"{exact_identity.sum()}/{expected_matches}"},
        {"gate":"team_perspectives","passed":len(teams)==expected_team_rows and teams.canonical_club_id.nunique()==20,"observed":f"{len(teams)} rows / {teams.canonical_club_id.nunique()} clubs"},
        {"gate":"xg_xga_reciprocity","passed":reciprocal,"observed":str(reciprocal)},
        {"gate":"player_match_rows","passed":len(players)>0,"observed":str(len(players))},
        {"gate":"played_zero_preserved","passed":bool(((players.minutes>0)&players.xg.eq(0)).any()),"observed":str(int(((players.minutes>0)&players.xg.eq(0)).sum()))},
    ])
    atomic_csv(identity,reference/f"understat_match_identity_{season}.csv");atomic_csv(players,model/f"understat_player_match_{season}.csv");atomic_csv(teams,model/f"understat_team_match_{season}.csv");atomic_csv(unresolved,quality/f"understat_unresolved_players_{season}.csv");atomic_csv(gates,quality/f"understat_gw1_quality_gates_{season}.csv")
    report={"status":"CURRENT" if gates.passed.all() else "FAILED_QUALITY_GATES","matches":len(identity),"team_rows":len(teams),"player_rows":len(players),"mapped_players":int(players.canonical_player_id.notna().sum()),"unresolved_players":len(unresolved),"retrieved_at":retrieved,"built_at":datetime.now(timezone.utc).isoformat()}
    atomic_json(report,quality/f"understat_live_latest_{season}.json");print(json.dumps(report,indent=2));return 0 if gates.passed.all() else 2
if __name__=="__main__":raise SystemExit(main())
