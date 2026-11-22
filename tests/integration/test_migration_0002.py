"""Migration 0002 (ADR-0034 points 11 to 13) and the shared tool-call counters."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import psycopg
import pytest
from psycopg import errors

from orchestrator.contracts import AgentSpecification, AgentStatus
from orchestrator.persistence.db import Pool, open_pool
from orchestrator.persistence.migrate import apply_migrations, migration_files
from orchestrator.persistence.repositories import PostgresAgentRegistry, PostgresLedger
from tests.integration.conftest import APP_ROLE, Stores
from tests.integration.test_postgres_guarantees import as_app
from tests.support import make_recruiter, make_request

D = Decimal


@pytest.fixture
def migrated(pg_dsn: str) -> str:
    apply_migrations(pg_dsn)
    return pg_dsn


@pytest.fixture
def app_pool(migrated: str) -> Iterator[Pool]:
    pool = open_pool(migrated, role=APP_ROLE, max_size=16)
    yield pool
    pool.close()


def test_the_second_migration_is_a_separate_file(pg_dsn: str) -> None:
    names = [version for version, _ in migration_files()]
    assert names[:2] == ["0001_governance_core", "0002_review_corrections"]
    assert apply_migrations(pg_dsn) == names


@pytest.mark.postgres
def test_the_application_role_cannot_delete_a_reservation(migrated: str, app_pool: Pool) -> None:
    ledger = PostgresLedger(app_pool)
    ledger.open_scope("prj_1", D("5"), changed_by="system:test")
    ledger.reserve("r1", ["prj_1"], D("2"))
    ledger.release("r1")
    with as_app(migrated) as conn:
        with pytest.raises(errors.InsufficientPrivilege):
            conn.execute(b"DELETE FROM budget_reservations")
        with pytest.raises(errors.InsufficientPrivilege):
            conn.execute(b"TRUNCATE budget_reservations")
    assert ledger.reservation("r1").state == "released"


@pytest.mark.postgres
def test_even_the_owner_cannot_delete_or_rewrite_a_closed_reservation(
    migrated: str, app_pool: Pool
) -> None:
    ledger = PostgresLedger(app_pool)
    ledger.open_scope("prj_1", D("5"), changed_by="system:test")
    ledger.reserve("done", ["prj_1"], D("2"))
    ledger.release("done")
    ledger.reserve("open", ["prj_1"], D("1"))
    with psycopg.connect(migrated, autocommit=True) as conn:
        with pytest.raises(errors.RestrictViolation, match="append-only"):
            conn.execute(b"DELETE FROM budget_reservations WHERE reservation_id = 'done'")
        with pytest.raises(errors.RestrictViolation, match="released reservation cannot change"):
            conn.execute(
                b"UPDATE budget_reservations SET state = 'reserved' WHERE reservation_id = 'done'"
            )
        with pytest.raises(errors.RestrictViolation, match="cannot change"):
            conn.execute(
                b"UPDATE budget_reservations SET amount = 99 WHERE reservation_id = 'open'"
            )
        with pytest.raises(errors.CheckViolation):
            conn.execute(
                b"UPDATE budget_reservations SET state = 'released' WHERE reservation_id = 'open'"
            )


@pytest.mark.postgres
def test_agent_transitions_are_append_only(migrated: str, app_pool: Pool) -> None:
    registry = PostgresAgentRegistry(app_pool)
    recruiter, _, _ = make_recruiter(registry)
    spec = recruiter.provision(make_request())
    assert isinstance(spec, AgentSpecification)
    registry.transition(spec.agent_id, AgentStatus.ASSIGNED)
    with as_app(migrated) as conn:
        for statement in (
            b"UPDATE agent_transitions SET status = 'accepted'",
            b"DELETE FROM agent_transitions",
            b"TRUNCATE agent_transitions",
        ):
            with pytest.raises(errors.InsufficientPrivilege):
                conn.execute(statement)
    with psycopg.connect(migrated, autocommit=True) as conn:
        for statement in (
            b"UPDATE agent_transitions SET status = 'accepted'",
            b"DELETE FROM agent_transitions",
        ):
            with pytest.raises(errors.RestrictViolation, match="append-only"):
                conn.execute(statement)
    history = [s for s, _ in registry.get(spec.agent_id).history]
    assert history[-1] is AgentStatus.ASSIGNED and len(history) == 4


@pytest.mark.postgres
def test_an_agents_specification_and_request_hash_cannot_be_updated(
    migrated: str, app_pool: Pool
) -> None:
    registry = PostgresAgentRegistry(app_pool)
    recruiter, _, _ = make_recruiter(registry)
    spec = recruiter.provision(make_request())
    assert isinstance(spec, AgentSpecification)
    before = registry.get(spec.agent_id)
    for connection in (as_app(migrated), psycopg.connect(migrated, autocommit=True)):
        with connection as conn:
            for statement in (
                b"UPDATE agent_records SET spec = jsonb_set(spec, '{role_title}', '\"x\"')",
                b"UPDATE agent_records SET request_hash = 'forged'",
                b"UPDATE agent_records SET project_id = 'prj_other'",
            ):
                with pytest.raises(errors.RestrictViolation, match="cannot be changed"):
                    conn.execute(statement)
    with psycopg.connect(migrated, autocommit=True) as conn:
        with pytest.raises(errors.RestrictViolation, match="append-only"):
            conn.execute(b"DELETE FROM agent_records")
    assert registry.get(spec.agent_id) == before


@pytest.mark.postgres
def test_status_and_retirement_can_still_change(migrated: str, app_pool: Pool) -> None:
    registry = PostgresAgentRegistry(app_pool)
    recruiter, _, _ = make_recruiter(registry)
    spec = recruiter.provision(make_request())
    assert isinstance(spec, AgentSpecification)
    for status in (AgentStatus.ASSIGNED, AgentStatus.RUNNING, AgentStatus.AWAITING_REVIEW):
        registry.transition(spec.agent_id, status)
    retirement = recruiter.retire(spec.agent_id, final_status=AgentStatus.CANCELLED, reason="x")
    assert registry.get(spec.agent_id).retirement == retirement


# ---------------------------------------------------------------- tool-call counters
def test_a_counter_counts_per_agent_and_tool_and_returns_the_new_value(stores: Stores) -> None:
    assert stores.counters.count("agt_1", "web_search") == 0
    assert [stores.counters.increment("agt_1", "web_search") for _ in range(3)] == [1, 2, 3]
    assert stores.counters.increment("agt_1", "other_tool") == 1
    assert stores.counters.increment("agt_2", "web_search") == 1
    assert stores.counters.count("agt_1", "web_search") == 3


def test_concurrent_increments_never_lose_a_count(stores: Stores) -> None:
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda _: stores.counters.increment("agt_1", "t"), range(64)))
    assert sorted(results) == list(range(1, 65))
    assert stores.counters.count("agt_1", "t") == 64
