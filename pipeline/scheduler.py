"""
Scheduled pipeline.

Two phases controlled by PIPELINE_CADENCE env var:

  Phase 1 — daily (default, first 90 days)
    Runs every day at 22:00 UTC (1 hour after US market close).
    Builds up time-series data fast enough to test all three hypotheses.

  Phase 2 — weekly (after 90+ days of data)
    Runs every Monday at 22:00 UTC.
    Market data is daily OHLCV — weekly scoring adds no analytical loss
    once correlations are established. Reduces API cost by ~85%.

To switch phases:
    Set PIPELINE_CADENCE=weekly in Railway environment variables.
    Rename .github/workflows/daily_pipeline.yml → weekly_pipeline.yml
    Update cron: '0 22 * * *' → '0 22 * * 1'

Scheduling rationale:
    - Market data (yfinance) is daily OHLCV — no intraday granularity to match
    - Correlation analysis is measured in trading days, not hours
    - 22:00 UTC = same-day prices are final before bias scores are computed
    - max_instances=1 prevents overlap if a run takes longer than the interval
    - misfire_grace_time=3600 allows Railway free tier to wake up late
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from pipeline.presslens_client import fetch_all_tracked_topics
from pipeline.price_fetcher import fetch_latest_prices
from analytics.polarization import compute_polarization
from backend.models.config import settings, TRACKED_TOPICS

scheduler = AsyncIOScheduler(timezone="UTC")


async def run_pipeline() -> None:
    """
    Full pipeline run — same logic regardless of daily or weekly cadence.
    Called on schedule and once on app startup.
    """
    cadence = settings.pipeline_cadence
    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    print(f"[Pipeline] Starting {cadence} run — {run_id}")

    # Step 1: Bias scores from PressLens API
    print("[Pipeline] Step 1/4 — Fetching bias scores from PressLens...")
    snapshots = await fetch_all_tracked_topics()
    print(f"[Pipeline] Got {len(snapshots)} outlet snapshots")

    if snapshots:
        await _store_bias_snapshots(snapshots)
        print("[Pipeline] Bias snapshots stored")

    # Step 2: Market prices via yfinance
    print("[Pipeline] Step 2/4 — Fetching market prices...")
    prices = fetch_latest_prices()
    print(f"[Pipeline] Got {len(prices)} price records")

    if prices:
        await _store_prices(prices)
        print("[Pipeline] Prices stored")

    # Step 3: Compute polarization per topic
    print("[Pipeline] Step 3/4 — Computing polarization scores...")
    for topic in TRACKED_TOPICS:
        topic_snapshots = [s for s in snapshots if s.topic == topic]
        if len(topic_snapshots) < 2:
            print(f"[Pipeline] {topic}: skipped (< 2 outlets)")
            continue
        pol_scores = compute_polarization(topic_snapshots, topic)
        if pol_scores:
            await _store_polarization(pol_scores)
            print(f"[Pipeline] {topic}: {len(pol_scores)} polarization scores stored")

    # Step 4: Recompute hypothesis tests in background
    print("[Pipeline] Step 4/4 — Triggering hypothesis recompute...")
    asyncio.create_task(_recompute_all_hypotheses())

    print(f"[Pipeline] {cadence.capitalize()} run complete — {run_id}")


async def _recompute_all_hypotheses() -> None:
    """Recompute all 3 hypothesis tests. Runs in background after pipeline."""
    from analytics.hypothesis_engine import test_all_hypotheses
    from backend.services.db import store_hypothesis_results

    print("[Hypothesis] Running all hypothesis tests...")
    try:
        results = await test_all_hypotheses()
        await store_hypothesis_results(results)
        supported = sum(1 for r in results if r.get("supported"))
        print(f"[Hypothesis] Complete — {supported}/{len(results)} supported")
    except Exception as e:
        print(f"[Hypothesis] Failed — {e}")


async def _store_bias_snapshots(snapshots) -> None:
    from backend.services.db import store_bias_snapshots
    await store_bias_snapshots(snapshots)


async def _store_prices(prices) -> None:
    from backend.services.db import store_prices
    await store_prices(prices)


async def _store_polarization(pol_scores) -> None:
    from backend.services.db import store_polarization
    await store_polarization(pol_scores)


def start_scheduler() -> None:
    """
    Start APScheduler. Cadence controlled by PIPELINE_CADENCE env var.

    Phase 1 (default): daily at 22:00 UTC
    Phase 2 (weekly):  every Monday at 22:00 UTC

    Called from FastAPI lifespan on app startup.
    """
    cadence = settings.pipeline_cadence

    if cadence == "weekly":
        trigger = CronTrigger(
            day_of_week="mon",
            hour=22,
            minute=0,
            timezone="UTC",
        )
        label = "every Monday at 22:00 UTC"
    else:
        trigger = CronTrigger(
            hour=22,
            minute=0,
            timezone="UTC",
        )
        label = "daily at 22:00 UTC"

    scheduler.add_job(
        run_pipeline,
        trigger=trigger,
        id="pipeline",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    scheduler.start()
    print(f"[Scheduler] Pipeline scheduled {label} (cadence={cadence})")
