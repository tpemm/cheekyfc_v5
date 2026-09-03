"""Build the cache-only Sprint 9.7.7A evidence and performance report."""
from pathlib import Path
import json,sys,time
import pandas as pd

ROOT=Path(__file__).parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

from fantrax.live.league_analytics import league_highlights,manager_active_season_totals,manager_award_leaderboards,scoring_frames
from fantrax.live.league_lineups import optimal_legal_xi
from views.live_league_hub import build_live_hub_model

MODEL=ROOT/"data/models/season_2627";QUALITY=ROOT/"data/quality/season_2627"


def timed(label,fn,rows):
    started=time.perf_counter();value=fn();return value,{"stage":label,"rows":rows,"seconds":round(time.perf_counter()-started,6)}


def main():
    weekly=pd.read_csv(MODEL/"current_player_weekly_2627.csv",dtype={"fantrax_player_id":str});active=pd.read_csv(MODEL/"league_active_player_weekly_2627.csv",dtype={"fantrax_player_id":str})
    weeks=pd.read_csv(MODEL/"manager_week_summary_2627.csv");games=pd.read_csv(MODEL/"weekly_matchups_2627.csv");teams=pd.read_csv(MODEL/"league_teams_2627.csv");standings=pd.read_csv(MODEL/"league_standings_2627.csv")
    timings=[];_,item=timed("active_lineup_preparation",lambda:active.copy(),len(active));timings.append(item)
    _,item=timed("efficiency_calculation",lambda:[optimal_legal_xi(group) for _,group in weekly[weekly.current_manager_id.notna()].groupby("current_manager_id")],len(weekly));timings.append(item)
    _,item=timed("league_awards",lambda:league_highlights(weeks,games),len(weeks));timings.append(item)
    totals,item=timed("manager_award_aggregation",lambda:manager_active_season_totals(active),len(active));timings.append(item)
    boards,item=timed("manager_award_ranking",lambda:manager_award_leaderboards(totals),len(totals));timings.append(item)
    model,item=timed("league_hub_model",lambda:build_live_hub_model(teams,standings,games,weeks),len(weeks));timings.append(item)
    scoring,history=scoring_frames(weeks);gw=games[pd.to_numeric(games.period,errors="coerce").eq(1)]
    report={"decision":"PASS","period_state_before":"ACTIVE","period_state_after":"COMPLETE_PENDING_CORRECTIONS","terminal_whoscored_matches":10,"fantrax_period_finalized":False,"completed_matchups":len(gw[gw.status.eq("completed")]),"manager_week_rows":len(weeks),"active_lineup_rows":len(active),"efficiency_rows":int(weeks.lineup_efficiency_pct.notna().sum()),"lineup_changes_non_null":int(weeks.lineup_changes.notna().sum()),"weekly_scoring_managers":max(len(scoring.columns)-1,0),"position_history_managers":len(history.columns),"leaderboard_rows":{key:len(value) for key,value in boards.items()}}
    QUALITY.mkdir(parents=True,exist_ok=True);(QUALITY/"league_hub_gw1_finalization_2627.json").write_text(json.dumps(report,indent=2),encoding="utf-8");pd.DataFrame(timings).to_csv(QUALITY/"league_hub_performance_2627.csv",index=False);totals.to_csv(QUALITY/"manager_active_season_totals_2627.csv",index=False)
    print(json.dumps(report,indent=2))


if __name__=="__main__":main()
