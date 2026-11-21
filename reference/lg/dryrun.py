"""Scripted dry run. Governance code is the real, tested code. The model, the agent
loop and the graph runtime are stand-ins (see stubs/). It checks node logic and routing."""
import asyncio, json, re, sys, types
from decimal import Decimal
sys.path[:0] = ["stubs", ".", ".."]
from pydantic import BaseModel
from contracts import *
from budget import InMemoryLedger
from recruiter import Recruiter, InMemoryAgentRegistry, Policy
from tool_registry import ToolDefinition, ToolRegistry
from guardrails import GuardrailMonitor
from resilience import SelfHealer, Step
import langgraph.types as lt, langchain.agents as la
from lead import build_lead_graph
from supervisor import build_supervisor

ids = lambda pat, text: list(dict.fromkeys(re.findall(pat + r"_[0-9a-f]{16}", text)))
CALLS = {"data_quality": 0}

# ---------------------------------------------------------------- scripted permanent agents
def scripted(schema, system, user):
    n = schema.__name__
    if n == "RequirementDraft":
        return schema(title="Replace nightly batch integration", business_outcome="Decide whether to move order-to-warehouse integration from nightly batch to event streaming, with an evidence-based recommendation.",
            constraints=["Azure only", "No production changes during the study"],
            success_criteria=[SuccessCriterion(statement="Options are compared on latency, cost and operational effort", measure="Comparison table with evidence for each cell"),
                              SuccessCriterion(statement="Data quality and lineage impact is assessed", measure="Named risks with mitigations"),
                              SuccessCriterion(statement="Source-system API constraints are identified", measure="List of constraints with vendor references")])
    if n == "PlanDraft":
        sc = ids("sc", user)
        return schema(workstreams=[dict(title="Data integration and quality", lead="lead_data_engineer", objective="Compare batch and streaming integration patterns and assess data quality and lineage impact", covers_criteria=sc[:2], budget_share=0.6),
                                   dict(title="Source-system interfaces", lead="lead_software_engineer", objective="Identify API and change-capture constraints of the order-management system", covers_criteria=sc[2:], budget_share=0.4)])
    if n == "TaskDrafts":
        if "quality" in user:
            return schema(tasks=[dict(objective="Compare streaming and batch options on latency, cost and operational effort", expected_output="Comparison with evidence", acceptance_criteria=["Each option has latency, cost and effort evidence"]),
                                 dict(objective="Assess data quality and lineage risks of moving to streaming", expected_output="Risk list with mitigations", acceptance_criteria=["Each risk has a mitigation and a source"])])
        return schema(tasks=[dict(objective="Identify API rate limits and change-data-capture support of the order-management system", expected_output="Constraint list with vendor references", acceptance_criteria=["Each constraint cites vendor documentation"])])
    if n == "RequestDrafts":
        out = []
        for tid in ids("task", user.split("Capability tags")[0]):
            seg = user[user.index(tid):]
            if "latency" in seg[:400]: role, exp = "Streaming platform analyst", ["Event streaming on Azure", "Batch ETL"]
            elif "lineage" in seg[:400]: role, exp = "Data quality analyst", ["Data quality", "Lineage"]
            elif "Challenge" in seg[:400]: role, exp = "Red-team reviewer", ["Evidence review"]
            else: role, exp = "Integration API specialist", ["REST APIs", "Change data capture"]
            cap = ["accepted_results"] if role == "Red-team reviewer" else ["web_research"]
            out.append(dict(task_id=tid, role_title=role, required_expertise=exp, scope=["Vendor and Microsoft documentation"], exclusions=["Commercial negotiation"],
                            capabilities_needed=cap, evidence_requirements=["Two independent sources for any high-confidence claim"], justification="No active agent covers this task in the workstream."))
        return schema(requests=out)
    if n == "ReviewDrafts":
        return schema(reviews=[dict(task_id=t, outcome="accept", comments=["Meets acceptance criteria"]) for t in ids("task", user)])
    if n == "ConsolidationDraft": return schema()
    if n == "GuardrailJudgements": return schema(judgements=[dict(agent_id=a, suspend=False, reason="Within scope; flags look like ordinary documentation text.") for a in ids("agt", user)])
    if n == "TestDrafts":
        out = []
        for tid in ids("task", user):
            seg = user[user.index(tid):].split("TASK task_")[0]
            bad = "higher steady-state platform cost" in seg and CALLS.setdefault("streaming_tests", 0) == 0
            if "higher steady-state platform cost" in seg: CALLS["streaming_tests"] += 1
            out.append(dict(task_id=tid, passed=not bad, failed_checks=["Cost claim: the cited extract does not state a cost comparison"] if bad else []))
        return schema(tests=out)
    if n == "DeliverableDraft":
        return schema(executive_summary="Streaming is feasible, cuts latency from next-day to seconds, and costs more to run; quality risks are manageable.", recommendations=["Run a bounded pilot on one order feed", "Design idempotent loads and watermarking before the pilot"],
                      criteria_coverage={c: "met" for c in ids("sc", user)}, claim_ids=ids("cl", user), unresolved_conflicts=[])
    if n == "Assessment": return schema(recommendation="approve", rationale="All mandatory criteria are met with cited evidence.")
    raise KeyError(n)

class FakeChat:
    def __init__(self, key): self.key = key
    def with_structured_output(self, schema, include_raw=False): self.schema = schema; return self
    async def ainvoke(self, msgs):
        raw = types.SimpleNamespace(usage_metadata={"input_tokens": 2500, "output_tokens": 600})
        return {"raw": raw, "parsed": scripted(self.schema, msgs[0][1], msgs[1][1]), "parsing_error": None}

# ---------------------------------------------------------------- scripted specialists
async def search(tools, q): return json.loads(await tools["web_search"].coroutine(query=q))["items"]
def out(summary, claims, status="complete", conf="medium", limits=()):
    return SpecialistOutput(executive_summary=summary, findings=[c.statement for c in claims], claims=claims, limitations=list(limits),
                            recommended_next_action="Hand to lead for review", completion_status=status, overall_confidence=conf)
async def streaming(tools, inp):
    ev = [i["evidence_id"] for i in await search(tools, "azure event streaming vs batch latency cost")]
    return out("Streaming cuts latency from hours to seconds at higher run cost.", [
        Claim(statement="Managed event streaming delivers order events in seconds rather than the next day.", evidence_ids=ev, confidence="high"),
        Claim(statement="Streaming has a higher steady-state platform cost than a nightly batch job.", evidence_ids=ev[:1], confidence="medium")])
async def quality(tools, inp):
    CALLS["data_quality"] += 1
    ev = [i["evidence_id"] for i in await search(tools, "streaming data quality lineage late events")]
    first = CALLS["data_quality"] == 1
    return out("Late and duplicate events are the main quality risks.", [
        Claim(statement="Out-of-order and duplicate events require idempotent loads and watermarking.", evidence_ids=ev[:1] if first else ev, confidence="high")])
async def api(tools, inp):
    CALLS["api"] = CALLS.get("api", 0) + 1
    ev = [i["evidence_id"] for i in await search(tools, "order management api rate limits cdc")]
    if CALLS["api"] == 2: ev += [i["evidence_id"] for i in await search(tools, "order management webhook limits cdc")]
    cited = ["ev_0000000000000000"] if CALLS["api"] == 1 else ev        # first attempt invents a source
    return out("The API supports change capture with documented rate limits.", [Claim(statement="The vendor API supports change data capture and enforces per-minute rate limits.", evidence_ids=cited, confidence="medium")])
async def reviewer(tools, inp):
    items = json.loads(await tools["results_reader"].coroutine(scope="accepted"))["items"]
    ev = [i["evidence_id"] for i in items]
    return out("No unsupported claims in accepted results; API criterion is unaddressed.", [
        Claim(statement="The source-system API criterion has no accepted evidence.", evidence_ids=ev, confidence="high")], limits=["Reviewed accepted results only"])
la.SCRIPT.update({"specialist:Streaming platform analyst": streaming, "specialist:Data quality analyst": quality,
                  "specialist:Integration API specialist": api, "specialist:Red-team reviewer": reviewer})

# ---------------------------------------------------------------- services
class Args(BaseModel): query: str = ""; scope: str = ""
class Impl:
    args_model = Args
    def __init__(self, kind): self.kind, self.calls = kind, 0
    async def run(self, args, ctx):
        self.calls += 1
        if self.kind == "web" and self.calls == 1: raise ConnectionResetError("connection reset by peer")
        return {"items": [{"text": f"{self.kind} extract {i} for {args}", "reference": f"https://learn.microsoft.com/example/{self.kind}/{i}",
                           "source_type": "primary_document" if self.kind == "web" else "enterprise_record", "title": f"{self.kind} source {i}", "quality": 0.8} for i in (1, 2)]}
class Creds:
    def __init__(self): self.live, self.frozen = {}, set()
    def issue(self, a, grants, ttl): self.live[a] = {g.tool_name for g in grants}
    def revoke(self, a): self.live.pop(a, None); self.frozen.discard(a); return True
    def freeze(self, a): self.frozen.add(a)
    def unfreeze(self, a): self.frozen.discard(a)
    async def is_live(self, a, tool): return a not in self.frozen and tool in self.live.get(a, ())
class Mem:
    def __init__(self): self.ns = set()
    def create(self, n): self.ns.add(n)
    def retire(self, n, p): self.ns.discard(n); return "deleted"
class Meter:
    RATE_IN, RATE_OUT = Decimal("0.003"), Decimal("0.012")     # made-up price per 1k tokens
    def __init__(self): self.u = {}
    def _g(self, o): return self.u.setdefault(o, Usage())
    async def add_model_call(self, o, dep, i, t):
        u = self._g(o); u.input_tokens += i; u.output_tokens += t; u.model_calls += 1
        u.cost += (i * self.RATE_IN + t * self.RATE_OUT) / 1000
    async def add_tool_call(self, o, c): u = self._g(o); u.tool_calls += 1; u.cost += c
    async def read(self, o): return self._g(o).model_copy()
    async def attribute(self, o, reservation):
        self.attr = getattr(self, "attr", {})
        if (o, reservation) not in self.attr:
            done = sum((u.cost for (a, _), u in self.attr.items() if a == o), Decimal(0))
            self.attr[(o, reservation)] = Usage(cost=self._g(o).cost - done)
        return self.attr[(o, reservation)]
    async def project_total(self, p):
        t = Usage()
        for u in self.u.values():
            for f in ("input_tokens", "output_tokens", "model_calls", "tool_calls", "cost"): setattr(t, f, getattr(t, f) + getattr(u, f))
        return t
class Ev:
    def __init__(self): self.items = []
    def score(self, item): return item.get("quality", 0.5)
    async def put(self, e): self.items.append(e)
    async def for_agent(self, p, a): return [e for e in self.items if e.captured_by_agent == a]
class Counters:
    def __init__(self): self.c = {}
    async def increment(self, a, t): self.c[(a, t)] = self.c.get((a, t), 0) + 1; return self.c[(a, t)]
class Audit:
    def __init__(self): self.rows = []
    async def record(self, kind, spec, **kw):
        self.rows.append((kind, spec.agent_id, kw)); self.monitor.observe(spec.agent_id, kind)   # the audit sink feeds the guardrail monitor

def make_services():
    tools = ToolRegistry(); common = dict(input_schema={}, output_schema={}, required_permission="Tools.Read", timeout_seconds=30, max_retries=1, produces_evidence=True)
    tools.register(ToolDefinition(name="web_search", version="1.0.0", description="Search public documentation through the egress proxy", max_classification=Classification.INTERNAL,
                                  network_scope="internet_egress_proxy", permitted_lead_roles=set(LeadRole), capability_tags={"web_research"}, cost_per_call=0.01, **common), Impl("web"))
    tools.register(ToolDefinition(name="results_reader", version="1.0.0", description="Read accepted results and their evidence for this project", max_classification=Classification.CONFIDENTIAL,
                                  network_scope="none", permitted_lead_roles=set(LeadRole), capability_tags={"accepted_results"}, **common), Impl("results"))
    svc = types.SimpleNamespace(); creds = Creds(); owners = {}
    svc.tools, svc.credentials, svc.ledger, svc.ledger_meter = tools, creds, InMemoryLedger(), Meter()
    svc.policy = Policy()
    svc.recruiter = Recruiter(tools=tools, agents=InMemoryAgentRegistry(), credentials=creds, memory=Mem(), policy=svc.policy, task_owner=lambda t: owners[t])
    svc.owners = owners
    svc.kill = types.SimpleNamespace(cached=lambda *a: False)
    svc.models = types.SimpleNamespace(chat=lambda key, **kw: FakeChat(key))
    svc.evidence, svc.counters, svc.audit = Ev(), Counters(), Audit()
    svc.injection = types.SimpleNamespace(flag=lambda text: "cdc" in text)
    svc.guardrail = GuardrailMonitor(lambda a, why: svc.recruiter.suspend(a, why)); svc.audit.monitor = svc.guardrail
    svc.incidents = []
    async def ok(inc, n): return True
    async def rec_inc(inc): svc.incidents.append(inc)
    svc.healer = SelfHealer({s: ok for s in Step if s is not Step.ESCALATE}, rec_inc)
    ap = lambda: types.SimpleNamespace(model_key="reasoning-standard", prompt="p")
    svc.assurance_profiles = {r.value: {"tester": ap(), "guardrail": ap()} for r in LeadRole}
    async def org_search(lead, q): return ["ADR-014 integration standards"]
    svc.org_memory = types.SimpleNamespace(search=org_search)
    prof = types.SimpleNamespace(model_key="reasoning-standard", decompose_prompt="decompose", staffing_prompt="staff", review_prompt="review", grantable_capabilities={"web_research", "accepted_results"})
    svc.lead_profiles = {r.value: prof for r in LeadRole}
    p = types.SimpleNamespace(model_key="reasoning-standard", intake_prompt="i", assess_prompt="a", decompose_prompt="d", consolidate_prompt="c", triage_prompt="t", assemble_prompt="f")
    svc.permanent_profiles = types.SimpleNamespace(cto=p, hod=p)
    svc.is_transient = lambda e: False
    async def store(*a): svc.archived = a
    svc.archive = types.SimpleNamespace(store=store)
    from worker import ToolGateway
    svc.gateway = ToolGateway(svc)
    return svc

async def main():
    svc = make_services()
    # task ownership comes from the plan; in this harness we learn it as tasks are created
    real_provision = svc.recruiter.provision
    def provision(req, **kw): svc.owners[req.task_id] = req.requested_by; return real_provision(req, **kw)
    svc.recruiter.provision = provision
    graph = build_supervisor(svc, build_lead_graph(svc)).compile()
    def guard(v):
        svc.guardrail_gate = v
        return {"approver": "security-owner-oid", "decisions": {a: "resume" for a in v["suspended"]}}
    lt.ANSWERS[:] = [lambda v: {"decision": "approve", "approver": "sponsor-oid"}, guard,
                     lambda v: {"decision": "approve", "approver": "sponsor-oid", "comment": "Approved. Proceed to pilot planning."}]
    limits = BudgetPolicy(max_cost=Decimal("40"), max_tokens=2_000_000, max_tool_calls=120, max_model_calls=120, timeout_seconds=600, max_retries=1)
    state = {"project_id": "prj_" + "ab12" * 4, "correlation_id": "cor_1", "versions": {"graph": "0.1.0", "policy": "2026.11.0"},
             "raw_request": "Should we replace nightly batch integration between order management and the warehouse with event streaming?",
             "sponsor": "sponsor-oid", "limits": limits.model_dump(mode="json")}
    trace = []
    await graph.run(state, trace)
    return svc, state, trace

if __name__ == "__main__":
    svc, state, trace = asyncio.run(main())
    print("TRACE:", " > ".join(trace))
    print("OUTCOME:", state["outcome"])
    for ws_id, r in state["workstream_results"].items():
        print("WS", r["lead"], r["status"], "accepted:", len(r["accepted_results"]), "gaps:", [(g["objective"][:40], g["reason"][:70]) for g in r["gaps"]])
    d = state["deliverable"]
    print("DELIVERABLE claims:", len(d["claims"]), "evidence:", len(d["evidence_ids"]), "coverage:", list(d["criteria_coverage"].values()))
    print("USAGE:", d["total_usage"])
    print("ASSESSMENT:", state["assessment"]["recommendation"])
    for r in svc.recruiter.agents.for_project(state["project_id"]):
        print("AGENT", r.spec.role_title, "|", r.spec.accountable_lead.value, "|", " > ".join(s.value for s, _ in r.history), "| tools", [t.tool_name for t in r.spec.tools], "| model", r.spec.model.deployment)
    print("LIVE CREDS:", svc.credentials.live, "| MEM:", svc.recruiter.memory.ns)
    print("LEDGER:", svc.ledger.snapshot(state["project_id"]))
    print("REVISIONS:", {k: v for k, v in state.get("agents", {}).items()} and CALLS)
    print("GUARD GATE:", getattr(svc, "guardrail_gate", None))
    print("INCIDENTS:", [(i.agent_id[-4:], i.operation, i.kind.value, [(s.value, ok) for s, ok in i.steps_tried], i.resolved) for i in svc.incidents])
    print("GUARD EVENTS:", [e for e in state["audit_events"] if e["type"].startswith(("guardrail", "test"))])
    print("AUDIT kinds:", sorted({k for k, *_ in svc.audit.rows}), "| events:", sorted({e["type"] for e in state["audit_events"]}))
    for o, u in svc.ledger_meter.u.items(): print("METER", o, u.model_calls, u.tool_calls, u.cost)

    r = svc.recruiter.agents.for_project(state["project_id"])[1]
    print("=== SPEC"); print(json.dumps(r.spec.model_dump(mode="json", exclude={"prompt"}), indent=1)[:1800])
    print("=== PROMPT sha", r.spec.prompt.sha256[:12]); print(r.spec.prompt.rendered)
