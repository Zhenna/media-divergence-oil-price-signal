"""
Pipeline entry point for GitHub Actions.

Usage:
    python -m pipeline.run

Runs the full pipeline once synchronously.
Exits with code 1 (failure) if:
- 0 outlets scored (API key issue or PressLens down)
- 0 price records fetched (yfinance issue)
- database write fails

GitHub Actions treats exit code 1 as a failed job
and sends an email notification automatically.
"""
import asyncio
import sys
from pipeline.scheduler import run_pipeline
from backend.services.db import init_db, get_bias_records, get_price_records


async def main() -> None:
    print("[Pipeline] Initialising database...")
    init_db()
    print("[Pipeline] Starting pipeline run...")
    await run_pipeline()

    # ── Validation: confirm data was actually written ──────────────────────
    print("[Pipeline] Validating data was written to database...")

    # Check bias snapshots were stored today
    from datetime import datetime, timezone, timedelta
    today_records = await get_bias_records("Iran US Conflict", days=1)
    if not today_records:
        print("[Pipeline] FAILURE: 0 bias snapshots in database — API key issue or PressLens down")
        sys.exit(1)

    # Check price records were stored
    price_records = await get_price_records(days=7)
    if not price_records:
        print("[Pipeline] FAILURE: 0 price records in database — yfinance issue")
        sys.exit(1)

    print(f"[Pipeline] Validation passed — {len(today_records)} bias snapshots, "
          f"{len(price_records)} price records in database")
    print("[Pipeline] Done.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
        sys.exit(0)
    except SystemExit as e:
        sys.exit(e.code)
    except Exception as e:
        print(f"[Pipeline] Fatal error: {e}")
        sys.exit(1)
