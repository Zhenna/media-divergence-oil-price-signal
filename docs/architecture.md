# Architecture

## Core hypothesis

> **Maximum polarization between outlets predicts market volatility
> better than any single outlet's sentiment score.**

Polarization = standard deviation of outlet scores across a bias dimension.
This measures narrative *distance* between outlets, not the tone of any one outlet.

When all outlets converge → low polarization → markets have clear information.
When outlets diverge sharply → high polarization → contested situation → uncertainty.

## Why polarization, not sentiment

Traditional financial NLP uses sentiment analysis:
- Score one source's text as positive/negative/neutral
- Correlate with price movement

This project tests a different signal:
- Measure how far apart *multiple* outlets are from each other
- Hypothesis: divergence signals uncertainty better than tone

The distinction matters because:
- A single outlet being "negative" is expected for RT on any US-related topic
- All outlets *simultaneously* shifting in divergent directions is unusual
- Unusual = information content = potential market signal

## System architecture

```
PressLens API (external)
    │
    │ POST /api/analyze
    │ Returns structured bias scores per outlet
    ▼
Pipeline (APScheduler, every 6h)
    │
    ├── presslens_client.py ──► fetch bias scores for tracked topics
    │
    ├── price_fetcher.py ─────► fetch market prices (yfinance)
    │
    └── PostgreSQL
          ├── bias_snapshots     (outlet scores over time)
          ├── market_prices      (daily OHLCV)
          ├── polarization_scores (std_dev per dimension per topic)
          └── correlations        (pre-computed Pearson r values)

Analytics Engine
    │
    ├── polarization.py ──► compute std_dev across outlets per dimension
    │
    └── correlation.py ───► Pearson r at lag 0,1,2,3,5,7 days
                            Tests polarization vs mean sentiment

FastAPI Backend
    │
    ├── GET /api/hypothesis/{topic}   ← the headline endpoint
    ├── GET /api/timeseries/{topic}/{symbol}
    ├── GET /api/correlations/{topic}
    └── GET /api/topics, /api/markets

Frontend (Plotly.js)
    ├── Dual time-series chart (polarization + price)
    ├── Correlation heatmap (dimensions × symbols)
    ├── Lag analysis chart (r at different lags)
    └── Hypothesis verdict card
```

## No code duplication

This repo calls PressLens as an external API.
All LLM prompt engineering, outlet registry, and bias scoring logic
lives in the PressLens repo: https://github.com/yourname/presslens-media-bias-analyzer

This repo is purely: pipeline + storage + analytics + visualisation.

## Deployment

One Railway project, two services:
- `geopolitical-media-market-signals` (this FastAPI app)
- PostgreSQL addon (free, 1GB)

Set environment variables in Railway:
- `PRESSLENS_API_KEY` — your Claude or OpenAI key
- `DATABASE_URL` — auto-injected by Railway PostgreSQL addon
