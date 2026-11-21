# ADR-0006: Agents hold no consequential tools; changes reach the estate as pull requests

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

A compromised or mistaken agent must not be able to change anything.

## Decision

No tool that changes state outside the platform is ever granted to an agent. A proposed change is emitted as a typed proposal, approved by a human, and carried out by a deterministic executor with its own narrow identity. For code and infrastructure the executor opens a pull request; people merge; the existing pipeline applies.

## Consequences

- Prompt injection cannot cause an external change.
- The platform is advisory by construction.
- Every change inherits the team's normal review and pipeline controls.

## Alternatives considered

- Granting write tools with per-call approval: rejected. One approval mistake becomes an incident.
