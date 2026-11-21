# WP-05: Supervisor graph, Small tier

- **Status:** Not started
- **Depends on:** WP-04

## Goal

A single-domain assignment runs from a sponsor's request to an accepted result, through the discovery stage and the two Small-tier human gates, with checkpointing.

## Read first

- ADR-0008
- ADR-0016
- ADR-0017
- ADR-0028
- docs/architecture/delivery-lifecycle.md
- agents/product-manager.agent.md
- agents/knowledge-steward.agent.md
- docs/architecture/runtime-design.md

## Tasks

1. Implement the Small-tier supervisor graph from the runtime design.
2. Implement the discovery stage for the Small tier: options, requirement draft, clarifying questions, consultation of the one Lead and the cost range, the Definition of Ready check, and the requirement approval gate. Define the schemas.
3. Implement the requirement baseline: versioned, immutable, and required by the Recruiter and the Lead subgraph.
4. Implement the change request path and the Product Manager's acceptance check against the latest baseline.
5. Implement the Knowledge Steward intake check as a stub that returns no matches, behind its interface.
6. Raise both gates as interrupts from the supervisor; resume with a verified decision.
7. Compile with the PostgreSQL checkpointer.

## Acceptance criteria

- [ ] The phase 2 exit criteria in the roadmap are met with a scripted model.
- [ ] An assignment with unanswered mandatory questions does not start (tested).
- [ ] A draft that fails any Definition of Ready item never reaches the approval gate (tested per item).
- [ ] No specialist can be requested without an approved baseline id (tested).
- [ ] A consultation concern cannot be dropped: it is answered in the draft or shown to the sponsor (tested).
- [ ] A change after approval produces a new baseline version and leaves unaffected work running (tested).
- [ ] Discovery stops at three refinement rounds and at its budget ceiling (tested).
- [ ] A request that is not a technology assignment is declined at intake with the reason (ADR-0022).
- [ ] A gate that times out takes its safe default (tested).
- [ ] The sponsor's request and criteria appear verbatim in every model call that works on them (tested).

## Out of scope

Standard and Major tiers.
