# WP-10: Tracing and evaluation

- **Status:** Not started
- **Depends on:** WP-05

## Goal

Every run is traceable in Application Insights, and prompt or model changes are gated by measured quality.

## Read first

- ADR-0014
- ADR-0025
- docs/architecture/azure-foundry.md
- docs/architecture/roles.md

## Tasks

1. Attach the Foundry tracer with the required metadata keys; redact or hide content by data class.
2. Build the first datasets: reference requirements with expected Lead selection, specialist tasks with a frozen evidence corpus, and an adversarial set.
3. Implement evaluators for task completion, citation correctness, evidence coverage, schema compliance and policy violations.
4. Compute the per-role metrics from `docs/architecture/roles.md`.
5. Add an evaluation job to CI that blocks a change to `agents/` or the model catalogue when a threshold is missed.

## Acceptance criteria

- [ ] A run can be found in Application Insights by `project_id` and followed to a specialist's tool call.
- [ ] Changing a prompt in `agents/` without passing the evaluation job cannot be merged.
- [ ] The adversarial set shows no case reaching a tool outside its grant.

## Out of scope

Self-hosted LangSmith.
