# Deploying to Railway

## Prerequisites
- Railway account at [railway.app](https://railway.app)
- OpenAI API key at [platform.openai.com](https://platform.openai.com)
- Neon PostgreSQL at [neon.tech](https://neon.tech)
- DagsHub account at [dagshub.com](https://dagshub.com)
- LangSmith account at [smith.langchain.com](https://smith.langchain.com)

---

## Step 1 — Clone and configure

```bash
git clone https://github.com/zhenna/media-divergence-oil-price-signal
cd media-divergence-oil-price-signal

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
cp railway.toml.example railway.toml
# Edit railway.toml — fill in your actual keys
```

---

## Step 2 — Create Neon PostgreSQL database

1. Go to [neon.tech](https://neon.tech) → create project
2. Copy the **Public** connection string (includes `?sslmode=require`)
3. Add to `railway.toml` and `.env`

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
# 2020-01-06 (Soleimani +1d): $63.27   ← confirms data is correct
# 2022-07-18 (JCPOA +1d): $102.60
# 2024-04-15 (Iran strike +1d): $85.41
```

---

## Step 4 — Push to GitHub

```bash
git add .
git commit -m "initial"
git push
```

---

## Step 5 — Deploy to Railway

1. Go to [railway.app](https://railway.app) → **New Project**
2. Select **Deploy from GitHub repo**
3. Choose `media-divergence-oil-price-signal`
4. Railway detects Python via RAILPACK builder automatically

---

## Step 6 — Add PostgreSQL addon

Railway dashboard → your project → **+ New** → **Database** → **PostgreSQL**

Railway injects `DATABASE_URL` automatically into your service.

---

## Step 7 — Generate public URL

Railway dashboard → your service → **Settings** → **Networking** → **Generate Domain**

Your URL: `https://media-divergence-oil-price-signal-production.up.railway.app`

---

## Step 8 — Verify deployment

```bash
# Should return Iran US Conflict with 6 outlets
curl https://your-url.up.railway.app/api/topics

# Trigger first pipeline run
curl -X POST https://your-url.up.railway.app/api/pipeline/run

# Check hypothesis status
curl https://your-url.up.railway.app/api/hypotheses
```

Watch Railway deploy logs for:
```
[PressLens] api_key resolved: length=164
[PressLens] Iran US Conflict: 6 outlets scored
[Pipeline] Daily run complete
```

---

## Step 9 — Set up keep-alive (free tier)

Railway free tier sleeps after inactivity. Set up a free ping at [cron-job.org](https://cron-job.org):

```
URL:      https://your-url.up.railway.app/api/topics
Schedule: every 10 minutes
```

---

## Step 10 — Set up GitHub Actions

Add these secrets to your GitHub repo:
**Settings → Secrets and variables → Actions → New repository secret**

```
PRESSLENS_API_KEY     your OpenAI key
DATABASE_URL          your Neon PostgreSQL URL
LANGCHAIN_API_KEY     your LangSmith key
MLFLOW_TRACKING_URI   https://dagshub.com/zhenna/media-divergence-oil-price-signal.mlflow
MLFLOW_TRACKING_USERNAME  zhenna
MLFLOW_TRACKING_PASSWORD  your DagsHub token
```

GitHub Actions runs the pipeline daily at 22:00 UTC as a backup to the Railway APScheduler.

---

## Pipeline cadence switch (Phase 1 → Phase 2)

After 90+ days of data, switch from daily to weekly:

**1. Update `railway.toml` startCommand** — no cron change needed, APScheduler reads `PIPELINE_CADENCE`

**2. Disable daily GitHub Actions workflow:**
```bash
git mv .github/workflows/daily_pipeline.yml .github/workflows/daily_pipeline.yml.disabled
git add .
git commit -m "switch to weekly pipeline cadence"
git push
```

**3. Railway environment** — already set in `railway.toml`:
```toml
PIPELINE_CADENCE = "weekly"
```

---

## Important note on Railway variable injection

Railway's Beta Runtime V2 blocks dashboard variable injection into the container.
The workaround is to pass secrets inline in `startCommand`:

```toml
[deploy]
startCommand = "OPENAI_API_KEY=sk-xxx uvicorn backend.main:app --host 0.0.0.0 --port $PORT"
```

This is why `railway.toml` is gitignored — it contains your live API key.
**Never commit `railway.toml` to a public repo.**
Use `railway.toml.example` as the committed template.

---

## Troubleshooting

**Pipeline scores 0 outlets:**
Check Railway logs for `[PressLens] api_key resolved: length=0`
→ API key not loading. Verify it's in `startCommand` in `railway.toml`.

**yfinance returning no data:**
```bash
pip install --upgrade yfinance  # ensure >= 1.4.0
```

**Healthcheck failure on deploy:**
Increase `healthcheckTimeout` in `railway.toml` to 90.

**Database connection error:**
Ensure `DATABASE_URL` uses the **public** Neon URL (not internal),
and includes `?sslmode=require` at the end.
