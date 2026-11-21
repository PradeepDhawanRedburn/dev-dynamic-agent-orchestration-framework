"""Measurement: checkpoint size and write latency for a ten-task workstream (WP-01).

Compares state held by reference (ids and statuses, ADR-0018) with state holding every result body.
Numbers depend on the machine and a local container; they size the problem, they are not a
benchmark of Azure Database for PostgreSQL. Run with `-s` to see the table.
"""

import base64
import operator
import os
import statistics
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Any

import psycopg
import pytest
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from psycopg.rows import dict_row
from typing_extensions import TypedDict

pytestmark = pytest.mark.postgres

TASKS = 10
BODY_BYTES = 20_000
RUNS = 8


def merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    return {**left, **right}


class Workstream(TypedDict):
    workstream_id: str
    tasks: Annotated[dict[str, Any], merge]
    reviewed: Annotated[list[str], operator.add]


class TimedSaver(PostgresSaver):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.timings: dict[str, list[float]] = {"put": [], "put_writes": []}

    def put(self, *args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            return super().put(*args, **kwargs)
        finally:
            self.timings["put"].append((time.perf_counter() - started) * 1000)

    def put_writes(self, *args: Any, **kwargs: Any) -> Any:
        started = time.perf_counter()
        try:
            return super().put_writes(*args, **kwargs)
        finally:
            self.timings["put_writes"].append((time.perf_counter() - started) * 1000)


@contextmanager
def timed_saver(dsn: str) -> Iterator[TimedSaver]:
    with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as conn:  # type: ignore[arg-type]
        saver = TimedSaver(conn)  # type: ignore[arg-type]
        saver.setup()
        yield saver


def build(saver: PostgresSaver, *, by_reference: bool) -> Any:
    def fan(state: Workstream) -> list[Send]:
        return [Send("task", {"task_id": f"task_{i}"}) for i in range(TASKS)]

    def task(payload: dict[str, Any]) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "status": "awaiting_review",
            "result_ref": f"res_{payload['task_id']}",
        }
        if not by_reference:
            entry["result_body"] = base64.b64encode(os.urandom(BODY_BYTES * 3 // 4)).decode()
        return {"tasks": {payload["task_id"]: entry}}

    def review(state: Workstream) -> dict[str, Any]:
        return {"reviewed": sorted(state["tasks"])}

    builder = StateGraph(Workstream)
    builder.add_node("task", task)
    builder.add_node("review", review)
    builder.add_conditional_edges(START, fan, ["task"])
    builder.add_edge("task", "review")
    builder.add_edge("review", END)
    return builder.compile(checkpointer=saver)


def stored_bytes(dsn: str, thread_id: str) -> tuple[int, int]:
    """Logical bytes held for the thread (blobs as written, JSON as text), and its checkpoints."""
    queries = (
        "select coalesce(sum(length(checkpoint::text) + length(metadata::text)), 0) "
        "from checkpoints where thread_id = %s",
        "select coalesce(sum(octet_length(blob)), 0) from checkpoint_blobs where thread_id = %s",
        "select coalesce(sum(octet_length(blob)), 0) from checkpoint_writes where thread_id = %s",
    )
    with psycopg.connect(dsn) as conn:
        total = 0
        for query in queries:
            (size,) = conn.execute(query, (thread_id,)).fetchone()  # type: ignore[misc]
            total += int(size)
        (rows,) = conn.execute(
            "select count(*) from checkpoints where thread_id = %s", (thread_id,)
        ).fetchone()  # type: ignore[misc]
    return total, int(rows)


def measure(dsn: str, *, by_reference: bool) -> dict[str, float]:
    puts: list[float] = []
    writes: list[float] = []
    run_ms: list[float] = []
    sizes: list[int] = []
    checkpoints = 0
    with timed_saver(dsn) as saver:
        graph = build(saver, by_reference=by_reference)
        for run in range(RUNS):
            thread = f"ten-{by_reference}-{run}"
            started = time.perf_counter()
            graph.invoke(
                {"workstream_id": "ws", "tasks": {}, "reviewed": []},
                {"configurable": {"thread_id": thread}},
            )
            run_ms.append((time.perf_counter() - started) * 1000)
            size, checkpoints = stored_bytes(dsn, thread)
            sizes.append(size)
        puts, writes = saver.timings["put"], saver.timings["put_writes"]
    return {
        "checkpoints_per_run": checkpoints,
        "bytes_per_run": statistics.median(sizes),
        "put_ms_median": statistics.median(puts),
        "put_ms_p95": sorted(puts)[int(len(puts) * 0.95) - 1],
        "put_writes_ms_median": statistics.median(writes),
        "put_writes_calls_per_run": len(writes) / RUNS,
        "run_ms_median": statistics.median(run_ms),
    }


def test_checkpoint_size_and_latency_for_a_ten_task_workstream(pg_dsn: str) -> None:
    by_reference = measure(pg_dsn, by_reference=True)
    by_value = measure(pg_dsn, by_reference=False)
    print(f"\n{'':28}{'by reference':>16}{'by value (20 kB/task)':>24}")
    for key in by_reference:
        print(f"{key:28}{by_reference[key]:>16.1f}{by_value[key]:>24.1f}")
    assert by_reference["bytes_per_run"] < by_value["bytes_per_run"]
    assert by_reference["bytes_per_run"] < 100_000
