"""
Filesystem anchors, computed from this file's own location rather than the
process's current working directory.

Every path in this project used to be built as a relative string like
"backend/generation/datasets", which only resolves correctly if you happen
to launch uvicorn from the project root. Run it from inside backend/ (or
any other directory) instead and every one of those breaks - most visibly
as `sqlite3.OperationalError: unable to open database file` or a poisoned
dataset "not found" error, depending on which path got hit first. Anchoring
to __file__ makes all of it independent of the caller's working directory.
"""
from __future__ import annotations

from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
