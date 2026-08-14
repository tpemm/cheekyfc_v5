"""Reusable analytics formulas shared across builders."""
from __future__ import annotations
import math
from collections.abc import Iterable

def safe_ratio(numerator: float, denominator: float, default: float = 0.0) -> float:
    try:
        n, d = float(numerator), float(denominator)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(n) or not math.isfinite(d) or d == 0:
        return default
    return n / d

def lineup_efficiency(actual_points: float, optimal_points: float) -> float:
    return 100.0 * safe_ratio(actual_points, optimal_points)

def points_missed(actual_points: float, optimal_points: float) -> float:
    return max(float(optimal_points) - float(actual_points), 0.0)

def mean(values: Iterable[float]) -> float:
    cleaned=[]
    for value in values:
        try:
            number=float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number): cleaned.append(number)
    return sum(cleaned)/len(cleaned) if cleaned else 0.0
