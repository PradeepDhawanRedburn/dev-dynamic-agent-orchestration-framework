# ADR-0013: Skill packs provide specialisation

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

The owner expects real specialisation, first in DevOps: Azure, Terraform, Argo CD, GitHub Actions. The brief also says no specialist agents are predefined.

## Decision

A skill pack is a reviewed, versioned bundle of standards, read-only capability tags, reference collections, Tester checks and forbidden actions. The Recruiter attaches up to three to a temporary specialist. Standards text comes from the library, never from a model, and sits in the prompt before the task brief.

## Consequences

- Agents remain per-task and disposable; expertise is now pre-built.
- Each pack needs a human owner and the team's real standards.
- A pack can never yield a consequential tool; this is tested.

## Alternatives considered

- Permanent specialist agents per technology: rejected. It grows the permanent organisation with every tool.
