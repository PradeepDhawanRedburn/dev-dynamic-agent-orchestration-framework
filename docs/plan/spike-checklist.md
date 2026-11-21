# Spike checklist

Assumptions the design makes about LangGraph, LangChain and Microsoft Foundry that the architect
could not run. WP-01 verifies each against installed versions and records the result in
[spike-findings.md](spike-findings.md).

Written against LangGraph 1.2.24 documentation, read 21 November 2026.

| # | Assumption | Why uncertain | If false |
| --- | --- | --- | --- |
| S-01 | `StateGraph(..., input_schema=..., output_schema=...)` limits what a subgraph returns to its parent | Keyword names from memory | Find the supported way; parallel subgraphs must not write non-reducer keys |
| S-02 | Nested fan-out works: `Send` to a subgraph that itself fans out with `Send` | Not run | Flatten to one level of fan-out |
| S-03 | `add_node(..., error_handler=...)` receives the `Send` payload as its first argument | Documentation shows `handler(state, error)`; payload assumed | Catch inside the node instead |
| S-04 | `Send(node, arg, timeout=TimeoutPolicy(run_timeout=...))` enforces a per-task timeout | Documented for 1.2+; not run | Use `asyncio.wait_for` inside the node |
| S-05 | A subgraph can return a `decision_needed` result and the supervisor can interrupt once, then resume the same workstream | Design choice in ADR-0016; not run | Redesign the gate; do not fall back to interrupts inside `Send` branches without testing them |
| S-06 | The node that called `interrupt()` re-runs from its first line on resume | Documented | None expected; confirm |
| S-07 | Killing the process mid-superstep and restarting does not re-run branches that completed | From general knowledge of LangGraph pending writes | Make every node idempotent regardless (already required) |
| S-08 | `AsyncPostgresSaver.from_conn_string` and `setup()` work against Azure Database for PostgreSQL with Entra authentication | Not run | Use a connection pool with a token callback |
| S-09 | `create_agent(..., response_format=ToolStrategy(Model))` returns a validated Pydantic instance under `structured_response` for a schema as large as `SpecialistOutput` | Documented for Pydantic; size not tested | Split the schema or use provider-native structured output |
| S-10 | `AgentMiddleware.abefore_model` and `aafter_model` run under `ainvoke`, and raising from a hook stops the agent | Hook names documented; behaviour on raise assumed | Use the documented jump-to-end mechanism |
| S-11 | `usage_metadata` carries `input_tokens` and `output_tokens` for Foundry model deployments | From memory | Read usage from the response metadata the provider returns |
| S-12 | A Foundry model deployment is usable from LangChain through `langchain-azure-ai`, with managed-identity authentication | Package confirmed to exist; chat-model class not checked | Use the Azure OpenAI client against the Foundry endpoint |
| S-13 | `AzureAIOpenTelemetryTracer` traces a LangGraph run with nested subgraphs into Application Insights, with our metadata keys searchable | Microsoft documents the tracer; nesting and metadata not tested | Add OpenTelemetry spans by hand around nodes |
| S-14 | `max_concurrency` in the run configuration limits parallel `Send` branches | From memory | Enforce concurrency with a semaphore in the node |
| S-15 | Mounting one compiled subgraph under two node names keeps checkpoint namespaces distinct | Believed allowed | Compile the subgraph twice |
| S-16 | `with_structured_output(schema, include_raw=True)` returns `raw`, `parsed` and `parsing_error` | From memory | Read usage another way |

## Also in the spike

- Measure checkpoint size and write latency for a ten-task workstream with state held by reference.
- Measure model calls and cost per role for one Small assignment.
- Confirm which sandbox approach the platform team will support.
- Start the mapping of this design to the firm's model-risk, outsourcing, records and
  operational-resilience policies, with risk and compliance.
