# ADR-0030: Which reasoning patterns the platform uses

- **Status:** Proposed
- **Date:** 2026-11-21

## Context

The owner asked whether the design follows ReAct, Self-Refine and AlphaCodium, and asked the
architect to say what is better for this platform. WP-13 records where the design stands. This
ADR is the architect's position. It is Proposed because none of it is measured yet.

## Decision

| Pattern | Position | Where |
| --- | --- | --- |
| ReAct | Keep for temporary specialists, where tools are used. Add a short plan before the first tool call | Specialist worker |
| ReAct | Do not use for permanent agents. They stay single-call into a narrow schema | All twelve roles |
| Self-Refine | Adopt one self-check pass by a specialist before submission. It never replaces the Tester or Reviewer | Specialist worker |
| AlphaCodium-style flow | Adopt as a second, registered task flow for tasks that produce code or configuration | Software and DevOps tasks |

1. **Task flows.** The worker has a small, fixed set of flows, registered in code and chosen by code from the task type: a research flow (the current one) and a code flow. A model never chooses or builds a flow, so ADR-0001 holds.
2. **The code flow.** Reflect on the task; take the Tester's checks; propose additional checks to the Tester; produce the work; run the checks in the sandbox; fix and re-run within a limit; a fix must keep passing every check that already passed.
3. **The self-check pass.** One pass against the acceptance criteria, then submit. Limit of one.
4. **Every loop is bounded in code and charged to the budget ledger.**
5. **Stated reasoning is trace content.** It is never evidence and never trusted as an account of what the agent did.
6. **Each item is switched on only after WP-13 shows it pays for itself** on the evaluation sets, in quality gained against cost and time added.

Not adopted, because they add many model calls and there is no evidence here that they help:
agents debating each other, and exploring many reasoning branches in parallel.

## Consequences

- If accepted, WP-13 becomes "build and measure these", not "explore".
- The code flow is the largest item: new registered flow, sandbox loop, and Tester interaction.
- More model calls per task. The expected return is fewer rejections by the Tester; unmeasured.
- The independence rule is unchanged: no function's own check counts as a test (ADR-0009, ADR-0012).

## Alternatives considered

- Adopt nothing until measured, with no stated position: safe, but gives the implementer no direction.
- Self-critique in place of the Tester: rejected; it removes independent testing.
- Loops for permanent agents: rejected; their single-call design is what keeps control decisions in code.
