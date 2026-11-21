# ADR-0026: Add a Solution Architect and an AI Specialist

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

Nobody drafted one design across workstreams. The Head of Delivery splits work, each Lead plans
its own workstream, and the CTO Agent only recommends at the end of a Major assignment.
Contradictions between workstreams were therefore found late, at consolidation. The team is
AI-first, and no permanent role held AI expertise. The repository owner asked for both roles.

## Decision

Add two permanent roles to the Deliver function, both reporting to the Head of Delivery. This
amends ADR-0007: twelve roles.

**Solution Architect.** Standard and Major tiers.

- Before the Leads plan, drafts the solution design across the Head of Delivery's workstreams:
  components and their owners, interfaces, design choices with reasons, assumptions.
- The design is attached to the plan. The sponsor approves both at the existing plan gate. No new human gate.
- After consolidation, checks the Lead summaries against the approved design and reports departures.
- It cannot change workstreams, direct Leads or edit results.

**AI Specialist.** Standard and Major tiers, and only when the plan marks an AI component.

- Advises the Solution Architect on the design, and a Lead who asks.
- It recommends. It cannot decide, direct specialists, or recommend a model that is not approved.
- It must mark any statement about current models, prices or interfaces as to be verified; a workstream establishes such facts with evidence.
- It does not maintain this platform's own agents.

**Boundaries.**

| Question | Who |
| --- | --- |
| Principles and standards for the organisation | CTO Agent |
| The design for one assignment | Solution Architect |
| A disagreement between a Lead and the design, or between Leads | CTO Agent arbitrates |
| Which workstreams exist | Head of Delivery |
| Independent challenge of the answer | Reviewer, unchanged |

## Consequences

- At least two more model calls per Standard or Major assignment, and one or more when AI advice is used. Cost and latency rise; the amount is unmeasured.
- The Solution Architect checks the result against its own design. This is a conformance check, not an independent review. The Reviewer remains the independent challenge, and the prompt requires the Architect to say when the evidence shows the design was wrong.
- The design can anchor the Leads on a wrong answer. Mitigations: assumptions are marked and must be established by evidence; a departure supported by evidence is not a fault.
- Neither role runs in the Small tier, so the first release is unaffected. A Small assignment with an AI component gets no AI advice; revisit after the proof of concept.
- Each role has a metric (`docs/architecture/roles.md`). If a role does not move its metric it is changed or removed, as for every other role.
- New schemas: `SolutionDesignDraft`, `DesignConformance`, `AiAdvice`. The plan needs an `ai_component` marker set by the Head of Delivery.

## Alternatives considered

- Give the design to the CTO Agent: rejected; it would then arbitrate disputes about its own design.
- Give the design to the Head of Delivery: rejected; coordination and design in one prompt weakens both.
- AI as a fifth Lead profile: not chosen by the owner. Can be added later as a profile without changing this ADR.
- AI expertise only as a skill pack for specialists: useful as well, but gives no advice at design time.
