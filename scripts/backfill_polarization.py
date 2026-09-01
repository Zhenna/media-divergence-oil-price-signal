"""
One-time script to compute polarization scores from historical GDELT bias snapshots.

Reads all bias_snapshots, groups by date, computes std dev across outlets
for each day, and stores in polarization_scores table.

Usage:
    python scripts/backfill_polarization.py

Expected output:
    Processing 2020-01-01... 6 outlets, std_dev=1.23
    ...
    Done — 1,847 polarization records stored
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.db import init_db, get_bias_records, store_polarization
from backend.models.schemas import PolarizationScore
import statistics

TOPIC = "Iran US Conflict"
DIMENSIONS = ["overall", "emotional_tone", "framing", "political_stance"]
DIMENSION_MAP = {
    "overall": "overall",
    "emotional_tone": "emotional_tone",
    "framing": "framing",
    "political_stance": "political_stance",
}


async def main():
    init_db()

    print("Loading all bias snapshots...")
    records = await get_bias_records(TOPIC, days=3000)
    print(f"Total bias snapshots: {len(records)}")

    # Group by calendar date
    by_date = defaultdict(list)
    for r in records:
        scored_at = r["scored_at"]
        if hasattr(scored_at, "date"):
            day = scored_at.date()
        else:
            day = scored_at
        by_date[day].append(r)

    print(f"Unique dates: {len(by_date)}")

    pol_scores = []
    for day in sorted(by_date.keys()):
        day_records = by_date[day]

        # Need at least 2 outlets to compute std dev
        if len(day_records) < 2:
            continue

        measured_at = datetime.combine(day, datetime.min.time()).replace(tzinfo=timezone.utc)

        for dimension in DIMENSIONS:
            scores = [r[dimension] for r in day_records if r.get(dimension) is not None]
            if len(scores) < 2:
                continue

            std_dev = statistics.stdev(scores)
            mean_score = statistics.mean(scores)
            min_score = min(scores)
            max_score = max(scores)

            pol_scores.append(PolarizationScore(
                topic=TOPIC,
                measured_at=measured_at,
                dimension=dimension,
                mean_score=round(mean_score, 4),
                std_dev=round(std_dev, 4),
                min_score=float(min_score),
                max_score=float(max_score),
                outlet_count=len(scores),
                spread=float(max_score - min_score),
            ))

    print(f"Computed {len(pol_scores)} polarization scores across {len(by_date)} days")
    print("Storing to database...")

    # Store in batches of 100
    batch_size = 100
    for i in range(0, len(pol_scores), batch_size):
        batch = pol_scores[i:i + batch_size]
        await store_polarization(batch)
        print(f"  Stored {min(i + batch_size, len(pol_scores))}/{len(pol_scores)}")

    print(f"\nDone — {len(pol_scores)} polarization records stored")
    print(f"Date range: {min(by_date.keys())} to {max(by_date.keys())}")
    print("\nTrigger a pipeline run to compute hypothesis correlations.")


if __name__ == "__main__":
    asyncio.run(main())