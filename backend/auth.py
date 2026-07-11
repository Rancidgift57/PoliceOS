"""
Account system for Police OS, backed by Turso (see backend/db.py).

Deliberately small: username + password -> a durable player_id ("badge
number") that replaces the old anonymous localStorage UUID. Every other
endpoint in the app still just takes a player_id, so logging in doesn't
require touching case/sandbox/interrogation routes - it just gives the
frontend a stable, recoverable player_id instead of a throwaway one, and a
JWT so the frontend knows who's currently logged in.

Also registers every new user in the `users` table, which the daily
rotation scheduler (backend/scheduler.py) reads to know whose progress to
roll into the "pending challenges" backlog at midnight.
"""
from __future__ import annotations

import logging
import os
import random
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from backend import db
from backend.tokens import TokenError, make_token, verify_token

logger = logging.getLogger("auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])

JWT_TTL_DAYS = 30

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,24}$")

# Indian state/agency codes used to mint a flavorful, unique "badge number"
# for each new officer (player) instead of a bare UUID.
_STATE_CODES = ["MH", "DL", "KA", "TN", "WB", "UP", "RJ", "GJ", "KL", "PB", "AP", "TS"]


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=24)
    password: str = Field(min_length=6, max_length=128)
    display_name: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    token: str
    player_id: str
    username: str
    badge_number: str
    display_name: str


def _hash_password(password: str) -> str:
    # bcrypt has a hard 72-byte input limit; truncate defensively rather
    # than letting long passwords raise at hash time.
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], password_hash.encode("utf-8"))
    except ValueError:
        return False


def _mint_badge_number() -> str:
    return f"{random.choice(_STATE_CODES)}-DET-{random.randint(1000, 9999)}"


def _make_token(player_id: str, username: str) -> str:
    return make_token({"sub": player_id, "username": username}, ttl_days=JWT_TTL_DAYS)


def decode_token(token: str) -> dict:
    try:
        return verify_token(token)
    except TokenError as exc:
        raise HTTPException(401, "Invalid or expired session token") from exc


async def get_current_user(authorization: Optional[str] = Header(default=None)) -> dict:
    """FastAPI dependency for routes that need to know who's logged in.
    Not currently required by the gameplay routes (they stay reachable by
    player_id alone, same as before login existed) - available for any
    future route that should be auth-gated."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing bearer token")
    return decode_token(authorization.removeprefix("Bearer ").strip())


@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest) -> AuthResponse:
    if not _USERNAME_RE.match(req.username):
        raise HTTPException(400, "Username must be 3-24 characters: letters, numbers, _ . -")

    existing = await db.execute("SELECT id FROM users WHERE username = ?", [req.username])
    if existing.rows:
        raise HTTPException(409, "That username is already registered")

    player_id = uuid.uuid4().hex
    badge_number = _mint_badge_number()
    display_name = (req.display_name or req.username).strip()[:40]
    password_hash = _hash_password(req.password)

    await db.execute(
        "INSERT INTO users (id, username, badge_number, password_hash, display_name, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [player_id, req.username, badge_number, password_hash, display_name, datetime.now(timezone.utc).isoformat()],
    )
    logger.info("Registered new officer %s (badge %s)", req.username, badge_number)

    token = _make_token(player_id, req.username)
    return AuthResponse(
        token=token, player_id=player_id, username=req.username,
        badge_number=badge_number, display_name=display_name,
    )


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest) -> AuthResponse:
    result = await db.execute(
        "SELECT id, username, badge_number, password_hash, display_name FROM users WHERE username = ?",
        [req.username],
    )
    if not result.rows:
        raise HTTPException(401, "Unknown username or wrong password")

    row = result.rows[0]
    player_id, username, badge_number, password_hash, display_name = row[0], row[1], row[2], row[3], row[4]
    if not _verify_password(req.password, password_hash):
        raise HTTPException(401, "Unknown username or wrong password")

    token = _make_token(player_id, username)
    return AuthResponse(
        token=token, player_id=player_id, username=username,
        badge_number=badge_number, display_name=display_name,
    )


@router.get("/me", response_model=AuthResponse)
async def me(current=Depends(get_current_user)) -> AuthResponse:
    result = await db.execute(
        "SELECT id, username, badge_number, display_name FROM users WHERE id = ?",
        [current["sub"]],
    )
    if not result.rows:
        raise HTTPException(404, "Officer record not found")
    row = result.rows[0]
    return AuthResponse(token="", player_id=row[0], username=row[1], badge_number=row[2], display_name=row[3])


async def list_all_player_ids() -> list[str]:
    """Used by the midnight rotation scheduler to know every registered
    player whose progress on the outgoing case should be checked and, if
    unsolved, filed into their pending-challenges backlog."""
    result = await db.execute("SELECT id FROM users")
    return [row[0] for row in result.rows]
