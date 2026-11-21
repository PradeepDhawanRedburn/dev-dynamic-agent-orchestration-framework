# Architecture overview

One fixed LangGraph supervisor graph runs twelve permanent roles. Specialists are data: a validated
specification run by one shared worker. Everything that controls cost, access and autonomy is code.

Diagrams: [platform](diagrams/platform-overview.html) · [assignment flow](diagrams/assignment-flow.html) · [agent lifecycle](diagrams/agent-lifecycle.html)

More detail: [roles](roles.md) · [runtime design](runtime-design.md) · [governance and security](governance-and-security.md) · [skill packs](skill-packs.md) · [interaction layer](interaction-layer.md) · [Azure and Foundry](azure-foundry.md)

## Principles

1. **Static graph, dynamic data.** No node, edge or code is created at runtime (ADR-0001).
2. **No function checks its own work.** Deliver never tests, reviews or polices itself (ADR-0007).
3. **The human's words travel verbatim.** The original request and success criteria reach every agent unchanged, alongside whatever its manager adds.
4. **Code decides, models draft.** A model returns one draft in a narrow schema. Code adds ids, budgets, ownership and consequences.
5. **Evidence by construction.** Tools issue evidence ids. A claim can cite an id; it cannot create one (ADR-0004).
6. **Agents cannot change your estate.** Changes arrive as pull requests that people merge (ADR-0006, ADR-0021).
7. **Proportionate.** The size of an assignment decides how many roles and gates it uses (ADR-0017).

## Five functions, twelve roles

| Function | Roles | Job |
| --- | --- | --- |
| Define | Product Manager, CTO Agent | The right problem, and technical direction |
| Deliver | Head of Delivery, Solution Architect, AI Specialist, Lead (one profile per domain), temporary specialists | The design and the work |
| Assure | Tester and Guardrail Manager (one profile each per Lead), Reviewer | Proof, challenge, and policing |
| Control | Delivery Controller, Recruiter | Budget, schedule, priority; creating and retiring specialists |
| Learn | Knowledge Steward | Prior answers and lessons |

Humans decide. See [roles.md](roles.md). Each role's system prompt is in [agents/](../../agents/README.md).

## Runtime in brief

- **Supervisor graph.** Intake, framing, plan, solution design, approval, fan-out to Leads, consolidation, review, final decision, retirement, archive.
- **Lead subgraph.** One compiled graph for every Lead profile: decompose, request specialists, reserve budget, fan out, guardrail check, evidence gate, test, review, loop or finish, retire.
- **Worker.** Builds a LangChain agent from an `AgentSpecification` and runs it. This is the only path by which a specialist executes.
- **Tool gateway.** Every tool call passes it: kill switch, grant, call limit, schema, execution with self-healing, clearance, evidence capture, audit.
- **Human gates.** Raised at the supervisor as LangGraph interrupts and shown through the interaction layer.

See [runtime-design.md](runtime-design.md).

## Size tiers

| Tier | When | Roles | Human gates |
| --- | --- | --- | --- |
| Small | One domain, low budget, Internal data or lower, nothing proposed for change | Product Manager, one Lead, its Tester, specialists, code controls, Knowledge Steward intake check | Confirm framing; accept result |
| Standard | Two or more domains, or mid-range budget | Adds Head of Delivery, Solution Architect, Reviewer, and the AI Specialist when the plan marks an AI component | Approve plan; accept result |
| Major | Confidential data, high budget, or any proposed change | Adds CTO Agent recommendation | Approve plan; accept result. Pull requests are opened without asking and merged by people (ADR-0021); other changes need approval |

Guardrail rules run in every tier. The first release implements Small only.

## Data stores

| Store | Holds | Technology | Authoritative |
| --- | --- | --- | --- |
| Workflow state | Requirement, plan, tasks, statuses, budgets, ledger, decisions, registry | PostgreSQL: LangGraph checkpoints plus domain tables | Yes |
| Agent working memory | One specialist's messages and notes | In-process; deleted at retirement | No |
| Organisational memory | Approved findings, decisions, standards, lessons | PostgreSQL rows; vector index derived | Rows yes |
| Evidence | Source snapshots, extracts, provenance | Blob Storage (immutable) plus PostgreSQL metadata | Yes |
| Audit | Requests, specifications, prompt hashes, tool calls, approvals, costs, retirements | Append-only PostgreSQL, hash-chained | Yes |

Graph state holds ids and statuses only; bodies live in the stores (ADR-0018). A vector index is
never the only copy of anything (ADR-0003).

## First-release platform

AKS, PostgreSQL Flexible Server, Microsoft Foundry model deployments, Blob Storage, Key Vault,
Application Insights, and an isolated sandbox node pool. Service Bus, Redis, AI Search, the
durable worker mode and self-hosted LangSmith are added when a measurement shows the need
(ADR-0019).

## Repository layout

```text
src/orchestrator/
  contracts.py  messages.py
  tools/        registry.py  gateway.py  impl/
  prompts/      compiler.py  sections/  profiles/
  skills/       library.py  packs/
  governance/   budget.py  recruiter.py  guardrails.py  resilience.py  policy.py  approvals.py
  graph/        state.py  worker.py  lead.py  supervisor.py  routing.py
  persistence/  repositories.py  migrations/
  interaction/  api.py  cards.py
  observability/ tracing.py  evaluators.py
tests/          unit/  contract/  routing/  integration/  security/
evals/          datasets/  run_offline.py
infra/          terraform/  argocd/
policy/         limits.yaml  model_catalogue.yaml  tool_registry.yaml  guardrail_rules.yaml
.github/workflows/
```

## What is proven and what is not

| Part | Evidence |
| --- | --- |
| Contracts, lifecycle, prompt compiler, tool registry, ledger, Recruiter, guardrail rules, self-healing, skill packs | 52 passing tests in `reference/` |
| Node logic and routing of the Lead subgraph and supervisor | Dry run through a stand-in runtime with scripted models (`reference/lg/dryrun.py`). Not LangGraph |
| Behaviour on real LangGraph, LangChain and Foundry | Nothing. See [the spike checklist](../plan/spike-checklist.md) |
| Product Manager, Knowledge Steward, Reviewer as a permanent role, tiers, interaction layer, requester access filtering, state by reference | Design only |
