"""Worker runtime: turns an AgentSpecification into a LangChain agent and runs it.

This is the only path through which a dynamic agent executes. Nothing in a specification is
executable: the agent is assembled from registered parts (the catalogue's model, the gateway's
tools, the fixed middleware list) and a prompt whose hash is checked first.

What code decides here, never a model: whether the prompt is the approved one, whether the model may
see this data, when the budget stops the run, what a content-filter block or a refusal means, and
which outcome and registry status follow. A model drafts a `SpecialistOutput`; the platform attaches
identity, usage and evidence and rejects a citation of evidence it did not issue.

Stores are reached through the async facade only (ADR-0034)."""

import asyncio
import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.exceptions import ModelRefusalError
from langchain_core.language_models import BaseChatModel
from pydantic import JsonValue, ValidationError

from orchestrator.contracts import (
    AgentResult,
    AgentSpecification,
    AgentStatus,
    Contract,
    SpecialistOutput,
    Task,
    Usage,
)
from orchestrator.governance.budget import ReservationClosed
from orchestrator.governance.metering import MeterBook, UsageMeter
from orchestrator.governance.pii import redact_output
from orchestrator.governance.resilience import SelfHealer
from orchestrator.graph.middleware import (
    ValidationCounter,
    build_middleware,
    is_content_filter_block,
)
from orchestrator.models.catalogue import ClearanceExceeded, ModelCatalogue, ModelEntry
from orchestrator.models.chat import build_chat_model
from orchestrator.persistence.facade import AsyncStores
from orchestrator.tools.gateway import AgentStopped, KillSwitch, ToolGateway, bind_tool
from orchestrator.tools.registry import ToolRegistry

ACTOR = "system:worker"
OutcomeStatus = Literal[
    "awaiting_review", "failed", "timed_out", "cancelled", "blocked_budget", "suspended"
]
ModelFactory = Callable[[ModelEntry, int, float], BaseChatModel]


def foundry_model_factory(
    entry: ModelEntry, max_output_tokens: int, timeout_seconds: float
) -> BaseChatModel:
    return build_chat_model(
        entry, max_output_tokens=max_output_tokens, timeout_seconds=timeout_seconds
    )


class SpecialistOutcome(Contract):
    task_id: str
    agent_id: str
    status: OutcomeStatus
    result: AgentResult | None = None
    error: str | None = None
    usage: Usage = Usage()


@dataclass
class WorkerDeps:
    stores: AsyncStores
    tools: ToolRegistry
    catalogue: ModelCatalogue
    healer: SelfHealer
    kill: KillSwitch
    model_factory: ModelFactory = foundry_model_factory
    meters: MeterBook = field(init=False)
    retry_initial_delay: float = 1.0

    def __post_init__(self) -> None:
        self.meters = MeterBook(self.catalogue)

    @property
    def gateway(self) -> ToolGateway:
        return ToolGateway(self.stores, self.tools, self.healer, self.meters, self.kill)


def task_message(task: Task, revision: int, comments: list[str]) -> str:
    lines = [
        f"Task {task.task_id}",
        f"Objective: {task.objective}",
        f"Expected output: {task.expected_output}",
        "Acceptance criteria:",
    ]
    lines += [f"- {c}" for c in task.acceptance_criteria]
    if revision:
        lines.append(f"This is revision {revision}. Your lead's review comments:")
        lines += [f"- {c}" for c in comments]
    return "\n".join(lines)


async def _audit(
    deps: WorkerDeps, kind: str, spec: AgentSpecification, **details: JsonValue
) -> None:
    await deps.stores.audit.append(
        kind,
        actor=ACTOR,
        project_id=spec.project_id,
        workstream_id=spec.workstream_id,
        task_id=spec.task_id,
        agent_id=spec.agent_id,
        details=dict(details),
    )


async def _check_before_build(deps: WorkerDeps, spec: AgentSpecification) -> ModelEntry:
    if hashlib.sha256(spec.prompt.rendered.encode()).hexdigest() != spec.prompt.sha256:
        await _audit(deps, "prompt.hash_mismatch", spec)
        raise AgentStopped("prompt_hash_mismatch")
    try:
        return deps.catalogue.check_clearance(spec.model.deployment, spec.clearance)
    except ClearanceExceeded as exc:
        await _audit(deps, "model.clearance_refused", spec, model=spec.model.deployment)
        raise AgentStopped("model_clearance") from exc


async def build_specialist(deps: WorkerDeps, spec: AgentSpecification) -> tuple[object, UsageMeter]:
    """Assemble the agent. Raises `AgentStopped` if it must not run."""
    entry = await _check_before_build(deps, spec)
    meter = deps.meters.for_agent(spec.agent_id, spec.model.deployment, spec.budget)
    timeout = float(spec.budget.timeout_seconds)
    fallbacks: list[BaseChatModel] = []
    if entry.fallback:
        fallback_entry = deps.catalogue.check_clearance(entry.fallback, spec.clearance)
        fallbacks.append(deps.model_factory(fallback_entry, spec.model.max_output_tokens, timeout))
    gateway = deps.gateway
    agent = create_agent(
        model=deps.model_factory(entry, spec.model.max_output_tokens, timeout),
        tools=[bind_tool(spec, grant, gateway) for grant in spec.tools],
        system_prompt=spec.prompt.rendered,
        response_format=ToolStrategy(SpecialistOutput, handle_errors=ValidationCounter(meter)),
        middleware=build_middleware(
            spec,
            meter=meter,
            stores=deps.stores,
            kill=deps.kill,
            fallback_models=fallbacks,
            retry_initial_delay=deps.retry_initial_delay,
        ),
        name=spec.agent_id,
    )
    return agent, meter


@dataclass
class _Verdict:
    """What a run came to, before it is settled and recorded."""

    status: OutcomeStatus
    registry_status: AgentStatus
    result: AgentResult | None = None
    error: str | None = None


async def _settle(deps: WorkerDeps, spec: AgentSpecification, reservation_id: str) -> None:
    """Charge what this run spent against its reservation. The meter is told only after the
    ledger has it, so a settlement that fails is tried again and the spend is never dropped."""
    meter = deps.meters.get(spec.agent_id)
    if meter is None:
        return
    delta, mark = meter.unsettled()
    try:
        await deps.stores.ledger.settle(reservation_id, delta)
    except ReservationClosed:
        await _audit(deps, "budget.settle_refused", spec, reservation=reservation_id)
        return
    meter.acknowledge(mark)


async def _outcome(
    deps: WorkerDeps, spec: AgentSpecification, verdict: _Verdict, started: float
) -> SpecialistOutcome:
    meter = deps.meters.get(spec.agent_id)
    usage = meter.usage() if meter else Usage()
    usage = usage.model_copy(update={"elapsed_seconds": time.monotonic() - started})
    status = verdict.status
    current = (await deps.stores.registry.get(spec.agent_id)).status
    if current is AgentStatus.SUSPENDED:
        status = "suspended"
    elif current is AgentStatus.RUNNING:
        await deps.stores.registry.transition(spec.agent_id, verdict.registry_status)
    result = verdict.result
    if result is not None:
        result = result.model_copy(update={"usage": usage})
    return SpecialistOutcome(
        task_id=spec.task_id,
        agent_id=spec.agent_id,
        status=status,
        result=result,
        error=verdict.error,
        usage=usage,
    )


async def run_specialist(
    deps: WorkerDeps,
    spec: AgentSpecification,
    task: Task,
    *,
    reservation_id: str,
    revision: int = 0,
    comments: list[str] | None = None,
) -> SpecialistOutcome:
    """Run one specialist to an outcome. Every path ends in one: an exception nobody planned for
    becomes outcome `failed` (the error is the exception's type name, never its message), and
    the spend is settled in a `finally`, so no path leaves the reservation open.

    Idempotent where it writes: audit events are the only repeat-sensitive writes, and a resumed
    node only adds to the record."""
    started = time.monotonic()
    try:
        verdict = await _attempt(deps, spec, task, revision, comments or [])
    except Exception as exc:
        verdict = _Verdict("failed", AgentStatus.FAILED, error=type(exc).__name__)
        await _audit(
            deps,
            "worker.unhandled_failure",
            spec,
            error_type=type(exc).__name__,
            model=spec.model.deployment,
        )
    finally:
        await _settle(deps, spec, reservation_id)
    return await _outcome(deps, spec, verdict, started)


async def _attempt(
    deps: WorkerDeps,
    spec: AgentSpecification,
    task: Task,
    revision: int,
    comments: list[str],
) -> _Verdict:
    current = (await deps.stores.registry.get(spec.agent_id)).status
    if current is AgentStatus.SUSPENDED:
        return _Verdict("suspended", AgentStatus.SUSPENDED, error="suspended")
    if current is not AgentStatus.RUNNING:
        if current not in (AgentStatus.ASSIGNED, AgentStatus.REVISION_REQUESTED):
            return _Verdict("failed", AgentStatus.FAILED, error=f"not runnable: {current}")
        await deps.stores.registry.transition(spec.agent_id, AgentStatus.RUNNING)

    try:
        agent, _ = await build_specialist(deps, spec)
        async with asyncio.timeout(spec.budget.timeout_seconds):
            final = await agent.ainvoke(  # type: ignore[attr-defined]
                {"messages": [{"role": "user", "content": task_message(task, revision, comments)}]},
                config={
                    "run_name": f"specialist:{spec.role_title}",
                    "metadata": {
                        "project_id": spec.project_id,
                        "agent_id": spec.agent_id,
                        "task_id": spec.task_id,
                        "prompt_sha256": spec.prompt.sha256,
                        "model_key": spec.model.deployment,
                        "revision": revision,
                    },
                },
            )
    except AgentStopped as stop:
        if stop.reason == "cancelled":
            return _Verdict("cancelled", AgentStatus.CANCELLED, error="cancelled")
        if stop.reason == "suspended":
            return _Verdict("suspended", AgentStatus.SUSPENDED, error="suspended")
        if stop.reason.startswith("budget:"):
            return _Verdict("blocked_budget", AgentStatus.FAILED, error=stop.reason)
        return _Verdict("failed", AgentStatus.FAILED, error=f"stopped: {stop.reason}")
    except TimeoutError:
        return _Verdict("timed_out", AgentStatus.TIMED_OUT, error="timed out")
    except ModelRefusalError:
        await _audit(deps, "guardrail.model_refusal", spec, model=spec.model.deployment)
        return _Verdict("failed", AgentStatus.FAILED, error="model_refusal")
    except Exception as exc:
        if not is_content_filter_block(exc):
            raise
        # Never retried: the prompt itself was refused. The task fails to its Lead.
        await _audit(deps, "guardrail.content_filter_block", spec, model=spec.model.deployment)
        return _Verdict("failed", AgentStatus.FAILED, error="content_filter_blocked")

    output = final.get("structured_response")
    if not isinstance(output, SpecialistOutput):
        return _Verdict("failed", AgentStatus.FAILED, error="no structured output within limits")
    try:
        output, report = redact_output(output)
    except ValidationError:
        # Failing closed: a redacted field no longer fits its schema, so nothing leaves unredacted.
        await _audit(deps, "guardrail.pii_redaction_failed", spec)
        return _Verdict("failed", AgentStatus.FAILED, error="pii_redaction_failed")
    if report.redacted:
        await _audit(
            deps,
            "guardrail.pii_redacted",
            spec,
            counts=dict(report.counts),
            fields=list(report.fields),
        )
    try:
        result = AgentResult(
            task_id=task.task_id,
            agent_id=spec.agent_id,
            revision=revision,
            output=output,
            usage=Usage(),
            evidence=await deps.stores.evidence.for_agent(spec.project_id, spec.agent_id),
        )
    except ValidationError as exc:
        await _audit(deps, "result.invalid_citation", spec)
        return _Verdict(
            "failed", AgentStatus.FAILED, error=f"invalid result: {exc.error_count()} error(s)"
        )
    return _Verdict("awaiting_review", AgentStatus.AWAITING_REVIEW, result=result)
