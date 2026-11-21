"""WP-01 task 2: run the reference LangGraph code (reference/lg) against the real libraries.

reference/ is read-only, so its modules are copied to a temporary folder and run there. app.py is
deliberately not copied: importing it creates a LangSmith client, which contacts
api.smith.langchain.com (found during this spike; see docs/plan/spike-findings.md).
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
DRIVER = Path(__file__).with_name("reference_run") / "driver.py"


@pytest.fixture(scope="module")
def reference_copy(tmp_path_factory: pytest.TempPathFactory) -> Path:
    target = tmp_path_factory.mktemp("reference")
    for source in [*(REPO / "reference").glob("*.py"), *(REPO / "reference" / "lg").glob("*.py")]:
        if source.name.startswith("test_") or source.name == "app.py":
            continue
        shutil.copy(source, target / source.name)
    return target


def run(mode: str, folder: Path) -> tuple[dict[str, Any], str]:
    env = {**os.environ, "SPIKE_REPO": str(REPO), "PYTHONIOENCODING": "utf-8"}
    for name in list(env):
        if name.startswith(("LANGSMITH_", "LANGCHAIN_")):
            del env[name]
    done = subprocess.run(
        [sys.executable, str(DRIVER), mode],
        cwd=folder, env=env, capture_output=True, text=True, timeout=300,
    )  # fmt: skip
    line = next((x for x in done.stdout.splitlines() if x.startswith("RESULT ")), "")
    assert line, f"driver failed:\n{done.stdout[-1500:]}\n{done.stderr[-2500:]}"
    report: dict[str, Any] = json.loads(line.removeprefix("RESULT "))
    return report, done.stderr


def test_reference_graphs_run_end_to_end_on_real_langgraph_with_a_stand_in_agent(
    reference_copy: Path,
) -> None:
    report, stderr = run("stand_in", reference_copy)
    assert report["outcome"] == "approved"
    assert report["gates"] == ["plan", "guardrail", "final"]
    assert {w["status"] for w in report["workstreams"].values()} == {"complete"}
    # The same figures the architect's stand-in runtime printed for this scenario.
    assert report["deliverable"]["claims"] == 5 and report["deliverable"]["evidence"] == 14
    assert report["deliverable"]["usage"]["model_calls"] == 33
    assert report["deliverable"]["usage"]["cost"] == "0.4501"
    assert report["revisions"] == {"data_quality": 2, "api": 2, "streaming_tests": 2}
    assert report["live_credentials"] == 0
    assert all(history[-1] == "retired" for _, history in report["agents"])
    assert "Deserializing unregistered type contracts.AgentStatus" in stderr


def test_reference_graphs_run_with_the_real_create_agent_and_governance_middleware(
    reference_copy: Path,
) -> None:
    report, _ = run("real_agent", reference_copy)
    assert report["outcome"] == "approved"
    assert {w["status"] for w in report["workstreams"].values()} == {"complete"}
    assert len(report["agents"]) == 4
    for _, history in report["agents"]:
        assert history[-3:] == ["awaiting_review", "accepted", "retired"]
    assert report["live_credentials"] == 0


def test_reference_graphs_under_strict_msgpack_still_finish_but_block_the_enum(
    reference_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LANGGRAPH_STRICT_MSGPACK", "true")
    report, stderr = run("stand_in", reference_copy)
    assert report["outcome"] == "approved"
    assert "Blocked deserialization of contracts.AgentStatus" in stderr
