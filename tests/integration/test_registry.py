"""The agent registry and the Recruiter (ADR-0007, WP-02): the same behaviour from the in-memory
and PostgreSQL registries, including everything the Recruiter does to one."""

import pytest

from orchestrator.contracts import (
    AgentSpecification,
    AgentStatus,
    IllegalTransition,
)
from orchestrator.governance.recruiter import AgentRecord, Policy, Recruiter
from tests.integration.conftest import Stores
from tests.support import (
    FakeCredentials,
    FakeMemory,
    make_request,
)
from tests.support import (
    make_recruiter as build_recruiter,
)

TASK_2 = "Assess the authentication options for system X."


def make_recruiter(
    stores: Stores, policy: Policy | None = None, creds: FakeCredentials | None = None
) -> tuple[Recruiter, FakeCredentials, FakeMemory]:
    return build_recruiter(stores.registry, policy, creds)


def provisioned(stores: Stores) -> AgentSpecification:
    recruiter, _, _ = make_recruiter(stores)
    spec = recruiter.provision(make_request())
    assert isinstance(spec, AgentSpecification)
    return spec


def test_provisioning_leaves_a_registered_record_with_its_history(stores: Stores) -> None:
    spec = provisioned(stores)
    record = stores.registry.get(spec.agent_id)
    assert record.status is AgentStatus.REGISTERED
    assert [s for s, _ in record.history] == [
        AgentStatus.APPROVED,
        AgentStatus.PROVISIONED,
        AgentStatus.REGISTERED,
    ]
    assert record.spec.prompt.sha256 == spec.prompt.sha256, "the prompt survived intact"
    assert [t.tool_name for t in record.spec.tools] == ["web_search"]
    assert record.spec.model_dump(exclude={"status", "created_at"}) == spec.model_dump(
        exclude={"status", "created_at"}
    )


def test_adding_the_same_agent_again_keeps_the_first_record(stores: Stores) -> None:
    spec = provisioned(stores)
    first = stores.registry.get(spec.agent_id)
    stores.registry.add(AgentRecord(spec=spec, status=AgentStatus.VALIDATED, request_hash="other"))
    assert stores.registry.get(spec.agent_id).request_hash == first.request_hash


def test_a_transition_to_the_current_status_is_a_no_op(stores: Stores) -> None:
    spec = provisioned(stores)
    stores.registry.transition(spec.agent_id, AgentStatus.ASSIGNED)
    stores.registry.transition(spec.agent_id, AgentStatus.ASSIGNED)
    history = [s for s, _ in stores.registry.get(spec.agent_id).history]
    assert history.count(AgentStatus.ASSIGNED) == 1


def test_illegal_transitions_are_refused_and_change_nothing(stores: Stores) -> None:
    spec = provisioned(stores)
    with pytest.raises(IllegalTransition):
        stores.registry.transition(spec.agent_id, AgentStatus.ACCEPTED)
    assert stores.registry.get(spec.agent_id).status is AgentStatus.REGISTERED
    with pytest.raises(KeyError):
        stores.registry.transition("agt_unknown", AgentStatus.ASSIGNED)
    with pytest.raises(KeyError):
        stores.registry.get("agt_unknown")


def test_a_duplicate_request_returns_the_existing_agent(stores: Stores) -> None:
    recruiter, _, _ = make_recruiter(stores)
    a = recruiter.provision(make_request())
    b = recruiter.provision(
        make_request(
            task_objective="  COMPARE the documented   integration options for system X and Y. "
        )
    )
    assert isinstance(a, AgentSpecification) and isinstance(b, AgentSpecification)
    assert a.agent_id == b.agent_id
    assert len(stores.registry.for_project("prj_ab12")) == 1


def test_for_project_returns_only_that_project_in_creation_order(stores: Stores) -> None:
    recruiter, _, _ = make_recruiter(stores)
    first = recruiter.provision(make_request())
    second = recruiter.provision(make_request(task_id="task_2", task_objective=TASK_2))
    other = recruiter.provision(make_request(project_id="prj_ab13"))
    assert isinstance(first, AgentSpecification) and isinstance(second, AgentSpecification)
    assert isinstance(other, AgentSpecification)
    assert [r.spec.agent_id for r in stores.registry.for_project("prj_ab12")] == [
        first.agent_id,
        second.agent_id,
    ]
    assert [r.spec.agent_id for r in stores.registry.for_project("prj_ab13")] == [other.agent_id]


def test_retiring_stores_the_record_and_is_idempotent(stores: Stores) -> None:
    recruiter, creds, mem = make_recruiter(stores)
    spec = recruiter.provision(make_request())
    assert isinstance(spec, AgentSpecification)
    for status in (
        AgentStatus.ASSIGNED,
        AgentStatus.RUNNING,
        AgentStatus.AWAITING_REVIEW,
        AgentStatus.ACCEPTED,
    ):
        stores.registry.transition(spec.agent_id, status)
    first = recruiter.retire(
        spec.agent_id,
        final_status=AgentStatus.ACCEPTED,
        reason="accepted",
        result_ids=["res_1"],
        evidence_ids=["ev_1"],
    )
    again = recruiter.retire(spec.agent_id, final_status=AgentStatus.FAILED, reason="again")
    assert again == first
    stored = stores.registry.get(spec.agent_id)
    assert stored.status is AgentStatus.RETIRED and stored.retirement == first
    assert first.final_status is AgentStatus.ACCEPTED and first.credentials_revoked
    assert not creds.live and not mem.namespaces
    with pytest.raises(IllegalTransition):
        stores.registry.transition(spec.agent_id, AgentStatus.RUNNING)


def test_retiring_an_agent_that_never_ran_records_it_as_cancelled(stores: Stores) -> None:
    recruiter, _, _ = make_recruiter(stores)
    spec = recruiter.provision(make_request())
    assert isinstance(spec, AgentSpecification)
    retirement = recruiter.retire(spec.agent_id, final_status=AgentStatus.ACCEPTED, reason="kill")
    assert retirement.final_status is AgentStatus.CANCELLED


def test_suspend_and_resume_go_through_the_registry(stores: Stores) -> None:
    recruiter, creds, _ = make_recruiter(stores)
    spec = recruiter.provision(make_request())
    assert isinstance(spec, AgentSpecification)
    for status in (AgentStatus.ASSIGNED, AgentStatus.RUNNING):
        stores.registry.transition(spec.agent_id, status)
    recruiter.suspend(spec.agent_id, "tool.denied x3")
    recruiter.suspend(spec.agent_id, "again")
    assert stores.registry.get(spec.agent_id).status is AgentStatus.SUSPENDED
    with pytest.raises(ValueError):
        recruiter.resume(spec.agent_id, approver="", has_held_result=False)
    recruiter.resume(spec.agent_id, approver="security-owner-oid", has_held_result=True)
    assert stores.registry.get(spec.agent_id).status is AgentStatus.AWAITING_REVIEW


def test_the_project_sweep_retires_everything_once(stores: Stores) -> None:
    recruiter, creds, _ = make_recruiter(stores)
    recruiter.provision(make_request())
    recruiter.provision(make_request(task_id="task_2", task_objective=TASK_2))
    records = recruiter.retire_project("prj_ab12", "kill switch")
    assert len(records) == 2 and not creds.live
    assert all(r.status is AgentStatus.RETIRED for r in stores.registry.for_project("prj_ab12"))
    assert recruiter.retire_project("prj_ab12", "again") == []
