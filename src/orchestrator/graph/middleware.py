"""The middleware list of a built specialist (ADR-0033 points 17 to 21; lang-family-controls).

A specialist may contain only the allow-listed classes, checked by class name, in one fixed order,
outermost first: budget metering, call limits, PII, model fallback, model retry, model refusal,
tool retry, tool error. `check_middleware` is the test of that rule and runs on every build.

Choices stated here rather than left to defaults:

- Retries are for transient faults only. A prompt the content filter blocks is never retried
  (ADR-0033 point 12): it is a refusal, and the worker ends the task.
- Both retry middlewares raise when they give up, so the failure reaches code that decides.
- The tool-error handler always returns content naming the exception type, never its message.
- PII: input is not scanned (the sponsor's request must reach the agent verbatim), model output is
  redacted, and tool results are not altered. Each setting is passed explicitly.
- Structured-output validation errors are counted by `ValidationCounter`, which is ours; the tool
  that reports an error is not trusted to count it."""

from collections.abc import Sequence
from typing import Any, Literal

import openai
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
    ModelFallbackMiddleware,
    ModelRefusalMiddleware,
    ModelRetryMiddleware,
    PIIMiddleware,
    ToolCallLimitMiddleware,
    ToolErrorMiddleware,
    ToolRetryMiddleware,
)
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage

from orchestrator.contracts import AgentSpecification
from orchestrator.governance.metering import UsageMeter
from orchestrator.governance.resilience import FailureKind, classify
from orchestrator.persistence.facade import AsyncStores
from orchestrator.tools.gateway import AgentStopped, KillSwitch, stop_reason

# Order matters: the first entry is the outermost.
MIDDLEWARE_ORDER: tuple[str, ...] = (
    "BudgetMeteringMiddleware",
    "ModelCallLimitMiddleware",
    "ToolCallLimitMiddleware",
    "PIIMiddleware",
    "ModelFallbackMiddleware",
    "ModelRetryMiddleware",
    "ModelRefusalMiddleware",
    "ToolRetryMiddleware",
    "ToolErrorMiddleware",
)
ALLOWED_MIDDLEWARE = frozenset(MIDDLEWARE_ORDER)

TRANSIENT = {
    FailureKind.NETWORK_LOST,
    FailureKind.DNS_FAILURE,
    FailureKind.TIMEOUT,
    FailureKind.THROTTLED,
    FailureKind.DEPENDENCY_DOWN,
}
PII_TYPES: tuple[Literal["email", "credit_card", "ip"], ...] = ("email", "credit_card", "ip")
ACTOR = "system:worker"


class MiddlewareNotAllowed(ValueError):
    """A class that is not on the allow-list was put in a specialist."""


class MiddlewareOutOfOrder(ValueError):
    """The allow-listed classes are not in the order ADR-0033 fixes."""


def check_middleware(stack: Sequence[object]) -> None:
    names = [type(m).__name__ for m in stack]
    refused = [n for n in names if n not in ALLOWED_MIDDLEWARE]
    if refused:
        raise MiddlewareNotAllowed(f"not on the allow-list: {refused}")
    ranks = [MIDDLEWARE_ORDER.index(n) for n in names]
    if ranks != sorted(ranks):
        raise MiddlewareOutOfOrder(f"expected the order {list(MIDDLEWARE_ORDER)}, got {names}")


def is_content_filter_block(error: BaseException) -> bool:
    """A prompt the Foundry content filter refused: HTTP 400 with the code `content_filter`."""
    return isinstance(error, openai.BadRequestError) and error.code == "content_filter"


def retry_only_transient(error: Exception) -> bool:
    if is_content_filter_block(error) or isinstance(error, AgentStopped):
        return False
    return classify(error) in TRANSIENT


class ValidationCounter:
    """Used as `ToolStrategy(handle_errors=...)`: counts each structured-output validation error and
    tells the model to correct it. The limit is enforced by the metering middleware."""

    def __init__(self, meter: UsageMeter) -> None:
        self._meter = meter

    def __call__(self, error: Exception) -> str:
        count = self._meter.record_validation_error()
        return f"Your answer did not match the required schema (attempt {count}). Correct it."


def tool_error_content(error: Exception, request: ToolCallRequest) -> str | None:
    """Content for the model, naming the exception type only. A stop ordered by governance code
    (`AgentStopped`) is not a tool failure and is never turned into content: it must reach the
    worker and end the run."""
    if isinstance(error, AgentStopped):
        return None
    return (
        f"The tool '{request.tool_call['name']}' failed with {type(error).__name__}. "
        "Do not repeat the same call; continue without it or report the limit."
    )


class BudgetMeteringMiddleware(AgentMiddleware[Any, Any, Any]):
    """Outermost. Stops the agent before a model call if it was killed, suspended or retired, or if
    its budget is spent, and meters every model call afterwards from the provider's token counts."""

    def __init__(
        self,
        spec: AgentSpecification,
        meter: UsageMeter,
        stores: AsyncStores,
        kill: KillSwitch,
    ) -> None:
        super().__init__()
        self.spec, self.meter, self.stores, self.kill = spec, meter, stores, kill

    async def abefore_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        if self.kill.is_set(self.spec.project_id, self.spec.agent_id):
            raise AgentStopped("cancelled")
        status = (await self.stores.registry.get(self.spec.agent_id)).status
        stopped = stop_reason(status)
        if stopped is not None:
            raise AgentStopped(stopped)
        reason = self.meter.exhausted()
        if reason is not None:
            await self.stores.audit.append(
                "budget.stopped",
                actor=ACTOR,
                project_id=self.spec.project_id,
                workstream_id=self.spec.workstream_id,
                task_id=self.spec.task_id,
                agent_id=self.spec.agent_id,
                details={"reason": reason},
            )
            raise AgentStopped(f"budget:{reason}" if reason in ("cost", "tokens") else reason)
        return None

    async def aafter_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        last = next((m for m in reversed(state["messages"]) if isinstance(m, AIMessage)), None)
        meta: Any = (last.usage_metadata if last is not None else None) or {}
        self.meter.record_model_call(meta.get("input_tokens", 0), meta.get("output_tokens", 0))
        return None


def build_middleware(
    spec: AgentSpecification,
    *,
    meter: UsageMeter,
    stores: AsyncStores,
    kill: KillSwitch,
    fallback_models: Sequence[BaseChatModel] = (),
    retry_initial_delay: float = 1.0,
) -> list[AgentMiddleware[Any, Any, Any]]:
    stack: list[AgentMiddleware[Any, Any, Any]] = [
        BudgetMeteringMiddleware(spec, meter, stores, kill),
        ModelCallLimitMiddleware(run_limit=spec.budget.max_model_calls, exit_behavior="end"),
        ToolCallLimitMiddleware(run_limit=spec.budget.max_tool_calls, exit_behavior="continue"),
        *[
            PIIMiddleware(
                kind,
                strategy="redact",
                apply_to_input=False,
                apply_to_output=True,
                apply_to_tool_results=False,
            )
            for kind in PII_TYPES
        ],
    ]
    if fallback_models:
        stack.append(ModelFallbackMiddleware(*fallback_models))
    stack += [
        ModelRetryMiddleware(
            max_retries=spec.budget.max_retries,
            retry_on=retry_only_transient,
            on_failure="error",
            initial_delay=retry_initial_delay,
        ),
        ModelRefusalMiddleware(),
        ToolRetryMiddleware(
            max_retries=spec.budget.max_retries,
            retry_on=retry_only_transient,
            on_failure="error",
            initial_delay=retry_initial_delay,
        ),
        ToolErrorMiddleware(on_error=tool_error_content),
    ]
    check_middleware(stack)
    return stack
