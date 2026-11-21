# ADR-0019: Lean first-release platform

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

The first design included two execution modes, Service Bus with an outbox, Redis, AI Search and self-hosted LangSmith from day one.

## Decision

The first release uses AKS, PostgreSQL, Foundry model deployments, Blob Storage, Key Vault, Application Insights and a sandbox node pool. Each further service is added only when a measurement shows the need, by a new ADR.

## Consequences

- Less to build and operate before anything is proven.
- A shared store for guardrail counters is required before running more than one replica.
