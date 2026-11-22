"""Tool-call counters, shared between replicas so any of them enforces the same call limit.

`increment` is atomic and returns the new count. The gateway compares it with the grant's limit; a
call that is refused for being over the limit still counts, so a loop cannot probe the limit."""

import threading
from typing import Protocol


class ToolCallCounters(Protocol):
    def increment(self, agent_id: str, tool_name: str) -> int: ...
    def count(self, agent_id: str, tool_name: str) -> int: ...


class InMemoryToolCallCounters:
    def __init__(self) -> None:
        self._counts: dict[tuple[str, str], int] = {}
        self._lock = threading.Lock()

    def increment(self, agent_id: str, tool_name: str) -> int:
        with self._lock:
            key = (agent_id, tool_name)
            self._counts[key] = self._counts.get(key, 0) + 1
            return self._counts[key]

    def count(self, agent_id: str, tool_name: str) -> int:
        return self._counts.get((agent_id, tool_name), 0)
