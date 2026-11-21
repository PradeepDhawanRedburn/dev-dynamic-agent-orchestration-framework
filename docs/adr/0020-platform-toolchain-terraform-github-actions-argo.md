# ADR-0020: Platform toolchain: Terraform, GitHub Actions, Argo CD

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

The owner's team uses these tools.

## Decision

Infrastructure is Terraform. CI is GitHub Actions, authenticating to Azure by workload identity federation. Deployment to AKS is by Argo CD from Git.

## Consequences

- The platform's own delivery follows the standards its skill packs teach.
