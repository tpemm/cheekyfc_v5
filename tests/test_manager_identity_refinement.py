import pandas as pd
import pytest

from fantrax.live.analytics import build_live_manager_analytics
from fantrax.live.manager_identity import manager_draft_origin_audit, manager_identity_crosswalk, normalize_manager_alias
from views.live_managers import selected_manager_id


def fixtures():
    teams=pd.DataFrame([{"season_id":"2627","manager_id":"oscar-id","manager_name":"Oscar Berkshire","fantasy_team_id":"team-id","fantasy_team_name":"Berkshire’s Club"}])
    draft=pd.DataFrame([{"fantrax_player_id":f"p{i}","manager":"Berkshire's Club"} for i in range(15)])
    ownership=pd.DataFrame([{"fantrax_player_id":f"p{i}","current_manager_id":"oscar-id"} for i in range(10)]+[{"fantrax_player_id":f"a{i}","current_manager_id":"oscar-id"} for i in range(6)])
    return teams,draft,ownership


def test_oscar_apostrophe_alias_resolves_to_stable_identity():
    teams,draft,_=fixtures();row=manager_identity_crosswalk(teams,draft).iloc[0]
    assert normalize_manager_alias("Berkshire’s Club")==normalize_manager_alias("Berkshire's Club")
    assert row.manager_id=="oscar-id" and row.draft_manager_name=="Berkshire's Club" and row.match_status=="matched"


def test_oscar_retention_acquired_and_dropped_reconcile():
    teams,draft,ownership=fixtures();row=manager_draft_origin_audit(teams,draft,ownership).iloc[0]
    assert row.retained_count==10 and row.acquired_later_count==6 and row.dropped_count==5
    assert row.retained_count+row.acquired_later_count==row.current_roster_count==16
    assert row.validation_status=="valid"


def test_all_manager_crosswalk_is_one_to_one_even_with_renamed_display_team():
    teams=[];draft=[]
    for index in range(12):
        frozen=f"Club {index}'s XI";live=f"Club {index}’s XI"
        teams.append({"season_id":"2627","manager_id":f"m{index}","manager_name":f"Manager {index}","fantasy_team_id":f"t{index}","fantasy_team_name":live})
        draft.extend({"fantrax_player_id":f"p{index}-{pick}","manager":frozen} for pick in range(15))
    result=manager_identity_crosswalk(pd.DataFrame(teams),pd.DataFrame(draft))
    assert len(result)==12 and result.manager_id.nunique()==12 and result.draft_manager_name.nunique()==12
    assert result.match_status.eq("matched").all()


def test_manager_model_uses_normalized_draft_identity_for_retention_percentage():
    teams,draft,_=fixtures();players=pd.DataFrame([{"season_id":"2627","fantrax_player_id":f"p{i}","current_manager_id":"oscar-id","drafted_manager_id":"oscar-id","still_with_drafting_manager":True} for i in range(10)]+[{"season_id":"2627","fantrax_player_id":f"a{i}","current_manager_id":"oscar-id","still_with_drafting_manager":False} for i in range(6)])
    row=build_live_manager_analytics(players,teams,pd.DataFrame(),pd.DataFrame(),draft).iloc[0]
    assert row.drafted_players_retained==10 and row.current_roster_acquired_later==6 and row.draft_retention_pct==pytest.approx(100*10/15)


def test_manager_card_selection_uses_stable_id_not_display_text():
    managers=pd.DataFrame([{"manager_id":"oscar-id","fantasy_team_name":"Renamed Again"},{"manager_id":"m2","fantasy_team_name":"Other"}])
    assert selected_manager_id(managers,{"live_manager_selected_id":"oscar-id"})=="oscar-id"
    assert selected_manager_id(managers,{"live_manager_selected_id":"missing"})=="oscar-id"
