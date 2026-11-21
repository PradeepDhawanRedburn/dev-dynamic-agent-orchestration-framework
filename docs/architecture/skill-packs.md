# Skill packs

A skill pack is a reviewed, versioned bundle of expertise for one technology. The Recruiter
attaches it to a temporary specialist (ADR-0013). Reference: `reference/skills.py`, tested.

## What a pack contains

| Part | Purpose |
| --- | --- |
| Standards | The organisation's rules for the technology, placed in the specialist's prompt after policy and before the task brief |
| Capability tags | Read-only tools the pack brings, resolved through the tool registry |
| Reference collections | Parts of organisational memory the specialist may read |
| Tester checks | What the Lead's Tester must verify on the output |
| Forbidden actions | Stated to the specialist; enforced by tool grants and guardrail rules |

Rules: at most three packs per specialist. A pack names the Lead profiles allowed to attach it.
A pack can never yield a tool that changes anything. Versions are immutable.

## First packs

| Pack | Example standards | Read-only tools | Tester checks | Never |
| --- | --- | --- | --- | --- |
| `azure-platform` | Managed identities; private endpoints; mandatory tags and approved regions | Azure resource and cost queries; Microsoft documentation search | Recommendations name resource type and SKU; service limits cite Microsoft documentation | Create, change or delete a resource |
| `terraform` | Remote state in Azure Storage with locking; pinned versions; no secrets in state; approved modules first | Repository read; static analysis in the sandbox; pipeline results | `fmt` and `validate` pass; no high-severity finding; pipeline plan shows no unexpected destroy | Run apply, import or state commands |
| `argo-cd` | Git is the only source of truth; one Application per environment; pruning only where approved | Repository read; application status and diff; manifest validation | Manifests validate for the target Kubernetes version; change renders to the expected diff | Trigger a sync, rollback or deletion |
| `github-actions` | Workload identity federation to Azure; third-party actions pinned to a commit SHA; least token permissions; protected environments | Repository read; workflow linting; pipeline results | Workflows lint clean; no unpinned action; no secret exposed | Trigger, re-run or cancel a workflow |

**The standards above are illustrative.** The owner must replace them with the team's real
standards and name an owner for each pack before first use.

## How DevOps work reaches the estate

1. The specialist writes the change. The Tester's checks pass and the Lead accepts it.
2. The action executor opens a pull request, labelled as agent-authored, in an allow-listed repository. No human approval is asked first (ADR-0021).
3. GitHub Actions runs validation and the Terraform plan with a read-only identity and no deployment secrets. The specialist's
   sandbox has no cloud credentials, so it reads the plan from the pipeline's result.
4. Engineers review and merge. This is the human gate; the platform cannot approve or merge.
5. The pipeline and Argo CD apply the change, as for any human's pull request.

## Relation to "no predefined specialists"

No agent exists until a Lead asks for one, and its role, task, scope and budget are written for
that task. What is predefined is expertise. A Lead asks for "a specialist for this task with the
`terraform` and `github-actions` packs".

## Adding a pack

Add a file under `src/orchestrator/skills/packs/`, register any new read-only tools, add tests
that the pack resolves and yields no consequential tool, and open a pull request reviewed by the
pack's owner. No change to the graph or the roles.
