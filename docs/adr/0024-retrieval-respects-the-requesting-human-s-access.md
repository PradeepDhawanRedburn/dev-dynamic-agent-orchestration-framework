# ADR-0024: Retrieval respects the requesting human's access rights

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

Agents read enterprise systems with a service identity. A deliverable could show a sponsor information they are not entitled to see.

## Decision

Retrieval is filtered to what the requesting human may see, and the deliverable's audience is checked against the same rights.

## Consequences

- Every enterprise read tool must accept and enforce the requester's identity.
- The most serious gap found in the architecture review; not yet designed in detail.
