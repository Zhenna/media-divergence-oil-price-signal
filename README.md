# media-divergence-oil-price-signal

> When RT and Al Jazeera tell a different story from Reuters and BBC, does oil move? A data pipeline that measures narrative divergence across global press and correlates it with WTI crude prices — daily, automated, statistically tested.

Live demo: **[TBC-railway-url]**
Built on top of: [PressLens](https://github.com/zhenna/presslens-media-bias-analyzer)

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

Three hypotheses tested daily against accumulating data:

**H1 — Confirmatory**
Narrative polarization between non-Western (RT, Al Jazeera, CGTN) and Western
(Reuters, BBC, NY Times) outlets predicts WTI crude oil price movement better
than any single outlet's mean sentiment score.

**H2 — Exploratory**
WTI crude rises within 48 hours of a polarization spike even when Reuters
scores below 3 — consistent with algorithmic trading on anticipated supply risk
rather than realized supply disruption.

**H3 — Exploratory**
The directional spread between non-Western cluster mean and Western cluster mean
is a stronger oil predictor than overall outlet standard deviation alone.

See the live dashboard for current hypothesis status, correlation charts,
and plain-English analysis of each result.

---

## What it tracks

**Topic:** Iran US Conflict

**Outlets — two clusters:**
```
Non-Western: RT (RU) · Al Jazeera (QA) · CGTN (CN)
Western:     Reuters (INT) · BBC (GB) · NY Times (US)
```

**Markets:** WTI Crude Oil · Brent Crude

**Key historical events used to validate data:**
- Jan 3 2020 — Soleimani assassination (+6% oil)
- Jul 15 2022 — JCPOA talks collapse (+2% oil)
- Apr 14 2024 — Iran direct strike on Israel (+4% oil)

---

## Architecture

```
Google BigQuery (one-time)
    └── GDELT historical data 2020–present ──► Neon PostgreSQL

GitHub Actions (daily at 22:00 UTC)
    ├── pytest tests (gate — pipeline only runs if tests pass)
    ├── PressLens API ──► bias scores ──────────► Neon PostgreSQL
    ├── yfinance ──────► WTI + Brent prices ───► Neon PostgreSQL
    ├── polarization engine (scipy) ────────────► Neon PostgreSQL
    └── hypothesis tests ──► MLflow (DagsHub) ──► Neon PostgreSQL

Railway (always-on)
    └── FastAPI dashboard ──► reads Neon ──► Plotly.js charts

LangSmith
    └── traces every PressLens API call (cost, latency, schema pass rate)
```

---

## MLOps stack

| Tool | Purpose | Why this tool |
|---|---|---|
| GitHub Actions | Daily pipeline + CI/CD | Tests gate every run; workflow file is version-controlled |
| Neon PostgreSQL | Time-series storage | Serverless, scales to zero, accessible from Actions + Railway |
| LangSmith | LLM call tracing | Cost, latency, schema pass rate per run — free tier |
| DagsHub MLflow | Experiment tracking | Every hypothesis test logged as a reproducible experiment |
| Pydantic | Output validation | Schema enforcement before any data reaches the database |
| APScheduler | In-app scheduling | Embedded in FastAPI — no separate Airflow infrastructure |

**What's intentionally excluded:**
- Airflow — one pipeline, one schedule; APScheduler is sufficient
- Kubernetes — single service, Railway handles deployment
- Kafka — one event per day; a cron job is the right tool
- Vector database — aggregated daily scores, no semantic search needed
- Feature store — no model training; PostgreSQL tables serve this role

---

## Pipeline cadence

**Phase 1 (first 90 days):** daily at 22:00 UTC
Builds time-series data fast enough to test all three hypotheses.

**Phase 2 (90+ days):** weekly, every Monday at 22:00 UTC
Market data is daily OHLCV — weekly scoring adds no analytical loss
once correlations are established.

To switch phases — no code change needed:
```bash
# In Railway environment variables
PIPELINE_CADENCE=weekly

# In GitHub repo
git mv .github/workflows/daily_pipeline.yml .github/workflows/daily_pipeline.yml.disabled
git push
```

---

## Quick start

```bash
git clone https://github.com/zhenna/media-divergence-oil-price-signal
cd media-divergence-oil-price-signal

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Edit .env: add PRESSLENS_API_KEY, DATABASE_URL, LANGCHAIN_API_KEY

# One-time historical backfill
python scripts/backfill_prices.py     # WTI + Brent, 2020–present (~30s)
python scripts/backfill_gdelt.py      # Iran coverage via BigQuery (~5min)

# Start the app
uvicorn backend.main:app --reload
# Open http://localhost:8000
```

---

## Environment variables

| Variable | Description | Where to get it |
|---|---|---|
| `PRESSLENS_API_KEY` | OpenAI key for PressLens scoring | platform.openai.com |
| `PRESSLENS_URL` | PressLens deployment URL | your Railway PressLens app |
| `DATABASE_URL` | PostgreSQL connection string | neon.tech |
| `PIPELINE_CADENCE` | `daily` or `weekly` | set manually |
| `MLFLOW_TRACKING_URI` | DagsHub MLflow endpoint | dagshub.com |
| `MLFLOW_TRACKING_USERNAME` | DagsHub username | dagshub.com |
| `MLFLOW_TRACKING_PASSWORD` | DagsHub token | dagshub.com → Settings |
| `LANGCHAIN_API_KEY` | LangSmith API key | smith.langchain.com |
| `LANGCHAIN_PROJECT` | LangSmith project name | set manually |

---

## Deploy

```bash
# Railway
railway login && railway init && railway up
# Add PostgreSQL addon in Railway dashboard
# Set all environment variables above

# GitHub Actions runs automatically at 22:00 UTC
# Add secrets: Settings → Secrets → Actions
```

Full instructions: [DEPLOY.md](DEPLOY.md)

---

## Tests

```bash
pytest tests/ -v
```

No API keys required — tests use synthetic data only.

---

## Limitations

**Correlation is not causation.** Both polarization and prices may respond
to the same underlying event rather than one causing the other.

**GDELT vs PressLens scoring.** Historical analysis uses GDELT tone scores
(dictionary-based) as a polarization proxy. Live analysis uses PressLens
6-dimension LLM scoring. The two methods are compared directly for the
overlapping period to validate consistency.

**LLM Western training bias.** PressLens scores are generated by GPT-4o mini,
trained predominantly on English-language Western text. RT and CGTN scores
may be systematically inflated. See PressLens limitations for detail.

**Sample size.** 90 days of daily data gives ~90 data points per outlet.
Sufficient for directional findings, not publication-quality research.

---

## Related

- [PressLens](https://github.com/zhenna/presslens-media-bias-analyzer) — media bias analyzer this project consumes
- [Blog post](https://medium.com/@luzhenna) — technical writeup

---

## License
MIT
