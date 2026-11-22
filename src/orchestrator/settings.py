"""Settings read from the environment. Nothing secret lives here: keys and connection strings are
read where they are used and never stored in a settings object."""

import os
from collections.abc import Mapping
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

THREADS_VARIABLE = "ORCHESTRATOR_STORE_THREADS"
POOL_VARIABLE = "ORCHESTRATOR_STORE_POOL_SIZE"


class StoreSettings(BaseModel):
    """How async code reaches the synchronous stores (ADR-0034 points 1 and 3).

    `threads` is the number of worker threads the facade runs store calls on. The connection pool
    is sized to the same number, so a thread never waits for a connection another thread holds;
    `pool_size` may be raised above it, never lowered below it."""

    model_config = ConfigDict(frozen=True)

    threads: int = Field(default=8, ge=1, le=64)
    pool_size: int | None = Field(default=None, ge=1, le=256)

    @model_validator(mode="after")
    def _pool_covers_threads(self) -> Self:
        if self.pool_size is not None and self.pool_size < self.threads:
            raise ValueError("the pool must have at least as many connections as worker threads")
        return self

    @property
    def effective_pool_size(self) -> int:
        return self.pool_size if self.pool_size is not None else self.threads

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "StoreSettings":
        source = os.environ if env is None else env
        values: dict[str, int] = {}
        if source.get(THREADS_VARIABLE):
            values["threads"] = int(source[THREADS_VARIABLE])
        if source.get(POOL_VARIABLE):
            values["pool_size"] = int(source[POOL_VARIABLE])
        return cls(**values)
