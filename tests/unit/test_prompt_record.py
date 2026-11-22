"""A run records which prompt it was given, including the skills that were skipped (WP-03)."""

from orchestrator.persistence.facade import AsyncStores
from orchestrator.prompts.agent_loader import load_agent
from orchestrator.prompts.record import record_prompt_load
from tests.conftest import run_async


def test_the_audit_event_names_the_hash_the_versions_and_every_skipped_skill() -> None:
    stores = AsyncStores.in_memory()
    agent = load_agent("solution-architect")

    async def scenario() -> dict[str, object]:
        event = await record_prompt_load(
            stores, agent, deployment="gpt-6-luna", project_id="prj_ab12"
        )
        return dict(event.details)

    details = run_async(scenario())
    stores.close()
    assert details["prompt_sha256"] == agent.sha256
    assert details["deployment"] == "gpt-6-luna" and details["model_key"] == "reasoning-standard"
    assert details["skills_loaded"] == ["solution-design@1.0.0"]
    skipped = details["skills_skipped"]
    assert isinstance(skipped, list) and len(skipped) == 2
    assert all("needs-content" in str(s) for s in skipped)
    assert "engineering-principles@0.1.0" in str(skipped)
    assert "prompt" not in details, "the text is identified by its hash, not stored"
