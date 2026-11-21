# ADR-0014: Azure only, with Microsoft Foundry for models and tracing

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

The organisation is a Microsoft house. LangSmith's cloud service runs outside Azure.

## Decision

Nothing runs or is stored outside the Azure tenant. Model deployments come from the Foundry project. Traces go through the Foundry tracer into Application Insights. LangSmith is optional and, if used, self-hosted on AKS. LangGraph and LangChain remain the orchestration stack.

## Consequences

- No extra licence is needed for tracing.
- The audit store never depends on the tracing tool.
- The Foundry chat-model class and evaluation features are not yet verified; see the spike checklist.
- Approved by the repository owner on 21 November 2026.

## Alternatives considered

- LangSmith cloud: excluded by residency.
- Self-hosted LangSmith as the default: deferred; adds services to operate.
