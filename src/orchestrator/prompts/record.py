"""Record, on the audit log, which prompt a permanent agent's run was given (agents/README.md,
step 5: "Record the hash, the file versions and the model version on every run").

A skill that was skipped is named here, so a reader of the audit log can see that an agent ran
without the organisation's own knowledge, and why. The prompt text itself is not stored: the hash
and the versions identify it, and `tests/golden/` holds the text for every version."""

from pydantic import JsonValue

from orchestrator.persistence.audit import AuditEvent
from orchestrator.persistence.facade import AsyncStores
from orchestrator.prompts.agent_loader import LoadedAgent

ACTOR = "system:agent_loader"


async def record_prompt_load(
    stores: AsyncStores,
    agent: LoadedAgent,
    *,
    deployment: str,
    project_id: str | None = None,
    correlation_id: str | None = None,
) -> AuditEvent:
    details: dict[str, JsonValue] = {
        "role": agent.role,
        "version": agent.version,
        "profile": agent.profile,
        "prompt_sha256": agent.sha256,
        "model_key": agent.model_key,
        "deployment": deployment,
        "file_versions": dict(agent.file_versions),
        "skills_loaded": list(agent.skills_loaded),
        "skills_skipped": [f"{s.name}@{s.version}: {s.reason}" for s in agent.skills_skipped],
    }
    return await stores.audit.append(
        "agent.prompt_loaded",
        actor=ACTOR,
        project_id=project_id,
        correlation_id=correlation_id,
        details=details,
    )
