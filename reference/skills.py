"""Skill packs: governed, versioned expertise that the Recruiter attaches to a
dynamic specialist. A pack is data reviewed like code. It is not an agent, and
attaching one never grants a tool that can change anything."""
from __future__ import annotations

from pydantic import Field

from contracts import Contract, LeadRole


class SkillPack(Contract):
    name: str
    version: str
    title: str
    permitted_leads: set[LeadRole]            # which lead profiles may attach it
    standards: list[str] = Field(min_length=1)   # the organisation's rules, injected into the prompt
    capability_tags: list[str] = []           # read-only tools the pack brings
    reference_collections: list[str] = []     # organisational memory it may read
    tester_checks: list[str] = []             # checks the lead's Tester must run on the output
    forbidden_actions: list[str] = []         # told to the agent; enforced by tool grants and guardrails


class SkillDenied(Exception):
    pass


class SkillLibrary:
    def __init__(self) -> None:
        self._packs: dict[tuple[str, str], SkillPack] = {}

    def register(self, pack: SkillPack) -> None:
        key = (pack.name, pack.version)
        if key in self._packs:
            raise ValueError(f"{key} already registered; publish a new version instead")
        self._packs[key] = pack

    def latest(self, name: str) -> SkillPack:
        versions = [p for (n, _), p in self._packs.items() if n == name]
        if not versions:
            raise SkillDenied(f"no skill pack named '{name}'")
        return max(versions, key=lambda p: tuple(int(x) for x in p.version.split(".")))

    def resolve(self, names: list[str], lead: LeadRole, max_packs: int = 3) -> list[SkillPack]:
        if len(set(names)) > max_packs:
            raise SkillDenied(f"at most {max_packs} skill packs per specialist; split the task")
        packs = [self.latest(n) for n in dict.fromkeys(names)]
        for pack in packs:
            if lead not in pack.permitted_leads:
                raise SkillDenied(f"{lead} may not attach '{pack.name}'")
        return packs


_NO_CHANGE = ["Do not apply, deploy, sync, merge or delete anything. Propose changes as a pull request."]
_DEVOPS = {LeadRole.DEVOPS, LeadRole.SECURITY}

# Illustrative content. Replace the standards with your own engineering standards.
DEVOPS_PACKS = [
    SkillPack(
        name="azure-platform", version="1.0.0", title="Azure platform engineering",
        permitted_leads=_DEVOPS | {LeadRole.DATA, LeadRole.SOFTWARE},
        standards=["Use managed identities; no stored credentials",
                   "Private endpoints for every data service; public network access disabled",
                   "Every resource carries the mandatory tags and sits in an approved region"],
        capability_tags=["azure_resource_read", "azure_cost_read", "microsoft_docs_search"],
        reference_collections=["org/azure-landing-zone", "org/architecture-decisions"],
        tester_checks=["Each recommendation names the Azure resource type and SKU it refers to",
                       "Each claim about a service limit cites Microsoft documentation"],
        forbidden_actions=_NO_CHANGE),
    SkillPack(
        name="terraform", version="1.0.0", title="Terraform infrastructure as code",
        permitted_leads=_DEVOPS,
        standards=["Remote state in Azure Storage with locking; never local state",
                   "Pin provider and module versions",
                   "No secrets in variables, outputs or state where a managed identity can be used",
                   "Reuse approved modules before writing new resources"],
        capability_tags=["repo_read", "iac_static_analysis", "pipeline_result_read"],
        reference_collections=["org/terraform-modules"],
        tester_checks=["terraform fmt -check passes", "terraform validate passes",
                       "Static analysis reports no high-severity finding",
                       "The plan produced by the pipeline shows no unexpected destroy"],
        forbidden_actions=_NO_CHANGE + ["Do not run terraform apply, import or state commands."]),
    SkillPack(
        name="argo-cd", version="1.0.0", title="GitOps delivery with Argo CD",
        permitted_leads=_DEVOPS,
        standards=["Git is the only source of truth; no manual changes to a cluster",
                   "Each environment has its own Application and promotion is a pull request",
                   "Automated pruning is enabled only where the environment owner has approved it"],
        capability_tags=["repo_read", "gitops_status_read", "manifest_validation"],
        reference_collections=["org/gitops-standards"],
        tester_checks=["Manifests pass schema validation for the target Kubernetes version",
                       "The proposed change renders to the expected diff against the live state"],
        forbidden_actions=_NO_CHANGE + ["Do not trigger a sync, rollback or deletion in Argo CD."]),
    SkillPack(
        name="github-actions", version="1.0.0", title="CI with GitHub Actions",
        permitted_leads=_DEVOPS | {LeadRole.SOFTWARE},
        standards=["Authenticate to Azure with workload identity federation; no long-lived secrets",
                   "Pin third-party actions to a commit SHA",
                   "Grant each workflow the least token permissions it needs",
                   "Production deployments run through a protected environment with required reviewers"],
        capability_tags=["repo_read", "workflow_lint", "pipeline_result_read"],
        reference_collections=["org/ci-standards"],
        tester_checks=["Workflow files pass linting", "No workflow uses an unpinned third-party action",
                       "No secret is printed or passed to an untrusted step"],
        forbidden_actions=_NO_CHANGE + ["Do not trigger, re-run or cancel a workflow."]),
]
