# WP-01: Architecture spike

- **Status:** Not started
- **Depends on:** WP-00

## Goal

Find out whether LangGraph, LangChain and Foundry behave as the design assumes, before anything is built on those assumptions.

## Read first

- docs/plan/spike-checklist.md
- ADR-0001
- ADR-0002
- ADR-0014
- ADR-0016
- reference/README.md

## Tasks

1. For each item S-01 to S-16, write the smallest script or test that settles it against the installed versions. Keep them under `tests/spike/`.
2. Run `reference/lg/` against real LangGraph with a fake chat model, and record what breaks.
3. Do the measurements listed under 'Also in the spike'.
4. Record every result in `docs/plan/spike-findings.md` with versions.
5. Open one issue labelled `spike-finding` for each assumption that does not hold.

## Acceptance criteria

- [ ] Every row of `spike-findings.md` is filled in.
- [ ] Each failed assumption has an issue with a minimal reproduction.
- [ ] A process kill and restart mid-run is demonstrated and its behaviour described.
- [ ] No production code is written.

## Out of scope

Fixing the design. Report; the architect amends the ADRs.
