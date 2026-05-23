"""
Database service layer.

Handles all reads and writes to PostgreSQL (or SQLite in dev).
Uses SQLModel for schema definition and raw SQL for analytics queries
where performance matters.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlmodel import Field, Session, SQLModel, create_engine, select, text

from backend.models.config import settings
from backend.models.schemas import (
    BiasSnapshot, MarketPrice, PolarizationScore, CorrelationResult
)

engine = create_engine(settings.database_url, echo=False)


# ── SQLModel table definitions ────────────────────────────────────────────────

class BiasSnapshotDB(SQLModel, table=True):
    __tablename__ = "bias_snapshots"
    id: Optional[int] = Field(default=None, primary_key=True)
    topic: str = Field(index=True)
    outlet_id: str = Field(index=True)
    outlet_name: str
    scored_at: datetime
    emotional_tone: int
    framing: int
    source_selection: int
    loaded_language: int
    political_stance: int = 5
    factual_density: int = 5
    overall: int
    sentiment: str
    verdict: str


class MarketPriceDB(SQLModel, table=True):
    __tablename__ = "market_prices"
    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True)
    name: str
    price_date: str          # stored as ISO date string
    close_price: float
    volume: Optional[int] = None


class PolarizationDB(SQLModel, table=True):
    __tablename__ = "polarization_scores"
    id: Optional[int] = Field(default=None, primary_key=True)
    topic: str = Field(index=True)
    measured_at: datetime
    dimension: str
    mean_score: float
    std_dev: float
    min_score: float
    max_score: float
    outlet_count: int
    spread: float


class CorrelationDB(SQLModel, table=True):
    __tablename__ = "correlations"
    id: Optional[int] = Field(default=None, primary_key=True)
    topic: str = Field(index=True)
    dimension: str
    market_symbol: str
    market_name: str
    lag_days: int
    pearson_r: float
    p_value: float
    sample_size: int
    is_significant: bool
    computed_at: datetime


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


# ── Write operations ──────────────────────────────────────────────────────────

async def store_bias_snapshots(snapshots: list[BiasSnapshot]) -> None:
    with Session(engine) as session:
        for s in snapshots:
            session.add(BiasSnapshotDB(**s.model_dump()))
        session.commit()


async def store_prices(prices: list[MarketPrice]) -> None:
    with Session(engine) as session:
        for p in prices:
            # Upsert by symbol + date
            existing = session.exec(
                select(MarketPriceDB).where(
                    MarketPriceDB.symbol == p.symbol,
                    MarketPriceDB.price_date == str(p.price_date),
                )
            ).first()
            if not existing:
                data = p.model_dump()
                data["price_date"] = str(data["price_date"])
                session.add(MarketPriceDB(**data))
        session.commit()


async def store_polarization(scores: list[PolarizationScore]) -> None:
    with Session(engine) as session:
        for s in scores:
            session.add(PolarizationDB(**s.model_dump()))
        session.commit()


async def store_correlations(correlations: list[CorrelationResult]) -> None:
    with Session(engine) as session:
        for c in correlations:
            session.add(CorrelationDB(**c.model_dump()))
        session.commit()


# ── Read operations ───────────────────────────────────────────────────────────

async def get_polarization_records(
    topic: str,
    days: int = 90,
) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with Session(engine) as session:
        rows = session.exec(
            select(PolarizationDB).where(
                PolarizationDB.topic == topic,
                PolarizationDB.measured_at >= cutoff,
            ).order_by(PolarizationDB.measured_at)
        ).all()
    return [r.model_dump() for r in rows]


async def get_price_records(
    symbols: list[str] | None = None,
    days: int = 90,
) -> list[dict]:
    from datetime import date, timedelta
    cutoff = str(date.today() - timedelta(days=days))
    with Session(engine) as session:
        query = select(MarketPriceDB).where(MarketPriceDB.price_date >= cutoff)
        if symbols:
            query = query.where(MarketPriceDB.symbol.in_(symbols))
        rows = session.exec(query.order_by(MarketPriceDB.price_date)).all()
    return [r.model_dump() for r in rows]


async def get_bias_records(topic: str, days: int = 90) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with Session(engine) as session:
        rows = session.exec(
            select(BiasSnapshotDB).where(
                BiasSnapshotDB.topic == topic,
                BiasSnapshotDB.scored_at >= cutoff,
            ).order_by(BiasSnapshotDB.scored_at)
        ).all()
    return [r.model_dump() for r in rows]


async def get_best_correlations(
    topic: str,
    limit: int = 10,
) -> list[dict]:
    with Session(engine) as session:
        rows = session.exec(
            select(CorrelationDB)
            .where(CorrelationDB.topic == topic, CorrelationDB.is_significant == True)
            .order_by(text("ABS(pearson_r) DESC"))
            .limit(limit)
        ).all()
    return [r.model_dump() for r in rows]


# ── Additional tables for H3 and hypothesis results ───────────────────────────

class ConsensusFact(SQLModel, table=True):
    __tablename__ = "consensus_facts"
    id: Optional[int] = Field(default=None, primary_key=True)
    topic: str = Field(index=True)
    scored_at: datetime
    consensus_fact_count: int
    key_divergence: str = ""


class HypothesisResult(SQLModel, table=True):
    __tablename__ = "hypothesis_results"
    id: Optional[int] = Field(default=None, primary_key=True)
    hypothesis_id: str = Field(index=True)
    name: str
    type: str                    # confirmatory or exploratory
    tested: bool
    supported: bool
    sample_size: int
    pearson_r: Optional[float] = None
    p_value: Optional[float] = None
    lag_days: Optional[int] = None
    verdict: str
    tested_at: datetime


async def store_consensus_facts(topic: str, fact_count: int,
                                 key_divergence: str = "") -> None:
    with Session(engine) as session:
        session.add(ConsensusFact(
            topic=topic,
            scored_at=datetime.now(timezone.utc),
            consensus_fact_count=fact_count,
            key_divergence=key_divergence,
        ))
        session.commit()


async def get_consensus_fact_counts(days: int = 90) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    with Session(engine) as session:
        rows = session.exec(
            select(ConsensusFact)
            .where(ConsensusFact.scored_at >= cutoff)
            .order_by(ConsensusFact.scored_at)
        ).all()
    return [r.model_dump() for r in rows]


async def store_hypothesis_results(results: list[dict]) -> None:
    with Session(engine) as session:
        for r in results:
            best = r.get("best_correlation") or {}
            session.add(HypothesisResult(
                hypothesis_id=r["hypothesis_id"],
                name=r["name"],
                type=r["type"],
                tested=r["tested"],
                supported=r["supported"],
                sample_size=r.get("sample_size", 0),
                pearson_r=best.get("pearson_r"),
                p_value=best.get("p_value"),
                lag_days=best.get("lag_days"),
                verdict=r["verdict"],
                tested_at=datetime.fromisoformat(r["tested_at"]),
            ))
        session.commit()


async def get_latest_hypothesis_results() -> list[dict]:
    """Return the most recent result for each hypothesis."""
    with Session(engine) as session:
        # Get latest tested_at per hypothesis_id
        results = []
        for h_id in ["H1", "H2", "H3", "H4", "H5"]:
            row = session.exec(
                select(HypothesisResult)
                .where(HypothesisResult.hypothesis_id == h_id)
                .order_by(HypothesisResult.tested_at.desc())
                .limit(1)
            ).first()
            if row:
                results.append(row.model_dump())
    return results
