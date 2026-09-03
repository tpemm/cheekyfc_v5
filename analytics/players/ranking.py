"""Shared numeric ranking rules for live player presentation paths."""
from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.players.comparison import primary_position


def metric_ranking(frame: pd.DataFrame, field: str, *, peer_basis: str = "League") -> pd.DataFrame:
    """Return one missing-safe value, rank, percentile, and peer-count universe."""
    values = pd.to_numeric(frame.get(field, pd.Series(np.nan, index=frame.index)), errors="coerce")
    result = pd.DataFrame(index=frame.index)
    result["value"] = values
    result["missing"] = values.isna()
    if peer_basis == "Position":
        positions = frame.apply(primary_position, axis=1)
        grouped = values.groupby(positions)
        result["rank"] = grouped.rank(method="min", ascending=False, na_option="keep")
        result["percentile"] = grouped.rank(method="average", pct=True, ascending=True, na_option="keep").mul(100)
        result["peer_count"] = grouped.transform("count").astype("Int64")
    else:
        result["rank"] = values.rank(method="min", ascending=False, na_option="keep")
        result["percentile"] = values.rank(method="average", pct=True, ascending=True, na_option="keep").mul(100)
        result["peer_count"] = int(values.count())
    return result


def sort_by_metric(frame: pd.DataFrame, field: str, ascending: bool) -> pd.DataFrame:
    """Stable numeric ordering using the same values and missing rules as ranking."""
    prepared = metric_ranking(frame, field)
    result = frame.assign(_metric_missing=prepared["missing"], _metric_value=prepared["value"])
    return result.sort_values(
        ["_metric_missing", "_metric_value"],
        ascending=[True, ascending],
        kind="stable",
        na_position="last",
    ).drop(columns=["_metric_missing", "_metric_value"])
