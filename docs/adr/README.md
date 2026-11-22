# Architecture decision records

One decision per file. A decision is **Proposed** until the repository owner accepts it, and **Deferred** when the owner has chosen to decide later.

- **Accepted** means the owner approved it in the design review of 21 November 2026, either explicitly or by adopting the revision that contains it.
- An Accepted ADR is never edited to change its meaning. To change a decision, add a new ADR that supersedes it and mark the old one `Superseded by ADR-NNNN`.
- Implementers who find an ADR unworkable open an issue labelled `architecture-question`.

| ADR | Decision | Status |
| --- | --- | --- |
| [0001](0001-static-graph-topology-variability-is-data.md) | Static graph topology; variability is data | Accepted |
| [0002](0002-specialists-run-as-one-parameterised-worker-laun.md) | Specialists run as one parameterised worker launched with Send | Accepted |
| [0003](0003-postgresql-is-the-system-of-record.md) | PostgreSQL is the system of record | Accepted |
| [0004](0004-evidence-by-construction.md) | Evidence by construction | Accepted |
| [0005](0005-budget-is-a-ledger-with-reservations.md) | Budget is a ledger with reservations | Accepted |
| [0006](0006-agents-hold-no-consequential-tools-changes-reach.md) | Agents hold no consequential tools; changes reach the estate as pull requests | Accepted |
| [0007](0007-five-functions-and-ten-roles.md) | Five functions and ten roles | Accepted, amended by 0026 |
| [0008](0008-humans-decide.md) | Humans decide; the CTO Agent recommends | Accepted |
| [0009](0009-permanent-reviewer.md) | A permanent independent Reviewer | Accepted |
| [0010](0010-guardrail-manager-placement.md) | Guardrail Manager placement: one per Lead | Accepted |
| [0011](0011-guardrail-rules-decide-a-model-can-only-tighten.md) | Guardrail rules decide; a model can only tighten; suspension is reversible | Accepted |
| [0012](0012-the-tester-writes-checks-first-and-a-failed-test.md) | The Tester writes checks first, and a failed test forces a revision | Accepted |
| [0013](0013-skill-packs-provide-specialisation.md) | Skill packs provide specialisation | Accepted |
| [0014](0014-azure-and-foundry.md) | Azure only, with Microsoft Foundry for models and tracing | Accepted |
| [0015](0015-self-healing-by-approved-runbook.md) | Self-healing by approved runbook | Accepted |
| [0016](0016-human-gates-are-raised-at-the-supervisor-through.md) | Human gates are raised at the supervisor through one interaction layer | Accepted |
| [0017](0017-assignment-size-tiers.md) | Assignment size tiers | Accepted |
| [0018](0018-state-holds-references-consolidation-is-staged.md) | State holds references; consolidation is staged | Accepted |
| [0019](0019-lean-first-release-platform.md) | Lean first-release platform | Accepted |
| [0020](0020-platform-toolchain-terraform-github-actions-argo.md) | Platform toolchain: Terraform, GitHub Actions, Argo CD | Accepted |
| [0021](0021-pull-request-approval.md) | The platform opens pull requests without per-request human approval | Accepted |
| [0022](0022-assignment-scope.md) | Assignment scope is technology only, for now | Accepted |
| [0023](0023-earned-autonomy.md) | Earned autonomy | Deferred |
| [0024](0024-retrieval-respects-the-requesting-human-s-access.md) | Retrieval respects the requesting human's access rights | Accepted |
| [0025](0025-agent-definitions-are-versioned-files.md) | Permanent agents are defined in versioned files | Accepted |
| [0026](0026-solution-architect-and-ai-specialist.md) | Add a Solution Architect and an AI Specialist | Accepted |
| [0027](0027-role-skills-and-tool-catalogue.md) | Permanent agents have role skills and a tool catalogue | Proposed |
| [0028](0028-discovery-stage-and-requirement-baseline.md) | A discovery stage and an approved requirement baseline before any delivery | Accepted |
| [0029](0029-use-of-the-langchain-family.md) | How the LangChain family of tools is used | Proposed |
| [0030](0030-reasoning-patterns.md) | Which reasoning patterns the platform uses | Proposed |
| [0031](0031-questions-without-stopping-the-run.md) | Agents can ask a person a question without stopping the run | Accepted |
| [0032](0032-human-override.md) | A person can override an agent, with a reason, on the record | Accepted |
| [0033](0033-decisions-from-the-architecture-spike.md) | Decisions from the architecture spike | Accepted |
| [0034](0034-store-access-and-limits-of-the-audit-record.md) | Store access from async nodes, and what the audit record proves | Accepted |

New ADRs use [template.md](template.md).
