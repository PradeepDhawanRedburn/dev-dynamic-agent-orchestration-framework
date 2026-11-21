# WP-11: Standard tier

- **Status:** Not started
- **Depends on:** WP-06, WP-09, WP-10

## Goal

Multi-domain assignments: several Leads in parallel, staged consolidation and an independent review.

## Read first

- ADR-0007
- ADR-0009
- ADR-0018
- ADR-0022
- ADR-0026
- ADR-0028
- agents/head-of-delivery.agent.md
- agents/reviewer.agent.md
- agents/solution-architect.agent.md
- agents/ai-specialist.agent.md

## Tasks

1. Implement planning, the plan approval gate and fan-out to several Leads, ordered by dependency.
2. Implement Lead summaries and staged consolidation with conflict return.
3. Implement the Reviewer on a different model deployment, and return of material findings.
4. Implement the tier rules.
5. Implement the Solution Architect: `SolutionDesignDraft` attached to the plan before the approval gate, passed unchanged to every Lead, and `DesignConformance` after consolidation.
6. Implement the AI Specialist: invoked when the plan marks an AI component or a Lead asks, with a limit on requests, and with recommended models checked against the approved list.
7. Route a disagreement about the design to the CTO Agent.
8. Extend discovery for Standard and Major: full options, and consultation fanned out to the named Leads, the Solution Architect, the AI Specialist where relevant, and the human security owner for Major.
9. Lead profiles are Data, Software, DevOps and Security only (ADR-0022).

## Acceptance criteria

- [ ] Only the Leads named in the plan are invoked (tested).
- [ ] A contradiction between workstreams reaches the owning Leads and, if unresolved, the sponsor with both positions (tested).
- [ ] The Reviewer's deployment differs from the producers' (tested).
- [ ] Requirement approval and plan approval are separate gates, in that order (tested).
- [ ] The sponsor sees the plan and the design at one gate; no Lead starts before approval (tested).
- [ ] Every component in the design has one owning workstream and every mandatory criterion is referenced (validated in code).
- [ ] The AI Specialist is not invoked when no AI component is marked (tested).
- [ ] A recommended model outside the approved list is rejected by code (tested).
- [ ] Assignments are run with and without the design step, and the contradictions found at consolidation are recorded for both.
- [ ] Checkpoint size stays within the bound measured in the spike.

## Out of scope

The Major tier.
