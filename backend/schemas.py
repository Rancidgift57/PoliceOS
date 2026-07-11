"""
Shared data contracts for the Police OS backend.

Every module (CRAG engine, sandbox executor, daily generator) imports from
here so the FastAPI request/response shapes, the Docker payloads, and the
LLM structured outputs never drift out of sync with each other.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Case / Evidence
# --------------------------------------------------------------------------- #

class EvidenceItem(BaseModel):
    id: str
    label: str = Field(description="Short human-readable evidence description shown on the Evidence Board")
    detail: str = Field(description="Full detail used by the CRAG evaluator to grade player claims")
    unlocked: bool = False
    unlocked_via: Optional[str] = Field(
        default=None, description="e.g. 'coding_challenge:binary_search' or 'confession:marcus_vance:1'"
    )


class AlibiLayer(BaseModel):
    """One peel of a suspect's story. Suspects with multiple layers don't
    fully confess on the first successful trap - each layer needs its own
    piece of evidence to break, and only the last layer reveals the full
    hidden_truth."""
    layer_index: int
    public_text: str = Field(description="What the suspect claims at this layer")
    requires_evidence_id: str = Field(description="Evidence id that breaks specifically this layer")
    reveal_text: str = Field(description="What the suspect admits once THIS layer breaks")
    unlocks_evidence_id: Optional[str] = Field(
        default=None, description="Evidence optionally unlocked by breaking this layer, feeding the next one"
    )


class Suspect(BaseModel):
    id: str
    name: str
    personality: str
    hidden_truth: str = Field(description="The full truth, only fully known once the last layer breaks")
    alibi_layers: List[AlibiLayer] = Field(
        default_factory=list,
        description="Ordered layers of the story. Empty/one-layer suspects behave like a simple single alibi.",
    )

    @property
    def public_alibi(self) -> str:
        """Convenience accessor for the outermost (first, unbroken) layer text."""
        return self.alibi_layers[0].public_text if self.alibi_layers else ""


class CodingChallenge(BaseModel):
    id: str
    title: str
    prompt: str
    poisoned_dataset_url: str
    cleaning_spec: str = Field(description="Description of the corruption rules the player's script must handle")
    algorithm_spec: str = Field(description="The core algorithm the player must implement post-cleaning")
    unit_tests: List[Dict[str, Any]]
    unlocks_evidence_id: str


class CaseFile(BaseModel):
    case_id: str
    generated_at: datetime
    title: str
    codename: str = Field(default="", description="Indian-themed 'Operation <Codename>' label, e.g. 'Operation Bijli'")
    is_tutorial: bool = Field(default=False, description="True only for the fixed first-timer tutorial case")
    victim: str
    crime_scene: str
    narrative_intro: str
    suspects: List[Suspect]
    evidence: List[EvidenceItem]
    challenges: List[CodingChallenge]


class CaseSummary(BaseModel):
    """Lightweight listing used by the Case Files board (tutorial / today /
    new / pending) so the frontend doesn't have to download full case
    payloads just to render a list of tiles."""
    case_id: str
    title: str
    codename: str
    generated_at: datetime
    is_tutorial: bool = False
    solved: bool = False
    started: bool = False


# --------------------------------------------------------------------------- #
# Player / Session state
# --------------------------------------------------------------------------- #

class PlayerState(BaseModel):
    player_id: str
    case_id: str
    unlocked_evidence_ids: List[str] = Field(default_factory=list)
    solved_challenge_ids: List[str] = Field(default_factory=list)
    suspect_alibis: Dict[str, str] = Field(
        default_factory=dict, description="suspect_id -> current visible alibi/reveal text"
    )
    suspect_broken: Dict[str, bool] = Field(default_factory=dict, description="fully broken (last layer down)")
    suspect_layer_index: Dict[str, int] = Field(
        default_factory=dict, description="suspect_id -> index of the current (still-unbroken) layer"
    )
    chat_history: Dict[str, List[Dict[str, str]]] = Field(
        default_factory=dict, description="suspect_id -> list of {role, content}"
    )
    suspect_failed_attempts: Dict[str, int] = Field(
        default_factory=dict,
        description="suspect_id -> consecutive non-breaking messages sent at their CURRENT layer, resets on any layer break",
    )
    suspect_last_reasoning: Dict[str, str] = Field(
        default_factory=dict,
        description="suspect_id -> evaluator's internal reasoning from the player's most recent message, source material for hints",
    )
    interrogation_attempts: int = 0
    submission_attempts: int = 0
    case_solved: bool = False
    solved_at: Optional[datetime] = None


# --------------------------------------------------------------------------- #
# CRAG
# --------------------------------------------------------------------------- #

class EvidenceEvaluation(BaseModel):
    referenced_evidence_ids: List[str] = Field(
        default_factory=list, description="IDs from unlocked_evidence the player message actually referenced"
    )
    uses_valid_evidence: bool = Field(
        description="True only if the player explicitly cites an unlocked, real piece of evidence"
    )
    contradicts_alibi: bool = Field(
        description="True if the cited evidence logically contradicts the suspect's CURRENT alibi layer"
    )
    reasoning: str = Field(description="One sentence of internal grading reasoning, never shown to the player")

    @property
    def trap_successful(self) -> bool:
        return self.uses_valid_evidence and self.contradicts_alibi


class InterrogationRequest(BaseModel):
    player_id: str
    suspect_id: str
    message: str
    case_id: Optional[str] = Field(
        default=None, description="Which case this interrogation belongs to; defaults to the player's latest case"
    )


class InterrogationResponse(BaseModel):
    suspect_reply: str
    trap_successful: bool
    suspect_broken: bool
    layer_advanced: bool = Field(description="True if this message broke the current layer (whether or not final)")
    current_layer_index: int
    updated_alibi: str
    newly_unlocked_evidence: List[str] = Field(default_factory=list)


class HintRequest(BaseModel):
    player_id: str
    suspect_id: str
    case_id: Optional[str] = None


class HintResponse(BaseModel):
    available: bool = Field(description="False if the player hasn't failed enough attempts yet to earn a hint")
    hint: Optional[str] = None
    attempts_made: int = 0
    attempts_until_hint: int = 0


# --------------------------------------------------------------------------- #
# Sandbox execution
# --------------------------------------------------------------------------- #

class ExecutionStatus(str, Enum):
    PASSED = "passed"
    FAILED_CLEANING = "failed_cleaning"
    FAILED_ALGORITHM = "failed_algorithm"
    RUNTIME_ERROR = "runtime_error"
    TIMEOUT = "timeout"


class CodeSubmission(BaseModel):
    """Sent AFTER the player's code has already run client-side in the
    browser (Pyodide/WASM - see frontend/src/lib/pyodideRunner.js). The
    backend never executes source_code; it's included purely so the run is
    logged/auditable, and grading still happens server-side against the
    secret unit_tests in the case file so the expected answers never ship
    to the client."""

    player_id: str
    case_id: str
    challenge_id: str
    source_code: str
    cleaned_count: Optional[int] = None
    answer: Optional[Any] = None
    error: Optional[str] = None
    client_runtime_ms: Optional[int] = None


class ExecutionResult(BaseModel):
    status: ExecutionStatus
    stdout: str = ""
    stderr: str = ""
    cleaning_tests_passed: int = 0
    cleaning_tests_total: int = 0
    algorithm_tests_passed: int = 0
    algorithm_tests_total: int = 0
    unlocked_evidence_id: Optional[str] = None
    runtime_ms: Optional[int] = None


# --------------------------------------------------------------------------- #
# Leaderboard / streaks
# --------------------------------------------------------------------------- #

class PlayerStats(BaseModel):
    player_id: str
    current_streak: int = 0
    longest_streak: int = 0
    last_solved_case_id: Optional[str] = None
    total_cases_solved: int = 0


class LeaderboardEntry(BaseModel):
    player_id: str
    case_id: str
    submission_attempts: int
    interrogation_attempts: int
    solved_at: datetime


class DailyLeaderboard(BaseModel):
    case_id: str
    entries: List[LeaderboardEntry]
