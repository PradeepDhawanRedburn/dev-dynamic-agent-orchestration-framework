# ADR-0033: Decisions from the architecture spike

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

WP-01 tested 26 assumptions against the pinned libraries and a Microsoft Foundry resource
(`docs/plan/spike-findings.md`). Sixteen held, two held with a rule, six held in part and two did
not hold. Three rows could not be fully tested for lack of Azure resources. This ADR records what
the architect decided from each finding that changes the design. Issue numbers are in the
repository.

## Decision

**Graphs**

1. Every subgraph run under `Send` declares an `output_schema` (S-01).
2. Every node is async, and every node that is a `Send` target has an error handler. A timeout without one fails the whole run (S-03, S-04).
3. Durability mode `exit` is never used. Nodes stay idempotent: a kill between a node returning and its write being stored is not protected (S-07).
4. Graph state holds only JSON primitives, lists and dicts. No Pydantic objects and no custom classes; an enumeration is stored as its string value. `LANGGRAPH_STRICT_MSGPACK` is set to true (issue 4).
5. ADR-0016 is unchanged. Interrupts inside parallel branches were found to work, so raising every gate at the supervisor is now a choice for one decision queue, not a workaround (S-05).

**Checkpoint encryption** (issue 4; amends ADR-0029 point 6)

6. The encrypted serialiser stays on, but it is defence in depth, not the control. It leaves strings, numbers and booleans held directly in state unencrypted.
7. The control is ADR-0018, tightened: state holds identifiers, statuses and counters only. No requirement text, prompt, result, answer or personal data is ever a state value. A test checks the state models for free-text fields.
8. Database encryption at rest covers the remainder. `pycryptodome` becomes a runtime dependency.

**Models** (issue 5)

9. The model catalogue records, per model: deployment name, which API to use (chat completions or Responses), the API version value, reasoning effort, the highest data classification, and cost band. Code reads these; nothing is hard-coded.
10. The two newer deployments tested need the Responses API for tool use and structured output. The API version is `v1`; dated versions are rejected.
11. Reasoning effort is set per role. On a small call roughly half the output tokens were reasoning, so it dominates cost; the default is the lowest setting that passes evaluation.
12. A prompt blocked by the provider's content filter is a refusal: never retried, recorded as a guardrail event, and the task fails to its Lead (S-23).

**Tracing** (issue 3; amends ADR-0029 point 3)

13. The Foundry tracer is kept for the connected trace. It does not carry the platform's identifiers, so the platform adds them itself as span attributes through OpenTelemetry. How (a span processor, or spans the platform opens around nodes) is settled by a test in WP-10; this is not yet verified.
14. Every audit event stores the trace id and span id current when it was written. That link does not depend on span attributes.
15. Content recording is all or nothing in this tracer. It is **off by default** and turned on per run only where the data classification allows it. Masking, if wanted, is done in the collector later (action H-19).
16. `langchain-azure-ai[opentelemetry]` becomes a runtime dependency.

**Middleware** (issue 6; amends `docs/governance/lang-family-controls.md`)

17. The rule is an allow-list: a built specialist may contain only the allowed middleware classes, checked by class name. The deny-list is kept as explanation. Two names on it do not exist in the pinned LangChain; they came from documentation for another package.
18. Order, outermost first: budget metering, call limits, PII, model fallback, model retry, model refusal, tool retry, tool error. With fallback outside retry, the primary model is retried before the fallback is used.
19. `ToolErrorMiddleware` always returns content from its handler, so a tool failure never escapes as an exception.
20. `PIIMiddleware` settings are stated explicitly for input, output and tool results; no default is relied on. Tool results are not altered, because the gateway has already captured them as evidence.
21. A structured-output validation error comes back as a tool message marked as success. Code counts these itself and does not trust the status.

**LangSmith** (issues 2 and 8)

22. No code constructs a LangSmith client, and no test uses the `langsmith` marker; both make a network call with nothing configured. A test enforces each.
23. `reference/lg/app.py` is deleted. It was the architect's draft and contacted LangSmith when imported. The composition root is written in WP-05 from the ADRs.

**Questions and pausing** (S-25, S-26; adds to ADR-0031)

24. The scheduler is a node that reads the question store at its top, decides, and calls `interrupt()` at most once per execution. A resume value is only a wake-up; answers come from the store. Task status in state uses a merging reducer.

## Consequences

- ADR-0029 points 3 and 6 are amended by this ADR.
- Three rows remain untested and are carried forward: PostgreSQL with Entra authentication (WP-12), Foundry with managed identity (WP-12), export to Application Insights (WP-10). Each needs an Azure resource (action H-28).
- The PostgreSQL driver is LGPL-3.0 (issue 7). That is a question for Legal (action H-18). The design does not change unless Legal objects; the checkpointer requires this driver.
- Local measurements showed about 5 KB of checkpoints per ten-task workstream with state by reference, against about 405 KB with bodies in state. ADR-0018 is confirmed on size. Latency on Azure is unmeasured.
- Cost per role is still unmeasured.

## Alternatives considered

- Encrypt primitives by wrapping the serialiser: rejected for now; more code in a security-sensitive place, when keeping content out of state removes the need.
- Rename identifiers with the `gen_ai.` prefix so the tracer carries them: rejected; they would appear on agent spans only, and it misuses a reserved namespace.
- Drop the Foundry tracer for plain OpenTelemetry: kept as the fallback if point 13 cannot be made to work.
