"""Provider contract for current-squad sources."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class CurrentSquadProvider(ABC):
    """Return provider-neutral current Premier League player rows."""

    name: str

    @abstractmethod
    def fetch_players(self) -> pd.DataFrame:
        """Fetch and normalize current players or raise a source error."""
