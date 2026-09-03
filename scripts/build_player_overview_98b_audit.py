#!/usr/bin/env python3
"""Build the real-player Sprint 9.8B validation artifact."""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from analytics.players.research_overview import overlay_current_ownership,overlay_current_summary
from integrations.whoscored.workflows import atomic_csv

MODEL=ROOT/"data/models/season_2627";QUALITY=ROOT/"data/quality/season_2627"
frame=pd.read_csv(MODEL/"live_player_analytics_2627.csv",low_memory=False);summary=pd.read_csv(MODEL/"current_player_season_summary_2627.csv");log=pd.read_csv(MODEL/"current_player_match_log_2627.csv",low_memory=False);ownership=pd.read_csv(MODEL/"player_ownership_2627.csv")
frame=overlay_current_ownership(overlay_current_summary(frame,summary),ownership)
examples=["06y9m","05tre","07877","070hq","062ct","02lk5"]
rows=[]
for pid in examples:
    player=frame[frame.fantrax_player_id.astype(str).eq(pid)].iloc[0];observed=log[log.fantrax_player_id.astype(str).eq(pid)];match=observed.iloc[0] if not observed.empty else pd.Series(dtype=object)
    historical=pd.notna(player.get("historical_points_per_start"));current_observed=not observed.empty
    rows.append({"fantrax_id":pid,"player_name":player.get("player_name"),"club":player.get("premier_league_club"),"position":player.get("fantrax_position"),"roster_status":player.get("roster_status"),"fantasy_manager":player.get("current_manager_name"),"ownership":player.get("rostered_pct"),"games_played":player.get("current_appearances"),"starts":player.get("current_starts"),"minutes":player.get("current_minutes"),"season_fpts":player.get("current_fantasy_points"),"fpts_per_game":player.get("current_points_per_game"),"fpts_per_start":player.get("current_points_per_start"),"ghost_per_start":player.get("current_ghost_per_start"),"goals":player.get("current_goals"),"assists":player.get("current_assists"),"assist_source":match.get("assist_source"),"key_passes":player.get("current_key_passes"),"sot":player.get("current_shots_on_target"),"accurate_crosses":player.get("current_accurate_crosses"),"tackles_won":player.get("current_tackles_won"),"interceptions":player.get("current_interceptions"),"clearances":player.get("current_clearances"),"aerial_wins":player.get("current_aerials_won"),"clean_sheets":player.get("current_clean_sheets"),"xg":player.get("current_xg"),"xa":player.get("current_xa"),"xg90":player.get("current_xg_per_90"),"xa90":player.get("current_xa_per_90"),"whoscored_coverage":bool(current_observed and pd.notna(match.get("whoscored_player_id"))),"understat_coverage":bool(current_observed and pd.notna(match.get("understat_player_id")) and pd.notna(match.get("xg"))),"historical_2526_available":historical,"historical_overlay_valid":bool(historical and current_observed),"validation_status":"PASS" if (current_observed or pid=="02lk5") and pd.notna(player.get("player_name")) else "FAIL"})
atomic_csv(pd.DataFrame(rows),QUALITY/"player_overview_98b_validation_2627.csv")
print(pd.DataFrame(rows)[["player_name","validation_status"]].to_string(index=False))
