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
- agents/head-of-delivery.agent.md
- agents/reviewer.agent.md

## Tasks

1. Implement planning, the plan approval gate and fan-out to several Leads, ordered by dependency.
2. Implement Lead summaries and staged consolidation with conflict return.
3. Implement the Reviewer on a different model deployment, and return of material findings.
4. Implement the tier rules.
5. Add the Business and Research profile only if ADR-0022 is accepted.

## Acceptance criteria

- [ ] Only the Leads named in the plan are invoked (tested).
- [ ] A contradiction between workstreams reaches the owning Leads and, if unresolved, the sponsor with both positions (tested).
- [ ] The Reviewer's deployment differs from the producers' (tested).
- [ ] Checkpoint size stays within the bound measured in the spike.

## Out of scope

The Major tier.
