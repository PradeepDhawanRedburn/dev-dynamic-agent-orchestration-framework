# ADR-0027: Permanent agents have role skills and a tool catalogue

- **Status:** Accepted
- **Decided:** Accepted on 22 November 2026 by the architect, under authority the repository owner delegated that day to take the decisions blocking implementation
- **Date:** 2026-11-21

## Context

Permanent agents named tools in their definitions, but no document said what each tool does.
Their know-how sat entirely inside the system prompt, mixing three things that change at
different rates and have different owners: the role, general method, and the organisation's own
standards. The owner asked what skills and tools each agent needs.

## Decision

1. **Tool catalogue.** `docs/architecture/tool-catalogue.md` is the contract for every tool. An agent definition may only name a tool listed there.
2. **Role skills.** A permanent agent may list skills in its front matter. A skill is a short text block in `agents/skills/`, appended to the prompt after the role's text.
3. **Two kinds.** Method skills are general practice and are drafted by the architect. Organisation skills hold the organisation's own rules and are written by a named owner.
4. **An empty organisation skill is never loaded.** The agent runs without it and the run records that it did.
5. **Lean by rule.** A role gets a skill only where it has know-how that changes separately from the role. Four roles have none.

## Consequences

- Twelve tools for permanent agents; one is new (`model_catalogue_read`).
- Seven method skills drafted, unevaluated. Four organisation skills are templates awaiting content.
- Until the organisation skills are written, the CTO Agent, Solution Architect, AI Specialist and Guardrail Manager work from general knowledge only. Their output will be generic, and the Architect's "cite the standard you applied" instruction cannot be met.
- Prompts get longer: up to 2,500 characters per skill. Cost per call rises slightly; unmeasured.
- The loader in WP-03 must assemble skills and hash them with the prompt.

## Alternatives considered

- Keep everything in the system prompt: rejected; the organisation's standards would be edited by whoever edits prompts.
- Put standards only in organisational memory and read them with a tool: kept for long material, but a role's core rules should not depend on the model choosing to look them up.
- Reuse specialist skill packs for permanent agents: rejected; packs bring tools and Tester checks, which permanent roles must not gain this way.
