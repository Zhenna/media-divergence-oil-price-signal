"""
Market price fetcher using yfinance.
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
    symbols = symbols or list(MARKET_SYMBOLS.keys())
    end = date.today()
    start = end - timedelta(days=lookback_days)
    prices = []

    for symbol in symbols:
        try:
            df = yf.download(
                symbol,
                start=str(start),
                end=str(end),
                interval="1d",
                auto_adjust=True,
                progress=False,
            )
            if df.empty:
                print(f"[yfinance] {symbol}: no data returned")
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            for price_date, row in df.iterrows():
                prices.append(MarketPrice(
                    symbol=symbol,
                    name=MARKET_SYMBOLS.get(symbol, symbol),
                    price_date=price_date.date(),
                    close_price=round(float(row["Close"]), 4),
                    volume=int(row["Volume"]) if pd.notna(row.get("Volume")) else None,
                ))
            print(f"[yfinance] {symbol}: {len(df)} days fetched")
        except Exception as e:
            print(f"[yfinance] {symbol}: failed — {e}")

    return prices


def fetch_latest_prices() -> list[MarketPrice]:
    """Fetch last 7 days — used for daily incremental updates."""
    return fetch_prices(lookback_days=7)


def fetch_historical_prices(start_date: str = "2020-01-01") -> list[MarketPrice]:
    """One-time historical backfill. Used by scripts/backfill_prices.py."""
    symbols = list(MARKET_SYMBOLS.keys())
    prices = []

    for symbol in symbols:
        try:
            df = yf.download(
                symbol,
                start=start_date,
                end=str(date.today()),
                interval="1d",
                auto_adjust=True,
                progress=False,
            )
            if df.empty:
                print(f"[yfinance] {symbol}: no data returned")
                continue

            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            for price_date, row in df.iterrows():
                prices.append(MarketPrice(
                    symbol=symbol,
                    name=MARKET_SYMBOLS.get(symbol, symbol),
                    price_date=price_date.date(),
                    close_price=round(float(row["Close"]), 4),
                    volume=int(row["Volume"]) if pd.notna(row.get("Volume")) else None,
                ))
            print(f"[yfinance] {symbol} ({MARKET_SYMBOLS[symbol]}): {len(df)} days fetched")
        except Exception as e:
            print(f"[yfinance] {symbol}: failed — {e}")

    return prices


def prices_to_dataframe(prices: list[MarketPrice]) -> pd.DataFrame:
    """Convert price list to pivot DataFrame: index=date, columns=symbols."""
    if not prices:
        return pd.DataFrame()
    df = pd.DataFrame([p.model_dump() for p in prices])
    pivot = df.pivot_table(index="price_date", columns="symbol", values="close_price")
    pivot.index = pd.to_datetime(pivot.index)
    return pivot.sort_index()
