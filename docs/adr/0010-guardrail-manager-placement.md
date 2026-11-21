# ADR-0010: Guardrail Manager placement

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

Two placements were considered: one Guardrail Manager per Lead, or one for the platform. The
architect recommended one for the platform, on the grounds that a per-Lead Guardrail Manager
polices its own manager's agents and leaves the permanent agents watched only by code. The
repository owner decided on one per Lead.

## Decision

Each Lead profile has its own Guardrail Manager. It reports to its Lead day to day and can
escalate directly to the human security owner without the Lead's consent. It watches the
specialists and the Tester working for that Lead, and the Lead's own requests to the Recruiter.

Three safeguards are mandatory because of the reporting line:

- The rule engine is platform-wide code. It suspends an agent without anyone's consent.
- A Lead can never resume or terminate a suspended agent. Only a named human can.
- Every suspension and every flag goes to the security owner, not only to the Lead.

Permanent agents (Product Manager, CTO Agent, Head of Delivery, Reviewer, Delivery Controller,
Recruiter, Knowledge Steward, and the Leads themselves) are covered by the platform-wide rule
engine and the human security owner, not by a Guardrail Manager.

## Consequences

- Guardrail judgement can use domain knowledge from the Lead's profile.
- One Guardrail Manager per Lead profile, so four at the start.
- No model-based judgement watches the permanent agents. This is a known gap, accepted for now; revisit after the proof of concept.
- `agents/guardrail-manager.agent.md` takes a domain profile like Lead and Tester.

## Alternatives considered

- One Guardrail Manager for the platform, reporting to the security owner: the architect's recommendation; not chosen.
