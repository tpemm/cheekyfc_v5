import json
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from fantrax.live.event_imports import IdentityBridge, normalize, merge_events, parse_slot, parse_bid, import_exports, read_export


def bridge():
    players=pd.DataFrame([{"fantrax_player_id":"078i7","player_name":"Player A","club":"LIV"},
                          {"fantrax_player_id":"06ew2","player_name":"Player B","club":"NEW"}])
    teams=pd.DataFrame([{"manager_id":"w2mnqywumrp1z5vp","fantasy_team_id":"w2mnqywumrp1z5vp","manager_name":"Manager A"}])
    return IdentityBridge(players,teams,pd.DataFrame())


def row(**overrides):
    return {"Player":"Player A","Team":"LIV","Position":"D","Team.1":"Manager A",
            "Type":"Claim","Bid/Win":"102.00/25.00","Pr":"1",
            "Date (CDT)":"Wed Sep 9, 2026, 3:39PM","Gameweek":"4",**overrides}


def test_transactions_raw_identity_types_groups_and_timezone():
    source=pd.DataFrame([row(),row(Player="Player B",Team="NEW",Type="Drop"),row(Type="Lineup Change"),row(Type="Other")])
    before=source.copy(deep=True);events=normalize(source,"transaction",bridge())
    assert events.normalized_transaction_type.tolist()==["CLAIM","DROP","LINEUP_CHANGE","UNKNOWN"]
    assert events.raw_transaction_type.tolist()==source.Type.tolist()
    assert events.transaction_group_id.nunique()==1 and events.transaction_event_id.nunique()==4
    assert events.player_id.tolist()[:2]==["078i7","06ew2"]
    assert events.manager_id.eq("w2mnqywumrp1z5vp").all()
    assert events.event_timestamp.iloc[0]=="2026-09-09T15:39:00-05:00"
    assert events.raw_player_name.iloc[0]=="Player A" and events.raw_manager_name.iloc[0]=="Manager A"
    assert events.raw_bid_win.iloc[0]=="102.00/25.00"
    assert events.bid_component_1.iloc[0]==102 and events.bid_component_2.iloc[0]==25
    assert_frame_equal(source,before)


def test_repeated_imports_preserve_actions_and_identical_rows_without_duplication():
    raw=pd.DataFrame([row(),row(),row(Type="Drop")])
    first=normalize(raw,"transaction",bridge());again=normalize(raw.iloc[::-1],"transaction",bridge())
    assert set(first.transaction_event_id)==set(again.transaction_event_id)
    assert len(first)==3 and first.transaction_event_id.nunique()==3
    merged,duplicates=merge_events(first,again,"transaction")
    assert len(merged)==3 and duplicates==3


@pytest.mark.parametrize("start,end",[("Active","Reserve"),("Reserve","Active"),("Inj Res","Active"),("Reserve, F","Active, M"),("D","M")])
def test_lineup_raw_states_and_slots(start,end):
    frame=pd.DataFrame([row(**{"From":start,"To":end})])
    events=normalize(frame,"lineup",bridge());event=events.iloc[0]
    assert event.raw_from==start and event.raw_to==end
    assert (event.from_roster_state,event.from_slot)==parse_slot(start)[:2]
    assert (event.to_roster_state,event.to_slot)==parse_slot(end)[:2]
    assert event.quality_flags==""


def test_unknown_identity_and_malformed_values_retained():
    frame=pd.DataFrame([row(Player="No match",**{"Team.1":"Unknown","Date (CDT)":"bad","Gameweek":"bad","Bid/Win":"?","Pr":"?"})])
    result=normalize(frame,"transaction",bridge()).iloc[0]
    assert pd.isna(result.player_id) and pd.isna(result.manager_id)
    assert result.identity_status=="REVIEW" and result.raw_player_name=="No match"
    assert "TIMESTAMP_PARSE_FAILURE" in result.quality_flags and "BID_WIN_UNPARSED" in result.quality_flags
    assert pd.isna(result.transaction_group_id)
    assert parse_slot("Active, unsupported")==("ACTIVE",None,"PARTIAL")
    assert parse_bid("")== (None,None,"EMPTY")


def test_ambiguous_alias_never_silently_selects_identity():
    players=pd.DataFrame([{"fantrax_player_id":"a","player_name":"Same","club":"LIV"},
                          {"fantrax_player_id":"b","player_name":"Same","club":"NEW"}])
    b=IdentityBridge(players,pd.DataFrame(),pd.DataFrame())
    assert b.resolve("Same","LIV","Unknown")["player_id"]=="a"
    assert b.resolve("Same","UNK","Unknown")["player_identity_status"]=="AMBIGUOUS"


def test_real_schema_file_import_is_idempotent_and_does_not_touch_other_products(tmp_path):
    tx=tmp_path/"claims.csv";lineup=tmp_path/"lineup.csv"
    pd.DataFrame([row()]).rename(columns={"Team.1":"Team"}).to_csv(tx,index=False)
    pd.DataFrame([{k:v for k,v in row(**{"From":"Reserve","To":"Active"}).items() if k not in {"Type","Bid/Win","Pr"}}]).rename(columns={"Team.1":"Team"}).to_csv(lineup,index=False)
    model=tmp_path/"data/models/season_2627";model.mkdir(parents=True)
    untouched={name:b"unchanged" for name in ("current_rosters_2627.csv","player_ownership_2627.csv")}
    for name,content in untouched.items():(model/name).write_bytes(content)
    first=import_exports(tx,lineup,root=tmp_path);second=import_exports(tx,lineup,root=tmp_path)
    assert first["transaction"]["events_normalized"]==1
    assert second["transaction"]["duplicate_events_removed"]==1
    assert second["lineup"]["total_events_stored"]==1
    for name,content in untouched.items():assert (model/name).read_bytes()==content
    assert json.loads((tmp_path/"data/quality/season_2627/event_import_quality_2627.json").read_text())["transaction"]["player_unresolved"]==1
    previous=(model/"transaction_events_2627.csv").read_bytes()
    lineup.write_text("Player,Team\nbroken\n")
    with pytest.raises(ValueError,match="Malformed CSV row"):import_exports(tx,lineup,root=tmp_path)
    assert (model/"transaction_events_2627.csv").read_bytes()==previous


def test_event_products_are_registered_separately():
    from core.services.dataset_registry import DatasetRegistry
    registry=DatasetRegistry()
    for key in ("transaction_events","lineup_events"):
        definition=registry.get(key)
        assert definition.producer=="fantrax.live.event_imports"
