"""
Hypothesis engine.

Tests all 5 hypotheses against accumulated data.
Called daily after pipeline completes.

H1 — Confirmatory:  Polarization vs VIX
H2 — Exploratory:   Iran divergence vs Oil
H3 — Exploratory:   Consensus collapse vs VIX spike
H4 — Exploratory:   RT Ukraine as lagging gas price indicator
H5 — Exploratory:   Al Jazeera vs BBC as oil predictor

Methodology:
- H1 is confirmatory: tested once, standard p < 0.05
- H2-H5 are exploratory: Bonferroni correction applied (p < 0.01)
- Negative lag in H4 tests reverse causality (prices → media)
- Results labelled clearly: SUPPORTED / NOT SUPPORTED / INSUFFICIENT DATA
"""
from __future__ import annotations

from datetime import datetime, timezone
import pandas as pd
import numpy as np
from scipy import stats

from backend.models.config import HYPOTHESES, settings
from backend.services.db import (
    get_polarization_records,
    get_price_records,
    get_bias_records,
    get_consensus_fact_counts,
)
from analytics.polarization import polarization_to_series


async def test_all_hypotheses() -> list[dict]:
    """Run all 5 hypothesis tests. Returns results list for storage."""
    results = []
    for h_id, h_config in HYPOTHESES.items():
        print(f"[Hypothesis] Testing {h_id}: {h_config['name']}...")
        try:
            result = await _test_hypothesis(h_id, h_config)
            results.append(result)
            status = "SUPPORTED" if result["supported"] else (
                "NOT SUPPORTED" if result["tested"] else "INSUFFICIENT DATA"
            )
            print(f"[Hypothesis] {h_id}: {status}")
        except Exception as e:
            print(f"[Hypothesis] {h_id}: error — {e}")
            results.append(_error_result(h_id, h_config, str(e)))
    return results


async def _test_hypothesis(h_id: str, h: dict) -> dict:
    """Route to correct test function based on signal type."""
    signal_type = h["signal"]

    if signal_type == "polarization_std_dev":
        return await _test_polarization_hypothesis(h_id, h)

    elif signal_type == "consensus_fact_count":
        return await _test_consensus_hypothesis(h_id, h)

    elif signal_type == "outlet_score":
        return await _test_outlet_score_hypothesis(h_id, h)

    elif signal_type == "outlet_comparison":
        return await _test_outlet_comparison_hypothesis(h_id, h)

    else:
        raise ValueError(f"Unknown signal type: {signal_type}")


async def _test_polarization_hypothesis(h_id: str, h: dict) -> dict:
    """
    H1 and H2: test polarization std_dev vs market price.
    """
    topic = h["topics"][0]
    pol_records = await get_polarization_records(topic)
    price_records = await get_price_records(symbols=[h["market"]])

    pol_signal = polarization_to_series(pol_records, h["dimension"])
    price_series = _records_to_series(price_records, h["market"])

    if len(pol_signal) < settings.min_sample_size:
        return _insufficient_result(h_id, h, len(pol_signal))

    best = _best_correlation(
        pol_signal, price_series, h["lag_days"], h["significance_threshold"]
    )

    # H1 additionally compares against mean sentiment
    comparison = None
    if h_id == "H1":
        bias_records = await get_bias_records(topic)
        mean_sentiment = _mean_sentiment_series(bias_records)
        sentiment_best = _best_correlation(
            mean_sentiment, price_series, h["lag_days"], h["significance_threshold"]
        )
        comparison = {
            "polarization_r": best["pearson_r"] if best else None,
            "sentiment_r": sentiment_best["pearson_r"] if sentiment_best else None,
            "polarization_wins": (
                best is not None
                and sentiment_best is not None
                and abs(best["pearson_r"]) > abs(sentiment_best["pearson_r"])
            ),
        }

    supported = (
        best is not None
        and best["is_significant"]
        and (comparison is None or comparison.get("polarization_wins", True))
    )

    return {
        "hypothesis_id": h_id,
        "name": h["name"],
        "type": h["type"],
        "description": h["description"],
        "tested": True,
        "supported": supported,
        "best_correlation": best,
        "comparison": comparison,
        "sample_size": len(pol_signal),
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "verdict": _verdict(h_id, supported, best, comparison),
    }


async def _test_consensus_hypothesis(h_id: str, h: dict) -> dict:
    """
    H3: test consensus fact count vs VIX spike.
    Low consensus fact count (< 2) precedes VIX spike within 3 days.
    """
    consensus_records = await get_consensus_fact_counts()
    price_records = await get_price_records(symbols=["^VIX"])

    if not consensus_records or len(consensus_records) < settings.min_sample_size:
        return _insufficient_result(h_id, h, len(consensus_records) if consensus_records else 0)

    # Build binary signal: 1 if consensus_facts < 2, else 0
    df = pd.DataFrame(consensus_records)
    df["date"] = pd.to_datetime(df["scored_at"]).dt.normalize()
    df = df.groupby("date")["consensus_fact_count"].mean()
    low_consensus = (df < 2).astype(float)

    price_series = _records_to_series(price_records, "^VIX")

    best = _best_correlation(
        low_consensus, price_series, h["lag_days"], h["significance_threshold"]
    )
    supported = best is not None and best["is_significant"] and best["pearson_r"] > 0

    return {
        "hypothesis_id": h_id,
        "name": h["name"],
        "type": h["type"],
        "description": h["description"],
        "tested": True,
        "supported": supported,
        "best_correlation": best,
        "sample_size": len(low_consensus),
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "verdict": _verdict(h_id, supported, best),
    }


async def _test_outlet_score_hypothesis(h_id: str, h: dict) -> dict:
    """
    H4: test a single outlet's score vs market price.
    Supports negative lag (reverse causality test).
    """
    topic = h["topics"][0]
    bias_records = await get_bias_records(topic)
    price_records = await get_price_records(symbols=[h["market"]])

    # Filter to specific outlet
    outlet_records = [r for r in bias_records if r["outlet_id"] == h["outlet"]]
    if len(outlet_records) < settings.min_sample_size:
        return _insufficient_result(h_id, h, len(outlet_records))

    df = pd.DataFrame(outlet_records)
    df["date"] = pd.to_datetime(df["scored_at"]).dt.normalize()
    signal = df.groupby("date")[h["dimension"]].mean()

    price_series = _records_to_series(price_records, h["market"])

    # Test both positive and negative lags
    best = _best_correlation(
        signal, price_series, h["lag_days"], h["significance_threshold"]
    )

    # H4 is "supported" if the best lag is NEGATIVE (prices lead media)
    supported = (
        best is not None
        and best["is_significant"]
        and best["lag_days"] < 0
    )

    return {
        "hypothesis_id": h_id,
        "name": h["name"],
        "type": h["type"],
        "description": h["description"],
        "tested": True,
        "supported": supported,
        "best_correlation": best,
        "sample_size": len(signal),
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "verdict": _verdict(h_id, supported, best),
    }


async def _test_outlet_comparison_hypothesis(h_id: str, h: dict) -> dict:
    """
    H5: compare two outlets' predictive power on same market.
    Al Jazeera vs BBC on Iran → Oil.
    """
    topic = h["topics"][0]
    bias_records = await get_bias_records(topic)
    price_records = await get_price_records(symbols=[h["market"]])
    price_series = _records_to_series(price_records, h["market"])

    outlet_results = {}
    for outlet_id in h["outlets"]:
        outlet_records = [r for r in bias_records if r["outlet_id"] == outlet_id]
        if len(outlet_records) < settings.min_sample_size:
            continue
        df = pd.DataFrame(outlet_records)
        df["date"] = pd.to_datetime(df["scored_at"]).dt.normalize()
        signal = df.groupby("date")[h["dimension"]].mean()
        best = _best_correlation(signal, price_series, h["lag_days"], h["significance_threshold"])
        outlet_results[outlet_id] = best

    if len(outlet_results) < 2:
        return _insufficient_result(h_id, h, len(outlet_results))

    outlet_a, outlet_b = h["outlets"][0], h["outlets"][1]
    r_a = abs(outlet_results[outlet_a]["pearson_r"]) if outlet_results.get(outlet_a) else 0
    r_b = abs(outlet_results[outlet_b]["pearson_r"]) if outlet_results.get(outlet_b) else 0

    # H5 supported if Al Jazeera (first outlet) has stronger correlation than BBC
    supported = r_a > r_b and outlet_results.get(outlet_a, {}).get("is_significant", False)

    return {
        "hypothesis_id": h_id,
        "name": h["name"],
        "type": h["type"],
        "description": h["description"],
        "tested": True,
        "supported": supported,
        "outlet_correlations": outlet_results,
        "winner": outlet_a if r_a > r_b else outlet_b,
        "sample_size": min(len(bias_records), settings.min_sample_size),
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "verdict": _verdict_comparison(h_id, outlet_a, outlet_b, r_a, r_b, outlet_results),
    }


# ── Helpers ────────────────────────────────────────────────────────────────────

def _records_to_series(records: list[dict], symbol: str) -> pd.Series:
    if not records:
        return pd.Series(dtype=float)
    df = pd.DataFrame(records)
    df = df[df["symbol"] == symbol] if "symbol" in df.columns else df
    df["price_date"] = pd.to_datetime(df["price_date"])
    return df.set_index("price_date")["close_price"].sort_index()


def _mean_sentiment_series(records: list[dict]) -> pd.Series:
    if not records:
        return pd.Series(dtype=float)
    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["scored_at"]).dt.normalize()
    return df.groupby("date")["overall"].mean()


def _best_correlation(
    signal: pd.Series,
    prices: pd.Series,
    lag_days: list[int],
    threshold: float,
) -> dict | None:
    best = None
    for lag in lag_days:
        price_lagged = prices.shift(-lag)
        combined = pd.concat([signal, price_lagged], axis=1).dropna()
        combined.columns = ["signal", "price"]
        if len(combined) < settings.min_sample_size:
            continue
        r, p = stats.pearsonr(combined["signal"], combined["price"])
        result = {
            "pearson_r": round(float(r), 4),
            "p_value": round(float(p), 6),
            "lag_days": lag,
            "sample_size": len(combined),
            "is_significant": float(p) < threshold,
        }
        if best is None or abs(r) > abs(best["pearson_r"]):
            best = result
    return best


def _verdict(h_id: str, supported: bool, best: dict | None, comparison: dict | None = None) -> str:
    if not best:
        return "Insufficient data to test this hypothesis yet."
    r, lag, p = best["pearson_r"], best["lag_days"], best["p_value"]
    if h_id == "H1" and comparison:
        if comparison.get("polarization_wins"):
            return (
                f"Polarization (r={r}, lag={lag}d, p={p:.3f}) correlates with VIX "
                f"more strongly than mean sentiment (r={comparison['sentiment_r']:.3f}). "
                f"Hypothesis supported."
            )
        else:
            return (
                f"Mean sentiment (r={comparison['sentiment_r']:.3f}) correlates with VIX "
                f"as strongly as polarization (r={r}). Hypothesis not supported."
            )
    if supported:
        lag_str = f"{abs(lag)} days before" if lag > 0 else (
            f"{abs(lag)} days after" if lag < 0 else "same day"
        )
        return f"Supported: r={r}, p={p:.3f}, best at lag {lag_str}."
    return f"Not supported: strongest correlation r={r} (p={p:.3f}) did not meet significance threshold."


def _verdict_comparison(h_id, outlet_a, outlet_b, r_a, r_b, results) -> str:
    winner = outlet_a if r_a > r_b else outlet_b
    loser = outlet_b if r_a > r_b else outlet_a
    sig = results.get(winner, {}).get("is_significant", False)
    return (
        f"{winner.title()} (r={max(r_a,r_b):.3f}) correlates more strongly with oil "
        f"than {loser.title()} (r={min(r_a,r_b):.3f}). "
        f"{'Significant.' if sig else 'Not statistically significant.'}"
    )


def _insufficient_result(h_id: str, h: dict, n: int) -> dict:
    return {
        "hypothesis_id": h_id,
        "name": h["name"],
        "type": h["type"],
        "description": h["description"],
        "tested": False,
        "supported": False,
        "sample_size": n,
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "verdict": f"Insufficient data ({n} days). Need {settings.min_sample_size} minimum.",
    }


def _error_result(h_id: str, h: dict, error: str) -> dict:
    return {
        "hypothesis_id": h_id,
        "name": h["name"],
        "type": h["type"],
        "description": h["description"],
        "tested": False,
        "supported": False,
        "sample_size": 0,
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "verdict": f"Error during testing: {error}",
    }
