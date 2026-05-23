"""
Tests for the core hypothesis:
    Polarization predicts market volatility better than mean sentiment.
"""
import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta

from analytics.polarization import compute_polarization, polarization_to_series
from analytics.correlation import compute_correlation, find_best_correlation
from backend.models.schemas import BiasSnapshot, CorrelationResult


def make_snapshot(outlet_id: str, overall: int, emotional_tone: int = 5,
                  topic: str = "Test Topic") -> BiasSnapshot:
    return BiasSnapshot(
        topic=topic,
        outlet_id=outlet_id,
        outlet_name=outlet_id,
        scored_at=datetime.now(timezone.utc),
        emotional_tone=emotional_tone,
        framing=5, source_selection=5, loaded_language=5,
        political_stance=5, factual_density=5,
        overall=overall,
        sentiment="Neutral",
        verdict="Test verdict",
    )


class TestPolarization:

    def test_high_divergence_produces_high_std_dev(self):
        """RT=9, Reuters=2 should produce high polarization."""
        snapshots = [
            make_snapshot("rt", overall=9, emotional_tone=8),
            make_snapshot("reuters", overall=2, emotional_tone=2),
            make_snapshot("bbc", overall=3, emotional_tone=3),
        ]
        scores = compute_polarization(snapshots, "Iran US Conflict")
        overall_pol = next(s for s in scores if s.dimension == "overall")

        assert overall_pol.std_dev > 3.0
        assert overall_pol.spread == 7  # 9 - 2

    def test_consensus_produces_low_std_dev(self):
        """All outlets agreeing should produce near-zero polarization."""
        snapshots = [
            make_snapshot("nyt", overall=5),
            make_snapshot("bbc", overall=5),
            make_snapshot("reuters", overall=5),
        ]
        scores = compute_polarization(snapshots, "Test Topic")
        overall_pol = next(s for s in scores if s.dimension == "overall")

        assert overall_pol.std_dev == 0.0
        assert overall_pol.spread == 0

    def test_requires_at_least_two_outlets(self):
        """Single outlet cannot produce polarization."""
        snapshots = [make_snapshot("rt", overall=9)]
        scores = compute_polarization(snapshots, "Test Topic")
        assert scores == []


class TestCorrelation:

    def _make_series(self, values: list[float], start_days_ago: int = 30) -> pd.Series:
        dates = pd.date_range(
            end=datetime.now(timezone.utc).date(),
            periods=len(values),
            freq="D",
        )
        return pd.Series(values, index=dates)

    def test_strong_positive_correlation_detected(self):
        """Perfectly correlated series should return r≈1."""
        values = list(range(1, 21))  # 1, 2, ..., 20
        signal = self._make_series(values)
        prices = self._make_series(values)  # same series

        result = compute_correlation(
            signal=signal, prices=prices, lag_days=0,
            topic="Test", dimension="overall", market_symbol="^VIX",
        )
        assert result is not None
        assert result.pearson_r > 0.95

    def test_insufficient_data_returns_none(self):
        """Less than min_sample_size should return None."""
        signal = self._make_series([5, 6, 7])   # only 3 points
        prices = self._make_series([100, 105, 98])

        result = compute_correlation(
            signal=signal, prices=prices, lag_days=0,
            topic="Test", dimension="overall", market_symbol="CL=F",
        )
        assert result is None

    def test_significance_flag(self):
        """p_value < 0.05 should set is_significant=True."""
        # 20 perfectly correlated points — will be significant
        values = list(range(1, 21))
        signal = self._make_series(values)
        prices = self._make_series(values)

        result = compute_correlation(
            signal=signal, prices=prices, lag_days=0,
            topic="Test", dimension="overall", market_symbol="^VIX",
        )
        assert result.is_significant is True

    def test_find_best_correlation_returns_strongest(self):
        """find_best_correlation should return highest |r| significant result."""
        correlations = [
            CorrelationResult(topic="T", dimension="overall", market_symbol="CL=F",
                              market_name="Oil", lag_days=1, pearson_r=0.45,
                              p_value=0.03, sample_size=30, is_significant=True,
                              computed_at=datetime.now(timezone.utc)),
            CorrelationResult(topic="T", dimension="overall", market_symbol="^VIX",
                              market_name="VIX", lag_days=1, pearson_r=0.72,
                              p_value=0.001, sample_size=30, is_significant=True,
                              computed_at=datetime.now(timezone.utc)),
            CorrelationResult(topic="T", dimension="overall", market_symbol="GC=F",
                              market_name="Gold", lag_days=2, pearson_r=0.30,
                              p_value=0.20, sample_size=30, is_significant=False,
                              computed_at=datetime.now(timezone.utc)),
        ]
        best = find_best_correlation(correlations)
        assert best.market_symbol == "^VIX"
        assert best.pearson_r == 0.72
