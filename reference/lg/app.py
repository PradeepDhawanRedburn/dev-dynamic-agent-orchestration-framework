"""Composition root: model catalogue, checkpointing, tracing, start, resume, cancel."""
import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any

import langsmith as ls
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from langchain_core.tracers.langchain import LangChainTracer
from langchain_openai import AzureChatOpenAI
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command
from langsmith import Client
from langsmith.anonymizer import create_anonymizer

from lead import build_lead_graph
from supervisor import HumanDecision, build_supervisor

ENV = os.environ.get("ORCH_ENV", "dev")


# ---------------------------------------------------------------- approved models only
class ModelCatalogue:
    """A specification names a catalogue key, never an endpoint or a secret."""

    def __init__(self, entries: dict[str, dict[str, str]]) -> None:
        self._entries = entries
        self._token = get_bearer_token_provider(
            DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default")

    def chat(self, key: str, *, temperature: float = 0.0, max_tokens: int = 4000):
        entry = self._entries[key]                    # KeyError: not an approved model
        return AzureChatOpenAI(
            azure_endpoint=entry["endpoint"], azure_deployment=entry["deployment"],
            api_version=entry["api_version"], azure_ad_token_provider=self._token,
            temperature=temperature, max_tokens=max_tokens, timeout=120,
            max_retries=0)                            # retries belong to the graph, not the client


# ---------------------------------------------------------------- LangSmith tracing
anonymizer = create_anonymizer([
    {"pattern": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "replace": "<email>"},
    {"pattern": r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*\S+", "replace": "<secret>"},
])
tracer = LangChainTracer(client=Client(anonymizer=anonymizer), project_name=f"orch-{ENV}")


def run_config(project_id: str, *, classification: str, versions: dict[str, str],
               max_agents: int) -> dict[str, Any]:
    return {
        "configurable": {"thread_id": project_id},     # one project = one checkpoint thread
        "recursion_limit": 150,                        # backstop against a routing defect
        "max_concurrency": max_agents,
        "callbacks": [tracer],
        "tags": [ENV, "orchestrator"],
        "metadata": {"project_id": project_id, "environment": ENV,
                     "data_classification": classification, **versions},
    }


@ls.traceable(run_type="chain", name="governance.cancel")
async def cancel(svc: Any, project_id: str, reason: str) -> int:
    """Project kill switch. Access is revoked now; the graph then routes to retire_all."""
    await svc.kill.set(project_id, reason)
    records = await asyncio.to_thread(svc.recruiter.retire_project, project_id, reason)
    return len(records)


# ---------------------------------------------------------------- checkpointing and lifecycle
@asynccontextmanager
async def orchestrator(svc: Any):
    async with AsyncPostgresSaver.from_conn_string(os.environ["CHECKPOINT_DB_URI"]) as saver:
        # `await saver.setup()` creates the checkpoint tables. Run it once from a
        # migration job with a privileged identity, not on every start.
        yield build_supervisor(svc, build_lead_graph(svc)).compile(checkpointer=saver)


async def surface_interrupts(svc: Any, project_id: str, result: dict) -> None:
    """Turn graph interrupts into approval requests. Idempotent by interrupt id."""
    for pending in result.get("__interrupt__", []):
        if pending.value.get("kind") == "await_worker":
            continue                                   # resumed by the worker's result message
        await svc.approvals.request(                   # also schedules the timeout message
            project_id=project_id, interrupt_id=pending.id, payload=pending.value,
            idempotency_key=f"approval:{project_id}:{pending.id}")


async def start_project(graph: Any, svc: Any, *, project_id: str, raw_request: str,
                        sponsor: str, limits: dict, classification: str,
                        versions: dict[str, str]) -> dict:
    config = run_config(project_id, classification=classification, versions=versions,
                        max_agents=svc.policy.max_concurrent_agents)
    result = await graph.ainvoke(
        {"project_id": project_id, "correlation_id": f"cor_{project_id}",
         "versions": versions, "raw_request": raw_request, "sponsor": sponsor,
         "limits": limits}, config)
    await surface_interrupts(svc, project_id, result)
    return result


async def resume(graph: Any, svc: Any, *, project_id: str, interrupt_id: str,
                 decision: HumanDecision, classification: str,
                 versions: dict[str, str]) -> dict:
    """Called by the approval service, a worker result, or the timeout message."""
    if decision.decision != "timeout":
        await svc.approvals.verify(project_id, interrupt_id, decision.approver)  # Entra identity and role
    config = run_config(project_id, classification=classification, versions=versions,
                        max_agents=svc.policy.max_concurrent_agents)
    result = await graph.ainvoke(
        Command(resume={interrupt_id: decision.model_dump(mode="json")}), config)
    await surface_interrupts(svc, project_id, result)
    return result
