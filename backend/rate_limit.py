"""
Per-player rate limiting for the two LLM/compute-costing endpoints
(interrogation messages, code submissions). Both cost real money per call,
so nothing should let a script hammer them.

Fixed-window counter, not a sliding log - simpler, and precise-enough for
this: a burst right at a window boundary is an acceptable tradeoff for not
needing sorted-set bookkeeping.
"""
from __future__ import annotations

from fastapi import HTTPException, Request

from backend.cache import cache_incr

WINDOW_SECONDS = 60


def rate_limit(scope: str, max_per_window: int):
    """Returns a FastAPI dependency that rate-limits `player_id` (read from
    the request body) to `max_per_window` calls per WINDOW_SECONDS for the
    given `scope` (e.g. 'interrogation', 'sandbox')."""

    async def _dependency(request: Request) -> None:
        body = await request.json()
        player_id = body.get("player_id", "anonymous")
        key = f"ratelimit:{scope}:{player_id}"
        count = await cache_incr(key, ttl_seconds=WINDOW_SECONDS)
        if count > max_per_window:
            raise HTTPException(
                status_code=429,
                detail=f"Too many {scope} requests - wait a moment before trying again.",
            )

    return _dependency
