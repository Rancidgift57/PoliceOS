"""
FastAPI-facing handler for the Database Terminal app.

Execution model: the player's Python runs entirely client-side in the
browser via Pyodide (CPython compiled to WebAssembly) - see
frontend/src/lib/pyodideRunner.js. The backend never runs player source
code, so there's no Docker daemon and no third-party code-execution API
(e.g. Piston) dependency at all.

Flow:
  1. GET /dataset/{case_id}/{challenge_id} - frontend fetches the poisoned
     dataset for the active challenge so it can hand it to the player's
     code inside Pyodide.
  2. Player code runs locally in the browser sandbox. The frontend harness
     produces {cleaned_count, answer, error} exactly like the old
     docker/piston harness did.
  3. POST /execute - frontend submits those already-computed results
     (plus the source, for audit/leaderboard logging - it is NOT re-run).
     The backend grades them against the case file's unit_tests, which are
     never sent to the client, so the expected answers stay secret even
     though execution itself happens off-server.
  4. On full success, unlock the evidence item tied to this challenge.
"""
from __future__ import annotations

import json
import logging
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


def _load_poisoned_dataset(dataset_url: str) -> list[dict[str, Any]]:
    """dataset_url is a case-relative path like 'datasets/case_042/txns.json',
    written by the daily generator alongside the rest of the case file."""
    path = DATASET_DIR.parent.parent / dataset_url  # backend/<dataset_url>
    with open(path) as f:
        return json.load(f)


@router.get("/dataset/{case_id}/{challenge_id}")
async def get_poisoned_dataset(case_id: str, challenge_id: str) -> list[dict[str, Any]]:
    """Public: the poisoned dataset is the puzzle input the player is meant
    to clean, not an answer key, so it's safe to serve directly to the
    browser for the Pyodide runner to consume."""
    case_file = await get_case_file(case_id)
    challenge = next((c for c in case_file.challenges if c.id == challenge_id), None)
    if challenge is None:
        raise HTTPException(404, f"Challenge '{challenge_id}' not found")
    return _load_poisoned_dataset(challenge.poisoned_dataset_url)


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

    player_state = await get_player_state(submission.player_id, submission.case_id)
    player_state.submission_attempts += 1

    # Execution already happened client-side in the browser (Pyodide). We
    # only grade what came back - never run submission.source_code here.
    raw_result = {
        "cleaned_count": submission.cleaned_count,
        "answer": submission.answer,
        "error": submission.error,
    }

    graded = _grade(raw_result, challenge.unit_tests)
    graded.runtime_ms = submission.client_runtime_ms

    if graded.status == ExecutionStatus.PASSED:
        if challenge.id not in player_state.solved_challenge_ids:
            player_state.solved_challenge_ids.append(challenge.id)
            if challenge.unlocks_evidence_id not in player_state.unlocked_evidence_ids:
                player_state.unlocked_evidence_ids.append(challenge.unlocks_evidence_id)
                graded.unlocked_evidence_id = challenge.unlocks_evidence_id

    await save_player_state(player_state)

    logger.info(
        "Sandbox run (client-executed) | player=%s challenge=%s status=%s runtime_ms=%s src_len=%d",
        submission.player_id, submission.challenge_id, graded.status,
        submission.client_runtime_ms, len(submission.source_code or ""),
    )
    return graded
