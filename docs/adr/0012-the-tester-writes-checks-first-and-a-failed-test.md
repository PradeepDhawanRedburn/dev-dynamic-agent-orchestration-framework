# ADR-0012: The Tester writes checks first, and a failed test forces a revision

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

A Lead reviewing its own specialists is marking its own homework, and specialists need to know what done means.

## Decision

Each Lead profile has a Tester. Before specialists start, the Tester turns the task's acceptance criteria and any skill-pack checks into explicit checks. After the work it runs them. A result without a passing report cannot be accepted by the Lead. The Tester cannot edit or accept a result.

## Consequences

- Adds model calls per review round; measure the defects caught against that cost.
- The reference draft tests only after the work; WP-04 adds checks-first.
