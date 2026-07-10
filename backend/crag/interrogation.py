"""
Orchestrates the full CRAG loop for a single interrogation turn and exposes
it as FastAPI routes: a plain JSON endpoint, an SSE streaming one, and a
hint endpoint that reuses the evaluator's internal reasoning. This is the
module the frontend's Secure Messenger app calls directly.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from backend.crag.evaluator import evaluate_player_message
from backend.crag.generator import generate_suspect_reply, stream_suspect_reply
from backend.crag.hints import generate_hint
from backend.rate_limit import rate_limit
from backend.schemas import HintRequest, HintResponse, InterrogationRequest, InterrogationResponse
from backend.state_store import (
    get_case_file,
    get_player_state,
    record_case_solved,
    save_player_state,
)

logger = logging.getLogger("crag.interrogation")
router = APIRouter(prefix="/api/interrogation", tags=["interrogation"])

INTERROGATION_RATE_LIMIT = rate_limit("interrogation", max_per_window=20)
HINT_RATE_LIMIT = rate_limit("hint", max_per_window=10)

# How many consecutive non-breaking messages at the CURRENT layer before a
# hint becomes available. Resets to 0 the moment any layer breaks, so hints
# are earned per-layer, not just once per suspect.
HINT_THRESHOLD = 3


async def _prepare_turn(req: InterrogationRequest):
    """Shared setup for both the JSON and streaming endpoints: load state,
    resolve the suspect and their current (unbroken) layer, and grade the
    message. Returns everything the two routes need to diverge on generation."""
    player_state = await get_player_state(req.player_id)
    case_file = await get_case_file(player_state.case_id)

    suspect = next((s for s in case_file.suspects if s.id == req.suspect_id), None)
    if suspect is None:
        raise HTTPException(404, f"Suspect '{req.suspect_id}' not found in case '{case_file.case_id}'")
    if not suspect.alibi_layers:
        raise HTTPException(500, f"Suspect '{req.suspect_id}' has no alibi layers configured")

    layer_index = player_state.suspect_layer_index.get(req.suspect_id, 0)
    already_broken = player_state.suspect_broken.get(req.suspect_id, False)
    current_layer = suspect.alibi_layers[min(layer_index, len(suspect.alibi_layers) - 1)]
    current_alibi_text = player_state.suspect_alibis.get(req.suspect_id, current_layer.public_text)

    unlocked_evidence = [e for e in case_file.evidence if e.id in player_state.unlocked_evidence_ids]

    evaluation = await evaluate_player_message(
        player_message=req.message,
        unlocked_evidence=unlocked_evidence,
        suspect_alibi=current_alibi_text,
    )

    # A layer only actually breaks if the SPECIFIC evidence it requires was
    # referenced - citing unrelated-but-valid evidence at a suspect who
    # hasn't been asked about it yet shouldn't skip layers.
    layer_break = (
        not already_broken
        and evaluation.trap_successful
        and current_layer.requires_evidence_id in evaluation.referenced_evidence_ids
    )

    return player_state, case_file, suspect, layer_index, current_layer, evaluation, layer_break


def _update_hint_tracking(player_state, suspect_id: str, evaluation, layer_break: bool) -> None:
    """Every turn, whether or not it breaks a layer, feeds the hint system:
    reset the failed-attempt counter on a break (a new layer means a fresh
    chance before hints kick in again), otherwise increment it and stash
    the evaluator's reasoning as the raw material for the next hint call."""
    if layer_break:
        player_state.suspect_failed_attempts[suspect_id] = 0
    else:
        player_state.suspect_failed_attempts[suspect_id] = (
            player_state.suspect_failed_attempts.get(suspect_id, 0) + 1
        )
    player_state.suspect_last_reasoning[suspect_id] = evaluation.reasoning


async def _apply_layer_break(player_state, case_file, suspect, layer_index, current_layer) -> tuple[bool, list[str]]:
    """Mutates player_state in place for a successful layer break. Returns
    (fully_broken, newly_unlocked_evidence_ids)."""
    newly_unlocked: list[str] = []
    is_last_layer = layer_index >= len(suspect.alibi_layers) - 1

    if current_layer.unlocks_evidence_id and current_layer.unlocks_evidence_id not in player_state.unlocked_evidence_ids:
        player_state.unlocked_evidence_ids.append(current_layer.unlocks_evidence_id)
        newly_unlocked.append(current_layer.unlocks_evidence_id)

    if is_last_layer:
        player_state.suspect_broken[suspect.id] = True
        player_state.suspect_alibis[suspect.id] = suspect.hidden_truth
        return True, newly_unlocked

    next_layer = suspect.alibi_layers[layer_index + 1]
    player_state.suspect_layer_index[suspect.id] = layer_index + 1
    player_state.suspect_alibis[suspect.id] = current_layer.reveal_text
    return False, newly_unlocked


async def _maybe_record_case_solved(player_state, case_file) -> None:
    if player_state.case_solved:
        return
    all_broken = all(player_state.suspect_broken.get(s.id, False) for s in case_file.suspects)
    if all_broken and case_file.suspects:
        player_state.case_solved = True
        player_state.solved_at = datetime.now(timezone.utc)
        await record_case_solved(player_state)


@router.post("/message", response_model=InterrogationResponse, dependencies=[Depends(INTERROGATION_RATE_LIMIT)])
async def handle_interrogation(req: InterrogationRequest) -> InterrogationResponse:
    player_state, case_file, suspect, layer_index, current_layer, evaluation, layer_break = await _prepare_turn(req)
    player_state.interrogation_attempts += 1
    _update_hint_tracking(player_state, req.suspect_id, evaluation, layer_break)

    reply = await generate_suspect_reply(player_message=req.message, evaluation=evaluation, suspect=suspect)

    newly_unlocked: list[str] = []
    fully_broken = player_state.suspect_broken.get(req.suspect_id, False)
    if layer_break:
        fully_broken, newly_unlocked = await _apply_layer_break(player_state, case_file, suspect, layer_index, current_layer)

    history = player_state.chat_history.setdefault(req.suspect_id, [])
    history.append({"role": "player", "content": req.message})
    history.append({"role": "suspect", "content": reply})

    await _maybe_record_case_solved(player_state, case_file)
    await save_player_state(player_state)

    return InterrogationResponse(
        suspect_reply=reply,
        trap_successful=evaluation.trap_successful,
        suspect_broken=fully_broken,
        layer_advanced=layer_break,
        current_layer_index=player_state.suspect_layer_index.get(req.suspect_id, layer_index),
        updated_alibi=player_state.suspect_alibis.get(req.suspect_id, current_layer.public_text),
        newly_unlocked_evidence=newly_unlocked,
    )


@router.post("/message/stream", dependencies=[Depends(INTERROGATION_RATE_LIMIT)])
async def handle_interrogation_stream(req: InterrogationRequest) -> StreamingResponse:
    """SSE variant: streams the suspect's reply token-by-token, then a final
    `event: done` frame carrying the same metadata as the JSON endpoint, so
    the frontend can render text live and still get trap/unlock state at
    the end of the stream."""
    player_state, case_file, suspect, layer_index, current_layer, evaluation, layer_break = await _prepare_turn(req)
    player_state.interrogation_attempts += 1
    _update_hint_tracking(player_state, req.suspect_id, evaluation, layer_break)

    async def event_stream():
        full_reply = ""
        async for chunk in stream_suspect_reply(player_message=req.message, evaluation=evaluation, suspect=suspect):
            full_reply += chunk
            yield f"event: token\ndata: {json.dumps({'text': chunk})}\n\n"

        newly_unlocked: list[str] = []
        fully_broken = player_state.suspect_broken.get(req.suspect_id, False)
        if layer_break:
            fully_broken, newly_unlocked = await _apply_layer_break(
                player_state, case_file, suspect, layer_index, current_layer
            )

        history = player_state.chat_history.setdefault(req.suspect_id, [])
        history.append({"role": "player", "content": req.message})
        history.append({"role": "suspect", "content": full_reply})

        await _maybe_record_case_solved(player_state, case_file)
        await save_player_state(player_state)

        done_payload = InterrogationResponse(
            suspect_reply=full_reply,
            trap_successful=evaluation.trap_successful,
            suspect_broken=fully_broken,
            layer_advanced=layer_break,
            current_layer_index=player_state.suspect_layer_index.get(req.suspect_id, layer_index),
            updated_alibi=player_state.suspect_alibis.get(req.suspect_id, current_layer.public_text),
            newly_unlocked_evidence=newly_unlocked,
        )
        yield f"event: done\ndata: {done_payload.model_dump_json()}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/hint", response_model=HintResponse, dependencies=[Depends(HINT_RATE_LIMIT)])
async def get_hint(req: HintRequest) -> HintResponse:
    """Surfaces the evaluator's internal `reasoning` field as a softened,
    in-world nudge - but only once the player has failed enough consecutive
    attempts at their CURRENT layer (HINT_THRESHOLD), so it doesn't trivialize
    a case someone is making steady progress on."""
    player_state = await get_player_state(req.player_id)
    case_file = await get_case_file(player_state.case_id)

    suspect = next((s for s in case_file.suspects if s.id == req.suspect_id), None)
    if suspect is None:
        raise HTTPException(404, f"Suspect '{req.suspect_id}' not found in case '{case_file.case_id}'")

    attempts = player_state.suspect_failed_attempts.get(req.suspect_id, 0)
    if attempts < HINT_THRESHOLD:
        return HintResponse(
            available=False,
            attempts_made=attempts,
            attempts_until_hint=HINT_THRESHOLD - attempts,
        )

    reasoning = player_state.suspect_last_reasoning.get(req.suspect_id)
    if not reasoning:
        # No message sent yet this layer - nothing to build a hint from.
        return HintResponse(available=False, attempts_made=attempts, attempts_until_hint=0)

    layer_index = player_state.suspect_layer_index.get(req.suspect_id, 0)
    current_layer = suspect.alibi_layers[min(layer_index, len(suspect.alibi_layers) - 1)]
    required_evidence = next(
        (e for e in case_file.evidence if e.id == current_layer.requires_evidence_id), None
    )
    evidence_unlocked = required_evidence is not None and required_evidence.id in player_state.unlocked_evidence_ids

    hint_text = await generate_hint(
        reasoning=reasoning,
        required_evidence_label=required_evidence.label if required_evidence else None,
        evidence_unlocked=evidence_unlocked,
        suspect_name=suspect.name,
    )

    return HintResponse(available=True, hint=hint_text, attempts_made=attempts, attempts_until_hint=0)
