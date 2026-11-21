"""Top-level supervisor graph. Fixed topology; every loop is bounded by a counter."""
import asyncio
from decimal import Decimal
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, Send, interrupt
from pydantic import Field

from contracts import (BudgetPolicy, Claim, Contract, FinalDeliverable, LeadRole,
                       ProjectPlan, StrategicRequirement, SuccessCriterion, Task, Usage,
                       Workstream)
from lead import LLM_RETRY, ask
from state import ProjectState

MAX_ROUNDS = {"plan": 2, "consolidation": 2, "review": 1, "rework_cycles": 2}
WORK_SHARE = Decimal("0.85")          # 15% of the budget is held back for review and rework


class PlanInvalid(Exception):
    """Not a ValueError on purpose: the retry policy re-asks the model."""


class HumanDecision(Contract):
    decision: Literal["approve", "reject", "changes", "more_work", "extend", "stop", "timeout"]
    approver: str                     # Entra object id, verified by the API before resuming
    comment: str = ""
    new_limit: Decimal | None = None  # absolute, so applying it twice is harmless


class RequirementDraft(Contract):
    title: str
    business_outcome: str
    context: str = ""
    constraints: list[str] = []
    success_criteria: list[SuccessCriterion] = Field(min_length=1)
    priorities: list[str] = []


class WorkstreamDraft(Contract):
    title: str
    lead: LeadRole
    objective: str
    covers_criteria: list[str]
    budget_share: float = Field(gt=0, le=1)


class PlanDraft(Contract):
    workstreams: list[WorkstreamDraft] = Field(min_length=1, max_length=4)


class Conflict(Contract):
    workstream_ids: list[str]
    description: str
    material: bool


class ConsolidationDraft(Contract):
    conflicts: list[Conflict] = []
    duplicated_findings: list[str] = []


class DeliverableDraft(Contract):
    executive_summary: str
    recommendations: list[str]
    criteria_coverage: dict[str, Literal["met", "partially_met", "not_met"]]
    claim_ids: list[str]
    unresolved_conflicts: list[str] = []


class Assessment(Contract):
    recommendation: Literal["approve", "reject", "more_work"]
    rationale: str
    unmet_criteria: list[str] = []


def bump(state: ProjectState, counter: str) -> dict[str, int]:
    rounds = dict(state.get("rounds", {}))
    rounds[counter] = rounds.get(counter, 0) + 1
    return rounds


def scaled(limits: BudgetPolicy, fraction: Decimal) -> BudgetPolicy:
    return limits.model_copy(update={
        "max_cost": (limits.max_cost * fraction).quantize(Decimal("0.01")),
        "max_tokens": int(limits.max_tokens * fraction),
        "max_tool_calls": int(limits.max_tool_calls * fraction),
        "max_model_calls": max(4, int(limits.max_model_calls * fraction))})


def build_supervisor(svc: Any, lead_graph: Any) -> StateGraph:
    P = svc.permanent_profiles          # prompts and model keys for CTO, HoD and PM

    async def cto(state: ProjectState, schema: type[Contract], prompt: str, user: str):
        return await ask(svc, state["project_id"], "cto_agent", P.cto.model_key,
                         schema, prompt, user)

    async def hod(state: ProjectState, schema: type[Contract], prompt: str, user: str):
        return await ask(svc, state["project_id"], "head_of_development", P.hod.model_key,
                         schema, prompt, user)

    # ------------------------------------------------------------ CTO Agent
    async def cto_intake(state: ProjectState) -> dict:
        draft = await cto(state, RequirementDraft, P.cto.intake_prompt,
                          state["raw_request"])
        requirement = StrategicRequirement(sponsor_principal=state["sponsor"],
                                           **draft.model_dump())
        return {"requirement": requirement.model_dump(mode="json")}

    async def cto_assess(state: ProjectState) -> dict:
        """Model work happens here, in its own node, so it is not repeated when the
        decision interrupt below resumes."""
        assessment = await cto(state, Assessment, P.cto.assess_prompt,
                               f"Requirement: {state['requirement']}\n"
                               f"Deliverable: {state['deliverable']}")
        return {"assessment": assessment.model_dump(mode="json")}

    # ------------------------------------------------------------ human gates
    async def plan_approval(state: ProjectState) -> dict:
        decision = interrupt({"gate": "plan", "project_id": state["project_id"],
                              "plan": state["plan"], "budget": state["limits"]})
        return {"approvals": {"plan": HumanDecision.model_validate(decision).model_dump(mode="json")}}

    async def budget_escalation(state: ProjectState) -> dict:
        decision = HumanDecision.model_validate(interrupt(
            {"gate": "budget", "project_id": state["project_id"], "budget": state["budget"],
             "incomplete": [w for w, r in state["workstream_results"].items()
                            if r["status"] != "complete"]}))
        update: dict = {"approvals": {"budget": decision.model_dump(mode="json")}, "rework": []}
        if decision.decision == "extend" and decision.new_limit:
            svc.ledger.open_scope(state["project_id"], decision.new_limit)   # absolute: idempotent
            update["rework"] = [w for w, r in state["workstream_results"].items()
                                if r["status"] == "partial_budget"]
        return update

    async def cto_decision(state: ProjectState) -> dict:
        decision = interrupt({"gate": "final", "project_id": state["project_id"],
                              "deliverable": state["deliverable"],
                              "agent_recommendation": state["assessment"]})
        decision = HumanDecision.model_validate(decision)
        return {"approvals": {"final": decision.model_dump(mode="json")},
                "rounds": bump(state, "rework_cycles"),
                "outcome": {"approve": "approved", "reject": "rejected"}.get(
                    decision.decision, "pending")}

    # ------------------------------------------------------------ Head of Development
    async def hod_decompose(state: ProjectState) -> dict:
        requirement = StrategicRequirement.model_validate(state["requirement"])
        limits = BudgetPolicy.model_validate(state["limits"])
        notes = [a.get("comment", "") for a in state.get("approvals", {}).values()]
        draft = await hod(state, PlanDraft, P.hod.decompose_prompt,
                          f"Requirement: {requirement.model_dump_json()}\n"
                          f"Sponsor comments so far: {notes}\n"
                          f"Workstreams already delivered: {sorted(state.get('workstream_results', {}))}\n"
                          "Use only the leads whose domain is needed.")
        known = {c.criterion_id for c in requirement.success_criteria}
        mandatory = {c.criterion_id for c in requirement.success_criteria if c.mandatory}
        covered = {c for w in draft.workstreams for c in w.covers_criteria}
        first_plan = state.get("rounds", {}).get("rework_cycles", 0) == 0
        if not covered <= known or (first_plan and not mandatory <= covered):
            raise PlanInvalid("every mandatory criterion needs a workstream; unknown ids are refused")
        if len({w.lead for w in draft.workstreams}) != len(draft.workstreams):
            raise PlanInvalid("one workstream per lead")
        total = Decimal(str(sum(w.budget_share for w in draft.workstreams)))
        plan = ProjectPlan(
            project_id=state["project_id"], requirement_id=requirement.requirement_id,
            budget=limits, max_concurrent_agents=svc.policy.max_concurrent_agents,
            plan_version=state.get("rounds", {}).get("plan", 0) + 1,
            workstreams=[Workstream(
                title=w.title, lead=w.lead, objective=w.objective,
                covers_criteria=w.covers_criteria,
                budget=scaled(limits, WORK_SHARE * Decimal(str(w.budget_share)) / total))
                for w in draft.workstreams])
        return {"plan": plan.model_dump(mode="json"), "rounds": bump(state, "plan"),
                "rework": [], "feedback": {}}

    async def hod_consolidate(state: ProjectState) -> dict:
        results = state.get("workstream_results", {})
        draft = await hod(state, ConsolidationDraft, P.hod.consolidate_prompt,
                          f"Accepted results by workstream: {results}")
        material = [c for c in draft.conflicts if c.material]
        again = state.get("rounds", {}).get("consolidation", 0) < MAX_ROUNDS["consolidation"]
        feedback: dict[str, list[str]] = {}
        for conflict in material if again else []:
            for ws_id in conflict.workstream_ids:
                if ws_id in results:
                    feedback.setdefault(ws_id, []).append(conflict.description)
        return {"rework": sorted(feedback), "feedback": feedback,
                "rounds": bump(state, "consolidation") if feedback else state.get("rounds", {}),
                "audit_events": [{"type": "conflict.detected", **c.model_dump()} for c in material]}

    async def plan_review(state: ProjectState) -> dict:
        """Deterministic choice of the reviewing lead and of the review task."""
        plan = ProjectPlan.model_validate(state["plan"])
        owners = {w.lead for w in plan.workstreams}
        reviewer = LeadRole.SECURITY if LeadRole.SECURITY not in owners else \
            min(plan.workstreams, key=lambda w: w.budget.max_cost).lead
        budget = scaled(plan.budget, Decimal("0.05"))
        ws = Workstream(title="Independent review", lead=reviewer,
                        objective="Find unsupported claims, missed criteria and unsafe advice",
                        covers_criteria=[c["criterion_id"]
                                         for c in state["requirement"]["success_criteria"]],
                        budget=budget)
        ws.tasks = [Task(
            workstream_id=ws.workstream_id, budget=budget,
            objective="Challenge the consolidated findings against the success criteria.",
            expected_output="A list of findings, each tied to a workstream and a claim id.",
            acceptance_criteria=["Every mandatory criterion is examined",
                                 "Each finding cites the evidence it disputes"],
            inputs=[f"accepted-results:{w}" for w in state["workstream_results"]])]
        svc.ledger.open_scope(f"{plan.project_id}/{ws.workstream_id}", budget.max_cost)
        return {"review_workstream": ws.model_dump(mode="json")}

    async def hod_triage_review(state: ProjectState) -> dict:
        review_id = state["review_workstream"]["workstream_id"]
        review = state["workstream_results"].get(review_id, {})
        draft = await hod(state, ConsolidationDraft, P.hod.triage_prompt,
                          f"Reviewer output: {review}\nWorkstreams: "
                          f"{[w for w in state['workstream_results'] if w != review_id]}")
        again = state.get("rounds", {}).get("review", 0) < MAX_ROUNDS["review"]
        feedback: dict[str, list[str]] = {}
        for finding in draft.conflicts if again else []:
            for ws_id in finding.workstream_ids:
                if finding.material and ws_id in state["workstream_results"] and ws_id != review_id:
                    feedback.setdefault(ws_id, []).append(finding.description)
        return {"rework": sorted(feedback), "feedback": feedback,
                "rounds": bump(state, "review") if feedback else state.get("rounds", {})}

    async def hod_final_assembly(state: ProjectState) -> dict:
        results = state["workstream_results"]
        claims: dict[str, Claim] = {}
        evidence_ids: set[str] = set()
        for ws in results.values():
            for result in ws["accepted_results"].values():
                for raw in result["output"]["claims"]:
                    claims[raw["claim_id"]] = Claim.model_validate(raw)
                evidence_ids.update(e["evidence_id"] for e in result["evidence"])
        draft = await hod(state, DeliverableDraft, P.hod.assemble_prompt,
                          f"Requirement: {state['requirement']}\nClaims you may use, by id: "
                          f"{ {k: c.statement for k, c in claims.items()} }\n"
                          f"Gaps: {[g for ws in results.values() for g in ws['gaps']]}")
        usage: Usage = await svc.ledger_meter.project_total(state["project_id"])
        deliverable = FinalDeliverable(
            project_id=state["project_id"],
            requirement_id=state["requirement"]["requirement_id"],
            executive_summary=draft.executive_summary, recommendations=draft.recommendations,
            criteria_coverage=draft.criteria_coverage,
            # the model selects claims by id; it cannot alter a claim or its evidence
            claims=[claims[i] for i in draft.claim_ids if i in claims],
            evidence_ids=sorted(evidence_ids),
            unresolved_conflicts=draft.unresolved_conflicts, total_usage=usage)
        return {"deliverable": deliverable.model_dump(mode="json")}

    # ------------------------------------------------------------ Project Manager
    async def pm_set_controls(state: ProjectState) -> dict:
        plan = ProjectPlan.model_validate(state["plan"])
        svc.ledger.open_scope(plan.project_id, plan.budget.max_cost)
        for ws in plan.workstreams:
            svc.ledger.open_scope(f"{plan.project_id}/{ws.workstream_id}", ws.budget.max_cost)
        return {"budget": svc.ledger.snapshot(plan.project_id).model_dump(mode="json")}

    async def pm_validate(state: ProjectState) -> dict:
        return {"budget": svc.ledger.snapshot(state["project_id"]).model_dump(mode="json")}

    # ------------------------------------------------------------ Recruiter and archive
    async def dispatch(state: ProjectState) -> dict:
        return {}

    async def retire_all(state: ProjectState) -> dict:
        reason = state.get("outcome") or "run ended"
        records = await asyncio.to_thread(svc.recruiter.retire_project,
                                          state["project_id"], reason)
        return {"agents": {r.agent_id: {"status": "retired", "final_status": r.final_status}
                           for r in records},
                "audit_events": [{"type": "agent.retired", **r.model_dump(mode="json")}
                                 for r in records],
                "outcome": "cancelled" if svc.kill.cached(state["project_id"])
                else state.get("outcome") or "stopped"}

    async def archive(state: ProjectState) -> dict:
        await svc.archive.store(state["project_id"], state.get("deliverable"),
                                state.get("audit_events", []), state.get("usage_events", []))
        return {}

    # ------------------------------------------------------------ routing: plain functions
    def stopped(state: ProjectState) -> bool:
        return svc.kill.cached(state["project_id"])

    def after_plan_approval(state: ProjectState) -> str:
        decision = state["approvals"]["plan"]["decision"]
        if decision == "approve" and not stopped(state):
            return "dispatch"
        if decision == "changes" and state["rounds"].get("plan", 0) < MAX_ROUNDS["plan"]:
            return "hod_decompose"
        return "retire_all"                         # reject, timeout, cancelled, or out of rounds

    def route_workstreams(state: ProjectState) -> list[Send] | str:
        """Fan out to the relevant leads only: the plan names them."""
        if stopped(state):
            return "retire_all"
        done = state.get("workstream_results", {})
        wanted = state.get("rework") or [w["workstream_id"] for w in state["plan"]["workstreams"]
                                         if w["workstream_id"] not in done]
        sends = [Send("lead_workstream", {
            "project_id": state["project_id"], "correlation_id": state["correlation_id"],
            "versions": state["versions"], "requirement": state["requirement"],
            "workstream": w, "feedback": state.get("feedback", {}).get(w["workstream_id"], []),
        }) for w in state["plan"]["workstreams"] if w["workstream_id"] in wanted]
        return sends or "hod_consolidate"

    def after_consolidate(state: ProjectState) -> str:
        if stopped(state):
            return "retire_all"
        return "dispatch" if state.get("rework") else "pm_validate"

    def after_pm(state: ProjectState) -> str:
        if stopped(state):
            return "retire_all"
        over = state["budget"]["state"] == "exhausted" or any(
            r["status"] == "partial_budget" for r in state["workstream_results"].values())
        if over and "budget" not in state.get("approvals", {}):
            return "budget_escalation"
        return "plan_review"

    def after_escalation(state: ProjectState) -> str:
        return "dispatch" if state.get("rework") else "hod_final_assembly"

    def send_review(state: ProjectState) -> list[Send]:
        return [Send("review_workstream", {
            "project_id": state["project_id"], "correlation_id": state["correlation_id"],
            "versions": state["versions"], "requirement": state["requirement"],
            "workstream": state["review_workstream"], "feedback": []})]

    def after_triage(state: ProjectState) -> str:
        if stopped(state):
            return "retire_all"
        return "dispatch" if state.get("rework") else "hod_final_assembly"

    def after_decision(state: ProjectState) -> str:
        decision = state["approvals"]["final"]["decision"]
        if decision == "more_work" and not stopped(state) and \
                state["rounds"].get("rework_cycles", 0) <= MAX_ROUNDS["rework_cycles"]:
            return "hod_decompose"
        return "retire_all"

    # ------------------------------------------------------------ wiring
    g = StateGraph(ProjectState)
    for name, fn in [("cto_intake", cto_intake), ("hod_decompose", hod_decompose),
                     ("hod_consolidate", hod_consolidate),
                     ("hod_triage_review", hod_triage_review),
                     ("hod_final_assembly", hod_final_assembly), ("cto_assess", cto_assess)]:
        g.add_node(name, fn, retry_policy=LLM_RETRY)
    for name, fn in [("pm_set_controls", pm_set_controls), ("plan_approval", plan_approval),
                     ("dispatch", dispatch), ("pm_validate", pm_validate),
                     ("budget_escalation", budget_escalation), ("plan_review", plan_review),
                     ("cto_decision", cto_decision), ("archive", archive)]:
        g.add_node(name, fn)
    g.add_node("retire_all", retire_all, retry_policy=RetryPolicy(max_attempts=5))
    g.add_node("lead_workstream", lead_graph)        # the same compiled subgraph,
    g.add_node("review_workstream", lead_graph)      # mounted twice

    g.add_edge(START, "cto_intake")
    g.add_edge("cto_intake", "hod_decompose")
    g.add_edge("hod_decompose", "pm_set_controls")
    g.add_edge("pm_set_controls", "plan_approval")
    g.add_conditional_edges("plan_approval", after_plan_approval,
                            ["dispatch", "hod_decompose", "retire_all"])
    g.add_conditional_edges("dispatch", route_workstreams,
                            ["lead_workstream", "hod_consolidate", "retire_all"])
    g.add_edge("lead_workstream", "hod_consolidate")
    g.add_conditional_edges("hod_consolidate", after_consolidate,
                            ["dispatch", "pm_validate", "retire_all"])
    g.add_conditional_edges("pm_validate", after_pm,
                            ["budget_escalation", "plan_review", "retire_all"])
    g.add_conditional_edges("budget_escalation", after_escalation,
                            ["dispatch", "hod_final_assembly"])
    g.add_conditional_edges("plan_review", send_review, ["review_workstream"])
    g.add_edge("review_workstream", "hod_triage_review")
    g.add_conditional_edges("hod_triage_review", after_triage,
                            ["dispatch", "hod_final_assembly", "retire_all"])
    g.add_edge("hod_final_assembly", "cto_assess")
    g.add_edge("cto_assess", "cto_decision")
    g.add_conditional_edges("cto_decision", after_decision, ["hod_decompose", "retire_all"])
    g.add_edge("retire_all", "archive")
    g.add_edge("archive", END)
    return g
