"""
Application settings and configuration.
All tracked topics, market symbols, and hypotheses defined here.
"""
from pydantic_settings import BaseSettings
from typing import Literal
import os


class Settings(BaseSettings):
    # PressLens API
    presslens_url: str = "https://presslens-production-3f0c.up.railway.app"
    presslens_api_key: str = ""
    presslens_provider: str = "openai"

    # Pipeline cadence — switch to "weekly" after 90+ days of data
    # Change this env var in Railway, no code change needed
    pipeline_cadence: Literal["daily", "weekly"] = "daily"

    # Database
    # Neon URL hardcoded as default — Railway Runtime V2 blocks DATABASE_URL injection
    # Override with DATABASE_URL env var for local development (SQLite)
    database_url: str = os.environ.get(
        "DATABASE_URL",
        "postgresql://neondb_owner:npg_YOseWvTU9zb6@ep-broad-pine-ap3xh6mt-pooler.c-7.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    )

    # Correlation analysis
    correlation_lag_days: list[int] = [0, 1, 2, 3, 5, 7]
    min_sample_size: int = 14
    significance_threshold: float = 0.05
    exploratory_significance_threshold: float = 0.01

    # MLflow (DagsHub)
    mlflow_tracking_uri: str = ""
    mlflow_tracking_username: str = ""
    mlflow_tracking_password: str = ""

    # LangSmith
    langchain_tracing_v2: str = "false"
    langchain_api_key: str = ""
    langchain_project: str = "media-divergence-oil-price-signal"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }


settings = Settings()

# pydantic-settings v2 env var loading is unreliable in some Railway configs
# Read critical vars directly from os.environ as fallback
if not settings.presslens_api_key:
    settings.presslens_api_key = os.environ.get("PRESSLENS_API_KEY", "")
if not settings.presslens_url:
    settings.presslens_url = os.environ.get("PRESSLENS_URL", "https://presslens-production-3f0c.up.railway.app")


# ── Tracked topics ─────────────────────────────────────────────────────────────
# 6 outlets: 3 non-Western cluster + 3 Western cluster

TRACKED_TOPICS: dict[str, list[str]] = {
    "Iran US Conflict": ["rt", "aljazeera", "cgtn", "reuters", "bbc", "nyt"],
}

# ── Outlet clusters ────────────────────────────────────────────────────────────
# The core signal: divergence between these two clusters

OUTLET_CLUSTERS = {
    "non_western": ["rt", "aljazeera", "cgtn"],   # Russia + Qatar + China
    "western":     ["reuters", "bbc", "nyt"],      # INT wire + UK + US
}

# ── Market symbols ─────────────────────────────────────────────────────────────

MARKET_SYMBOLS: dict[str, str] = {
    "CL=F":  "WTI Crude Oil",
    "BZ=F":  "Brent Crude Oil",
    "GC=F":  "Gold",
    "^VIX":  "Volatility Index (VIX)",
}

# ── Key historical events ──────────────────────────────────────────────────────
# Used to annotate charts and validate that data captures expected moves

KEY_EVENTS = [
    {"date": "2020-01-03", "label": "Soleimani assassination", "expected": "+6%"},
    {"date": "2022-07-15", "label": "JCPOA talks collapse",    "expected": "+2%"},
    {"date": "2024-04-14", "label": "Iran direct strike",      "expected": "+4%"},
]

# ── Polarization dimensions ────────────────────────────────────────────────────

POLARIZATION_DIMENSIONS = [
    "overall",
    "emotional_tone",
    "framing",
    "political_stance",
]

# ── Three hypotheses ───────────────────────────────────────────────────────────

HYPOTHESES = {
    "H1": {
        "name": "Polarization predicts oil better than mean sentiment",
        "type": "confirmatory",
        "description": (
            "Narrative polarization (std deviation of outlet scores) between "
            "non-Western and Western clusters on Iran coverage predicts WTI crude "
            "oil price movement better than any single outlet's mean sentiment score."
        ),
        "signal": "polarization_std_dev",
        "dimension": "overall",
        "topics": ["Iran US Conflict"],
        "market": "CL=F",
        "lag_days": [0, 1, 2, 3],
        "significance_threshold": settings.significance_threshold,
        "rationale": (
            "When RT, Al Jazeera and CGTN diverge from Reuters, BBC and NY Times, "
            "the situation is contested. Contested geopolitical situations drive "
            "oil market uncertainty. Polarization captures this more precisely "
            "than any single outlet's tone."
        ),
    },
    "H2": {
        "name": "Anticipated shock premium on quiet Reuters days",
        "type": "exploratory",
        "description": (
            "WTI crude rises within 48 hours of a polarization spike even when "
            "Reuters scores below 3 — consistent with algorithmic trading on "
            "anticipated supply risk rather than realized supply disruption."
        ),
        "signal": "polarization_std_dev",
        "dimension": "overall",
        "topics": ["Iran US Conflict"],
        "market": "CL=F",
        "lag_days": [0, 1, 2],
        "reuters_threshold": 3,
        "significance_threshold": settings.significance_threshold,
        "rationale": (
            "The Reuters calm condition isolates the anticipatory signal from "
            "reactions to actual events. If oil moves when Reuters is calm, "
            "traders are pricing in risk, not responding to facts."
        ),
    },
    "H3": {
        "name": "Cluster divergence beats raw spread",
        "type": "exploratory",
        "description": (
            "The directional spread between non-Western cluster mean and Western "
            "cluster mean is a stronger oil predictor than overall outlet "
            "standard deviation alone."
        ),
        "signal": "cluster_divergence",
        "dimension": "overall",
        "topics": ["Iran US Conflict"],
        "market": "CL=F",
        "lag_days": [0, 1, 2, 3],
        "significance_threshold": settings.significance_threshold,
        "rationale": (
            "Directional divergence (non-Western higher than Western) is a "
            "different signal from raw spread. A situation where RT is alarmed "
            "while Reuters is calm is more informative than one where all outlets "
            "are equally uncertain."
        ),
    },
}
