"""The worker (WP-03): a scripted model, fake tools and in-memory stores. No model, no database."""

import json
from decimal import Decimal
from typing import Any

import httpx2
import openai
import pytest
from langchain_core.messages import AIMessage

from orchestrator.contracts import AgentSpecification, AgentStatus, Classification
from orchestrator.graph.worker import SpecialistOutcome, run_specialist
from orchestrator.tools.gateway import evidence_id_for, idempotency_key
from tests.conftest import run_async
from tests.scripted import specialist_output_args, tool_call_message
from tests.worker_env import RESERVATION, WorkerEnv, budget, grant, make_env, make_spec, make_task

SEARCH_ARGS = {"query": "rest"}


def evidence_id(spec: AgentSpecification) -> str:
    return evidence_id_for(idempotency_key(spec.agent_id, "fake_search", SEARCH_ARGS), 0)


def final_answer(spec: AgentSpecification, **usage: int) -> AIMessage:
    return tool_call_message(
        "SpecialistOutput", specialist_output_args(2, [evidence_id(spec)]), **usage
    )


def plain_answer(**usage: int) -> AIMessage:
    """A valid answer that cites nothing, for runs that gathered no evidence."""
    args = specialist_output_args(1)
    args["claims"] = []
    return tool_call_message("SpecialistOutput", args, **usage)


def run(
    env: WorkerEnv, spec: AgentSpecification, script: list[Any], status: AgentStatus | None = None
) -> tuple[SpecialistOutcome, list[str], AgentStatus]:
    async def scenario() -> tuple[SpecialistOutcome, list[str], AgentStatus]:
        await env.add_agent(spec, status or AgentStatus.ASSIGNED)
        env.script = script
        outcome = await run_specialist(env.deps, spec, make_task(spec), reservation_id=RESERVATION)
        audit = [e.kind for e in await env.stores.audit.events(agent_id=spec.agent_id)]
        return outcome, audit, (await env.stores.registry.get(spec.agent_id)).status

    return run_async(scenario())


def content_filter_error() -> openai.BadRequestError:
    response = httpx2.Response(400, request=httpx2.Request("POST", "https://example.invalid/x"))
    return openai.BadRequestError(
        "blocked",
        response=response,
        body={"code": "content_filter", "innererror": {"code": "ResponsibleAIPolicyViolation"}},
    )


@pytest.fixture
def env() -> WorkerEnv:
    return make_env()


# ------------------------------------------------------------------ a successful run
def test_a_run_ends_in_a_valid_agent_result_with_the_evidence_it_cited(env: WorkerEnv) -> None:
    spec = make_spec(tools=[grant()])
    outcome, audit, registry = run(
        env,
        spec,
        [
            tool_call_message("fake_search", SEARCH_ARGS, input_tokens=100, output_tokens=50),
            final_answer(spec, input_tokens=200, output_tokens=100),
        ],
    )
    assert outcome.status == "awaiting_review" and outcome.error is None
    assert outcome.result is not None
    assert [e.evidence_id for e in outcome.result.evidence] == [evidence_id(spec)]
    assert {i for c in outcome.result.output.claims for i in c.evidence_ids} == {evidence_id(spec)}
    assert outcome.result.agent_id == spec.agent_id
    assert registry is AgentStatus.AWAITING_REVIEW
    assert audit == ["tool.called"]


def test_a_result_that_cites_evidence_the_gateway_never_issued_is_rejected(
    env: WorkerEnv,
) -> None:
    spec = make_spec(tools=[grant()])
    outcome, audit, registry = run(
        env,
        spec,
        [
            tool_call_message("fake_search", SEARCH_ARGS),
            tool_call_message("SpecialistOutput", specialist_output_args(2, ["ev_invented"])),
        ],
    )
    assert outcome.status == "failed" and outcome.result is None
    assert "invalid result" in (outcome.error or "")
    assert "result.invalid_citation" in audit and registry is AgentStatus.FAILED


def test_the_agent_gets_the_task_in_the_user_message_and_the_prompt_in_the_system_message(
    env: WorkerEnv,
) -> None:
    spec = make_spec(tools=[])
    run(env, spec, [plain_answer()])
    sent = env.models[0].seen[0]
    assert sent[0].type == "system" and sent[0].content == spec.prompt.rendered
    assert sent[1].type == "human" and "Compare the integration options." in str(sent[1].content)


# ------------------------------------------------------------------ metering and budget
def test_every_model_call_is_metered_from_the_providers_counts_and_priced_from_the_catalogue(
    env: WorkerEnv,
) -> None:
    spec = make_spec(tools=[grant()])
    outcome, _, _ = run(
        env,
        spec,
        [
            tool_call_message("fake_search", SEARCH_ARGS, input_tokens=100, output_tokens=50),
            final_answer(spec, input_tokens=200, output_tokens=100),
        ],
    )
    assert (outcome.usage.input_tokens, outcome.usage.output_tokens) == (300, 150)
    assert (outcome.usage.model_calls, outcome.usage.tool_calls) == (2, 1)
    assert outcome.usage.cost == env.catalogue.cost("reasoning-standard", 300, 150)
    assert outcome.usage.cost > 0

    async def settled() -> tuple[str, Decimal | None]:
        record = await env.stores.ledger.reservation(RESERVATION)
        return record.state, record.settled_amount

    state, amount = run_async(settled())
    assert state == "settled" and amount == outcome.usage.cost


def test_the_run_stops_before_the_next_model_call_when_the_token_budget_is_spent(
    env: WorkerEnv,
) -> None:
    spec = make_spec(tools=[grant()], budget=budget(max_tokens=1000))
    outcome, audit, registry = run(
        env,
        spec,
        [
            tool_call_message("fake_search", SEARCH_ARGS, input_tokens=600, output_tokens=600),
            final_answer(spec),
        ],
    )
    assert outcome.status == "blocked_budget" and outcome.error == "budget:tokens"
    assert env.models[0].calls == 1, "no second model call was made"
    assert "budget.stopped" in audit and registry is AgentStatus.FAILED
    assert outcome.usage.input_tokens + outcome.usage.output_tokens == 1200


def test_the_run_stops_when_the_cost_budget_is_spent(env: WorkerEnv) -> None:
    spec = make_spec(
        tools=[grant()],
        budget=make_spec().budget.model_copy(update={"max_cost": Decimal("0.001")}),
    )
    outcome, audit, _ = run(
        env,
        spec,
        [tool_call_message("fake_search", SEARCH_ARGS, input_tokens=0, output_tokens=1000)],
    )
    assert outcome.status == "blocked_budget" and outcome.error == "budget:cost"
    assert "budget.stopped" in audit


def test_what_a_stopped_run_spent_is_still_settled_against_its_reservation(
    env: WorkerEnv,
) -> None:
    spec = make_spec(tools=[grant()], budget=budget(max_tokens=100))
    outcome, _, _ = run(
        env,
        spec,
        [tool_call_message("fake_search", SEARCH_ARGS, input_tokens=80, output_tokens=80)],
    )

    async def settled() -> Decimal | None:
        return (await env.stores.ledger.reservation(RESERVATION)).settled_amount

    assert outcome.status == "blocked_budget"
    assert run_async(settled()) == outcome.usage.cost


def test_the_model_call_limit_ends_the_run_without_an_answer(env: WorkerEnv) -> None:
    spec = make_spec(
        tools=[grant()], budget=make_spec().budget.model_copy(update={"max_model_calls": 2})
    )
    outcome, _, registry = run(env, spec, [tool_call_message("fake_search", {"query": "again"})])
    assert outcome.status == "failed" and "no structured output" in (outcome.error or "")
    assert env.models[0].calls == 2 and registry is AgentStatus.FAILED


# ------------------------------------------------------------------ structured-output errors
def test_validation_errors_are_counted_by_our_code_and_the_model_is_asked_to_correct(
    env: WorkerEnv,
) -> None:
    spec = make_spec(tools=[])
    bad = tool_call_message("SpecialistOutput", {"executive_summary": "only this"})
    good = plain_answer()
    outcome, _, _ = run(env, spec, [bad, bad, good])
    assert outcome.status == "awaiting_review"
    meter = env.deps.meters.get(spec.agent_id)
    assert meter is not None and meter.validation_errors == 2
    retry_prompt = " ".join(str(m.content) for m in env.models[0].seen[1])
    assert "did not match the required schema (attempt 1)" in retry_prompt


def test_too_many_validation_errors_end_the_run(env: WorkerEnv) -> None:
    spec = make_spec(tools=[])  # max_retries is 2, so a third error is one too many
    bad = tool_call_message("SpecialistOutput", {"executive_summary": "only this"})
    outcome, _, registry = run(env, spec, [bad])
    assert outcome.status == "failed" and outcome.error == "stopped: validation_errors"
    meter = env.deps.meters.get(spec.agent_id)
    assert meter is not None and meter.validation_errors == 3
    assert registry is AgentStatus.FAILED


# ------------------------------------------------------------------ content filter and failures
def test_a_prompt_the_content_filter_blocks_is_never_retried_and_fails_to_the_lead(
    env: WorkerEnv,
) -> None:
    spec = make_spec(tools=[])
    outcome, audit, registry = run(env, spec, [content_filter_error()])
    assert env.models[0].calls == 1, "a blocked prompt is not sent again"
    assert outcome.status == "failed" and outcome.error == "content_filter_blocked"
    assert audit == ["guardrail.content_filter_block"] and registry is AgentStatus.FAILED
    events = run_async(env.stores.audit.events(kind="guardrail.content_filter_block"))
    assert "prompt" not in json.dumps(dict(events[0].details)).lower()


def test_a_transient_model_failure_is_retried_and_then_succeeds(env: WorkerEnv) -> None:
    spec = make_spec(tools=[])
    ok = plain_answer()
    outcome, _, _ = run(env, spec, [ConnectionError("blip"), ok])
    assert outcome.status == "awaiting_review"
    assert env.models[0].calls == 2


def test_a_model_that_keeps_failing_is_retried_a_bounded_number_of_times_then_raised(
    env: WorkerEnv,
) -> None:
    spec = make_spec(tools=[])  # max_retries is 2: one try and two retries
    with pytest.raises(ConnectionError):
        run(env, spec, [ConnectionError("down")])
    assert env.models[0].calls == 3


def test_a_model_refusal_is_a_failure_not_an_answer(env: WorkerEnv) -> None:
    spec = make_spec(tools=[])
    refusal = AIMessage(content=[{"type": "refusal", "refusal": "I cannot help"}])
    outcome, audit, _ = run(env, spec, [refusal])
    assert outcome.status == "failed" and outcome.error == "model_refusal"
    assert audit == ["guardrail.model_refusal"] and outcome.result is None


def test_a_stuck_tool_does_not_end_the_run_the_model_is_told_and_goes_on() -> None:
    from orchestrator.tools.impl.fake import FakeSearch

    env = make_env(search=FakeSearch(fail_times=99))
    spec = make_spec(tools=[grant()])
    outcome, audit, _ = run(
        env,
        spec,
        [
            tool_call_message("fake_search", SEARCH_ARGS),
            tool_call_message("SpecialistOutput", specialist_output_args(1, ["ev_x"])),
        ],
    )
    # The model cited an id it was never given, so the result is rejected: the run was not aborted
    # by the tool failure, it reached the answer.
    assert "tool.failed" in audit
    assert outcome.status == "failed" and "invalid result" in (outcome.error or "")
    told = " ".join(str(m.content) for m in env.models[0].seen[1])
    assert "needs_human_decision" in told


# ------------------------------------------------------------------ refusals before the model
def test_a_model_not_cleared_for_the_data_is_refused_before_any_call(env: WorkerEnv) -> None:
    spec = make_spec(tools=[], clearance=Classification.CONFIDENTIAL)
    outcome, audit, _ = run(env, spec, [AIMessage("never sent")])
    assert outcome.status == "failed" and outcome.error == "stopped: model_clearance"
    assert audit == ["model.clearance_refused"] and env.models == []


def test_a_prompt_whose_hash_does_not_match_is_not_run(env: WorkerEnv) -> None:
    spec = make_spec(tools=[])
    tampered = spec.model_copy(
        update={"prompt": spec.prompt.model_copy(update={"sha256": "0" * 64})}
    )
    outcome, audit, _ = run(env, tampered, [AIMessage("never sent")])
    assert outcome.error == "stopped: prompt_hash_mismatch"
    assert audit == ["prompt.hash_mismatch"] and env.models == []


def test_a_killed_agent_ends_cancelled_before_the_model_is_called(env: WorkerEnv) -> None:
    spec = make_spec(tools=[])
    env.kill.kill_agent(spec.agent_id)
    outcome, _, registry = run(env, spec, [AIMessage("never")])
    assert outcome.status == "cancelled" and registry is AgentStatus.CANCELLED
    assert env.models[0].calls == 0


def test_a_suspended_agent_keeps_its_status_and_the_outcome_says_suspended(
    env: WorkerEnv,
) -> None:
    spec = make_spec(tools=[grant()])

    async def scenario() -> tuple[SpecialistOutcome, AgentStatus]:
        await env.add_agent(spec, AgentStatus.RUNNING)
        await env.stores.registry.transition(spec.agent_id, AgentStatus.SUSPENDED)
        env.script = [tool_call_message("fake_search", SEARCH_ARGS), final_answer(spec)]
        outcome = await run_specialist(env.deps, spec, make_task(spec), reservation_id=RESERVATION)
        return outcome, (await env.stores.registry.get(spec.agent_id)).status

    outcome, status = run_async(scenario())
    assert outcome.status == "suspended" and status is AgentStatus.SUSPENDED
    assert env.search.calls == 0


# ------------------------------------------------------------------ revisions
def test_a_revision_settles_only_its_own_spend(env: WorkerEnv) -> None:
    spec = make_spec(tools=[])
    answer = plain_answer(input_tokens=1000, output_tokens=500)

    async def scenario() -> tuple[Decimal | None, Decimal | None, SpecialistOutcome]:
        await env.add_agent(spec)
        env.script = [answer]
        first = await run_specialist(env.deps, spec, make_task(spec), reservation_id=RESERVATION)
        await env.stores.registry.transition(spec.agent_id, AgentStatus.REVISION_REQUESTED)
        await env.stores.ledger.reserve("res_2", ["prj_ab12"], Decimal("1"))
        second = await run_specialist(
            env.deps,
            spec,
            make_task(spec),
            reservation_id="res_2",
            revision=1,
            comments=["be more specific"],
        )
        one = (await env.stores.ledger.reservation(RESERVATION)).settled_amount
        two = (await env.stores.ledger.reservation("res_2")).settled_amount
        assert first.usage.cost * 2 == second.usage.cost, "usage is cumulative across revisions"
        return one, two, second

    one, two, second = run_async(scenario())
    assert one == two, "the second reservation was charged for its own run, not both"
    assert "be more specific" in " ".join(str(m.content) for m in env.models[1].seen[0])
