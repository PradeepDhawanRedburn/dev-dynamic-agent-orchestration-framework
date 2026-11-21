# WP-06: Guardrail rules, suspension and the human gate

- **Status:** Not started
- **Depends on:** WP-05

## Goal

An agent that behaves outside what was approved is suspended in real time and a human decides what happens next.

## Read first

- ADR-0010
- ADR-0011
- ADR-0016
- agents/guardrail-manager.agent.md
- reference/guardrails.py

## Tasks

1. Feed audit events to the rule engine; move its counters to a shared store.
2. Implement suspension so the Lead subgraph returns `decision_needed` and the supervisor raises the gate.
3. Implement resume and terminate, including a held result going on to the evidence gate and Tester.
4. Load rule thresholds from `policy/guardrail_rules.yaml`.
5. Run one Guardrail Manager per Lead profile, with its domain profile, and send every flag and suspension to the security owner as well as to the Lead (ADR-0010).

## Acceptance criteria

- [ ] Three denied tool calls suspend an agent before its next call (tested).
- [ ] A suspended agent cannot run, be accepted or be revised (tested).
- [ ] Only a named human can resume; a Lead cannot (tested).
- [ ] A gate timeout terminates the agent and revokes its access (tested).

## Out of scope

A Guardrail Manager for the permanent agents; they are covered by the rule engine and the security owner.
