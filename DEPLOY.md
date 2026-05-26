# Deploying to Railway

## Prerequisites
- Railway account at [railway.app](https://railway.app)
- OpenAI API key at [platform.openai.com](https://platform.openai.com)
- Neon PostgreSQL at [neon.tech](https://neon.tech)
- DagsHub account at [dagshub.com](https://dagshub.com)
- LangSmith account at [smith.langchain.com](https://smith.langchain.com)

---

## Architecture

```
GitHub Actions (daily at 22:00 UTC)
    └── runs pipeline — reads secrets from GitHub secrets store
    └── writes results to Neon PostgreSQL

Railway (always-on)
    └── FastAPI serves dashboard only
    └── reads from Neon PostgreSQL
    └── no pipeline logic, no API keys needed
```

All secrets live in GitHub Actions secrets. Railway only serves the dashboard.

---

## Step 1 — Clone and configure

```bash
git clone https://github.com/zhenna/media-divergence-oil-price-signal
cd media-divergence-oil-price-signal

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env    # fill in your keys for local development
```

---

## Step 2 — Create Neon PostgreSQL database

1. Go to [neon.tech](https://neon.tech) → create project
2. Copy the **Public** connection string (includes `?sslmode=require`)
3. Add to `.env` as `DATABASE_URL`

---

## Step 3 — Run historical price backfill locally

```bash
export DATABASE_URL="postgresql://..."   # your Neon public URL

python scripts/backfill_prices.py
# Expected output:
# CL=F (WTI Crude Oil): 1608 days fetched
# BZ=F (Brent Crude Oil): 1609 days fetched
# Done — 6,432 records stored
#
# Verifying key events:
# 2020-01-06 (Soleimani +1d): $63.27
# 2022-07-18 (JCPOA +1d): $102.60
# 2024-04-15 (Iran strike +1d): $85.41
```

---

## Step 4 — Add GitHub Actions secrets

GitHub → your repo → **Settings → Secrets and variables → Actions → New repository secret**

| Secret | Value |
|---|---|
| `OPENAI_API_KEY` | your OpenAI key |
| `DATABASE_URL` | your Neon PostgreSQL URL |
| `LANGCHAIN_API_KEY` | your LangSmith key |
| `MLFLOW_TRACKING_URI` | `https://dagshub.com/Zhenna/media-divergence-oil-price-signal.mlflow` |
| `MLFLOW_TRACKING_USERNAME` | your DagsHub username |
| `MLFLOW_TRACKING_PASSWORD` | your DagsHub token |

The pipeline runs automatically at 22:00 UTC daily via `.github/workflows/daily_pipeline.yml`.

---

## Step 5 — Deploy to Railway

```bash
git push   # Railway auto-deploys from GitHub
```

Or manually:
1. Railway dashboard → **New Project** → **Deploy from GitHub repo**
2. Select `media-divergence-oil-price-signal`
3. Railway detects Python via RAILPACK builder automatically

Railway serves the dashboard only — no secrets needed.

---

## Step 6 — Add PostgreSQL addon

Railway dashboard → your project → **+ New** → **Database** → **PostgreSQL**

Railway injects `DATABASE_URL` automatically into your service.

---

## Step 7 — Generate public URL

Railway dashboard → your service → **Settings** → **Networking** → **Generate Domain**

---

## Step 8 — Verify deployment

```bash
# Should return Iran US Conflict with 6 outlets
curl https://media-divergence-oil-price-signal-production.up.railway.app/api/topics

# Check hypothesis status
curl https://media-divergence-oil-price-signal-production.up.railway.app/api/hypotheses
```

---

## Step 9 — Set up keep-alive (free tier)

Railway free tier sleeps after inactivity. Set up a free ping at [cron-job.org](https://cron-job.org):

```
URL:      https://media-divergence-oil-price-signal-production.up.railway.app/api/topics
Schedule: every 10 minutes
```

---

## Step 10 — Test the pipeline manually

GitHub → your repo → **Actions** → **Daily Pipeline** → **Run workflow**

Watch it run in real time. Expected output:
```
[PressLens] Iran US Conflict: 6 outlets scored
[yfinance] CL=F: 5 days fetched
[Pipeline] Daily run complete
```

---

## Pipeline cadence switch (Phase 1 → Phase 2)

After 90+ days of data, switch from daily to weekly:

```bash
# Disable daily workflow
git mv .github/workflows/daily_pipeline.yml \
       .github/workflows/daily_pipeline.yml.disabled

# Update cadence in railway.toml
# Change: PIPELINE_CADENCE = "daily"
# To:     PIPELINE_CADENCE = "weekly"

git add .
git commit -m "switch to weekly pipeline cadence"
git push
```

Weekly pipeline (`.github/workflows/weekly_pipeline.yml`) fires every Monday at 22:00 UTC automatically.

---

## Troubleshooting

**Pipeline scores 0 outlets:**
Check Actions logs for `[PressLens] Error 422`
→ API key not loading. Verify `OPENAI_API_KEY` is set in GitHub secrets.

**yfinance returning no data:**
Ensure `yfinance>=1.4.0` in `requirements.txt`.

**Healthcheck failure on Railway deploy:**
Increase `healthcheckTimeout` to 90 in `railway.toml`.

**Database connection error:**
Ensure `DATABASE_URL` uses the **public** Neon URL (not internal),
and includes `?sslmode=require` at the end.
