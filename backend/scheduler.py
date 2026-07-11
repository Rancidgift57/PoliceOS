"""
Midnight rotation.

Every night at 00:00 IST (Asia/Kolkata - this is an Indian-themed game, so
the day boundary follows Indian time regardless of where the backend
happens to be hosted), a fresh daily case is generated exactly like the
manual /api/admin/generate-daily-case trigger already did. The only new
behaviour is bookkeeping around the case that's rotating OUT:

  - For every registered officer (player) who had opened that outgoing
    case but not solved it, the case_id is filed into their personal
    "pending challenges" backlog (backend/state_store.get_pending_case_ids)
    so they can come back and finish it later without it ever being lost.
  - The new case becomes "today's case" and also shows up for everyone
    else as a "new challenge" the moment they next open the Case Files
    board, simply by virtue of being the newest entry in the case archive
    that they have no saved player state against yet.

Uses APScheduler's AsyncIOScheduler so it runs in-process alongside
uvicorn - no separate cron/worker process required for local dev or a
single-instance deploy. For a multi-instance production deploy, prefer
triggering /api/admin/generate-daily-case from an external scheduler (see
DEPLOYMENT.md) and simply not starting this in-process one, to avoid two
instances both firing at midnight.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.generation.daily_case import generate_daily_case
from backend.state_store import add_pending_case, get_latest_case_id, has_player_state, get_player_state

logger = logging.getLogger("scheduler")

_scheduler: AsyncIOScheduler | None = None


async def rotate_daily_case() -> None:
    try:
        outgoing_case_id = await get_latest_case_id()
    except KeyError:
        outgoing_case_id = None

    if outgoing_case_id is not None:
        # Local import avoids a circular import (auth -> db -> ... at module
        # load time); scheduler is the only place that needs the user list.
        from backend.auth import list_all_player_ids

        player_ids = await list_all_player_ids()
        for player_id in player_ids:
            if not await has_player_state(player_id, outgoing_case_id):
                continue  # never opened - nothing to file as pending
            state = await get_player_state(player_id, outgoing_case_id)
            if not state.case_solved:
                await add_pending_case(player_id, outgoing_case_id)
                logger.info("Filed unsolved case %s into %s's pending backlog", outgoing_case_id, player_id)

    new_case = await generate_daily_case()
    logger.info("Midnight rotation complete. New case: %s (%s)", new_case.case_id, new_case.codename)


def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
    _scheduler.add_job(rotate_daily_case, CronTrigger(hour=0, minute=0, timezone="Asia/Kolkata"), id="midnight_rotation")
    _scheduler.start()
    logger.info("Midnight rotation scheduler started (00:00 Asia/Kolkata)")


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
