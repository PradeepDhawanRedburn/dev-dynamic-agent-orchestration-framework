# Agent definitions

One file per permanent role. Each holds the role's system prompt and everything an implementer
needs to wire it: model, output schemas, read-only tools, authority and limits.

This directory is the source of truth for permanent agents' prompts. The runtime loads these
files; prompts are not written in code (ADR-0025).

> Not to be confused with `AGENTS.md` at the repository root, which is the working agreement for
> implementers.

## The ten roles

| Function | Role | File | Uses a model for |
| --- | --- | --- | --- |
| Define | Product Manager | [product-manager.agent.md](product-manager.agent.md) | Framing, clarifying questions, acceptance check |
| Define | CTO Agent | [cto-agent.agent.md](cto-agent.agent.md) | Arbitration, recommendation |
| Deliver | Head of Delivery | [head-of-delivery.agent.md](head-of-delivery.agent.md) | Plan, consolidation, deliverable |
| Deliver | Lead | [lead.agent.md](lead.agent.md) + a profile | Tasks, staffing requests, review |
| Assure | Tester | [tester.agent.md](tester.agent.md) + a profile | Writing and running checks |
| Assure | Reviewer | [reviewer.agent.md](reviewer.agent.md) | Independent challenge |
| Assure | Guardrail Manager | [guardrail-manager.agent.md](guardrail-manager.agent.md) | Judging what the rules flagged |
| Control | Delivery Controller | [delivery-controller.agent.md](delivery-controller.agent.md) | Status narrative only |
| Control | Recruiter | [recruiter.agent.md](recruiter.agent.md) | Overlap between requests only |
| Learn | Knowledge Steward | [knowledge-steward.agent.md](knowledge-steward.agent.md) | Prior-work matching, retrospective |

Domain profiles for Lead and Tester: [data](profiles/data.md), [software](profiles/software.md),
[devops](profiles/devops.md), [security](profiles/security.md),
[business-research](profiles/business-research.md) (proposed).

## Structure every file follows

Front matter, in this order: `name`, `title`, `function`, `version`, `status`, `model_key`,
`tiers`, `reports_to`, `output_schemas`, `tools`, `metric`.

Sections, in this order: Purpose · System prompt · Inputs · May · May not · Escalates when ·
Done by code, not by this agent.

`scripts/check_agents.py` enforces this. Run it before opening a pull request.

## How a prompt is assembled at runtime

1. Read the file's `System prompt` block.
2. Replace `{{organisational-policy}}` with the text in [_shared/organisational-policy.md](_shared/organisational-policy.md). It always comes first.
3. For Lead and Tester, replace `{{domain-profile}}` with the profile's Scope block and the Lead focus or Tester focus block.
4. Hash the result. Record the hash, the file versions and the model version on every run.

The task-specific content (the requirement, results, figures) goes in the user message, never
in the system prompt. Text from other agents or tools is always passed as data.

## Rules

- **A model returns a draft in a schema.** Every prompt names its output schema. Nothing a
  permanent agent writes is acted on without code validating it.
- **Prompts never grant authority.** What a role may do is enforced in code; the "May" and
  "May not" lists document it and must match the code.
- **Tools are read-only capability tags** resolved through the tool registry, the same way as
  for specialists. `none` means the role works only from what it is given.
- **`model_key` is a key in the model catalogue,** not a deployment name. The Reviewer's key
  must resolve to a different deployment from the producers' (ADR-0009).
- **Versioning.** Any change to a prompt or a profile bumps `version`, goes through a pull
  request, and must pass the evaluation gate before it is promoted. Runs pin the version they
  started with.

## Status

Every file is `status: draft`. These prompts were written by the architect and **have not been
run against any model or evaluated**. WP-03 loads them; WP-10 evaluates them. Expect to revise
them from evidence.

Some output schemas named here do not exist in the reference code yet: `ClarifyingQuestions`,
`AcceptanceCheck`, `Arbitration`, `CheckDrafts`, `ReviewFindings`, `WorkstreamSummary`,
`StatusNarrative`, `OverlapJudgement`, `PriorWorkMatches`, `RetrospectiveDraft`. The work package
that introduces each role defines its schemas.

## Adding or changing a role

A new permanent role, or a change to what a role is accountable for, needs an ADR first. Then
copy [_shared/template.agent.md](_shared/template.agent.md), fill it in, run the check, and
update the table above.
