"""Graph state. Values are JSON-serialisable dicts made with model_dump(mode="json")
and re-validated with Pydantic at node boundaries."""
import operator
from typing import Annotated

from typing_extensions import TypedDict


def merge(left: dict | None, right: dict | None) -> dict:
    """Reducer for parallel writers: union of keys, the newer value wins."""
    return {**(left or {}), **(right or {})}


class Shared(TypedDict, total=False):
    """The only keys a Lead subgraph returns to the supervisor. Each has a reducer
    because several workstreams write them in the same superstep."""
    workstream_results: Annotated[dict[str, dict], merge]   # workstream_id -> result
    agents: Annotated[dict[str, dict], merge]               # agent_id -> registry view
    usage_events: Annotated[list[dict], operator.add]
    audit_events: Annotated[list[dict], operator.add]


class ProjectState(Shared, total=False):
    """Project scope. Written only by permanent-agent nodes of the supervisor."""
    project_id: str
    correlation_id: str
    versions: dict[str, str]          # graph, policy, prompt set, model catalogue
    raw_request: str
    sponsor: str
    limits: dict                      # BudgetPolicy for the whole project
    requirement: dict                 # StrategicRequirement
    plan: dict                        # ProjectPlan
    approvals: Annotated[dict[str, dict], merge]   # gate name -> HumanDecision
    rework: list[str]                 # workstream ids to run again
    feedback: dict[str, list[str]]    # workstream_id -> conflicts or review findings
    rounds: dict[str, int]            # loop counters
    budget: dict                      # BudgetSnapshot
    review_workstream: dict           # Workstream for the independent review
    assessment: dict                  # CTO Agent's scoring of the deliverable
    deliverable: dict                 # FinalDeliverable
    outcome: str


class WorkstreamInput(TypedDict):
    """What the supervisor passes with Send. A lead never sees other workstreams."""
    project_id: str
    correlation_id: str
    versions: dict[str, str]
    requirement: dict
    workstream: dict
    feedback: list[str]


class WorkstreamState(Shared, total=False):
    """Workstream scope. Private to one run of the Lead subgraph."""
    project_id: str
    correlation_id: str
    versions: dict[str, str]
    requirement: dict
    workstream: dict
    feedback: list[str]
    tasks: Annotated[dict[str, dict], merge]         # task_id -> Task
    requests: dict[str, dict]                        # task_id -> AgentRequest, this round
    specs: Annotated[dict[str, dict], merge]         # task_id -> AgentSpecification
    reservations: Annotated[dict[str, str], merge]   # task_id -> reservation id
    dispatch: list[str]                              # task ids cleared by the budget gate
    outcomes: Annotated[dict[str, dict], merge]      # task_id -> SpecialistOutcome
    reviews: Annotated[dict[str, dict], merge]       # task_id -> ReviewDecision
    revisions: Annotated[dict[str, int], merge]      # task_id -> revision count
    suspended: dict[str, dict]                       # agent_id -> guardrail verdict, this round
    recruit_rounds: int


class SpecialistInput(TypedDict):
    """Task scope. The complete input of one specialist run."""
    project_id: str
    correlation_id: str
    workstream_id: str
    task: dict
    spec: dict
    reservation_id: str
    revision: int
    comments: list[str]
