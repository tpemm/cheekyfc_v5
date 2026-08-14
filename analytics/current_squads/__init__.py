"""Reusable current Premier League squad service."""

from analytics.current_squads.fpl_provider import FPLCurrentSquadProvider
from analytics.current_squads.provider import CurrentSquadProvider

__all__ = ["CurrentSquadProvider", "FPLCurrentSquadProvider"]
