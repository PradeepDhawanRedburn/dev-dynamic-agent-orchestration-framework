"""Fixtures for the integration tests: every behaviour test runs against the in-memory stores and
against PostgreSQL, and must give the same answers.

The PostgreSQL stores run as `orchestrator_app`, the role the application uses, so these tests
also prove that role has every privilege normal operation needs."""

from collections.abc import Iterator
from dataclasses import dataclass

import pytest

from orchestrator.governance.approvals import DecisionRegister, InMemoryDecisionRegister
from orchestrator.governance.budget import BudgetLedger, InMemoryLedger
from orchestrator.governance.recruiter import AgentRegistry, InMemoryAgentRegistry
from orchestrator.persistence.audit import AuditLog, InMemoryAuditLog
from orchestrator.persistence.db import Pool, open_pool
from orchestrator.persistence.evidence import EvidenceStore, InMemoryEvidenceStore
from orchestrator.persistence.migrate import apply_migrations
from orchestrator.persistence.repositories import (
    PostgresAgentRegistry,
    PostgresAuditLog,
    PostgresDecisionRegister,
    PostgresEvidenceStore,
    PostgresLedger,
)

APP_ROLE = "orchestrator_app"


@dataclass
class Stores:
    ledger: BudgetLedger
    registry: AgentRegistry
    evidence: EvidenceStore
    audit: AuditLog
    decisions: DecisionRegister
    backend: str
    dsn: str | None = None  # PostgreSQL only: the owner's DSN, for tests that simulate tampering


@pytest.fixture(params=["memory", "postgres"])
def stores(request: pytest.FixtureRequest) -> Iterator[Stores]:
    if request.param == "memory":
        yield Stores(
            InMemoryLedger(),
            InMemoryAgentRegistry(),
            InMemoryEvidenceStore(),
            InMemoryAuditLog(),
            InMemoryDecisionRegister(),
            "memory",
        )
        return
    dsn: str = request.getfixturevalue("pg_dsn")
    apply_migrations(dsn)
    pool: Pool = open_pool(dsn, role=APP_ROLE, max_size=12)
    try:
        yield Stores(
            PostgresLedger(pool),
            PostgresAgentRegistry(pool),
            PostgresEvidenceStore(pool),
            PostgresAuditLog(pool),
            PostgresDecisionRegister(pool),
            "postgres",
            dsn,
        )
    finally:
        pool.close()
