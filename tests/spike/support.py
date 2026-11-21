"""Test doubles and schemas shared by the spike tests.

`Claim`, `SpecialistOutput` and `Confidence` are copied from reference/contracts.py (read-only
there) so S-09 can use a schema of the size the design expects.
"""

from collections.abc import Sequence
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator


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


def specialist_output_args(claims: int = 3) -> dict[str, Any]:
    return {
        "executive_summary": "Summary of the work.",
        "findings": [f"finding {i}" for i in range(claims)],
        "claims": [
            {
                "statement": f"claim {i}",
                "evidence_ids": [f"ev_{i}"],
                "confidence": "high",
            }
            for i in range(claims)
        ],
        "assumptions": ["an assumption"],
        "limitations": [],
        "risks": ["a risk"],
        "recommended_next_action": "Ship it.",
        "completion_status": "complete",
        "overall_confidence": "medium",
    }


def tool_call_message(
    name: str, args: dict[str, Any], *, input_tokens: int = 0, output_tokens: int = 0
) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {"name": name, "args": args, "id": f"call_{uuid4().hex[:8]}", "type": "tool_call"}
        ],
        usage_metadata={
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
    )


class ScriptedChatModel(BaseChatModel):
    """A chat model that returns scripted messages in order and records what it was sent."""

    script: list[AIMessage]
    fail_first: int = 0
    _next: int = PrivateAttr(default=0)
    _attempts: int = PrivateAttr(default=0)
    _seen: list[list[BaseMessage]] = PrivateAttr(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    @property
    def seen(self) -> list[list[BaseMessage]]:
        return self._seen

    @property
    def calls(self) -> int:
        return self._next

    @property
    def attempts(self) -> int:
        return self._attempts

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self._attempts += 1
        if self._attempts <= self.fail_first:
            raise ConnectionError("transient failure")
        self._seen.append(list(messages))
        message = self.script[min(self._next, len(self.script) - 1)]
        self._next += 1
        return ChatResult(generations=[ChatGeneration(message=message)])

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "ScriptedChatModel":
        return self
