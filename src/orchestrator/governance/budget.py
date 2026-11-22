"""Budget ledger with reservations (ADR-0005). `BudgetLedger` is the interface; the in-memory
version below is for tests and the PostgreSQL version (persistence/repositories.py) is the real
one, using row locks so concurrent reservations never overspend a scope."""

from __future__ import annotations

import threading
from decimal import Decimal
from typing import Literal, Protocol

from orchestrator.contracts import Contract, Usage


class BudgetExceeded(Exception):
    def __init__(self, scope: str, limit: Decimal, attempted: Decimal) -> None:
        super().__init__(f"{scope}: {attempted} exceeds {limit}")
        self.scope, self.limit, self.attempted = scope, limit, attempted


class BudgetSnapshot(Contract):
    scope: str
    limit: Decimal
    committed: Decimal
    reserved: Decimal
    state: Literal["ok", "warning", "exhausted"]

    @property
    def available(self) -> Decimal:
        return self.limit - self.committed - self.reserved


class BudgetLedger(Protocol):
    """Every method is safe to repeat: a graph node that is retried calls them again."""

    def open_scope(self, scope: str, limit: Decimal) -> None: ...
    def reserve(self, reservation_id: str, chain: list[str], amount: Decimal) -> None: ...
    def settle(self, reservation_id: str, usage: Usage) -> None: ...
    def release(self, reservation_id: str) -> None: ...
    def snapshot(self, scope: str) -> BudgetSnapshot: ...


class InMemoryLedger:
    """Scopes form a chain, e.g. ['prj_1', 'prj_1/ws_2']. A reservation must fit
    every scope in the chain, so a task cannot overspend its workstream or project."""

    def __init__(self, warn_fraction: Decimal = Decimal("0.8")) -> None:
        self._limits: dict[str, Decimal] = {}
        self._committed: dict[str, Decimal] = {}
        self._reservations: dict[str, tuple[list[str], Decimal]] = {}
        self._settled: set[str] = set()
        self._lock = threading.Lock()
        self._warn = warn_fraction

    def open_scope(self, scope: str, limit: Decimal) -> None:
        self._limits[scope] = limit
        self._committed.setdefault(scope, Decimal(0))

    def _reserved(self, scope: str) -> Decimal:
        return sum(
            (amt for chain, amt in self._reservations.values() if scope in chain), Decimal(0)
        )

    def reserve(self, reservation_id: str, chain: list[str], amount: Decimal) -> None:
        with self._lock:
            if reservation_id in self._reservations or reservation_id in self._settled:
                return  # idempotent on retry
            for scope in chain:
                used = self._committed[scope] + self._reserved(scope) + amount
                if used > self._limits[scope]:
                    raise BudgetExceeded(scope, self._limits[scope], used)
            self._reservations[reservation_id] = (chain, amount)

    def settle(self, reservation_id: str, usage: Usage) -> None:
        """Replace the reservation with actual cost. Safe to call twice."""
        with self._lock:
            if reservation_id in self._settled:
                return
            chain, _ = self._reservations.pop(reservation_id)
            for scope in chain:
                self._committed[scope] += usage.cost
            self._settled.add(reservation_id)

    def release(self, reservation_id: str) -> None:
        with self._lock:
            self._reservations.pop(reservation_id, None)

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
