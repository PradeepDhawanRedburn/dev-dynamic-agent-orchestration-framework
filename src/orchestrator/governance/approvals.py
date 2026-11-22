"""The decision register: one row per decision, human or code.

Specified in docs/governance/traceability-and-decisions.md. Part of the audit store: rows are
written once and never changed. The rules the model enforces, repeated by the PostgreSQL table as
CHECK constraints:

- A human decision names the person and the role. Their identity is verified by the interaction
  API before anything is written here (WP-09).
- An agent's recommendation lives on the card as a recommendation. It is never a decision. The
  one thing an agent may decide is the answer to another agent's question, recorded as such.
- A timeout is a timeout, with the default that was taken. It is never recorded as approval.
- An override is its own row. It names the decision it overrides and gives the reason (ADR-0032).
"""

import hashlib
import json
import threading
from datetime import datetime
from typing import Literal, Protocol, Self

from pydantic import Field, computed_field, model_validator

from orchestrator.contracts import Contract, new_id, utcnow

DecisionType = Literal[
    "answer_to_question",
    "override",
    "choose_option",
    "approve_requirement",
    "approve_plan",
    "change_request",
    "budget_overrun",
    "resume_agent",
    "terminate_agent",
    "incident",
    "accept_result",
    # Decisions made by code that change an outcome are recorded too.
    "evidence_gate_rejection",
    "budget_refusal",
    "guardrail_suspension",
    "tier_assignment",
    "consultation",
]
DecidedByKind = Literal["human", "rule", "agent"]
Outcome = Literal[
    "approved",
    "rejected",
    "chosen",
    "answered",
    "changes_requested",
    "timeout",
    "overridden",
    "applied",
]
TIMEOUT_RULE = "deadline_expired"


class DecisionCard(Contract):
    """What the decider was shown."""

    question: str = Field(min_length=1)
    options: list[str] = []
    recommendation: str | None = None
    recommended_by: str | None = Field(
        default=None, description="Agent id or role that recommended; a recommendation only"
    )
    evidence_ids: list[str] = []
    default: str | None = Field(default=None, description="What happens if nobody answers")
    deadline: datetime | None = None


def card_hash(card: DecisionCard) -> str:
    canonical = json.dumps(card.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class DecisionRecord(Contract):
    decision_id: str = Field(default_factory=lambda: new_id("dec"))
    project_id: str
    decided_at: datetime = Field(default_factory=utcnow)
    type: DecisionType
    decided_by_kind: DecidedByKind
    decided_by: str = Field(
        min_length=1, description="Entra object id, rule name, or agent id, by kind"
    )
    decided_by_role: str | None = None
    card: DecisionCard
    outcome: Outcome
    comment: str = ""
    default_taken: str | None = None
    overrides_decision_id: str | None = None
    checkpoint_id: str | None = Field(default=None, description="The state it was decided on")
    baseline_version: int | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def card_hash(self) -> str:
        return card_hash(self.card)

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if self.decided_by_kind == "human" and not self.decided_by_role:
            raise ValueError("a human decision names the person's role")
        if self.decided_by_kind == "agent" and self.type != "answer_to_question":
            raise ValueError("an agent's recommendation is not a decision (ADR-0008)")
        if self.outcome == "timeout" and (self.decided_by_kind != "rule" or not self.default_taken):
            raise ValueError("a timeout is recorded by a rule, with the default that was taken")
        if self.decided_by == TIMEOUT_RULE and self.outcome != "timeout":
            raise ValueError("a timeout is never recorded as anything but a timeout")
        if self.type == "override" and (
            self.decided_by_kind != "human"
            or not self.overrides_decision_id
            or not self.comment.strip()
        ):
            raise ValueError(
                "an override is a person's, names what it overrides, and gives a reason"
            )
        return self


class DecisionConflict(ValueError):
    """A different decision was offered under an id that already exists."""


class DecisionRegister(Protocol):
    def record(self, decision: DecisionRecord) -> DecisionRecord:
        """Store a decision. Recording the same decision again changes nothing."""
        ...

    def get(self, decision_id: str) -> DecisionRecord: ...
    def for_project(self, project_id: str) -> list[DecisionRecord]: ...
    def add_followup(self, decision_id: str, audit_event_id: str) -> None:
        """Link the audit event that followed from the decision."""
        ...

    def followups(self, decision_id: str) -> list[str]: ...


class InMemoryDecisionRegister:
    def __init__(self) -> None:
        self._decisions: dict[str, DecisionRecord] = {}
        self._followups: dict[str, list[str]] = {}
        self._lock = threading.Lock()

    def record(self, decision: DecisionRecord) -> DecisionRecord:
        with self._lock:
            existing = self._decisions.get(decision.decision_id)
            if existing is not None:
                if existing != decision.model_copy(deep=True):
                    raise DecisionConflict(f"{decision.decision_id} already exists")
                return existing.model_copy(deep=True)
            if (
                decision.overrides_decision_id is not None
                and decision.overrides_decision_id not in self._decisions
            ):
                raise KeyError(decision.overrides_decision_id)
            stored = decision.model_copy(deep=True)
            self._decisions[decision.decision_id] = stored
            return stored.model_copy(deep=True)

    def get(self, decision_id: str) -> DecisionRecord:
        return self._decisions[decision_id].model_copy(deep=True)

    def for_project(self, project_id: str) -> list[DecisionRecord]:
        found = [
            d.model_copy(deep=True)
            for d in self._decisions.values()
            if d.project_id == project_id
        ]
        return sorted(found, key=lambda d: d.decided_at)

    def add_followup(self, decision_id: str, audit_event_id: str) -> None:
        if decision_id not in self._decisions:
            raise KeyError(decision_id)
        links = self._followups.setdefault(decision_id, [])
        if audit_event_id not in links:
            links.append(audit_event_id)

    def followups(self, decision_id: str) -> list[str]:
        return list(self._followups.get(decision_id, []))
