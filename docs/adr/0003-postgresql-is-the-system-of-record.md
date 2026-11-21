# ADR-0003: PostgreSQL is the system of record

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

Workflow state, money and audit need transactions and a single source of truth.

## Decision

PostgreSQL holds LangGraph checkpoints, domain tables, the agent registry, the ledger and the audit log. Vector indexes are derived and can be rebuilt. A vector database is never the authoritative store for workflow state.

## Consequences

- A state change, its audit row and its outbound message can commit together.
- Any orchestrator replica can resume any project.
- Checkpoint write latency must be load-tested early.
