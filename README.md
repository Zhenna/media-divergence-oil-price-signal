# media-divergence-oil-price-signal

> Does narrative divergence between non-Western and Western outlets track oil price movements after a geopolitical shock? Six months of automated LLM scoring across RT, Al Jazeera, CGTN, Reuters, BBC and NY Times — tested against WTI crude during the 2026 Iran war.

**Live dashboard:** [media-divergence-oil-price-signal-production.up.railway.app](https://media-divergence-oil-price-signal-production.up.railway.app)
**Blog post:** [Iran, Oil, and the Narrative Gap](BLOG_URL_PLACEHOLDER)
**Built on top of:** [PressLens](https://github.com/zhenna/presslens-media-bias-analyzer) — LLM-based media bias scorer

---

## Finding

The biggest oil spike in forty years happened while media polarization was at its lowest — all six outlets converged on the same undisputed fact (Hormuz closure). After the shock, the directional gap between non-Western and Western outlet clusters showed a statistically significant correlation with WTI at 3-day lag (r = 0.329, p = 0.011): when non-Western outlets stayed more alarmed than Western outlets after a ceasefire, oil prices remained elevated longer.

Kinetic events drive oil prices. Narrative divergence is a secondary signal that tracks how markets interpret what comes next. Full analysis in the [blog post](BLOG_URL_PLACEHOLDER).

---

## Architecture

```
Google BigQuery (one-time)
    └── GDELT historical Iran coverage 2020–present ──► Neon PostgreSQL

GitHub Actions (weekly at 22:00 UTC Monday)
    ├── pytest gate — pipeline only runs if tests pass
    ├── PressLens API ──► bias scores (6 outlets × 6 dimensions) ──► Neon
    ├── yfinance ──────► WTI, Brent, Gold, VIX prices ───────────► Neon
    ├── polarization engine ────────────────────────────────────► Neon
    └── hypothesis tests ──► DagsHub MLflow ────────────────────► Neon

Railway (always-on)
    └── FastAPI dashboard ──► reads Neon ──► Plotly.js annotated chart

LangSmith
    └── traces every PressLens API call (cost, latency, schema pass rate)
```

---

## Hypotheses tested

Three hypotheses tested using Pearson correlation at lag 0–7 days. Significance threshold p < 0.05. Sample: 87 days live data + GDELT historical backfill.

| | Hypothesis | r | p | Result |
|---|---|---|---|---|
| H1 | Polarization std dev predicts oil better than mean sentiment | 0.130 | 0.327 | Not supported |
| H2 | Anticipated shock premium on quiet Reuters days | 0.081 | 0.538 | Not supported |
| H3 | Directional cluster divergence (non-Western minus Western) | 0.329 | 0.011 | Significant |

H1 and H2 being unsupported is itself informative — during undeniable physical events (Hormuz closure), all outlets converge and polarization collapses as a signal. See the [blog post](BLOG_URL_PLACEHOLDER) for the full interpretation.

---

## MLOps stack

| Tool | Role |
|---|---|
| GitHub Actions | Weekly pipeline + CI/CD — tests gate every run |
| Neon PostgreSQL | Single database shared by pipeline (writes) and dashboard (reads) |
| PressLens API | LLM-based bias scoring — no scoring code duplicated here |
| GDELT + BigQuery | Historical backfill — 6 years of Iran coverage |
| DagsHub MLflow | Hypothesis test logging — every run is a reproducible experiment |
| LangSmith | LLM call tracing — cost, latency, schema pass rate |
| Railway | Always-on FastAPI dashboard |

**Intentionally excluded:** Airflow (one pipeline), Kubernetes (single service), Kafka (one weekly event), feature store (no model training).

---

## Quick start

```bash
git clone https://github.com/zhenna/media-divergence-oil-price-signal
cd media-divergence-oil-price-signal

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env    # fill in your keys

# One-time historical price backfill
python scripts/backfill_prices.py      # WTI + Brent 2020–present

# Optional — GDELT historical news backfill (requires Google Cloud)
# pip install google-cloud-bigquery
# export GOOGLE_APPLICATION_CREDENTIALS="/path/to/key.json"
# python scripts/backfill_gdelt.py
# python scripts/backfill_polarization.py

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

All secrets managed via GitHub Actions secrets — no secrets in code.

---

## Tests

```bash
pytest tests/ -v
# No API keys required — tests use synthetic data
```

---

## Limitations

- Correlation not causation — multiple mechanisms plausible, indistinguishable with this dataset
- One topic (Iran-US conflict), one commodity (WTI crude) — generalisability unknown
- LLM scoring bias — GPT-4o mini trained predominantly on Western English text
- GDELT historical data uses dictionary-based tone vs live LLM 6-dimension scoring

---

## Related

- [PressLens](https://github.com/zhenna/presslens-media-bias-analyzer) — the bias scoring engine this project consumes
- [Blog post](BLOG_URL_PLACEHOLDER) — full analysis and findings

---

## License
MIT
