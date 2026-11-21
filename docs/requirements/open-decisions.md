# Open decisions

Decisions the repository owner has not yet made. Each has a Proposed ADR with the architect's
recommendation. Work packages that depend on one say so.

| # | Decision | Architect's recommendation | ADR | Blocks |
| --- | --- | --- | --- | --- |
| 1 | One Guardrail Manager for the platform, or one per Lead | One for the platform, reporting to the security owner | [ADR-0010](../adr/0010-guardrail-manager-placement.md) | WP-06 |
| 2 | Does opening a pull request need human approval every time | Every time at first; relax only through earned autonomy | [ADR-0021](../adr/0021-pull-request-approval.md) | WP-08 |
| 3 | Technology and business assignments, or technology only | Both, with a Business and Research Lead profile | [ADR-0022](../adr/0022-assignment-scope.md) | WP-11 |
| 4 | Earned autonomy: may measured quality relax a human gate | Yes, after sign-off from the governance function | [ADR-0023](../adr/0023-earned-autonomy.md) | Nothing in the first release |

Also needed from the owner, though not architecture decisions:

- The real engineering standards for the four DevOps skill packs, and an owner for each pack.
- Named human sponsor, deputy and security owner for the proof of concept.
- Budget ceilings per size tier.
- Retention periods, from records management.

## Decided on 21 November 2026

- The human sponsor decides; the CTO Agent only recommends ([ADR-0008](../adr/0008-humans-decide.md)).
- A permanent independent Reviewer ([ADR-0009](../adr/0009-permanent-reviewer.md)).
- Azure-only, with Microsoft Foundry for models and tracing; LangSmith optional ([ADR-0014](../adr/0014-azure-and-foundry.md)).
