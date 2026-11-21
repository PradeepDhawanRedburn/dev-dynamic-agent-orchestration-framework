# ADR-0022: Assignment scope is technology only, for now

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

All four Lead profiles are engineering roles. The architect proposed adding a Business and
Research profile so that business assignments have an owner. The repository owner decided to
start with technology only and involve the business later.

## Decision

The platform accepts technology assignments only. Lead profiles are Data, Software, DevOps and
Security. A request that is not a technology assignment is declined at intake by the Product
Manager, with the reason.

The Business and Research profile stays in `agents/profiles/` marked Deferred and is not loaded.

## Consequences

- "Domain-agnostic" means any technology topic.
- Adding business assignments later needs a new ADR, a `LeadRole` value, a standards library and evaluation data. It needs no change to the graph or the roles (ADR-0007).
- A technology assignment may still include commercial facts, such as vendor pricing, as evidence.

## Alternatives considered

- Technology and business from the start, with a fifth Lead profile: the architect's recommendation; not chosen for now.
