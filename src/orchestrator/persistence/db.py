"""Connection pool for the PostgreSQL stores.

Rows come back as dicts. Pass `role` to run every connection as that role (the stores run as
`orchestrator_app`, which can append to the audit log but never change it)."""

from typing import Any

from psycopg import Connection, sql
from psycopg.rows import DictRow, dict_row
from psycopg_pool import ConnectionPool

type Pool = ConnectionPool[Connection[DictRow]]


def open_pool(dsn: str, *, min_size: int = 1, max_size: int = 10, role: str | None = None) -> Pool:
    def configure(conn: Connection[Any]) -> None:
        if role is not None:
            conn.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
        conn.commit()  # leave the connection idle, as the pool requires

    pool: Pool = ConnectionPool(
        dsn,
        min_size=min_size,
        max_size=max_size,
        kwargs={"row_factory": dict_row},
        configure=configure,
        open=False,
    )
    pool.open(wait=True, timeout=30)
    return pool
