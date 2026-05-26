# media-divergence-oil-price-signal

> When RT and Al Jazeera tell a different story from Reuters and BBC, does oil move? A data pipeline that measures narrative divergence across global press and correlates it with WTI crude prices — daily, automated, statistically tested.

**Live demo:** [railway-url](https://media-divergence-oil-price-signal-production.up.railway.app/)
**Built on top of:** [PressLens](https://github.com/zhenna/presslens-media-bias-analyzer) — no LLM code duplicated.

---

## The hypothesis

Traditional financial NLP measures sentiment — how negative is a given source?

This project measures **polarization** — how far apart are sources from each other?

```
Sentiment:    RT scores 8/10 negative        ← expected, not surprising
Polarization: RT=8, Reuters=2, std_dev=3.4   ← unusual divergence = signal?
```

When outlets converge, the situation is understood.
When outlets diverge sharply, the situation is contested — and contested
geopolitical situations drive oil market uncertainty.

---

## Results

*Accumulating data — results published after 90 days.*

Three hypotheses tested daily:

**H1 — Confirmatory**
Narrative polarization between non-Western (RT, Al Jazeera, CGTN) and Western
(Reuters, BBC, NY Times) outlets predicts WTI crude oil price movement better
than any single outlet's mean sentiment score.

**H2 — Exploratory**
WTI crude rises within 48 hours of a polarization spike even when Reuters
scores below 3 — anticipated shock premium, not realized event response.

**H3 — Exploratory**
Directional cluster divergence (non-Western mean minus Western mean) is a
stronger oil predictor than raw standard deviation alone.

---

## What it tracks

**Topic:** Iran US Conflict

**Outlets — two clusters:**
```
Non-Western: RT (RU) · Al Jazeera (QA) · CGTN (CN)
Western:     Reuters (INT) · BBC (GB) · NY Times (US)
```

**Markets:** WTI Crude Oil · Brent Crude · Gold · VIX

**Key historical anchor events:**
- Jan 3 2020 — Soleimani assassination ($63.27 → $65.75 WTI)
- Jul 15 2022 — JCPOA talks collapse ($102.60 WTI)
- Apr 14 2024 — Iran direct strike on Israel ($85.41 WTI)

---

## Architecture

```
Google BigQuery (one-time)
    └── GDELT historical data 2020–present ──► Neon PostgreSQL

GitHub Actions (daily at 22:00 UTC)
    ├── pytest tests (gate — only runs if tests pass)
    ├── PressLens API ──► bias scores ──────────► Neon PostgreSQL
    ├── yfinance ──────► WTI + Brent prices ───► Neon PostgreSQL
    ├── polarization engine (scipy) ────────────► Neon PostgreSQL
    └── hypothesis tests ──► MLflow (DagsHub) ──► Neon PostgreSQL

Railway (always-on)
    └── FastAPI + Plotly.js dashboard ──► reads Neon

LangSmith
    └── traces every PressLens API call
```

---

## MLOps stack

| Tool | Purpose | Why this tool |
|---|---|---|
| GitHub Actions | Daily pipeline + CI/CD | Tests gate every run; version-controlled |
| Neon PostgreSQL | Time-series storage | Serverless, scales to zero |
| LangSmith | LLM call tracing | Cost, latency, schema pass rate |
| DagsHub MLflow | Experiment tracking | Every hypothesis test logged reproducibly |
| Pydantic | Output validation | Schema enforcement before DB writes |
| APScheduler | In-app scheduling | No Airflow overhead for one daily job |

**Intentionally excluded:** Airflow (one pipeline), Kubernetes (single service),
Kafka (one daily event), vector database (no semantic search needed),
feature store (no model training).

---

## Pipeline cadence

**Phase 1 (first 90 days):** daily at 22:00 UTC
**Phase 2 (90+ days):** weekly, every Monday 22:00 UTC

To switch — no code change needed:
```bash
# In railway.toml startCommand, change cron reference
# Rename .github/workflows/daily_pipeline.yml → .disabled
```

---

## Quick start

```bash
git clone https://github.com/zhenna/media-divergence-oil-price-signal
cd media-divergence-oil-price-signal

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env          # fill in your keys
cp railway.toml.example railway.toml   # fill in for Railway deploy

# One-time historical backfill
python scripts/backfill_prices.py      # WTI + Brent 2020–present

# Run locally
uvicorn backend.main:app --reload
# Open http://localhost:8000
```

---

## Environment variables

| Variable | Description | Where to get it |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI key for PressLens scoring | platform.openai.com |
| `PRESSLENS_URL` | PressLens deployment URL | your Railway PressLens app |
| `DATABASE_URL` | PostgreSQL connection string | neon.tech |
| `PIPELINE_CADENCE` | `daily` or `weekly` | set manually |
| `MLFLOW_TRACKING_URI` | DagsHub MLflow endpoint | dagshub.com |
| `LANGCHAIN_API_KEY` | LangSmith tracing key | smith.langchain.com |

---

## Deploy

See [DEPLOY.md](DEPLOY.md) for full Railway deployment instructions.

**Note:** `railway.toml` is gitignored — it contains your API key inline
due to a Railway Beta Runtime V2 variable injection bug.
Copy `railway.toml.example` → `railway.toml` and fill in your values.

---

## Tests

```bash
pytest tests/ -v
# No API keys required — tests use synthetic data
```

---

## Limitations

**Correlation ≠ causation.** Both polarization and prices respond to the same
underlying geopolitical events — not necessarily one causing the other.

**GDELT vs PressLens scoring.** Historical analysis uses GDELT tone scores
(dictionary-based). Live analysis uses PressLens 6-dimension LLM scoring.
The two methods are compared for the overlapping period.

**LLM Western training bias.** GPT-4o mini was trained on predominantly
English-language Western text. RT and CGTN scores may be systematically
inflated compared to a truly neutral baseline.

**Sample size.** 90 days gives ~90 data points. Directionally meaningful,
not publication-quality research.

---

## Related

- [PressLens](https://github.com/zhenna/presslens-media-bias-analyzer) — the bias scoring engine this project consumes
- [Blog post](https://medium.com/@luzhenna) — technical writeup

---

## License
MIT
