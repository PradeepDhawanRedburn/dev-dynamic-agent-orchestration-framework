"""No state model holds free text (ADR-0018, ADR-0033 points 4 and 7)."""

import importlib
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel

from orchestrator.contracts import AgentStatus, Identifier
from orchestrator.governance.policy import STATE_MODELS, free_text_fields, state_model


class Colour(StrEnum):
    RED = "red"


class Reference(BaseModel):
    task_id: Identifier
    agent_id: Identifier
    status: AgentStatus


class GoodState(TypedDict):
    project_id: Identifier
    stage: Literal["intake", "plan", "done"]
    colour: Colour
    attempts: int
    paused: bool
    refs: list[Reference]
    outcomes: dict[Identifier, AgentStatus]
    owner: Identifier | None
    counters: dict[Identifier, int]
    pairs: tuple[Identifier, int]


def test_identifiers_statuses_and_counters_are_allowed() -> None:
    assert free_text_fields(GoodState) == []


def test_a_plain_string_is_free_text() -> None:
    class Bad(TypedDict):
        raw_request: str

    assert len(free_text_fields(Bad)) == 1
    assert "raw_request" in free_text_fields(Bad)[0]


def test_a_string_with_only_a_length_limit_is_still_free_text() -> None:
    class Bad(BaseModel):
        note: Annotated[str, "short"]

    assert free_text_fields(Bad)


def test_free_text_hidden_in_a_container_or_a_union_is_found() -> None:
    class Bad(TypedDict):
        answers: list[str]
        by_task: dict[Identifier, str]
        maybe: str | None
        outcomes: dict[str, int]

    problems = free_text_fields(Bad)
    assert [p.split(":")[0] for p in problems] == ["answers", "by_task", "maybe", "outcomes"]


def test_free_text_in_a_nested_model_is_found_and_named() -> None:
    class Inner(BaseModel):
        task_id: Identifier
        comment: str

    class Outer(TypedDict):
        inner: Inner

    (problem,) = free_text_fields(Outer)
    assert problem.startswith("inner: Inner.comment: ")


def test_numbers_other_than_counters_and_untyped_content_are_refused() -> None:
    class Bad(TypedDict):
        cost: Decimal
        ratio: float
        anything: Any
        loose: dict  # type: ignore[type-arg]
        bag: list  # type: ignore[type-arg]

    assert [p.split(":")[0] for p in free_text_fields(Bad)] == [
        "cost",
        "ratio",
        "anything",
        "loose",
        "bag",
    ]


class Node(BaseModel):
    task_id: Identifier
    children: list["Node"] = []


def test_a_self_referencing_model_does_not_loop_forever() -> None:
    assert free_text_fields(Node) == []


def test_every_registered_state_model_is_free_of_free_text() -> None:
    importlib.import_module("orchestrator.graph.state")  # registers the graph's state models
    offenders = {model.__name__: free_text_fields(model) for model in STATE_MODELS}
    assert {name: problems for name, problems in offenders.items() if problems} == {}


def test_the_decorator_registers_a_model_and_returns_it_unchanged() -> None:
    before = len(STATE_MODELS)

    @state_model
    class Registered(TypedDict):
        project_id: Identifier

    try:
        assert len(STATE_MODELS) == before + 1 and STATE_MODELS[-1] is Registered
    finally:
        STATE_MODELS.remove(Registered)


def test_an_identifier_rejects_prose() -> None:
    from pydantic import TypeAdapter, ValidationError

    adapter: TypeAdapter[str] = TypeAdapter(Identifier)
    assert adapter.validate_python("prj_ab12/ws_1") == "prj_ab12/ws_1"
    for prose in ("Please deploy this to production", "", " leading space", "a" * 200):
        try:
            adapter.validate_python(prose)
        except ValidationError:
            continue
        raise AssertionError(f"{prose!r} was accepted as an identifier")
