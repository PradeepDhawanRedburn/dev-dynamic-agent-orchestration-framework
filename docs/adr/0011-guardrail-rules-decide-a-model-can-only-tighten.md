# ADR-0011: Guardrail rules decide; a model can only tighten; suspension is reversible

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

A model-based guardrail can be wrong or can itself be misled.

## Decision

A rule engine in code counts audit events per agent in real time and returns none, flag or suspend. The Guardrail Manager's model judges only what was flagged and can turn a flag into a suspension, never clear one. Suspension freezes credentials and moves the agent to Suspended; nothing is deleted. Only a named human resumes or terminates. No answer means terminate.

## Consequences

- Hard controls stay primary.
- The Lead cannot resume its own suspended agent.
- Counters need a shared store once there is more than one replica.
