"""Runs the reference supervisor and Lead graphs (copied to the cwd) on REAL LangGraph.

    driver.py stand_in    real graph runtime; specialists' agent loop is a stand-in, as in dryrun.py
    driver.py real_agent  real graph runtime AND real langchain create_agent with the reference
                          governance middleware, driven by a scripted BaseChatModel

Permanent agents' answers are scripted (dryrun.scripted). No model, no network: every outbound
connection is refused. Prints one `RESULT {json}` line. Run by test_reference_lg.py.
"""

import asyncio
import json
import os
import socket
import sys
from decimal import Decimal
from typing import Any

_connect = socket.socket.connect


def _refuse(*args: Any, **kwargs: Any) -> Any:
    raise OSError("network blocked by spike guard")


def _connect_loopback_only(self: socket.socket, address: Any) -> Any:
    if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1"):
        return _connect(self, address)
    return _refuse()


socket.getaddrinfo = _refuse  # type: ignore[assignment]
socket.create_connection = _refuse  # type: ignore[assignment]
socket.socket.connect = _connect_loopback_only  # type: ignore[method-assign]
socket.socket.connect_ex = _refuse  # type: ignore[assignment,method-assign]
sys.path.insert(0, ".")
sys.path.insert(0, os.environ["SPIKE_REPO"])

import langchain.agents as la  # noqa: E402

la.SCRIPT = {}  # type: ignore[attr-defined]  # dryrun.py expects this from its stub library
import dryrun  # noqa: E402
import worker  # noqa: E402
from contracts import BudgetPolicy  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from langgraph.types import Command  # noqa: E402

from tests.spike.support import (  # noqa: E402
    ScriptedChatModel,
    specialist_output_args,
    tool_call_message,
)


class StandInMessage:
    usage_metadata = {"input_tokens": 1200, "output_tokens": 300}


class StandInAgent:
    """What the reference dry run used in place of create_agent."""

    def __init__(self, **kw: Any) -> None:
        self.kw = kw

    async def ainvoke(self, inp: Any, config: Any = None) -> Any:
        state = {"messages": list(inp["messages"])}
        hooks = [m for m in self.kw["middleware"] if hasattr(m, "abefore_model")]
        for turn in range(2):
            for m in hooks:
                await m.abefore_model(state, None)
            state["messages"].append(StandInMessage())
            for m in hooks:
                await m.aafter_model(state, None)
            if turn == 0:
                tools = {t.name: t for t in self.kw["tools"]}
                out = await la.SCRIPT[config["run_name"]](tools, inp)  # type: ignore[attr-defined]
        return {"messages": state["messages"], "structured_response": out}


class ReferenceChat(ScriptedChatModel):
    """Answers for permanent agents (via with_structured_output) and for specialists."""

    schemas: list[Any] = []
    tool_names: list[str] = []

    def _generate(self, messages: Any, stop: Any = None, run_manager: Any = None, **kw: Any) -> Any:
        if self.schemas:
            schema = self.schemas[0]
            parsed = dryrun.scripted(schema, messages[0].content, messages[1].content)
            reply = tool_call_message(
                schema.__name__,
                parsed.model_dump(mode="json"),
                input_tokens=2500,
                output_tokens=600,
            )
            return ChatResult(generations=[ChatGeneration(message=reply)])
        results = [m for m in messages if m.type == "tool" and m.name != "SpecialistOutput"]
        domain = [n for n in self.tool_names if n != "SpecialistOutput"]
        if not results and domain:
            reply = tool_call_message(
                domain[0], {"query": "azure event streaming", "scope": "accepted"},
                input_tokens=120, output_tokens=30,
            )  # fmt: skip
        else:
            evidence = (
                [
                    i["evidence_id"]
                    for i in json.loads(results[-1].content)["items"]
                    if "evidence_id" in i
                ]
                if results
                else []
            )
            args = specialist_output_args(1)
            args["claims"][0]["evidence_ids"] = evidence or ["ev_missing"]
            reply = tool_call_message("SpecialistOutput", args, input_tokens=300, output_tokens=200)
        return ChatResult(generations=[ChatGeneration(message=reply)])

    def bind_tools(self, tools: Any, **kw: Any) -> Any:
        classes = [t for t in tools if isinstance(t, type)]
        if classes and len(classes) == len(tools):
            return self.model_copy(update={"schemas": classes})
        names = [getattr(t, "name", None) or getattr(t, "__name__", "?") for t in tools]
        return self.model_copy(update={"tool_names": names})


GATES = {
    "plan": lambda v: {"decision": "approve", "approver": "sponsor-oid"},
    "guardrail": lambda v: {
        "approver": "security-owner-oid",
        "decisions": {a: "resume" for a in v["suspended"]},
    },
    "final": lambda v: {"decision": "approve", "approver": "sponsor-oid", "comment": "Approved."},
}


async def main(mode: str) -> dict[str, Any]:
    from lead import build_lead_graph
    from supervisor import build_supervisor

    report: dict[str, Any] = {"mode": mode, "gates": []}
    svc = dryrun.make_services()
    if mode == "stand_in":
        worker.create_agent = lambda **kw: StandInAgent(**kw)
    else:
        svc.models = type(
            "Models", (), {"chat": staticmethod(lambda key, **kw: ReferenceChat(script=[]))}
        )()
    provision = svc.recruiter.provision

    def tracked(req: Any, **kw: Any) -> Any:
        svc.owners[req.task_id] = req.requested_by
        return provision(req, **kw)

    svc.recruiter.provision = tracked
    graph = build_supervisor(svc, build_lead_graph(svc)).compile(checkpointer=InMemorySaver())
    limits = BudgetPolicy(
        max_cost=Decimal("40"), max_tokens=2_000_000, max_tool_calls=120,
        max_model_calls=120, timeout_seconds=600, max_retries=1,
    )  # fmt: skip
    project = "prj_" + "ab12" * 4
    payload: Any = {
        "project_id": project, "correlation_id": "cor_1",
        "versions": {"graph": "0.1.0", "policy": "2026.11.0"},
        "raw_request": "Should we replace nightly batch integration with event streaming?",
        "sponsor": "sponsor-oid", "limits": limits.model_dump(mode="json"),
    }  # fmt: skip
    config = {"configurable": {"thread_id": project}, "recursion_limit": 150}
    result: Any = None
    for _ in range(8):
        result = await graph.ainvoke(payload, config)
        pending = result.get("__interrupt__")
        if not pending:
            break
        value = pending[0].value
        report["gates"].append(value["gate"])
        payload = Command(resume=GATES[value["gate"]](value))
    report["outcome"] = result.get("outcome")
    report["workstreams"] = {
        r["lead"]: {
            "status": r["status"],
            "accepted": len(r["accepted_results"]),
            "gaps": len(r["gaps"]),
        }
        for r in result["workstream_results"].values()
    }
    report["deliverable"] = {
        "claims": len(result["deliverable"]["claims"]),
        "evidence": len(result["deliverable"]["evidence_ids"]),
        "usage": result["deliverable"]["total_usage"],
    }
    report["agents"] = [
        [r.spec.role_title, [s.value for s, _ in r.history]]
        for r in svc.recruiter.agents.for_project(project)
    ]
    report["live_credentials"] = len(svc.credentials.live)
    report["meter"] = {
        owner.split(":", 1)[-1] if owner.startswith("prj_") else "specialist:" + owner: [
            u.model_calls,
            u.tool_calls,
            u.input_tokens,
            u.output_tokens,
        ]  # fmt: skip
        for owner, u in svc.ledger_meter.u.items()
    }
    report["revisions"] = dryrun.CALLS
    return report


if __name__ == "__main__":
    print("RESULT " + json.dumps(asyncio.run(main(sys.argv[1])), default=str))
