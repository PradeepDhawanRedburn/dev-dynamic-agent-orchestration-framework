# ADR-0031: Agents can ask a person a question without stopping the run

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

The owner requires an interactive mode: any agent with a question or doubt can leave it for a
person; if that needs a pause, only the work that depends on the answer pauses; everything else
continues, including other work by the same agent.

Before this ADR only the Product Manager could ask questions, during discovery, and every pause
stopped the whole run at the supervisor (ADR-0016).

## Decision

1. **Any agent may ask.** Every output schema gains an optional list of questions. An agent never contacts a person; code posts the question.
2. **A question is a decision card.** The question, why it matters, two to four options, the recommended one, what the agent will assume if nobody answers, and which work depends on it.
3. **Two kinds.**

   | Kind | Meaning | The task |
   | --- | --- | --- |
   | Proceeding | "I will assume X unless told otherwise" | Continues on the stated assumption; results that rely on it are marked provisional |
   | Waiting | "I cannot do this without an answer" | Is parked. Nothing is assumed |

4. **Only dependent work waits.** A parked task blocks itself and the tasks that depend on it. Other tasks in the workstream, and other workstreams, continue.
5. **No agent is kept alive waiting.** A specialist that asks a waiting question returns its partial work and the question, and is retired as usual. When the answer arrives the task is staffed again with the partial work and the answer. Permanent agents hold no state between calls, so a Lead with a parked task simply continues with the others.
6. **An answer ladder before a person.** A specialist's question goes first to its Lead, then to the Solution Architect, AI Specialist or Product Manager where it is theirs to answer. Only what they cannot answer reaches a person. An agent's answer is recorded as an agent's answer, is visible to the person, and can be overridden (ADR-0032).
7. **Routing.** Requirement questions go to the sponsor through the Product Manager, and become a change request if they alter the baseline. Security and data questions go to the security owner. Technical questions go to the sponsor or a technical owner they name.
8. **Mechanics.** Questions and answers live in a store outside graph state. The graph is never interrupted for a question. Scheduling nodes read newly answered questions at safe points and release parked tasks. Only when nothing in the run can proceed does the supervisor pause the run, at the existing kind of gate. ADR-0016 is unchanged: the supervisor is still the only place a run pauses.
9. **Limits.** Two questions per task; a ceiling per assignment; identical questions are merged; a Lead consolidates the questions of its workstream. Low-urgency questions are batched into a digest.
10. **No answer.** Every question has a deadline. A proceeding question keeps its assumption, and the deliverable says so. A waiting question's task is reported as a gap. Silence is never treated as an answer.
11. **An answer that contradicts an assumption** causes the provisional results that relied on it to be redone. The cost of that rework is recorded.
12. **Two modes per assignment.** Interactive, the default. Unattended: agents may not ask waiting questions outside the human gates; they proceed on stated assumptions or report a gap.

## Consequences

- People are asked more often. The ladder, limits and digest exist to keep that useful; whether they are enough is unmeasured.
- Provisional results and rework are new states the Lead subgraph, Tester and deliverable must handle.
- A parked task that is staffed again costs a second specialist. Cheaper than holding one open, and simpler, but not free.
- New spike items: S-25 and S-26.
- Built in WP-14. The task outcome type in WP-04 must be extensible so that "waiting" and "provisional" can be added without rework.

## Alternatives considered

- Interrupt inside the task that has the question: rejected; LangGraph behaviour for interrupts inside parallel branches is unverified, and ADR-0016 exists to avoid depending on it.
- Pause the whole run for every question: rejected; it is what the owner asked to avoid.
- Keep the specialist alive until answered: rejected; it holds credentials and budget open for an unknown time.
- Let agents always assume and never ask: rejected; a wrong assumption found at acceptance costs more than a question.
