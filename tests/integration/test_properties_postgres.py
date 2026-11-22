"""The ledger properties against PostgreSQL: the same operations must give the same results as the
in-memory ledger, and no sequence of them may overspend a scope."""

from collections.abc import Iterator
from itertools import count
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings

from orchestrator.governance.budget import InMemoryLedger
from orchestrator.persistence.db import Pool, open_pool
from orchestrator.persistence.migrate import apply_migrations
from orchestrator.persistence.repositories import PostgresLedger
from tests.integration.conftest import APP_ROLE
from tests.unit.test_properties import operations, run_operations

pytestmark = pytest.mark.postgres


@pytest.fixture
def pool(pg_dsn: str) -> Iterator[Pool]:
    apply_migrations(pg_dsn)
    opened = open_pool(pg_dsn, role=APP_ROLE)
    yield opened
    opened.close()


def test_postgres_and_memory_agree_on_every_generated_sequence(pool: Pool) -> None:
    ledger = PostgresLedger(pool)
    example = count()

    @settings(
        max_examples=40,
        deadline=None,
        database=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    @given(operations)
    def check(ops: list[tuple[Any, ...]]) -> None:
        in_memory = run_operations(InMemoryLedger(), ops)
        in_postgres = run_operations(ledger, ops, prefix=f"e{next(example)}:")
        assert in_postgres == in_memory

    check()
