"""LangGraph checkpoints on PostgreSQL, set up the way ADR-0033 requires.

- The serialiser encrypts with AES (key from `LANGGRAPH_AES_KEY`, which comes from Key Vault).
  This is defence in depth: strings, numbers and booleans held directly in state are stored
  unencrypted by this library (spike S-17). The control is that state holds identifiers, statuses
  and counters only (ADR-0018, ADR-0033 point 7); database encryption at rest covers the rest.
- Strict msgpack: only the library's safe types are rebuilt from a checkpoint. Anything else comes
  back as a plain dict, so a poisoned checkpoint cannot make the platform import and run code.
- Pickle fallback is never enabled.
- The connection is autocommit with dict rows; the checkpointer's own migrations use
  CREATE INDEX CONCURRENTLY, which cannot run in a transaction (spike S-08).

Set `LANGGRAPH_STRICT_MSGPACK=true` in the deployment as well, so any serialiser LangGraph builds
for itself is strict too. This module does not depend on it: it passes the setting explicitly.
"""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.encrypted import EncryptedSerializer
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from psycopg.rows import dict_row

KEY_VARIABLE = "LANGGRAPH_AES_KEY"


def build_serializer(key: bytes | None = None) -> EncryptedSerializer:
    """An encrypting, strict serialiser. Without `key` it reads LANGGRAPH_AES_KEY (16, 24 or 32
    bytes) and raises if that is missing or the wrong length."""
    inner = JsonPlusSerializer(pickle_fallback=False, allowed_msgpack_modules=None)
    if key is None:
        return EncryptedSerializer.from_pycryptodome_aes(serde=inner)
    return EncryptedSerializer.from_pycryptodome_aes(serde=inner, key=key)


@contextmanager
def open_checkpointer(dsn: str, *, setup: bool = True) -> Iterator[PostgresSaver]:
    with psycopg.connect(dsn, autocommit=True, prepare_threshold=0, row_factory=dict_row) as conn:
        saver = PostgresSaver(conn, serde=build_serializer())
        if setup:
            saver.setup()
        yield saver


@asynccontextmanager
async def open_async_checkpointer(
    dsn: str, *, setup: bool = True
) -> AsyncIterator[AsyncPostgresSaver]:
    """The checkpointer for async graph nodes (ADR-0033 point 2). The library opens this
    connection with autocommit and dict rows itself."""
    async with AsyncPostgresSaver.from_conn_string(dsn, serde=build_serializer()) as saver:
        if setup:
            await saver.setup()
        yield saver
