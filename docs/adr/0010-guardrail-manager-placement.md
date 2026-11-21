# ADR-0010: Guardrail Manager placement

- **Status:** Proposed
- **Date:** 2026-11-21

## Context

In Revision 1 the owner chose one Guardrail Manager per Lead, reporting to that Lead with direct escalation to a human. The architect's review found that this has each Guardrail Manager policing its own manager's agents, and leaves the permanent agents watched only by code.

## Decision

Proposed: one Guardrail Manager for the platform, reporting to the human security owner, covering temporary and permanent agents alike.

## Consequences

- More independent and fewer roles.
- Loses domain-specific judgement per Lead; the rule engine does not depend on it.
- Awaiting the owner's decision. WP-06 builds the rule engine either way and leaves the judgement step configurable.

## Alternatives considered

- One per Lead with direct escalation (the Revision 1 choice).
