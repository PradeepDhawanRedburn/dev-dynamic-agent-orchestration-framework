# WP-05: Supervisor graph, Small tier

- **Status:** Not started
- **Depends on:** WP-04

## Goal

A single-domain assignment runs from a sponsor's request to an accepted result, with the two Small-tier human gates and checkpointing.

## Read first

- ADR-0008
- ADR-0016
- ADR-0017
- agents/product-manager.agent.md
- agents/knowledge-steward.agent.md
- docs/architecture/runtime-design.md

## Tasks

1. Implement the Small-tier supervisor graph from the runtime design.
2. Implement the Product Manager's framing, clarifying questions and acceptance check, and define their schemas.
3. Implement the Knowledge Steward intake check as a stub that returns no matches, behind its interface.
4. Raise both gates as interrupts from the supervisor; resume with a verified decision.
5. Compile with the PostgreSQL checkpointer.

## Acceptance criteria

- [ ] The phase 2 exit criteria in the roadmap are met with a scripted model.
- [ ] An assignment with unanswered mandatory questions does not start (tested).
- [ ] A gate that times out takes its safe default (tested).
- [ ] The sponsor's request and criteria appear verbatim in every model call that works on them (tested).

## Out of scope

Standard and Major tiers.
