"""
Pipeline entry point for GitHub Actions.

Usage:
    python -m pipeline.run

Runs the full pipeline once synchronously.
Used by GitHub Actions workflows — not the FastAPI scheduler.
The FastAPI app uses APScheduler; GitHub Actions uses this script directly.
"""
import asyncio
import sys
from pipeline.scheduler import run_pipeline
from backend.services.db import init_db


async def main() -> None:
    print("[Pipeline] Initialising database...")
    init_db()
    print("[Pipeline] Starting pipeline run...")
    await run_pipeline()
    print("[Pipeline] Done.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
        sys.exit(0)
    except Exception as e:
        print(f"[Pipeline] Fatal error: {e}")
        sys.exit(1)
