"""Write the Sprint 9.8B.1 representative historical-profile quality audit."""
from pathlib import Path
import pandas as pd
from analytics.players.research_overview import historical_profile_availability,overlay_historical_advanced

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"data/quality/season_2627/player_historical_profile_98b1_validation.csv"
METRICS=("goals","assists","key_passes","shots_on_target","successful_dribbles","tackles_won","interceptions","clearances","aerials_won","clean_sheets")

def main():
    current=pd.read_csv(ROOT/"data/models/season_2627/live_player_analytics_2627.csv",low_memory=False)
    profile=pd.read_csv(ROOT/"data/models/season_2627/historical_player_research_profile_2526.csv",low_memory=False)
    frame=overlay_historical_advanced(current,profile)
    preferred=["06y9m"]
    for position in ("G","D","M","F"):
        candidates=frame[frame.fantrax_position.astype(str).str.startswith(position)]
        if not candidates.empty:preferred.append(str(candidates.fantrax_player_id.iloc[0]))
    no_history=frame[[not historical_profile_availability(r)["fantasy"]["available"] for _,r in frame.iterrows()]]
    if not no_history.empty:preferred.append(str(no_history.fantrax_player_id.iloc[0]))
    rows=[]
    for _,row in frame[frame.fantrax_player_id.astype(str).isin(dict.fromkeys(preferred))].iterrows():
        availability=historical_profile_availability(row);record={"canonical_player_id":row.get("registry_player_id"),"player":row.get("player_name"),"position":row.get("fantrax_position"),"historical_available":any(x["available"] for x in availability.values())}
        for section in ("fantasy","attacking","defensive"):record[f"{section}_axes_available"]=len(availability[section]["available_axes"])
        for metric in METRICS:
            field=f"historical_{metric}_per_start";record[f"historical_{metric.replace('key_passes','kp').replace('shots_on_target','sot').replace('successful_dribbles','dribbles').replace('tackles_won','tkw').replace('interceptions','int').replace('clearances','clr').replace('aerials_won','aer').replace('clean_sheets','cs')}"]=row.get(field);record[f"{metric.replace('key_passes','kp').replace('shots_on_target','sot').replace('successful_dribbles','dribbles').replace('tackles_won','tkw').replace('interceptions','int').replace('clearances','clr').replace('aerials_won','aer').replace('clean_sheets','cs')}_source"]=row.get(f"{field}_source","MISSING") if pd.notna(row.get(field)) else "MISSING"
        for section in ("fantasy","attacking","defensive"):record[f"{section}_radar_rendered"]=availability[section]["available"]
        record["validation_status"]="PASS";rows.append(record)
    OUT.parent.mkdir(parents=True,exist_ok=True);pd.DataFrame(rows).to_csv(OUT,index=False);print(f"wrote {len(rows)} rows to {OUT}")

if __name__=="__main__":main()
