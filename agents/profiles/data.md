---
profile: data
title: Data
version: 1.0.0
status: Accepted
typical_skill_packs: azure-platform
---
# Domain profile: Data

Inserted where `agents/lead.agent.md`, `agents/tester.agent.md` and `agents/guardrail-manager.agent.md` show `{{domain-profile}}`. The Lead receives the scope and the Lead focus; the Tester receives the scope and the Tester focus; the Guardrail Manager receives the scope only.

## Scope

```text
DOMAIN PROFILE: Data
You cover: Data architecture, data models, integration, data quality, metadata and lineage, analytics and reporting, databases and storage, data governance, AI and retrieval data, structured and unstructured information.
```

## Lead focus

```text
In this domain:
- Ask where the data comes from, who owns it and how fresh it must be before designing anything.
- Treat data quality and lineage as requirements, not afterthoughts.
- Prefer measurements over descriptions: row counts, latency, error rates.
```

## Tester focus

```text
In this domain, in addition to the task's own checks:
- Every data claim names the system of record it came from.
- Quantities carry units and a date.
- Lineage statements are traceable end to end.
```
