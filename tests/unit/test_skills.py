import pytest

from orchestrator.contracts import AgentSpecification, Classification, LeadRole
from orchestrator.governance.recruiter import InMemoryAgentRegistry, Policy, Recruiter, Rejection
from orchestrator.skills.library import DEVOPS_PACKS, SkillLibrary
from orchestrator.tools.registry import ToolDefinition
from tests.unit.test_assurance import Creds
from tests.unit.test_core import make_request, registry
from tests.unit.test_recruiter import Mem


def lib():
    library = SkillLibrary()
    for p in DEVOPS_PACKS:
        library.register(p)
    return library


def tools():
    reg = registry()
    common = dict(
        input_schema={},
        output_schema={},
        required_permission="Tools.Read",
        timeout_seconds=30,
        max_retries=1,
        max_classification=Classification.INTERNAL,
        permitted_lead_roles=set(LeadRole),
    )
    for name, tag, net in [
        ("repo_reader", "repo_read", "internal"),
        ("iac_scanner", "iac_static_analysis", "none"),
        ("pipeline_results", "pipeline_result_read", "internal"),
        ("gitops_status", "gitops_status_read", "internal"),
        ("manifest_validator", "manifest_validation", "none"),
        ("workflow_linter", "workflow_lint", "none"),
    ]:
        reg.register(
            ToolDefinition(
                name=name,
                version="1.0.0",
                description=f"{name} (read-only)",
                network_scope=net,
                capability_tags={tag},
                **common,
            ),
            None,
        )
    return reg


def rec(lead=LeadRole.DEVOPS):
    c = Creds()
    return Recruiter(
        tools=tools(),
        agents=InMemoryAgentRegistry(),
        credentials=c,
        memory=Mem(),
        policy=Policy(),
        task_owner=lambda t: lead,
        skills=lib(),
    ), c


def req(**kw):
    base = dict(
        requested_by=LeadRole.DEVOPS,
        role_title="Terraform module reviewer",
        required_expertise=["Terraform on Azure"],
        task_objective=(
            "Review the proposed storage module and propose corrections as a pull request."
        ),
        capabilities_needed=[],
        skills_needed=["terraform"],
    )
    base.update(kw)
    return make_request(**base)


def test_pack_brings_standards_tools_checks_and_memory() -> None:
    r, _ = rec()
    spec = r.provision(req())
    assert isinstance(spec, AgentSpecification), spec
    assert spec.skills == ["terraform@1.0.0"]
    assert {t.tool_name for t in spec.tools} == {"repo_reader", "iac_scanner", "pipeline_results"}
    assert "terraform validate passes" in spec.required_checks
    assert spec.memory.readable_org_collections == ["org/terraform-modules"]
    text = spec.prompt.rendered
    assert (
        "Remote state in Azure Storage with locking" in text
        and "Do not run terraform apply" in text
    )
    assert text.index("These rules outrank") < text.index("STANDARDS") < text.index("TASK BRIEF")


def test_two_packs_combine_without_duplicate_tools() -> None:
    r, _ = rec()
    spec = r.provision(req(skills_needed=["terraform", "github-actions"]))
    assert spec.skills == ["terraform@1.0.0", "github-actions@1.0.0"]
    assert sorted(t.tool_name for t in spec.tools) == [
        "iac_scanner",
        "pipeline_results",
        "repo_reader",
        "workflow_linter",
    ]
    assert spec.prompt.rendered.count("Propose changes as a pull request") == 1


@pytest.mark.parametrize(
    "kw,lead,why",
    [
        ({"skills_needed": ["kubernetes-wizardry"]}, LeadRole.DEVOPS, "no skill pack"),
        (
            {"skills_needed": ["terraform"], "requested_by": LeadRole.DATA},
            LeadRole.DATA,
            "may not attach",
        ),
        (
            {"skills_needed": ["terraform", "argo-cd", "github-actions", "azure-platform"]},
            LeadRole.DEVOPS,
            "at most 3",
        ),
    ],
)
def test_skill_requests_are_refused_with_a_reason(kw, lead, why) -> None:
    r, c = rec(lead)
    out = r.provision(req(**kw))
    assert (
        isinstance(out, Rejection)
        and out.code == "skill_denied"
        and why in out.detail
        and not c.live
    )


def test_no_pack_grants_a_consequential_tool_and_every_pack_forbids_changes() -> None:
    reg = tools()
    for p in DEVOPS_PACKS:
        assert any("Do not apply, deploy, sync, merge or delete" in f for f in p.forbidden_actions)
    r, _ = rec()
    spec = r.provision(req(skills_needed=["argo-cd"]))
    assert all(not reg.definition(t.tool_name, t.tool_version).consequential for t in spec.tools)


def test_specialist_without_packs_is_unchanged_in_behaviour() -> None:
    r, _ = rec(LeadRole.SOFTWARE)
    spec = r.provision(make_request())
    assert spec.skills == [] and "- none specific to this task" in spec.prompt.rendered


def test_library_versions_are_immutable_and_latest_wins() -> None:
    library = lib()
    with pytest.raises(ValueError):
        library.register(DEVOPS_PACKS[1])
    library.register(DEVOPS_PACKS[1].model_copy(update={"version": "1.1.0"}))
    assert library.latest("terraform").version == "1.1.0"
