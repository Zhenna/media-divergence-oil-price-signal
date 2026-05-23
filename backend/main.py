"""
FastAPI entry point.

Starts the APScheduler pipeline on app startup.
Serves the analytics dashboard frontend.
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.api.routes import router
from backend.services.db import init_db
from pipeline.scheduler import start_scheduler, run_pipeline

FRONTEND_DIR = Path(__file__).parent.parent / "frontend" / "src"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialise database
    init_db()

    # Start scheduled pipeline
    start_scheduler()

    # Run pipeline once immediately on startup to populate data
    import asyncio
    asyncio.create_task(run_pipeline())

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
