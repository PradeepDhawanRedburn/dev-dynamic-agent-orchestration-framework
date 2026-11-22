# WP-03: Agent definitions, worker runtime and tool gateway

- **Status:** Not started
- **Depends on:** WP-02

## Goal

Permanent agents load their prompts from `agents/`, and a specialist can be built from a specification and run against a Foundry model with fake tools.

## Read first

- ADR-0002
- ADR-0006
- ADR-0025
- ADR-0033
- ADR-0034
- ADR-0029
- docs/governance/lang-family-controls.md
- ADR-0027
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

## Not blocked by open human actions

The architect has decided that this work package proceeds without waiting for the actions below.
Do not stop for them.

| Open action | How this work package proceeds |
| --- | --- |
| H-01, H-02, H-03, H-04: organisation skills not written | They are marked `needs-content`. The loader skips them and records that it did. That is the designed behaviour and is tested here |
| H-03, H-14: approved model list | Use a **provisional model catalogue** in configuration, holding the deployments named in `.env.example`. Mark every entry provisional, with the highest data classification set to Internal. The AI lead replaces it later; no code changes |
| H-10: search service and egress allow-list | Not needed here; this work package uses two fake tools |
| H-13: evaluation examples | Not needed here; prompts stay drafts |
| H-27: key rotation | Not a blocker. Tests that need Foundry are skipped visibly when no key is present |

## Carried over from the review of WP-02

Done first, in this pull request (ADR-0034).

- A second migration: released reservations are kept with state `released` and the application role loses DELETE on reservations; agent transitions are append-only; an agent's specification and request hash cannot be updated. Update the in-memory twins and tests to match.
- A change to a budget limit writes an audit event naming who changed it.
- Build the async facade over the stores. Add the test that fails when a module under the graph package imports a synchronous store.
- Pool size and worker-thread count are configuration.

## Acceptance criteria

- [ ] The carried-over items are done and tested; a released reservation is still readable after release.
- [ ] A built specialist contains only allow-listed middleware, by class name, in the order in ADR-0033 (tested).
- [ ] The model catalogue carries the fields in ADR-0033 point 9, and the API and reasoning effort used for a call come from it (tested).
- [ ] A tool failure and a content-filter block each produce the outcome in ADR-0033, with no retry of a blocked prompt (tested).
- [ ] Loader output for all twelve roles and five profiles is covered by golden-file tests.
- [ ] A skill marked `needs-content` is not in the assembled prompt, and the run records it as skipped (tested).
- [ ] A specialist run with a fake model returns a valid `AgentResult`; a result citing an unknown evidence id is rejected.
- [ ] A tool call without a grant, past its limit, or after retirement is refused and audited.
- [ ] Token usage is metered per model call and stops the agent at its budget.

## Out of scope

The Lead subgraph.
