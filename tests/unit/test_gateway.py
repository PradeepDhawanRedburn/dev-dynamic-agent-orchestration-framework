"""The tool gateway (ADR-0006): grants, limits, retirement, clearance, evidence and audit."""

import json
from typing import Any

import pytest

from orchestrator.contracts import AgentSpecification, AgentStatus, ToolPermission
from orchestrator.tools.gateway import (
    AgentStopped,
    ToolGateway,
    bind_tool,
    evidence_id_for,
    idempotency_key,
)
from orchestrator.tools.impl.fake import DEFAULT_ITEM, FakeSearch
from tests.conftest import run_async
from tests.worker_env import RESERVATION, WorkerEnv, grant, make_env, make_spec


def gateway_for(env: WorkerEnv, spec: AgentSpecification) -> ToolGateway:
    env.deps.meters.for_agent(spec.agent_id, spec.model.deployment, spec.budget)
    return env.deps.gateway


async def kinds(env: WorkerEnv, spec: AgentSpecification) -> list[str]:
    return [e.kind for e in await env.stores.audit.events(agent_id=spec.agent_id)]


def call(env: WorkerEnv, spec: AgentSpecification, g: ToolPermission, **args: Any) -> str:
    async def scenario() -> str:
        return await gateway_for(env, spec).call(spec, g, args or {"query": "rest"})

    return run_async(scenario())


@pytest.fixture
def env() -> WorkerEnv:
    return make_env(consequential_tool=True)


def test_a_granted_call_runs_stores_evidence_and_is_audited(env: WorkerEnv) -> None:
    g = grant()
    spec = make_spec(tools=[g])

    async def scenario() -> tuple[str, list[str], list[object]]:
        await env.add_agent(spec, AgentStatus.RUNNING)
        text = await gateway_for(env, spec).call(spec, g, {"query": "rest"})
        stored = await env.stores.evidence.for_agent(spec.project_id, spec.agent_id)
        return text, await kinds(env, spec), list(stored)

    text, audit, stored = run_async(scenario())
    body = json.loads(text)
    assert "untrusted data" in body["notice"]
    item = body["items"][0]
    key = idempotency_key(spec.agent_id, "fake_search", {"query": "rest"})
    assert item["evidence_id"] == evidence_id_for(key, 0)
    assert len(stored) == 1 and stored[0].captured_by_agent == spec.agent_id  # type: ignore[attr-defined]
    assert audit == ["tool.called"]


def test_the_audit_event_of_a_full_io_tool_records_the_arguments_and_a_result_hash(
    env: WorkerEnv,
) -> None:
    g = grant()
    spec = make_spec(tools=[g])

    async def scenario() -> dict[str, Any]:
        await env.add_agent(spec, AgentStatus.RUNNING)
        await gateway_for(env, spec).call(spec, g, {"query": "rest"})
        return dict(
            (await env.stores.audit.events(agent_id=spec.agent_id, kind="tool.called"))[0].details
        )

    details = run_async(scenario())
    assert details["arguments"] == {"query": "rest"}
    assert len(str(details["result_sha256"])) == 64 and "idempotency_key" in details


def test_a_tool_that_was_not_granted_is_refused_and_audited(env: WorkerEnv) -> None:
    spec = make_spec(tools=[grant()])
    other = grant("model_catalogue_read")

    async def scenario() -> tuple[str, list[str]]:
        await env.add_agent(spec, AgentStatus.RUNNING)
        return await gateway_for(env, spec).call(spec, other, {}), await kinds(env, spec)

    text, audit = run_async(scenario())
    assert json.loads(text) == {"error": "permission_denied"}
    assert audit == ["tool.denied"]
    assert env.search.calls == 0


def test_a_consequential_tool_is_never_run_even_if_it_was_somehow_granted(env: WorkerEnv) -> None:
    g = grant("fake_publish")
    spec = make_spec(tools=[g])

    async def scenario() -> tuple[str, list[str]]:
        await env.add_agent(spec, AgentStatus.RUNNING)
        return await gateway_for(env, spec).call(spec, g, {"query": "x"}), await kinds(env, spec)

    text, audit = run_async(scenario())
    assert json.loads(text) == {"error": "permission_denied"}
    assert audit == ["tool.denied"]


def test_calls_past_the_grants_limit_are_refused_and_still_counted(env: WorkerEnv) -> None:
    g = grant(max_calls=2)
    spec = make_spec(tools=[g])

    async def scenario() -> tuple[list[str], int, list[str]]:
        await env.add_agent(spec, AgentStatus.RUNNING)
        gateway = gateway_for(env, spec)
        replies = [await gateway.call(spec, g, {"query": f"q{i}"}) for i in range(4)]
        return (
            replies,
            await env.stores.counters.count(spec.agent_id, "fake_search"),
            await kinds(env, spec),
        )

    replies, counted, audit = run_async(scenario())
    assert [("error" in json.loads(r)) for r in replies] == [False, False, True, True]
    assert json.loads(replies[2]) == {"error": "call_limit_reached"}
    assert counted == 4, "a refused call counts, so a loop cannot probe the limit"
    assert audit.count("tool.limit_reached") == 2 and env.search.calls == 2


@pytest.mark.parametrize(
    "status,reason",
    [
        (AgentStatus.RETIRED, "retired"),
        (AgentStatus.ACCEPTED, "retired"),
        (AgentStatus.SUSPENDED, "suspended"),
        (AgentStatus.CANCELLED, "cancelled"),
    ],
)
def test_a_call_after_retirement_or_suspension_is_stopped_and_audited(
    env: WorkerEnv, status: AgentStatus, reason: str
) -> None:
    g = grant()
    spec = make_spec(tools=[g])

    async def scenario() -> list[str]:
        await env.add_agent(spec, status)
        with pytest.raises(AgentStopped) as stopped:
            await gateway_for(env, spec).call(spec, g, {"query": "x"})
        assert stopped.value.reason == reason
        return await kinds(env, spec)

    assert run_async(scenario()) == ["tool.denied"]
    assert env.search.calls == 0


def test_the_kill_switch_stops_a_call_before_anything_else(env: WorkerEnv) -> None:
    g = grant()
    spec = make_spec(tools=[g])
    env.kill.kill_agent(spec.agent_id)

    async def scenario() -> list[str]:
        await env.add_agent(spec, AgentStatus.RUNNING)
        with pytest.raises(AgentStopped, match="cancelled"):
            await gateway_for(env, spec).call(spec, g, {"query": "x"})
        return await kinds(env, spec)

    assert run_async(scenario()) == ["tool.denied"], "a refused call is audited"
    assert env.search.calls == 0


def test_a_malformed_call_through_the_bound_tool_still_reaches_the_gateway(
    env: WorkerEnv,
) -> None:
    """The model's tool must not validate the arguments itself, or a malformed call would be
    neither counted nor audited."""
    g = grant()
    spec = make_spec(tools=[g])

    async def scenario() -> tuple[str, int, list[str]]:
        await env.add_agent(spec, AgentStatus.RUNNING)
        tool = bind_tool(spec, g, gateway_for(env, spec))
        reply = await tool.ainvoke({"query": "", "extra": "x"})
        return (
            str(reply),
            await env.stores.counters.count(spec.agent_id, "fake_search"),
            await kinds(env, spec),
        )

    reply, counted, audit = run_async(scenario())
    assert json.loads(reply)["error"] == "invalid_arguments"
    assert counted == 1 and audit == ["tool.invalid_arguments"]


def test_the_model_is_still_shown_the_tools_own_schema() -> None:
    env = make_env()
    spec = make_spec(tools=[grant()])
    tool = bind_tool(spec, grant(), env.deps.gateway)
    schema = tool.tool_call_schema
    properties = schema["properties"] if isinstance(schema, dict) else {}
    assert properties["query"]["maxLength"] == 200


def test_a_source_that_changed_between_two_identical_calls_is_not_cited_under_the_old_id() -> None:
    class Changing(FakeSearch):
        async def run(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
            self.calls += 1
            return {"items": [{**DEFAULT_ITEM, "text": f"version {self.calls} of the page"}]}

    env = make_env(search=Changing())
    g = grant()
    spec = make_spec(tools=[g])

    async def scenario() -> tuple[str, str, list[str]]:
        await env.add_agent(spec, AgentStatus.RUNNING)
        gateway = gateway_for(env, spec)
        first = await gateway.call(spec, g, {"query": "same"})
        second = await gateway.call(spec, g, {"query": "same"})
        return first, second, await kinds(env, spec)

    first, second, audit = run_async(scenario())
    assert "evidence_id" in json.loads(first)["items"][0]
    assert json.loads(second)["items"] == [
        {"withheld": "the source changed since it was first captured"}
    ]
    assert "version 2" not in second
    assert "tool.evidence_changed" in audit


def test_arguments_that_do_not_match_the_tools_schema_are_refused_with_field_names_only(
    env: WorkerEnv,
) -> None:
    g = grant()
    spec = make_spec(tools=[g])

    async def scenario() -> tuple[str, list[str]]:
        await env.add_agent(spec, AgentStatus.RUNNING)
        gateway = gateway_for(env, spec)
        return await gateway.call(spec, g, {"query": "", "extra": "x"}), await kinds(env, spec)

    text, audit = run_async(scenario())
    body = json.loads(text)
    assert body["error"] == "invalid_arguments" and body["fields"] == ["extra", "query"]
    assert audit == ["tool.invalid_arguments"] and env.search.calls == 0


def test_content_above_the_agents_clearance_is_withheld_and_not_stored_as_evidence() -> None:
    secret = {**DEFAULT_ITEM, "classification": "confidential", "text": "board minutes"}
    env = make_env(search=FakeSearch([secret, DEFAULT_ITEM]))
    g = grant()
    spec = make_spec(tools=[g])

    async def scenario() -> tuple[str, int, list[str]]:
        await env.add_agent(spec, AgentStatus.RUNNING)
        text = await gateway_for(env, spec).call(spec, g, {"query": "x"})
        stored = await env.stores.evidence.for_agent(spec.project_id, spec.agent_id)
        return text, len(stored), await kinds(env, spec)

    text, stored, audit = run_async(scenario())
    items = json.loads(text)["items"]
    assert items[0] == {"withheld": "content above your clearance"}
    assert "board minutes" not in text
    assert "evidence_id" in items[1] and stored == 1
    assert audit == ["tool.withheld", "tool.called"]


def test_repeating_the_same_call_gives_the_same_evidence_ids_without_a_conflict(
    env: WorkerEnv,
) -> None:
    g = grant()
    spec = make_spec(tools=[g])

    async def scenario() -> tuple[str, str, int]:
        await env.add_agent(spec, AgentStatus.RUNNING)
        gateway = gateway_for(env, spec)
        first = await gateway.call(spec, g, {"query": "same"})
        second = await gateway.call(spec, g, {"query": "same"})
        stored = await env.stores.evidence.for_agent(spec.project_id, spec.agent_id)
        return first, second, len(stored)

    first, second, stored = run_async(scenario())
    assert (
        json.loads(first)["items"][0]["evidence_id"]
        == json.loads(second)["items"][0]["evidence_id"]
    )
    assert stored == 1


def test_a_tool_failure_goes_through_self_healing_and_a_stuck_call_reaches_a_person() -> None:
    env = make_env(search=FakeSearch(fail_times=99))
    g = grant()
    spec = make_spec(tools=[g])

    async def scenario() -> tuple[str, list[str]]:
        await env.add_agent(spec, AgentStatus.RUNNING)
        return await gateway_for(env, spec).call(spec, g, {"query": "x"}), await kinds(env, spec)

    text, audit = run_async(scenario())
    body = json.loads(text)
    assert body["error"] == "needs_human_decision" and body["incident_id"].startswith("inc_")
    assert audit == ["tool.failed"] and env.incidents and not env.incidents[0].resolved


def test_a_transient_tool_failure_is_healed_and_the_call_succeeds() -> None:
    env = make_env(search=FakeSearch(fail_times=1))
    g = grant()
    spec = make_spec(tools=[g])

    async def scenario() -> tuple[str, list[str]]:
        await env.add_agent(spec, AgentStatus.RUNNING)
        return await gateway_for(env, spec).call(spec, g, {"query": "x"}), await kinds(env, spec)

    text, audit = run_async(scenario())
    assert "items" in json.loads(text) and audit == ["tool.called"]
    assert env.incidents[0].resolved, "a healed fault is still reported"


def test_each_call_is_metered(env: WorkerEnv) -> None:
    g = grant()
    spec = make_spec(tools=[g])

    async def scenario() -> int:
        await env.add_agent(spec, AgentStatus.RUNNING)
        gateway = gateway_for(env, spec)
        await gateway.call(spec, g, {"query": "a"})
        await gateway.call(spec, g, {"query": "b"})
        meter = env.deps.meters.get(spec.agent_id)
        assert meter is not None
        return meter.usage().tool_calls

    assert run_async(scenario()) == 2


def test_the_reservation_exists_for_the_worker_tests(env: WorkerEnv) -> None:
    spec = make_spec(tools=[grant()])

    async def scenario() -> str:
        await env.add_agent(spec)
        return (await env.stores.ledger.reservation(RESERVATION)).state

    assert run_async(scenario()) == "reserved"
