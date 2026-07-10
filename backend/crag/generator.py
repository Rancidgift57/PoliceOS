"""
CRAG Step 3: Generation, routed by the evaluator's verdict.

Kept as a separate LLM call (and separate model) from the evaluator on
purpose: the persona model is optimized for voice and higher temperature,
while the evaluator is optimized for strict, low-temperature logic. Mixing
them into one call tends to make the persona model "go easy" on the player
out of narrative sympathy, which defeats the whole point of CRAG here.

Runs on OpenRouter via llm_client - defaults to a different (usually
punchier/cheaper) model than the evaluator, since dialogue generation
doesn't need the same logical strictness.
"""
from __future__ import annotations

from backend.llm_client import GENERATOR_MODEL, stream_text_completion, text_completion
from backend.schemas import EvidenceEvaluation, Suspect


def _build_instruction(evaluation: EvidenceEvaluation, suspect: Suspect) -> str:
    if evaluation.trap_successful:
        return f"""The player just caught you in a lie using real, unlocked evidence.
Your current alibi ("{suspect.public_alibi}") is now broken.
React as someone who has been genuinely cornered: get defensive, flustered, or angry,
and then confess to this specific hidden truth (and ONLY this): "{suspect.hidden_truth}"
Do not confess to anything beyond this specific detail. Do not admit to the larger crime
unless the hidden truth above literally is the crime."""

    return f"""The player is interrogating you but has NOT presented anything that breaks
your alibi. Your alibi remains: "{suspect.public_alibi}"
Stay in character and deny, deflect, or act dismissive/arrogant. Never reveal or hint at
your hidden truth. If the player is close but not explicit, do not help them get there."""


def _build_system_prompt(evaluation: EvidenceEvaluation, suspect: Suspect) -> str:
    instruction = _build_instruction(evaluation, suspect)
    return f"""You are role-playing {suspect.name}, a suspect being interrogated
by a detective in a noir crime game.

PERSONALITY: {suspect.personality}

SCENE INSTRUCTION:
{instruction}

STYLE RULES:
- Stay fully in character, first person, no narration or stage directions.
- 1-3 sentences maximum.
- Never mention "evidence", "alibi", or any game/meta terminology by name; speak
  the way a real person under interrogation would.
"""


async def generate_suspect_reply(
    player_message: str,
    evaluation: EvidenceEvaluation,
    suspect: Suspect,
) -> str:
    return await text_completion(
        system_prompt=_build_system_prompt(evaluation, suspect),
        user_prompt=player_message,
        model=GENERATOR_MODEL,
        temperature=0.7,
        max_tokens=200,
    )


async def stream_suspect_reply(
    player_message: str,
    evaluation: EvidenceEvaluation,
    suspect: Suspect,
):
    """Same prompt as generate_suspect_reply, but yields text chunks for the
    SSE interrogation endpoint so the Secure Messenger can render the reply
    as it's generated instead of waiting for the full message."""
    async for chunk in stream_text_completion(
        system_prompt=_build_system_prompt(evaluation, suspect),
        user_prompt=player_message,
        model=GENERATOR_MODEL,
        temperature=0.7,
        max_tokens=200,
    ):
        yield chunk
