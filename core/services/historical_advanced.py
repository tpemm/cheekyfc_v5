"""Cross-season access and canonical identity bridge for supplemental advanced models."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import pandas as pd

from core.services.data_manager import DataManager,DatasetNotFoundError,DatasetValidationError,UnsupportedFormatError

HISTORICAL_ADVANCED_SEASON="2526"
# Explicit canonical bridge for legacy advanced IDs. Identity is used otherwise.
CURRENT_TO_HISTORICAL_CLUB={"afc_bournemouth":"bournemouth","brighton_hove_albion":"brighton"}


def historical_club_id(current_club_id:str)->str:
    return CURRENT_TO_HISTORICAL_CLUB.get(str(current_club_id),str(current_club_id))


def load_historical_advanced_frame(data:DataManager,key:str,season:str=HISTORICAL_ADVANCED_SEASON,ui:Any|None=None)->pd.DataFrame:
    """Load supplemental historical models from their registered working root.

    Finalized core history defaults to the snapshot namespace; supplemental advanced
    products deliberately remain under data/models and therefore request working.
    """
    try:result=data.load_frame(key,season,"working")
    except DatasetNotFoundError:return pd.DataFrame()
    except (DatasetValidationError,UnsupportedFormatError) as exc:
        if ui is not None:ui.warning(str(exc))
        return pd.DataFrame()
    return result.data.copy() if isinstance(result.data,pd.DataFrame) else pd.DataFrame()


@dataclass(frozen=True)
class HistoricalTeamAdvanced:
    current_club_id:str
    historical_club_id:str
    historical_eligible:bool
    formations:pd.DataFrame
    fantasy_allowed:pd.DataFrame
    playstyle:pd.DataFrame
    role_usage:pd.DataFrame
    set_pieces:pd.DataFrame

    @property
    def status(self)->str:
        if not self.historical_eligible:return "NO_HISTORICAL_EPL_DATA"
        return "AVAILABLE" if all(not x.empty for x in (self.formations,self.fantasy_allowed,self.playstyle,self.role_usage,self.set_pieces)) else "HISTORICAL_LOOKUP_FAILED"


def get_historical_team_advanced(data:DataManager,current_club_id:str,season:str=HISTORICAL_ADVANCED_SEASON,ui:Any|None=None)->HistoricalTeamAdvanced:
    historical_id=historical_club_id(current_club_id) if season==HISTORICAL_ADVANCED_SEASON else str(current_club_id)
    formations=load_historical_advanced_frame(data,"team_formation_profile",season,ui);allowed=load_historical_advanced_frame(data,"historical_fantasy_allowed_ranked",season,ui);style=load_historical_advanced_frame(data,"team_playstyle_profile",season,ui);roles=load_historical_advanced_frame(data,"formation_player_usage",season,ui);pieces=load_historical_advanced_frame(data,"team_set_piece_hierarchy",season,ui)
    eligible_ids=set(formations.get("club_id",pd.Series(dtype=object)).astype(str))|set(style.get("club_id",pd.Series(dtype=object)).astype(str))
    return HistoricalTeamAdvanced(str(current_club_id),historical_id,historical_id in eligible_ids,formations[formations.get("club_id",pd.Series(index=formations.index,dtype=object)).astype(str).eq(historical_id)],allowed[allowed.get("opponent_id",pd.Series(index=allowed.index,dtype=object)).astype(str).eq(historical_id)],style[style.get("club_id",pd.Series(index=style.index,dtype=object)).astype(str).eq(historical_id)],roles[roles.get("club_id",pd.Series(index=roles.index,dtype=object)).astype(str).eq(historical_id)],pieces[pieces.get("club_id",pd.Series(index=pieces.index,dtype=object)).astype(str).eq(historical_id)])


def get_historical_player_advanced(data:DataManager,fantrax_player_id:str,season:str=HISTORICAL_ADVANCED_SEASON,ui:Any|None=None,include_pitch:bool=True)->dict[str,pd.DataFrame]:
    supplemental=load_historical_advanced_frame(data,"supplemental_player_match",season,ui);selected=supplemental[supplemental.get("fantrax_player_id",pd.Series(index=supplemental.index,dtype=object)).astype(str).eq(str(fantrax_player_id))]
    canonical=None if selected.empty else str(selected.canonical_player_id.iloc[0])
    def player_rows(key:str)->pd.DataFrame:
        frame=load_historical_advanced_frame(data,key,season,ui)
        return frame.iloc[0:0] if canonical is None else frame[frame.get("canonical_player_id",pd.Series(index=frame.index,dtype=object)).astype(str).eq(canonical)]
    return {"supplemental":selected,"profile":player_rows("player_advanced_profile"),"roles":player_rows("player_role_usage"),"set_pieces":player_rows("player_set_piece_usage"),"pitch":player_rows("player_pitch_events") if include_pitch else pd.DataFrame()}
