"""
Market price fetcher.

Fetches daily OHLCV data for tracked symbols using yfinance.
Free, no API key required.
"""
from __future__ import annotations

from datetime import date, timedelta
import yfinance as yf
import pandas as pd

from backend.models.schemas import MarketPrice
from backend.models.config import MARKET_SYMBOLS


def fetch_prices(
    symbols: list[str] | None = None,
    lookback_days: int = 90,
) -> list[MarketPrice]:
    """
    Fetch daily closing prices for all tracked symbols.

    Args:
        symbols: list of yfinance symbols, defaults to all MARKET_SYMBOLS
        lookback_days: how many days of history to fetch

    Returns:
        List of MarketPrice objects ready for database storage
    """
    symbols = symbols or list(MARKET_SYMBOLS.keys())
    end = date.today()
    start = end - timedelta(days=lookback_days)

    prices = []

    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=str(start), end=str(end), interval="1d")

            if hist.empty:
                print(f"[yfinance] {symbol}: no data returned")
                continue

            for price_date, row in hist.iterrows():
                prices.append(MarketPrice(
                    symbol=symbol,
                    name=MARKET_SYMBOLS.get(symbol, symbol),
                    price_date=price_date.date(),
                    close_price=round(float(row["Close"]), 4),
                    volume=int(row["Volume"]) if row["Volume"] else None,
                ))

            print(f"[yfinance] {symbol}: {len(hist)} days fetched")

        except Exception as e:
            print(f"[yfinance] {symbol}: failed — {e}")

    return prices


def fetch_latest_prices() -> list[MarketPrice]:
    """Fetch just the last 7 days — used for daily incremental updates."""
    return fetch_prices(lookback_days=7)


def prices_to_dataframe(prices: list[MarketPrice]) -> pd.DataFrame:
    """Convert price list to a pivot DataFrame: index=date, columns=symbols."""
    df = pd.DataFrame([p.model_dump() for p in prices])
    if df.empty:
        return df
    pivot = df.pivot_table(
        index="price_date",
        columns="symbol",
        values="close_price",
    )
    pivot.index = pd.to_datetime(pivot.index)
    return pivot.sort_index()


def fetch_historical_prices(start_date: str = "2020-01-01") -> list[MarketPrice]:
    """
    One-time historical backfill from start_date to today.
    Used by scripts/backfill_prices.py — not called by the daily pipeline.
    """
    symbols = list(MARKET_SYMBOLS.keys())
    end = date.today()
    prices = []

    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start_date, end=str(end), interval="1d")

            if hist.empty:
                print(f"[yfinance] {symbol}: no data returned")
                continue

            for price_date, row in hist.iterrows():
                prices.append(MarketPrice(
                    symbol=symbol,
                    name=MARKET_SYMBOLS.get(symbol, symbol),
                    price_date=price_date.date(),
                    close_price=round(float(row["Close"]), 4),
                    volume=int(row["Volume"]) if row["Volume"] else None,
                ))

            print(f"[yfinance] {symbol} ({MARKET_SYMBOLS[symbol]}): {len(hist)} days fetched")

        except Exception as e:
            print(f"[yfinance] {symbol}: failed — {e}")

    return prices
