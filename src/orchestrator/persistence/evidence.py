"""Evidence store (ADR-0004): only the platform writes evidence, and an agent may cite only ids
that were issued to it. The record is immutable: saving the same evidence again changes nothing,
and saving different content under an existing id is an error.

`EvidenceStore` is the interface. The PostgreSQL version is in persistence/repositories.py; source
bodies will live in Blob Storage later, so only metadata and the bounded extract are stored here."""

from collections.abc import Iterable
from typing import Protocol

from orchestrator.contracts import Evidence


class EvidenceConflict(ValueError):
    """Different content was offered for an evidence id that already exists."""


class EvidenceStore(Protocol):
    def put(self, evidence: Evidence) -> None: ...
    def get(self, evidence_id: str) -> Evidence: ...
    def for_agent(self, project_id: str, agent_id: str) -> list[Evidence]: ...
    def not_issued_to(
        self, project_id: str, agent_id: str, evidence_ids: Iterable[str]
    ) -> set[str]:
        """The ids among `evidence_ids` that were not issued to this agent in this project."""
        ...


class InMemoryEvidenceStore:
    def __init__(self) -> None:
        self._items: dict[str, Evidence] = {}

    def put(self, evidence: Evidence) -> None:
        existing = self._items.get(evidence.evidence_id)
        if existing is None:
            self._items[evidence.evidence_id] = evidence.model_copy(deep=True)
        elif existing != evidence.model_copy(deep=True):
            raise EvidenceConflict(f"{evidence.evidence_id} already exists with other content")

    def get(self, evidence_id: str) -> Evidence:
        return self._items[evidence_id].model_copy(deep=True)

    def for_agent(self, project_id: str, agent_id: str) -> list[Evidence]:
        return [
            e.model_copy(deep=True)
            for e in self._items.values()
            if e.project_id == project_id and e.captured_by_agent == agent_id
        ]

    def not_issued_to(
        self, project_id: str, agent_id: str, evidence_ids: Iterable[str]
    ) -> set[str]:
        issued = {e.evidence_id for e in self.for_agent(project_id, agent_id)}
        return {i for i in evidence_ids if i not in issued}
