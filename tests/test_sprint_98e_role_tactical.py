import pandas as pd

from analytics.advanced_descriptive import add_plot_coordinates, filter_pitch_events
from analytics.players.research_overview import overview_gameweek_table
from analytics.players.role_tactical import event_activity_by_zone, filter_role_scope, role_snapshot
from components.player_pitch import draw_pitch, pitch_shapes


def test_successful_dribble_layer_contains_only_successful_takeons():
    events=pd.DataFrame({"event_type":["TakeOn","TakeOn","Pass"],"outcome":["Successful","Unsuccessful","Successful"],"qualifiers":["[]"]*3,"is_key_pass":[False]*3})
    shown=filter_pitch_events(events,"Successful Dribbles")
    assert shown[["event_type","outcome"]].values.tolist()==[["TakeOn","Successful"]]


def test_lateral_orientation_raw_preservation_and_endpoints():
    raw=pd.DataFrame({"x":[90.,10.],"y":[80.,20.],"end_x":[95.,40.],"end_y":[90.,30.]})
    shown=add_plot_coordinates(raw)
    pd.testing.assert_frame_equal(shown[["x","y","end_x","end_y"]],raw)
    assert shown.loc[0,["plot_x","plot_y","plot_end_x","plot_end_y"]].tolist()==[20.,90.,10.,95.]
    assert shown.loc[1,"plot_x"]==80 and shown.loc[1,"plot_y"]==10


def test_cole_palmer_goal_canary_corrects_left_without_changing_depth():
    raw=pd.DataFrame({"event_id":["ws:2959574243:1"],"x":[96.9],"y":[65.0],"end_x":[None],"end_y":[None]})
    shown=add_plot_coordinates(raw)
    assert shown.loc[0,"plot_x"]==35.0
    assert shown.loc[0,"plot_y"]==96.9
    assert shown.loc[0,"x"]==96.9 and shown.loc[0,"y"]==65.0


def test_complete_pitch_geometry_and_no_cartesian_axes():
    shapes=pitch_shapes(); types=[shape["type"] for shape in shapes]
    assert len(shapes)==18
    assert types.count("rect")==7  # boundary, four boxes, and two goals
    assert types.count("circle")==4  # center circle/spot and two penalty spots
    assert types.count("path")==6  # two penalty arcs and four corner arcs
    fig=draw_pitch()
    assert fig.layout.xaxis.visible is False and fig.layout.yaxis.visible is False


def test_role_filters_snapshot_and_zone_activity_are_descriptive():
    matches=pd.DataFrame({"canonical_match_id":["a","b","c"],"venue":["H","A","H"],"started":[True,True,False],"actual_tactical_role":["LW","LW","LB"],"formation":["433","433","4231"],"minutes":[90,80,20]})
    events=add_plot_coordinates(pd.DataFrame({"canonical_match_id":["a","b","c"],"x":[80.,50.,20.],"y":[80.,50.,20.],"end_x":[None]*3,"end_y":[None]*3}))
    selected,selected_events=filter_role_scope(matches,events,context="Home",start_status="All appearances")
    assert selected.canonical_match_id.tolist()==["a","c"] and len(selected_events)==2
    snapshot=role_snapshot(matches); assert snapshot["primary_role"]=="LW" and snapshot["role_share"]==1
    zones=event_activity_by_zone(events); assert zones["events"]==3 and zones["box_count"]==0


def test_overview_gameweek_table_places_successful_dribbles_between_ac_and_tkw():
    row={"fantrax_player_id":"p","fantrax_period":1,"opponent_id":"x","venue":"H","canonical_match_id":"m","fantrax_points":1,"ghost_points":0,"appeared":True,"started":True,"minutes":90,"goals":0,"assists":0,"key_passes":1,"shots_on_target":1,"accurate_crosses":2,"successful_dribbles":3,"tackles_won":4,"interceptions":0,"clearances":0,"aerial_wins":0,"clean_sheets":0}
    table=overview_gameweek_table(pd.DataFrame([row]),"p",pd.DataFrame())
    columns=list(table); assert columns.index("Accurate Crosses") < columns.index("Successful Dribbles") < columns.index("Tackles Won")


def test_role_tactical_ui_language_has_no_tracking_claim():
    source=open("views/players.py",encoding="utf-8").read()
    assert '["Overview","Match Analysis","Role & Tactical","Advanced"]' in source
    assert "Event Activity, not tracking" in source
    assert "Successful Dribbles" in source
