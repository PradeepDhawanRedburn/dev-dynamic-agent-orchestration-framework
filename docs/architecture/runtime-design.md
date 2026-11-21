# Runtime design

## Supervisor graph (Small tier, first release)

```mermaid
flowchart TD
  START([start]) --> reuse[knowledge_intake_check]
  reuse --> frame[product_frame]
  frame --> clarify{{confirm_framing: human}}
  clarify -->|changes| frame
  clarify -->|rejected| retire
  clarify -->|confirmed| controls[controller_set_limits]
  controls --> lead[[lead_workstream]]
  lead --> gate{decision needed?}
  gate -->|guardrail or incident| human{{human_decision}}
  human --> lead
  gate -->|no| accept_check[product_acceptance_check]
  accept_check --> decision{{accept_result: human}}
  decision -->|more work| frame
  decision -->|approve or reject| retire[retire_all]
  retire --> retro[knowledge_retrospective]
  retro --> archive[archive] --> END([end])
```

Standard and Major tiers add `delivery_plan`, a plan approval gate, fan-out to several Leads,
staged consolidation, the Reviewer and the CTO Agent recommendation.

## Lead subgraph

```mermaid
flowchart TD
  a[analyse_and_decompose] --> t0[tester_write_checks]
  t0 --> b[build_agent_requests]
  b --> c[recruit]
  c --> d{budget_gate}
  d -->|nothing to run| h
  d -.->|Send per task| e[run_specialist]
  e --> g[guardrail_review]
  g -->|suspended| up[return decision_needed to supervisor]
  g --> f[evidence_gate]
  f --> t[tester_validate]
  t --> r[lead_review]
  r -->|revise| d
  r -->|another specialist| b
  r -->|done| h[workstream_result]
  h --> i[retire_workstream_agents]
```

The draft in `reference/lg/lead.py` differs in two ways that work packages correct: it pauses for
the guardrail gate inside the subgraph, and the Tester does not yet write checks first.

## State

| Scope | Lives in | Holds |
| --- | --- | --- |
| Project | Supervisor state | Ids of requirement, plan and results; approvals; loop counters; tier; outcome |
| Workstream | Lead subgraph state | Task ids, specification ids, outcome ids, review decisions, revision counters |
| Task | The `Send` payload | One task, one specification, reservation id, revision comments |
| Agent | Inside the worker's agent loop | Messages and notes; discarded when the node returns |

Rules: values are JSON-serialisable and re-validated with Pydantic at node boundaries. Keys
written by parallel branches have reducers. A subgraph returns only reducer keys to its parent.
State holds references; bodies are read from the stores.

## Loops and their ceilings

| Loop | Default ceiling | At the ceiling |
| --- | --- | --- |
| Revisions per task | 2 | Result rejected; task re-staffed if rounds remain, otherwise reported as a gap |
| Recruitment rounds per workstream | 2 | Gap reported |
| Framing rounds | 2 | Run ends as not confirmed |
| Sponsor rework cycles | 2 | Run ends with the last deliverable |

Counters live in state. A `recursion_limit` is a final backstop.

## Specialist lifecycle

Requested, Validated, Approved, Provisioned, Registered, Assigned, Running, Awaiting review,
Revision requested, Suspended, then Accepted, Failed, Cancelled, Timed out or Rejected, then
Retired. The table of allowed moves is `ALLOWED_TRANSITIONS` in `reference/contracts.py`; the
registry refuses anything else. Retirement revokes access first and cannot be recorded while
access is live.

## Human gates

Every gate is an interrupt raised by the supervisor. Subgraphs return `decision_needed`; they do
not pause themselves (ADR-0016).

| Gate | Approver | No answer means |
| --- | --- | --- |
| Confirm framing (Small) or approve plan | Sponsor | Run expires; nothing spent |
| Budget or deadline overrun | Sponsor | New work stops; partial result assembled |
| Proposed change other than a pull request | Change owner | Change not made |
| Guardrail suspension | Security owner | Agent terminated |
| Incident: runbook exhausted | Sponsor | Task cancelled |
| Accept result | Sponsor | Result stays pending; agents are retired regardless |

Pull requests have no gate in the graph: the executor opens them and people review and merge in GitHub (ADR-0021).

A node that calls `interrupt()` re-runs from its first line on resume. Gate nodes therefore do
nothing before the call, and any model work sits in the node before.

## Failure handling

| Situation | Response |
| --- | --- |
| Model or tool call fails | Self-healing runbook for that fault; then an incident to a human (ADR-0015) |
| Specialist fails or times out | Outcome recorded as failed; Lead re-staffs within its round limit |
| Result cites unknown evidence | Rejected by schema; agent failed; guardrail event recorded |
| Evidence insufficient | One revision naming the gap; then accepted as partial with confidence capped |
| Budget reservation refused | Task blocked and reported; escalation to the sponsor |
| Two Leads request the same work | Second request held; Head of Delivery assigns one owner |
| Workstream results conflict | Returned to the owning Leads; unresolved conflicts shown to the sponsor with both positions |
| Process dies mid-run | Resumes from the last checkpoint; completed branches are not re-run |
