"""The audit log: the same behaviour from both logs, plus the guarantees only PostgreSQL gives."""

import psycopg
import pytest
from opentelemetry.sdk.trace import TracerProvider
from pydantic import JsonValue, ValidationError

from orchestrator.persistence.audit import GENESIS_HASH, InMemoryAuditLog
from tests.integration.conftest import Stores


def test_events_are_numbered_and_chained_from_the_genesis_hash(stores: Stores) -> None:
    first = stores.audit.append("request.received", actor="system:intake", project_id="prj_1")
    second = stores.audit.append("tool.denied", actor="system:gateway", agent_id="agt_1")
    third = stores.audit.append("agent.suspended", actor="system:recruiter", agent_id="agt_1")
    assert [e.seq for e in (first, second, third)] == [1, 2, 3]
    assert first.prev_hash == GENESIS_HASH
    assert second.prev_hash == first.hash and third.prev_hash == second.hash
    assert len({first.hash, second.hash, third.hash}) == 3
    report = stores.audit.verify_chain()
    assert report.ok and report.checked == 3


def test_an_empty_log_verifies(stores: Stores) -> None:
    assert stores.audit.verify_chain().ok


def test_appending_with_the_same_event_id_writes_one_event(stores: Stores) -> None:
    a = stores.audit.append("budget.reserved", actor="system:ledger", event_id="aud_stable")
    b = stores.audit.append("budget.reserved", actor="system:ledger", event_id="aud_stable")
    assert a == b
    assert len(stores.audit.events()) == 1
    assert stores.audit.append("budget.settled", actor="system:ledger").seq == 2


def test_events_can_be_listed_by_project_agent_and_kind(stores: Stores) -> None:
    stores.audit.append("tool.denied", actor="s", project_id="prj_1", agent_id="agt_1")
    stores.audit.append("tool.called", actor="s", project_id="prj_1", agent_id="agt_2")
    stores.audit.append("tool.denied", actor="s", project_id="prj_2", agent_id="agt_1")
    assert [e.seq for e in stores.audit.events(project_id="prj_1")] == [1, 2]
    assert [e.seq for e in stores.audit.events(agent_id="agt_1")] == [1, 3]
    assert [e.seq for e in stores.audit.events(kind="tool.denied", project_id="prj_2")] == [3]


def test_details_and_identifiers_round_trip(stores: Stores) -> None:
    details: dict[str, JsonValue] = {
        "tool": "web_search",
        "attempt": 2,
        "ratio": 0.25,
        "flags": ["a", "b"],
        "n": None,
    }
    written = stores.audit.append(
        "tool.called",
        actor="agent:agt_1",
        project_id="prj_1",
        workstream_id="ws_1",
        task_id="task_1",
        agent_id="agt_1",
        correlation_id="cor_1",
        details=details,
    )
    (read,) = stores.audit.events()
    assert read == written and read.details == details
    assert stores.audit.verify_chain().ok


def test_an_event_kind_must_look_like_a_kind() -> None:
    log = InMemoryAuditLog()
    for bad in ("denied", "Tool.Denied", "tool denied", "tool."):
        with pytest.raises(ValidationError):
            log.append(bad, actor="s")


def test_an_event_records_the_trace_and_span_that_were_current(stores: Stores) -> None:
    tracer = TracerProvider().get_tracer("audit-test")
    outside = stores.audit.append("tool.called", actor="s")
    assert outside.trace_id is None and outside.span_id is None
    with tracer.start_as_current_span("node") as span:
        context = span.get_span_context()
        inside = stores.audit.append("tool.called", actor="s")
    assert inside.trace_id == format(context.trace_id, "032x")
    assert inside.span_id == format(context.span_id, "016x")
    stored = stores.audit.events()[1]
    assert (stored.trace_id, stored.span_id) == (inside.trace_id, inside.span_id)
    assert stores.audit.verify_chain().ok, "the ids are part of the hashed content"


def test_a_changed_event_breaks_the_chain(stores: Stores) -> None:
    for kind in ("a.one", "a.two", "a.three"):
        stores.audit.append(kind, actor="s", details={"n": 1})
    if isinstance(stores.audit, InMemoryAuditLog):
        events = stores.audit._events
        events[1] = events[1].model_copy(update={"details": {"n": 2}})
    else:
        tamper(stores, "UPDATE audit_events SET details = '{\"n\": 2}' WHERE seq = 2")
    report = stores.audit.verify_chain()
    assert not report.ok and report.first_bad_seq == 2 and report.reason == "altered event"


def test_a_removed_event_is_detected(stores: Stores) -> None:
    for kind in ("a.one", "a.two", "a.three"):
        stores.audit.append(kind, actor="s")
    if isinstance(stores.audit, InMemoryAuditLog):
        del stores.audit._events[1]
    else:
        tamper(stores, "DELETE FROM audit_events WHERE seq = 2")
    report = stores.audit.verify_chain()
    assert not report.ok and report.first_bad_seq == 2 and report.reason == "gap"


def test_removing_the_last_event_is_detected_by_the_stored_head(stores: Stores) -> None:
    for kind in ("a.one", "a.two"):
        stores.audit.append(kind, actor="s")
    if isinstance(stores.audit, InMemoryAuditLog):
        stores.audit._events.pop()
    else:
        tamper(stores, "DELETE FROM audit_events WHERE seq = 2")
    report = stores.audit.verify_chain()
    assert not report.ok and report.reason == "head mismatch"


def tamper(stores: Stores, statement: str) -> None:
    """Change the log as a superuser who switches the append-only trigger off, then back on.
    The application role and the triggers make this impossible in normal operation."""
    assert stores.dsn is not None
    with psycopg.connect(stores.dsn, autocommit=True) as conn:
        conn.execute("ALTER TABLE audit_events DISABLE TRIGGER USER")
        try:
            conn.execute(statement.encode())
        finally:
            conn.execute("ALTER TABLE audit_events ENABLE TRIGGER USER")
