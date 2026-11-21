"""Probe for S-24: run LangGraph, LangChain and the langsmith pytest plugin with every network
entry point recorded and refused, then print what was attempted as JSON.

Run only by tests/spike/test_langsmith_silence.py, in a subprocess with a clean environment.
"""

import json
import socket
import sys
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

attempts: list[str] = []


def refuse(name: str) -> Any:
    def guard(*args: Any, **kwargs: Any) -> Any:
        attempts.append(f"{name}{args[:2] if name == 'getaddrinfo' else ''}")
        raise OSError(f"network blocked by probe: {name}")

    return guard


socket.getaddrinfo = refuse("getaddrinfo")  # type: ignore[assignment]
socket.create_connection = refuse("create_connection")  # type: ignore[assignment]
socket.socket.connect = refuse("connect")  # type: ignore[assignment,method-assign]
socket.socket.connect_ex = refuse("connect_ex")  # type: ignore[assignment,method-assign]

import pytest  # noqa: E402
from langchain.agents import create_agent  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402
from langgraph.graph import END, START, StateGraph  # noqa: E402
from langsmith import utils  # noqa: E402
from typing_extensions import TypedDict  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.spike.support import ScriptedChatModel  # noqa: E402


class State(TypedDict):
    n: int


def run_workloads() -> None:
    builder = StateGraph(State)
    builder.add_node("inc", lambda s: {"n": s["n"] + 1})
    builder.add_edge(START, "inc")
    builder.add_edge("inc", END)
    builder.compile().invoke({"n": 0})
    agent = create_agent(ScriptedChatModel(script=[AIMessage("hi")]), tools=[])
    agent.invoke({"messages": [HumanMessage("hello")]})


def run_pytest(body: str) -> dict[str, Any]:
    before = len(attempts)
    with tempfile.TemporaryDirectory() as folder:
        test_file = Path(folder) / "test_probe.py"
        test_file.write_text("import pytest\n" + body, encoding="utf-8")
        exit_code = int(pytest.main(["-q", "-p", "no:cacheprovider", str(test_file)]))
    return {"exit": exit_code, "attempts": sorted(set(attempts[before:]))}


def positive_control() -> bool:
    before = len(attempts)
    try:
        urllib.request.urlopen("http://control.invalid/", timeout=1)  # noqa: S310
    except Exception:  # noqa: BLE001
        pass
    return len(attempts) > before


TESTS = {
    "plain": "def test_probe():\n    assert True\n",
    "marked": "@pytest.mark.langsmith\ndef test_probe():\n    assert True\n",
}

report: dict[str, Any] = {"tracing_enabled": utils.tracing_is_enabled()}
run_workloads()
report["after_graph_and_agent"] = list(attempts)
report["pytest"] = run_pytest(TESTS[sys.argv[1]])
attempts.clear()
report["guard_catches_a_real_attempt"] = positive_control()
print("PROBE " + json.dumps(report))
