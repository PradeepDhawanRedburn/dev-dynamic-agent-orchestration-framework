# WP-12: Platform infrastructure

- **Status:** Not started
- **Depends on:** WP-01

## Goal

The first-release platform, reproducible from Git.

## Read first

- ADR-0014
- ADR-0019
- ADR-0020
- docs/architecture/azure-foundry.md

## Tasks

1. Terraform for the private AKS cluster with a sandbox node pool, PostgreSQL, Blob Storage, Key Vault, Application Insights and private endpoints, in a development environment.
2. GitHub Actions for build, scan and image publish, authenticating to Azure by workload identity federation.
3. Argo CD applications for the orchestrator and gateway.
4. Network policies: only the gateway reaches the egress proxy; the sandbox reaches nothing.

## Acceptance criteria

- [ ] A fresh environment is created from the repository with no manual step.
- [ ] No data service has public network access (verified by a policy check).
- [ ] The spike rows left untested are run and recorded: PostgreSQL with Entra authentication (S-08) and Foundry with managed identity (S-12).
- [ ] The egress proxy blocks LangSmith's hosts (tested).
- [ ] The database owner and the application use separate identities; the application cannot alter a table or disable a trigger (tested).
- [ ] The audit chain head is exported to immutable storage on a schedule and at project close; scheduled verification against the latest anchor raises an incident on failure (tested, including removal of the tail with its head).
- [ ] The application role is created by infrastructure code, not by a migration, on Azure.
- [ ] The identity used by workflows on pull requests is read-only; write access exists only behind a protected environment after merge (ADR-0021).
- [ ] The sandbox cannot resolve or reach any address (tested).

## Out of scope

Production, disaster recovery and Service Bus.
