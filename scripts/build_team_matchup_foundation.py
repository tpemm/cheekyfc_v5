"""Build cache-only Sprint 9.1 observed and derived matchup datasets."""
from pathlib import Path
import sys,pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from analytics.teams.fixtures import load_clubs
from analytics.teams.matchup import *

def read(path): return pd.read_csv(path) if path.exists() else pd.DataFrame()
def build():
    model=ROOT/"data/models/season_2627"; quality=ROOT/"data/quality/season_2627"; quality.mkdir(parents=True,exist_ok=True)
    clubs=load_clubs(ROOT/"data/reference/premier_league_clubs_2627.csv"); fixtures=read(model/"team_fixtures_2627.csv"); weekly=read(model/"current_player_weekly_2627.csv"); players=read(model/"live_player_analytics_2627.csv")
    observations=build_team_match_observations(fixtures,weekly,clubs); allowed=build_position_fantasy_allowed(weekly,fixtures,clubs); attack,defense=build_team_profiles(observations)
    team_features=build_team_matchup_features(fixtures,attack,defense); player_features=build_player_matchup_features(players,fixtures,allowed,clubs,weekly)
    outputs={"team_match_observations":observations,"team_position_fantasy_allowed":allowed,"team_attack_profile":attack,"team_defense_profile":defense,"team_matchup_features":team_features,"player_matchup_features":player_features}
    for key,frame in outputs.items(): frame.to_csv(model/f"{key}_2627.csv",index=False)
    assigned=assign_position_groups(weekly); pd.DataFrame([{"metric":"weekly_rows","value":len(weekly),"status":"preseason" if weekly.empty else "available"},{"metric":"unresolved_positions","value":int(assigned.position_group.isna().sum()),"status":"passed" if assigned.position_group.notna().all() else "review"},{"metric":"allowed_rows","value":len(allowed),"status":"preseason" if allowed.empty else "available"}]).to_csv(quality/"team_position_fantasy_allowed_validation_2627.csv",index=False)
    pd.DataFrame([{"dataset":"team_matchup_features","rows":len(team_features),"observed_rows":len(observations),"prediction_columns":0,"status":"schedule-only preseason" if observations.empty else "observations available"}]).to_csv(quality/"team_matchup_feature_coverage_2627.csv",index=False)
    pd.DataFrame([{"dataset":"player_matchup_features","rows":len(player_features),"resolved_clubs":int(player_features.club_id.notna().sum()),"contains_predictions":False,"status":"schedule/player context; preseason observations unavailable"}]).to_csv(quality/"player_matchup_feature_coverage_2627.csv",index=False)
    pd.DataFrame([{"source":"Fantrax current_player_weekly","rows":len(weekly),"completed_periods":int(pd.to_numeric(weekly.get("period",pd.Series(dtype=float)),errors="coerce").nunique()),"fantasy_points_rows":int(weekly.get("fantasy_points",pd.Series(dtype=float)).notna().sum()),"ghost_points_rows":int(weekly.get("ghost_points",pd.Series(dtype=float)).notna().sum()),"minutes_rows":int(weekly.get("minutes",pd.Series(dtype=float)).notna().sum()),"status":"preseason awaiting completed periods" if weekly.empty else "available"}]).to_csv(quality/"fantrax_positional_observation_coverage_2627.csv",index=False)
    understat=read(model/"understat_player_weekly_2627.csv"); pd.DataFrame([{"source":"Understat current player weekly","rows":len(understat),"xg_rows":int(understat.get("xg",pd.Series(dtype=float)).notna().sum()),"xa_rows":int(understat.get("xa",pd.Series(dtype=float)).notna().sum()),"status":"preseason unavailable" if understat.empty else "available"}]).to_csv(quality/"understat_team_observation_coverage_2627.csv",index=False)
    pd.DataFrame([{"provider":"Sofascore 1.9.1","method":"read_schedule","status":"available","rows":380,"fields":"date|home_team|away_team|scores|round|game_id","cache_path":"data/raw/soccerdata/coverage_2627/sofascore"},{"provider":"Sofascore 1.9.1","method":"read_team_match_stats","status":"method unavailable","rows":0,"fields":"","cache_path":""},{"provider":"Sofascore 1.9.1","method":"read_player_match_stats","status":"method unavailable","rows":0,"fields":"","cache_path":""},{"provider":"Sofascore 1.9.1","method":"read_lineups/formations/events","status":"methods unavailable","rows":0,"fields":"","cache_path":""}]).to_csv(quality/"sofascore_match_context_coverage_2627.csv",index=False)
    pd.DataFrame([{"source":"Sofascore/WhoScored","formation_rows":0,"lineup_rows":0,"role_rows":0,"status":"no reproducible 2026/27 source cache; no inference performed"}]).to_csv(quality/"lineup_formation_coverage_2627.csv",index=False)
    pd.DataFrame([{"source":"WhoScored via soccerdata 1.9.1","prototype_matches":0,"event_rows":0,"schedule_cache":False,"event_cache":False,"status":"blocked: no reproducible cache; Selenium reader not promoted"}]).to_csv(quality/"whoscored_event_prototype_2627.csv",index=False)
    return outputs
if __name__=="__main__":
    result=build(); print(" ".join(f"{k}={len(v)}" for k,v in result.items()))
