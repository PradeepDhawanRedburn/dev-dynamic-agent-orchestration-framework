"""Spike-specific test configuration (WP-01). The PostgreSQL fixtures are in tests/conftest.py.

Spike tests need no cloud credentials unless marked `foundry`; those are skipped, visibly, when
Foundry is not configured.
"""

import os
import pathlib

import pytest

# What the Foundry tests read unconditionally; the mid and hard deployments skip on their own.
FOUNDRY_VARIABLES = ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_MODEL_EASY_TASK")


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


def foundry_configured() -> bool:
    return all(os.environ.get(name) for name in FOUNDRY_VARIABLES)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if foundry_configured():
        return
    skip = pytest.mark.skip(
        reason=f"needs Microsoft Foundry: set {' and '.join(FOUNDRY_VARIABLES)} (could not test)"
    )
    for item in items:
        if "foundry" in item.keywords and "spike" in str(item.path):
            item.add_marker(skip)
