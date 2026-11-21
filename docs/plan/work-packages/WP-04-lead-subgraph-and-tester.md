# WP-04: Lead subgraph with Tester

- **Status:** Not started
- **Depends on:** WP-03

## Goal

One Lead profile can decompose a workstream, staff it, and return tested, accepted results.

## Read first

- ADR-0012
- ADR-0018
- docs/architecture/runtime-design.md
- agents/lead.agent.md
- agents/tester.agent.md
- reference/lg/lead.py

## Tasks

1. Implement the Lead subgraph from the runtime design, starting from `reference/lg/lead.py`.
2. Add `tester_write_checks` before staffing, and make `tester_validate` run those checks plus the specification's `required_checks`.
3. Hold ids in state and read bodies from repositories.
4. Define the schemas `CheckDrafts` and `WorkstreamSummary`.
5. Keep the task outcome type and the scheduling step open to extension: WP-14 adds the outcomes "waiting" and "provisional" (ADR-0031). Do not build them here.

## Acceptance criteria

- [ ] Whole-subgraph tests with a scripted model reproduce the scenario in `reference/lg/dryrun.py`: one revision forced by the evidence gate, one by the Tester, one re-staffing after an invalid citation.
- [ ] A result without a passing test report cannot reach Accepted (tested).
- [ ] Every loop stops at its ceiling (tested).
- [ ] Every specialist is retired when the subgraph ends, on every path (tested).

## Out of scope

Guardrail suspension handling; that is WP-06.
