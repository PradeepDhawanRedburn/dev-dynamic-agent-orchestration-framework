"""A worker environment for tests: in-memory stores, a scripted model and fake tools.

Nothing here needs PostgreSQL or Foundry. The same worker code runs against both."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from langchain_core.language_models import BaseChatModel

from orchestrator.contracts import (
    AgentSpecification,
    AgentStatus,
    BudgetPolicy,
    Classification,
    CommunicationPolicy,
    LeadRole,
    MemoryPolicy,
    ModelConfig,
    SystemPromptSpecification,
    Task,
    ToolPermission,
    new_id,
)
from orchestrator.governance.recruiter import AgentRecord
from orchestrator.governance.resilience import Incident, SelfHealer, Step
from orchestrator.graph.worker import WorkerDeps
from orchestrator.models.catalogue import ModelCatalogue, ModelEntry, load_catalogue
from orchestrator.persistence.facade import AsyncStores
from orchestrator.tools.gateway import InMemoryKillSwitch
from orchestrator.tools.impl.fake import FakeSearch, fake_search_definition
from orchestrator.tools.impl.model_catalogue import MODEL_CATALOGUE_READ, ModelCatalogueRead
from orchestrator.tools.registry import ToolRegistry
from tests.scripted import ScriptedChatModel

PROJECT = "prj_ab12"
RESERVATION = "res_1"


def budget(**over: Any) -> BudgetPolicy:
    base: dict[str, Any] = dict(
        max_cost=Decimal("5"),
        max_tokens=100_000,
        max_tool_calls=10,
        max_model_calls=10,
        timeout_seconds=30,
        max_retries=2,
    )
    base.update(over)
    return BudgetPolicy(**base)


def make_spec(*, tools: list[ToolPermission] | None = None, **over: Any) -> AgentSpecification:
    rendered = "You are a test specialist."
    import hashlib

    agent_id = new_id("agt")
    base: dict[str, Any] = dict(
        agent_id=agent_id,
        request_id="areq_1",
        project_id=PROJECT,
        workstream_id="ws_1",
        task_id="task_1",
        accountable_lead=LeadRole.SOFTWARE,
        role_title="Test specialist",
        prompt=SystemPromptSpecification(
            compiler_version="test",
            sections=[],
            rendered=rendered,
            sha256=hashlib.sha256(rendered.encode()).hexdigest(),
        ),
        model=ModelConfig(deployment="reasoning-standard"),
        tools=tools if tools is not None else [],
        memory=MemoryPolicy(namespace=f"{PROJECT}/{agent_id}"),
        communication=CommunicationPolicy(may_message=["lead"], may_receive_from=["lead"]),
        budget=budget(),
        clearance=Classification.INTERNAL,
        evidence_requirements=["two sources"],
        completion_criteria=["done"],
        failure_criteria=["blocked"],
        escalation_rules=["ask the lead"],
        policy_version="2026.11.0",
    )
    base.update(over)
    return AgentSpecification(**base)


def grant(name: str = "fake_search", max_calls: int = 5) -> ToolPermission:
    return ToolPermission(
        tool_name=name,
        tool_version="1.0.0",
        max_calls=max_calls,
        justification="needed for the test task",
    )


def make_task(spec: AgentSpecification) -> Task:
    return Task(
        task_id=spec.task_id,
        workstream_id=spec.workstream_id,
        objective="Compare the integration options.",
        expected_output="A short comparison.",
        acceptance_criteria=["Two sources per option"],
        budget=spec.budget,
    )


async def _always(incident: Incident, attempt: int) -> bool:
    return True


async def _never(incident: Incident, attempt: int) -> bool:
    return False


async def _ignore(incident: Incident) -> None:
    return None


@dataclass
class WorkerEnv:
    stores: AsyncStores
    tools: ToolRegistry
    catalogue: ModelCatalogue
    kill: InMemoryKillSwitch
    search: FakeSearch
    incidents: list[Incident] = field(default_factory=list)
    models: list[ScriptedChatModel] = field(default_factory=list)
    timeouts: list[float] = field(default_factory=list)
    script: list[Any] = field(default_factory=list)
    deps: WorkerDeps = field(init=False)

    def __post_init__(self) -> None:
        async def record(incident: Incident) -> None:
            self.incidents.append(incident)

        healer = SelfHealer(
            {
                Step.PROBE: _always,
                Step.RETRY_BACKOFF: _always,
                Step.REFRESH_CREDENTIAL: _never,
                Step.SWITCH_ENDPOINT: _never,
                Step.ESCALATE: _never,
            },
            record,
        )

        def factory(
            entry: ModelEntry, max_output_tokens: int, timeout_seconds: float
        ) -> BaseChatModel:
            self.timeouts.append(timeout_seconds)
            model = ScriptedChatModel(script=list(self.script))
            self.models.append(model)
            return model

        self.deps = WorkerDeps(
            stores=self.stores,
            tools=self.tools,
            catalogue=self.catalogue,
            healer=healer,
            kill=self.kill,
            model_factory=factory,
            retry_initial_delay=0.0,
        )

    async def add_agent(
        self, spec: AgentSpecification, status: AgentStatus = AgentStatus.ASSIGNED
    ) -> None:
        await self.stores.registry.add(AgentRecord(spec=spec, status=status, request_hash="hash_1"))
        await self.stores.ledger.open_scope(PROJECT, Decimal("100"), changed_by="usr_test")
        await self.stores.ledger.reserve(RESERVATION, [PROJECT], Decimal("5"))

    def close(self) -> None:
        self.stores.close()


def make_env(
    *,
    search: FakeSearch | None = None,
    consequential_tool: bool = False,
    catalogue: ModelCatalogue | None = None,
) -> WorkerEnv:
    catalogue = catalogue or load_catalogue()
    tools = ToolRegistry()
    fake = search or FakeSearch()
    tools.register(fake_search_definition(), fake)
    tools.register(MODEL_CATALOGUE_READ, ModelCatalogueRead(catalogue))
    if consequential_tool:
        tools.register(
            fake_search_definition("fake_publish", consequential=True, tags={"publish"}),
            FakeSearch(),
        )
    return WorkerEnv(
        stores=AsyncStores.in_memory(),
        tools=tools,
        catalogue=catalogue,
        kill=InMemoryKillSwitch(),
        search=fake,
    )
