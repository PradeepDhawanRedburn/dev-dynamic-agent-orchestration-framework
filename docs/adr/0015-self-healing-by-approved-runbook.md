# ADR-0015: Self-healing by approved runbook

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

Agents are expected to identify and fix routine faults such as network loss, and to involve a human when needed.

## Decision

Every model and tool call runs through one routine. It classifies the fault, works through that fault's runbook (probe, retry with backoff, refresh credential, switch to an approved alternate), and retries the call after each successful step. When the runbook is exhausted, or the fault is unknown, it raises an incident and a human chooses: wait and retry, switch region, reduce scope, or cancel.

## Consequences

- Agents never restart services, change configuration or use unlisted endpoints.
- Operations must be idempotent because they may run several times.
- Healed faults are still recorded.
