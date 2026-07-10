"""
Player-facing hints, built from the CRAG evaluator's internal `reasoning`
field (schemas.EvidenceEvaluation.reasoning) - previously computed every
turn but only ever logged, never surfaced.

Two failure modes get very different hints:
  1. The player hasn't unlocked the evidence this layer needs yet -> nudge
     them toward finding it (coding challenge or another suspect breaking),
     WITHOUT revealing what the evidence actually is.
  2. The player has the evidence unlocked but isn't using it explicitly/
     correctly enough -> nudge them to be more direct, naming the evidence's
     public label (not its full detail text) as a memory jog.

Both are separate LLM calls in the "detective mentor" voice, not the
suspect's voice - this is meta-game guidance, not in-fiction dialogue.
"""
from __future__ import annotations

from typing import Optional

from backend.llm_client import GENERATOR_MODEL, text_completion

HINT_MODEL = GENERATOR_MODEL


async def generate_hint(
    reasoning: str,
    required_evidence_label: Optional[str],
    evidence_unlocked: bool,
    suspect_name: str,
) -> str:
    if not evidence_unlocked:
        system_prompt = f"""You are a terse, experienced detective mentor giving a rookie a nudge.
The rookie is interrogating {suspect_name} but doesn't yet have the evidence needed to break
their current story. You know WHY (internal grading note below) but must NOT reveal what the
evidence actually is or where it comes from - only that they're missing something and should
keep working other leads (the coding terminal, other suspects) before coming back.

INTERNAL GRADING NOTE (never quote this directly, it's for your context only):
{reasoning}

Write ONE short sentence of in-world mentor advice. No meta-language like "evidence" or "clue" -
speak like a real detective giving field advice."""
    else:
        system_prompt = f"""You are a terse, experienced detective mentor giving a rookie a nudge.
The rookie is interrogating {suspect_name} and already has what they need, but isn't presenting
it clearly or directly enough to make it stick. You know WHY (internal grading note below).

INTERNAL GRADING NOTE (never quote this directly, it's for your context only):
{reasoning}

Something in your case file called "{required_evidence_label}" is the relevant lead - you may
reference that by name, but do not restate its exact contents or wording.

Write ONE short sentence of in-world mentor advice pushing them to use it more directly."""

    return await text_completion(
        system_prompt=system_prompt,
        user_prompt="Give the hint now.",
        model=HINT_MODEL,
        temperature=0.4,
        max_tokens=80,
    )
