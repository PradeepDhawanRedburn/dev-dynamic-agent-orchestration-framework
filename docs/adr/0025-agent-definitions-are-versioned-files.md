# ADR-0025: Permanent agents are defined in versioned files

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

Each permanent agent needs a system prompt. Prompts written inside code drift from the documented
role, cannot be reviewed by non-engineers, and are hard to version and evaluate. The owner asked
for a system prompt and definition file for every permanent agent.

## Decision

Every permanent role has one file, `agents/<role>.agent.md`, with fixed front matter and fixed
sections, holding its system prompt, model key, output schemas, read-only tools, authority and
limits. A shared organisational policy is placed first in every prompt. Lead and Tester take a
domain profile from `agents/profiles/`. The runtime loads these files, assembles the prompt,
hashes it and records the hash and versions on every run. `scripts/check_agents.py` enforces
the structure and runs in CI.

## Consequences

- Prompts are reviewed and versioned like code, and evaluated before promotion.
- The "May" and "May not" lists document what code enforces; they do not enforce anything themselves.
- All prompts are first drafts that have not been run against a model.
- A new role or a change of accountability needs an ADR before a file.

## Alternatives considered

- Prompts in Python modules: rejected. Harder to review and version.
- Prompts in a hosted prompt store only: rejected as the source of truth, because the repository is how requirements and architecture are communicated. A store may mirror these files.
