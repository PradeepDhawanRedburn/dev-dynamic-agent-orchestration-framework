"""Lead Engineer subgraph. One compiled graph serves all four leads; the lead's
role arrives in the workstream and selects a profile (prompt, model, standards)."""
import asyncio
from decimal import Decimal
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, Send, TimeoutPolicy, interrupt
from pydantic import Field, ValidationError

from budget import BudgetExceeded
from contracts import (AgentRequest, AgentResult, AgentSpecification, AgentStatus,
                       Classification, Contract, ReviewDecision, StrategicRequirement,
                       Task, Workstream)
from guardrails import tighten
from recruiter import TERMINAL, Rejection
from state import Shared, WorkstreamInput, WorkstreamState
from worker import SpecialistOutcome, make_specialist_node

MAX_TASKS, MAX_REVISIONS, MAX_RECRUIT_ROUNDS, MIN_EVIDENCE_QUALITY = 6, 2, 2, 0.5
TASK_SHARE = Decimal("0.6")     # 40% of a workstream budget is held for revisions and re-staffing
LLM_RETRY = RetryPolicy(max_attempts=3, initial_interval=1.0, backoff_factor=2.0, jitter=True)


# ---- what a lead's model is allowed to write: drafts, never ids, budgets or grants
class TaskDraft(Contract):
    objective: str
    expected_output: str
    acceptance_criteria: list[str] = Field(min_length=1, max_length=6)
    inputs: list[str] = []


class TaskDrafts(Contract):
    tasks: list[TaskDraft] = Field(min_length=1, max_length=MAX_TASKS)


class RequestDraft(Contract):
    task_id: str
    role_title: str
    required_expertise: list[str]
    scope: list[str]
    exclusions: list[str] = []
    capabilities_needed: list[str]
    evidence_requirements: list[str]
    justification: str


class RequestDrafts(Contract):
    requests: list[RequestDraft]


class ReviewDraft(Contract):
    task_id: str
    outcome: Literal["accept", "revise", "need_additional_specialist"]
    comments: list[str] = []
    failed_criteria: list[str] = []


class ReviewDrafts(Contract):
    reviews: list[ReviewDraft]


class TestDraft(Contract):                 # written by a Tester
    task_id: str
    passed: bool
    failed_checks: list[str] = []


class TestDrafts(Contract):
    tests: list[TestDraft]


class GuardrailJudgement(Contract):        # written by a Guardrail Manager
    agent_id: str
    suspend: bool
    reason: str = ""


class GuardrailJudgements(Contract):
    judgements: list[GuardrailJudgement] = []


class GuardrailDecision(Contract):         # written by a human
    approver: str
    decisions: dict[str, Literal["resume", "terminate"]]


class ModelOutputInvalid(Exception):
    """Not a ValueError on purpose, so the node's retry policy asks the model again."""


async def ask(svc: Any, project_id: str, role: str, model_key: str,
              schema: type[Contract], system: str, user: str):
    """One structured model call by a permanent agent. The schema is the contract;
    free text is not accepted. Usage is metered against the project."""
    model = svc.models.chat(model_key).with_structured_output(schema, include_raw=True)
    out = await model.ainvoke([("system", system), ("user", user)])
    meta = getattr(out["raw"], "usage_metadata", None) or {}
    await svc.ledger_meter.add_model_call(f"{project_id}:{role}", model_key,
                                          meta.get("input_tokens", 0),
                                          meta.get("output_tokens", 0))
    if out.get("parsed") is None:
        raise ModelOutputInvalid(str(out.get("parsing_error")))
    return out["parsed"]


def build_lead_graph(svc: Any):
    run_specialist, on_specialist_error = make_specialist_node(svc)

    def profile(state: WorkstreamState):
        return svc.lead_profiles[state["workstream"]["lead"]]

    async def lead(state: WorkstreamState, schema: type[Contract], prompt: str, user: str):
        return await ask(svc, state["project_id"], state["workstream"]["lead"],
                         profile(state).model_key, schema, prompt, user)

    async def assurance(state: WorkstreamState, kind: str, schema: type[Contract], user: str):
        """A call by this lead's permanent Tester or Guardrail Manager."""
        p = svc.assurance_profiles[state["workstream"]["lead"]][kind]
        return await ask(svc, state["project_id"], f"{state['workstream']['lead']}:{kind}",
                         p.model_key, schema, p.prompt, user)

    # ------------------------------------------------------------ Guardrail Manager
    async def guardrail_review(state: WorkstreamState) -> dict:
        """Rules first, then judgement on what the rules only flagged. The model can
        tighten a verdict; it cannot clear one."""
        verdicts = {tid: svc.guardrail.verdict(state["outcomes"][tid]["agent_id"])
                    for tid in state.get("dispatch", [])
                    if state["outcomes"][tid]["agent_id"] != "none"}
        flagged = {tid: v for tid, v in verdicts.items() if v.action == "flag"}
        if flagged:
            drafts = await assurance(
                state, "guardrail", GuardrailJudgements,
                "\n".join(f"AGENT {v.agent_id} rule {v.rule} count {v.count}; "
                          f"scope {state['specs'][tid]['prompt']['sections'][2]['text']}; "
                          f"outcome {state['outcomes'][tid]['status']}"
                          for tid, v in flagged.items()))
            wants = {j.agent_id for j in drafts.judgements if j.suspend}
            for tid, v in flagged.items():
                verdicts[tid] = tighten(v, v.agent_id in wants)

        suspended, outcomes = {}, {}
        for tid, v in verdicts.items():
            if v.action != "suspend":
                continue
            status = svc.recruiter.agents.get(v.agent_id).status
            if status in TERMINAL or status is AgentStatus.RETIRED:
                continue                                   # already stopped; nothing to freeze
            await asyncio.to_thread(svc.recruiter.suspend, v.agent_id, f"{v.rule} x{v.count}")
            suspended[v.agent_id] = {"task_id": tid, **v.model_dump()}
            outcomes[tid] = {**state["outcomes"][tid], "status": "suspended"}
        return {"suspended": suspended, "outcomes": outcomes,
                "audit_events": [{"type": "guardrail.verdict", "task_id": t, **v.model_dump()}
                                 for t, v in verdicts.items() if v.action != "none"]}

    async def guardrail_hold(state: WorkstreamState) -> dict:
        """Suspension is reversible and automatic; what happens next is a human's call.
        This escalation goes to the security owner or CTO, not through the lead."""
        suspended = state.get("suspended") or {}
        if not suspended:
            return {}
        answer = GuardrailDecision.model_validate(interrupt(
            {"gate": "guardrail", "project_id": state["project_id"],
             "lead": state["workstream"]["lead"], "suspended": suspended}))
        outcomes, agents = {}, {}
        for agent_id, info in suspended.items():
            tid = info["task_id"]
            outcome = SpecialistOutcome.model_validate(state["outcomes"][tid])
            still_held = svc.recruiter.agents.get(agent_id).status is AgentStatus.SUSPENDED
            if answer.decisions.get(agent_id) == "resume":
                if still_held:
                    await asyncio.to_thread(svc.recruiter.resume, agent_id, approver=answer.approver,
                                            has_held_result=outcome.result is not None)
                    svc.guardrail.cleared(agent_id)
                outcome.status = "awaiting_review" if outcome.result else "resumed"
                agents[agent_id] = {"status": "resumed", "task_id": tid, "by": answer.approver}
            else:                                          # terminate; also the default
                await asyncio.to_thread(
                    svc.recruiter.retire, agent_id, final_status=AgentStatus.FAILED,
                    reason=f"terminated after guardrail suspension by {answer.approver}")
                outcome = SpecialistOutcome(task_id=tid, agent_id=agent_id, status="failed",
                                            error="terminated by guardrail decision",
                                            usage=outcome.usage)
                agents[agent_id] = {"status": "retired", "task_id": tid, "by": answer.approver}
            outcomes[tid] = outcome.model_dump(mode="json")
        return {"suspended": {}, "outcomes": outcomes, "agents": agents,
                "audit_events": [{"type": "guardrail.decision", "approver": answer.approver,
                                  "decisions": answer.decisions}]}

    # ------------------------------------------------------------ Tester
    async def tester_validate(state: WorkstreamState) -> dict:
        """Independent validation before the lead judges. A failed test forces a
        revision; the lead cannot accept past it."""
        gate = state.get("reviews", {})
        todo = {}
        for tid in state.get("dispatch", []):
            outcome = SpecialistOutcome.model_validate(state["outcomes"][tid])
            if outcome.status != "awaiting_review":
                continue
            if gate.get(tid, {}).get("result_id") == outcome.result.result_id:
                continue                                   # the evidence gate already sent it back
            todo[tid] = outcome.result
        if not todo:
            return {}
        drafts = await assurance(
            state, "tester", TestDrafts,
            "\n\n".join(
                f"TASK {tid}\nAcceptance criteria: {state['tasks'][tid]['acceptance_criteria']}\n"
                f"CLAIMS: {[c.model_dump(mode='json') for c in r.output.claims]}\n"
                f"EVIDENCE: { {e.evidence_id: e.extract for e in r.evidence} }"
                for tid, r in todo.items()))
        reports = {t.task_id: t for t in drafts.tests if t.task_id in todo}
        reviews = {}
        for tid, result in todo.items():
            report = reports.get(tid)
            if report is None or not report.passed:
                reviews[tid] = ReviewDecision(
                    result_id=result.result_id, reviewer="tester", outcome="revise",
                    failed_criteria=(report.failed_checks if report and report.failed_checks
                                     else ["No passing test report for this result."])
                ).model_dump(mode="json")
        return {"reviews": reviews,
                "audit_events": [{"type": "test.report", "task_id": t, "passed": t not in reviews}
                                 for t in todo]}

    # ------------------------------------------------------------ model-backed nodes
    async def analyse_and_decompose(state: WorkstreamState) -> dict:
        ws = Workstream.model_validate(state["workstream"])
        if ws.tasks:                                   # e.g. the independent review: one fixed task
            return {"tasks": {t.task_id: t.model_dump(mode="json") for t in ws.tasks}}
        if state.get("tasks") and not state.get("feedback"):
            return {}
        requirement = StrategicRequirement.model_validate(state["requirement"])
        drafts = await lead(
            state, TaskDrafts, profile(state).decompose_prompt,
            f"Requirement: {requirement.business_outcome}\nWorkstream: {ws.objective}\n"
            f"Feedback to address: {state.get('feedback') or 'none'}\n"
            f"Relevant standards: {await svc.org_memory.search(ws.lead, ws.objective)}")
        n = len(drafts.tasks)
        share = ws.budget.model_copy(update={
            "max_cost": (ws.budget.max_cost * TASK_SHARE / n).quantize(Decimal("0.01")),
            "max_tokens": ws.budget.max_tokens // n,
            "max_tool_calls": ws.budget.max_tool_calls // n,
            "max_model_calls": max(4, ws.budget.max_model_calls // n)})
        tasks = [Task(workstream_id=ws.workstream_id, budget=share, **d.model_dump())
                 for d in drafts.tasks]
        return {"tasks": {t.task_id: t.model_dump(mode="json") for t in tasks}}

    async def build_agent_requests(state: WorkstreamState) -> dict:
        ws = Workstream.model_validate(state["workstream"])
        reviews = state.get("reviews", {})
        unstaffed = {tid: t for tid, t in state["tasks"].items()
                     if tid not in state.get("specs", {})
                     or reviews.get(tid, {}).get("outcome") == "need_additional_specialist"}
        if not unstaffed:
            return {"requests": {}}
        drafts = await lead(
            state, RequestDrafts, profile(state).staffing_prompt,
            f"Tasks: {unstaffed}\nCapability tags you may ask for: "
            f"{sorted(profile(state).grantable_capabilities)}\n"
            f"Earlier review comments: { {t: reviews[t].get('comments') for t in unstaffed if t in reviews} }")
        requirement = StrategicRequirement.model_validate(state["requirement"])
        requests = {}
        for d in drafts.requests:
            if d.task_id not in unstaffed:
                continue                                   # a model cannot staff tasks it was not shown
            task = Task.model_validate(unstaffed[d.task_id])
            try:
                requests[d.task_id] = AgentRequest(
                    project_id=state["project_id"], workstream_id=ws.workstream_id,
                    requested_by=ws.lead, task_objective=task.objective,
                    data_classification=Classification(requirement.classification),
                    budget=task.budget, input_refs=task.inputs,
                    **d.model_dump()).model_dump(mode="json")
            except ValidationError:
                continue                                   # left unstaffed; reported as a gap
        return {"requests": requests}

    async def lead_review(state: WorkstreamState) -> dict:
        reviews: dict[str, dict] = {}
        revisions: dict[str, int] = {}
        agents: dict[str, dict] = {}
        to_judge: dict[str, SpecialistOutcome] = {}
        gate = state.get("reviews", {})
        for tid in state.get("dispatch", []):
            outcome = SpecialistOutcome.model_validate(state["outcomes"][tid])
            if outcome.status == "resumed":               # cut short, then cleared by a human
                reviews[tid] = ReviewDecision(
                    result_id="none", reviewer="system", outcome="revise",
                    comments=["Resumed after a guardrail hold; run again."]).model_dump(mode="json")
            elif outcome.status != "awaiting_review":     # failed, timed out, cancelled, blocked
                restaff = outcome.status in ("failed", "timed_out") and \
                    state.get("recruit_rounds", 0) < MAX_RECRUIT_ROUNDS
                reviews[tid] = ReviewDecision(
                    result_id="none", reviewer="system",
                    outcome="need_additional_specialist" if restaff else "reject",
                    comments=[outcome.error or outcome.status]).model_dump(mode="json")
            elif gate.get(tid, {}).get("reviewer") in ("evidence_gate", "tester") and \
                    gate[tid]["result_id"] == outcome.result.result_id:
                reviews[tid] = gate[tid]                   # a gate or the Tester already sent it back
            else:
                to_judge[tid] = outcome

        if to_judge:
            drafts = await lead(
                state, ReviewDrafts, profile(state).review_prompt,
                "\n\n".join(f"TASK {tid}\nAcceptance criteria: "
                            f"{state['tasks'][tid]['acceptance_criteria']}\n"
                            f"RESULT: {o.result.output.model_dump_json()}"
                            for tid, o in to_judge.items()))
            judged = {d.task_id: d for d in drafts.reviews if d.task_id in to_judge}
            for tid, outcome in to_judge.items():
                d = judged.get(tid)
                reviews[tid] = ReviewDecision(
                    result_id=outcome.result.result_id, reviewer=state["workstream"]["lead"],
                    outcome=d.outcome if d else "revise",
                    comments=(d.comments if d else ["No review was returned for this result."]),
                    failed_criteria=d.failed_criteria if d else []).model_dump(mode="json")

        # deterministic consequences of each decision
        for tid, review in reviews.items():
            spec = AgentSpecification.model_validate(state["specs"][tid])
            count = state.get("revisions", {}).get(tid, 0)
            if review["outcome"] == "revise" and count >= MAX_REVISIONS:
                review["outcome"] = "reject"
                review["comments"] = review["comments"] + ["Revision limit reached."]
            if review["outcome"] == "revise":
                revisions[tid] = count + 1
                if svc.recruiter.agents.get(spec.agent_id).status is AgentStatus.AWAITING_REVIEW:
                    svc.recruiter.agents.transition(spec.agent_id, AgentStatus.REVISION_REQUESTED)
                agents[spec.agent_id] = {"status": "revision_requested", "task_id": tid}
                continue
            accepted = review["outcome"] == "accept"
            outcome = SpecialistOutcome.model_validate(state["outcomes"][tid])
            record = await asyncio.to_thread(
                svc.recruiter.retire, spec.agent_id,
                final_status=AgentStatus.ACCEPTED if accepted else AgentStatus.FAILED,
                reason=review["outcome"], usage=outcome.usage,
                result_ids=[outcome.result.result_id] if accepted and outcome.result else [],
                evidence_ids=[e.evidence_id for e in outcome.result.evidence]
                if accepted and outcome.result else [])
            agents[spec.agent_id] = {"status": "retired", "task_id": tid,
                                     "final_status": record.final_status}
        return {"reviews": reviews, "revisions": revisions, "agents": agents,
                "audit_events": [{"type": "review.decided", "task_id": t, **r}
                                 for t, r in reviews.items()]}

    # ------------------------------------------------------------ deterministic nodes
    async def recruit(state: WorkstreamState) -> dict:
        specs, outcomes, agents, audit, revisions = {}, {}, {}, [], {}
        for tid, raw in state.get("requests", {}).items():
            request = AgentRequest.model_validate(raw)
            out = await asyncio.to_thread(svc.recruiter.provision, request)
            if isinstance(out, Rejection):
                outcomes[tid] = SpecialistOutcome(
                    task_id=tid, agent_id="none", status="failed",
                    error=f"agent request rejected: {out.code}").model_dump(mode="json")
                audit.append({"type": "agent.rejected", **out.model_dump(mode="json")})
            else:
                specs[tid] = out.model_dump(mode="json")
                revisions[tid] = 0                         # a new agent starts a fresh count
                agents[out.agent_id] = {"status": out.status, "task_id": tid,
                                        "role": out.role_title, "lead": out.accountable_lead}
                audit.append({"type": "agent.created", "agent_id": out.agent_id,
                              "prompt_sha256": out.prompt.sha256,
                              "tools": [t.tool_name for t in out.tools]})
        return {"specs": specs, "outcomes": outcomes, "agents": agents, "audit_events": audit,
                "revisions": revisions, "recruit_rounds": state.get("recruit_rounds", 0) + 1}

    async def budget_gate(state: WorkstreamState) -> dict:
        """Reserve the maximum cost of each ready task before it may run."""
        if svc.kill.cached(state["project_id"]):
            return {"dispatch": []}
        ws_id = state["workstream"]["workstream_id"]
        runnable = {AgentStatus.REGISTERED, AgentStatus.ASSIGNED, AgentStatus.REVISION_REQUESTED}
        dispatch, reservations, blocked = [], {}, {}
        for tid, raw in state.get("specs", {}).items():
            spec = AgentSpecification.model_validate(raw)
            status = svc.recruiter.agents.get(spec.agent_id).status   # the registry decides
            if status not in runnable:
                continue
            revision = state.get("revisions", {}).get(tid, 0)
            reservation_id = f"{spec.agent_id}:{revision}"
            try:
                svc.ledger.reserve(reservation_id, [state["project_id"],
                                                    f"{state['project_id']}/{ws_id}"],
                                   spec.budget.max_cost)
            except BudgetExceeded as exc:
                blocked[tid] = SpecialistOutcome(
                    task_id=tid, agent_id=spec.agent_id, status="blocked_budget",
                    error=str(exc)).model_dump(mode="json")
                continue
            if status is AgentStatus.REGISTERED:
                svc.recruiter.agents.transition(spec.agent_id, AgentStatus.ASSIGNED)
            dispatch.append(tid)
            reservations[tid] = reservation_id
        return {"dispatch": dispatch, "reservations": reservations, "outcomes": blocked}

    def fan_out(state: WorkstreamState) -> list[Send] | str:
        """One Send per cleared task. The worker receives only its own task."""
        sends = []
        for tid in state.get("dispatch", []):
            spec = state["specs"][tid]
            sends.append(Send("run_specialist", {
                "project_id": state["project_id"], "correlation_id": state["correlation_id"],
                "workstream_id": state["workstream"]["workstream_id"],
                "task": state["tasks"][tid], "spec": spec,
                "reservation_id": state["reservations"][tid],
                "revision": state.get("revisions", {}).get(tid, 0),
                "comments": state.get("reviews", {}).get(tid, {}).get("comments", []),
            }, timeout=TimeoutPolicy(run_timeout=spec["budget"]["timeout_seconds"])))
        return sends or "workstream_result"

    async def evidence_gate(state: WorkstreamState) -> dict:
        """Code, not judgement: provenance and source quality of what was cited."""
        reviews = {}
        for tid in state.get("dispatch", []):
            outcome = SpecialistOutcome.model_validate(state["outcomes"][tid])
            if outcome.status != "awaiting_review":
                continue
            result: AgentResult = outcome.result
            by_id = {e.evidence_id: e for e in result.evidence}
            problems = []
            for claim in result.output.claims:
                cited = [by_id[i] for i in claim.evidence_ids]
                if any(e.captured_by_agent != result.agent_id for e in cited):
                    problems.append(f"{claim.claim_id}: cites evidence captured by another agent")
                if cited and sum(e.quality_score for e in cited) / len(cited) < MIN_EVIDENCE_QUALITY:
                    problems.append(f"{claim.claim_id}: sources are below the quality threshold")
                if claim.confidence == "high" and len(cited) < 2:
                    problems.append(f"{claim.claim_id}: high confidence needs two sources")
            if problems:
                reviews[tid] = ReviewDecision(
                    result_id=result.result_id, reviewer="evidence_gate", outcome="revise",
                    failed_criteria=problems).model_dump(mode="json")
        return {"reviews": reviews}

    def route_after_review(state: WorkstreamState) -> str:
        if svc.kill.cached(state["project_id"]):
            return "workstream_result"
        latest = [state["reviews"][t]["outcome"] for t in state.get("dispatch", [])
                  if t in state.get("reviews", {})]
        if "revise" in latest:
            return "budget_gate"
        if "need_additional_specialist" in latest and \
                state.get("recruit_rounds", 0) < MAX_RECRUIT_ROUNDS:
            return "build_agent_requests"
        return "workstream_result"

    async def workstream_result(state: WorkstreamState) -> dict:
        ws = state["workstream"]
        reviews, outcomes = state.get("reviews", {}), state.get("outcomes", {})
        accepted = {t: outcomes[t]["result"] for t, r in reviews.items()
                    if r["outcome"] == "accept"}
        gaps = [{"task_id": t, "objective": task["objective"],
                 "reason": (outcomes.get(t) or {}).get("error")
                 or "; ".join(reviews.get(t, {}).get("comments", [])) or "not staffed"}
                for t, task in state.get("tasks", {}).items() if t not in accepted]
        budget_blocked = any((outcomes.get(g["task_id"]) or {}).get("status") == "blocked_budget"
                             for g in gaps)
        status = ("complete" if not gaps else "partial_budget" if budget_blocked else "partial")
        return {"workstream_results": {ws["workstream_id"]: {
            "workstream_id": ws["workstream_id"], "lead": ws["lead"], "status": status,
            "accepted_results": accepted, "gaps": gaps}}}

    async def retire_workstream_agents(state: WorkstreamState) -> dict:
        """Sweep. Idempotent: agents retired at review time are returned unchanged."""
        agents, audit = {}, []
        for tid, raw in state.get("specs", {}).items():
            record = await asyncio.to_thread(
                svc.recruiter.retire, raw["agent_id"], final_status=AgentStatus.CANCELLED,
                reason="workstream closed")
            agents[raw["agent_id"]] = {"status": "retired", "task_id": tid,
                                       "final_status": record.final_status}
            audit.append({"type": "agent.retired", **record.model_dump(mode="json")})
        return {"agents": agents, "audit_events": audit}

    # ------------------------------------------------------------ wiring
    g = StateGraph(WorkstreamState, input_schema=WorkstreamInput, output_schema=Shared)
    g.add_node("analyse_and_decompose", analyse_and_decompose, retry_policy=LLM_RETRY)
    g.add_node("build_agent_requests", build_agent_requests, retry_policy=LLM_RETRY)
    g.add_node("recruit", recruit)
    g.add_node("budget_gate", budget_gate)
    g.add_node("run_specialist", run_specialist,
               retry_policy=RetryPolicy(max_attempts=2, retry_on=svc.is_transient),
               error_handler=on_specialist_error)
    g.add_node("guardrail_review", guardrail_review, retry_policy=LLM_RETRY)
    g.add_node("guardrail_hold", guardrail_hold)
    g.add_node("evidence_gate", evidence_gate)
    g.add_node("tester_validate", tester_validate, retry_policy=LLM_RETRY)
    g.add_node("lead_review", lead_review, retry_policy=LLM_RETRY)
    g.add_node("workstream_result", workstream_result)
    g.add_node("retire_workstream_agents", retire_workstream_agents)

    g.add_edge(START, "analyse_and_decompose")
    g.add_edge("analyse_and_decompose", "build_agent_requests")
    g.add_edge("build_agent_requests", "recruit")
    g.add_edge("recruit", "budget_gate")
    g.add_conditional_edges("budget_gate", fan_out, ["run_specialist", "workstream_result"])
    g.add_edge("run_specialist", "guardrail_review")
    g.add_edge("guardrail_review", "guardrail_hold")
    g.add_edge("guardrail_hold", "evidence_gate")
    g.add_edge("evidence_gate", "tester_validate")
    g.add_edge("tester_validate", "lead_review")
    g.add_conditional_edges("lead_review", route_after_review,
                            ["budget_gate", "build_agent_requests", "workstream_result"])
    g.add_edge("workstream_result", "retire_workstream_agents")
    g.add_edge("retire_workstream_agents", END)
    return g.compile()
