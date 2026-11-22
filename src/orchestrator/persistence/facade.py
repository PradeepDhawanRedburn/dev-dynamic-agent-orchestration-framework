"""The async facade over the synchronous stores (ADR-0034 points 1 to 3).

Graph nodes, the tool gateway and middleware reach the stores through this module only. It owns
the hand-off to a fixed pool of worker threads, so a blocking database call never stalls the event
loop and no call site has to remember to move it off the loop. A test fails if a module under
`orchestrator.graph` imports a synchronous store directly.

The caller's context travels with each call, so an audit event written on a worker thread still
records the OpenTelemetry trace and span that were current in the node."""

import asyncio
import contextvars
import functools
from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

from pydantic import JsonValue

from orchestrator.contracts import (
    AgentStatus,
    Evidence,
    RetirementRecord,
    Usage,
)
from orchestrator.governance.approvals import (
    DecisionRecord,
    DecisionRegister,
    InMemoryDecisionRegister,
)
from orchestrator.governance.budget import (
    BudgetLedger,
    BudgetSnapshot,
    InMemoryLedger,
    ReservationRecord,
)
from orchestrator.governance.recruiter import AgentRecord, AgentRegistry, InMemoryAgentRegistry
from orchestrator.persistence.audit import (
    AuditEvent,
    AuditLog,
    ChainReport,
    InMemoryAuditLog,
)
from orchestrator.persistence.counters import InMemoryToolCallCounters, ToolCallCounters
from orchestrator.persistence.db import Pool, open_pool
from orchestrator.persistence.evidence import EvidenceStore, InMemoryEvidenceStore
from orchestrator.persistence.repositories import (
    PostgresAgentRegistry,
    PostgresAuditLog,
    PostgresDecisionRegister,
    PostgresEvidenceStore,
    PostgresLedger,
    PostgresToolCallCounters,
)
from orchestrator.settings import StoreSettings


class StoreExecutor:
    """Runs blocking store calls on a fixed number of threads."""

    def __init__(self, threads: int) -> None:
        self._pool = ThreadPoolExecutor(max_workers=threads, thread_name_prefix="store")
        self.threads = threads

    async def call[**P, R](self, fn: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
        context = contextvars.copy_context()
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._pool, context.run, functools.partial(fn, *args, **kwargs)
        )

    def close(self) -> None:
        self._pool.shutdown(wait=True)


class AsyncLedger:
    def __init__(self, ledger: BudgetLedger, run: StoreExecutor) -> None:
        self._ledger, self._run = ledger, run

    async def open_scope(self, scope: str, limit: Decimal, *, changed_by: str) -> None:
        await self._run.call(self._ledger.open_scope, scope, limit, changed_by=changed_by)

    async def reserve(self, reservation_id: str, chain: list[str], amount: Decimal) -> None:
        await self._run.call(self._ledger.reserve, reservation_id, chain, amount)

    async def settle(self, reservation_id: str, usage: Usage) -> None:
        await self._run.call(self._ledger.settle, reservation_id, usage)

    async def release(self, reservation_id: str) -> None:
        await self._run.call(self._ledger.release, reservation_id)

    async def reservation(self, reservation_id: str) -> ReservationRecord:
        return await self._run.call(self._ledger.reservation, reservation_id)

    async def snapshot(self, scope: str) -> BudgetSnapshot:
        return await self._run.call(self._ledger.snapshot, scope)


class AsyncRegistry:
    def __init__(self, registry: AgentRegistry, run: StoreExecutor) -> None:
        self._registry, self._run = registry, run

    async def add(self, record: AgentRecord) -> None:
        await self._run.call(self._registry.add, record)

    async def get(self, agent_id: str) -> AgentRecord:
        return await self._run.call(self._registry.get, agent_id)

    async def for_project(self, project_id: str) -> list[AgentRecord]:
        return await self._run.call(self._registry.for_project, project_id)

    async def transition(self, agent_id: str, new: AgentStatus) -> None:
        await self._run.call(self._registry.transition, agent_id, new)

    async def set_retirement(self, agent_id: str, retirement: RetirementRecord) -> None:
        await self._run.call(self._registry.set_retirement, agent_id, retirement)


class AsyncEvidence:
    def __init__(self, evidence: EvidenceStore, run: StoreExecutor) -> None:
        self._evidence, self._run = evidence, run

    async def put(self, evidence: Evidence) -> None:
        await self._run.call(self._evidence.put, evidence)

    async def get(self, evidence_id: str) -> Evidence:
        return await self._run.call(self._evidence.get, evidence_id)

    async def for_agent(self, project_id: str, agent_id: str) -> list[Evidence]:
        return await self._run.call(self._evidence.for_agent, project_id, agent_id)

    async def not_issued_to(
        self, project_id: str, agent_id: str, evidence_ids: Iterable[str]
    ) -> set[str]:
        return await self._run.call(
            self._evidence.not_issued_to, project_id, agent_id, list(evidence_ids)
        )


class AsyncAudit:
    def __init__(self, audit: AuditLog, run: StoreExecutor) -> None:
        self._audit, self._run = audit, run

    async def append(
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
        return await self._run.call(
            self._audit.append,
            kind,
            actor=actor,
            project_id=project_id,
            workstream_id=workstream_id,
            task_id=task_id,
            agent_id=agent_id,
            correlation_id=correlation_id,
            details=details,
            event_id=event_id,
        )

    async def events(
        self, *, project_id: str | None = None, agent_id: str | None = None, kind: str | None = None
    ) -> list[AuditEvent]:
        return await self._run.call(
            self._audit.events, project_id=project_id, agent_id=agent_id, kind=kind
        )

    async def verify_chain(self) -> ChainReport:
        return await self._run.call(self._audit.verify_chain)


class AsyncDecisions:
    def __init__(self, decisions: DecisionRegister, run: StoreExecutor) -> None:
        self._decisions, self._run = decisions, run

    async def record(self, decision: DecisionRecord) -> DecisionRecord:
        return await self._run.call(self._decisions.record, decision)

    async def get(self, decision_id: str) -> DecisionRecord:
        return await self._run.call(self._decisions.get, decision_id)

    async def for_project(self, project_id: str) -> list[DecisionRecord]:
        return await self._run.call(self._decisions.for_project, project_id)

    async def add_followup(self, decision_id: str, audit_event_id: str) -> None:
        await self._run.call(self._decisions.add_followup, decision_id, audit_event_id)

    async def followups(self, decision_id: str) -> list[str]:
        return await self._run.call(self._decisions.followups, decision_id)


class AsyncCounters:
    def __init__(self, counters: ToolCallCounters, run: StoreExecutor) -> None:
        self._counters, self._run = counters, run

    async def increment(self, agent_id: str, tool_name: str) -> int:
        return await self._run.call(self._counters.increment, agent_id, tool_name)

    async def count(self, agent_id: str, tool_name: str) -> int:
        return await self._run.call(self._counters.count, agent_id, tool_name)


class AsyncStores:
    """Every store, async. Build one with `open` (PostgreSQL) or `in_memory` (tests), and `close`
    it when done."""

    def __init__(
        self,
        *,
        ledger: BudgetLedger,
        registry: AgentRegistry,
        evidence: EvidenceStore,
        audit: AuditLog,
        decisions: DecisionRegister,
        counters: ToolCallCounters,
        settings: StoreSettings,
        pool: Pool | None = None,
    ) -> None:
        self._executor = StoreExecutor(settings.threads)
        self._pool = pool
        self.settings = settings
        self.ledger = AsyncLedger(ledger, self._executor)
        self.registry = AsyncRegistry(registry, self._executor)
        self.evidence = AsyncEvidence(evidence, self._executor)
        self.audit = AsyncAudit(audit, self._executor)
        self.decisions = AsyncDecisions(decisions, self._executor)
        self.counters = AsyncCounters(counters, self._executor)

    @classmethod
    def open(
        cls, dsn: str, settings: StoreSettings | None = None, *, role: str | None = None
    ) -> "AsyncStores":
        """PostgreSQL stores on one pool sized to the worker threads (ADR-0034 point 3)."""
        settings = settings or StoreSettings.from_env()
        pool = open_pool(dsn, min_size=1, max_size=settings.effective_pool_size, role=role)
        return cls(
            ledger=PostgresLedger(pool),
            registry=PostgresAgentRegistry(pool),
            evidence=PostgresEvidenceStore(pool),
            audit=PostgresAuditLog(pool),
            decisions=PostgresDecisionRegister(pool),
            counters=PostgresToolCallCounters(pool),
            settings=settings,
            pool=pool,
        )

    @classmethod
    def in_memory(cls, settings: StoreSettings | None = None) -> "AsyncStores":
        audit = InMemoryAuditLog()
        return cls(
            ledger=InMemoryLedger(audit=audit),
            registry=InMemoryAgentRegistry(),
            evidence=InMemoryEvidenceStore(),
            audit=audit,
            decisions=InMemoryDecisionRegister(),
            counters=InMemoryToolCallCounters(),
            settings=settings or StoreSettings(),
        )

    def close(self) -> None:
        self._executor.close()
        if self._pool is not None:
            self._pool.close()
