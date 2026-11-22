"""What only PostgreSQL gives: migrations, the application role's limits, append-only tables, and
reservations that stay safe under concurrency. Each test gets its own empty database."""

import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from decimal import Decimal

import psycopg
import pytest
from psycopg import errors

from orchestrator.contracts import Usage
from orchestrator.governance.approvals import TIMEOUT_RULE, DecisionCard, DecisionRecord
from orchestrator.governance.budget import BudgetExceeded
from orchestrator.persistence.db import Pool, open_pool
from orchestrator.persistence.migrate import apply_migrations, migration_files
from orchestrator.persistence.repositories import (
    PostgresAuditLog,
    PostgresDecisionRegister,
    PostgresLedger,
)
from tests.integration.conftest import APP_ROLE

pytestmark = pytest.mark.postgres

D = Decimal


@contextmanager
def as_app(dsn: str) -> Iterator[psycopg.Connection[tuple[object, ...]]]:
    """A connection running as the application role."""
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(f"SET ROLE {APP_ROLE}")
        yield conn


@pytest.fixture
def migrated(pg_dsn: str) -> str:
    apply_migrations(pg_dsn)
    return pg_dsn


@pytest.fixture
def app_pool(migrated: str) -> Iterator[Pool]:
    pool = open_pool(migrated, role=APP_ROLE, max_size=16)
    yield pool
    pool.close()


# ---------------------------------------------------------------- migrations
def test_migrations_apply_once_and_are_recorded(pg_dsn: str) -> None:
    versions = [version for version, _ in migration_files()]
    assert versions and versions == sorted(versions)
    assert apply_migrations(pg_dsn) == versions
    assert apply_migrations(pg_dsn) == [], "a second run has nothing to do"
    with psycopg.connect(pg_dsn) as conn:
        recorded = [r[0] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY 1")]
        tables = {
            r[0]
            for r in conn.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )
        }
    assert recorded == versions
    assert {
        "budget_scopes",
        "budget_reservations",
        "agent_records",
        "agent_transitions",
        "evidence",
        "audit_events",
        "audit_head",
        "decisions",
        "decision_followups",
    } <= tables


def test_two_runners_at_once_apply_each_migration_once(pg_dsn: str) -> None:
    barrier = threading.Barrier(2)

    def run() -> list[str]:
        barrier.wait()
        return apply_migrations(pg_dsn)

    with ThreadPoolExecutor(2) as pool:
        results = [f.result() for f in [pool.submit(run), pool.submit(run)]]
    assert sorted(len(r) for r in results) == [0, len(migration_files())]


# ---------------------------------------------------------------- the application role
APPEND_ONLY = ["audit_events", "decisions", "decision_followups", "evidence"]
CHANGEABLE_COLUMN = {
    "audit_events": "actor",
    "decisions": "comment",
    "decision_followups": "audit_event_id",
    "evidence": "title",
}


@pytest.mark.parametrize("table", APPEND_ONLY)
def test_the_application_role_cannot_update_delete_or_truncate_an_append_only_table(
    migrated: str, table: str
) -> None:
    column = CHANGEABLE_COLUMN[table]
    with as_app(migrated) as conn:
        for statement in (
            f"UPDATE {table} SET {column} = 'x'",
            f"DELETE FROM {table}",
            f"TRUNCATE {table}",
        ):
            with pytest.raises(errors.InsufficientPrivilege):
                conn.execute(statement.encode())


def test_an_audit_row_cannot_be_changed_or_removed_by_the_application_role(
    app_pool: Pool, migrated: str
) -> None:
    log = PostgresAuditLog(app_pool)
    event = log.append("request.received", actor="system:intake", project_id="prj_1")
    with as_app(migrated) as conn:
        assert conn.execute("SELECT count(*) FROM audit_events").fetchone() == (1,)
        with pytest.raises(errors.InsufficientPrivilege):
            conn.execute(b"UPDATE audit_events SET actor = 'someone-else'")
        with pytest.raises(errors.InsufficientPrivilege):
            conn.execute(b"DELETE FROM audit_events")
    assert log.events() == [event]
    assert log.verify_chain().ok


SEED = {
    "audit_events": (
        "INSERT INTO audit_events (seq, event_id, occurred_at, kind, actor, prev_hash, hash) "
        "VALUES (1, 'aud_1', now(), 'a.b', 's', 'p', 'h')"
    ),
    "decisions": (
        "INSERT INTO decisions (decision_id, project_id, decided_at, type, decided_by_kind, "
        "decided_by, decided_by_role, card, card_hash, outcome) VALUES ('dec_1', 'prj_1', now(), "
        "'approve_plan', 'human', 'oid', 'sponsor', '{}', 'h', 'approved')"
    ),
    "decision_followups": (
        "INSERT INTO decisions (decision_id, project_id, decided_at, type, decided_by_kind, "
        "decided_by, decided_by_role, card, card_hash, outcome) VALUES ('dec_1', 'prj_1', now(), "
        "'approve_plan', 'human', 'oid', 'sponsor', '{}', 'h', 'approved'); "
        "INSERT INTO decision_followups VALUES ('dec_1', 'aud_1')"
    ),
    "evidence": (
        "INSERT INTO evidence VALUES ('ev_1', 'prj_1', 'agt_1', 't', 'community', 'r', 't', 'e', "
        "'h', NULL, now(), 'internal', 0.5)"
    ),
}


@pytest.mark.parametrize("table", APPEND_ONLY)
def test_even_the_owner_is_stopped_by_the_trigger(migrated: str, table: str) -> None:
    column = CHANGEABLE_COLUMN[table]
    with psycopg.connect(migrated, autocommit=True) as conn:
        conn.execute(SEED[table].encode())
        for statement in (
            f"UPDATE {table} SET {column} = 'x'",
            f"DELETE FROM {table}",
            f"TRUNCATE {table} CASCADE",
        ):
            with pytest.raises(errors.RestrictViolation, match="append-only"):
                conn.execute(statement.encode())
        (count,) = conn.execute(f"SELECT count(*) FROM {table}".encode()).fetchone() or (0,)  # noqa: S608
        assert count == 1, "the row is still there"


def test_the_trigger_stops_an_update_by_the_owner_too(migrated: str, app_pool: Pool) -> None:
    PostgresAuditLog(app_pool).append("request.received", actor="s")
    with psycopg.connect(migrated, autocommit=True) as conn:
        with pytest.raises(errors.RestrictViolation, match="append-only"):
            conn.execute(b"UPDATE audit_events SET actor = 'x'")


def test_the_application_role_can_do_everything_normal_operation_needs(app_pool: Pool) -> None:
    ledger = PostgresLedger(app_pool)
    ledger.open_scope("s", D("5"))
    ledger.reserve("r", ["s"], D("2"))
    ledger.settle("r", Usage(cost=D("1")))
    ledger.reserve("r2", ["s"], D("1"))
    ledger.release("r2")
    assert ledger.snapshot("s").committed == D("1")


def test_the_application_role_cannot_create_or_drop_tables(migrated: str) -> None:
    with as_app(migrated) as conn:
        with pytest.raises(errors.InsufficientPrivilege):
            conn.execute(b"CREATE TABLE sneaky (x int)")
        with pytest.raises(errors.InsufficientPrivilege):
            conn.execute(b"DROP TABLE audit_events")


# ---------------------------------------------------------------- the database repeats the rules
def raw_decision(migrated: str, **over: object) -> None:
    columns: dict[str, object] = dict(
        decision_id="dec_raw",
        project_id="prj_ab12",
        decided_at="2026-11-21T12:00:00Z",
        type="approve_requirement",
        decided_by_kind="human",
        decided_by="oid",
        decided_by_role="sponsor",
        card="{}",
        card_hash="h",
        outcome="approved",
        comment="ok",
        default_taken=None,
    )
    columns.update(over)
    names = ", ".join(columns)
    marks = ", ".join(["%s"] * len(columns))
    with psycopg.connect(migrated, autocommit=True) as conn:
        conn.execute(
            f"INSERT INTO decisions ({names}) VALUES ({marks})".encode(), list(columns.values())
        )  # noqa: S608


def test_the_database_itself_refuses_a_timeout_that_is_not_a_rule_with_a_default(
    migrated: str,
) -> None:
    with pytest.raises(errors.CheckViolation):
        raw_decision(migrated, outcome="timeout", decided_by_kind="human", default_taken="x")
    with pytest.raises(errors.CheckViolation):
        raw_decision(
            migrated, outcome="timeout", decided_by_kind="rule", decided_by=TIMEOUT_RULE,
            decided_by_role=None, default_taken=None,
        )  # fmt: skip
    raw_decision(
        migrated, outcome="timeout", decided_by_kind="rule", decided_by=TIMEOUT_RULE,
        decided_by_role=None, default_taken="request changes",
    )  # fmt: skip


def test_the_database_itself_refuses_a_human_without_a_role_and_a_bare_override(
    migrated: str,
) -> None:
    with pytest.raises(errors.CheckViolation):
        raw_decision(migrated, decided_by_role=None)
    with pytest.raises(errors.CheckViolation):
        raw_decision(migrated, type="override", overrides_decision_id=None)


def test_a_decision_is_stored_with_the_database_checks_satisfied(app_pool: Pool) -> None:
    register = PostgresDecisionRegister(app_pool)
    decision = DecisionRecord(
        project_id="prj_ab12",
        type="approve_plan",
        decided_by_kind="human",
        decided_by="oid",
        decided_by_role="sponsor",
        card=DecisionCard(question="Approve the plan?"),
        outcome="approved",
    )
    assert register.record(decision) == decision


# ---------------------------------------------------------------- concurrency
def test_concurrent_reservations_never_overspend_a_scope(app_pool: Pool) -> None:
    ledger = PostgresLedger(app_pool)
    ledger.open_scope("prj", D("8"))
    for ws in ("a", "b", "c"):
        ledger.open_scope(f"prj/{ws}", D("5"))
    attempts = 36

    def reserve(i: int) -> bool:
        try:
            ledger.reserve(f"r{i}", ["prj", f"prj/{'abc'[i % 3]}"], D("1"))
        except BudgetExceeded:
            return False
        return True

    with ThreadPoolExecutor(12) as pool:
        granted = sum(pool.map(reserve, range(attempts)))
    assert granted == 8, "exactly the project's limit was granted, and no more"
    project = ledger.snapshot("prj")
    assert project.reserved == D("8") and project.available == D("0")
    for ws in ("a", "b", "c"):
        assert ledger.snapshot(f"prj/{ws}").reserved <= D("5")


def test_concurrent_identical_reservations_reserve_once(app_pool: Pool) -> None:
    ledger = PostgresLedger(app_pool)
    ledger.open_scope("s", D("10"))
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda _: ledger.reserve("same", ["s"], D("3")), range(16)))
    assert ledger.snapshot("s").reserved == D("3")


def test_concurrent_settle_and_reserve_never_lose_or_double_count_money(app_pool: Pool) -> None:
    ledger = PostgresLedger(app_pool)
    ledger.open_scope("s", D("100"))
    for i in range(20):
        ledger.reserve(f"old{i}", ["s"], D("2"))

    def work(i: int) -> None:
        ledger.settle(f"old{i}", Usage(cost=D("1.5")))
        ledger.settle(f"old{i}", Usage(cost=D("1.5")))  # a retry at the same time
        ledger.reserve(f"new{i}", ["s"], D("1"))

    with ThreadPoolExecutor(10) as pool:
        list(pool.map(work, range(20)))
    snap = ledger.snapshot("s")
    assert snap.committed == D("30") and snap.reserved == D("20")


def test_concurrent_audit_appends_form_one_unbroken_chain(app_pool: Pool) -> None:
    log = PostgresAuditLog(app_pool)
    count = 40
    with ThreadPoolExecutor(10) as pool:
        list(pool.map(lambda i: log.append("load.tested", actor=f"w{i}"), range(count)))
    events = log.events()
    assert [e.seq for e in events] == list(range(1, count + 1))
    report = log.verify_chain()
    assert report.ok and report.checked == count


def test_concurrent_appends_with_one_event_id_write_one_event(app_pool: Pool) -> None:
    log = PostgresAuditLog(app_pool)
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda _: log.append("retry.safe", actor="s", event_id="aud_one"), range(16)))
    assert len(log.events()) == 1 and log.verify_chain().ok
