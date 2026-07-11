"""
Operation Prashikshan - the fixed tutorial case.

Unlike the daily cases, this one is never LLM-generated and never rotates.
It exists once, at a stable case_id ("case_tutorial"), gets (re)seeded on
every backend startup, and is what index.js/PoliceOS point brand-new
players at before they ever touch a real (randomized) daily case. It uses
the exact same CaseFile/CodingChallenge/Suspect shapes as a real case, so
every existing app (terminal, evidence board, messenger) just works on it
unmodified - it's a real, tiny, single-layer case, not a fake walkthrough.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from backend.generation.indian_theme import TUTORIAL_CODENAME, TUTORIAL_TITLE
from backend.schemas import AlibiLayer, CaseFile, CodingChallenge, EvidenceItem, Suspect
from backend.state_store import save_case_file

TUTORIAL_CASE_ID = "case_tutorial"

_DATASET_RELPATH = "generation/datasets/tutorial/duty_log.json"


def _write_tutorial_dataset() -> None:
    """A tiny, hand-authored poisoned dataset: a constable's duty-roster
    log. Cleaning rule is dead simple (drop entries with a non-numeric
    'badge' or missing 'post') and the algorithm is a linear scan - meant
    to be solvable in under a minute so it teaches the terminal→submit loop
    without being a real puzzle."""
    records = [
        {"badge": 4821, "post": "Colaba Gate", "shift": "night"},
        {"badge": "unknown", "post": "Colaba Gate", "shift": "day"},   # bad badge -> invalid
        {"badge": 5190, "post": None, "shift": "night"},                # missing post -> invalid
        {"badge": 3307, "post": "Fort Chowki", "shift": "day"},
        {"badge": 6642, "post": "Marine Drive", "shift": "night"},
        {"badge": 1188, "post": "Fort Chowki", "shift": "night"},
        {"badge": 9004, "post": "CST Junction", "shift": "day"},
    ]
    out_path = Path("backend") / _DATASET_RELPATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(records))


def build_tutorial_case() -> CaseFile:
    _write_tutorial_dataset()

    challenge_evidence_id = "ev_tutorial_duty_log"

    suspect = Suspect(
        id="sus_head_constable",
        name="Head Constable Bhonsle",
        personality="Gruff, overly formal, hides nerves behind procedure.",
        hidden_truth=(
            "Bhonsle swapped the duty roster to cover for a missed night patrol "
            "at Fort Chowki - nothing sinister, just avoiding a reprimand."
        ),
        alibi_layers=[
            AlibiLayer(
                layer_index=0,
                public_text="\"The roster is accurate. Every post was manned exactly as logged, sir.\"",
                requires_evidence_id=challenge_evidence_id,
                reveal_text=(
                    "\"...Fine. The Fort Chowki night entry was padded. Nobody was hurt, "
                    "I just didn't want it on record that the post was empty.\""
                ),
                unlocks_evidence_id=None,
            )
        ],
    )

    return CaseFile(
        case_id=TUTORIAL_CASE_ID,
        generated_at=datetime.now(timezone.utc),
        title=TUTORIAL_TITLE,
        codename=f"Operation {TUTORIAL_CODENAME}",
        is_tutorial=True,
        victim="N/A — training file, no crime, just a discrepancy to catch",
        crime_scene="Colaba Police Chowki, night duty roster",
        narrative_intro=(
            "Welcome to the bureau, Officer. Before you're handed a live case, walk through "
            "this training file: clean a poisoned duty log in the DB_TERMINAL, recover the "
            "one discrepancy it's hiding, then use it in SECURE_MESSENGER to get Head "
            "Constable Bhonsle to admit what really happened that night."
        ),
        suspects=[suspect],
        evidence=[
            EvidenceItem(
                id=challenge_evidence_id,
                label="Cleaned duty log",
                detail=(
                    "Of 7 logged entries, only 5 are valid duty records; the valid Fort Chowki "
                    "night-shift entry belongs to badge 1188, not the padded one Bhonsle is "
                    "hiding behind."
                ),
                unlocked=False,
                unlocked_via="coding_challenge:main",
            )
        ],
        challenges=[
            CodingChallenge(
                id="chal_tutorial",
                title="Pehchaan 1: Clean the Duty Log",
                prompt=(
                    "Some entries in this duty log are corrupted: a non-numeric 'badge' field, "
                    "or a missing 'post'. Write Python that filters `records` down to the valid "
                    "ones (numeric badge AND non-null post), then sets `answer` to the count of "
                    "valid records and `cleaned_count` to that same count."
                ),
                poisoned_dataset_url=_DATASET_RELPATH,
                cleaning_spec=(
                    "A valid record has a numeric 'badge' field and a non-null 'post' field."
                ),
                algorithm_spec=(
                    "No further algorithm beyond counting - this is the tutorial, kept to just "
                    "the clean-and-submit loop. Return the count of valid records as the answer."
                ),
                unit_tests=[
                    {"stage": "cleaning", "expected_cleaned_count": 5},
                    {"stage": "algorithm", "expected_answer": 5},
                ],
                unlocks_evidence_id=challenge_evidence_id,
            )
        ],
    )


async def ensure_tutorial_case_exists() -> None:
    """Called on every backend startup. Cheap and idempotent - just
    re-seeds the fixed tutorial case file (never touches player progress
    against it, since that lives in a separate per-player key)."""
    await save_case_file(build_tutorial_case())
