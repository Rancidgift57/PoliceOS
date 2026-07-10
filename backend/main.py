"""
Police OS backend entrypoint.

    uvicorn backend.main:app --reload
"""
from __future__ import annotations

import logging

from dotenv import load_dotenv

load_dotenv()  # must run before backend.llm_client reads env vars at import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.crag.interrogation import router as interrogation_router
from backend.generation.daily_case import router as generation_router
from backend.leaderboard import router as leaderboard_router
from backend.sandbox.executor import router as sandbox_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Police OS Backend", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Next.js dev server
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(interrogation_router)
app.include_router(sandbox_router)
app.include_router(generation_router)
app.include_router(leaderboard_router)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}
