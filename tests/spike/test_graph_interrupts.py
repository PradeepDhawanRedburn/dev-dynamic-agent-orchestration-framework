"""S-05, S-06, S-22: human gates raised at the supervisor, re-run on resume, and state history."""

from collections import Counter
from typing import Annotated, Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send, interrupt
from typing_extensions import TypedDict


def merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    return {**left, **right}


class Supervisor(TypedDict):
    outcomes: Annotated[dict[str, Any], merge]


def build_supervisor(
    runs: Counter[str], gate_entries: list[str], checkpointer: Any | None = None
) -> Any:
    def dispatch(_: Supervisor) -> list[Send]:
        return [Send("workstream", {"ws": ws, "answer": None}) for ws in ("A", "B")]

    def workstream(payload: dict[str, Any]) -> dict[str, Any]:
        runs[payload["ws"]] += 1
        if payload["ws"] == "B" and payload["answer"] is None:
            outcome = {"status": "decision_needed", "question": "which database?"}
        else:
            outcome = {"status": "done", "answer": payload["answer"]}
        return {"outcomes": {payload["ws"]: outcome}}

    def gate(state: Supervisor) -> Command[Any]:
        gate_entries.append("entered")
        pending = [ws for ws, o in state["outcomes"].items() if o["status"] == "decision_needed"]
        if not pending:
            return Command(goto=END)
        answers = interrupt(
            {"questions": {ws: state["outcomes"][ws]["question"] for ws in pending}}
        )
        return Command(
            goto=[Send("workstream", {"ws": ws, "answer": answers[ws]}) for ws in pending]
        )

    builder = StateGraph(Supervisor)
    builder.add_node("workstream", workstream)
    builder.add_node("gate", gate, destinations=("workstream", END))
    builder.add_conditional_edges(START, dispatch, ["workstream"])
    builder.add_edge("workstream", "gate")
    return builder.compile(checkpointer=checkpointer or InMemorySaver())


def test_s05_supervisor_interrupts_once_and_reruns_only_the_workstream_that_asked() -> None:
    runs: Counter[str] = Counter()
    gate_entries: list[str] = []
    graph = build_supervisor(runs, gate_entries)
    config: Any = {"configurable": {"thread_id": "s05"}}

    first = graph.invoke({"outcomes": {}}, config)
    interrupts = first["__interrupt__"]
    assert len(interrupts) == 1
    assert interrupts[0].value == {"questions": {"B": "which database?"}}
    assert runs == Counter({"A": 1, "B": 1})

    final = graph.invoke(Command(resume={"B": "postgres"}), config)
    assert "__interrupt__" not in final
    assert final["outcomes"]["A"] == {"status": "done", "answer": None}
    assert final["outcomes"]["B"] == {"status": "done", "answer": "postgres"}
    assert runs == Counter({"A": 1, "B": 2}), "workstream A must not run again"


def test_s05_parallel_interrupts_inside_send_branches_are_listed_with_ids() -> None:
    """Informational: what happens if branches interrupt instead of returning decision_needed."""

    class S(TypedDict):
        answers: Annotated[dict[str, Any], merge]

    def ask(payload: dict[str, Any]) -> dict[str, Any]:
        return {"answers": {payload["ws"]: interrupt(f"question for {payload['ws']}")}}

    builder = StateGraph(S)
    builder.add_node("ask", ask)
    builder.add_conditional_edges(
        START, lambda _: [Send("ask", {"ws": "A"}), Send("ask", {"ws": "B"})], ["ask"]
    )
    builder.add_edge("ask", END)
    graph = builder.compile(checkpointer=InMemorySaver())
    config: Any = {"configurable": {"thread_id": "s05b"}}

    first = graph.invoke({"answers": {}}, config)
    pending = first["__interrupt__"]
    assert sorted(i.value for i in pending) == ["question for A", "question for B"]
    assert all(i.id for i in pending)

    by_id = {i.id: f"answer to {i.value}" for i in pending}
    final = graph.invoke(Command(resume=by_id), config)
    assert final["answers"] == {
        "A": "answer to question for A",
        "B": "answer to question for B",
    }


def test_s06_node_that_interrupted_reruns_from_its_first_line() -> None:
    lines: list[str] = []

    class S(TypedDict):
        value: str

    def node(_: S) -> dict[str, Any]:
        lines.append("before")
        answer = interrupt("question")
        lines.append("after")
        return {"value": answer}

    builder = StateGraph(S)
    builder.add_node("node", node)
    builder.add_edge(START, "node")
    builder.add_edge("node", END)
    graph = builder.compile(checkpointer=InMemorySaver())
    config: Any = {"configurable": {"thread_id": "s06"}}

    graph.invoke({"value": ""}, config)
    assert lines == ["before"]
    result = graph.invoke(Command(resume="yes"), config)
    assert lines == ["before", "before", "after"]
    assert result["value"] == "yes"


def test_s22_state_history_links_a_decision_to_the_state_it_was_made_on() -> None:
    runs: Counter[str] = Counter()
    graph = build_supervisor(runs, [])
    config: Any = {"configurable": {"thread_id": "s22"}}
    graph.invoke({"outcomes": {}}, config)

    waiting = graph.get_state(config)
    assert waiting.next == ("gate",)
    assert waiting.interrupts and waiting.interrupts[0].value["questions"] == {
        "B": "which database?"
    }
    decided_on = waiting.config["configurable"]["checkpoint_id"]

    graph.invoke(Command(resume={"B": "postgres"}), config)
    history = list(graph.get_state_history(config))
    ids = [s.config["configurable"]["checkpoint_id"] for s in history]
    assert decided_on in ids

    snapshot = next(s for s in history if s.config["configurable"]["checkpoint_id"] == decided_on)
    assert snapshot.values["outcomes"]["B"]["status"] == "decision_needed"
    assert snapshot.created_at
    assert snapshot.parent_config is not None
    assert snapshot.metadata is not None and "step" in snapshot.metadata
