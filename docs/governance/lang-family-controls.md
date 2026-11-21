# How the LangChain family of tools is used

What each tool contributes to traceability, security, guardrails, flows and decision tracking,
and how it is enabled. No code here; implementers work from the work packages.

*Verified* means read in the vendor's documentation on 21 November 2026 (links at the end).
*To verify* means from general knowledge, to be confirmed in WP-01.

## The tools and their place

| Tool | What it is | Used here for | Runs where |
| --- | --- | --- | --- |
| LangGraph | Open-source library for stateful workflows | The fixed supervisor and Lead graphs, checkpoints, human gates | Inside the platform on AKS |
| LangChain | Open-source library for model calls and agents | Building each specialist; middleware for limits, retries and redaction | Inside the platform on AKS |
| `langchain-azure-ai` | Microsoft's integration package | Calling Foundry models; sending traces to Application Insights | Inside the platform |
| LangSmith | Commercial product: tracing, evaluation, prompt management | **Optional. A decision is needed**; see "LangSmith" below | Not inside Azure unless self-hosted |
| OpenTelemetry | Open standard for traces | The trace format, so the trace store can be changed | Application Insights |

## 1. Flows

| Need | Mechanism | Status |
| --- | --- | --- |
| A workflow that cannot be changed by a model | The graph is compiled from code. Agents are data handed to one worker node. No node is created at runtime (ADR-0001) | Design |
| Flow documentation that cannot drift from the code | Generate the diagram from the compiled graph in CI and commit it beside the hand-written one | To verify: the graph's own Mermaid export |
| Visual step-through for engineers | LangSmith Studio, if LangSmith is adopted | To verify |
| Parallel work with limits | Fan-out with `Send`, with per-branch timeouts | Verified earlier in this project for LangGraph 1.2; behaviour in WP-01 |

## 2. Decision tracking

| Need | Mechanism | Status |
| --- | --- | --- |
| A run pauses for a person and resumes only on their answer | LangGraph `interrupt()` with `Command(resume=...)`, raised only by the supervisor (ADR-0016) | Verified API; behaviour in WP-01 |
| The pause survives restarts | PostgreSQL checkpointer (`AsyncPostgresSaver`) | Verified |
| What the run looked like at any step | `get_state` and `get_state_history` return snapshots with values, next nodes, time, parent, and pending interrupts | Verified |
| A correction by an operator leaves a trace | `update_state` creates a new checkpoint and leaves the original unchanged | Verified |
| Who decided, when, on what evidence | **Not a LangGraph feature.** The platform's decision register in the audit store, written by the interaction API after it verifies the person's Entra identity | Design; WP-05, WP-09 |

Checkpoints are working state, not the record. They are pruned on a schedule, and LangGraph's
own documentation advises pruning. The decision register and audit store are the record.

## 3. Traceability

| Need | Mechanism | Status |
| --- | --- | --- |
| Every model and tool call is traced | LangChain and LangGraph emit a run tree per call | Verified |
| Traces stay in Azure | `AzureAIOpenTelemetryTracer` to Application Insights (Microsoft Learn) | Verified document; behaviour in WP-01 |
| No trace content sent to LangSmith's cloud | Either do not configure LangSmith, or set `LANGSMITH_OTEL_ONLY` so spans go only to your own collector | Verified |
| One request followed across agents | The same identifiers on every span; see [traceability-and-decisions.md](traceability-and-decisions.md) | Design; WP-10 |
| Sensitive content kept out of traces | Redaction before export; see section 4 | Verified options; WP-10 |

## 4. Security

| Need | Mechanism | Status |
| --- | --- | --- |
| Workflow state encrypted at rest beyond disk encryption | LangGraph `EncryptedSerializer`, AES key from `LANGGRAPH_AES_KEY`; the key is held in Key Vault | Verified |
| No unsafe deserialisation | Keep the default serialiser; **do not** enable `pickle_fallback` | Verified option exists; rule for implementers |
| Trace content hidden | With LangSmith: `LANGSMITH_HIDE_INPUTS`, `LANGSMITH_HIDE_OUTPUTS`, `LANGSMITH_HIDE_METADATA`, or pattern-based masking with `create_anonymizer`. With OpenTelemetry only: redaction in the collector | Verified for LangSmith; collector redaction to verify |
| Agents cannot reach systems | Not a LangChain feature. The tool gateway, network policy and the absence of credentials (ADR-0006) | Design; WP-03, WP-12 |
| Secrets never in state, prompts or traces | Rule in `AGENTS.md`; test in WP-10 that scans traces | Design |

## 5. Guardrails

Three layers. The first is the control; the other two reduce what reaches it.

| Layer | Mechanism | Decides by |
| --- | --- | --- |
| 1. Platform rules | Guardrail rule engine and tool gateway (ADR-0011) | Code |
| 2. LangChain middleware on every specialist | See the table below | Code |
| 3. Model provider filters | Microsoft Foundry content filters and prompt-attack detection | Provider; to verify what is available and configurable |

LangChain middleware, all *Verified* to exist under `langchain.agents.middleware`:

| Middleware | Use here |
| --- | --- |
| `ModelCallLimitMiddleware` | Hard ceiling on model calls per specialist |
| `ToolCallLimitMiddleware` | Hard ceiling on tool calls, overall and per tool |
| `ModelRetryMiddleware`, `ToolRetryMiddleware` | Bounded retries; the platform's self-healing routine sits above them (ADR-0015) |
| `ModelFallbackMiddleware` | Switch to an approved alternate deployment only |
| `ToolErrorMiddleware` | A tool failure becomes a message, not a crash. Needs a recent LangChain version |
| `ModelRefusalMiddleware` | A model refusal is raised as an error, so it is never read as an answer. Needs a recent LangChain version |
| `PIIMiddleware` | Redact, mask, hash or block personal data in messages. Built-in types are few (email, card number, IP address, MAC address, URL); names and account numbers need custom detectors |
| Custom `AgentMiddleware` | Budget metering, and checks before and after a specialist runs |

Middleware that must **not** be enabled, because each conflicts with an accepted decision:

| Middleware | Why not |
| --- | --- |
| `ShellToolMiddleware` | Gives an agent a shell |
| `FilesystemMiddleware`, `FilesystemFileSearchMiddleware` | File access outside the gateway |
| `SubAgentMiddleware` | Lets an agent create agents; only the Recruiter may (F-03) |
| `AutoModeMiddleware` (beta) | A model decides whether a tool call is risky; here that decision is code |
| `ModelRouterMiddleware` (beta) | A model chooses the model; here the model is fixed in the specification |
| `HumanInTheLoopMiddleware` | Pauses inside an agent; here every pause is raised by the supervisor (ADR-0016) |
| `LLMToolEmulator` | Test use only; never in a deployed environment |

WP-03 must test that none of these is present in a built specialist.

## 6. Evaluation

| Need | Mechanism | Status |
| --- | --- | --- |
| A prompt or model change is measured before release | Datasets and evaluators run in CI; a missed threshold blocks the merge (WP-10) | Design |
| Tooling | Foundry evaluation, LangSmith evaluation, or plain test code. Not chosen | To verify; decision H-17 |
| Human review of samples | An annotation queue in LangSmith if adopted; otherwise a simple review page | To verify |

## LangSmith: a decision is needed

LangSmith is the part of the family that is a hosted product. Facts, all *Verified*:

- LangSmith Cloud runs in the US, the Netherlands and Sydney on Google Cloud, and in the US on AWS. There is no Azure region and no UK region.
- Self-hosted LangSmith runs on AKS with Azure Database for PostgreSQL, Azure Managed Redis, Blob Storage and ClickHouse. It is an add-on to the Enterprise plan and needs a licence key.
- Self-hosted includes observability, evaluation and prompt engineering.

| Option | Gives | Costs |
| --- | --- | --- |
| A. No LangSmith. OpenTelemetry to Application Insights | Tracing inside Azure, no new vendor | Evaluation and review tooling must come from Foundry or be built |
| B. Self-hosted LangSmith on AKS | Tracing, evaluation, prompt management, inside the tenant | A licence, and four more services to run, including ClickHouse |
| C. LangSmith Cloud, EU region | The same, with nothing to run | Prompts, outputs and metadata leave Azure, unless hidden, which removes most of the value. Contradicts ADR-0014 |

The architect's recommendation is in ADR-0029: build on A so nothing depends on LangSmith, and
evaluate B during the proof of concept if a licence can be obtained. C is not recommended.

## How each is enabled

Settings only. Names are *Verified* unless marked.

| Capability | Setting or component | Where it is set |
| --- | --- | --- |
| Durable state | PostgreSQL checkpointer; tables created by its setup step | WP-02 |
| State encryption | `LANGGRAPH_AES_KEY` from Key Vault, with the encrypted serialiser | WP-02, WP-12 |
| Checkpoint pruning | A scheduled job, per the retention period | WP-12; H-09 |
| Human gates | `interrupt()` in supervisor gate nodes | WP-05 |
| Tracing to Application Insights | The Foundry tracer from `langchain-azure-ai`; the Application Insights connection comes from the Foundry project | WP-10 |
| Tracing by OpenTelemetry without LangSmith | `langsmith[otel]`, `LANGSMITH_TRACING`, `LANGSMITH_OTEL_ENABLED`, `LANGSMITH_OTEL_ONLY`, and the standard `OTEL_EXPORTER_OTLP_ENDPOINT` | Only if the Foundry tracer proves insufficient |
| Trace redaction | Hide or mask settings above, chosen by data classification | WP-10 |
| Limits, retries, PII handling | Middleware list in the specialist builder | WP-03 |
| Thread identifier | The project id; keep under 255 characters | WP-05 |

## Sources

Read 21 November 2026.

- [LangChain built-in middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in)
- [LangChain guardrails](https://docs.langchain.com/oss/python/langchain/guardrails)
- [LangGraph checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers)
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangSmith Cloud regions](https://docs.langchain.com/langsmith/cloud)
- [LangSmith self-hosted](https://docs.langchain.com/langsmith/self-hosted)
- [LangSmith self-hosted on Azure](https://docs.langchain.com/langsmith/azure-self-hosted)
- [LangSmith: mask inputs and outputs](https://docs.langchain.com/langsmith/mask-inputs-outputs)
- [LangSmith: trace with OpenTelemetry](https://docs.langchain.com/langsmith/trace-with-opentelemetry)
- [Microsoft Learn: trace LangChain and LangGraph in Foundry](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/langchain-traces)
