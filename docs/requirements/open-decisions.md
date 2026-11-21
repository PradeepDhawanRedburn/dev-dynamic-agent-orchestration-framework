# Open decisions

## Still open

| Decision | State | ADR | Blocks |
| --- | --- | --- | --- |
| Earned autonomy: may measured quality later relax a human gate | Deferred by the owner on 21 November 2026 | [ADR-0023](../adr/0023-earned-autonomy.md) | Nothing in the first release |

## Needed from the owner, though not architecture decisions

- The real engineering standards for the four DevOps skill packs, and an owner for each pack.
- Named human sponsor, deputy and security owner for the proof of concept.
- The allow-list of repositories in which the platform may open pull requests (ADR-0021).
- Budget ceilings per size tier.
- Retention periods, from records management.

## Decided on 21 November 2026

| Decision | Outcome | ADR |
| --- | --- | --- |
| Who decides | The human sponsor decides; the CTO Agent only recommends | [ADR-0008](../adr/0008-humans-decide.md) |
| Independent review | A permanent Reviewer | [ADR-0009](../adr/0009-permanent-reviewer.md) |
| Hosting | Azure only, with Microsoft Foundry for models and tracing; LangSmith optional | [ADR-0014](../adr/0014-azure-and-foundry.md) |
| Guardrail Manager placement | One per Lead, with direct escalation to the security owner. The architect recommended one for the platform | [ADR-0010](../adr/0010-guardrail-manager-placement.md) |
| Pull requests | Opened without per-request human approval; people review and merge. The architect recommended approval each time, and attached six mandatory conditions | [ADR-0021](../adr/0021-pull-request-approval.md) |
| Scope | Technology assignments only for now; business later | [ADR-0022](../adr/0022-assignment-scope.md) |
