"""
FastAPI entry point.

Starts the APScheduler pipeline on app startup UNLESS
DISABLE_SCHEDULER=true is set (used on Railway where
GitHub Actions handles the pipeline instead).
"""
import os
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.api.routes import router
from backend.services.db import init_db

FRONTEND_DIR = Path(__file__).parent.parent / "frontend" / "src"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialise database tables
    init_db()

    # Only start scheduler if not disabled
    # Set DISABLE_SCHEDULER=true on Railway — GitHub Actions handles the pipeline
    if not os.environ.get("DISABLE_SCHEDULER", "").lower() in ("true", "1", "yes"):
        from pipeline.scheduler import start_scheduler
        from pipeline.scheduler import run_pipeline
        start_scheduler()
        asyncio.create_task(run_pipeline())
    else:
        print("[Scheduler] Disabled — pipeline managed by GitHub Actions")

    yield


app = FastAPI(
    title="Geopolitical Media Market Signals",
    description=(
        "Does narrative polarization between global outlets "
        "predict market volatility better than any single outlet's sentiment? "
        "Powered by PressLens bias scoring."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")

# Serve frontend
if FRONTEND_DIR.exists():
    @app.get("/", include_in_schema=False)
    async def serve_index():
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        return FileResponse(FRONTEND_DIR / "index.html")
