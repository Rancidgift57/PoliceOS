"""
CRAG Step 1 + 2: Retrieval + Evaluator/Grader.

Retrieval here is deliberately simple (a dict lookup against the player's
game state) rather than a vector search, because the "documents" being
retrieved are small, structured, per-case objects (evidence + alibi), not an
open corpus. The correction/grading step is where the real CRAG behavior
lives: a strict, low-temperature LLM call that must ground its verdict in
the retrieved evidence and is not allowed to invent evidence that wasn't
unlocked.

Runs on OpenRouter (any model string OpenRouter serves) via llm_client.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import List

from backend.cache import cache_get_json, cache_set_json
from backend.llm_client import EVALUATOR_MODEL, structured_completion
from backend.schemas import EvidenceEvaluation, EvidenceItem

logger = logging.getLogger("crag.evaluator")

# The evaluator runs at temperature 0 with a fully-specified prompt, so the
# same (evidence, alibi, message) triple always grades the same way. Caching
# it cuts LLM spend on the common case of a player re-sending a near-
# identical accusation, or retrying after a typo doesn't change the verdict.
EVAL_CACHE_TTL_SECONDS = 60 * 10


def _retrieve_context(unlocked_evidence: List[EvidenceItem]) -> str:
    """Step 1 (Retrieval): format only the evidence the player has actually
    unlocked. Locked evidence is never shown to the evaluator, so the model
    can't accidentally credit the player for something they haven't earned."""
    if not unlocked_evidence:
        return "(The player has not unlocked any evidence yet.)"
    return json.dumps(
        [{"id": e.id, "detail": e.detail} for e in unlocked_evidence],
        indent=2,
    )


def _cache_key(player_message: str, unlocked_evidence: List[EvidenceItem], suspect_alibi: str) -> str:
    fingerprint = json.dumps(
        {
            "message": player_message.strip().lower(),
            "evidence": sorted(e.id for e in unlocked_evidence),
            "alibi": suspect_alibi,
        },
        sort_keys=True,
    )
    digest = hashlib.sha256(fingerprint.encode()).hexdigest()[:24]
    return f"eval_cache:{digest}"


async def evaluate_player_message(
    player_message: str,
    unlocked_evidence: List[EvidenceItem],
    suspect_alibi: str,
) -> EvidenceEvaluation:
    """Step 2 (Evaluator/Grader): binary, evidence-grounded verdict.

    Runs at temperature 0 with a strict JSON-mode schema so the grading
    decision can never leak into the player-facing narrative voice, and so
    downstream routing logic (Step 3) can branch on a clean boolean instead
    of parsing free text. Checks a short-lived cache first.
    """
    cache_key = _cache_key(player_message, unlocked_evidence, suspect_alibi)
    cached = await cache_get_json(cache_key)
    if cached is not None:
        logger.info("CRAG eval | cache hit")
        return EvidenceEvaluation.model_validate(cached)

    evidence_context = _retrieve_context(unlocked_evidence)

    system_prompt = f"""You are an impartial forensic evaluator inside a detective game.
Your ONLY job is to grade whether the player's interrogation message legitimately
uses evidence they have unlocked to contradict the suspect's current alibi.

CURRENT SUSPECT ALIBI:
{suspect_alibi}

PLAYER'S UNLOCKED EVIDENCE (the ONLY evidence you may credit them for):
{evidence_context}

GRADING RULES:
1. The player must EXPLICITLY reference the substance of a piece of unlocked evidence.
   Vague accusations, guesses, or bluffing do not count, even if they happen to be true.
2. Evidence the player has NOT unlocked must never be credited, even if the player
   somehow guesses it correctly.
3. The referenced evidence must actually create a logical contradiction with the
   CURRENT alibi text above, not just be generally related to the suspect.
4. Return the ids of every unlocked evidence item the message actually referenced.
5. Be strict. When in doubt, grade it as not using valid evidence.
"""

    evaluation = await structured_completion(
        schema=EvidenceEvaluation,
        system_prompt=system_prompt,
        user_prompt=f"Player message: {player_message}",
        model=EVALUATOR_MODEL,
        temperature=0.0,
        max_tokens=400,
    )

    logger.info(
        "CRAG eval | trap_successful=%s referenced=%s reasoning=%s",
        evaluation.trap_successful,
        evaluation.referenced_evidence_ids,
        evaluation.reasoning,
    )
    await cache_set_json(cache_key, evaluation.model_dump(mode="json"), ttl_seconds=EVAL_CACHE_TTL_SECONDS)
    return evaluation
