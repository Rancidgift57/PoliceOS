"""
Turso (libsql) client for durable user accounts.

Everything else in this project (case files, player progress, leaderboard)
deliberately lives in backend/cache.py's Redis-or-memory store, because it's
disposable, per-day, per-player scratch state. Accounts are different: a
username/password needs to survive process restarts and redeploys, so it
gets its own real database - Turso, an edge-hosted SQLite (libsql) service.

Falls back to a local SQLite file (via the same libsql client, using
"file:local.db") when TURSO_DATABASE_URL isn't set, so local dev works with
zero external setup - same philosophy as cache.py's in-memory fallback.
"""
from __future__ import annotations

import os
from typing import Any, Optional

import libsql_client

from backend.paths import BACKEND_DIR

_TURSO_URL = os.environ.get("TURSO_DATABASE_URL")
_TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN")

_client: Optional[libsql_client.Client] = None


def _make_client() -> libsql_client.Client:
    if _TURSO_URL:
        # libsql_client wants "libsql://..." (or "wss://...") for remote Turso
        # databases; accept either scheme the user pastes from the Turso CLI.
        url = _TURSO_URL.replace("https://", "libsql://", 1) if _TURSO_URL.startswith("https://") else _TURSO_URL
        return libsql_client.create_client(url=url, auth_token=_TURSO_TOKEN)
    # Local fallback: an on-disk SQLite file next to this module (backend/),
    # anchored by absolute path so it works no matter what directory uvicorn
    # was launched from - not "backend/local_users.db" relative to CWD.
    local_path = BACKEND_DIR / "local_users.db"
    return libsql_client.create_client(url=f"file:{local_path.as_posix()}")


def get_client() -> libsql_client.Client:
    global _client
    if _client is None:
        _client = _make_client()
    return _client


async def init_db() -> None:
    """Called once on FastAPI startup. Creates the users table if missing."""
    client = get_client()
    await client.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            badge_number TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )


async def execute(sql: str, args: Optional[list[Any]] = None):
    client = get_client()
    return await client.execute(sql, args or [])


async def close_db() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
