# Work packages

Each work package is one pull request's worth of implementation with acceptance criteria. Take
them in dependency order. Read [AGENTS.md](../../../AGENTS.md) first.

| Work package | Title | Depends on | Status |
| --- | --- | --- | --- |
| [WP-00](WP-00-bootstrap.md) | Bootstrap the implementation project | None | Not started |
| [WP-01](WP-01-architecture-spike.md) | Architecture spike | WP-00 | Not started |
| [WP-02](WP-02-governance-core.md) | Governance core on PostgreSQL | WP-01 | Not started |
| [WP-03](WP-03-agent-definitions-and-worker.md) | Agent definitions, worker runtime and tool gateway | WP-02 | Not started |
| [WP-04](WP-04-lead-subgraph-and-tester.md) | Lead subgraph with Tester | WP-03 | Not started |
| [WP-05](WP-05-supervisor-small-tier.md) | Supervisor graph, Small tier | WP-04 | Not started |
| [WP-06](WP-06-guardrails.md) | Guardrail rules, suspension and the human gate | WP-05 | Not started |
| [WP-07](WP-07-self-healing-and-incidents.md) | Self-healing and the incident gate | WP-05 | Not started |
| [WP-08](WP-08-skill-packs-and-devops-tools.md) | Skill packs and the first DevOps tools | WP-04 | Not started |
| [WP-09](WP-09-interaction-layer.md) | Interaction layer, first version | WP-05 | Not started |
| [WP-10](WP-10-tracing-and-evaluation.md) | Tracing and evaluation | WP-05 | Not started |
| [WP-11](WP-11-standard-tier.md) | Standard tier | WP-06, WP-09, WP-10 | Not started |
| [WP-12](WP-12-platform-infrastructure.md) | Platform infrastructure | WP-01 | Not started |

The architect updates the Status column when a pull request is merged. Statuses: Not started,
In progress, In review, Done, Blocked.

If a work package is too large for one pull request, say so in an issue labelled `scope-question`
before splitting it.
