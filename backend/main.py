"""FastAPI application entry point."""

import logging
import sys
from pathlib import Path

# Make the engine package importable (lives in sibling directory)
_ENGINE_DIR = Path(__file__).resolve().parent.parent
if str(_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(_ENGINE_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import CORS_ORIGINS
from database import init_db
from routes.auth import router as auth_router
from routes.stories import router as stories_router
from routes.tiers import router as tiers_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Unorthodox Writer API",
    version="0.1.0",
    description="Backend for the Unorthodox Writer text-to-story AI service.",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth_router)
app.include_router(stories_router)
app.include_router(tiers_router)


@app.on_event("startup")
def on_startup():
    logger.info("Initializing database...")
    init_db()
    logger.info("Database ready.")


@app.get("/api/health")
def health():
    return {"status": "ok"}
