# WP-10: Tracing and evaluation

- **Status:** Not started
- **Depends on:** WP-05

## Goal

Every run is traceable in Application Insights, and prompt or model changes are gated by measured quality.

## Read first

- ADR-0014
- ADR-0025
- ADR-0029
- docs/governance/traceability-and-decisions.md
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

## Added by ADR-0033

- Settle how the platform's identifiers reach spans (point 13), with a test. If it cannot be done with the Foundry tracer, say so in an issue before using plain OpenTelemetry.
- Content recording off by default, on per run by classification (point 15).
- Test export to Application Insights, which the spike could not (needs H-28).
- Move `langchain-azure-ai[opentelemetry]` to the runtime dependencies.

## Added by ADR-0029

- Put every identifier in `docs/governance/traceability-and-decisions.md` on every span and audit event.
- A test follows one claim from a deliverable back to the original request using stored identifiers only.
- A test scans exported traces for secrets and for content above the permitted classification.
- If S-20 passed, generate graph diagrams in CI and fail when they differ from the committed ones.
- Update the control matrix status for each control this work package builds.

## Added by ADR-0028

Measure rework (revision rounds, sponsor "more work" decisions, change requests) and time to the requirement baseline, so the cost and benefit of the discovery stage can be judged.

## Out of scope

Self-hosted LangSmith.
