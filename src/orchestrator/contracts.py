"""Typed contracts. Pure Pydantic v2 - no LangChain imports, so this module is
shared by graph nodes, workers, the API and tests."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

# What may be a string in graph state: a short token, not prose (ADR-0033 point 7).
IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$"
Identifier = Annotated[str, StringConstraints(pattern=IDENTIFIER_PATTERN)]


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


def utcnow() -> datetime:
    return datetime.now(UTC)


class Contract(BaseModel):
    """Base: unknown fields are rejected so LLM output cannot smuggle extras."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


# ---------------------------------------------------------------- enums
class LeadRole(StrEnum):
    DATA = "lead_data_engineer"
    SOFTWARE = "lead_software_engineer"
    DEVOPS = "lead_devops_engineer"
    SECURITY = "lead_security_engineer"


class Classification(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"

    @property
    def rank(self) -> int:
        return list(Classification).index(self)


class AgentStatus(StrEnum):
    REQUESTED = "requested"
    VALIDATED = "validated"
    APPROVED = "approved"
    PROVISIONED = "provisioned"
    REGISTERED = "registered"
    ASSIGNED = "assigned"
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    REVISION_REQUESTED = "revision_requested"
    SUSPENDED = "suspended"  # frozen by a Guardrail Manager; a human resumes or terminates
    ACCEPTED = "accepted"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    REJECTED = "rejected"  # request refused before provisioning
    RETIRED = "retired"


_S = AgentStatus
_TERMINAL = {_S.ACCEPTED, _S.FAILED, _S.CANCELLED, _S.TIMED_OUT, _S.REJECTED}
ALLOWED_TRANSITIONS: dict[AgentStatus, set[AgentStatus]] = {
    _S.REQUESTED: {_S.VALIDATED, _S.REJECTED},
    _S.VALIDATED: {_S.APPROVED, _S.REJECTED},
    _S.APPROVED: {_S.PROVISIONED, _S.CANCELLED},
    _S.PROVISIONED: {_S.REGISTERED, _S.FAILED, _S.CANCELLED},
    _S.REGISTERED: {_S.ASSIGNED, _S.CANCELLED},
    _S.ASSIGNED: {_S.RUNNING, _S.SUSPENDED, _S.FAILED, _S.CANCELLED},  # FAILED: could not start
    _S.RUNNING: {_S.AWAITING_REVIEW, _S.SUSPENDED, _S.FAILED, _S.CANCELLED, _S.TIMED_OUT},
    _S.AWAITING_REVIEW: {_S.ACCEPTED, _S.REVISION_REQUESTED, _S.SUSPENDED, _S.FAILED, _S.CANCELLED},
    _S.REVISION_REQUESTED: {_S.RUNNING, _S.SUSPENDED, _S.CANCELLED},
    _S.SUSPENDED: {_S.ASSIGNED, _S.AWAITING_REVIEW, _S.FAILED, _S.CANCELLED},  # resume or terminate
    **{s: {_S.RETIRED} for s in _TERMINAL},
    _S.RETIRED: set(),
}


class IllegalTransition(ValueError):
    pass


def assert_transition(current: AgentStatus, new: AgentStatus) -> None:
    if new not in ALLOWED_TRANSITIONS[current]:
        raise IllegalTransition(f"{current} -> {new} is not permitted")


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SourceType(StrEnum):
    PRIMARY_DOCUMENT = "primary_document"  # vendor docs, standards, contracts
    ENTERPRISE_RECORD = "enterprise_record"  # internal systems of record
    MEASUREMENT = "measurement"  # test run, query result, scan output
    SECONDARY_ANALYSIS = "secondary_analysis"  # analyst reports, reputable press
    COMMUNITY = "community"  # forums, blogs
    EXPERT_STATEMENT = "expert_statement"  # named human input


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ---------------------------------------------------------------- requirement and plan
class SuccessCriterion(Contract):
    criterion_id: str = Field(default_factory=lambda: new_id("sc"))
    statement: str = Field(min_length=10, max_length=500)
    measure: str = Field(description="How a reviewer decides pass or fail")
    mandatory: bool = True


class StrategicRequirement(Contract):
    requirement_id: str = Field(default_factory=lambda: new_id("req"))
    title: str = Field(max_length=200)
    business_outcome: str
    context: str = ""
    constraints: list[str] = []
    success_criteria: list[SuccessCriterion] = Field(min_length=1)
    priorities: list[str] = []
    classification: Classification = Classification.INTERNAL
    sponsor_principal: str = Field(description="Entra ID object id of the human sponsor")
    version: int = 1


class BudgetPolicy(Contract):
    max_cost: Decimal = Field(gt=0)
    currency: str = "USD"
    max_tokens: int = Field(gt=0)
    max_tool_calls: int = Field(ge=0)
    max_model_calls: int = Field(gt=0)
    timeout_seconds: int = Field(gt=0, le=86_400)
    max_retries: int = Field(ge=0, le=5)
    warn_at_fraction: float = Field(default=0.8, gt=0, lt=1)


class Dependency(Contract):
    from_task_id: str
    to_task_id: str
    kind: Literal["finish_to_start", "informs"] = "finish_to_start"


class Task(Contract):
    task_id: str = Field(default_factory=lambda: new_id("task"))
    workstream_id: str
    objective: str
    inputs: list[str] = []
    expected_output: str
    acceptance_criteria: list[str] = Field(min_length=1)
    status: Literal[
        "planned", "ready", "running", "in_review", "accepted", "failed", "cancelled"
    ] = "planned"
    assigned_agent_id: str | None = None
    budget: BudgetPolicy


class Workstream(Contract):
    workstream_id: str = Field(default_factory=lambda: new_id("ws"))
    title: str
    lead: LeadRole
    objective: str
    covers_criteria: list[str] = Field(
        min_length=1, description="SuccessCriterion ids this workstream serves"
    )
    tasks: list[Task] = []
    budget: BudgetPolicy


class ProjectPlan(Contract):
    project_id: str = Field(default_factory=lambda: new_id("prj"))
    requirement_id: str
    workstreams: list[Workstream] = Field(min_length=1)
    dependencies: list[Dependency] = []
    budget: BudgetPolicy
    max_concurrent_agents: int = Field(default=8, ge=1, le=64)
    plan_version: int = 1

    @model_validator(mode="after")
    def _budgets_fit(self) -> ProjectPlan:
        total = sum((w.budget.max_cost for w in self.workstreams), Decimal(0))
        if total > self.budget.max_cost:
            raise ValueError("workstream budgets exceed the project budget")
        return self


# ---------------------------------------------------------------- agent request and specification
class ToolPermission(Contract):
    tool_name: str
    tool_version: str
    scopes: list[str] = []
    max_calls: int = Field(gt=0, le=500)
    justification: str = Field(min_length=10)


class CommunicationPolicy(Contract):
    may_message: list[str] = Field(description="Principal ids; normally only the accountable lead")
    may_receive_from: list[str]
    may_read_results_of: list[str] = []  # agent ids whose ACCEPTED results are visible
    can_spawn_agents: Literal[False] = False  # schema-level ban on recursive creation


class MemoryPolicy(Contract):
    namespace: str = Field(pattern=r"^prj_[0-9a-f]+/agt_[0-9a-f]+$")
    readable_org_collections: list[str] = []
    retention: Literal["delete_on_retire", "archive_on_retire"] = "delete_on_retire"
    archive_days: int = Field(default=0, ge=0, le=365)


class PromptSection(Contract):
    name: str
    template_id: str
    template_version: str
    text: str


class SystemPromptSpecification(Contract):
    compiler_version: str
    sections: list[PromptSection]
    rendered: str
    sha256: str

    @model_validator(mode="after")
    def _hash_matches(self) -> SystemPromptSpecification:
        if hashlib.sha256(self.rendered.encode()).hexdigest() != self.sha256:
            raise ValueError("prompt hash mismatch")
        return self


class AgentRequest(Contract):
    request_id: str = Field(default_factory=lambda: new_id("areq"))
    project_id: str
    workstream_id: str
    task_id: str
    requested_by: LeadRole
    role_title: str = Field(max_length=80)
    required_expertise: list[str] = Field(min_length=1, max_length=8)
    task_objective: str = Field(min_length=20, max_length=1500)
    scope: list[str] = Field(min_length=1)
    exclusions: list[str] = []
    input_refs: list[str] = []
    capabilities_needed: list[str] = Field(
        description="Capability tags resolved to tools by the Recruiter, e.g. 'web_research'"
    )
    skills_needed: list[str] = Field(default=[], description="Skill pack names, e.g. 'terraform'")
    evidence_requirements: list[str] = Field(min_length=1)
    data_classification: Classification
    budget: BudgetPolicy
    justification: str = Field(min_length=20)


class ModelConfig(Contract):
    deployment: str  # key in the approved model catalogue, not a raw endpoint
    temperature: float = Field(default=0.0, ge=0, le=1)
    max_output_tokens: int = Field(default=4_000, gt=0)


class AgentSpecification(Contract):
    agent_id: str = Field(default_factory=lambda: new_id("agt"))
    request_id: str
    project_id: str
    workstream_id: str
    task_id: str
    accountable_lead: LeadRole
    role_title: str
    output_schema: Literal["SpecialistOutput.v1"] = "SpecialistOutput.v1"
    prompt: SystemPromptSpecification
    model: ModelConfig
    tools: list[ToolPermission]
    memory: MemoryPolicy
    communication: CommunicationPolicy
    budget: BudgetPolicy
    clearance: Classification
    evidence_requirements: list[str]
    completion_criteria: list[str] = Field(min_length=1)
    failure_criteria: list[str] = Field(min_length=1)
    escalation_rules: list[str] = Field(min_length=1)
    skills: list[str] = []  # attached skill packs, as name@version
    required_checks: list[str] = []  # what the lead's Tester must verify
    retirement_policy: Literal["on_accept", "on_workstream_close"] = "on_accept"
    execution_mode: Literal["inline", "durable"] = "inline"
    policy_version: str
    status: AgentStatus = AgentStatus.VALIDATED
    created_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def _unique_tools(self) -> AgentSpecification:
        names = [t.tool_name for t in self.tools]
        if len(names) != len(set(names)):
            raise ValueError("duplicate tool grants")
        if not self.memory.namespace.startswith(self.project_id + "/"):
            raise ValueError("memory namespace must sit under the project")
        return self


# ---------------------------------------------------------------- evidence and results
class Evidence(Contract):
    evidence_id: str = Field(default_factory=lambda: new_id("ev"))
    project_id: str
    captured_by_agent: str
    captured_by_tool: str
    source_type: SourceType
    reference: str = Field(description="URL or enterprise reference")
    title: str = ""
    extract: str = Field(max_length=4000)
    content_sha256: str
    published_at: datetime | None = None
    retrieved_at: datetime = Field(default_factory=utcnow)
    classification: Classification = Classification.INTERNAL
    quality_score: float = Field(default=0.0, ge=0, le=1)


class Claim(Contract):
    claim_id: str = Field(default_factory=lambda: new_id("cl"))
    statement: str
    material: bool = True
    evidence_ids: list[str] = []
    contradicting_evidence_ids: list[str] = []
    confidence: Confidence

    @model_validator(mode="after")
    def _material_needs_evidence(self) -> Claim:
        if self.material and not self.evidence_ids:
            raise ValueError("a material claim must cite at least one evidence id")
        return self


class Usage(Contract):
    input_tokens: int = 0
    output_tokens: int = 0
    model_calls: int = 0
    tool_calls: int = 0
    cost: Decimal = Field(default=Decimal(0), ge=0)
    elapsed_seconds: float = 0.0


class SpecialistOutput(Contract):
    """What the LLM is allowed to author. Identity, usage and evidence bodies are
    attached by the runtime, never by the model."""

    executive_summary: str = Field(max_length=1500)
    findings: list[str]
    claims: list[Claim]
    assumptions: list[str] = []
    limitations: list[str] = []
    risks: list[str] = []
    recommended_next_action: str
    completion_status: Literal["complete", "partial", "blocked"]
    overall_confidence: Confidence


class AgentResult(Contract):
    result_id: str = Field(default_factory=lambda: new_id("res"))
    task_id: str
    agent_id: str
    revision: int = 0
    output: SpecialistOutput
    evidence: list[Evidence]
    usage: Usage
    produced_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def _citations_resolve(self) -> AgentResult:
        known = {e.evidence_id for e in self.evidence}
        wrong_owner = {e.evidence_id for e in self.evidence if e.captured_by_agent != self.agent_id}
        if wrong_owner:
            raise ValueError(f"evidence ids issued to another agent: {sorted(wrong_owner)}")
        cited = {
            i for c in self.output.claims for i in c.evidence_ids + c.contradicting_evidence_ids
        }
        missing = cited - known
        if missing:
            raise ValueError(f"claims cite unknown evidence ids: {sorted(missing)}")
        return self


class ReviewDecision(Contract):
    review_id: str = Field(default_factory=lambda: new_id("rev"))
    result_id: str
    reviewer: str
    outcome: Literal["accept", "revise", "reject", "need_additional_specialist"]
    comments: list[str] = []
    failed_criteria: list[str] = []
    decided_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def _non_accept_needs_reason(self) -> ReviewDecision:
        if self.outcome != "accept" and not (self.comments or self.failed_criteria):
            raise ValueError("a non-accept decision must say why")
        return self


# ---------------------------------------------------------------- RAID, decisions, deliverable
class Risk(Contract):
    risk_id: str = Field(default_factory=lambda: new_id("risk"))
    description: str
    severity: Severity
    likelihood: Confidence
    owner: str
    mitigation: str = ""
    status: Literal["open", "mitigated", "accepted", "closed"] = "open"


class Issue(Contract):
    issue_id: str = Field(default_factory=lambda: new_id("iss"))
    description: str
    severity: Severity
    owner: str
    status: Literal["open", "resolved"] = "open"


class Assumption(Contract):
    assumption_id: str = Field(default_factory=lambda: new_id("asm"))
    statement: str
    raised_by: str
    validated: bool = False


class Decision(Contract):
    decision_id: str = Field(default_factory=lambda: new_id("dec"))
    question: str
    outcome: str
    rationale: str
    decided_by: str  # agent role or human principal
    human_approved: bool = False
    evidence_ids: list[str] = []
    decided_at: datetime = Field(default_factory=utcnow)


class FinalDeliverable(Contract):
    deliverable_id: str = Field(default_factory=lambda: new_id("del"))
    project_id: str
    requirement_id: str
    executive_summary: str
    recommendations: list[str]
    criteria_coverage: dict[str, Literal["met", "partially_met", "not_met"]]
    claims: list[Claim]
    evidence_ids: list[str]
    open_risks: list[Risk] = []
    assumptions: list[Assumption] = []
    unresolved_conflicts: list[str] = []
    total_usage: Usage
    approval: Literal["pending", "approved", "rejected", "more_work"] = "pending"


class RetirementRecord(Contract):
    agent_id: str
    project_id: str
    final_status: AgentStatus
    reason: str
    retained_result_ids: list[str] = []
    retained_evidence_ids: list[str] = []
    working_memory_action: Literal["deleted", "archived"]
    credentials_revoked: bool
    sessions_closed: bool
    usage: Usage
    retired_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def _must_be_clean(self) -> RetirementRecord:
        if not (self.credentials_revoked and self.sessions_closed):
            raise ValueError("retirement is incomplete: access still live")
        return self
