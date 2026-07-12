"""
CRAG Step 3: Generation - now a pre-generated-line lookup instead of a live
LLM call per turn.

Previously this called the LLM on every single interrogation message (in
character, at temperature 0.7) to write the suspect's reply live. That's
replaced with:
  - On a layer BREAK: the suspect's authored `reveal_text` for that layer
    (already written at case-generation time, either by the LLM narrative
    call or hand-authored for the tutorial) - no generation needed, it's
    the confession text that already exists on the CaseFile.
  - On a non-breaking turn: one of that suspect/layer's pre-generated
    `denial_lines` from the dialogue bank (backend/crag/dialogue_bank.py),
    rotated by attempt count so repeated denials don't always show the
    same line, with a static fallback to the suspect's public alibi text
    if a bank somehow doesn't exist for this case (e.g. one generated
    before this feature shipped).

stream_suspect_reply keeps the same async-generator shape the SSE endpoint
expects, just yielding the pre-written line in word-chunks with a small
delay instead of streaming live tokens from a provider.
"""
from __future__ import annotations

import asyncio

from backend.schemas import AlibiLayer, EvidenceEvaluation, Suspect
from backend.state_store import get_dialogue_bank

# Small delay between word-chunks so the SSE stream still reads as a
# typed-out reply in the UI, instead of the whole line appearing at once.
_STREAM_WORD_DELAY_SECONDS = 0.035


async def _resolve_reply(
    case_id: str,
    suspect: Suspect,
    layer_index: int,
    current_layer: AlibiLayer,
    evaluation: EvidenceEvaluation,
    layer_break: bool,
    attempts_made: int,
) -> str:
    if layer_break:
        # The confession text for this layer already exists on the case
        # file - it's what the interrogation endpoint also stores as the
        # player's new visible alibi/reveal text, so reusing it here keeps
        # the messenger's displayed line consistent with that state.
        return current_layer.reveal_text

    bank = await get_dialogue_bank(case_id)
    layer_bank = bank.suspects.get(suspect.id, {}).get(str(layer_index))
    if layer_bank and layer_bank.denial_lines:
        return layer_bank.denial_lines[attempts_made % len(layer_bank.denial_lines)]

    # No bank for this case (pre-dialogue-bank case still in flight) -
    # fall back to restating the layer's own authored public text.
    return current_layer.public_text


async def generate_suspect_reply(
    case_id: str,
    suspect: Suspect,
    layer_index: int,
    current_layer: AlibiLayer,
    evaluation: EvidenceEvaluation,
    layer_break: bool,
    attempts_made: int,
) -> str:
    return await _resolve_reply(case_id, suspect, layer_index, current_layer, evaluation, layer_break, attempts_made)


async def stream_suspect_reply(
    case_id: str,
    suspect: Suspect,
    layer_index: int,
    current_layer: AlibiLayer,
    evaluation: EvidenceEvaluation,
    layer_break: bool,
    attempts_made: int,
):
    """Same resolution as generate_suspect_reply, yielded word-by-word so
    the Secure Messenger's existing SSE token-rendering keeps working
    unchanged even though there's no live model stream underneath anymore.
    """
    reply = await _resolve_reply(case_id, suspect, layer_index, current_layer, evaluation, layer_break, attempts_made)
    words = reply.split(" ")
    for i, word in enumerate(words):
        yield word if i == 0 else f" {word}"
        await asyncio.sleep(_STREAM_WORD_DELAY_SECONDS)
