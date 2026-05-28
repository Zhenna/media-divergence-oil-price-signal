"""
Polarization engine.

Core hypothesis:
    Maximum polarization between outlets predicts market volatility
    better than any single outlet's sentiment score.

Polarization is measured as the standard deviation of outlet scores
across a given bias dimension. Higher std dev = more narrative divergence.

This is fundamentally different from sentiment analysis:
- Sentiment: how negative is outlet X?
- Polarization: how far apart are outlets X, Y, Z from each other?

When all outlets agree (low polarization), the situation is clear.
When outlets diverge sharply (high polarization), the situation is contested —
and contested geopolitical situations drive market uncertainty.
"""
from __future__ import annotations

from datetime import datetime, timezone
import numpy as np
import pandas as pd

from backend.models.schemas import BiasSnapshot, PolarizationScore
from backend.models.config import POLARIZATION_DIMENSIONS


def compute_polarization(
    snapshots: list[BiasSnapshot],
    topic: str,
    measured_at: datetime | None = None,
) -> list[PolarizationScore]:
    """
    Compute polarization scores from a set of outlet snapshots.

    For each tracked dimension, computes:
    - mean score across outlets
    - std deviation (the polarization signal)
    - min/max spread

    Args:
        snapshots: bias snapshots for a single topic at a single time point
        topic: topic name
        measured_at: timestamp, defaults to now

    Returns:
        List of PolarizationScore objects, one per dimension
    """
    if not snapshots:
        return []

    measured_at = measured_at or datetime.now(timezone.utc)
    results = []

    for dimension in POLARIZATION_DIMENSIONS:
        scores = [getattr(s, dimension) for s in snapshots if hasattr(s, dimension)]
        if len(scores) < 2:
            continue

        arr = np.array(scores, dtype=float)
        results.append(PolarizationScore(
            topic=topic,
            measured_at=measured_at,
            dimension=dimension,
            mean_score=round(float(np.mean(arr)), 4),
            std_dev=round(float(np.std(arr)), 4),
            min_score=float(np.min(arr)),
            max_score=float(np.max(arr)),
            outlet_count=len(scores),
            spread=round(float(np.max(arr) - np.min(arr)), 4),
        ))

    return results


def polarization_to_series(
    polarization_records: list[dict],
    dimension: str = "overall",
) -> pd.Series:
    """
    Convert stored polarization records to a pandas Series indexed by date.
    Used as input to the correlation engine.

    Args:
        polarization_records: list of dicts from DB query
        dimension: which bias dimension to use

    Returns:
        pd.Series with DatetimeIndex and std_dev values
    """
    filtered = [r for r in polarization_records if r["dimension"] == dimension]
    if not filtered:
        return pd.Series(dtype=float)

    df = pd.DataFrame(filtered)
    df["date"] = pd.to_datetime(df["measured_at"]).dt.normalize()
    
    # Deduplicate — take mean if multiple runs on same day
    daily = df.groupby("date")["std_dev"].mean()
    return daily.sort_index()

    # df["measured_at"] = pd.to_datetime(df["measured_at"]).dt.normalize()
    # # If multiple readings per day, take the last one
    # df = df.sort_values("measured_at").groupby("measured_at")["std_dev"].last()
    # return df
