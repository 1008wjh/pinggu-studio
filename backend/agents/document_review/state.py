from __future__ import annotations
from typing import Any, TypedDict
from pydantic import BaseModel, Field

STEP_EXTRACT = "step1_extract"
STEP_RISK = "step2_risk_review"
STEP_REPORT = "step3_report"
STEPS = (STEP_EXTRACT, STEP_RISK, STEP_REPORT)

class ReviewNote(BaseModel):
    summary: str = ""
    risks: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)

class DocumentReviewState(TypedDict, total=False):
    workflow_id: str
    thread_id: str
    tenant_id: str
    user_id: str
    file_paths: list[str]
    document_type: str
    instruction: str
    current_step: str
    status: str
    step_outputs: dict[str, dict[str, Any]]
    review_context: dict[str, Any]
    pending_action: dict[str, Any]
    audit_log: list[dict[str, Any]]
    checkpoint_version: int
    error: str
