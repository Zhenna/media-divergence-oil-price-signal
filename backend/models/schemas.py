"""
Pydantic schemas for the geopolitical media market signals pipeline.
"""
from __future__ import annotations
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field


# ── PressLens API ─────────────────────────────────────────────────────────────

class OutletScores(BaseModel):
    """Bias scores for a single outlet — mirrors PressLens BiasScores schema."""
    emotional_tone: int
    framing: int
    source_selection: int
    loaded_language: int
    political_stance: int = 5
    factual_density: int = 5
    overall: int
    sentiment: str
    sentiment_target: str
    verdict: str
    key_phrases: list[str] = []


class OutletResult(BaseModel):
    outlet_id: str
    outlet_name: str
    region: str
    scores: Optional[OutletScores] = None
    error: Optional[str] = None


class PressLensResponse(BaseModel):
    """Response from PressLens /api/analyze endpoint."""
    topic: str
    provider: str
    time_range_days: int
    results: list[OutletResult]


# ── Pipeline storage ──────────────────────────────────────────────────────────

class BiasSnapshot(BaseModel):
    """A single point-in-time bias scoring snapshot stored in the DB."""
    topic: str
    outlet_id: str
    outlet_name: str
    scored_at: datetime
    emotional_tone: int
    framing: int
    source_selection: int
    loaded_language: int
    political_stance: int
    factual_density: int
    overall: int
    sentiment: str
    verdict: str


class MarketPrice(BaseModel):
    """Daily closing price for a market symbol."""
    symbol: str
    name: str
    price_date: date
    close_price: float
    volume: Optional[int] = None


# ── Polarization ─────────────────────────────────────────────────────────────

class PolarizationScore(BaseModel):
    """
    Polarization = narrative distance between outlets.
    Measured as std deviation of outlet scores on a given dimension.
    Higher = more divergence between outlets.
    """
    topic: str
    measured_at: datetime
    dimension: str           # e.g. "overall", "emotional_tone"
    mean_score: float
    std_dev: float           # the polarization signal
    min_score: float
    max_score: float
    outlet_count: int
    spread: float            # max - min, simpler than std_dev for display


# ── Correlation ───────────────────────────────────────────────────────────────

class CorrelationResult(BaseModel):
    """
    Correlation between a polarization signal and a market price,
    tested at multiple lag values.
    """
    topic: str
    dimension: str           # bias dimension used as signal
    market_symbol: str
    market_name: str
    lag_days: int            # 0=same day, 1=next day, etc.
    pearson_r: float
    p_value: float
    sample_size: int
    is_significant: bool     # p_value < 0.05
    computed_at: datetime


# ── API responses ─────────────────────────────────────────────────────────────

class TimeSeriesPoint(BaseModel):
    date: str
    polarization: Optional[float] = None
    price: Optional[float] = None


class DashboardData(BaseModel):
    """Everything the frontend needs for the correlation dashboard."""
    topic: str
    market_symbol: str
    market_name: str
    time_series: list[TimeSeriesPoint]
    best_correlation: Optional[CorrelationResult] = None
    all_correlations: list[CorrelationResult] = []
    insight: str             # LLM-generated plain English summary
