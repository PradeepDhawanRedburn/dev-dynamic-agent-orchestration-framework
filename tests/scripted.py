"""A scripted chat model and helpers for tests that need model-shaped behaviour but no model.

Moved from tests/spike/support.py (WP-03). A script entry is an `AIMessage` to return, or an
exception to raise, so failures such as a content-filter block can be scripted too."""

from collections.abc import Sequence
from typing import Any
from uuid import uuid4

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr


def specialist_output_args(
    claims: int = 3, evidence_ids: list[str] | None = None
) -> dict[str, Any]:
    return {
        "executive_summary": "Summary of the work.",
        "findings": [f"finding {i}" for i in range(claims)],
        "claims": [
            {
                "statement": f"claim {i}",
                "evidence_ids": [
                    evidence_ids[i % len(evidence_ids)] if evidence_ids else f"ev_{i}"
                ],
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
    """Returns scripted messages in order (the last one repeats) and records what it was sent.
    An entry may be an exception to raise, or a function to call that returns the message."""

    script: list[Any]
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
        entry = self.script[min(self._next, len(self.script) - 1)]
        self._next += 1
        if callable(entry) and not isinstance(entry, BaseMessage):
            entry = entry()  # a hook: runs on the worker thread, returns the message to send
        if isinstance(entry, BaseException):
            raise entry
        return ChatResult(generations=[ChatGeneration(message=entry)])

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "ScriptedChatModel":
        return self
