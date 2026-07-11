"""
Police OS backend entrypoint.

    uvicorn backend.main:app --reload
"""
from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

load_dotenv()  # must run before backend.llm_client reads env vars at import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend import db
from backend.auth import router as auth_router
from backend.case import router as case_router
from backend.crag.interrogation import router as interrogation_router
from backend.generation.daily_case import router as generation_router
from backend.generation.tutorial_case import ensure_tutorial_case_exists
from backend.leaderboard import router as leaderboard_router
from backend.sandbox.executor import router as sandbox_router
from backend.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main")

app = FastAPI(title="Police OS Backend", version="0.2.0")

# --------------------------------------------------------------------------- #
# CORS
#
# Previously hardcoded to a single localhost origin, which breaks the moment
# the frontend is deployed anywhere else (Vercel, etc) and also blocked
# credentialed requests (needed once login/JWT-bearing requests exist).
# FRONTEND_ORIGINS is a comma-separated list of exact allowed origins (set
# this to your deployed frontend URL(s) in production); allow_origin_regex
# additionally covers local dev on any port so http://localhost:3001 etc.
# still works without extra config.
# --------------------------------------------------------------------------- #
_default_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
_extra_origins = [o.strip() for o in os.environ.get("FRONTEND_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_default_origins + _extra_origins,
    allow_origin_regex=r"^https?://localhost(:\d+)?$|^https?://127\.0\.0\.1(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(case_router)
app.include_router(interrogation_router)
app.include_router(sandbox_router)
app.include_router(generation_router)
app.include_router(leaderboard_router)


@app.on_event("startup")
async def on_startup() -> None:
    await db.init_db()
    await ensure_tutorial_case_exists()
    start_scheduler()
    logger.info("Police OS backend ready.")


@app.on_event("shutdown")
async def on_shutdown() -> None:
    stop_scheduler()
    await db.close_db()


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}
