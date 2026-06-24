from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


ALLOWED_PHASES = (
    "start",
    "need_w2",
    "need_filing_status",
    "need_household",
    "need_digital_assets",
    "need_refund",
    "ready_to_prepare",
    "complete",
    "out_of_scope",
)

Phase = Literal[
    "start",
    "need_w2",
    "need_filing_status",
    "need_household",
    "need_digital_assets",
    "need_refund",
    "ready_to_prepare",
    "complete",
    "out_of_scope",
]

MAX_USER_QUESTIONS = 5


class QuestionBudgetExceeded(Exception):
    """Raised when a session would exceed its user-facing question budget."""


class TaxSession(BaseModel):
    session_id: str
    phase: Phase = "start"
    question_count: int = 0
    w2: Optional[Dict[str, Any]] = None
    answers: Dict[str, Any] = Field(default_factory=dict)
    return_summary: Optional[Dict[str, Any]] = None
    download_id: Optional[str] = None

    def transition_to(self, next_phase: Phase) -> "TaxSession":
        if next_phase not in ALLOWED_PHASES:
            raise ValueError(f"Invalid phase: {next_phase}")
        self.phase = next_phase
        return self

    def ask_question(self, next_phase: Phase) -> "TaxSession":
        if self.question_count >= MAX_USER_QUESTIONS:
            raise QuestionBudgetExceeded("Maximum user-facing questions exceeded")
        self.question_count += 1
        return self.transition_to(next_phase)
