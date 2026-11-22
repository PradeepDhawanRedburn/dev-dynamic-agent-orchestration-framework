"""Typed test helpers for the integration and property tests. The ported reference tests in
tests/unit keep their own, untyped copies."""

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel

from orchestrator.contracts import (
    AgentRequest,
    BudgetPolicy,
    Classification,
    LeadRole,
    MemoryPolicy,
    ToolPermission,
)
from orchestrator.governance.recruiter import Policy, Recruiter
from orchestrator.tools.registry import ToolDefinition, ToolRegistry

BUDGET = BudgetPolicy(
    max_cost=Decimal("5"),
    max_tokens=200_000,
    max_tool_calls=20,
    max_model_calls=15,
    timeout_seconds=900,
    max_retries=1,
)


def make_request(**over: Any) -> AgentRequest:
    base: dict[str, Any] = dict(
        project_id="prj_ab12",
        workstream_id="ws_1",
        task_id="task_1",
        requested_by=LeadRole.SOFTWARE,
        role_title="Integration options analyst",
        required_expertise=["REST and event-driven integration"],
        task_objective="Compare the documented integration options for system X and Y.",
        scope=["Public vendor documentation"],
        exclusions=["Pricing negotiation"],
        capabilities_needed=["web_research"],
        evidence_requirements=["At least two primary sources per option"],
        data_classification=Classification.INTERNAL,
        budget=BUDGET,
        justification="No active agent covers integration research for this task.",
    )
    base.update(over)
    return AgentRequest(**base)


class NoTool:
    """A tool that does nothing: the Recruiter only needs the definition."""

    args_model: type[BaseModel] = BaseModel

    async def run(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        return {}


def tool_registry() -> ToolRegistry:
    tools = ToolRegistry()
    common: dict[str, Any] = dict(
        input_schema={},
        output_schema={},
        required_permission="Tools.Read",
        timeout_seconds=30,
        max_retries=1,
    )
    tools.register(
        ToolDefinition(
            name="web_search",
            version="1.0.0",
            description="Search the public web via the egress proxy",
            max_classification=Classification.INTERNAL,
            network_scope="internet_egress_proxy",
            permitted_lead_roles=set(LeadRole),
            capability_tags={"web_research"},
            produces_evidence=True,
            **common,
        ),
        NoTool(),
    )
    return tools


class FakeCredentials:
    def __init__(self, revokes: bool = True) -> None:
        self.live: dict[str, int] = {}
        self.frozen: set[str] = set()
        self._revokes = revokes

    def issue(self, agent_id: str, grants: list[ToolPermission], ttl_seconds: int) -> None:
        self.live[agent_id] = ttl_seconds

    def revoke(self, agent_id: str) -> bool:
        if self._revokes:
            self.live.pop(agent_id, None)
        return agent_id not in self.live

    def freeze(self, agent_id: str) -> None:
        self.frozen.add(agent_id)

    def unfreeze(self, agent_id: str) -> None:
        self.frozen.discard(agent_id)


class FakeMemory:
    def __init__(self) -> None:
        self.namespaces: set[str] = set()

    def create(self, namespace: str) -> None:
        self.namespaces.add(namespace)

    def retire(self, namespace: str, policy: MemoryPolicy) -> Literal["deleted", "archived"]:
        self.namespaces.discard(namespace)
        return "deleted"


def make_recruiter(
    agents: Any,
    policy: Policy | None = None,
    credentials: FakeCredentials | None = None,
) -> tuple[Recruiter, FakeCredentials, FakeMemory]:
    creds, memory = credentials or FakeCredentials(), FakeMemory()
    recruiter = Recruiter(
        tools=tool_registry(),
        agents=agents,
        credentials=creds,
        memory=memory,
        policy=policy or Policy(),
        task_owner=lambda task: LeadRole.SOFTWARE,
    )
    return recruiter, creds, memory
