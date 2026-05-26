"""
FastAPI routes for the analytics dashboard.
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
import os

from backend.models.config import TRACKED_TOPICS, MARKET_SYMBOLS, HYPOTHESES
from backend.models.schemas import DashboardData, TimeSeriesPoint
from backend.services.db import (
    get_polarization_records,
    get_price_records,
    get_bias_records,
    get_best_correlations,
    get_latest_hypothesis_results,
)
from analytics.correlation import (
    compute_all_correlations,
    find_best_correlation,
    polarization_vs_sentiment_comparison,
)
from analytics.polarization import polarization_to_series
from pipeline.price_fetcher import prices_to_dataframe

router = APIRouter()


# @router.get("/debug/env")
# async def debug_env():
#     """Temporary — remove after confirming pipeline works."""
#     from backend.models.config import settings
#     return {
#         "OPENAI_API_KEY_length": len(os.environ.get("OPENAI_API_KEY", "")),
#         "provider": settings.presslens_provider,
#         "pipeline_cadence": settings.pipeline_cadence,
#         "presslens_url": settings.presslens_url,
#     }


@router.get("/topics")
async def list_topics():
    return [{"topic": t, "outlets": o} for t, o in TRACKED_TOPICS.items()]


@router.get("/markets")
async def list_markets():
    return [{"symbol": s, "name": n} for s, n in MARKET_SYMBOLS.items()]


@router.get("/correlations/{topic}")
async def get_correlations(topic: str):
    correlations = await get_best_correlations(topic)
    if not correlations:
        raise HTTPException(
            status_code=404,
            detail=f"No correlations yet for '{topic}'. Need {14} days minimum."
        )
    return correlations


@router.get("/timeseries/{topic}/{symbol}")
async def get_timeseries(topic: str, symbol: str, days: int = 90):
    pol_records = await get_polarization_records(topic, days=days)
    price_records = await get_price_records(symbols=[symbol], days=days)

    if not pol_records:
        raise HTTPException(status_code=404, detail=f"No polarization data for '{topic}'")
    if not price_records:
        raise HTTPException(status_code=404, detail=f"No price data for '{symbol}'")

    pol_series = polarization_to_series(pol_records, dimension="overall")
    import pandas as pd
    price_series = pd.Series(
        {r["price_date"]: r["close_price"] for r in price_records}
    )
    price_series.index = pd.to_datetime(price_series.index)

    all_dates = sorted(set(pol_series.index) | set(price_series.index))
    points = []
    for d in all_dates:
        points.append(TimeSeriesPoint(
            date=str(d.date()),
            polarization=round(float(pol_series.get(d)), 4) if d in pol_series.index else None,
            price=round(float(price_series.get(d)), 4) if d in price_series.index else None,
        ))

    return {
        "topic": topic,
        "symbol": symbol,
        "symbol_name": MARKET_SYMBOLS.get(symbol, symbol),
        "points": points,
    }


@router.get("/hypothesis/{topic}")
async def test_hypothesis(topic: str):
    pol_records = await get_polarization_records(topic)
    sentiment_records = await get_bias_records(topic)
    price_records = await get_price_records(symbols=["^VIX"])

    comparison = polarization_vs_sentiment_comparison(
        polarization_records=pol_records,
        sentiment_records=sentiment_records,
        price_records=price_records,
        topic=topic,
        market_symbol="^VIX",
    )

    pol_r = comparison.get("polarization")
    sent_r = comparison.get("mean_sentiment")

    hypothesis_supported = (
        pol_r is not None
        and sent_r is not None
        and abs(pol_r.pearson_r) > abs(sent_r.pearson_r)
        and pol_r.is_significant
    )

    return {
        "topic": topic,
        "hypothesis": "Polarization predicts VIX better than mean sentiment",
        "supported": hypothesis_supported,
        "polarization_correlation": pol_r.model_dump() if pol_r else None,
        "sentiment_correlation": sent_r.model_dump() if sent_r else None,
    }


@router.get("/hypotheses")
async def get_all_hypothesis_results():
    results = await get_latest_hypothesis_results()
    results_by_id = {r["hypothesis_id"]: r for r in results}
    output = []
    for h_id, h_config in HYPOTHESES.items():
        stored = results_by_id.get(h_id, {})
        output.append({
            "hypothesis_id": h_id,
            "name": h_config["name"],
            "type": h_config["type"],
            "description": h_config["description"],
            "rationale": h_config["rationale"],
            "market": h_config["market"],
            "market_name": MARKET_SYMBOLS.get(h_config["market"], h_config["market"]),
            "status": (
                "supported" if stored.get("supported")
                else "not_supported" if stored.get("tested")
                else "pending"
            ),
            "sample_size": stored.get("sample_size", 0),
            "pearson_r": stored.get("pearson_r"),
            "p_value": stored.get("p_value"),
            "lag_days": stored.get("lag_days"),
            "verdict": stored.get("verdict", f"Accumulating data. Need {14} days minimum."),
            "tested_at": stored.get("tested_at"),
        })
    return output


@router.post("/pipeline/run")
async def trigger_pipeline(background_tasks: BackgroundTasks):
    from pipeline.scheduler import run_pipeline
    background_tasks.add_task(run_pipeline)
    return {"message": "Pipeline triggered. Check logs for progress."}
