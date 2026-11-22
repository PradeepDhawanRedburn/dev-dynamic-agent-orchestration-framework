"""Budget ledger with reservations (ADR-0005, ADR-0034). `BudgetLedger` is the interface; the
in-memory version below is for tests and the PostgreSQL version (persistence/repositories.py) is
the real one, using row locks so concurrent reservations never overspend a scope.

The ledger is a financial record. A reservation is never deleted: it is `reserved`, then either
`settled` with the actual cost or `released`, and stays readable afterwards. A change to a scope's
limit is written to the audit log with the name of whoever made it."""

from __future__ import annotations

import threading
from decimal import Decimal
from typing import Literal, Protocol

from pydantic import JsonValue

from orchestrator.contracts import Contract, Usage
from orchestrator.persistence.audit import AuditLog, InMemoryAuditLog


class BudgetExceeded(Exception):
    def __init__(self, scope: str, limit: Decimal, attempted: Decimal) -> None:
        super().__init__(f"{scope}: {attempted} exceeds {limit}")
        self.scope, self.limit, self.attempted = scope, limit, attempted


class ReservationClosed(Exception):
    """The reservation was released, so it can no longer be settled."""


class BudgetSnapshot(Contract):
    scope: str
    limit: Decimal
    committed: Decimal
    reserved: Decimal
    state: Literal["ok", "warning", "exhausted"]

    @property
    def available(self) -> Decimal:
        return self.limit - self.committed - self.reserved


class ReservationRecord(Contract):
    reservation_id: str
    chain: list[str]
    amount: Decimal
    state: Literal["reserved", "settled", "released"]
    settled_amount: Decimal | None = None


class BudgetLedger(Protocol):
    """Every method is safe to repeat: a graph node that is retried calls them again."""

    def open_scope(self, scope: str, limit: Decimal, *, changed_by: str) -> None:
        """Create a scope or change its limit. Whoever does it is named in the audit log; setting
        the limit it already has changes and records nothing."""
        ...

    def reserve(self, reservation_id: str, chain: list[str], amount: Decimal) -> None: ...
    def settle(self, reservation_id: str, usage: Usage) -> None: ...
    def release(self, reservation_id: str) -> None: ...
    def reservation(self, reservation_id: str) -> ReservationRecord: ...
    def snapshot(self, scope: str) -> BudgetSnapshot: ...


def scope_project(scope: str) -> str | None:
    """The project a scope belongs to: scopes are named prj_x or prj_x/ws_y."""
    head = scope.split("/", 1)[0]
    return head if head.startswith("prj_") else None


def limit_event(scope: str, old: Decimal | None, new: Decimal) -> tuple[str, dict[str, JsonValue]]:
    kind = "budget.scope_opened" if old is None else "budget.limit_changed"
    return kind, {
        "scope": scope,
        "old_limit": None if old is None else str(old),
        "new_limit": str(new),
    }


class InMemoryLedger:
    """Scopes form a chain, e.g. ['prj_1', 'prj_1/ws_2']. A reservation must fit
    every scope in the chain, so a task cannot overspend its workstream or project."""

    def __init__(
        self, warn_fraction: Decimal = Decimal("0.8"), audit: AuditLog | None = None
    ) -> None:
        self._limits: dict[str, Decimal] = {}
        self._committed: dict[str, Decimal] = {}
        self._records: dict[str, ReservationRecord] = {}
        self._lock = threading.Lock()
        self._warn = warn_fraction
        self.audit: AuditLog = audit if audit is not None else InMemoryAuditLog()

    def open_scope(self, scope: str, limit: Decimal, *, changed_by: str) -> None:
        with self._lock:
            old = self._limits.get(scope)
            if old == limit:
                return
            kind, details = limit_event(scope, old, limit)
            self.audit.append(
                kind, actor=changed_by, project_id=scope_project(scope), details=details
            )  # first: a refused audit event (no actor) must leave the limit unchanged
            self._limits[scope] = limit
            self._committed.setdefault(scope, Decimal(0))

    def _reserved(self, scope: str) -> Decimal:
        return sum(
            (
                r.amount
                for r in self._records.values()
                if r.state == "reserved" and scope in r.chain
            ),
            Decimal(0),
        )

    def reserve(self, reservation_id: str, chain: list[str], amount: Decimal) -> None:
        with self._lock:
            if reservation_id in self._records:
                return  # idempotent on retry, in any state
            for scope in chain:
                used = self._committed[scope] + self._reserved(scope) + amount
                if used > self._limits[scope]:
                    raise BudgetExceeded(scope, self._limits[scope], used)
            self._records[reservation_id] = ReservationRecord(
                reservation_id=reservation_id, chain=list(chain), amount=amount, state="reserved"
            )

    def settle(self, reservation_id: str, usage: Usage) -> None:
        """Replace the reservation with actual cost. Safe to call twice."""
        with self._lock:
            record = self._records.get(reservation_id)
            if record is None:
                raise KeyError(reservation_id)
            if record.state == "settled":
                return
            if record.state == "released":
                raise ReservationClosed(reservation_id)
            for scope in record.chain:
                self._committed[scope] += usage.cost
            self._records[reservation_id] = record.model_copy(
                update={"state": "settled", "settled_amount": usage.cost}
            )

    def release(self, reservation_id: str) -> None:
        with self._lock:
            record = self._records.get(reservation_id)
            if record is not None and record.state == "reserved":
                self._records[reservation_id] = record.model_copy(update={"state": "released"})

    def reservation(self, reservation_id: str) -> ReservationRecord:
        return self._records[reservation_id]

    def snapshot(self, scope: str) -> BudgetSnapshot:
        committed, reserved, limit = (
            self._committed[scope],
            self._reserved(scope),
            self._limits[scope],
        )
        used = committed + reserved
        state: Literal["ok", "warning", "exhausted"] = (
            "exhausted" if used >= limit else "warning" if used >= limit * self._warn else "ok"
        )
        return BudgetSnapshot(
            scope=scope, limit=limit, committed=committed, reserved=reserved, state=state
        )
