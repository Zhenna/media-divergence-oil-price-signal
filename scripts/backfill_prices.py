"""
One-time historical price backfill.

Fetches WTI crude and Brent crude daily prices from 2020-01-01 to today.
Loads directly into the database configured in .env.

Usage:
    python scripts/backfill_prices.py

Expected output:
    CL=F (WTI Crude Oil): 1,257 days fetched
    BZ=F (Brent Crude Oil): 1,257 days fetched
    Done — 2,514 price records stored

Key dates to verify after backfill:
    2020-01-03  Soleimani assassination — WTI should spike +6% next day
    2022-07-15  JCPOA talks collapse — WTI +2%
    2024-04-14  Iran direct strike on Israel — WTI +4%
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.db import init_db, store_prices
from pipeline.price_fetcher import fetch_historical_prices


async def main():
    print("Initialising database...")
    init_db()

    print("Fetching historical prices from 2020-01-01...")
    prices = fetch_historical_prices(start_date="2020-01-01")

    if not prices:
        print("No prices fetched — check yfinance connection")
        sys.exit(1)

    print(f"Storing {len(prices)} price records...")
    await store_prices(prices)

    print(f"\nDone — {len(prices)} records stored")
    print("\nVerifying key events:")

    wti = [p for p in prices if p.symbol == "CL=F"]
    dates = {str(p.price_date): p.close_price for p in wti}

    for event_date, label in [
        ("2020-01-06", "Soleimani +1d"),
        ("2022-07-18", "JCPOA +1d"),
        ("2024-04-15", "Iran strike +1d"),
    ]:
        price = dates.get(event_date)
        status = f"${price:.2f}" if price else "not found (weekend/holiday)"
        print(f"  {event_date} ({label}): {status}")


if __name__ == "__main__":
    asyncio.run(main())
