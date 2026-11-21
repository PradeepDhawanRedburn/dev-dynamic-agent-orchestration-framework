"""S-01, S-02, S-15, S-20: subgraph schemas, nested fan-out, reuse and Mermaid export."""

import operator
from typing import Annotated, Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import InvalidUpdateError
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send, interrupt
from typing_extensions import TypedDict


class ChildState(TypedDict):
    task_id: str
    scratch: str
    results: list[str]


class ChildInput(TypedDict):
    task_id: str


class ChildOutput(TypedDict):
    results: list[str]


class ParentState(TypedDict):
    results: Annotated[list[str], operator.add]
    scratch: str


def child_work(state: ChildState) -> dict[str, Any]:
    return {"scratch": f"scratch-{state['task_id']}", "results": [f"done-{state['task_id']}"]}


def build_child(*, restrict: bool) -> Any:
    if restrict:
        builder = StateGraph(ChildState, input_schema=ChildInput, output_schema=ChildOutput)
    else:
        builder = StateGraph(ChildState)
    builder.add_node("work", child_work)
    builder.add_edge(START, "work")
    builder.add_edge("work", END)
    return builder.compile()


def build_parent(child: Any) -> Any:
    def fan(_: ParentState) -> list[Send]:
        return [Send("child", {"task_id": "a"}), Send("child", {"task_id": "b"})]

    builder = StateGraph(ParentState)
    builder.add_node("child", child)
    builder.add_conditional_edges(START, fan, ["child"])
    builder.add_edge("child", END)
    return builder.compile()


def test_s01_output_schema_limits_what_a_subgraph_returns() -> None:
    result = build_parent(build_child(restrict=True)).invoke({"results": []})
    assert sorted(result["results"]) == ["done-a", "done-b"]
    assert "scratch" not in result


def test_s01_without_output_schema_parallel_subgraphs_collide_on_shared_keys() -> None:
    with pytest.raises(InvalidUpdateError):
        build_parent(build_child(restrict=False)).invoke({"results": []})


class LeadState(TypedDict):
    lead_id: str
    results: Annotated[list[str], operator.add]


class LeadInput(TypedDict):
    lead_id: str


class LeadOutput(TypedDict):
    results: list[str]


class SpecialistState(TypedDict):
    lead_id: str
    specialist: str


def test_s02_nested_send_fan_out() -> None:
    def specialist(state: SpecialistState) -> dict[str, Any]:
        return {"results": [f"{state['lead_id']}/{state['specialist']}"]}

    def spread(state: LeadState) -> list[Send]:
        return [Send("specialist", {"lead_id": state["lead_id"], "specialist": s}) for s in "xy"]

    lead = StateGraph(LeadState, input_schema=LeadInput, output_schema=LeadOutput)
    lead.add_node("specialist", specialist)
    lead.add_conditional_edges(START, spread, ["specialist"])
    lead.add_edge("specialist", END)
    lead_graph = lead.compile()

    def fan(_: ParentState) -> list[Send]:
        return [Send("lead", {"lead_id": "L1"}), Send("lead", {"lead_id": "L2"})]

    parent = StateGraph(ParentState)
    parent.add_node("lead", lead_graph)
    parent.add_conditional_edges(START, fan, ["lead"])
    parent.add_edge("lead", END)
    result = parent.compile().invoke({"results": []})
    assert sorted(result["results"]) == ["L1/x", "L1/y", "L2/x", "L2/y"]


class SharedState(TypedDict):
    topic: str
    log: Annotated[list[str], operator.add]


class InnerInput(TypedDict):
    topic: str


def test_s15_one_compiled_subgraph_under_two_node_names() -> None:
    def ask(state: SharedState) -> dict[str, Any]:
        answer = interrupt("question")
        return {"log": [f"{state['topic']}={answer}"]}

    inner = StateGraph(SharedState, input_schema=InnerInput)
    inner.add_node("ask", ask)
    inner.add_edge(START, "ask")
    inner.add_edge("ask", END)
    shared = inner.compile()

    outer = StateGraph(SharedState)
    outer.add_node("first", shared)
    outer.add_node("second", shared)
    outer.add_edge(START, "first")
    outer.add_edge("first", "second")
    outer.add_edge("second", END)
    graph = outer.compile(checkpointer=InMemorySaver())
    config: Any = {"configurable": {"thread_id": "s15"}}

    namespaces: list[tuple[str, ...]] = []
    for step_input in ({"topic": "t", "log": []}, Command(resume="one"), Command(resume="two")):
        for namespace, _ in graph.stream(step_input, config, stream_mode="updates", subgraphs=True):
            if namespace:
                namespaces.append(namespace)

    prefixes = {ns[0].split(":")[0] for ns in namespaces}
    assert prefixes == {"first", "second"}
    assert len({ns[0] for ns in namespaces}) == 2
    assert graph.get_state(config).values["log"] == ["t=one", "t=two"]


def test_s20_compiled_graph_exports_mermaid() -> None:
    graph = build_parent(build_child(restrict=True))
    flat = graph.get_graph().draw_mermaid()
    nested = graph.get_graph(xray=True).draw_mermaid()
    assert "child" in flat and flat.startswith("---")
    assert "work" in nested
