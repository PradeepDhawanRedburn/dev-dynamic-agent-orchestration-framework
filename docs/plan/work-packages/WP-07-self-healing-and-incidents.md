# WP-07: Self-healing and the incident gate

- **Status:** Not started
- **Depends on:** WP-05

## Goal

Routine faults heal by runbook for every agent, and exhausted runbooks reach a human with clear options.

## Read first

- ADR-0015
- reference/resilience.py

## Tasks

1. Wrap tool calls and every permanent agent's model calls in the self-healer.
2. Implement the probe, backoff, credential refresh and switch-to-alternate actions against real endpoints.
3. Raise an incident gate at the supervisor with the four options, and act on the answer.
4. Record every incident, healed or not.

## Acceptance criteria

- [ ] Fault-injection tests cover each fault kind in the runbook table.
- [ ] An unknown fault escalates at once with no remediation attempted (tested).
- [ ] An operation is never repeated without its idempotency key (tested).

## Out of scope

Infrastructure changes of any kind.
