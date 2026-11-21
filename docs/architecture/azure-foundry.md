# Azure and Microsoft Foundry

Everything runs in the Azure tenant. Models and tracing come from Microsoft Foundry (ADR-0014).

## First-release services

| Concern | Service |
| --- | --- |
| Orchestrator, gateway, governance services, interaction API | AKS, private cluster |
| Sandbox for static checks and code execution | Separate AKS node pool with deny-all egress |
| Models | Microsoft Foundry model deployments; at least two, so the Reviewer can use a different one |
| Workflow state, ledger, registry, audit | Azure Database for PostgreSQL Flexible Server |
| Evidence and artefacts | Blob Storage with immutability policies |
| Secrets | Key Vault; managed identities everywhere else |
| Tracing and platform telemetry | Application Insights, through the Foundry tracer |
| Identity | Microsoft Entra ID; AKS workload identity |
| Infrastructure as code | Terraform |
| CI | GitHub Actions |
| Deployment | Argo CD |

Added when measured need appears (ADR-0019): Service Bus with a transactional outbox, a durable
worker mode, a shared cache for guardrail counters and semaphores, Azure AI Search, self-hosted
LangSmith.

## Network and identity

- Private AKS API server. No public address on any node or data service.
- Private endpoints for PostgreSQL, Blob, Key Vault and Foundry.
- Network policy: only the tool gateway reaches the egress proxy and enterprise systems; the
  sandbox reaches nothing.
- Agents get no Entra identities. The gateway issues short-lived scoped tokens that expire with
  the task, and alone holds the identities that reach enterprise systems.

## Tracing

Microsoft documents tracing LangChain and LangGraph from a Foundry project into Application
Insights with `AzureAIOpenTelemetryTracer` from the `langchain-azure-ai` package
([Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/langchain-traces),
read 21 November 2026). That is the default. The portal view for agent traces was labelled
preview on that date.

Every run carries: `project_id`, `correlation_id`, `workstream_id`, `task_id`, `agent_id`,
`agent_role`, `graph_version`, `policy_version`, `prompt_sha256`, `model_deployment`,
`data_classification`, `environment`. Prompts and outputs are redacted or hidden for
Confidential projects.

## Capacity

The binding limit is model throughput. Capacity planning and admission control are built around
tokens per minute per deployment, with a per-sponsor allowance, not around pod count.

## Not verified

- The chat-model class in `langchain-azure-ai` for Foundry deployments. The draft in
  `reference/lg/app.py` still uses `AzureChatOpenAI` and a LangSmith tracer.
- How Foundry's evaluation features compare with LangSmith's.
- Which web-search service to use for research. Queries leave the network whichever is chosen,
  so it is an item for the security review.
- Specific redundancy options and tiers for the chosen regions.
