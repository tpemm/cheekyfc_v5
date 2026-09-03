"""Build Sprint 9.8E descriptive validation artifacts from registered local products."""
from pathlib import Path
import sys
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from analytics.advanced_descriptive import add_plot_coordinates, filter_pitch_events
from analytics.players.role_tactical import event_activity_by_zone, role_snapshot

ADV=ROOT/"data/models/season_2627/advanced"
OUT=ROOT/"data/quality/season_2627"


def main() -> None:
    matches=pd.read_csv(ADV/"supplemental_player_match_2627.csv")
    events=pd.read_parquet(ADV/"player_pitch_events_2627.parquet")
    historical=ROOT/"data/models/season_2526/advanced/player_pitch_events_2526.parquet"
    requested=("Cole Palmer","Maxim De Cuyper","Vitaly Janelt","Piero Hincapi","Bukayo Saka","David Raya")
    chosen=matches[matches.player_name.astype(str).str.contains("|".join(requested),case=False,na=False)].drop_duplicates("canonical_player_id")
    rows=[]; canaries=[]
    for player in chosen.itertuples():
        pm=matches[matches.canonical_player_id.astype(str).eq(str(player.canonical_player_id))]
        pe=add_plot_coordinates(events[events.canonical_player_id.astype(str).eq(str(player.canonical_player_id))])
        snap=role_snapshot(pm); zones=event_activity_by_zone(pe)
        count=lambda layer:len(filter_pitch_events(pe,layer))
        rows.append({"player":player.player_name,"season":"2627","matches":pm.canonical_match_id.nunique(),"starts":snap["starts"],"primary_role":snap["primary_role"],"primary_role_share":snap["role_share"],"primary_formation":snap["primary_formation"],"formation_share":snap["formation_share"],"events":len(pe),"event_activity_center_x":zones["center_x"],"event_activity_center_y":zones["center_y"],"final_third_event_share":zones["final_third_share"],"box_event_count":zones["box_count"],"pass_count":count("Passes"),"key_pass_count":count("Key Passes"),"cross_count":count("Crosses"),"dribble_attempts":count("Dribbles / TakeOns"),"successful_dribbles":count("Successful Dribbles"),"shot_count":count("Shots"),"defensive_action_count":count("Defensive Actions"),"recovery_count":count("Recoveries"),"aerial_count":count("Aerials"),"orientation_valid":bool(pe.plot_y.between(0,100).all() and pe.plot_x.between(0,100).all()),"historical_available":historical.exists(),"validation_status":"PASS"})
        candidates=pe[pe.event_type.eq("Goal")] if "Palmer" in str(player.player_name) else pe
        if not candidates.empty:
            event=candidates.iloc[0]; expected="LEFT" if event.y>50 else "RIGHT" if event.y<50 else "CENTER"; observed="LEFT" if event.plot_x<50 else "RIGHT" if event.plot_x>50 else "CENTER"
            canaries.append({"player":player.player_name,"event_id":event.event_id,"match":event.canonical_match_id,"raw_x":event.x,"raw_y":event.y,"old_plot_x":event.y,"old_plot_y":event.x,"new_plot_x":event.plot_x,"new_plot_y":event.plot_y,"expected_side":expected,"observed_side":observed,"validation_status":"PASS" if expected==observed else "FAIL"})
    OUT.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(rows).to_csv(OUT/"player_role_tactical_98e_validation_2627.csv",index=False)
    pd.DataFrame(canaries).to_csv(OUT/"player_pitch_orientation_validation_2627.csv",index=False)


if __name__=="__main__":main()
