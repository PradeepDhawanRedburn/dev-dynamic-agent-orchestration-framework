# WP-03: Agent definitions, worker runtime and tool gateway

- **Status:** Not started
- **Depends on:** WP-02

## Goal

Permanent agents load their prompts from `agents/`, and a specialist can be built from a specification and run against a Foundry model with fake tools.

## Read first

- ADR-0002
- ADR-0006
- ADR-0025
- ADR-0027 (Proposed; confirm it is accepted before task 5)
- agents/skills/README.md
- docs/architecture/tool-catalogue.md
- agents/README.md
- reference/lg/worker.py

## Tasks

1. Write a loader that reads an `*.agent.md` file, substitutes the organisational policy and domain profile, and returns the prompt with its hash and versions.
2. Implement the model catalogue for Foundry deployments, using whatever S-12 established.
3. Implement the worker and tool gateway from `reference/lg/worker.py`, corrected by the spike findings.
4. Provide two fake read-only tools that produce evidence records.
5. Extend the loader to append role skills, skip any marked `needs-content`, and record which were loaded and skipped.
6. Implement `model_catalogue_read` over the model catalogue.

## Acceptance criteria

- [ ] Loader output for all twelve roles and five profiles is covered by golden-file tests.
- [ ] A skill marked `needs-content` is not in the assembled prompt, and the run records it as skipped (tested).
- [ ] A specialist run with a fake model returns a valid `AgentResult`; a result citing an unknown evidence id is rejected.
- [ ] A tool call without a grant, past its limit, or after retirement is refused and audited.
- [ ] Token usage is metered per model call and stops the agent at its budget.

## Out of scope

The Lead subgraph.
