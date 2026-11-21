# Human interaction layer

People deal with the platform through one front door, in four ways (ADR-0016).

| Interaction | Started by | Example | Handled by |
| --- | --- | --- | --- |
| Clarify | Agent | "All order feeds, or only retail?" | During discovery, the Product Manager. During delivery, any agent, through the question queue (ADR-0031) |
| Decide | Agent | Choose an option; approve the requirement; approve a plan; extend a budget; resume or terminate a suspended agent; choose what to do about an outage | The role that raised it |
| Inform | Either | Status, cost so far, what is blocked, "why did you conclude this?" | Answered from audit and ledger |
| Steer or stop | Human | Change scope, reprioritise, pause, cancel | Product Manager for scope; kill switch for stop |

## Decision card

Every request for a decision carries the same seven fields, and always offers "accept the
recommendation" and "something else":

1. The question.
2. The options.
3. The recommended option, and which role recommends it.
4. The evidence.
5. What waiting costs.
6. What happens if nobody answers.
7. The deadline.

## Questions during delivery (ADR-0031)

Any agent can leave a question. Only work that depends on the answer waits.

| Field of a question | Content |
| --- | --- |
| Question, and why it matters | One sentence each |
| Options | Two to four, with the one the agent recommends |
| Kind | Proceeding ("I will assume X") or waiting ("I cannot continue") |
| Assumption if unanswered | For a proceeding question |
| What depends on it | Task ids |
| Asked by, and any agent answer so far | With role |
| Urgency and deadline | |

- The question first climbs an answer ladder of agents; a person sees what they answered and can overrule it.
- Low-urgency questions arrive as a digest. Waiting questions arrive at once.
- A person can answer with an option, accept the recommendation, or write their own answer.
- No answer by the deadline: a proceeding question keeps its assumption and the deliverable says so; a waiting question's task is reported as a gap.
- An assignment can be run unattended, in which case agents do not raise waiting questions outside the gates.

## Override (ADR-0032)

A person holding the right role can overrule a recommendation, an agent's answer, an assumption,
a Lead's decision, a failed check, a review finding, the tier, or a guardrail judgement. A reason
is mandatory. The override is recorded and shown on the deliverable. Some things cannot be
overridden through the platform at all; they are listed in ADR-0032.

## Rules

- **One place where a run pauses.** The supervisor raises every interrupt. This gives one
  decision queue per project. A question does not pause the run; the run pauses only when
  nothing can proceed.
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
