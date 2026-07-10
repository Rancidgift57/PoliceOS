"""
Small async cache/counter abstraction shared by evaluator caching, session
state, and rate limiting.

Uses Redis (`redis.asyncio`) if `REDIS_URL` is set - this is what you want
in production, since it survives backend restarts and works across multiple
backend instances. Falls back to a process-local in-memory store otherwise,
so local dev and `docker compose up` work with zero extra setup.

Both backends expose the same tiny interface (get/set/incr/delete), so
nothing above this layer needs to know which one is active.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Optional


class _InMemoryBackend:
    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, Optional[float]]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[str]:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if expires_at is not None and time.monotonic() > expires_at:
                del self._store[key]
                return None
            return value

    async def set(self, key: str, value: str, ttl_seconds: Optional[int] = None) -> None:
        async with self._lock:
            expires_at = time.monotonic() + ttl_seconds if ttl_seconds else None
            self._store[key] = (value, expires_at)

    async def incr(self, key: str, ttl_seconds: Optional[int] = None) -> int:
        async with self._lock:
            entry = self._store.get(key)
            now = time.monotonic()
            if entry is None or (entry[1] is not None and now > entry[1]):
                count = 1
                expires_at = now + ttl_seconds if ttl_seconds else None
            else:
                count = int(entry[0]) + 1
                expires_at = entry[1]
            self._store[key] = (str(count), expires_at)
            return count

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._store.pop(key, None)


class _RedisBackend:
    def __init__(self, url: str) -> None:
        import redis.asyncio as redis  # imported lazily so redis is optional at runtime

        self._client = redis.from_url(url, decode_responses=True)

    async def get(self, key: str) -> Optional[str]:
        return await self._client.get(key)

    async def set(self, key: str, value: str, ttl_seconds: Optional[int] = None) -> None:
        await self._client.set(key, value, ex=ttl_seconds)

    async def incr(self, key: str, ttl_seconds: Optional[int] = None) -> int:
        count = await self._client.incr(key)
        if count == 1 and ttl_seconds:
            await self._client.expire(key, ttl_seconds)
        return count

    async def delete(self, key: str) -> None:
        await self._client.delete(key)


_REDIS_URL = os.environ.get("REDIS_URL")
_backend = _RedisBackend(_REDIS_URL) if _REDIS_URL else _InMemoryBackend()


async def cache_get_json(key: str) -> Optional[Any]:
    raw = await _backend.get(key)
    return json.loads(raw) if raw is not None else None


async def cache_set_json(key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
    await _backend.set(key, json.dumps(value), ttl_seconds)


async def cache_get(key: str) -> Optional[str]:
    return await _backend.get(key)


async def cache_set(key: str, value: str, ttl_seconds: Optional[int] = None) -> None:
    await _backend.set(key, value, ttl_seconds)


async def cache_incr(key: str, ttl_seconds: Optional[int] = None) -> int:
    return await _backend.incr(key, ttl_seconds)


async def cache_delete(key: str) -> None:
    await _backend.delete(key)


def using_redis() -> bool:
    return isinstance(_backend, _RedisBackend)
