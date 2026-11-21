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
- ADR-0029
- docs/governance/lang-family-controls.md
- reference/README.md

## Tasks

1. For each item in the spike checklist (S-01 to S-24), write the smallest script or test that settles it against the installed versions. Keep them under `tests/spike/`.
2. Run `reference/lg/` against real LangGraph with a fake chat model, and record what breaks.
3. Do the measurements listed under 'Also in the spike'.
4. Record every result in `docs/plan/spike-findings.md` with versions.
5. Open one issue labelled `spike-finding` for each assumption that does not hold.

## Carried over from the review of WP-00

Small items, done in this pull request.

6. Add the packages the spike needs and WP-00 did not list, pinned exactly: the PostgreSQL checkpointer package for LangGraph and its database driver. Re-lock.
7. Run CI on pushes to `main` as well as on pull requests.
8. Generate `docs/governance/dependency-licences.md` on Linux, the platform that will be deployed, and fail CI when it is out of date with `uv.lock`.
9. `langsmith` is installed as a dependency of `langchain`. Settle S-24, and add a test that fails if any LangSmith or LangChain tracing or endpoint environment variable is set in the test or CI environment.
10. Run the spike tests in a separate CI job that needs no cloud credentials; mark tests that need Foundry so they are skipped, visibly, when it is absent.

## Acceptance criteria

- [ ] Every row of `spike-findings.md` is filled in.
- [ ] Each failed assumption has an issue with a minimal reproduction.
- [ ] A process kill and restart mid-run is demonstrated and its behaviour described.
- [ ] No production code is written.
- [ ] Rows that could not be tested say why and what is needed; none is left blank or guessed.

## Out of scope

Fixing the design. Report; the architect amends the ADRs.
