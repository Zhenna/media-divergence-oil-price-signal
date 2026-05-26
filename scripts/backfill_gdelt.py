"""
One-time GDELT historical backfill.

Fetches Iran US Conflict coverage from GDELT for 6 tracked outlets,
2020-01-01 to present. Uses Google BigQuery free tier (1TB/month).

Prerequisites:
    1. Google Cloud account (free) at console.cloud.google.com
    2. Create a project → enable BigQuery API
    3. Create service account → download JSON key
    4. pip install google-cloud-bigquery

Usage:
    export GOOGLE_APPLICATION_CREDENTIALS="/path/to/key.json"
    export DATABASE_URL="postgresql://..."
    python scripts/backfill_gdelt.py

Expected output:
    Got 1,200+ rows from GDELT
    Storing 1,200+ historical snapshots...
    Done — date range: 2020-01-02 to 2025-05-26
    Outlets: {'rt', 'aljazeera', 'cgtn', 'reuters', 'bbc', 'nyt'}

GDELT tone scores are cruder than PressLens 6-dimension scoring
but sufficient for historical baseline correlation analysis.
Stored with data_source='gdelt' to distinguish from live PressLens data.

Note: After running this, hypothesis correlations compute immediately
using 4+ years of historical data rather than waiting 90 days.
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.db import init_db, store_bias_snapshots
from backend.models.schemas import BiasSnapshot

OUTLET_MAP = {
    "rt.com":         "rt",
    "aljazeera.com":  "aljazeera",
    "cgtn.com":       "cgtn",
    "reuters.com":    "reuters",
    "bbc.co.uk":      "bbc",
    "bbc.com":        "bbc",
    "nytimes.com":    "nyt",
}

OUTLET_NAMES = {
    "rt": "RT", "aljazeera": "Al Jazeera", "cgtn": "CGTN",
    "reuters": "Reuters", "bbc": "BBC", "nyt": "NY Times",
}

GDELT_QUERY = """
SELECT
    DATE(CAST(SUBSTR(CAST(date AS STRING), 1, 8) AS DATE FORMAT 'YYYYMMDD')) as scored_date,
    SourceCommonName as source,
    AVG(CAST(SPLIT(V2Tone, ',')[OFFSET(0)] AS FLOAT64)) as mean_tone,
    COUNT(*) as article_count
FROM
    `gdelt-bq.gdeltv2.gkg_partitioned`
WHERE
    _PARTITIONTIME >= '2020-01-01'
    AND (
        Themes LIKE '%IRANPERSIAN%'
        OR Themes LIKE '%USGOV%'
        OR Locations LIKE '%Iran%'
    )
    AND SourceCommonName IN (
        'rt.com', 'aljazeera.com', 'cgtn.com',
        'reuters.com', 'bbc.co.uk', 'bbc.com', 'nytimes.com'
    )
GROUP BY
    scored_date, source
ORDER BY
    scored_date, source
"""


def tone_to_score(tone: float) -> int:
    """
    Convert GDELT tone (-10 to +10) to PressLens-compatible 1-10 score.
    More negative tone = higher bias/emotional score.
    """
    normalized = abs(tone) / 10.0
    return max(1, min(10, round(1 + normalized * 9)))


async def run_bigquery_backfill():
    try:
        from google.cloud import bigquery
    except ImportError:
        print("ERROR: google-cloud-bigquery not installed.")
        print("Run: pip install google-cloud-bigquery")
        sys.exit(1)

    print("Connecting to BigQuery...")
    client = bigquery.Client()

    print("Running GDELT query (may take 1-3 minutes)...")
    query_job = client.query(GDELT_QUERY)
    rows = list(query_job.result())
    print(f"Got {len(rows)} rows from GDELT")

    if not rows:
        print("No data returned. Check your Google Cloud credentials and query.")
        sys.exit(1)

    snapshots = []
    for row in rows:
        outlet_id = OUTLET_MAP.get(row.source)
        if not outlet_id:
            continue

        score = tone_to_score(row.mean_tone or 0)
        scored_at = datetime.combine(
            row.scored_date,
            datetime.min.time()
        ).replace(tzinfo=timezone.utc)

        snapshots.append(BiasSnapshot(
            topic="Iran US Conflict",
            outlet_id=outlet_id,
            outlet_name=OUTLET_NAMES.get(outlet_id, outlet_id),
            scored_at=scored_at,
            emotional_tone=score,
            framing=score,
            source_selection=score,
            loaded_language=score,
            political_stance=score,
            factual_density=max(1, 11 - score),
            overall=score,
            sentiment="Historical",
            verdict=f"GDELT tone: {row.mean_tone:.2f} ({row.article_count} articles)",
            data_source="gdelt",
        ))

    if not snapshots:
        print("No snapshots created — check outlet mapping")
        sys.exit(1)

    print(f"Storing {len(snapshots)} historical snapshots...")
    await store_bias_snapshots(snapshots)

    print(f"\nDone — {len(snapshots)} GDELT records stored")
    print(f"Date range: {min(s.scored_at for s in snapshots).date()} "
          f"to {max(s.scored_at for s in snapshots).date()}")
    print(f"Outlets: {set(s.outlet_id for s in snapshots)}")
    print("\nCorrelations will now compute using full historical dataset.")


async def main():
    init_db()
    await run_bigquery_backfill()


if __name__ == "__main__":
    asyncio.run(main())
