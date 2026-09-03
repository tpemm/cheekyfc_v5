import pandas as pd

from analytics.advanced_presentation import (
    formation_summary,
    pitch_layer_summary,
    player_metric_group,
    player_snapshot,
    playstyle_league_relative,
    role_share_frame,
)
from views.teams import formation_pitch_figure


def test_player_snapshot_and_groups_respect_one_rate_basis():
    profile=pd.Series({"average_rating":7.1,"goals_per90":.4,"assists_per90":.2,"key_passes_per90":2.1,
                       "dribbles_successful_per90":1.3,"aerial_wins_per90":2.0,"shots_per90":3.2,
                       "shots_on_target_per90":1.1,"xg_per90":.35})
    snapshot=player_snapshot(profile,"Per 90")
    assert snapshot.loc[snapshot.Metric.eq("Goals"),"Value"].item()==.4
    shooting=player_metric_group(profile,"Shooting","Per 90")
    assert dict(zip(shooting.Metric,shooting.Value))["Shots"]==3.2


def test_role_share_frame_honors_manager_context():
    roles=pd.DataFrame({"manager_name":["A","A","B"],"actual_tactical_role":["CM","RW","CM"],
                        "role_starts":[4,2,3],"role_share":[.67,.33,1.0]})
    shown=role_share_frame(roles,"A")
    assert shown.Starts.sum()==6
    assert set(shown["Observed Role"])=={"CM","RW"}


def test_pitch_summary_reconciles_selected_rows():
    events=pd.DataFrame({"canonical_match_id":["m1","m1","m2"],"outcome":["Successful","Failed","Successful"]})
    matches=pd.DataFrame({"canonical_match_id":["m1","m2","m3"]})
    result=pitch_layer_summary(events,matches)
    assert result=={"actions":3,"successful":2,"success_rate":200/3,"matches":2,"available_matches":3}


def test_formation_and_playstyle_summaries_are_display_only():
    formations=pd.DataFrame({"formation":["4-3-3","4-3-3","3-4-2-1"],"matches":[4,2,3]})
    assert formation_summary(formations)["formation"]=="4-3-3"
    league=pd.DataFrame({"club_id":["a","b","c"],"manager_id":["x","y","z"],"passes_attempted_per_match":[50,40,30]})
    relative=playstyle_league_relative(league[league.club_id.eq("a")],league,(("Passes","passes_attempted_per_match"),))
    assert relative.iloc[0]["Rank"]==1
    assert relative.iloc[0]["League Average"]==40


def test_formation_pitch_uses_observed_role_leaders():
    usage=pd.DataFrame({"actual_tactical_role":["CAM","CAM","ST"],"role_rank":[1,2,1],
                        "player_name":["One","Two","Nine"],"role_starts":[10,4,12]})
    figure=formation_pitch_figure(usage)
    assert "One" in " ".join(figure.data[0].text)
    assert list(figure.layout.yaxis.range)==[0,100]
