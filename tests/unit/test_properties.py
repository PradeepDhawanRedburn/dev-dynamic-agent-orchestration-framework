"""Property-based tests (Hypothesis) for the lifecycle transition table, the ledger and the audit
chain. They need no database. The same ledger properties run against PostgreSQL in
tests/integration/test_properties_postgres.py."""

from decimal import Decimal
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from orchestrator.contracts import (
    ALLOWED_TRANSITIONS,
    AgentSpecification,
    AgentStatus,
    IllegalTransition,
    Usage,
    assert_transition,
)
from orchestrator.governance.budget import BudgetExceeded, BudgetLedger, InMemoryLedger
from orchestrator.governance.recruiter import InMemoryAgentRegistry
from orchestrator.persistence.audit import (
    GENESIS_HASH,
    InMemoryAuditLog,
    check_chain,
)
from tests.support import make_recruiter, make_request

STATUSES = list(AgentStatus)
TERMINAL = {
    AgentStatus.ACCEPTED,
    AgentStatus.FAILED,
    AgentStatus.CANCELLED,
    AgentStatus.TIMED_OUT,
    AgentStatus.REJECTED,
}


# ---------------------------------------------------------------- the transition table
def test_the_table_covers_every_status_and_only_leads_to_statuses() -> None:
    assert set(ALLOWED_TRANSITIONS) == set(AgentStatus)
    for current, targets in ALLOWED_TRANSITIONS.items():
        assert targets <= set(AgentStatus)
        assert current not in targets, (
            "no status moves to itself: that is a no-op, not a transition"
        )


def test_retired_is_final_and_only_a_finished_agent_can_retire() -> None:
    assert ALLOWED_TRANSITIONS[AgentStatus.RETIRED] == set()
    for status, targets in ALLOWED_TRANSITIONS.items():
        if AgentStatus.RETIRED in targets:
            assert status in TERMINAL, f"{status} may not retire straight away"
    for status in TERMINAL:
        assert ALLOWED_TRANSITIONS[status] == {AgentStatus.RETIRED}


def test_no_status_is_a_dead_end_and_everything_is_reachable_from_the_start() -> None:
    def reachable_from(start: AgentStatus) -> set[AgentStatus]:
        seen, frontier = {start}, [start]
        while frontier:
            for nxt in ALLOWED_TRANSITIONS[frontier.pop()]:
                if nxt not in seen:
                    seen.add(nxt)
                    frontier.append(nxt)
        return seen

    for status in AgentStatus:
        assert AgentStatus.RETIRED in reachable_from(status), f"{status} can never be retired"
    assert reachable_from(AgentStatus.REQUESTED) == set(AgentStatus) - set()


def test_suspension_is_reversible_but_never_skips_review() -> None:
    assert ALLOWED_TRANSITIONS[AgentStatus.SUSPENDED] == {
        AgentStatus.ASSIGNED,
        AgentStatus.AWAITING_REVIEW,
        AgentStatus.FAILED,
        AgentStatus.CANCELLED,
    }
    assert AgentStatus.ACCEPTED not in ALLOWED_TRANSITIONS[AgentStatus.SUSPENDED]


@given(
    st.sampled_from(STATUSES),
    st.sampled_from(STATUSES),
)
def test_assert_transition_agrees_with_the_table_for_every_pair(
    current: AgentStatus, new: AgentStatus
) -> None:
    if new in ALLOWED_TRANSITIONS[current]:
        assert_transition(current, new)
    else:
        with pytest.raises(IllegalTransition):
            assert_transition(current, new)


# ---------------------------------------------------------------- a registry under random attempts
def fresh_agent() -> tuple[InMemoryAgentRegistry, str]:
    agents = InMemoryAgentRegistry()
    recruiter, _, _ = make_recruiter(agents)
    spec = recruiter.provision(make_request())
    assert isinstance(spec, AgentSpecification)
    return agents, spec.agent_id


@settings(max_examples=150, deadline=None)
@given(st.lists(st.sampled_from(STATUSES), max_size=40))
def test_random_transition_attempts_only_ever_follow_the_table(attempts: list[AgentStatus]) -> None:
    agents, agent_id = fresh_agent()
    expected = [AgentStatus.APPROVED, AgentStatus.PROVISIONED, AgentStatus.REGISTERED]
    current = AgentStatus.REGISTERED
    for new in attempts:
        if new == current:
            agents.transition(agent_id, new)  # a repeat changes nothing
        elif new in ALLOWED_TRANSITIONS[current]:
            agents.transition(agent_id, new)
            expected.append(new)
            current = new
        else:
            with pytest.raises(IllegalTransition):
                agents.transition(agent_id, new)
        record = agents.get(agent_id)
        assert record.status is current
        assert [s for s, _ in record.history] == expected
    if current is AgentStatus.RETIRED:
        for new in STATUSES:
            if new is not AgentStatus.RETIRED:
                with pytest.raises(IllegalTransition):
                    agents.transition(agent_id, new)


# ---------------------------------------------------------------- the ledger
D = Decimal
CHAINS = [["p", "p/a"], ["p", "p/b"], ["p/a"], ["p/b"], ["p"]]
amounts = st.decimals(min_value=D("0"), max_value=D("6"), places=2)
operations = st.lists(
    st.one_of(
        st.tuples(st.just("reserve"), st.integers(0, 5), st.sampled_from(CHAINS), amounts),
        st.tuples(
            st.just("settle"), st.integers(0, 5), st.sampled_from([0, 1, 2, 3, 4]), st.just(D(0))
        ),
        st.tuples(st.just("release"), st.integers(0, 5), st.just(None), st.just(D(0))),
    ),
    max_size=30,
)
LIMITS = {"p": D("10"), "p/a": D("6"), "p/b": D("6")}


def run_operations(ledger: BudgetLedger, ops: list[tuple[Any, ...]], prefix: str = "") -> list[Any]:
    """Apply `ops` and return what each one did. The same list must give the same answer on every
    implementation. A settlement never costs more than was reserved: the worker stops an agent at
    its limit, so the ledger is only ever told a cost within the reservation."""
    scoped = {f"{prefix}{scope}": limit for scope, limit in LIMITS.items()}
    for scope, limit in scoped.items():
        ledger.open_scope(scope, limit)
    reserved: dict[str, Decimal] = {}
    log: list[Any] = []
    for kind, index, extra, amount in ops:
        rid = f"{prefix}r{index}"
        try:
            if kind == "reserve":
                ledger.reserve(rid, [f"{prefix}{s}" for s in extra], amount)
                reserved.setdefault(rid, amount)
            elif kind == "settle":
                cost = reserved.get(rid, D("0.5")) * D(extra) / D(4)
                ledger.settle(rid, Usage(cost=cost))
            else:
                ledger.release(rid)
                reserved.pop(rid, None)
            log.append(("ok", kind))
        except BudgetExceeded as error:
            log.append(("exceeded", error.scope.removeprefix(prefix), error.limit, error.attempted))
        except KeyError:
            log.append(("unknown", kind))
        for scope, limit in scoped.items():
            snap = ledger.snapshot(scope)
            assert snap.committed >= 0 and snap.reserved >= 0
            assert snap.committed + snap.reserved <= limit, f"{scope} was overspent"
            log.append((scope.removeprefix(prefix), snap.committed, snap.reserved, snap.state))
    return log


@settings(max_examples=300, deadline=None)
@given(operations)
def test_no_sequence_of_operations_overspends_any_scope(ops: list[tuple[Any, ...]]) -> None:
    run_operations(InMemoryLedger(), ops)


class OverspendingLedger(InMemoryLedger):
    """A ledger with the limit check removed, to prove the property above can fail."""

    def reserve(self, reservation_id: str, chain: list[str], amount: Decimal) -> None:
        if reservation_id not in self._reservations and reservation_id not in self._settled:
            self._reservations[reservation_id] = (chain, amount)


def test_the_ledger_property_catches_a_ledger_that_overspends() -> None:
    @settings(max_examples=300, deadline=None, database=None)
    @given(operations)
    def check(ops: list[tuple[Any, ...]]) -> None:
        run_operations(OverspendingLedger(), ops)

    with pytest.raises(AssertionError, match="overspent"):
        check()


@settings(max_examples=100, deadline=None)
@given(operations)
def test_repeating_every_operation_gives_the_same_result_as_doing_it_once(
    ops: list[tuple[Any, ...]],
) -> None:
    once, twice = InMemoryLedger(), InMemoryLedger()
    run_operations(once, ops)
    doubled = [op for op in ops for _ in (0, 1)]
    run_operations(twice, doubled)
    for scope in LIMITS:
        a, b = once.snapshot(scope), twice.snapshot(scope)
        assert (a.committed, a.reserved) == (b.committed, b.reserved)


# ---------------------------------------------------------------- the audit chain
event_lists = st.lists(
    st.tuples(
        st.sampled_from(["tool.called", "tool.denied", "budget.reserved", "agent.retired"]),
        st.dictionaries(st.sampled_from(["a", "b", "c"]), st.integers(0, 9), max_size=3),
    ),
    min_size=1,
    max_size=12,
)


def logged(events: list[tuple[str, dict[str, int]]]) -> InMemoryAuditLog:
    log = InMemoryAuditLog()
    for kind, details in events:
        log.append(kind, actor="system:test", details=dict(details))
    return log


@settings(max_examples=100, deadline=None)
@given(event_lists)
def test_any_log_that_is_only_appended_to_verifies(
    events: list[tuple[str, dict[str, int]]],
) -> None:
    log = logged(events)
    report = log.verify_chain()
    assert report.ok and report.checked == len(events)
    stored = log.events()
    assert stored[0].prev_hash == GENESIS_HASH
    assert all(b.prev_hash == a.hash for a, b in zip(stored, stored[1:], strict=False))


@settings(max_examples=150, deadline=None)
@given(event_lists, st.data())
def test_changing_removing_or_reordering_any_event_is_detected(
    events: list[tuple[str, dict[str, int]]], data: st.DataObject
) -> None:
    log = logged(events)
    stored = log.events()
    head = (stored[-1].seq, stored[-1].hash)
    index = data.draw(st.integers(0, len(stored) - 1))

    changed = list(stored)
    changed[index] = changed[index].model_copy(update={"actor": "someone-else"})
    assert not check_chain(changed, head).ok
    assert check_chain(changed, head).first_bad_seq == index + 1

    removed = stored[:index] + stored[index + 1 :]
    assert not check_chain(removed, head).ok

    if len(stored) > 1:
        other = data.draw(st.integers(0, len(stored) - 1).filter(lambda i: i != index))
        swapped = list(stored)
        swapped[index], swapped[other] = swapped[other], swapped[index]
        assert not check_chain(swapped, head).ok
