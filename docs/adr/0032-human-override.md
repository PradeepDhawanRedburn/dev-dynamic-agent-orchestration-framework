# ADR-0032: A person can override an agent, with a reason, on the record

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

The owner requires that the person in the loop is given options and the opportunity to override.
ADR-0008 already says humans decide. It did not say what a person may overrule, who may do it,
or what is recorded.

## Decision

1. **Every decision card offers:** the options, the recommendation, "accept the recommendation", and "something else" with free text.
2. **A person may overrule agent and code outcomes** as listed, when they hold the role shown.

   | What | Who may override | Effect |
   | --- | --- | --- |
   | A recommendation or a ranking of options | The decision's approver | Their choice stands |
   | An agent's answer to a question | The person the question would have reached | Their answer stands; dependent provisional work is redone |
   | An assumption an agent is proceeding on | Sponsor | As above |
   | A Lead's acceptance or rejection of a result | Sponsor | Result state changes |
   | A failed Tester check | Sponsor | Result accepted "with a known failed check" |
   | A Reviewer's material finding | Sponsor | Deliverable released "with an accepted finding" |
   | A Solution Architect conformance finding | Sponsor | Departure accepted |
   | Size tier | Sponsor: upward freely; downward with a reason | Tier changes |
   | Who is consulted | Sponsor | Consultees added or removed |
   | Budget ceiling | Sponsor, within their authority | Ceiling changes |
   | A Guardrail Manager's judgement to suspend | Security owner | Agent resumed |

3. **Nobody can override these through the platform.** They change only by a reviewed change to code or an ADR.

   - Agents hold no consequential tools; changes reach the estate as pull requests that people merge.
   - A claim without evidence is never recorded as supported.
   - Data classification limits on what a model or a reader may receive.
   - Hard guardrail rules, and the kill switch.
   - Audit recording.
   - An approved requirement baseline before any delivery.

4. **Every override records:** who, their role, what was overridden and what it said, the new outcome, and a mandatory reason. It is a row in the decision register with type "override".
5. **An override is visible.** The deliverable lists every override that affected it. Nothing overridden is shown as if it had passed.
6. **Overrides are a signal.** They are counted per role and per type, and the Knowledge Steward reports patterns. Frequent overrides of one role mean its prompt, skill or checks need changing.
7. **An override does not teach by itself.** It changes this run only. A lasting change goes through a pull request.

## Consequences

- People can release work with a known failed check or an accepted finding. That is intended, and it is always visible.
- The interaction layer needs a role-to-override table, and one more decision type.
- Which named people hold each role, and whether any override needs two people, is for the owner and the security owner (action H-25).

## Alternatives considered

- No override; people can only choose among offered options: rejected; the owner asked for override, and a person accountable for the outcome must be able to decide.
- Override of anything by the sponsor: rejected; the items in point 3 are what make the record trustworthy.
