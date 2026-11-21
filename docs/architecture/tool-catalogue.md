# Tool catalogue

Every tool an agent can be given, permanent or temporary. All are **read-only** or run in the
sandbox; none can change anything outside the platform (ADR-0006). Every call goes through the
tool gateway.

What this file defines: each tool's purpose, input, output and limits. That is the contract an
implementer builds to. What it cannot define: the implementation, and the connection to your
real systems. Those need the human actions listed in [human-actions.md](../plan/human-actions.md).

Names here are capability tags. Function names, library calls and service APIs are for the
implementer to choose and verify against current documentation.

## A. Tools for permanent agents

| Tool | Purpose | Input | Output | Reads from | Built in | Needs from a human |
| --- | --- | --- | --- | --- | --- | --- |
| `org_memory_read` | Fetch one approved item by id: a standard, decision, design or finding | Item id | The item, its classification, its version | Organisational memory (PostgreSQL) | WP-02 | Content: H-01, H-02, H-12 |
| `org_memory_search` | Find approved items relevant to a question | Query text, optional type, result limit | Ranked item ids with titles and short extracts | Organisational memory and its derived index | WP-02 | Content: H-12 |
| `deliverables_read` | Read a past accepted deliverable | Deliverable id | Summary, claims, evidence ids | Workflow state | WP-05 | None |
| `results_read` | Read accepted results of the current assignment | Project id, optional workstream | Results with claim ids | Workflow state | WP-04 | None |
| `evidence_read` | Read an evidence record and its stored snapshot | Evidence id | Source, capture time, extract, hash | Evidence store | WP-02 | None |
| `source_refetch` | Fetch a cited source again to confirm it still says what was claimed | Evidence id | Match, changed, or unavailable, with the new extract | The original source, through the egress proxy | WP-04 | Egress allow-list: H-10 |
| `sandbox_test_run` | Run a check on produced files: lint, validate, unit test | Artefact ids, a check from an approved list | Pass or fail, output, exit code | Sandbox with no credentials and no network | WP-04, WP-08 | Approved check list per pack: H-05 |
| `audit_read` | Read audit events for agents of one workstream | Workstream id, time range, optional agent id | Events: who, what, tool, outcome | Audit store | WP-06 | None |
| `ledger_read` | Read budget, reservations and spend | Project id | Figures per workstream and task | Budget ledger | WP-02 | Ceilings: H-08 |
| `plan_read` | Read the approved plan, schedule and risks | Project id | Workstreams, dependencies, dates, risks | Workflow state | WP-05 | None |
| `registry_read` | Read live and recent specialists and their requests | Project id | Specialist records without working memory | Agent registry | WP-02 | None |
| `model_catalogue_read` | List the models approved for use, with limits | Optional purpose | Model key, purpose, highest data classification, cost band, status | Model catalogue (configuration) | WP-03 | The catalogue itself: H-03, H-14 |

Scope limits enforced by the gateway, not by the prompt:

- A Guardrail Manager's `audit_read` returns only its own Lead's workstream.
- The Reviewer's and Tester's reads are limited to the current project.
- Every read is filtered by the data classification of the assignment and the access rights of the requesting human (ADR-0024).

## B. Tools for temporary specialists

Granted by the Recruiter, by capability tag, usually through a skill pack. All read-only.

| Capability | Purpose | Built in | Needs from a human |
| --- | --- | --- | --- |
| Web search | Find public sources | WP-04 | An approved search service and its terms of use: H-10 |
| Page and document fetch | Capture a public page or file as evidence | WP-04 | Egress allow-list: H-10 |
| Internal document read | Read documents the requesting human may read | After the proof of concept | Source systems, and how access rights are checked: H-11 |
| Repository read | Read code and configuration | WP-08 | Read-only access to named repositories: H-07, H-11 |
| Static analysis, manifest validation, workflow linting | Check produced files in the sandbox | WP-08 | Which tools and rule sets are approved: H-05 |
| Pipeline results | Read the outcome of a pipeline run, such as a Terraform plan | WP-08 | Read-only access: H-11 |
| Argo CD application status and diff | Read deployment state | WP-08 | A read-only Argo CD account: H-11 |
| Azure resource and cost queries | Read what exists and what it costs | WP-08 | A read-only identity and its scope: H-11 |
| Microsoft documentation search | Cite service limits and guidance | WP-08 | None expected; verify the access method in the spike |

## C. What is deliberately not a tool

- Opening a pull request, creating a ticket, sending a message: done by the action executor, never by an agent.
- Creating or contacting another agent.
- Anything that writes to a system outside the platform.

## Adding a tool

Add a row here, a `ToolDefinition` and a reviewed implementation, tests that it is read-only and
produces evidence where it should, and a pull request reviewed by the security owner.
`scripts/check_agents.py` rejects an agent definition that names a tool missing from section A.
