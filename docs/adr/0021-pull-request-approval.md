# ADR-0021: Human approval for opening a pull request

- **Status:** Proposed
- **Date:** 2026-11-21

## Context

Opening a pull request starts workflows, so it is not a no-op.

## Decision

Proposed: a human approves every pull request the platform opens. This may be relaxed only through earned autonomy (ADR-0023).

## Consequences

- Slower at first.
- Awaiting the owner's decision.

## Alternatives considered

- Automatic pull requests to an allow-list of repositories and non-protected branches.
