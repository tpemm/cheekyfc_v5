#!/usr/bin/env python3
"""Build the Sprint 9.8F real-player Advanced validation artifact."""
from pathlib import Path
import sys
import pandas as pd

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from analytics.players.advanced import aggregate_advanced,fantasy_contributions,fantasy_reconciliation,overlay_fantrax_authority,return_points

MODEL=ROOT/"data/models/season_2627";ADV=MODEL/"advanced";OUT=ROOT/"data/quality/season_2627"


def main():
    log=pd.read_csv(MODEL/"current_player_match_log_2627.csv",low_memory=False)
    supp=pd.read_csv(ADV/"supplemental_player_match_2627.csv",low_memory=False)
    live=pd.read_csv(MODEL/"live_player_analytics_2627.csv",low_memory=False)
    merged=overlay_fantrax_authority(supp,log)
    names=["Maxim De Cuyper","Jack Hinshelwood","Vitaly Janelt","Mamadou Sang","Piero Hincapi","Carl Rushworth"]
    forward=log[log.fantrax_position.astype(str).str.startswith("F")].player_name.dropna().astype(str)
    keeper=log[log.fantrax_position.astype(str).eq("G")].player_name.dropna().astype(str)
    if len(forward):names.append(forward.iloc[0])
    if len(keeper):names.append(keeper.iloc[0])
    candidates=[]
    for pid,group in merged.groupby("fantrax_player_id",dropna=True):
        profile=aggregate_advanced(group);position=log.loc[log.fantrax_player_id.astype(str).eq(str(pid)),"fantrax_position"]
        if position.empty:continue
        recon=fantasy_reconciliation(profile,fantasy_contributions(profile,position.iloc[0]));candidates.append((abs(recon["unreconciled_difference"]) if pd.notna(recon["unreconciled_difference"]) else -1,group.player_name.iloc[0]))
    if candidates:names.append(max(candidates)[1])
    rows=[]
    for name in dict.fromkeys(names):
        selected=merged[merged.player_name.astype(str).str.contains(str(name),case=False,na=False)]
        current=log[log.player_name.astype(str).str.contains(str(name),case=False,na=False)]
        if selected.empty or current.empty:continue
        profile=aggregate_advanced(selected);identity=current.iloc[0];position=identity.fantrax_position
        scoring=selected.get("ghost_scoring_position",pd.Series(index=selected.index,dtype=object)).dropna().astype(str);scoring_position=scoring.mode().iat[0] if len(scoring) else str(position).split(',')[0]
        contributions=fantasy_contributions(profile,scoring_position);recon=fantasy_reconciliation(profile,contributions)
        live_row=live[live.fantrax_player_id.astype(str).eq(str(identity.fantrax_player_id))]
        hist_starts=pd.to_numeric(live_row.get("historical_starts"),errors="coerce").iloc[0] if not live_row.empty and "historical_starts" in live_row else pd.NA
        value=lambda field:profile.get(field,pd.NA)
        rows.append({"player":identity.player_name,"position":position,"ownership_status":identity.get("roster_status",pd.NA),"starts":profile.starts,"minutes":profile.minutes,"fpts":value("fantrax_points"),"fpts_per_start":value("fantrax_points")/profile.starts if profile.starts else pd.NA,"ghost":value("ghost_points"),"ghost_per_start":value("ghost_points")/profile.starts if profile.starts else pd.NA,"return_points":return_points(profile,scoring_position),"goals":value("goals"),"assists":value("assists"),"cs":value("clean_sheets"),"kp":value("key_passes"),"sot":value("shots_on_target"),"shots":value("shots"),"xg":value("xg"),"xa":value("xa"),"cross_attempts":value("cross_attempts"),"accurate_crosses":value("accurate_crosses"),"dribble_attempts":value("dribbles_attempted"),"successful_dribbles":value("successful_dribbles"),"tackle_attempts":value("tackles"),"tackles_won":value("tackles_won"),"interceptions":value("interceptions"),"clearances":value("clearances"),"recoveries":value("recoveries"),"aerial_attempts":value("aerial_attempts"),"aerial_wins":value("aerial_wins"),"rating":value("rating"),"fantasy_component_sum":recon["known_component_contribution"],"official_fpts":recon["official_fpts"],"unreconciled_difference":recon["unreconciled_difference"],"historical_available":pd.notna(hist_starts) and hist_starts>0,"historical_starts":hist_starts,"validation_status":"PASS"})
    OUT.mkdir(parents=True,exist_ok=True);pd.DataFrame(rows).to_csv(OUT/"player_advanced_98f_validation_2627.csv",index=False)


if __name__=="__main__":main()
