# ADR-0018: State holds references; consolidation is staged

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

The draft state carried full results, evidence and audit events and rewrote them at every checkpoint. Consolidation put every result into one prompt.

## Decision

Graph state carries ids and statuses. Results, evidence and audit events live in their stores. Each Lead writes a bounded summary with claim ids; the Head of Delivery works from summaries and pulls full results only for conflicts.

## Consequences

- Checkpoints stay small.
- Nodes read from repositories, so repository reads must be fast and idempotent.
- The reference draft does not do this yet.
