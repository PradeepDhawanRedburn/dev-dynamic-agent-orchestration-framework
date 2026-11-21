# ADR-0007: Five functions and ten roles

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

The first design copied a human software department. Hierarchy is costly for agents: each layer paraphrases the one above, adding cost and losing meaning. Nobody owned the problem or what the organisation learns.

## Decision

Organise around Define, Deliver, Assure, Control and Learn. Ten roles: Product Manager, CTO Agent, Head of Delivery, Lead, Tester, Reviewer, Guardrail Manager, Delivery Controller, Recruiter, Knowledge Steward. Lead and Tester have one profile per domain. No function checks its own work. The human's request and success criteria travel verbatim to every agent.

## Consequences

- A new domain is a new profile, not a reorganisation.
- Supersedes the eight-agent and sixteen-agent organisations of earlier revisions.
- Reference code still uses older role names until WP-02.

## Alternatives considered

- Keep the department model with more roles: rejected as slower and costlier per assignment.
