"""S-03, S-04, S-14: error handlers, per-task timeouts and concurrency limits on Send fan-out."""

import asyncio
import operator
import time
from typing import Annotated, Any

import pytest
from langgraph.errors import NodeError, NodeTimeoutError
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send, TimeoutPolicy
from typing_extensions import TypedDict


class State(TypedDict):
    results: Annotated[list[str], operator.add]


def build(
    node: Any,
    sends: list[Send],
    *,
    error_handler: Any = None,
    extra: dict[str, Any] | None = None,
) -> Any:
    builder = StateGraph(State)
    builder.add_node("worker", node, error_handler=error_handler)
    for name, fn in (extra or {}).items():
        builder.add_node(name, fn)
    builder.add_conditional_edges(START, lambda _: sends, ["worker", *(extra or {})])
    builder.add_edge("worker", END)
    return builder.compile()


def test_s03_error_handler_receives_the_send_payload_first() -> None:
    received: dict[str, Any] = {}

    def failing(payload: dict[str, Any]) -> dict[str, Any]:
        raise ValueError(f"boom {payload['task_id']}")

    def handler(payload: dict[str, Any], error: NodeError) -> Command[Any]:
        received["payload"] = payload
        received["node"] = error.node
        received["error"] = repr(error.error)
        return Command(update={"results": [f"recovered {payload['task_id']}"]})

    graph = build(failing, [Send("worker", {"task_id": "t1", "other": 7})], error_handler=handler)
    result = graph.invoke({"results": []})

    assert received["payload"] == {"task_id": "t1", "other": 7}
    assert received["node"] == "worker"
    assert "boom t1" in received["error"]
    assert result["results"] == ["recovered t1"]


def test_s04_send_timeout_cancels_a_slow_branch() -> None:
    async def slow(_: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(5)
        return {"results": ["late"]}

    graph = build(slow, [Send("worker", {}, timeout=TimeoutPolicy(run_timeout=0.3))])
    started = time.monotonic()
    with pytest.raises(NodeTimeoutError):
        asyncio.run(graph.ainvoke({"results": []}))
    assert time.monotonic() - started < 3


def test_s04_timed_out_branch_can_be_recovered_by_an_error_handler() -> None:
    async def worker(payload: dict[str, Any]) -> dict[str, Any]:
        if payload["slow"]:
            await asyncio.sleep(5)
        return {"results": [f"ok {payload['name']}"]}

    def on_error(payload: dict[str, Any], error: NodeError) -> Command[Any]:
        return Command(
            update={"results": [f"timeout {payload['name']}: {type(error.error).__name__}"]}
        )

    policy = TimeoutPolicy(run_timeout=0.3)
    graph = build(
        worker,
        [
            Send("worker", {"name": "fast", "slow": False}, timeout=policy),
            Send("worker", {"name": "slow", "slow": True}, timeout=policy),
        ],
        error_handler=on_error,
    )
    result = asyncio.run(graph.ainvoke({"results": []}))
    assert sorted(result["results"]) == ["ok fast", "timeout slow: NodeTimeoutError"]


def concurrency_graph(branches: int) -> tuple[Any, dict[str, int]]:
    counters = {"now": 0, "peak": 0}

    async def worker(_: dict[str, Any]) -> dict[str, Any]:
        counters["now"] += 1
        counters["peak"] = max(counters["peak"], counters["now"])
        await asyncio.sleep(0.2)
        counters["now"] -= 1
        return {"results": ["x"]}

    graph = build(worker, [Send("worker", {"i": i}) for i in range(branches)])
    return graph, counters


def test_s14_max_concurrency_limits_parallel_send_branches() -> None:
    graph, counters = concurrency_graph(6)
    asyncio.run(graph.ainvoke({"results": []}, {"max_concurrency": 2}))
    assert counters["peak"] == 2


def test_s14_without_a_limit_all_branches_run_together() -> None:
    graph, counters = concurrency_graph(6)
    asyncio.run(graph.ainvoke({"results": []}))
    assert counters["peak"] == 6
