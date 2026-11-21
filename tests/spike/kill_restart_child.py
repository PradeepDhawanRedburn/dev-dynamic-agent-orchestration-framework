"""Child process for S-07: a fan-out run that the test kills mid-superstep and then resumes.

Environment: SPIKE_DSN, SPIKE_LOG (side-effect log), SPIKE_THREAD, SPIKE_DURABILITY,
SPIKE_MODE (`run` or `resume`), SPIKE_HANG (name of the branch that hangs, or empty).
"""

import asyncio
import json
import operator
import os
from typing import Annotated, Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from typing_extensions import TypedDict


class State(TypedDict):
    results: Annotated[list[str], operator.add]


def log(line: str) -> None:
    with open(os.environ["SPIKE_LOG"], "a", encoding="utf-8") as handle:
        handle.write(line + "\n")
        handle.flush()
        os.fsync(handle.fileno())


async def branch(payload: dict[str, Any]) -> dict[str, Any]:
    name = payload["name"]
    log(f"start {name}")
    if name == os.environ.get("SPIKE_HANG"):
        await asyncio.sleep(600)
    log(f"done {name}")
    return {"results": [name]}


async def finish(state: State) -> dict[str, Any]:
    log("finish")
    return {}


def build(saver: AsyncPostgresSaver) -> Any:
    builder = StateGraph(State)
    builder.add_node("branch", branch)
    builder.add_node("finish", finish)
    builder.add_conditional_edges(
        START, lambda _: [Send("branch", {"name": n}) for n in ("a", "b", "c")], ["branch"]
    )
    builder.add_edge("branch", "finish")
    builder.add_edge("finish", END)
    return builder.compile(checkpointer=saver)


async def main() -> None:
    config: Any = {"configurable": {"thread_id": os.environ["SPIKE_THREAD"]}}
    async with AsyncPostgresSaver.from_conn_string(os.environ["SPIKE_DSN"]) as saver:
        await saver.setup()
        graph = build(saver)
        first = os.environ["SPIKE_MODE"] == "run"
        result = await graph.ainvoke(
            {"results": []} if first else None,
            config,
            durability=os.environ["SPIKE_DURABILITY"],
        )
        log("result " + json.dumps(sorted(result["results"]) if result else None))


if __name__ == "__main__":
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        runner.run(main())
