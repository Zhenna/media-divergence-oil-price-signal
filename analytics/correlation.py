"""
Correlation engine.

Tests the core hypothesis:
    Maximum polarization between outlets predicts market volatility
    better than any single outlet's sentiment score.

Method:
    1. For each topic × dimension combination, compute daily polarization (std dev)
    2. For each market symbol, fetch daily closing prices
    3. Compute Pearson correlation at multiple lag values (0–7 days)
    4. Compare: does polarization correlate better than mean sentiment?

Lag interpretation:
    lag=0: same-day correlation (do markets react instantly?)
    lag=1: polarization today predicts tomorrow's price
    lag=2: polarization today predicts price in 2 days
    (negative lag would mean prices predict polarization — reverse causality)
"""
from __future__ import annotations

from datetime import datetime, timezone
import pandas as pd
import numpy as np
from scipy import stats

from backend.models.schemas import CorrelationResult
from backend.models.config import settings, POLARIZATION_DIMENSIONS, MARKET_SYMBOLS


def compute_correlation(
    signal: pd.Series,
    prices: pd.Series,
    lag_days: int,
    topic: str,
    dimension: str,
    market_symbol: str,
) -> CorrelationResult | None:
    """
    Compute Pearson correlation between a polarization signal
    and a market price series at a given lag.

    lag_days > 0 means: does today's polarization predict future prices?
    (price series is shifted backwards by lag_days)
    """
    # Align on dates
    price_lagged = prices.shift(-lag_days)
    combined = pd.concat([signal, price_lagged], axis=1).dropna()
    combined.columns = ["signal", "price"]

    if len(combined) < settings.min_sample_size:
        return None

    r, p = stats.pearsonr(combined["signal"], combined["price"])

    return CorrelationResult(
        topic=topic,
        dimension=dimension,
        market_symbol=market_symbol,
        market_name=MARKET_SYMBOLS.get(market_symbol, market_symbol),
        lag_days=lag_days,
        pearson_r=round(float(r), 4),
        p_value=round(float(p), 6),
        sample_size=len(combined),
        is_significant=float(p) < settings.significance_threshold,
        computed_at=datetime.now(timezone.utc),
    )


def compute_all_correlations(
    polarization_records: list[dict],
    price_records: list[dict],
    topic: str,
) -> list[CorrelationResult]:
    """
    Compute correlations for all dimension × symbol × lag combinations.

    Args:
        polarization_records: from DB, already filtered by topic
        price_records: from DB, all symbols
        topic: topic name

    Returns:
        All computed CorrelationResult objects, sorted by |pearson_r| desc
    """
    from analytics.polarization import polarization_to_series

    # Build price dataframe: index=date, columns=symbols
    price_df = _build_price_df(price_records)
    if price_df.empty:
        return []

    results = []

    for dimension in POLARIZATION_DIMENSIONS:
        signal = polarization_to_series(polarization_records, dimension)
        if signal.empty:
            continue

        for symbol in price_df.columns:
            prices = price_df[symbol].dropna()

            for lag in settings.correlation_lag_days:
                result = compute_correlation(
                    signal=signal,
                    prices=prices,
                    lag_days=lag,
                    topic=topic,
                    dimension=dimension,
                    market_symbol=symbol,
                )
                if result:
                    results.append(result)

    # Sort by absolute correlation strength
    results.sort(key=lambda r: abs(r.pearson_r), reverse=True)
    return results


def find_best_correlation(
    correlations: list[CorrelationResult],
    market_symbol: str | None = None,
) -> CorrelationResult | None:
    """Return the strongest significant correlation, optionally filtered by symbol."""
    filtered = [
        r for r in correlations
        if r.is_significant and (market_symbol is None or r.market_symbol == market_symbol)
    ]
    return filtered[0] if filtered else None


def polarization_vs_sentiment_comparison(
    polarization_records: list[dict],
    sentiment_records: list[dict],
    price_records: list[dict],
    topic: str,
    market_symbol: str = "^VIX",
) -> dict:
    """
    The core hypothesis test:
    Compare polarization (std dev) vs mean sentiment as predictors of VIX.

    Returns a dict with both correlation results for display in the dashboard.
    """
    from analytics.polarization import polarization_to_series

    price_df = _build_price_df(price_records)
    if price_df.empty or market_symbol not in price_df.columns:
        return {}

    prices = price_df[market_symbol].dropna()
    results = {}

    # Polarization signal (std dev of outlet scores)
    pol_signal = polarization_to_series(polarization_records, "overall")
    if not pol_signal.empty:
        best_pol = None
        for lag in settings.correlation_lag_days:
            r = compute_correlation(pol_signal, prices, lag, topic, "overall", market_symbol)
            if r and (best_pol is None or abs(r.pearson_r) > abs(best_pol.pearson_r)):
                best_pol = r
        results["polarization"] = best_pol

    # Mean sentiment signal (single outlet average — the baseline to beat)
    if sentiment_records:
        mean_signal = _build_mean_sentiment_series(sentiment_records)
        if not mean_signal.empty:
            best_sent = None
            for lag in settings.correlation_lag_days:
                r = compute_correlation(mean_signal, prices, lag, topic, "mean_sentiment", market_symbol)
                if r and (best_sent is None or abs(r.pearson_r) > abs(best_sent.pearson_r)):
                    best_sent = r
            results["mean_sentiment"] = best_sent

    return results


def _build_price_df(price_records: list[dict]) -> pd.DataFrame:
    if not price_records:
        return pd.DataFrame()
    df = pd.DataFrame(price_records)
    df["price_date"] = pd.to_datetime(df["price_date"])
    pivot = df.pivot_table(index="price_date", columns="symbol", values="close_price")
    return pivot.sort_index()


def _build_mean_sentiment_series(sentiment_records: list[dict]) -> pd.Series:
    """Average overall score across all outlets per day — the baseline comparator."""
    if not sentiment_records:
        return pd.Series(dtype=float)
    df = pd.DataFrame(sentiment_records)
    df["scored_at"] = pd.to_datetime(df["scored_at"]).dt.normalize()
    return df.groupby("scored_at")["overall"].mean()
