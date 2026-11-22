"""Test doubles and schemas shared by the spike tests.

`Claim`, `SpecialistOutput` and `Confidence` are copied from reference/contracts.py (read-only
there) so S-09 can use a schema of the size the design expects.
"""

from enum import StrEnum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tests.scripted import ScriptedChatModel, specialist_output_args, tool_call_message

__all__ = [
    "Claim",
    "Confidence",
    "Contract",
    "ScriptedChatModel",
    "SpecialistOutput",
    "specialist_output_args",
    "tool_call_message",
]


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class Claim(Contract):
    claim_id: str = Field(default_factory=lambda: f"cl_{uuid4().hex[:16]}")
    statement: str
    material: bool = True
    evidence_ids: list[str] = []
    contradicting_evidence_ids: list[str] = []
    confidence: Confidence

    @model_validator(mode="after")
    def _material_needs_evidence(self) -> "Claim":
        if self.material and not self.evidence_ids:
            raise ValueError("a material claim must cite at least one evidence id")
        return self


class SpecialistOutput(Contract):
    """What the model is allowed to author."""

    executive_summary: str = Field(max_length=1500)
    findings: list[str]
    claims: list[Claim]
    assumptions: list[str] = []
    limitations: list[str] = []
    risks: list[str] = []
    recommended_next_action: str
    completion_status: Literal["complete", "partial", "blocked"]
    overall_confidence: Confidence


