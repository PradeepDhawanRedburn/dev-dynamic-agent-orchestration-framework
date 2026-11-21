"""S-24: with no LangSmith variables set, the installed langsmith package stays silent."""

import functools
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

PROBE = Path(__file__).with_name("langsmith_silence_probe.py")
TRACING_PREFIXES = ("LANGSMITH_", "LANGCHAIN_")


@functools.cache
def run_probe(kind: str) -> dict[str, Any]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(TRACING_PREFIXES)}
    done = subprocess.run(
        [sys.executable, str(PROBE), kind], env=env, capture_output=True, text=True, timeout=180
    )
    line = next((x for x in done.stdout.splitlines() if x.startswith("PROBE ")), "")
    assert line, f"probe did not report:\n{done.stdout[-800:]}\n{done.stderr[-800:]}"
    report: dict[str, Any] = json.loads(line.removeprefix("PROBE "))
    return report


def test_s24_graphs_agents_and_plain_tests_make_no_network_attempt_when_unconfigured() -> None:
    report = run_probe("plain")
    assert report["guard_catches_a_real_attempt"], "the guard must see a real attempt"
    assert report["tracing_enabled"] is False
    assert report["after_graph_and_agent"] == []
    assert report["pytest"] == {"exit": 0, "attempts": []}


def test_s24_a_test_marked_langsmith_contacts_langsmith_even_with_nothing_configured() -> None:
    """The assumption fails for the pytest plugin: see docs/plan/spike-findings.md S-24."""
    marked = run_probe("marked")["pytest"]
    assert marked["exit"] == 1, "the marked test fails because the connection is refused"
    assert marked["attempts"] == ["getaddrinfo('api.smith.langchain.com', 443)"]
