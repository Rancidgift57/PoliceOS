"""
Player-facing hints - now a pre-generated-text lookup instead of a live LLM
call per hint request.

Both hint variants (evidence not found yet / evidence found but not used
directly enough) are written once per suspect-layer at case-generation
time by backend/crag/dialogue_bank.py and stored in the DialogueBank. This
function just looks the right one up; it never talks to an LLM provider.
"""
from __future__ import annotations

from typing import Optional

from backend.state_store import get_dialogue_bank

_FALLBACK_HINT_LOCKED = "You're missing something. Work another lead before coming back to this one."
_FALLBACK_HINT_UNLOCKED = "You have what you need - be more direct about it."


async def generate_hint(
    case_id: str,
    suspect_id: str,
    layer_index: int,
    evidence_unlocked: bool,
) -> str:
    bank = await get_dialogue_bank(case_id)
    layer_bank = bank.suspects.get(suspect_id, {}).get(str(layer_index))

    if layer_bank is None:
        return _FALLBACK_HINT_UNLOCKED if evidence_unlocked else _FALLBACK_HINT_LOCKED

    hint = layer_bank.hint_unlocked if evidence_unlocked else layer_bank.hint_locked
    return hint or (_FALLBACK_HINT_UNLOCKED if evidence_unlocked else _FALLBACK_HINT_LOCKED)
