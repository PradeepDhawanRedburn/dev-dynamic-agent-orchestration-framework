# Roles

Ten permanent roles in five functions. Lead, Tester and Guardrail Manager have one profile per domain (ADR-0010); a new domain
is a new profile, never a change to the graph.

| Function | Role | Accountable for | Uses a model for | Small tier |
| --- | --- | --- | --- | --- |
| Define | Product Manager | Framing the problem, clarifying with the human, measurable success criteria, scope and non-goals, trade-offs, acceptance from the user's side, whether the result was used | Framing, questions, acceptance check | Yes |
| Define | CTO Agent | Technical principles and standards, arbitration between Leads, final technical recommendation | Arbitration, recommendation | No |
| Deliver | Head of Delivery | Workstreams, dependencies between them, coordination, staged consolidation | Decomposition, conflict detection, synthesis | No |
| Deliver | Lead | One workstream in one domain: tasks, specialist requests, direction, acceptance | Decomposition, staffing, review | One |
| Assure | Tester | Checks written from acceptance criteria before work starts, then run on each result | Writing checks, judging claims against evidence | Yes |
| Assure | Reviewer | An independent challenge of the consolidated answer, on a different model deployment | Adversarial review | No |
| Assure | Guardrail Manager | No agent working for its Lead acting outside what was approved. One per Lead; escalates directly to the security owner | Judging what the rule engine flags | Rules always |
| Control | Delivery Controller | Budget, schedule, risks, priority across assignments | Status narrative only | As code |
| Control | Recruiter | Creating, equipping and retiring specialists | Judging overlap between requests only | As code |
| Learn | Knowledge Steward | Prior answers at intake; retrospective at close | Matching requests to past work | Intake check |

Lead profiles: Data, Software, DevOps, Security. Technology assignments only for now; a Business and Research profile is deferred (ADR-0022).

## Authority

| Action | Who may do it |
| --- | --- |
| Request a specialist | A Lead, for a task it owns |
| Create, freeze access for, and retire a specialist | The Recruiter |
| Decide a specialist should be suspended | The guardrail rule engine, or the Guardrail Manager tightening a flag |
| Resume or terminate a suspended agent | A named human: security owner, or sponsor when unavailable |
| Force a revision | Evidence gate (code), Tester (failed report), or Lead |
| Accept a specialist result | The Lead, and only with a passing test report |
| Approve plan, budget overrun, final result; merge pull requests; approve any other proposed change | A named human |
| Cancel a project | Sponsor; platform-wide stop by the security owner |

The CTO Agent and Product Manager recommend. They never approve (ADR-0008).

## Metrics per role

A role that does not move its metric over a review period is changed or removed.

| Role | Metric |
| --- | --- |
| Product Manager | Deliverables accepted without scope dispute; share reported as used a month later |
| CTO Agent | Share of recommendations the sponsor agrees with |
| Head of Delivery | Conflicts and gaps found at consolidation; rework rounds |
| Lead | First-time acceptance rate; cost per accepted task |
| Tester | Defects caught before acceptance against defects found later |
| Reviewer | Material findings that led to a change |
| Guardrail Manager | Suspensions upheld against suspensions reversed |
| Delivery Controller | Forecast accuracy on cost and time |
| Recruiter | Specialists whose accepted work reaches the deliverable; duplicates caught |
| Knowledge Steward | Assignments shortened or avoided by reuse |

## Names changed during design

Head of Development became Head of Delivery. Project Manager became Delivery Controller. The
reference code still uses the old names in places; WP-02 renames them.
