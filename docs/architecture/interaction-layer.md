# Human interaction layer

People deal with the platform through one front door, in four ways (ADR-0016).

| Interaction | Started by | Example | Handled by |
| --- | --- | --- | --- |
| Clarify | Agent | "All order feeds, or only retail?" | Product Manager |
| Decide | Agent | Choose an option; approve the requirement; approve a plan; extend a budget; resume or terminate a suspended agent; choose what to do about an outage | The role that raised it |
| Inform | Either | Status, cost so far, what is blocked, "why did you conclude this?" | Answered from audit and ledger |
| Steer or stop | Human | Change scope, reprioritise, pause, cancel | Product Manager for scope; kill switch for stop |

## Decision card

Every request for a decision carries the same seven fields:

1. The question.
2. The options.
3. The recommended option, and which role recommends it.
4. The evidence.
5. What waiting costs.
6. What happens if nobody answers.
7. The deadline.

## Rules

- **One place where a run pauses.** The supervisor raises every interrupt. This gives one
  decision queue per project.
- **Identity.** The approver signs in with Entra ID. The API verifies identity and role before
  resuming the run, and records both.
- **Timeouts.** Each gate has a deadline and a safe default. A timeout never resolves to "approved".
- **Tiered approvals.** Low-risk decisions may be batched into a digest or delegated to a named
  deputy. High-risk decisions always go to the named approver.
- **Change control.** A change after the requirement is approved is a change request. The
  Product Manager states the effect on cost and time. After approval a new baseline version is
  issued and only affected work is re-planned (ADR-0028).
- **Feedback.** Every approval, rejection and comment is stored against the run and feeds the
  evaluation datasets.

## Channels

First release: an HTTP API and a minimal web page for decision cards. Later: a Teams bot for
decisions and questions, and a web console for plans, evidence and audit. The Teams design is
from general knowledge and has not been verified against current Teams capabilities.
