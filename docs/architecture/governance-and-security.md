# Governance and security

Assume any model output and any retrieved content may be hostile. Every control that matters is
enforced in code outside the model. Prompts are guidance.

## The property everything rests on

A specialist holds no capability to change anything outside its sandbox, even if injected text
takes it over completely. Three risks remain and each has a control: wasted budget (limits),
wrong answers (evidence gate, Tester, Reviewer), and leakage through outbound queries
(data-class rule and egress proxy). None of these is perfect; residual risk belongs in the
security review.

## Controls

| Threat | Control enforced in code |
| --- | --- |
| Prompt injection in the request or a Lead's brief | Lead text fills bounded, linted prompt slots; policy and standards sections come first |
| Injection from retrieved content or tool output | Read-only grants; tool output wrapped as data and flagged; flags feed the guardrail rules |
| Privilege escalation | Gateway checks the grant on every call; three denials suspend the agent |
| Invented sources | Evidence ids are issued only by the gateway; a result citing an unknown id fails validation |
| Unsafe generated code | Runs only in a sandbox with no credentials and no outbound network |
| Recursive agent creation | No tool or message exists for it; `can_spawn_agents` is fixed to `False` |
| Unbounded loops | Counters in state with ceilings in policy |
| Tampered prompt | Prompt hash verified when the agent is built |
| Reading another agent's memory | Namespace derived from caller identity; row-level security |
| Data shown to someone not entitled | Retrieval filtered to the requesting human's access rights (ADR-0024) |
| Cost exhaustion | Ledger reservations, per-call metering, call limits, timeouts, concurrency caps |
| An agent's pull request triggering a privileged workflow | Workflows on agent-authored pull requests run read-only with no deployment secrets; the platform cannot approve or merge (ADR-0021) |
| Supply chain | Pinned and hashed dependencies, private feed, signed images, pinned model versions |

## Budget

A ledger with reservations (ADR-0005). The maximum cost of a task is reserved against its
workstream and project before it runs. The worker meters every model call and stops the agent at
its limit. Settlement records what each run actually spent. Tasks share 60% of a workstream
budget; 40% is held for revisions and re-staffing. Reference: `reference/budget.py`.

## Guardrails

Two parts (ADR-0011):

1. **Rule engine, code.** Counts audit events per agent in real time and returns none, flag or
   suspend. Reference: `reference/guardrails.py`.
2. **Guardrail Manager, model, one per Lead (ADR-0010).** Judges what the rules flagged for its Lead's agents. It can turn a flag into a
   suspension. It can never clear one.

| Event | Flag at | Suspend at |
| --- | --- | --- |
| Tool call denied | 1 | 3 |
| Output withheld: above clearance | | 1 |
| Tool output looked like instructions | 1 | 3 |
| Cited evidence never issued | 1 | 2 |
| Tried to create or contact an agent | | 1 |
| Prompt hash mismatch | | 1 |
| Stopped by budget | 1 | |
| Output addresses excluded scope | 1 | 2 |

Permanent agents are covered by the rule engine and the human security owner only; no Guardrail Manager judges them. That is a known gap.

Suspension freezes credentials and moves the agent to Suspended. Nothing is deleted. A named
human resumes or terminates. Thresholds are starting values to tune; they live in
`policy/guardrail_rules.yaml`. With more than one replica the counters must be in a shared store.

## Self-healing

Every model and tool call runs through one routine (ADR-0015). Reference: `reference/resilience.py`.

| Fault | Runbook | Then |
| --- | --- | --- |
| Network lost | Probe; retry with backoff twice; switch to approved alternate | Human decides |
| DNS failure | Probe; retry; switch | Human decides |
| Timeout | Retry twice; switch | Human decides |
| Throttled (429) | Retry twice honouring retry-after; switch deployment | Human decides |
| Credential expired (401, 403) | Refresh token from managed identity | Human decides |
| Dependency down (5xx) | Probe; switch; retry | Human decides |
| Prompt blocked by the provider's content filter | None. Never retried; recorded as a guardrail event | Task fails to its Lead |
| Unknown | None | Human decides |

An agent may not restart services, change configuration, or use an endpoint that is not on the
approved list. The human is offered: wait and retry, switch region, reduce scope, cancel.

## Audit

Append-only, hash-chained, written by governance services and never by agents. It records who
submitted and approved what; every agent request and its outcome; every specification with
prompt hash, template versions and model version; every tool call; every permission decision;
every state transition; every budget event; every incident; every retirement. It does not depend
on the tracing tool being available.

## Earned autonomy (deferred, ADR-0023)

Every assignment type starts with all its human gates. Measured quality held over an agreed
number of runs may relax one low-risk gate for that type. A drop in quality or any suspension
restores it. Final acceptance of a Major assignment and approval of a change to the estate are
never relaxed. Needs sign-off from the governance function before it is switched on.
