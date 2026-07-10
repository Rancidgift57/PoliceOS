"""
Alternative to docker_runner.py: runs player submissions against Piston
(https://github.com/engineer-man/piston), a hosted code-execution API,
instead of a self-managed Docker daemon.

Why this matters for deployment: docker_runner.py requires a host with a
real Docker daemon it controls (see DEPLOYMENT.md Path A - a VPS). This
module has no such requirement - it's a plain HTTPS call - so choosing it
via SANDBOX_BACKEND=piston lets the whole backend run on serverless/edge
platforms (Vercel functions, Cloudflare Workers via a Python shim, AWS
Lambda, etc.) with zero container-orchestration infrastructure of your own.

Trade-offs vs. self-managed Docker:
- No control over resource limits, uptime, or queueing on the public
  instance - fine for a prototype/low-traffic game, not for guaranteed SLAs.
  Piston can be self-hosted too (their own Docker image) if you want the
  isolation guarantees back without the multi-tenant public queue.
- Same wrapped-harness approach as docker_runner.py (see _build_run_script),
  so the "player only writes clean_data/solve" contract is identical - the
  sandbox backend is swappable without touching the executor's grading logic.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict

import httpx

logger = logging.getLogger("sandbox.piston_runner")

PISTON_URL = os.environ.get("PISTON_URL", "https://emkc.org/api/v2/piston/execute")
PISTON_LANGUAGE = os.environ.get("PISTON_LANGUAGE", "python")
PISTON_VERSION = os.environ.get("PISTON_VERSION", "3.10.0")
TIMEOUT_SECONDS = 10


class SandboxTimeout(Exception):
    pass


def _build_run_script(player_source: str) -> str:
    """Identical harness contract to docker_runner._build_run_script: the
    player writes clean_data(records) and solve(cleaned), the harness
    handles all I/O and emits one parseable __RESULT__ line."""
    return f"""
import json, sys, traceback

result = {{"cleaned_count": None, "answer": None, "error": None}}

try:
    with open("dataset.json") as f:
        raw_records = json.load(f)

{_indent(player_source, 4)}

    cleaned = clean_data(raw_records)
    result["cleaned_count"] = len(cleaned)

    answer = solve(cleaned)
    result["answer"] = answer
except Exception:
    result["error"] = traceback.format_exc()

print("__RESULT__" + json.dumps(result))
"""


def _indent(text: str, spaces: int) -> str:
    pad = " " * spaces
    return "\n".join(pad + line for line in text.splitlines())


async def run_submission_in_piston(
    player_source: str,
    poisoned_dataset: list[dict[str, Any]],
) -> Dict[str, Any]:
    """Same return contract as docker_runner.run_submission_in_docker:
    {"cleaned_count": int|None, "answer": Any|None, "error": str|None}."""
    payload = {
        "language": PISTON_LANGUAGE,
        "version": PISTON_VERSION,
        "files": [
            {"name": "run.py", "content": _build_run_script(player_source)},
            {"name": "dataset.json", "content": json.dumps(poisoned_dataset)},
        ],
        "stdin": "",
        "run_timeout": TIMEOUT_SECONDS * 1000,
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS + 5) as client:
            response = await client.post(PISTON_URL, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException as exc:
        raise SandboxTimeout(f"Piston execution exceeded {TIMEOUT_SECONDS}s") from exc
    except httpx.HTTPError as exc:
        logger.error("Piston request failed: %s", exc)
        return {"error": f"Sandbox provider error: {exc}", "cleaned_count": None, "answer": None}

    run = data.get("run", {})
    stdout = run.get("stdout", "")
    stderr = run.get("stderr", "")

    for line in stdout.splitlines():
        if line.startswith("__RESULT__"):
            return json.loads(line[len("__RESULT__"):])

    error_detail = stderr or f"No result line produced. Raw stdout:\n{stdout}"
    return {"error": error_detail, "cleaned_count": None, "answer": None}
