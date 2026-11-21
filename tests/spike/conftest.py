"""Shared fixtures for the architecture spike (WP-01).

Spike tests settle one assumption each from docs/plan/spike-checklist.md. They need no cloud
credentials unless marked `foundry`; those are skipped, visibly, when Foundry is not configured.
Tests marked `postgres` use a throwaway local container, or `SPIKE_POSTGRES_DSN` when set (CI).
"""

import asyncio
import os
import pathlib
import secrets
import shutil
import subprocess
import time
from collections.abc import Callable, Coroutine, Iterator
from typing import Any

import psycopg
import pytest
from psycopg.conninfo import make_conninfo

POSTGRES_IMAGE = (
    "postgres:17-alpine@sha256:526f86d93c6ea08fd3f1fe5605650cacc781b2c6013169a0ad8f42c7d3d84f32"
)
# What the Foundry tests read unconditionally; the mid and hard deployments skip on their own.
FOUNDRY_VARIABLES = ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_MODEL_EASY_TASK")
ON_CI = bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))


def load_foundry_settings() -> None:
    """Read AZURE_* settings from the git-ignored .env; a variable already set wins.

    Empty values are ignored, so copying .env.example does not switch the Foundry tests on.
    """
    env_file = pathlib.Path(__file__).resolve().parents[2] / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if separator and key.startswith("AZURE_") and value and not line.lstrip().startswith("#"):
            os.environ.setdefault(key, value)


load_foundry_settings()


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


def postgres_unavailable(reason: str) -> None:
    """Skip locally, but fail on CI, where a skip would hide a broken check."""
    if ON_CI:
        pytest.fail(f"PostgreSQL is required on CI and is not available: {reason}", pytrace=False)
    pytest.skip(f"{reason} (could not test)")


@pytest.fixture(scope="session")
def postgres_admin_dsn() -> Iterator[str]:
    """A DSN for a PostgreSQL server the spike may create databases on."""
    configured = os.environ.get("SPIKE_POSTGRES_DSN")
    if configured:
        yield configured
        return
    if shutil.which("docker") is None:
        postgres_unavailable("needs PostgreSQL: install Docker or set SPIKE_POSTGRES_DSN")
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
        postgres_unavailable(
            f"could not start PostgreSQL container: {started.stderr.strip()[:200]}"
        )
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
def new_database(postgres_admin_dsn: str) -> Iterator[Callable[[], str]]:
    """Create empty databases on request and drop every one of them afterwards, pass or fail.

    The DSN returned keeps every connection parameter of the admin DSN and changes only dbname,
    so it works for URI and keyword DSNs and keeps options such as sslmode.
    """
    created: list[str] = []

    def create() -> str:
        name = f"spike_{secrets.token_hex(6)}"
        with psycopg.connect(postgres_admin_dsn, autocommit=True) as conn:
            conn.execute(f'CREATE DATABASE "{name}"')
        created.append(name)
        return make_conninfo(postgres_admin_dsn, dbname=name)

    yield create
    with psycopg.connect(postgres_admin_dsn, autocommit=True) as conn:
        for name in created:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture
def pg_dsn(new_database: Callable[[], str]) -> str:
    return new_database()
