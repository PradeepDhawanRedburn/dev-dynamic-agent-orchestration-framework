# ADR-0005: Budget is a ledger with reservations

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

No model should decide whether money is left.

## Decision

The maximum cost of a task is reserved against its workstream and project before it runs. The worker meters each model call and stops the agent at its limit. Settlement records what each run spent and is idempotent per reservation. Tasks share 60% of a workstream budget; 40% is held for revisions and re-staffing.

## Consequences

- A task cannot overspend its workstream or project.
- Retries cannot double-charge.
- The held-back share was found necessary in the dry run; tune it from real data.
