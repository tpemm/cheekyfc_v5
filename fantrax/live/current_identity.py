"""Current-season identity and display-name rules.

Provider matches are deliberately conservative: only one exact normalized
name-and-club candidate is deterministic.  Ambiguous candidates stay unresolved.
"""
from __future__ import annotations

import re
import unicodedata

import pandas as pd


def normalized_name(value: object) -> str:
    if pd.isna(value):
        return ""
    ascii_name = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", ascii_name.casefold())


def nonblank(series: pd.Series) -> pd.Series:
    value = series.astype("string").str.strip()
    return value.mask(value.eq("") | value.str.casefold().isin(("nan", "none", "<na>")))


def display_names(canonical: pd.Series, fantrax: pd.Series, provider: pd.Series | None = None) -> pd.Series:
    """Canonical approved name -> current Fantrax name -> provider fallback."""
    result = nonblank(canonical).combine_first(nonblank(fantrax))
    return result.combine_first(nonblank(provider)) if provider is not None else result


def deterministic_candidates(provider: pd.DataFrame, current: pd.DataFrame) -> pd.DataFrame:
    """Return unique exact normalized-name + canonical-club matches only."""
    left = provider.copy()
    right = current.copy()
    left["_identity_name"] = left["provider_name"].map(normalized_name)
    right["_identity_name"] = right["fantrax_name"].map(normalized_name)
    candidates = left.merge(right, on=["_identity_name", "club_id"], how="left")
    counts = candidates.groupby("provider_id", dropna=False)["fantrax_player_id"].transform("count")
    candidates["identity_status"] = counts.map(lambda n: "DETERMINISTIC" if n == 1 else "AMBIGUOUS" if n > 1 else "UNRESOLVED")
    return candidates
