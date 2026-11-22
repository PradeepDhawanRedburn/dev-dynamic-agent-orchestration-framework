"""The audit log: append-only and hash-chained (ADR-0003).

Specified in docs/governance/traceability-and-decisions.md. Every event carries the hash of the
event before it, so removing or changing any event breaks the chain from that point on. The
PostgreSQL log (persistence/repositories.py) also refuses UPDATE and DELETE; this module holds the
event model, the hash and the in-memory log used in tests."""

import hashlib
import json
import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Protocol

from pydantic import Field, JsonValue

from orchestrator.contracts import Contract, new_id, utcnow
from orchestrator.observability.tracing import current_trace_ids

GENESIS_HASH = "0" * 64
KIND_PATTERN = r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$"


class AuditEvent(Contract):
    seq: int = Field(ge=1)
    event_id: str
    occurred_at: datetime
    kind: str = Field(pattern=KIND_PATTERN, description="For example tool.denied")
    actor: str = Field(min_length=1, description="A person's principal id, or system:<component>")
    project_id: str | None = None
    workstream_id: str | None = None
    task_id: str | None = None
    agent_id: str | None = None
    correlation_id: str | None = None
    details: dict[str, JsonValue] = {}
    trace_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    span_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{16}$")
    prev_hash: str
    hash: str


class ChainReport(Contract):
    ok: bool
    checked: int
    first_bad_seq: int | None = None
    reason: str = ""


def event_hash(event: AuditEvent) -> str:
    """Hash of every field except `hash` itself, chained to the previous event's hash."""
    body = event.model_dump(mode="json", exclude={"hash", "occurred_at"})
    body["occurred_at"] = event.occurred_at.astimezone(UTC).isoformat(timespec="microseconds")
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def seal(event: AuditEvent) -> AuditEvent:
    return event.model_copy(update={"hash": event_hash(event)})


def check_chain(events: list[AuditEvent], head: tuple[int, str] | None = None) -> ChainReport:
    """Verify sequence, links and hashes. `head` is the stored (last seq, last hash), if any."""
    previous_hash, expected_seq = GENESIS_HASH, 1
    for event in events:
        if event.seq != expected_seq:
            return ChainReport(
                ok=False, checked=expected_seq - 1, first_bad_seq=expected_seq, reason="gap"
            )
        if event.prev_hash != previous_hash:
            return ChainReport(
                ok=False, checked=expected_seq - 1, first_bad_seq=event.seq, reason="broken link"
            )
        if event.hash != event_hash(event):
            return ChainReport(
                ok=False, checked=expected_seq - 1, first_bad_seq=event.seq, reason="altered event"
            )
        previous_hash, expected_seq = event.hash, expected_seq + 1
    if head is not None and head != (expected_seq - 1, previous_hash):
        return ChainReport(
            ok=False, checked=len(events), first_bad_seq=expected_seq, reason="head mismatch"
        )
    return ChainReport(ok=True, checked=len(events))


class AuditLog(Protocol):
    def append(
        self,
        kind: str,
        *,
        actor: str,
        project_id: str | None = None,
        workstream_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        correlation_id: str | None = None,
        details: Mapping[str, JsonValue] | None = None,
        event_id: str | None = None,
    ) -> AuditEvent:
        """Add an event. A caller that may be retried passes a stable `event_id`: appending the
        same id again returns the stored event instead of writing a second one."""
        ...

    def events(
        self, *, project_id: str | None = None, agent_id: str | None = None, kind: str | None = None
    ) -> list[AuditEvent]: ...

    def verify_chain(self) -> ChainReport: ...


class InMemoryAuditLog:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []
        self._by_id: dict[str, AuditEvent] = {}
        self._head: tuple[int, str] = (0, GENESIS_HASH)
        self._lock = threading.Lock()

    def append(
        self,
        kind: str,
        *,
        actor: str,
        project_id: str | None = None,
        workstream_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        correlation_id: str | None = None,
        details: Mapping[str, JsonValue] | None = None,
        event_id: str | None = None,
    ) -> AuditEvent:
        with self._lock:
            if event_id is not None and event_id in self._by_id:
                return self._by_id[event_id]
            trace_id, span_id = current_trace_ids()
            event = seal(
                AuditEvent(
                    seq=self._head[0] + 1,
                    event_id=event_id or new_id("aud"),
                    occurred_at=utcnow(),
                    kind=kind,
                    actor=actor,
                    project_id=project_id,
                    workstream_id=workstream_id,
                    task_id=task_id,
                    agent_id=agent_id,
                    correlation_id=correlation_id,
                    details=dict(details or {}),
                    trace_id=trace_id,
                    span_id=span_id,
                    prev_hash=self._head[1],
                    hash="",
                )
            )
            self._events.append(event)
            self._by_id[event.event_id] = event
            self._head = (event.seq, event.hash)  # kept apart from the events, as in PostgreSQL
            return event

    def events(
        self, *, project_id: str | None = None, agent_id: str | None = None, kind: str | None = None
    ) -> list[AuditEvent]:
        return [
            e
            for e in self._events
            if (project_id is None or e.project_id == project_id)
            and (agent_id is None or e.agent_id == agent_id)
            and (kind is None or e.kind == kind)
        ]

    def verify_chain(self) -> ChainReport:
        with self._lock:
            return check_chain(list(self._events), self._head)
