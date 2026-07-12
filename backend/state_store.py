"""
Persistence layer for case files, player state, and leaderboards.

Goes through backend/cache.py, which is Redis-backed when REDIS_URL is set
and an in-memory dict otherwise - so this module doesn't know or care which
one is active. Case files are cached with no TTL (they're small and finite,
one per day); player state gets a generous TTL so abandoned sessions don't
accumulate forever in Redis.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import List, Optional

from backend.cache import cache_get_json, cache_incr, cache_set_json
from backend.schemas import CaseFile, DailyLeaderboard, DialogueBank, LeaderboardEntry, PlayerState, PlayerStats

PLAYER_STATE_TTL_SECONDS = 60 * 60 * 24 * 3  # 3 days - plenty for a daily game
_LATEST_CASE_KEY = "case:latest_id"
_CASE_ID_DATE_RE = re.compile(r"^case_(\d{8})_")


async def save_case_file(case_file: CaseFile) -> None:
    await cache_set_json(f"case:{case_file.case_id}", case_file.model_dump(mode="json"))
    if not case_file.is_tutorial:
        # The tutorial is a fixed, always-available case, not part of the
        # rotating daily lineup, so it never becomes "latest" and never
        # shows up in the new/pending archive.
        await cache_set_json(_LATEST_CASE_KEY, case_file.case_id)
        await add_case_to_archive(case_file)


async def get_case_file(case_id: str) -> CaseFile:
    raw = await cache_get_json(f"case:{case_id}")
    if raw is None:
        raise KeyError(f"No case file loaded for case_id={case_id!r}")
    return CaseFile.model_validate(raw)


async def save_dialogue_bank(bank: DialogueBank) -> None:
    """The pre-generated denial lines / hints / evidence trigger-phrases
    for a case (see backend/crag/dialogue_bank.py), stored right alongside
    the case file itself so interrogation, hints, and grading can all read
    it back with a plain cache lookup instead of calling the LLM."""
    await cache_set_json(f"case:{bank.case_id}:dialogue_bank", bank.model_dump(mode="json"))


async def get_dialogue_bank(case_id: str) -> DialogueBank:
    """Returns an empty (but valid) bank if none was generated - this only
    happens for a case that was already in flight when this feature
    shipped. Rule-based code downstream falls back to each suspect's
    authored public_text/reveal_text and a generic mentor line in that
    case, rather than crashing."""
    raw = await cache_get_json(f"case:{case_id}:dialogue_bank")
    if raw is None:
        return DialogueBank(case_id=case_id)
    return DialogueBank.model_validate(raw)


async def get_latest_case_id() -> str:
    case_id = await cache_get_json(_LATEST_CASE_KEY)
    if case_id is None:
        raise KeyError("No active case file exists yet; run the daily generator first")
    return case_id


def _player_key(player_id: str, case_id: str) -> str:
    return f"player:{player_id}:{case_id}"


async def get_player_state(player_id: str, case_id: Optional[str] = None) -> PlayerState:
    """State is keyed per (player, case) so a player can have independent,
    simultaneous progress on the tutorial, today's case, and any backlog of
    unsolved past cases sitting in their "pending challenges" list -
    starting the tutorial doesn't touch today's case progress, and vice
    versa. If case_id is omitted, defaults to whatever case is currently
    latest (this is what all the existing single-case call sites want)."""
    resolved_case_id = case_id or await get_latest_case_id()
    raw = await cache_get_json(_player_key(player_id, resolved_case_id))
    if raw is not None:
        return PlayerState.model_validate(raw)

    state = PlayerState(player_id=player_id, case_id=resolved_case_id)
    await save_player_state(state)
    return state


async def save_player_state(state: PlayerState) -> None:
    await cache_set_json(
        _player_key(state.player_id, state.case_id),
        state.model_dump(mode="json"),
        ttl_seconds=PLAYER_STATE_TTL_SECONDS,
    )


async def has_player_state(player_id: str, case_id: str) -> bool:
    """True only if the player has actually touched this case (i.e. state
    was persisted) - used to distinguish "new, never opened" cases from
    ones with saved-but-unsolved progress."""
    raw = await cache_get_json(_player_key(player_id, case_id))
    return raw is not None


# --------------------------------------------------------------------------- #
# Case archive - a running list of every case ever generated (title,
# codename, date), so the Case Files board can list "new" and "pending"
# cases without downloading each one's full payload.
# --------------------------------------------------------------------------- #

_CASE_ARCHIVE_KEY = "case:archive_ids"


async def add_case_to_archive(case_file: CaseFile) -> None:
    ids: List[str] = await cache_get_json(_CASE_ARCHIVE_KEY) or []
    if case_file.case_id not in ids:
        ids.append(case_file.case_id)
        await cache_set_json(_CASE_ARCHIVE_KEY, ids)


async def list_archived_case_ids() -> List[str]:
    return await cache_get_json(_CASE_ARCHIVE_KEY) or []


# --------------------------------------------------------------------------- #
# Pending-challenges backlog - per player list of case_ids they had open but
# hadn't solved when the daily rotation moved on. Populated by
# backend/scheduler.py at midnight; cleared automatically the moment that
# case is solved (see record_case_solved below).
# --------------------------------------------------------------------------- #

def _pending_key(player_id: str) -> str:
    return f"player:{player_id}:pending_case_ids"


async def get_pending_case_ids(player_id: str) -> List[str]:
    return await cache_get_json(_pending_key(player_id)) or []


async def add_pending_case(player_id: str, case_id: str) -> None:
    pending = await get_pending_case_ids(player_id)
    if case_id not in pending:
        pending.append(case_id)
        await cache_set_json(_pending_key(player_id), pending)


async def remove_pending_case(player_id: str, case_id: str) -> None:
    pending = await get_pending_case_ids(player_id)
    if case_id in pending:
        pending.remove(case_id)
        await cache_set_json(_pending_key(player_id), pending)


# --------------------------------------------------------------------------- #
# Leaderboard / streaks
# --------------------------------------------------------------------------- #

async def get_player_stats(player_id: str) -> PlayerStats:
    raw = await cache_get_json(f"stats:{player_id}")
    if raw is not None:
        return PlayerStats.model_validate(raw)
    return PlayerStats(player_id=player_id)


async def _save_player_stats(stats: PlayerStats) -> None:
    await cache_set_json(f"stats:{stats.player_id}", stats.model_dump(mode="json"))


def _case_date(case_id: Optional[str]) -> Optional[date]:
    """Parses the YYYYMMDD embedded in case ids of the form
    'case_20260710_a1b2c3' (see generation/daily_case.py). Returns None for
    malformed/legacy ids rather than raising, since streak logic should
    degrade gracefully rather than crash on an unexpected id shape."""
    if not case_id:
        return None
    match = _CASE_ID_DATE_RE.match(case_id)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d").date()
    except ValueError:
        return None


async def record_case_solved(state: PlayerState) -> PlayerStats:
    """Called once, when a player's case flips to solved. Streak logic uses
    the actual calendar date embedded in each case_id (not just "was it a
    different case_id"):
      - no previous solve                    -> streak starts at 1
      - previous solve was exactly 1 day ago  -> streak continues (+1)
      - previous solve was the SAME day       -> streak unchanged (still
        counts as a solved case, e.g. if a day's case was regenerated)
      - previous solve was >1 day ago, or
        either date is unparseable            -> streak resets to 1
    """
    stats = await get_player_stats(state.player_id)

    if stats.last_solved_case_id != state.case_id:
        current_date = _case_date(state.case_id)
        last_date = _case_date(stats.last_solved_case_id)

        if last_date is None:
            stats.current_streak = 1
        elif current_date is not None:
            day_gap = (current_date - last_date).days
            if day_gap == 1:
                stats.current_streak += 1
            elif day_gap == 0:
                pass  # same calendar day, e.g. a regenerated case - streak unchanged
            else:
                stats.current_streak = 1
        else:
            # Can't parse the current case's date - fail safe rather than
            # silently inflating a streak on malformed input.
            stats.current_streak = 1

        stats.longest_streak = max(stats.longest_streak, stats.current_streak)
        stats.total_cases_solved += 1
        stats.last_solved_case_id = state.case_id
        await _save_player_stats(stats)

    entry = LeaderboardEntry(
        player_id=state.player_id,
        case_id=state.case_id,
        submission_attempts=state.submission_attempts,
        interrogation_attempts=state.interrogation_attempts,
        solved_at=state.solved_at or datetime.now(timezone.utc),
    )
    rank = await cache_incr(f"leaderboard:{state.case_id}:next_rank")
    await cache_set_json(f"leaderboard:{state.case_id}:entry:{rank}", entry.model_dump(mode="json"))
    await cache_set_json(f"leaderboard:{state.case_id}:count", rank)

    await remove_pending_case(state.player_id, state.case_id)

    return stats


async def get_daily_leaderboard(case_id: str, limit: int = 20) -> DailyLeaderboard:
    count = await cache_get_json(f"leaderboard:{case_id}:count") or 0
    entries: List[LeaderboardEntry] = []
    for rank in range(1, count + 1):
        raw = await cache_get_json(f"leaderboard:{case_id}:entry:{rank}")
        if raw:
            entries.append(LeaderboardEntry.model_validate(raw))

    # Best runs first: fewest total attempts, then earliest solve time.
    entries.sort(key=lambda e: (e.submission_attempts + e.interrogation_attempts, e.solved_at))
    return DailyLeaderboard(case_id=case_id, entries=entries[:limit])
