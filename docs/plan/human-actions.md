# Actions that need a person

Things the architect cannot define, because they are your organisation's knowledge, decisions or
access. Each has an id cited by the tool catalogue, the skills and the work packages.

**Do first:** H-14, H-06, H-08 and H-10 block the first release (Small tier). H-16 is a quick decision.

| Id | Action | Who (role) | How | Until it is done | Blocks |
| --- | --- | --- | --- | --- | --- |
| H-01 | Write the engineering principles and standards | Head of architecture or CTO | Fill `agents/skills/engineering-principles.md`: numbered rules with ids, under 2,500 characters. Put the full standards into organisational memory (see H-12). Open a pull request. | CTO Agent and Solution Architect give generic advice | WP-11 |
| H-02 | Write the Azure reference architecture summary | Cloud platform owner | Fill `agents/skills/azure-reference-architecture.md` from your landing zone documents: approved regions and services, network, identity, tagging and naming rules. | Solution Architect cannot design to your platform | WP-11 |
| H-03 | Decide the approved AI models and AI rules | AI lead, with the security owner | Fill `agents/skills/approved-ai-models-and-standards.md`. Separately list each approved model with purpose and the highest data classification it may receive; the implementer turns that list into the model catalogue. | AI Specialist has nothing to recommend from; `model_catalogue_read` is empty | WP-03, WP-11 |
| H-04 | Write the security and data handling rules for agents | Security owner | Fill `agents/skills/security-and-data-policy.md`. Also confirm or correct the rule list in `docs/architecture/governance-and-security.md`; those rules become the guardrail rule engine. | Guardrail rules are the architect's guess | WP-06 |
| H-05 | Supply real standards for the four DevOps skill packs, and name an owner for each | DevOps lead | For Azure, Terraform, Argo CD and GitHub Actions: replace the illustrative standards in `docs/architecture/skill-packs.md`, and list the linters and rule sets the sandbox may run. | Specialists follow illustrative standards | WP-08 |
| H-06 | Name the sponsor, a deputy and the security owner for the proof of concept | Repository owner | Add the three names and how each is reached to `docs/requirements/open-decisions.md`. | No human gate can be routed | WP-05 |
| H-07 | Choose the repositories where the platform may open pull requests, and protect them | DevOps lead and security owner | List the repositories. On each: require one human review, block direct pushes to the main branch. Create the platform's GitHub identity with rights to create branches and pull requests only. Read ADR-0021 first. | No pull requests can be opened safely | WP-08, WP-12 |
| H-08 | Set budget ceilings per size tier | Sponsor | Give a maximum cost for a Small, Standard and Major assignment. A rough first figure is enough; it is revised from measurements. | Tier rules and budget gates have no numbers | WP-05 |
| H-09 | Confirm retention periods | Records management | State how long audit records, evidence, deliverables and traces are kept, and whether any must be deleted on request. | Storage lifecycle cannot be configured | WP-12 |
| H-10 | Approve an internet search service and an egress allow-list | Security owner | Decide which search service specialists may use and which domains they may fetch. Check the service's terms for storing results as evidence. | Specialists cannot research public sources | WP-04 |
| H-11 | Create read-only identities for the estate | Cloud platform owner | Managed identities with read-only roles for Azure resource and cost queries, a read-only Argo CD account, and read access to the chosen repositories and pipeline results. Scope each to the minimum. Exact role names should be checked against current Microsoft and Argo CD documentation. | DevOps specialists see nothing real | WP-08, WP-12 |
| H-12 | Seed organisational memory and name a curator | Head of architecture | Collect existing standards, decision records and reference designs. Mark each with a data classification. Name the person who approves what enters memory. | `org_memory_read` and `org_memory_search` return nothing | WP-02, WP-11 |
| H-13 | Provide evaluation examples | Each Lead's human counterpart | Ten to twenty past assignments per domain, each with the request and what a good answer contained. Remove confidential data or mark its classification. | No prompt or skill can be evaluated; all stay drafts | WP-10 |
| H-14 | Provision Microsoft Foundry | Cloud platform owner | A Foundry project, the model deployments, and a second deployment of a different model for the Reviewer (ADR-0009). Record deployment names and quotas. | Nothing can run | WP-01 |
| H-15 | Choose and register the human channel | Repository owner | Decide Teams, a web page or both, and register the application so decision cards can be sent. | Human gates have no front door | WP-09 |
| H-16 | Decide ADR-0027 | Repository owner | Accept or change the proposal to give permanent agents role skills and a tool catalogue. | The loader in WP-03 does not know whether to assemble skills | WP-03 |

## How to hand something over

Open a pull request that changes the file named in "How", or raise an issue labelled
`scope-question` with the content and the action id. Do not send secrets, keys or connection
strings through the repository; identities and secrets are configured in Azure (WP-12).

## What the architect has defined

- The contract for every tool: [tool-catalogue.md](../architecture/tool-catalogue.md).
- Seven method skills and the templates for four organisation skills: [agents/skills/](../../agents/skills/README.md).
- Which role has which tool and skill: each file in `agents/`.
