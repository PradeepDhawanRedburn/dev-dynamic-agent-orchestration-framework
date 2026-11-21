# ADR-0002: Specialists run as one parameterised worker launched with Send

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

The number and kind of specialists is known only at runtime.

## Decision

A single worker runtime builds a LangChain agent from an `AgentSpecification`. The Lead subgraph launches one per task with LangGraph `Send`. A durable mode behind messaging is deferred until a measurement requires it; the specification already carries an `execution_mode` field for it.

## Consequences

- One code path to test and secure.
- Parallelism, per-task input and timeouts come from LangGraph.
- Long or isolated tasks wait for the durable mode.

## Alternatives considered

- Independent durable executions for everything: rejected for the first release as too much to operate.
