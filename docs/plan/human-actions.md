# Actions that need a person

Things the architect cannot define, because they are your organisation's knowledge, decisions or
access. Each has an id cited by the tool catalogue, the skills and the work packages.

**Do first:** H-14, H-06, H-08 and H-10 block the first release (Small tier). H-16 and H-22 are quick decisions. H-17 to H-21 are for the group functions; see [docs/governance/](../governance/README.md).

| Id | Action | Who (role) | How | Until it is done | Blocks |
| --- | --- | --- | --- | --- | --- |
| H-01 | Write the engineering principles and standards | Head of architecture or CTO | Fill `agents/skills/engineering-principles.md`: numbered rules with ids, under 2,500 characters. Put the full standards into organisational memory (see H-12). Open a pull request. | CTO Agent and Solution Architect give generic advice | WP-11 |
| H-02 | Write the Azure reference architecture summary | Cloud platform owner | Fill `agents/skills/azure-reference-architecture.md` from your landing zone documents: approved regions and services, network, identity, tagging and naming rules. | Solution Architect cannot design to your platform | WP-11 |
| H-03 | Decide the approved AI models and AI rules | AI lead, with the security owner | Fill `agents/skills/approved-ai-models-and-standards.md`. Separately list each approved model with purpose and the highest data classification it may receive; the implementer turns that list into the model catalogue. | AI Specialist has nothing to recommend from; `model_catalogue_read` is empty | WP-03, WP-11 |
| H-04 | Write the security and data handling rules for agents | Security owner | Fill `agents/skills/security-and-data-policy.md`. Also confirm or correct the rule list in `docs/architecture/governance-and-security.md`; those rules become the guardrail rule engine. | Guardrail rules are the architect's guess | WP-06 |
| H-05 | Supply real standards for the four DevOps skill packs, and name an owner for each | DevOps lead | For Azure, Terraform, Argo CD and GitHub Actions: replace the illustrative standards in `docs/architecture/skill-packs.md`, and list the linters and rule sets the sandbox may run. | Specialists follow illustrative standards | WP-08 |
| H-06 | Name the sponsor, a deputy and the security owner for the proof of concept | Repository owner | Add the three names and how each is reached to `docs/requirements/open-decisions.md`. | No human gate can be routed | WP-05 |
| H-07 | Choose the repositories where the platform may open pull requests, and protect them | DevOps lead and security owner | List the repositories. On each: require one human review, block direct pushes to the main branch. Create the platform's GitHub identity with rights to create branches and pull requests only. Read ADR-0021 first. | No pull requests can be opened safely | WP-08, WP-12 |
| H-08 | Set budget ceilings per size tier | Sponsor | Give a maximum cost for a Small, Standard and Major assignment, and a smaller ceiling for the discovery stage of each. A rough first figure is enough; it is revised from measurements. | Tier rules and budget gates have no numbers | WP-05 |
| H-09 | Confirm retention periods | Records management | State how long audit records, evidence, deliverables and traces are kept, and whether any must be deleted on request. | Storage lifecycle cannot be configured | WP-12 |
| H-10 | Approve an internet search service and an egress allow-list | Security owner | Decide which search service specialists may use and which domains they may fetch. Check the service's terms for storing results as evidence. | Specialists cannot research public sources | WP-04 |
| H-11 | Create read-only identities for the estate | Cloud platform owner | Managed identities with read-only roles for Azure resource and cost queries, a read-only Argo CD account, and read access to the chosen repositories and pipeline results. Scope each to the minimum. Exact role names should be checked against current Microsoft and Argo CD documentation. | DevOps specialists see nothing real | WP-08, WP-12 |
| H-12 | Seed organisational memory and name a curator | Head of architecture | Collect existing standards, decision records and reference designs. Mark each with a data classification. Name the person who approves what enters memory. | `org_memory_read` and `org_memory_search` return nothing | WP-02, WP-11 |
| H-13 | Provide evaluation examples | Each Lead's human counterpart | Ten to twenty past assignments per domain, each with the request and what a good answer contained. Remove confidential data or mark its classification. | No prompt or skill can be evaluated; all stay drafts | WP-10 |
| H-14 | Provision Microsoft Foundry | Cloud platform owner | A Foundry project, the model deployments, and a second deployment of a different model for the Reviewer (ADR-0009). Record deployment names and quotas. | Nothing can run | WP-01 |
| H-15 | Choose and register the human channel | Repository owner | Decide Teams, a web page or both, and register the application so decision cards can be sent. | Human gates have no front door | WP-09 |
| H-16 | Decide ADR-0027 | Repository owner | Accept or change the proposal to give permanent agents role skills and a tool catalogue. | The loader in WP-03 does not know whether to assemble skills | WP-03 |
| H-17 | Decide on LangSmith | Information security, with the repository owner | Read the LangSmith section of `docs/governance/lang-family-controls.md`. Choose: none, or self-hosted on AKS. If self-hosted, ask the vendor about the Enterprise licence and its cost. | Evaluation and review tooling is undecided | WP-10 |
| H-18 | Answer the Legal and Compliance questions | Legal; Compliance | Work through the questions in `docs/governance/function-briefs.md`. Include the LGPL-3.0 PostgreSQL driver (issue 7). Record answers as a document in `docs/governance/` or as issues. State which regulations and policies apply. | The platform cannot be assessed for production use | Phase 5; retention blocks WP-12 |
| H-19 | Decide what trace content is stored for Confidential work | Information security | Choose: full content, masked content, or hashes only. Applies per data classification. | Tracing for Confidential assignments stays off | WP-10 |
| H-20 | Review the security design and threat model | IT security; information security | Review `docs/architecture/governance-and-security.md`, `azure-foundry.md` and the control matrix. Raise findings as issues labelled `risk`. Schedule penetration and red-team testing before production. | Security is self-assessed by the architect only | WP-12; Phase 5 |
| H-21 | Classify the system under your AI governance framework | AI governance | Assess risk level, required oversight and documentation. Confirm the human gates are sufficient. Agree evaluation thresholds with the Leads' human counterparts. | No AI governance approval | Phase 5 |
| H-22 | Decide ADR-0029 | Repository owner | Accept or change the proposed use of the LangChain family. | Implementers lack the middleware lists and tracing approach | WP-03, WP-10 |
| H-23 | Protect the `main` branch | Repository owner | In the repository settings: require a pull request before merging, require the CI check to pass, and block force pushes. Note that this also stops the architect pushing documents directly; either exempt that or have the architect use pull requests too. | Anyone with access can push unreviewed changes to a public repository | Now |
| H-24 | Say who answers which kind of question | Sponsor | Name the technical owner for technical questions, and confirm the routing in ADR-0031. Say whether assignments default to interactive or unattended. | Questions all go to the sponsor | WP-14 |
| H-25 | Confirm who may override what | Repository owner; security owner | Review the table in ADR-0032. Name the people. Say whether any override needs two people. | Override roles are the architect's proposal | WP-14 |
| H-26 | Decide ADR-0030 | Repository owner | Accept or change the architect's position on reasoning patterns. | WP-13 stays exploratory | WP-13 |
| H-27 | Rotate the Foundry API key | Repository owner | The key was pasted into the implementer's session during the spike. Regenerate it in the Foundry resource and update the local `.env`. Prefer managed identity over keys from now on. | A key that has been exposed in a chat session stays valid | Now |
| H-28 | Provide Azure resources for the three untested spike rows | Cloud platform owner | An Azure Database for PostgreSQL Flexible Server with Entra authentication; an identity with access to the Foundry resource; the Application Insights connection for the Foundry project. Non-production is fine. | Three assumptions stay unverified | WP-10, WP-12 |

## How to hand something over

Open a pull request that changes the file named in "How", or raise an issue labelled
`scope-question` with the content and the action id. Do not send secrets, keys or connection
strings through the repository; identities and secrets are configured in Azure (WP-12).

## What the architect has defined

- The contract for every tool: [tool-catalogue.md](../architecture/tool-catalogue.md).
- Seven method skills and the templates for four organisation skills: [agents/skills/](../../agents/skills/README.md).
- Which role has which tool and skill: each file in `agents/`.
