"""No LangSmith or LangChain tracing or endpoint variable may be set (ADR-0029, WP-01 item 9).

The langsmith client arrives as a dependency of langchain. It stays unconfigured so that nothing
can leave Azure by accident.
"""

import os
from pathlib import Path

from langsmith import utils

PREFIXES = ("LANGSMITH_", "LANGCHAIN_")


def test_no_langsmith_or_langchain_variable_is_set() -> None:
    present = sorted(name for name in os.environ if name.upper().startswith(PREFIXES))
    assert present == [], f"remove these from the environment: {present}"


def test_langsmith_tracing_is_off() -> None:
    assert utils.tracing_is_enabled() is False


def test_no_test_uses_the_langsmith_marker() -> None:
    """A test marked `langsmith` contacts api.smith.langchain.com even with nothing configured
    (spike S-24), so only the probe that demonstrates it may use the marker."""
    needle = "mark." + "langsmith"
    offenders = [
        path.name
        for path in Path(__file__).resolve().parents[1].rglob("*.py")
        if path.name != "langsmith_silence_probe.py" and needle in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
