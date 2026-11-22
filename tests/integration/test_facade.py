"""ADR-0034: the async facade, its settings, and the rule that graph code uses only the facade."""

import asyncio
import threading
import time
from collections.abc import AsyncIterator, Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from opentelemetry.sdk.trace import TracerProvider
from pydantic import ValidationError

from orchestrator.contracts import AgentSpecification, AgentStatus, Usage
from orchestrator.governance.budget import BudgetExceeded
from orchestrator.governance.import_rules import find_store_imports, find_store_imports_in_package
from orchestrator.governance.recruiter import AgentRecord, InMemoryAgentRegistry
from orchestrator.persistence.facade import AsyncStores, StoreExecutor
from orchestrator.persistence.migrate import apply_migrations
from orchestrator.settings import POOL_VARIABLE, THREADS_VARIABLE, StoreSettings
from tests.integration.conftest import APP_ROLE
from tests.support import make_recruiter, make_request

GRAPH_PACKAGE = Path(__file__).resolve().parents[2] / "src" / "orchestrator" / "graph"
D = Decimal

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def memory() -> AsyncIterator[AsyncStores]:
    stores = AsyncStores.in_memory(StoreSettings(threads=4))
    yield stores
    stores.close()


# ---------------------------------------------------------------- settings
def test_threads_and_pool_size_are_configuration() -> None:
    assert StoreSettings().threads == 8 and StoreSettings().effective_pool_size == 8
    settings = StoreSettings.from_env({THREADS_VARIABLE: "5", POOL_VARIABLE: "9"})
    assert (settings.threads, settings.effective_pool_size) == (5, 9)
    assert StoreSettings.from_env({THREADS_VARIABLE: "3"}).effective_pool_size == 3
    assert StoreSettings.from_env({}) == StoreSettings()


def test_a_pool_smaller_than_the_thread_count_is_refused() -> None:
    with pytest.raises(ValidationError, match="at least as many connections"):
        StoreSettings(threads=8, pool_size=4)
    with pytest.raises(ValidationError):
        StoreSettings(threads=0)
    with pytest.raises(ValueError):
        StoreSettings.from_env({THREADS_VARIABLE: "many"})


# ---------------------------------------------------------------- the executor
async def test_blocking_store_calls_do_not_stall_the_event_loop() -> None:
    executor = StoreExecutor(2)
    ticks: list[float] = []

    async def heartbeat() -> None:
        for _ in range(8):
            ticks.append(time.monotonic())
            await asyncio.sleep(0.02)

    try:
        started = time.monotonic()
        await asyncio.gather(executor.call(time.sleep, 0.3), heartbeat())
        gaps = [b - a for a, b in zip(ticks, ticks[1:], strict=False)]
        assert max(gaps) < 0.15, "the loop kept running while the call blocked a worker thread"
        assert time.monotonic() - started >= 0.3
    finally:
        executor.close()


async def test_calls_run_on_the_configured_number_of_threads() -> None:
    executor = StoreExecutor(3)
    names: set[str] = set()
    gate = threading.Barrier(3, timeout=5)

    def work() -> None:
        gate.wait()  # only passes if three calls really run at once
        names.add(threading.current_thread().name)

    try:
        await asyncio.gather(*(executor.call(work) for _ in range(3)))
        assert len(names) == 3 and all(n.startswith("store") for n in names)
    finally:
        executor.close()


async def test_the_callers_trace_context_reaches_the_worker_thread(memory: AsyncStores) -> None:
    tracer = TracerProvider().get_tracer("facade-test")
    with tracer.start_as_current_span("node") as span:
        event = await memory.audit.append("tool.called", actor="system:test")
        context = span.get_span_context()
    assert event.trace_id == format(context.trace_id, "032x")
    assert event.span_id == format(context.span_id, "016x")
    assert (await memory.audit.append("tool.called", actor="system:test")).trace_id is None


async def test_an_error_in_a_store_call_reaches_the_caller(memory: AsyncStores) -> None:
    await memory.ledger.open_scope("prj_1", D("1"), changed_by="system:test")
    with pytest.raises(BudgetExceeded):
        await memory.ledger.reserve("r", ["prj_1"], D("2"))
    with pytest.raises(KeyError):
        await memory.registry.get("agt_unknown")


# ---------------------------------------------------------------- every store through the facade
async def test_every_store_works_through_the_in_memory_facade(memory: AsyncStores) -> None:
    await memory.ledger.open_scope("prj_ab12", D("5"), changed_by="system:test")
    await memory.ledger.reserve("r1", ["prj_ab12"], D("2"))
    await memory.ledger.settle("r1", Usage(cost=D("1")))
    assert (await memory.ledger.snapshot("prj_ab12")).committed == D("1")
    assert (await memory.ledger.reservation("r1")).state == "settled"

    assert await memory.counters.increment("agt_1", "web_search") == 1
    assert await memory.counters.count("agt_1", "web_search") == 1

    events = await memory.audit.events(project_id="prj_ab12")
    assert [e.kind for e in events] == ["budget.scope_opened"]
    assert (await memory.audit.verify_chain()).ok


@pytest.fixture
def postgres_stores(pg_dsn: str) -> Iterator[AsyncStores]:
    apply_migrations(pg_dsn)
    stores = AsyncStores.open(pg_dsn, StoreSettings(threads=4), role=APP_ROLE)
    yield stores
    stores.close()


@pytest.mark.postgres
async def test_the_postgres_facade_runs_calls_in_parallel_on_a_pool_sized_to_the_threads(
    postgres_stores: AsyncStores,
) -> None:
    stores = postgres_stores
    assert stores.settings.effective_pool_size == 4
    await stores.ledger.open_scope("prj_1", D("100"), changed_by="system:test")
    await asyncio.gather(*(stores.ledger.reserve(f"r{i}", ["prj_1"], D("1")) for i in range(40)))
    assert (await stores.ledger.snapshot("prj_1")).reserved == D("40")
    counts = await asyncio.gather(*(stores.counters.increment("agt", "t") for _ in range(20)))
    assert sorted(counts) == list(range(1, 21))


@pytest.mark.postgres
async def test_the_registry_works_behind_the_postgres_facade(
    postgres_stores: AsyncStores,
) -> None:
    recruiter, _, _ = make_recruiter(InMemoryAgentRegistry())
    spec = recruiter.provision(make_request())
    assert isinstance(spec, AgentSpecification)
    record = AgentRecord(spec=spec, status=AgentStatus.VALIDATED, request_hash="h")
    await postgres_stores.registry.add(record)
    await postgres_stores.registry.transition(spec.agent_id, AgentStatus.APPROVED)
    stored = await postgres_stores.registry.get(spec.agent_id)
    assert stored.status is AgentStatus.APPROVED
    assert [r.spec.agent_id for r in await postgres_stores.registry.for_project("prj_ab12")] == [
        spec.agent_id
    ]


# ---------------------------------------------------------------- the import rule
def test_graph_modules_do_not_import_a_synchronous_store() -> None:
    """Every module under orchestrator/graph: the worker, middleware, state, and later the
    Lead subgraph and supervisor."""
    assert GRAPH_PACKAGE.is_dir()
    assert find_store_imports_in_package(GRAPH_PACKAGE) == []


OFFENDERS = [
    "from orchestrator.persistence.repositories import PostgresLedger\n",
    "import orchestrator.persistence.repositories\n",
    "from orchestrator.persistence import repositories\n",
    "from orchestrator.persistence.repositories import *\n",
    "from orchestrator.governance.budget import InMemoryLedger\n",
    "from orchestrator.governance.budget import BudgetLedger\n",
    "from orchestrator.persistence.audit import AuditLog, AuditEvent\n",
    "from orchestrator.persistence.evidence import InMemoryEvidenceStore\n",
    "from orchestrator.persistence.db import open_pool\n",
    "import psycopg\n",
    "from psycopg_pool import ConnectionPool\n",
    "from ..persistence.repositories import PostgresAuditLog\n",
    "def late():\n    from orchestrator.persistence.repositories import PostgresLedger\n",
    "from orchestrator.persistence.facade import StoreExecutor\n",
]


@pytest.mark.parametrize("source", OFFENDERS)
def test_the_import_rule_catches_each_way_of_reaching_a_store(tmp_path: Path, source: str) -> None:
    module = tmp_path / "offender.py"
    module.write_text(source, encoding="utf-8")
    assert find_store_imports(module), f"not caught: {source!r}"


@pytest.mark.parametrize(
    "source",
    [
        "from orchestrator.persistence.facade import AsyncStores\n",
        "from orchestrator.persistence.audit import AuditEvent\n",
        "from orchestrator.contracts import AgentSpecification, Evidence\n",
        "from orchestrator.governance.budget import BudgetExceeded, ReservationRecord\n",
        "import asyncio\n",
    ],
)
def test_the_import_rule_allows_the_facade_and_plain_data_models(
    tmp_path: Path, source: str
) -> None:
    module = tmp_path / "fine.py"
    module.write_text(source, encoding="utf-8")
    assert find_store_imports(module) == []
