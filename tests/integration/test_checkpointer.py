"""Checkpoints on PostgreSQL (ADR-0033 points 4, 6 and 8): encrypted, strict, no pickle."""

import logging
from typing import Annotated, Any, TypedDict

import psycopg
import pytest
from langgraph.checkpoint.serde.encrypted import EncryptedSerializer
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import BaseModel

from orchestrator.persistence.checkpointer import (
    KEY_VARIABLE,
    build_serializer,
    open_async_checkpointer,
    open_checkpointer,
)
from tests.conftest import run_async

KEY = b"0123456789abcdef0123456789abcdef"  # 32 bytes, for tests only
MARKER = "TOP-SECRET-MARKER-123"


class Plan(BaseModel):
    title: str


# ---------------------------------------------------------------- the serialiser
def test_the_serialiser_encrypts_what_it_writes() -> None:
    serde = build_serializer(KEY)
    kind, blob = serde.dumps_typed({"secret": MARKER})
    assert kind.endswith("+aes")
    assert MARKER.encode() not in blob
    assert serde.loads_typed((kind, blob)) == {"secret": MARKER}


def test_a_different_key_cannot_read_what_was_written() -> None:
    kind, blob = build_serializer(KEY).dumps_typed({"secret": MARKER})
    other = build_serializer(b"fedcba9876543210fedcba9876543210")
    with pytest.raises(ValueError):
        other.loads_typed((kind, blob))


def test_the_key_comes_from_the_environment_and_must_be_a_valid_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(KEY_VARIABLE, raising=False)
    with pytest.raises(ValueError, match=KEY_VARIABLE):
        build_serializer()
    monkeypatch.setenv(KEY_VARIABLE, "too-short")
    with pytest.raises(ValueError, match="16, 24, or 32"):
        build_serializer()
    monkeypatch.setenv(KEY_VARIABLE, KEY.decode())
    kind, _ = build_serializer().dumps_typed({"a": 1})
    assert kind.endswith("+aes")


def test_pickle_fallback_is_off() -> None:
    serde = build_serializer(KEY)
    assert isinstance(serde, EncryptedSerializer) and isinstance(serde.serde, JsonPlusSerializer)
    assert serde.serde.pickle_fallback is False

    class NotSerialisable:
        pass

    with pytest.raises(TypeError):
        serde.dumps_typed(NotSerialisable())


def test_strict_msgpack_returns_an_unregistered_object_as_a_plain_dict(
    caplog: pytest.LogCaptureFixture,
) -> None:
    serde = build_serializer(KEY)
    with caplog.at_level(logging.WARNING):
        restored = serde.loads_typed(serde.dumps_typed(Plan(title="t")))
    assert restored == {"title": "t"} and not isinstance(restored, Plan)
    assert "Blocked deserialization" in caplog.text


def test_the_default_library_serialiser_would_have_rebuilt_the_object() -> None:
    """The reason strict mode matters: without it a stored type name is imported and run."""
    permissive = JsonPlusSerializer(allowed_msgpack_modules=True)
    assert permissive.loads_typed(permissive.dumps_typed(Plan(title="t"))) == Plan(title="t")


# ---------------------------------------------------------------- the checkpointer
def merge_notes(left: dict[str, str], right: dict[str, str]) -> dict[str, str]:
    return {**left, **right}


class State(TypedDict):
    stage: str
    notes: Annotated[dict[str, str], merge_notes]


def build_graph(saver: Any) -> Any:
    def first(state: State) -> dict[str, Any]:
        return {"stage": "first", "notes": {"secret": MARKER}}

    def second(state: State) -> dict[str, Any]:
        answer = interrupt("go on?")
        return {"stage": f"second:{answer}"}

    builder = StateGraph(State)
    builder.add_node("first", first)
    builder.add_node("second", second)
    builder.add_edge(START, "first")
    builder.add_edge("first", "second")
    builder.add_edge("second", END)
    return builder.compile(checkpointer=saver)


@pytest.mark.postgres
def test_a_run_pauses_and_resumes_through_the_encrypting_checkpointer(
    pg_dsn: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(KEY_VARIABLE, KEY.decode())
    config: Any = {"configurable": {"thread_id": "t1"}}
    with open_checkpointer(pg_dsn) as saver:
        graph = build_graph(saver)
        paused = graph.invoke({"stage": "", "notes": {}}, config)
        assert paused["__interrupt__"][0].value == "go on?"

    with open_checkpointer(pg_dsn, setup=False) as other:  # a new connection, as after a restart
        finished = build_graph(other).invoke(Command(resume="yes"), config)
    assert finished["stage"] == "second:yes" and finished["notes"] == {"secret": MARKER}


@pytest.mark.postgres
def test_what_the_checkpointer_stores_is_encrypted_apart_from_plain_state_values(
    pg_dsn: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(KEY_VARIABLE, KEY.decode())
    with open_checkpointer(pg_dsn) as saver:
        build_graph(saver).invoke({"stage": "", "notes": {}}, {"configurable": {"thread_id": "t"}})
    with psycopg.connect(pg_dsn) as conn:
        types = [r[0] for r in conn.execute("SELECT type FROM checkpoint_blobs")]
        types += [r[0] for r in conn.execute("SELECT type FROM checkpoint_writes")]
        blobs = [bytes(r[0]) for r in conn.execute("SELECT blob FROM checkpoint_blobs")]
        blobs += [bytes(r[0]) for r in conn.execute("SELECT blob FROM checkpoint_writes")]
        inline = [str(r[0]) for r in conn.execute("SELECT checkpoint FROM checkpoints")]
    assert types and all(t.endswith("+aes") for t in types)
    assert not any(MARKER.encode() in blob for blob in blobs), "the dict value is encrypted"
    assert not any(MARKER in text for text in inline)
    assert any("first" in text for text in inline), "a plain string such as the stage is not"


@pytest.mark.postgres
def test_the_checkpointer_connection_commits_its_own_setup(
    pg_dsn: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The checkpointer's migrations need autocommit; another connection must see the tables."""
    monkeypatch.setenv(KEY_VARIABLE, KEY.decode())
    with open_checkpointer(pg_dsn), psycopg.connect(pg_dsn) as other:
        tables = {
            r[0]
            for r in other.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
            )
        }
    assert {"checkpoints", "checkpoint_blobs", "checkpoint_writes"} <= tables


@pytest.mark.postgres
def test_the_async_checkpointer_works_the_same_way(
    pg_dsn: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(KEY_VARIABLE, KEY.decode())
    config: Any = {"configurable": {"thread_id": "async"}}

    async def go() -> dict[str, Any]:
        async with open_async_checkpointer(pg_dsn) as saver:
            graph = build_graph(saver)
            paused = await graph.ainvoke({"stage": "", "notes": {}}, config)
            assert paused["__interrupt__"][0].value == "go on?"
        async with open_async_checkpointer(pg_dsn, setup=False) as other:
            result: dict[str, Any] = await build_graph(other).ainvoke(Command(resume="yes"), config)
            return result

    assert run_async(go())["stage"] == "second:yes"
    with psycopg.connect(pg_dsn) as conn:
        assert all(r[0].endswith("+aes") for r in conn.execute("SELECT type FROM checkpoint_blobs"))
