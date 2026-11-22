"""The worker against real Microsoft Foundry deployments (marked `foundry`; skipped, visibly, when
the key is absent). Everything else about the worker is tested with a scripted model."""

import hashlib
from typing import Any

import pytest

from orchestrator.contracts import AgentStatus, SystemPromptSpecification
from orchestrator.graph.worker import SpecialistOutcome, foundry_model_factory, run_specialist
from tests.conftest import run_async
from tests.spike.test_foundry import PROMPT_ATTACK
from tests.worker_env import RESERVATION, WorkerEnv, make_env, make_spec, make_task

pytestmark = pytest.mark.foundry

PROMPT = (
    "You are a concise technical analyst. Answer in the required schema. Leave `claims` empty, "
    "because you have no sources. Keep every field short."
)


def real_run(objective: str, **spec_over: Any) -> tuple[SpecialistOutcome, WorkerEnv, list[str]]:
    env = make_env()
    env.deps.model_factory = foundry_model_factory
    spec = make_spec(
        tools=[],
        prompt=SystemPromptSpecification(
            compiler_version="test",
            sections=[],
            rendered=PROMPT,
            sha256=hashlib.sha256(PROMPT.encode()).hexdigest(),
        ),
        **spec_over,
    )
    task = make_task(spec).model_copy(update={"objective": objective})

    async def scenario() -> tuple[SpecialistOutcome, list[str]]:
        await env.add_agent(spec)
        outcome = await run_specialist(env.deps, spec, task, reservation_id=RESERVATION)
        audit = [e.kind for e in await env.stores.audit.events(agent_id=spec.agent_id)]
        return outcome, audit

    outcome, audit = run_async(scenario())
    return outcome, env, audit


@pytest.mark.parametrize("key", ["reasoning-small", "reasoning-standard", "reasoning-alternate"])
def test_a_real_deployment_returns_a_valid_result_and_is_metered(key: str) -> None:
    from orchestrator.contracts import ModelConfig

    outcome, env, audit = real_run(
        "In two sentences, say what a REST API is.",
        model=ModelConfig(deployment=key, max_output_tokens=4000),
    )
    assert outcome.status == "awaiting_review", f"{key}: {outcome.status} {outcome.error}"
    assert outcome.result is not None and outcome.result.output.executive_summary
    assert outcome.usage.input_tokens > 0 and outcome.usage.output_tokens > 0
    assert outcome.usage.cost == env.catalogue.cost(
        key, outcome.usage.input_tokens, outcome.usage.output_tokens
    )
    assert audit == []
    registry = run_async(env.stores.registry.get(outcome.agent_id))
    assert registry.status is AgentStatus.AWAITING_REVIEW


def test_a_real_content_filter_block_is_never_retried_and_fails_the_task() -> None:
    outcome, env, audit = real_run(PROMPT_ATTACK)
    assert outcome.status == "failed" and outcome.error == "content_filter_blocked"
    assert audit == ["guardrail.content_filter_block"]
    assert outcome.usage.model_calls == 0, "a blocked prompt returned no tokens to meter"
