"""Deterministic live manager identity and draft-origin reconciliation."""
from __future__ import annotations
import re
import unicodedata
import pandas as pd


def normalize_manager_alias(value:object)->str:
    if pd.isna(value):return ""
    text=unicodedata.normalize("NFKC",str(value)).casefold()
    text=text.translate(str.maketrans({"’":"'","‘":"'","`":"'","´":"'"}))
    return re.sub(r"[^a-z0-9]+","",text)


def manager_identity_crosswalk(teams:pd.DataFrame,draft:pd.DataFrame)->pd.DataFrame:
    rows=[];draft_names=draft.get("manager",pd.Series(dtype=object)).dropna().astype(str).drop_duplicates().tolist()
    by_alias={normalize_manager_alias(name):name for name in draft_names}
    for team in teams.to_dict("records"):
        candidates=(team.get("manager_name"),team.get("fantasy_team_name"));match=next((by_alias.get(normalize_manager_alias(value)) for value in candidates if normalize_manager_alias(value) in by_alias),None)
        rows.append({"season_id":team.get("season_id"),"manager_id":team.get("manager_id"),"manager_name":team.get("manager_name"),"fantasy_team_id":team.get("fantasy_team_id"),"fantasy_team_name":team.get("fantasy_team_name"),"draft_manager_name":match,"normalized_alias":normalize_manager_alias(match or candidates[0]),"match_status":"matched" if match else "unresolved","source":"Fantrax league teams + frozen draft results"})
    return pd.DataFrame(rows)


def draft_manager_id_lookup(teams:pd.DataFrame,draft:pd.DataFrame)->dict[str,str]:
    crosswalk=manager_identity_crosswalk(teams,draft)
    return {normalize_manager_alias(row.draft_manager_name):str(row.manager_id) for row in crosswalk.itertuples() if row.match_status=="matched"}


def manager_draft_origin_audit(teams:pd.DataFrame,draft:pd.DataFrame,ownership:pd.DataFrame)->pd.DataFrame:
    crosswalk=manager_identity_crosswalk(teams,draft);rows=[]
    draft_ids=draft.copy();draft_ids["fantrax_player_id"]=draft_ids.get("fantrax_player_id",pd.Series(dtype=object)).astype("string")
    own=ownership.copy();own["fantrax_player_id"]=own.get("fantrax_player_id",pd.Series(dtype=object)).astype("string")
    for identity in crosswalk.to_dict("records"):
        manager_id=str(identity.get("manager_id"));draft_name=identity.get("draft_manager_name")
        drafted=draft_ids[draft_ids.get("manager",pd.Series(index=draft_ids.index,dtype=object)).astype(str).eq(str(draft_name))] if draft_name else draft_ids.iloc[0:0]
        current=own[own.get("current_manager_id",pd.Series(index=own.index,dtype=object)).astype(str).eq(manager_id)]
        drafted_set=set(drafted["fantrax_player_id"].dropna());current_set=set(current["fantrax_player_id"].dropna());retained=len(drafted_set&current_set);acquired=len(current_set-drafted_set);dropped=len(drafted_set-current_set)
        unresolved=int(drafted["fantrax_player_id"].isna().sum()) if not drafted.empty else 0;valid=identity["match_status"]=="matched" and retained+acquired==len(current_set)
        rows.append({**identity,"drafted_count":len(drafted_set),"retained_count":retained,"acquired_later_count":acquired,"dropped_count":dropped,"current_roster_count":len(current_set),"unresolved_count":unresolved,"validation_status":"valid" if valid else "review","note":"retained + acquired later reconciles to current roster" if valid else "manager identity or roster accounting requires review"})
    return pd.DataFrame(rows)
