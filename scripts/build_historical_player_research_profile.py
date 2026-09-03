"""Build the compact 2025/26 presentation profile without changing frozen sources."""
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
PROFILE=ROOT/"data/models/season_2526/advanced/player_advanced_profile_2526.csv"
EVENTS=ROOT/"data/models/season_2526/advanced/player_event_data_2526.csv"
OUTPUT=ROOT/"data/models/season_2627/historical_player_research_profile_2526.csv"

def build()->pd.DataFrame:
    profile=pd.read_csv(PROFILE)
    events=pd.read_csv(EVENTS,usecols=["canonical_player_id","event_type","outcome"],low_memory=False)
    won=events[events.event_type.eq("Tackle")&events.outcome.eq("Successful")].groupby("canonical_player_id").size().rename("tackles_won")
    profile=profile.merge(won,on="canonical_player_id",how="left")
    observed=profile.canonical_player_id.isin(events.canonical_player_id.unique())
    profile.loc[observed,"tackles_won"]=profile.loc[observed,"tackles_won"].fillna(0)
    starts=pd.to_numeric(profile.starts,errors="coerce")
    profile["tackles_won_per_start"]=pd.to_numeric(profile.tackles_won,errors="coerce").div(starts.where(starts.gt(0)))
    return profile

if __name__=="__main__":
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    result=build();result.to_csv(OUTPUT,index=False)
    print(f"wrote {len(result)} rows to {OUTPUT}")
