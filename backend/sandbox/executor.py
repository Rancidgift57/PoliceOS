"""
FastAPI-facing handler for the Database Terminal app. This is the piece the
frontend IDE pane calls when the player hits "Run".

Flow:
  1. Load the challenge's poisoned dataset + unit test spec from the case file.
  2. Ship the player's source + poisoned data into an isolated sandbox
     (self-managed Docker, or a hosted Piston instance - see SANDBOX_BACKEND
     below and sandbox/piston_runner.py for why you'd pick one over the other).
  3. Compare the harness output against the expected cleaning/algorithm
     results defined in the case file's unit_tests.
  4. On full success, unlock the evidence item tied to this challenge.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from backend.rate_limit import rate_limit
from backend.schemas import (
    CodeSubmission,
    ExecutionResult,
    ExecutionStatus,
)
from backend.state_store import get_case_file, get_player_state, save_player_state

logger = logging.getLogger("sandbox.executor")
router = APIRouter(prefix="/api/sandbox", tags=["sandbox"])

SANDBOX_RATE_LIMIT = rate_limit("sandbox", max_per_window=15)

DATASET_DIR = Path("backend/generation/datasets")  # populated by the daily generator

# "docker" (default): self-managed Docker daemon, see sandbox/docker_runner.py
#   and DEPLOYMENT.md Path A - requires a VPS you control.
# "piston": hosted code-execution API, see sandbox/piston_runner.py - no
#   Docker dependency at all, so the backend can run on serverless/edge
#   platforms. Set via .env: SANDBOX_BACKEND=piston
SANDBOX_BACKEND = os.environ.get("SANDBOX_BACKEND", "docker")

if SANDBOX_BACKEND == "piston":
    from backend.sandbox.piston_runner import SandboxTimeout, run_submission_in_piston as _run_submission
else:
    from backend.sandbox.docker_runner import SandboxTimeout, run_submission_in_docker as _run_submission

logger.info("Sandbox backend: %s", SANDBOX_BACKEND)


def _load_poisoned_dataset(dataset_url: str) -> list[dict[str, Any]]:
    """dataset_url is a case-relative path like 'datasets/case_042/txns.json',
    written by the daily generator alongside the rest of the case file."""
    path = DATASET_DIR.parent.parent / dataset_url  # backend/<dataset_url>
    with open(path) as f:
        return json.load(f)


def _grade(result: dict[str, Any], unit_tests: list[dict[str, Any]]) -> ExecutionResult:
    if result.get("error"):
        return ExecutionResult(status=ExecutionStatus.RUNTIME_ERROR, stderr=result["error"])

    cleaning_tests = [t for t in unit_tests if t["stage"] == "cleaning"]
    algorithm_tests = [t for t in unit_tests if t["stage"] == "algorithm"]

    cleaning_passed = sum(
        1 for t in cleaning_tests if result.get("cleaned_count") == t["expected_cleaned_count"]
    )
    if cleaning_tests and cleaning_passed < len(cleaning_tests):
        return ExecutionResult(
            status=ExecutionStatus.FAILED_CLEANING,
            cleaning_tests_passed=cleaning_passed,
            cleaning_tests_total=len(cleaning_tests),
            algorithm_tests_total=len(algorithm_tests),
            stdout=f"Expected cleaned record count did not match. Got {result.get('cleaned_count')}.",
        )

    algorithm_passed = sum(1 for t in algorithm_tests if result.get("answer") == t["expected_answer"])
    if algorithm_tests and algorithm_passed < len(algorithm_tests):
        return ExecutionResult(
            status=ExecutionStatus.FAILED_ALGORITHM,
            cleaning_tests_passed=cleaning_passed,
            cleaning_tests_total=len(cleaning_tests),
            algorithm_tests_passed=algorithm_passed,
            algorithm_tests_total=len(algorithm_tests),
            stdout=f"Algorithm output did not match expected answer. Got {result.get('answer')!r}.",
        )

    return ExecutionResult(
        status=ExecutionStatus.PASSED,
        cleaning_tests_passed=cleaning_passed,
        cleaning_tests_total=len(cleaning_tests),
        algorithm_tests_passed=algorithm_passed,
        algorithm_tests_total=len(algorithm_tests),
    )


@router.post("/execute", response_model=ExecutionResult, dependencies=[Depends(SANDBOX_RATE_LIMIT)])
async def execute_submission(submission: CodeSubmission) -> ExecutionResult:
    case_file = await get_case_file(submission.case_id)
    challenge = next((c for c in case_file.challenges if c.id == submission.challenge_id), None)
    if challenge is None:
        raise HTTPException(404, f"Challenge '{submission.challenge_id}' not found")

    player_state = await get_player_state(submission.player_id)
    player_state.submission_attempts += 1

    poisoned_dataset = _load_poisoned_dataset(challenge.poisoned_dataset_url)

    start = time.monotonic()
    try:
        raw_result = await _run_submission(submission.source_code, poisoned_dataset)
    except SandboxTimeout:
        await save_player_state(player_state)
        return ExecutionResult(status=ExecutionStatus.TIMEOUT, stderr="Execution exceeded the time limit.")
    runtime_ms = int((time.monotonic() - start) * 1000)

    graded = _grade(raw_result, challenge.unit_tests)
    graded.runtime_ms = runtime_ms

    if graded.status == ExecutionStatus.PASSED:
        if challenge.id not in player_state.solved_challenge_ids:
            player_state.solved_challenge_ids.append(challenge.id)
            if challenge.unlocks_evidence_id not in player_state.unlocked_evidence_ids:
                player_state.unlocked_evidence_ids.append(challenge.unlocks_evidence_id)
                graded.unlocked_evidence_id = challenge.unlocks_evidence_id

    await save_player_state(player_state)

    logger.info(
        "Sandbox run | player=%s challenge=%s status=%s runtime_ms=%d",
        submission.player_id, submission.challenge_id, graded.status, runtime_ms,
    )
    return graded
