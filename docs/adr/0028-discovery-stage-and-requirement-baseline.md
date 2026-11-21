# ADR-0028: A discovery stage and an approved requirement baseline before any delivery

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

The owner asked that an assignment follow a typical software delivery lifecycle: ideation,
refinement, cross-questioning and clarification, consultation, and only then implementation.

The design before this ADR covered that only in part:

| Stage | Before this ADR |
| --- | --- |
| Ideation | Missing. The Product Manager framed one reading of the request |
| Refinement | Present: framing, up to two rounds |
| Clarification | Present, one direction only: the Product Manager asked the sponsor |
| Consultation | Missing. Technical roles first saw the requirement after it was fixed |
| Requirement sign-off | Small tier only. In Standard and Major the requirement was confirmed together with the plan |
| Change after sign-off | One sentence in the interaction layer; no versioning |

## Decision

Every assignment passes through a **discovery stage** owned by the Product Manager, and ends it
at a human gate that approves a **requirement baseline**. Nothing in delivery starts before that.

1. **Intake.** The request is stored verbatim. The Knowledge Steward checks for prior answers.
2. **Ideation.** The Product Manager offers two or three distinct readings of what could be delivered, always including the smallest useful one and, where prior work exists, reusing it. The sponsor chooses or combines. Small tier: one reading plus the alternatives set aside, unless the request is ambiguous.
3. **Refinement.** The chosen option becomes a requirement draft: outcome, users, success criteria with measures, scope, non-goals, constraints, assumptions.
4. **Clarification.** Questions go to the sponsor from the Product Manager and from the roles consulted. Mandatory questions block.
5. **Consultation.** Code selects who is consulted; each returns a note on feasibility, concerns, questions and rough effort.

   | Consulted | When |
   | --- | --- |
   | The Lead profile for each domain the draft names | Always |
   | Solution Architect | Standard and Major |
   | AI Specialist | When the draft has an AI component |
   | Delivery Controller (cost and time range, computed) | Always |
   | Human security owner | Confidential data, or any proposed change to the estate |
   | Other people the sponsor names | When named |

   Those consulted advise. The Product Manager must answer each concern in the draft or show it to the sponsor as unresolved.
6. **Definition of Ready.** Checked by code; see `docs/architecture/delivery-lifecycle.md`.
7. **Approve requirement.** A human gate in every tier. The approved baseline is versioned and immutable.
8. **Delivery.** Planning, design, staffing and build may start only with a baseline id. The Recruiter refuses a request without one.
9. **Change control.** A change after approval is a change request: the Product Manager states the effect, the sponsor approves, a new baseline version is issued, and only affected work is re-planned.

Discovery creates no specialists and uses no internet tools. If a question needs research before
the requirement can be fixed, the Product Manager proposes a separate, small investigation
assignment, and this one waits.

Discovery has its own budget ceiling and a limit of three refinement rounds.

## Consequences

- Standard and Major assignments gain a gate: approve requirement, then approve plan. Small keeps two gates; "confirm framing" becomes "approve requirement".
- More model calls and more of the sponsor's time before any work. Unmeasured. The return expected is less rework; WP-10 must measure rework with the stage on.
- Three roles gain a consultation task and a new output, `ConsultationNote`. The Product Manager gains `OptionsDraft`.
- The first release (Small tier) is affected: WP-05 grows.
- ADR-0026 is unchanged: the Solution Architect still drafts the design after the baseline. Consultation is an opinion on feasibility, not a design.

## Alternatives considered

- Leave discovery to the sponsor before they submit: rejected; the owner asked for it in the platform.
- Full ideation and consultation in every tier: rejected as too heavy for small requests.
- Let consulted roles research with specialists: rejected; that is delivery work without an approved requirement.
