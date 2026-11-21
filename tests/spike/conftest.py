"""Shared fixtures for the architecture spike (WP-01).

Spike tests settle one assumption each from docs/plan/spike-checklist.md. They need no cloud
credentials unless marked `foundry`; those are skipped, visibly, when Foundry is not configured.
Tests marked `postgres` use a throwaway local container, or `SPIKE_POSTGRES_DSN` when set (CI).
"""

import asyncio
import os
import secrets
import shutil
import subprocess
import time
from collections.abc import Callable, Coroutine, Iterator
from typing import Any

import psycopg
import pytest

POSTGRES_IMAGE = (
    "postgres:17-alpine"
    "@sha256:526f86d93c6ea08fd3f1fe5605650cacc781b2c6013169a0ad8f42c7d3d84f32"
)
FOUNDRY_VARIABLES = ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY")


def run_async[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine on a selector loop; psycopg's async mode rejects the Windows default."""
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        return runner.run(coro)


def foundry_configured() -> bool:
    return all(os.environ.get(name) for name in FOUNDRY_VARIABLES)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if foundry_configured():
        return
    skip = pytest.mark.skip(
        reason=f"needs Microsoft Foundry: set {' and '.join(FOUNDRY_VARIABLES)} (could not test)"
    )
    for item in items:
        if "foundry" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def postgres_admin_dsn() -> Iterator[str]:
    """A DSN for a PostgreSQL server the spike may create databases on."""
    configured = os.environ.get("SPIKE_POSTGRES_DSN")
    if configured:
        yield configured
        return
    if shutil.which("docker") is None:
        pytest.skip("needs PostgreSQL: install Docker or set SPIKE_POSTGRES_DSN (could not test)")
    password = secrets.token_urlsafe(16)
    started = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--rm",
            "-p",
            "127.0.0.1::5432",
            "-e",
            f"POSTGRES_PASSWORD={password}",
            POSTGRES_IMAGE,
        ],  # fmt: skip
        capture_output=True,
        text=True,
    )
    if started.returncode != 0:
        pytest.skip(f"could not start PostgreSQL container: {started.stderr.strip()[:200]}")
    container = started.stdout.strip()
    try:
        port = subprocess.run(
            ["docker", "port", container, "5432/tcp"], capture_output=True, text=True, check=True
        ).stdout.splitlines()[0].rsplit(":", 1)[1]  # fmt: skip
        dsn = f"postgresql://postgres:{password}@127.0.0.1:{port}/postgres"
        deadline = time.monotonic() + 60
        while True:
            try:
                psycopg.connect(dsn, connect_timeout=2).close()
                break
            except psycopg.OperationalError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.5)
        yield dsn
    finally:
        subprocess.run(["docker", "rm", "-f", container], capture_output=True)


@pytest.fixture
def new_database(postgres_admin_dsn: str) -> Callable[[], str]:
    """Create an empty database and return its DSN; each test gets its own."""

    def create() -> str:
        name = f"spike_{secrets.token_hex(6)}"
        with psycopg.connect(postgres_admin_dsn, autocommit=True) as conn:
            conn.execute(f'CREATE DATABASE "{name}"')
        head, _, _ = postgres_admin_dsn.rpartition("/")
        return f"{head}/{name}"

    return create


@pytest.fixture
def pg_dsn(new_database: Callable[[], str]) -> str:
    return new_database()
