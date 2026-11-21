# WP-14: Questions without stopping the run, and human override

- **Status:** Not started. Do not begin before WP-09 is done
- **Depends on:** WP-04, WP-05, WP-09
- **Suggested position:** straight after WP-09. It changes how a Lead schedules tasks, which is cheaper to do before the Standard tier (WP-11) than after. It may be done last if the owner prefers.

## Goal

Any agent can leave a question for a person; only the work that depends on the answer waits;
a person can choose, answer in their own words, or override, and all of it is on the record.

## Read first

- ADR-0031
- ADR-0032
- ADR-0016
- ADR-0008
- docs/architecture/interaction-layer.md
- docs/governance/traceability-and-decisions.md
- docs/plan/spike-findings.md, items S-25 and S-26 (both held)
- ADR-0033, point 24

## Tasks

1. Define `HumanQuestion` and add an optional list of them to every agent output schema. Fields are in the interaction-layer document.
2. Build the question store outside graph state: post, merge identical, route, answer, expire.
3. Add the task outcomes "waiting" and "provisional". A waiting task parks itself and its dependants only.
4. In the Lead's scheduling step, read newly answered questions at a safe point, release parked tasks, and staff a parked task again with its partial work and the answer.
5. Implement the answer ladder: Lead, then the Solution Architect, AI Specialist or Product Manager, then a person.
6. Pause the run at the supervisor only when nothing can proceed.
7. Mark results that rely on an unanswered assumption as provisional through to the deliverable. Redo them when an answer contradicts the assumption, and record the rework cost.
8. Implement limits, the digest, deadlines and the no-answer outcomes.
9. Implement the assignment mode: interactive or unattended.
10. Extend the decision card with "accept the recommendation" and "something else".
11. Implement override: the role table from ADR-0032, a mandatory reason, the decision register entry, and the list of overrides on the deliverable.
12. Refuse, in code, every override listed as not possible in ADR-0032.
13. Count overrides and questions per role and type for the Knowledge Steward.
14. Update the control matrix rows this work package builds.
15. Add rule 9 to `agents/_shared/organisational-policy.md`, bump its version, and add the matching rule to the specialists' policy section. The architect's wording:

    > If you are unsure about something that changes the outcome, ask. Put the question in the questions field: the question, why it matters, two to four options, the one you recommend, and either the assumption you will proceed on or that you cannot continue without an answer. Do not ask what the documents you were given already answer. Do not guess silently.

    This is the one change to `agents/` this work package is allowed to make.

## Acceptance criteria

- [ ] With one task waiting, the other tasks of the workstream and the other workstreams finish (tested).
- [ ] The graph is not interrupted when a question is posted; the run pauses only when nothing can proceed (tested).
- [ ] No specialist stays registered while its task waits (tested).
- [ ] An answered question releases exactly its dependent tasks (tested).
- [ ] A waiting question that expires produces a reported gap, never an assumed answer (tested).
- [ ] A contradicting answer causes the provisional results that relied on the assumption to be redone, and only those (tested).
- [ ] An agent's answer on the ladder is recorded as an agent's answer and can be overridden (tested).
- [ ] An override without a reason, or by someone without the role, is refused and audited (tested).
- [ ] Each override listed as not possible is refused (tested, one test per item).
- [ ] A deliverable released over a failed check or a finding says so (tested).
- [ ] In unattended mode no waiting question is raised outside the human gates (tested).
- [ ] Question limits hold (tested).

## Out of scope

The Teams bot. Changing which decisions are human gates. Learning from overrides automatically.
