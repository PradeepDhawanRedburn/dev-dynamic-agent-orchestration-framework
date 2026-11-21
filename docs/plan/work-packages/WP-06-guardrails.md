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
5. Leave the Guardrail Manager's judgement step configurable as one per platform or one per Lead until ADR-0010 is decided.

## Acceptance criteria

- [ ] Three denied tool calls suspend an agent before its next call (tested).
- [ ] A suspended agent cannot run, be accepted or be revised (tested).
- [ ] Only a named human can resume; a Lead cannot (tested).
- [ ] A gate timeout terminates the agent and revokes its access (tested).

## Out of scope

Changing which placement is used; that is the owner's decision.
