"""
FastAPI entry point.

Railway serves the dashboard only.
The daily pipeline runs via GitHub Actions (see .github/workflows/daily_pipeline.yml).
"""
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
    init_db()
    print("[App] Dashboard ready — pipeline runs via GitHub Actions at 22:00 UTC")
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

if FRONTEND_DIR.exists():
    @app.get("/", include_in_schema=False)
    async def serve_index():
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        return FileResponse(FRONTEND_DIR / "index.html")
