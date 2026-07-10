"""
Low-level Docker execution primitive.

Design goals:
- The player's code NEVER touches the host filesystem or network.
- Each run gets a fresh container (no reuse) so state can't leak between
  submissions, and the container is force-removed even on crash/timeout.
- Resource limits (memory, CPU, no network, read-only rootfs except /tmp)
  are applied at container-create time, not left to the image's defaults.
"""
from __future__ import annotations

import asyncio
import json
import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict

import docker
from docker.errors import ContainerError, ImageNotFound
from docker.types import Ulimit

logger = logging.getLogger("sandbox.docker_runner")

IMAGE = "police-os-sandbox:python3.11"  # pinned, prebuilt image - see Dockerfile below
TIMEOUT_SECONDS = 10
MEMORY_LIMIT = "256m"
CPU_QUOTA = 50_000  # 0.5 CPU (quota is in units of 1/100,000 CPU)

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = docker.from_env()
    return _client


class SandboxTimeout(Exception):
    pass


def _build_run_script(player_source: str) -> str:
    """Wraps the player's raw script with a harness that loads the poisoned
    dataset from /data/dataset.json, captures whatever the player's
    `clean_data` and `solve` functions return, and prints a single JSON
    result line the host process can parse deterministically. Wrapping like
    this means the player only ever has to write two plain functions and
    never touches file I/O or the test harness itself."""
    return f"""
import json, sys, traceback

result = {{"cleaned_count": None, "answer": None, "error": None}}

try:
    with open("/data/dataset.json") as f:
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


async def run_submission_in_docker(
    player_source: str,
    poisoned_dataset: list[dict[str, Any]],
) -> Dict[str, Any]:
    """Spins up an isolated container, injects the poisoned dataset + the
    player's wrapped script as read-only mounts, and returns the parsed
    harness output. Raises SandboxTimeout if the container exceeds the
    execution budget."""
    run_id = uuid.uuid4().hex[:12]

    with tempfile.TemporaryDirectory(prefix=f"police-os-{run_id}-") as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "dataset.json").write_text(json.dumps(poisoned_dataset))
        (tmp_path / "run.py").write_text(_build_run_script(player_source))

        loop = asyncio.get_event_loop()
        try:
            container = await loop.run_in_executor(
                None,
                lambda: _get_client().containers.run(
                    image=IMAGE,
                    command=["python", "/data/run.py"],
                    volumes={str(tmp_path): {"bind": "/data", "mode": "ro"}},
                    working_dir="/data",
                    network_disabled=True,
                    mem_limit=MEMORY_LIMIT,
                    nano_cpus=int(CPU_QUOTA * 10_000),  # convert quota->nanocpus roughly
                    pids_limit=64,
                    read_only=True,
                    tmpfs={"/tmp": "size=32m"},
                    ulimits=[Ulimit(name="nproc", soft=64, hard=64)],
                    detach=False,
                    remove=True,
                    stdout=True,
                    stderr=True,
                    name=f"police-os-run-{run_id}",
                ),
            )
        except ContainerError as exc:
            # Non-zero exit: still try to salvage stdout for a __RESULT__ line
            output = exc.stderr.decode() if exc.stderr else str(exc)
            return {"error": output, "cleaned_count": None, "answer": None}
        except ImageNotFound:
            logger.error("Sandbox image %s not found - build it first (see Dockerfile.sandbox)", IMAGE)
            raise
        except asyncio.TimeoutError as exc:
            raise SandboxTimeout(f"run {run_id} exceeded {TIMEOUT_SECONDS}s") from exc

        stdout = container.decode() if isinstance(container, bytes) else str(container)

    for line in stdout.splitlines():
        if line.startswith("__RESULT__"):
            return json.loads(line[len("__RESULT__"):])

    return {"error": f"No result line produced. Raw output:\n{stdout}", "cleaned_count": None, "answer": None}
