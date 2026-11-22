import asyncio
import socket
from collections import Counter
from typing import Never

import pytest

from orchestrator.contracts import (
    AgentStatus,
    IllegalTransition,
    LeadRole,
)
from orchestrator.governance.guardrails import GuardrailMonitor, Verdict, evaluate, tighten
from orchestrator.governance.recruiter import InMemoryAgentRegistry, Policy, Recruiter
from orchestrator.governance.resilience import (
    HUMAN_OPTIONS,
    RUNBOOKS,
    FailureKind,
    NeedsHuman,
    SelfHealer,
    Step,
    classify,
)
from tests.unit.test_core import make_request, registry
from tests.unit.test_recruiter import Mem


class Creds:
    def __init__(self):
        self.live, self.frozen = {}, set()

    def issue(self, a, g, t) -> None:
        self.live[a] = t

    def revoke(self, a) -> bool:
        self.live.pop(a, None)
        return True

    def freeze(self, a) -> None:
        self.frozen.add(a)

    def unfreeze(self, a) -> None:
        self.frozen.discard(a)


def rec():
    c = Creds()
    r = Recruiter(
        tools=registry(),
        agents=InMemoryAgentRegistry(),
        credentials=c,
        memory=Mem(),
        policy=Policy(),
        task_owner=lambda t: LeadRole.SOFTWARE,
    )
    return r, c


def test_suspend_freezes_and_blocks_progress_until_human_resumes() -> None:
    r, c = rec()
    spec = r.provision(make_request())
    a = spec.agent_id
    r.agents.transition(a, AgentStatus.ASSIGNED)
    r.agents.transition(a, AgentStatus.RUNNING)
    r.suspend(a, "tool.denied x3")
    r.suspend(a, "again")
    assert r.agents.get(a).status is AgentStatus.SUSPENDED and a in c.frozen and a in c.live
    with pytest.raises(IllegalTransition):
        r.agents.transition(a, AgentStatus.RUNNING)
    with pytest.raises(IllegalTransition):
        r.agents.transition(a, AgentStatus.ACCEPTED)
    with pytest.raises(ValueError):
        r.resume(a, approver="", has_held_result=False)
    r.resume(a, approver="security-owner-oid", has_held_result=False)
    assert r.agents.get(a).status is AgentStatus.ASSIGNED and a not in c.frozen


def test_suspended_agent_can_be_terminated_and_is_fully_revoked() -> None:
    r, c = rec()
    a = r.provision(make_request()).agent_id
    r.agents.transition(a, AgentStatus.ASSIGNED)
    r.suspend(a, "x")
    out = r.retire(
        a, final_status=AgentStatus.FAILED, reason="terminated after guardrail suspension"
    )
    assert out.final_status is AgentStatus.FAILED and a not in c.live


def test_held_result_goes_to_review_on_resume() -> None:
    r, _ = rec()
    a = r.provision(make_request()).agent_id
    for s in (AgentStatus.ASSIGNED, AgentStatus.RUNNING):
        r.agents.transition(a, s)
    r.suspend(a, "x")
    r.resume(a, approver="h", has_held_result=True)
    assert r.agents.get(a).status is AgentStatus.AWAITING_REVIEW


def test_rules_flag_then_suspend() -> None:
    assert evaluate(Counter(), "a").action == "none"
    assert evaluate(Counter({"tool.denied": 1}), "a").action == "flag"
    assert evaluate(Counter({"tool.denied": 3}), "a").action == "suspend"
    assert evaluate(Counter({"tool.withheld": 1}), "a").action == "suspend"
    assert evaluate(Counter({"budget.stopped": 9}), "a").action == "flag"
    v = evaluate(Counter({"budget.stopped": 1, "agent.spawn_attempt": 1}), "a")
    assert (v.action, v.rule) == ("suspend", "agent.spawn_attempt")


def test_model_can_tighten_never_loosen() -> None:
    flag, susp, none = (Verdict(agent_id="a", action=x) for x in ("flag", "suspend", "none"))
    assert tighten(flag, True).action == "suspend" and tighten(flag, False).action == "flag"
    assert tighten(susp, False).action == "suspend" and tighten(none, True).action == "none"


def test_monitor_suspends_once_in_real_time_and_resets_on_clear() -> None:
    calls = []
    m = GuardrailMonitor(lambda a, why: calls.append((a, why)))
    assert [m.observe("a", "tool.injection_flag").action for _ in range(4)] == [
        "flag",
        "flag",
        "suspend",
        "suspend",
    ]
    assert (
        calls == [("a", "tool.injection_flag x3")]
        and m.observe("b", "tool.called").action == "none"
    )
    m.cleared("a")
    assert m.observe("a", "tool.injection_flag").action == "flag" and len(calls) == 1


class E(Exception):
    def __init__(self, status):
        self.status_code = status


def test_classify() -> None:
    assert (
        classify(E(429)) is FailureKind.THROTTLED and classify(E(401)) is FailureKind.AUTH_EXPIRED
    )
    assert (
        classify(E(503)) is FailureKind.DEPENDENCY_DOWN
        and classify(socket.gaierror()) is FailureKind.DNS_FAILURE
    )
    assert (
        classify(ConnectionResetError()) is FailureKind.NETWORK_LOST
        and classify(TimeoutError()) is FailureKind.TIMEOUT
    )
    assert classify(KeyError("x")) is FailureKind.UNKNOWN
    assert all(steps[-1] is Step.ESCALATE for steps in RUNBOOKS.values()) and set(RUNBOOKS) == set(
        FailureKind
    )


def healer(fail_steps=()):
    log, incidents = [], []

    async def act(step, inc, attempt):
        log.append(step)
        return step not in fail_steps

    async def record(inc) -> None:
        incidents.append(inc)

    return (
        SelfHealer(
            {s: (lambda inc, n, s=s: act(s, inc, n)) for s in Step if s is not Step.ESCALATE},
            record,
        ),
        log,
        incidents,
    )


def op(errors):
    errors = list(errors)

    async def run() -> str:
        if errors:
            raise errors.pop(0)
        return "ok"

    return run


def go(h, o):
    return asyncio.run(h.run(o, name="tool:web_search", project_id="p", agent_id="a"))


def test_network_blip_heals_without_a_human() -> None:
    h, log, inc = healer()
    assert go(h, op([ConnectionResetError()])) == "ok"
    assert (
        log == [Step.PROBE, Step.RETRY_BACKOFF]
        and inc[0].resolved
        and inc[0].kind is FailureKind.NETWORK_LOST
    )


def test_expired_token_is_refreshed() -> None:
    h, log, inc = healer()
    assert go(h, op([E(401)])) == "ok" and log == [Step.REFRESH_CREDENTIAL]


def test_dependency_down_switches_to_alternate() -> None:
    h, log, _ = healer()
    assert go(h, op([E(503)])) == "ok" and log == [Step.PROBE, Step.SWITCH_ENDPOINT]


def test_persistent_outage_escalates_with_history_and_options() -> None:
    h, log, inc = healer()
    with pytest.raises(NeedsHuman) as e:
        go(h, op([ConnectionResetError()] * 9))
    i = e.value.incident
    assert [s for s, _ in i.steps_tried] == [
        Step.PROBE,
        Step.RETRY_BACKOFF,
        Step.RETRY_BACKOFF,
        Step.SWITCH_ENDPOINT,
    ]
    assert not i.resolved and i.options == HUMAN_OPTIONS and inc == [i]


def test_unknown_fault_is_never_guessed_at() -> None:
    h, log, _ = healer()
    with pytest.raises(NeedsHuman):
        go(h, op([KeyError("weird")]))
    assert log == []


def test_failed_remediation_step_does_not_retry_operation() -> None:
    h, log, _ = healer(fail_steps={Step.REFRESH_CREDENTIAL})
    calls = []

    async def o() -> Never:
        calls.append(1)
        raise E(401)

    with pytest.raises(NeedsHuman):
        go(h, o)
    assert len(calls) == 1
