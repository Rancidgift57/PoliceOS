"""
Read-only endpoints for daily leaderboards and player streaks. Writes
happen as a side effect of solving a case (see
crag/interrogation.py::_maybe_record_case_solved -> state_store.record_case_solved).
"""
from __future__ import annotations

from fastapi import APIRouter

from backend.schemas import DailyLeaderboard, PlayerStats
from backend.state_store import get_daily_leaderboard, get_player_stats

router = APIRouter(prefix="/api", tags=["leaderboard"])


@router.get("/leaderboard/{case_id}", response_model=DailyLeaderboard)
async def leaderboard(case_id: str, limit: int = 20) -> DailyLeaderboard:
    return await get_daily_leaderboard(case_id, limit=limit)


@router.get("/players/{player_id}/stats", response_model=PlayerStats)
async def player_stats(player_id: str) -> PlayerStats:
    return await get_player_stats(player_id)
