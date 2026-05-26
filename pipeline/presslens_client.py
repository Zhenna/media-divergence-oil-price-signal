"""
PressLens API client.

This project does not duplicate PressLens source code.
All bias scoring is delegated to the deployed PressLens API.

PressLens repo: https://github.com/yourname/presslens-media-bias-analyzer
"""
from __future__ import annotations

import httpx
import os
from datetime import datetime, timezone

from backend.models.schemas import BiasSnapshot
from backend.models.config import settings, TRACKED_TOPICS


async def fetch_bias_scores(topic, outlet_ids):
    api_key = os.environ.get("PRESSLENS_API_KEY", "")
    print(f"[DEBUG] api_key from os.environ: length={len(api_key)}")
    
    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(
            f"{settings.presslens_url}/api/analyze",
            json={
                "topic": topic,
                "outlets": outlet_ids,
                "provider": settings.presslens_provider,
                "api_key": api_key,
                "time_range_days": 7,
            },
        )
        if res.status_code != 200:
            print(f"[PressLens DEBUG] Status: {res.status_code}")
            print(f"[PressLens DEBUG] Response body: {res.text}")
            print(f"[PressLens DEBUG] api_key sent: length={len(settings.presslens_api_key)} prefix={settings.presslens_api_key[:8] if settings.presslens_api_key else 'EMPTY'}")
            res.raise_for_status()
        data = res.json()

    snapshots = []
    now = datetime.now(timezone.utc)

    for result in data.get("results", []):
        if not result.get("scores"):
            continue
        s = result["scores"]
        outlet = result["outlet"]
        snapshots.append(BiasSnapshot(
            topic=topic,
            outlet_id=outlet.get("id", ""),
            outlet_name=outlet.get("name", ""),
            scored_at=now,
            emotional_tone=s["emotional_tone"],
            framing=s["framing"],
            source_selection=s["source_selection"],
            loaded_language=s["loaded_language"],
            political_stance=s.get("political_stance", 5),
            factual_density=s.get("factual_density", 5),
            overall=s["overall"],
            sentiment=s["sentiment"],
            verdict=s["verdict"],
        ))

    # Extract consensus fact count from synthesis (H3 signal)
    synthesis = data.get("synthesis") or {}
    consensus_facts = synthesis.get("consensus_facts") or []
    key_divergence = synthesis.get("key_divergence") or ""
    consensus_fact_count = len(consensus_facts)

    return snapshots, consensus_fact_count, key_divergence


async def fetch_all_tracked_topics() -> list[BiasSnapshot]:
    """
    Fetch bias scores for all tracked topics.
    Also stores consensus fact counts for H3.
    """
    from backend.services.db import store_consensus_facts

    all_snapshots = []
    for topic, outlet_ids in TRACKED_TOPICS.items():
        try:
            snapshots, fact_count, divergence = await fetch_bias_scores(topic, outlet_ids)
            all_snapshots.extend(snapshots)
            # Store consensus fact count for H3
            if snapshots:
                await store_consensus_facts(topic, fact_count, divergence)
            print(f"[PressLens] {topic}: {len(snapshots)} outlets, {fact_count} consensus facts")
        except Exception as e:
            print(f"[PressLens] {topic}: failed — {e}")
    return all_snapshots
