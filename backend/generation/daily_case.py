"""
Phase 4: Daily Automated Content Generation.

A verified coding template (data-cleaning spec + algorithm spec + real unit
tests) is never itself LLM-generated - only the narrative wrapper is. This
keeps the actual test cases deterministic and exploit-free while still
giving every day a fresh crime story. Two templates exist so the daily pick
varies both the narrative flavor and the algorithm the player has to write.

Suspects get TWO alibi layers, built programmatically rather than asking
the LLM to invent evidence ids it can't know about yet:
  - Layer 0 breaks on the evidence unlocked by the day's coding challenge.
  - Breaking layer 0 unlocks a "slip" evidence item (the suspect's own
    admission), which is what's required to break layer 1 and get the full
    confession. So the interrogation itself generates the leverage needed
    to finish it, instead of every layer needing its own coding challenge.
"""
from __future__ import annotations

import json
import logging
import random
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, Field

from backend.generation.indian_theme import challenge_label, pick_codename
from backend.llm_client import NARRATIVE_MODEL, structured_completion
from backend.schemas import AlibiLayer, CaseFile, CodingChallenge, EvidenceItem, Suspect
from backend.state_store import save_case_file

logger = logging.getLogger("generation.daily_case")
router = APIRouter(prefix="/api/admin", tags=["generation"])

DATASET_DIR = Path("backend/generation/datasets")


# --------------------------------------------------------------------------- #
# LLM-facing narrative schema.
#
# Deliberately NOT the same shape as Suspect - the LLM shouldn't have to
# invent evidence ids that don't exist yet. It only writes the words; the
# case generator wires those words into real AlibiLayer/EvidenceItem objects.
# --------------------------------------------------------------------------- #

class SuspectNarrative(BaseModel):
    id: str
    name: str
    personality: str
    alibi_public_text: str = Field(description="How the suspect answers before any evidence is used against them")
    partial_admission_text: str = Field(
        description="What the suspect admits once caught in the FIRST lie - still evasive, still hiding the full truth"
    )
    hidden_truth: str = Field(description="The full truth, only admitted once fully broken")


class NarrativeWrapper(BaseModel):
    title: str
    victim: str
    crime_scene: str
    narrative_intro: str
    suspects: List[SuspectNarrative]
    evidence_label: str = Field(description="Player-facing label for the evidence the coding challenge recovers")
    evidence_detail: str = Field(description="Full detail text used by the CRAG evaluator for that evidence")


# --------------------------------------------------------------------------- #
# Verified templates - deterministic cleaning/algorithm specs + unit tests.
# Only the narrative wrapper around these is LLM-generated.
# --------------------------------------------------------------------------- #

def _transactions_template() -> Dict[str, Any]:
    from backend.generation.dataset_generators import generate_poisoned_transactions

    return {
        "template_id": "cleaning_binary_search_v1",
        "challenge_title": "Recover the transaction record",
        "cleaning_spec": (
            "Records may contain negative timestamps, non-numeric 'amount' fields, or "
            "duplicate 'record_id's. A valid record has a positive integer timestamp, a "
            "numeric amount, and a unique record_id."
        ),
        "algorithm_spec": (
            "After cleaning, sort records by timestamp. Binary search for the first record "
            "at or after a target timestamp threshold and return its record_id."
        ),
        "unit_tests": [
            {"stage": "cleaning", "expected_cleaned_count": 8214},
            {"stage": "algorithm", "expected_answer": "TXN-55291"},
        ],
        "generator": generate_poisoned_transactions,
        "generator_kwargs": {},
        "dataset_filename": "transactions.json",
        "narrative_hint": (
            "a poisoned bank transaction log; the player must clean it and binary-search "
            "for one specific transaction tied to the crime"
        ),
    }


def _cell_pings_template() -> Dict[str, Any]:
    from backend.generation.dataset_generators import generate_poisoned_cell_pings

    return {
        "template_id": "cleaning_loitering_scan_v1",
        "challenge_title": "Trace the burner phone",
        "cleaning_spec": (
            "Records may have a null 'device_id', a non-numeric 'signal_strength', or a "
            "non-string 'tower_id'. A valid record has all three fields present and correctly typed."
        ),
        "algorithm_spec": (
            "After cleaning, find the one device that pinged the crime-scene tower "
            "('TWR-CS-07') twice in quick succession (a two-pointer scan over that device's "
            "sorted pings) and return its device_id."
        ),
        "unit_tests": [
            {"stage": "cleaning", "expected_cleaned_count": 2400},
            # expected_answer is appended per-case below - the suspect device id is randomized per seed
        ],
        "generator": generate_poisoned_cell_pings,
        "generator_kwargs": {},
        "dataset_filename": "cell_pings.json",
        "narrative_hint": (
            "a poisoned cell-tower ping log; the player must clean it and scan for the one "
            "device that loitered near the crime scene"
        ),
    }


_TEMPLATES = [_transactions_template, _cell_pings_template]


async def _generate_narrative(template: Dict[str, Any]) -> NarrativeWrapper:
    system_prompt = f"""You write short noir crime-fiction wrappers for a daily coding game.
A player will clean a poisoned dataset and run an algorithm to recover a piece of evidence.
The technical task is: {template['narrative_hint']}. Do NOT alter or reference the technical
spec directly, it only needs to fit thematically:

{template['cleaning_spec']}
{template['algorithm_spec']}

Invent a victim, a crime scene, and exactly TWO suspects (one guilty, one red herring).
For each suspect write:
- alibi_public_text: their claimed story, stated confidently
- partial_admission_text: what they admit once first caught in a lie - still evasive,
  still hiding the full truth, but visibly rattled
- hidden_truth: the full truth, admitted only once fully broken

Also write evidence_label (short) and evidence_detail (one sentence, specific enough to
logically contradict an alibi) for the evidence this coding challenge recovers.

Keep narrative_intro under 120 words. Output must match the required schema exactly."""

    return await structured_completion(
        schema=NarrativeWrapper,
        system_prompt=system_prompt,
        user_prompt="Generate today's case narrative now.",
        model=NARRATIVE_MODEL,
        temperature=0.9,
        max_tokens=900,
    )


def _build_suspects(narrative: NarrativeWrapper, challenge_evidence_id: str) -> List[Suspect]:
    suspects: List[Suspect] = []
    for sn in narrative.suspects:
        slip_evidence_id = f"ev_{sn.id}_slip"
        layers = [
            AlibiLayer(
                layer_index=0,
                public_text=sn.alibi_public_text,
                requires_evidence_id=challenge_evidence_id,
                reveal_text=sn.partial_admission_text,
                unlocks_evidence_id=slip_evidence_id,
            ),
            AlibiLayer(
                layer_index=1,
                public_text=sn.partial_admission_text,
                requires_evidence_id=slip_evidence_id,
                reveal_text=sn.hidden_truth,
                unlocks_evidence_id=None,
            ),
        ]
        suspects.append(
            Suspect(
                id=sn.id,
                name=sn.name,
                personality=sn.personality,
                hidden_truth=sn.hidden_truth,
                alibi_layers=layers,
            )
        )
    return suspects


def _build_evidence(narrative: NarrativeWrapper, challenge_evidence_id: str, suspects: List[Suspect]) -> List[EvidenceItem]:
    items = [
        EvidenceItem(
            id=challenge_evidence_id,
            label=narrative.evidence_label,
            detail=narrative.evidence_detail,
            unlocked=False,
            unlocked_via="coding_challenge:main",
        )
    ]
    for suspect in suspects:
        slip_layer = suspect.alibi_layers[0]
        if slip_layer.unlocks_evidence_id:
            items.append(
                EvidenceItem(
                    id=slip_layer.unlocks_evidence_id,
                    label=f"{suspect.name}'s slip",
                    detail=slip_layer.reveal_text,
                    unlocked=False,
                    unlocked_via=f"confession:{suspect.id}:0",
                )
            )
    return items


async def generate_daily_case(template_index: Optional[int] = None) -> CaseFile:
    case_id = f"case_{datetime.now(timezone.utc):%Y%m%d}_{uuid.uuid4().hex[:6]}"

    rng = random.Random(case_id)
    template_fn = _TEMPLATES[template_index] if template_index is not None else rng.choice(_TEMPLATES)
    template = template_fn()

    narrative = await _generate_narrative(template)

    challenge_evidence_id = "ev_main_recovery"
    challenge_id = "chal_main"
    dataset_relpath = f"generation/datasets/{case_id}/{template['dataset_filename']}"

    dataset = template["generator"](seed=case_id, **template["generator_kwargs"])
    out_path = DATASET_DIR.parent.parent / dataset_relpath
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(dataset))

    unit_tests = list(template["unit_tests"])
    if template["template_id"] == "cleaning_loitering_scan_v1":
        # This template's answer (the burner device id) is randomized per
        # seed by the generator itself, so derive the expected answer the
        # same deterministic way rather than hardcoding it.
        suspect_device = next(r["device_id"] for r in dataset if r.get("tower_id") == "TWR-CS-07")
        unit_tests.append({"stage": "algorithm", "expected_answer": suspect_device})

    suspects = _build_suspects(narrative, challenge_evidence_id)
    evidence = _build_evidence(narrative, challenge_evidence_id, suspects)
    codename = pick_codename(case_id)

    case_file = CaseFile(
        case_id=case_id,
        generated_at=datetime.now(timezone.utc),
        title=narrative.title,
        codename=f"Operation {codename}",
        victim=narrative.victim,
        crime_scene=narrative.crime_scene,
        narrative_intro=narrative.narrative_intro,
        suspects=suspects,
        evidence=evidence,
        challenges=[
            CodingChallenge(
                id=challenge_id,
                title=f"{challenge_label(case_id, 0)}: {template['challenge_title']}",
                prompt=(
                    f"{narrative.narrative_intro}\n\n"
                    f"Clean the poisoned dataset, then run the algorithm to recover the evidence."
                ),
                poisoned_dataset_url=dataset_relpath,
                cleaning_spec=template["cleaning_spec"],
                algorithm_spec=template["algorithm_spec"],
                unit_tests=unit_tests,
                unlocks_evidence_id=challenge_evidence_id,
            )
        ],
    )

    await save_case_file(case_file)
    logger.info("Generated daily case %s (%s): %s", case_id, template["template_id"], case_file.title)
    return case_file


@router.post("/generate-daily-case")
async def trigger_daily_case(background_tasks: BackgroundTasks) -> dict:
    """Manual/admin trigger; in production this is called by an external
    scheduler (cron, GitHub Actions, cloud scheduler) - see DEPLOYMENT.md."""
    background_tasks.add_task(generate_daily_case)
    return {"status": "generation_started"}
