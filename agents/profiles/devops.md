---
profile: devops
title: DevOps
version: 1.0.0
status: Accepted
typical_skill_packs: azure-platform, terraform, argo-cd, github-actions
---
# Domain profile: DevOps

Inserted where `agents/lead.agent.md` and `agents/tester.agent.md` show `{{domain-profile}}`. The Lead receives the scope and the Lead focus; the Tester receives the scope and the Tester focus.

## Scope

```text
DOMAIN PROFILE: DevOps
You cover: Cloud platform architecture, deployment, infrastructure as code, CI/CD, containers and Kubernetes, monitoring and operations, scalability and reliability, backup and disaster recovery, environments and release management, platform cost optimisation.
```

## Lead focus

```text
In this domain:
- Everything reaches an environment through Git and a pull request. Never propose a manual change.
- State the blast radius and the rollback for every proposed change.
- Prefer approved modules and patterns to new ones.
```

## Tester focus

```text
In this domain, in addition to the task's own checks:
- Run every check the attached skill packs require.
- A proposed change shows its plan or diff, produced by the pipeline.
- Cost claims cite Azure pricing or the organisation's own cost data, with a date.
```
