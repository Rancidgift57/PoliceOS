"""
Public, read-only case endpoints. `/current` is what useGameStore.initSession()
calls on load; `/board` powers the Case Files app (tutorial / today / new /
pending challenges).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

from backend.generation.tutorial_case import TUTORIAL_CASE_ID
from backend.schemas import CaseSummary
from backend.state_store import (
    get_case_file,
    get_latest_case_id,
    get_pending_case_ids,
    get_player_state,
    has_player_state,
    list_archived_case_ids,
)

router = APIRouter(prefix="/api/case", tags=["case"])


@router.get("/current")
async def get_current_case(player_id: str, case_id: Optional[str] = None) -> dict:
    """Loads a specific case (tutorial, a pending backlog case, or any
    archived case) if `case_id` is given, otherwise today's latest case -
    merged with this player's progress against exactly that case."""
    try:
        resolved_case_id = case_id or await get_latest_case_id()
        case_file = await get_case_file(resolved_case_id)
    except KeyError:
        raise HTTPException(
            503,
            "No case has been generated yet. POST /api/admin/generate-daily-case first.",
        )

    player_state = await get_player_state(player_id, resolved_case_id)

    payload = case_file.model_dump(mode="json")
    payload["player_state"] = player_state.model_dump(mode="json")
    return payload


@router.get("/board")
async def get_case_board(player_id: str) -> dict:
    """Everything the Case Files app needs in one call:
      - tutorial: the fixed onboarding case + whether this player solved it
      - today: the current daily case
      - new_challenges: archived cases the player has never opened, newest first
      - pending_challenges: cases the player opened but hasn't solved
    """
    async def _summary(cid: str) -> Optional[CaseSummary]:
        try:
            cf = await get_case_file(cid)
        except KeyError:
            return None
        started = await has_player_state(player_id, cid)
        solved = False
        if started:
            solved = (await get_player_state(player_id, cid)).case_solved
        return CaseSummary(
            case_id=cf.case_id, title=cf.title, codename=cf.codename,
            generated_at=cf.generated_at, is_tutorial=cf.is_tutorial,
            solved=solved, started=started,
        )

    tutorial = await _summary(TUTORIAL_CASE_ID)

    try:
        today_id = await get_latest_case_id()
    except KeyError:
        today_id = None
    today = await _summary(today_id) if today_id else None

    archived_ids = await list_archived_case_ids()
    pending_ids = set(await get_pending_case_ids(player_id))

    new_challenges = []
    pending_challenges = []
    for cid in reversed(archived_ids):  # newest first
        if cid == today_id:
            continue
        summary = await _summary(cid)
        if summary is None:
            continue
        if cid in pending_ids and not summary.solved:
            pending_challenges.append(summary)
        elif not summary.started:
            new_challenges.append(summary)

    return {
        "tutorial": tutorial.model_dump(mode="json") if tutorial else None,
        "today": today.model_dump(mode="json") if today else None,
        "new_challenges": [s.model_dump(mode="json") for s in new_challenges],
        "pending_challenges": [s.model_dump(mode="json") for s in pending_challenges],
    }
