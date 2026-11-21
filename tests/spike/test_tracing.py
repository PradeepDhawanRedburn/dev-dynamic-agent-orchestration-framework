"""S-13 (without Application Insights) and S-21: what the Foundry tracer emits, offline.

The tracer is attached to an in-memory OpenTelemetry exporter. Whether the spans arrive in
Application Insights is not tested here: that needs a Foundry project's connection string.
"""

import json
from collections.abc import Iterator
from typing import Any

import pytest
from langchain.agents import create_agent
from langchain_azure_ai.callbacks.tracers.inference_tracing import AzureAIOpenTelemetryTracer
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from typing_extensions import TypedDict

from tests.spike.support import ScriptedChatModel

MARKER = "SECRET-PROMPT-TEXT"
METADATA = {"project_id": "p-1", "task_id": "t-1", "gen_ai.custom": "x", "agent_id": "lead-1"}


@pytest.fixture(scope="module")
def exporter() -> Iterator[InMemorySpanExporter]:
    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(memory))
    trace.set_tracer_provider(provider)
    yield memory
    memory.clear()


class State(TypedDict):
    messages: list[Any]


def run_nested_graph(exporter: InMemorySpanExporter, *, record_content: bool) -> list[ReadableSpan]:
    exporter.clear()
    agent = create_agent(
        ScriptedChatModel(script=[AIMessage(f"reply {MARKER}")]), tools=[], name="specialist"
    )
    lead = StateGraph(State)
    lead.add_node("work", agent)
    lead.add_edge(START, "work")
    lead.add_edge("work", END)
    parent = StateGraph(State)
    parent.add_node("lead", lead.compile())
    parent.add_edge(START, "lead")
    parent.add_edge("lead", END)

    tracer = AzureAIOpenTelemetryTracer(
        auto_configure_azure_monitor=False,
        enable_content_recording=record_content,
        trace_all_langgraph_nodes=True,
        name="spike",
    )
    parent.compile().invoke(
        {"messages": [HumanMessage(f"hello {MARKER}")]},
        {"callbacks": [tracer], "metadata": METADATA, "configurable": {"thread_id": "th-1"}},
    )
    return list(exporter.get_finished_spans())


def attributes(span: ReadableSpan) -> dict[str, Any]:
    return dict(span.attributes or {})


def test_s13_nested_subgraphs_and_a_model_call_produce_one_connected_trace(
    exporter: InMemorySpanExporter,
) -> None:
    spans = run_nested_graph(exporter, record_content=True)
    by_id = {s.context.span_id: s for s in spans}
    roots = [s for s in spans if s.parent is None]
    assert len(roots) == 1 and roots[0].name == "invoke_agent spike"
    assert all(s.parent is None or s.parent.span_id in by_id for s in spans)
    assert len({s.context.trace_id for s in spans}) == 1
    names = [s.name for s in spans]
    assert "chat" in names and names.count("invoke_agent lead") == 2


def test_s21_arbitrary_metadata_keys_are_not_copied_to_spans(
    exporter: InMemorySpanExporter,
) -> None:
    spans = run_nested_graph(exporter, record_content=True)
    everything = json.dumps([attributes(s) for s in spans], default=str)
    assert "p-1" not in everything and "t-1" not in everything
    assert not any(
        k in {"project_id", "task_id", "metadata.project_id"} for s in spans for k in attributes(s)
    )


def test_s21_only_gen_ai_prefixed_keys_are_carried_and_only_on_agent_spans(
    exporter: InMemorySpanExporter,
) -> None:
    spans = run_nested_graph(exporter, record_content=True)
    agent_spans = [s for s in spans if s.name.startswith("invoke_agent")]
    chat_spans = [s for s in spans if s.name == "chat"]
    assert all(attributes(s).get("gen_ai.custom") == "x" for s in agent_spans)
    assert chat_spans and all("gen_ai.custom" not in attributes(s) for s in chat_spans)
    assert all("gen_ai.agent.id" not in attributes(s) for s in chat_spans)


def test_s21_content_is_recorded_by_default_and_can_be_switched_off_per_tracer(
    exporter: InMemorySpanExporter,
) -> None:
    shown = json.dumps([attributes(s) for s in run_nested_graph(exporter, record_content=True)])
    assert MARKER in shown
    hidden = json.dumps([attributes(s) for s in run_nested_graph(exporter, record_content=False)])
    assert MARKER not in hidden
