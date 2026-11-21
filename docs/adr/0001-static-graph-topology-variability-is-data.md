# ADR-0001: Static graph topology; variability is data

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

The platform must serve unrelated assignments without redesign, and every run must be auditable and testable ahead of time.

## Decision

The LangGraph topology is fixed and compiled. No node, edge or Python code is created at runtime. What varies per assignment is typed data: the plan, workstreams, agent specifications and tool grants.

## Consequences

- The graph that ran is the graph that was reviewed and tested.
- Checkpoints stay compatible within a release.
- A new kind of specialist is a new specification, not a deployment.
- Anything that cannot be expressed as data needs a release.

## Alternatives considered

- Runtime-created graph nodes: rejected. Topology becomes model-influenced and cannot be regression-tested.
