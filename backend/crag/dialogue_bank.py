"""
Pre-generates everything interrogation needs to run WITHOUT a live LLM call
per player message: each suspect's per-layer denial lines and hint text,
plus per-evidence "trigger phrases" used to grade whether a player message
actually cites that evidence.

This runs exactly ONCE per case, at generation time (see
backend/generation/daily_case.py and backend/generation/tutorial_case.py),
in a single batched structured_completion call covering every suspect,
every layer, and every evidence item at once - not one call per suspect
and not one call per layer. That's the entire point: a day's worth of
interrogation (which could otherwise be dozens of separate evaluator +
generator + hint calls as players interrogate suspects) collapses into one
generation-time call, with the result cached in the same store as the case
file itself (see state_store.save_dialogue_bank/get_dialogue_bank).

At runtime, backend/crag/evaluator.py, generator.py, and hints.py all
become pure dict lookups against the stored DialogueBank - no player
message ever gets sent to an LLM provider, which is also what makes the
interrogation loop immune to "API sniffing" (there's no outbound request
containing the player's message or the case's secrets to intercept).
"""
from __future__ import annotations

import logging
from typing import Dict, List

from pydantic import BaseModel, Field

from backend.llm_client import NARRATIVE_MODEL, structured_completion
from backend.schemas import CaseFile, DialogueBank, LayerDialogue

logger = logging.getLogger("crag.dialogue_bank")


class _LayerDialogueDraft(BaseModel):
    layer_index: int
    denial_lines: List[str] = Field(
        min_length=3, max_length=5,
        description="3-5 short in-character deflection lines used while this layer is unbroken. "
                    "Vary phrasing/tone across them so repeating one doesn't feel robotic.",
    )
    hint_locked: str = Field(
        description="One sentence of terse detective-mentor advice for when the player hasn't found "
                    "the evidence this layer needs yet. No meta-words like 'evidence' or 'clue'."
    )
    hint_unlocked: str = Field(
        description="One sentence of terse detective-mentor advice for when the player HAS the "
                    "evidence but isn't presenting it directly enough to make it stick."
    )


class _SuspectDialogueDraft(BaseModel):
    suspect_id: str
    layers: List[_LayerDialogueDraft]


class _EvidenceTriggerDraft(BaseModel):
    evidence_id: str
    trigger_phrases: List[str] = Field(
        min_length=3, max_length=6,
        description="Short lowercase phrases/keywords (3-8 words each) that, if a player's message "
                    "contains one (word-for-word or close paraphrase), should count as citing this "
                    "specific evidence. Cover the natural ways a player might phrase the accusation.",
    )


class _DialogueBankDraft(BaseModel):
    suspects: List[_SuspectDialogueDraft]
    evidence_triggers: List[_EvidenceTriggerDraft]


def _build_prompt(case_file: CaseFile) -> str:
    suspect_briefs = []
    for s in case_file.suspects:
        layer_briefs = "\n".join(
            f"    layer {l.layer_index}: public_text={l.public_text!r} | "
            f"reveal_text={l.reveal_text!r} | requires_evidence_id={l.requires_evidence_id!r}"
            for l in s.alibi_layers
        )
        suspect_briefs.append(
            f"- id={s.id!r} name={s.name!r} personality={s.personality!r}\n{layer_briefs}"
        )

    evidence_briefs = "\n".join(
        f"- id={e.id!r} label={e.label!r} detail={e.detail!r}" for e in case_file.evidence
    )

    return f"""Case: {case_file.title}
{case_file.narrative_intro}

SUSPECTS (with their existing alibi layers - do not change these, just write dialogue for them):
{chr(10).join(suspect_briefs)}

EVIDENCE (already unlockable in the case, you're writing trigger phrases for grading):
{evidence_briefs}

For EVERY suspect and EVERY one of their layers, write a _LayerDialogueDraft: several denial
lines matching that suspect's personality (used verbatim while the layer holds, so make them
distinct from each other), plus the two hint variants.

For EVERY evidence item, write an _EvidenceTriggerDraft: short phrases a player might plausibly
type when confronting a suspect with that evidence. Keep phrases lowercase and specific to the
evidence's actual content (not generic phrases like "i have evidence").

Output must match the required schema exactly - one entry per suspect (with one layer-entry per
existing alibi layer) and one entry per evidence item, no more, no fewer."""


async def generate_dialogue_bank(case_file: CaseFile) -> DialogueBank:
    draft = await structured_completion(
        schema=_DialogueBankDraft,
        system_prompt=(
            "You write supporting dialogue and grading phrases for a noir detective game's "
            "interrogation system. You are NOT writing the case itself (already written) - only "
            "filling in denial lines, mentor hints, and evidence trigger phrases for it."
        ),
        user_prompt=_build_prompt(case_file),
        model=NARRATIVE_MODEL,
        temperature=0.8,
        max_tokens=1800,
    )

    suspects: Dict[str, Dict[str, LayerDialogue]] = {}
    for sd in draft.suspects:
        suspects[sd.suspect_id] = {
            str(ld.layer_index): LayerDialogue(
                denial_lines=ld.denial_lines,
                hint_locked=ld.hint_locked,
                hint_unlocked=ld.hint_unlocked,
            )
            for ld in sd.layers
        }

    evidence_triggers: Dict[str, List[str]] = {
        et.evidence_id: [p.lower().strip() for p in et.trigger_phrases] for et in draft.evidence_triggers
    }

    bank = DialogueBank(case_id=case_file.case_id, suspects=suspects, evidence_triggers=evidence_triggers)
    logger.info(
        "Generated dialogue bank for %s: %d suspects, %d evidence trigger sets",
        case_file.case_id, len(suspects), len(evidence_triggers),
    )
    return bank
