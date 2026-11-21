# Role skills

A role skill is a short, versioned block of know-how added to a permanent agent's prompt. It
changes on its own schedule, separately from the role's prompt (ADR-0027).

Not to be confused with **skill packs** (`docs/architecture/skill-packs.md`), which give
technology expertise to temporary specialists.

| Kind | Holds | Written by |
| --- | --- | --- |
| `method` | How to do the role's job well. General practice | The architect; drafts are here |
| `organisation` | Your organisation's own rules and standards | A named owner in your organisation |

## Which role has which skill

| Role | Method skills | Organisation skills |
| --- | --- | --- |
| Product Manager | [requirement-framing](requirement-framing.md) | none |
| CTO Agent | none | [engineering-principles](engineering-principles.md) |
| Head of Delivery | none | none |
| Solution Architect | [solution-design](solution-design.md) | [engineering-principles](engineering-principles.md), [azure-reference-architecture](azure-reference-architecture.md) |
| AI Specialist | [ai-evaluation-and-risk](ai-evaluation-and-risk.md) | [approved-ai-models-and-standards](approved-ai-models-and-standards.md) |
| Lead | none; its domain profile and the specialists' skill packs carry the expertise | none |
| Tester | [test-design](test-design.md) | none |
| Reviewer | [independent-review](independent-review.md) | none |
| Guardrail Manager | [guardrail-judgement](guardrail-judgement.md) | [security-and-data-policy](security-and-data-policy.md) |
| Delivery Controller | none; it only narrates figures computed by code | none |
| Recruiter | none; its work is code | none |
| Knowledge Steward | [retrospective](retrospective.md) | none |

## Rules

- A skill's text is appended to the system prompt after the role's own text, in the order listed in the agent's `skills` front matter.
- A skill with `status: needs-content` is never loaded. The agent runs without it and the run records that.
- A skill gives knowledge. It never grants a tool or authority.
- Limit: 2,500 characters per skill. Longer material belongs in organisational memory, read with a tool.
- A change bumps `version` and goes through a pull request and the evaluation gate, like a prompt.

## Status

The seven method skills are the architect's first drafts and have not been evaluated. The four
organisation skills are empty templates.
