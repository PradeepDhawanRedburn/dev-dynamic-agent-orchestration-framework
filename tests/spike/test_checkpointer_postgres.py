"""S-08 (local part), S-17, S-22: the PostgreSQL checkpointer against a real PostgreSQL server."""

from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg
import pytest
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.encrypted import EncryptedSerializer
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from psycopg.rows import dict_row
from pydantic import BaseModel
from typing_extensions import TypedDict

from tests.spike.conftest import run_async
from tests.spike.test_graph_interrupts import build_supervisor

pytestmark = pytest.mark.postgres

MARKER = "TOP-SECRET-MARKER-123"
TEST_KEY = b"0123456789abcdef0123456789abcdef"  # 32 bytes; test-only, never a real key


@contextmanager
def saver_for(dsn: str, serde: Any | None = None) -> Iterator[PostgresSaver]:
    with psycopg.connect(dsn, autocommit=True, row_factory=dict_row) as conn:  # type: ignore[arg-type]
        saver = PostgresSaver(conn, serde=serde)  # type: ignore[arg-type]
        saver.setup()
        yield saver


def table_names(dsn: str) -> set[str]:
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            "select table_name from information_schema.tables where table_schema = 'public'"
        ).fetchall()
    return {row[0] for row in rows}


def test_s08_async_saver_setup_creates_tables_and_is_repeatable(pg_dsn: str) -> None:
    async def go() -> None:
        async with AsyncPostgresSaver.from_conn_string(pg_dsn) as saver:
            await saver.setup()
            await saver.setup()

    run_async(go())
    assert {"checkpoints", "checkpoint_blobs", "checkpoint_writes", "checkpoint_migrations"} <= (
        table_names(pg_dsn)
    )


@pytest.mark.skip(reason="could not test: needs Azure Database for PostgreSQL with Entra auth")
def test_s08_entra_authentication_against_azure_postgresql() -> None:
    raise AssertionError("not runnable without an Azure Database for PostgreSQL server")


def test_s22_decision_can_be_linked_to_state_and_survives_a_new_connection(pg_dsn: str) -> None:
    config: Any = {"configurable": {"thread_id": "s22-pg"}}
    with saver_for(pg_dsn) as saver:
        graph = build_supervisor(Counter(), [], checkpointer=saver)
        graph.invoke({"outcomes": {}}, config)
        decided_on = graph.get_state(config).config["configurable"]["checkpoint_id"]

    with saver_for(pg_dsn) as other:
        graph = build_supervisor(Counter(), [], checkpointer=other)
        graph.invoke(Command(resume={"B": "postgres"}), config)
        history = list(graph.get_state_history(config))
        by_id = {s.config["configurable"]["checkpoint_id"]: s for s in history}
        assert decided_on in by_id
        assert by_id[decided_on].values["outcomes"]["B"]["status"] == "decision_needed"
        assert history[0].values["outcomes"]["B"]["status"] == "done"


class Secret(TypedDict):
    text: str
    nested: dict[str, Any]
    items: list[str]


def run_secret_graph(saver: PostgresSaver, thread: str) -> Any:
    def write(_: Secret) -> dict[str, Any]:
        return {"text": MARKER, "nested": {"k": MARKER}, "items": [MARKER]}

    def wait(_: Secret) -> dict[str, Any]:
        interrupt("hold")
        return {}

    builder = StateGraph(Secret)
    builder.add_node("write", write)
    builder.add_node("wait", wait)
    builder.add_edge(START, "write")
    builder.add_edge("write", "wait")
    builder.add_edge("wait", END)
    graph = builder.compile(checkpointer=saver)
    config: Any = {"configurable": {"thread_id": thread}}
    graph.invoke({"text": "", "nested": {}, "items": []}, config)
    return graph, config


def where_marker_appears(dsn: str) -> set[str]:
    found: set[str] = set()
    needle = MARKER.encode()
    with psycopg.connect(dsn) as conn:
        for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
            for (row,) in conn.execute(f"select t::text from {table} t").fetchall():  # noqa: S608
                if needle in row.encode(errors="ignore"):
                    found.add(table)
        for (blob,) in conn.execute("select blob from checkpoint_blobs where blob is not null"):
            if needle in bytes(blob):
                found.add("checkpoint_blobs.blob")
        for (blob,) in conn.execute("select blob from checkpoint_writes"):
            if needle in bytes(blob):
                found.add("checkpoint_writes.blob")
    return found


def test_s17_without_encryption_the_marker_is_readable(pg_dsn: str) -> None:
    with saver_for(pg_dsn) as saver:
        run_secret_graph(saver, "plain")
    found = where_marker_appears(pg_dsn)
    print("PLAINTEXT marker found in:", sorted(found))
    assert found


def test_s17_encrypted_serialiser_works_with_the_postgres_checkpointer(
    pg_dsn: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LANGGRAPH_AES_KEY", TEST_KEY.decode())
    serde = EncryptedSerializer.from_pycryptodome_aes()
    with saver_for(pg_dsn, serde=serde) as saver:
        graph, config = run_secret_graph(saver, "enc")
        resumed = graph.invoke(Command(resume="go"), config)
        assert resumed["items"] == [MARKER]
        types = [
            row[0] for row in psycopg.connect(pg_dsn).execute("select type from checkpoint_blobs")
        ]
        assert any("+aes" in t for t in types)
        with psycopg.connect(pg_dsn) as conn:
            inline = [
                cp["channel_values"] for (cp,) in conn.execute("select checkpoint from checkpoints")
            ]
    # Observed: strings, numbers, booleans and None are kept inline in the checkpoint JSON and are
    # NOT encrypted. Dicts, lists and objects go to the blob tables and are.
    assert any(values.get("text") == MARKER for values in inline)
    assert not any("nested" in values or "items" in values for values in inline)
    assert where_marker_appears(pg_dsn) == {"checkpoints"}


def test_s17_a_different_key_cannot_read_the_checkpoints(pg_dsn: str) -> None:
    writer = EncryptedSerializer.from_pycryptodome_aes(key=TEST_KEY)
    with saver_for(pg_dsn, serde=writer) as saver:
        _, config = run_secret_graph(saver, "key")

    reader = EncryptedSerializer.from_pycryptodome_aes(key=b"fedcba9876543210fedcba9876543210")
    with saver_for(pg_dsn, serde=reader) as other:
        graph = StateGraph(Secret)
        graph.add_node("n", lambda s: s)
        graph.add_edge(START, "n")
        with pytest.raises(ValueError):
            graph.compile(checkpointer=other).get_state(config)


class Plan(BaseModel):
    title: str


class WithModel(TypedDict):
    plan: Plan


def serialiser_for(mode: str) -> JsonPlusSerializer:
    if mode == "default":
        return JsonPlusSerializer()
    if mode == "strict":
        return JsonPlusSerializer(allowed_msgpack_modules=[])
    return JsonPlusSerializer(allowed_msgpack_modules=[(Plan.__module__, "Plan")])


@pytest.mark.parametrize("mode", ["default", "strict", "allow_listed"])
def test_s17_pydantic_object_in_state_under_each_deserialisation_mode(
    pg_dsn: str, mode: str
) -> None:
    """Informational: what comes back for a Pydantic model held in graph state."""
    builder = StateGraph(WithModel)
    builder.add_node("make", lambda _: {"plan": Plan(title="t")})
    builder.add_edge(START, "make")
    builder.add_edge("make", END)
    config: Any = {"configurable": {"thread_id": f"model-{mode}"}}
    with saver_for(pg_dsn, serde=serialiser_for(mode)) as saver:
        graph = builder.compile(checkpointer=saver)
        graph.invoke({"plan": Plan(title="")}, config)
        loaded = graph.get_state(config).values["plan"]
    expected: dict[str, Any] = {
        "default": Plan(title="t"),
        "strict": {"title": "t"},  # blocked by the allow-list: silently a dict, with a warning
        "allow_listed": Plan(title="t"),
    }
    assert loaded == expected[mode]
    assert type(loaded) is type(expected[mode])
