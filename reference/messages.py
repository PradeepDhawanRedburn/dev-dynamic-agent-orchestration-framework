"""Typed message envelope. Every cross-process message uses it."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from contracts import Contract, new_id, utcnow

MessageType = Literal[
    "command.start_project", "command.cancel", "task.assigned", "status.changed",
    "agent.requested", "agent.created", "result.submitted", "review.decided",
    "escalation.raised", "budget.reserved", "budget.warning", "budget.exceeded",
    "agent.retired",
]


class Envelope(Contract):
    message_id: str = Field(default_factory=lambda: new_id("msg"))
    type: MessageType
    schema_version: str = "1.0"
    project_id: str                      # also the Service Bus session id
    correlation_id: str                  # one per project run
    causation_id: str | None = None      # message_id that caused this one
    idempotency_key: str                 # stable for a logical action, reused on retry
    sender: str
    recipient: str
    occurred_at: datetime = Field(default_factory=utcnow)
    payload: dict


def child_of(parent: Envelope, *, type: MessageType, sender: str, recipient: str,
             idempotency_key: str, payload: dict) -> Envelope:
    return Envelope(type=type, project_id=parent.project_id,
                    correlation_id=parent.correlation_id, causation_id=parent.message_id,
                    idempotency_key=idempotency_key, sender=sender, recipient=recipient,
                    payload=payload)
