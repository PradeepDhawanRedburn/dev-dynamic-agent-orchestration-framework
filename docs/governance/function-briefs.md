# Briefs by function

One section per function: what you are likely to ask, where the answer is, and what we need you
to decide. Each request has an action id in [human-actions.md](../plan/human-actions.md).

The questions under Legal and Compliance are questions, not statements of what applies.

## IT security

| You will ask | Answer |
| --- | --- |
| What runs where, and what can reach what? | [azure-foundry.md](../architecture/azure-foundry.md): private AKS, private endpoints, deny-all sandbox, one egress proxy |
| What identities exist and what can they do? | Agents have none. The gateway holds scoped identities. Read-only roles for the estate (H-11) |
| Can it change production? | No. Pull requests only; people merge (ADR-0006, ADR-0021) |
| What happens in an outage? | Approved runbooks, then a person (ADR-0015) |

**We need from you:** review of the network and identity design before WP-12 (H-20); the read-only identities (H-11); the egress allow-list (H-10).

## Information security

| You will ask | Answer |
| --- | --- |
| What data can agents see? | Only what a task's classification and the requester's access allow (ADR-0024). Tools are granted per task |
| Where do prompts and outputs go? | To Foundry model deployments in the tenant, and to traces subject to redaction |
| How is a compromised or manipulated agent contained? | It has no credentials, a short task, bounded tools, and is suspended by rule (ADR-0011) |
| Is the record tamper-evident? | Append-only, hash-chained audit, written only by governance services |
| What about prompt injection? | Treated as expected. Controls limit what a manipulated agent can do; see the control matrix |

**We need from you:** the agent security rules and classification scheme (H-04); the decision on trace content for Confidential work (H-19); a view on LangSmith (H-17); a threat-model review (H-20); review of ADR-0021 before any repository is allow-listed (H-07).

## Architecture

| You will ask | Answer |
| --- | --- |
| Does it fit our standards? | It cannot know them until they are supplied (H-01, H-02) |
| Why this stack? | ADR-0001 to ADR-0005, ADR-0014 |
| What is unproven? | [spike-checklist.md](../plan/spike-checklist.md) |
| How does it scale and what does it cost? | Bounded by model throughput; unmeasured until WP-01 |

**We need from you:** the principles and reference architecture (H-01, H-02); a seat in the review of spike findings; the decision on ADR-0027.

## Legal

Questions for you to answer; the architect does not know which apply.

- Which data protection obligations apply to prompts, outputs, evidence snapshots and traces, including retention and deletion on request?
- Do the terms for the Foundry model deployments permit the intended use, and what do they say about use of our data?
- Are evidence snapshots of public web pages and documents acceptable to store, and for how long?
- Who owns, and who is liable for, content the platform produces, including code?
- Are the open-source licences of LangGraph, LangChain and their dependencies acceptable? The licence of each resolved dependency is listed in WP-00 for your review; the architect has not verified them.
- If LangSmith is adopted, are its terms and data locations acceptable?
- Must people be told when content was produced by AI?

**We need from you:** answers recorded as issues or a document in this folder (H-18).

## Compliance

Questions for you to answer.

- Which regulations and internal policies apply to this use of AI, to outsourcing or third-party services, to record keeping and to operational resilience?
- Does the audit record meet your record-keeping requirements in content, integrity and retention?
- Which decisions require a named accountable person, and is the sponsor role sufficient?
- What must be reported, to whom, when an agent is suspended or an incident occurs?

What exists for you: the [control matrix](control-matrix.md), the [decision register](traceability-and-decisions.md), and the human gates in [delivery-lifecycle.md](../architecture/delivery-lifecycle.md).

**We need from you:** the mapping of this design to your policies (H-18); retention periods (H-09).

## AI governance

| You will ask | Answer |
| --- | --- |
| Is a human accountable for every outcome? | Yes: requirement, plan and result are approved by a named person; agents only recommend (ADR-0008) |
| Can we see why it concluded something? | Every claim links to captured evidence and to the agent, prompt and model that produced it |
| How is quality assured? | Tests written before work, an independent Reviewer on a different model, and an evaluation gate on every prompt or model change |
| Which models, and who approved them? | Only those in the model catalogue (H-03) |
| Can autonomy increase over time? | Not decided (ADR-0023, deferred). It would need your sign-off |
| What are the known limitations? | "Known gaps" in the control matrix; every prompt is an unevaluated draft |

**We need from you:** the approved model list and AI rules (H-03); risk classification of this system under your framework (H-21); agreement on evaluation thresholds (H-13); a position on ADR-0023 when it is taken up.
