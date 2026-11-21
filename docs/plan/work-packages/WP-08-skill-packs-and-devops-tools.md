# WP-08: Skill packs and the first DevOps tools

- **Status:** Not started
- **Depends on:** WP-04

## Goal

A DevOps Lead can staff a specialist with the Terraform, Argo CD, GitHub Actions or Azure packs, and the result is checked and proposed as a pull request.

## Read first

- ADR-0006
- ADR-0013
- ADR-0021
- docs/architecture/skill-packs.md
- agents/profiles/devops.md

## Tasks

1. Move the four packs into `src/orchestrator/skills/packs/` and replace the illustrative standards with the team's, supplied by each pack owner.
2. Implement read-only tools: repository read, static analysis and manifest validation and workflow linting in the sandbox, pipeline results, Argo CD application status, Azure resource and cost queries.
3. Implement the action executor that opens a pull request once the Lead has accepted the change, under the six conditions in ADR-0021.
4. Define the artefact contract and record every produced file as an artefact.

## Acceptance criteria

- [ ] No pack can yield a consequential tool (tested for every pack).
- [ ] The sandbox has no credentials and no outbound network (tested).
- [ ] A Terraform change is rejected when the pipeline plan shows an unexpected destroy.
- [ ] A pull request is opened only in an allow-listed repository, from a branch the executor created, and is labelled agent-authored.
- [ ] The platform's identity cannot approve, merge or push to a protected branch (tested against a test repository).
- [ ] A workflow triggered by an agent-authored pull request has no write credentials and no deployment secrets (demonstrated).

## Out of scope

Applying, syncing, merging or triggering anything.
