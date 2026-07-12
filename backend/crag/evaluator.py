"""
CRAG Step 1 + 2: Retrieval + Evaluator/Grader - now entirely rule-based.

This used to be a live, low-temperature LLM call per interrogation turn.
It's now a lookup against each evidence item's pre-generated "trigger
phrases" (see backend/crag/dialogue_bank.py, generated once per case at
creation time and stored via state_store.save_dialogue_bank). Retrieval is
still deliberately simple (a dict lookup against the player's game state,
not a vector search) for the same reason as before: the "documents" are
small, structured, per-case objects, not an open corpus.

Why this is safe to make rule-based: the trigger phrases were written by
an LLM that saw the full evidence detail and case narrative, covering the
natural ways a player might phrase an accusation - grading is just "does
the player's message contain (or closely paraphrase) one of these
pre-vetted phrases", which is exactly what the old LLM call was doing
turn-by-turn, just computed once in advance instead of live every time.
"""
from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import List

from backend.schemas import EvidenceEvaluation, EvidenceItem
from backend.state_store import get_dialogue_bank

logger = logging.getLogger("crag.evaluator")

_WORD_RE = re.compile(r"[a-z0-9']+")

# A trigger phrase counts as matched if it appears verbatim, OR if the
# player's message shares this fraction or more of the phrase's words
# (order-independent), which catches minor paraphrasing without needing
# an LLM call to judge semantic similarity.
_WORD_OVERLAP_THRESHOLD = 0.7
# Fallback for single-longer-phrase near-misses (typos, word order swaps):
# a straight sequence-similarity ratio against the normalized message.
_SEQUENCE_SIMILARITY_THRESHOLD = 0.85


def _normalize(text: str) -> str:
    return " ".join(_WORD_RE.findall(text.lower()))


def _phrase_matches(message_norm: str, phrase_norm: str) -> bool:
    if not phrase_norm:
        return False
    if phrase_norm in message_norm:
        return True

    phrase_words = set(phrase_norm.split())
    if phrase_words:
        message_words = set(message_norm.split())
        overlap = len(phrase_words & message_words) / len(phrase_words)
        if overlap >= _WORD_OVERLAP_THRESHOLD:
            return True

    return SequenceMatcher(None, phrase_norm, message_norm).ratio() >= _SEQUENCE_SIMILARITY_THRESHOLD


async def evaluate_player_message(
    player_message: str,
    unlocked_evidence: List[EvidenceItem],
    suspect_alibi: str,
    case_id: str,
    current_layer_requires_evidence_id: str,
) -> EvidenceEvaluation:
    """Grades whether the player's message legitimately cites a piece of
    UNLOCKED evidence, and whether that citation is the specific evidence
    needed to break the suspect's CURRENT alibi layer.

    Locked evidence is never checked against - only evidence the player has
    actually unlocked is considered, same guarantee the old LLM prompt
    enforced by simply never being shown locked evidence in its context.
    """
    message_norm = _normalize(player_message)
    bank = await get_dialogue_bank(case_id)

    referenced: List[str] = []
    for evidence in unlocked_evidence:
        phrases = bank.evidence_triggers.get(evidence.id, [])
        if any(_phrase_matches(message_norm, _normalize(p)) for p in phrases):
            referenced.append(evidence.id)

    uses_valid_evidence = len(referenced) > 0
    contradicts_alibi = current_layer_requires_evidence_id in referenced

    if contradicts_alibi:
        reasoning = f"Message cited evidence '{current_layer_requires_evidence_id}', which breaks the current layer."
    elif uses_valid_evidence:
        reasoning = f"Message cited {referenced}, but not the evidence this layer needs ({current_layer_requires_evidence_id})."
    else:
        reasoning = "Message didn't match any trigger phrase for the player's unlocked evidence."

    logger.info(
        "CRAG eval (rule-based) | referenced=%s contradicts_alibi=%s", referenced, contradicts_alibi
    )

    return EvidenceEvaluation(
        referenced_evidence_ids=referenced,
        uses_valid_evidence=uses_valid_evidence,
        contradicts_alibi=contradicts_alibi,
        reasoning=reasoning,
    )
