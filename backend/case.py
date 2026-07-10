"""
Public, read-only case endpoint. This is what useGameStore.initSession()
calls on load to get the current case file merged with the requesting
player's progress.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.state_store import get_case_file, get_latest_case_id, get_player_state

router = APIRouter(prefix="/api/case", tags=["case"])


@router.get("/current")
async def get_current_case(player_id: str) -> dict:
    try:
        case_id = await get_latest_case_id()
        case_file = await get_case_file(case_id)
    except KeyError:
        raise HTTPException(
            503,
            "No case has been generated yet. POST /api/admin/generate-daily-case first.",
        )

    player_state = await get_player_state(player_id)

    payload = case_file.model_dump(mode="json")
    payload["player_state"] = player_state.model_dump(mode="json")
    return payload
