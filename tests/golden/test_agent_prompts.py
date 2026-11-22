"""Golden files for the assembled prompts of the twelve roles and the five profiles (WP-03).

`tests/golden/prompts/` holds the exact system prompt each role gets, and `manifest.json` holds its
hash, the versions of the files it was built from, and the skills that were skipped. A change to
anything under `agents/` changes a golden file, so a prompt change is always visible in the diff
of a pull request (ADR-0025).

To accept a deliberate change:  ORCHESTRATOR_UPDATE_GOLDEN=1 python -m pytest tests/golden
then read the diff before committing it."""

import json
import os
import re
from pathlib import Path

import pytest

from orchestrator.prompts.agent_loader import (
    PROFILED_ROLES,
    AgentDefinitionError,
    LoadedAgent,
    agents_directory,
    load_agent,
)

GOLDEN = Path(__file__).parent / "prompts"
MANIFEST = Path(__file__).parent / "manifest.json"
UPDATE = os.environ.get("ORCHESTRATOR_UPDATE_GOLDEN") == "1"

ROLES = sorted(p.name.removesuffix(".agent.md") for p in agents_directory().glob("*.agent.md"))
PROFILES = sorted(p.stem for p in (agents_directory() / "profiles").glob("*.md"))
CASES = [(role, None) for role in ROLES if role not in PROFILED_ROLES] + [
    (role, profile) for role in sorted(PROFILED_ROLES) for profile in PROFILES
]


def case_name(role: str, profile: str | None) -> str:
    return role if profile is None else f"{role}--{profile}"


def load(role: str, profile: str | None) -> LoadedAgent:
    return load_agent(role, profile=profile, allow_deferred_profile=True)


def manifest_entry(agent: LoadedAgent) -> dict[str, object]:
    return {
        "sha256": agent.sha256,
        "version": agent.version,
        "model_key": agent.model_key,
        "file_versions": agent.file_versions,
        "skills_loaded": agent.skills_loaded,
        "skills_skipped": [s.name for s in agent.skills_skipped],
    }


def test_there_are_twelve_roles_and_five_profiles() -> None:
    assert len(ROLES) == 12
    assert len(PROFILES) == 5
    assert len(CASES) == 9 + 3 * 5


def test_update_goldens() -> None:
    """Rewrites the golden files only when ORCHESTRATOR_UPDATE_GOLDEN=1; otherwise a no-op."""
    if not UPDATE:
        pytest.skip("set ORCHESTRATOR_UPDATE_GOLDEN=1 to rewrite the golden files")
    GOLDEN.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {}
    for role, profile in CASES:
        agent = load(role, profile)
        name = case_name(role, profile)
        (GOLDEN / f"{name}.txt").write_text(agent.prompt + "\n", encoding="utf-8", newline="\n")
        manifest[name] = manifest_entry(agent)
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@pytest.mark.parametrize("role,profile", CASES, ids=[case_name(r, p) for r, p in CASES])
def test_the_assembled_prompt_matches_its_golden_file(role: str, profile: str | None) -> None:
    name = case_name(role, profile)
    agent = load(role, profile)
    golden = (GOLDEN / f"{name}.txt").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert agent.prompt + "\n" == golden, (
        f"{name}: run with ORCHESTRATOR_UPDATE_GOLDEN=1 if intended"
    )
    entry = json.loads(MANIFEST.read_text(encoding="utf-8"))[name]
    assert manifest_entry(agent) == entry


def test_no_golden_file_is_stale() -> None:
    expected = {f"{case_name(r, p)}.txt" for r, p in CASES}
    assert {p.name for p in GOLDEN.glob("*.txt")} == expected
    assert set(json.loads(MANIFEST.read_text(encoding="utf-8"))) == {
        case_name(r, p) for r, p in CASES
    }


@pytest.mark.parametrize("role,profile", CASES, ids=[case_name(r, p) for r, p in CASES])
def test_every_prompt_is_complete(role: str, profile: str | None) -> None:
    agent = load(role, profile)
    assert agent.prompt.startswith("You are a permanent agent")
    assert not re.search(r"\{\{[a-z-]+\}\}", agent.prompt)
    assert len(agent.sha256) == 64


# ------------------------------------------------------------ what each role's assembly includes
def test_the_lead_gets_scope_and_lead_focus_but_not_tester_focus() -> None:
    prompt = load("lead", "data").prompt
    assert "DOMAIN PROFILE: Data" in prompt
    assert "Treat data quality and lineage as requirements" in prompt
    assert "Every data claim names the system of record" not in prompt


def test_the_tester_gets_scope_and_tester_focus_but_not_lead_focus() -> None:
    prompt = load("tester", "data").prompt
    assert "DOMAIN PROFILE: Data" in prompt
    assert "Every data claim names the system of record" in prompt
    assert "Treat data quality and lineage as requirements" not in prompt


def test_the_guardrail_manager_gets_the_scope_only() -> None:
    prompt = load("guardrail-manager", "data").prompt
    assert "DOMAIN PROFILE: Data" in prompt
    assert "Treat data quality and lineage" not in prompt
    assert "Every data claim names the system of record" not in prompt


def test_the_policy_comes_first_in_every_prompt() -> None:
    for role, profile in CASES:
        assert load(role, profile).prompt.startswith("You are a permanent agent")


def test_the_prompt_hash_is_the_hash_of_the_prompt_and_changes_with_it() -> None:
    import hashlib

    a, b = load("lead", "data"), load("lead", "software")
    assert a.sha256 == hashlib.sha256(a.prompt.encode()).hexdigest()
    assert a.sha256 != b.sha256


def test_roles_without_a_profile_refuse_one_and_profiled_roles_require_one() -> None:
    with pytest.raises(AgentDefinitionError, match="profile"):
        load_agent("reviewer", profile="data")
    with pytest.raises(AgentDefinitionError, match="profile"):
        load_agent("lead")


def test_the_deferred_profile_is_not_loaded_unless_asked_for() -> None:
    with pytest.raises(AgentDefinitionError, match="deferred"):
        load_agent("lead", profile="business-research")
    assert load_agent("lead", profile="business-research", allow_deferred_profile=True)


# ------------------------------------------------------------ skills
NEEDS_CONTENT = {
    "engineering-principles",
    "azure-reference-architecture",
    "approved-ai-models-and-standards",
    "security-and-data-policy",
}


def test_a_needs_content_skill_is_skipped_and_the_skip_is_recorded() -> None:
    agent = load("solution-architect", None)
    assert {s.name for s in agent.skills_skipped} == {
        "engineering-principles",
        "azure-reference-architecture",
    }
    assert [s.split("@")[0] for s in agent.skills_loaded] == ["solution-design"]
    assert all("needs-content" in s.reason for s in agent.skills_skipped)
    skill_text = (agents_directory() / "skills" / "engineering-principles.md").read_text(
        encoding="utf-8"
    )
    placeholder = re.search(r"## Skill text\n\n```text\n(.*?)\n```", skill_text, re.S)
    if placeholder and placeholder.group(1).strip():
        assert placeholder.group(1) not in agent.prompt


def test_skills_are_appended_in_the_order_the_file_lists_them() -> None:
    agent = load("ai-specialist", None)
    assert [s.split("@")[0] for s in agent.skills_loaded] == ["ai-evaluation-and-risk"]
    assert [s.name for s in agent.skills_skipped] == ["approved-ai-models-and-standards"]


def test_every_needs_content_skill_is_skipped_wherever_it_is_used() -> None:
    for role, profile in CASES:
        agent = load(role, profile)
        loaded = {s.split("@")[0] for s in agent.skills_loaded}
        assert not loaded & NEEDS_CONTENT, role


def test_a_skill_that_is_filled_in_is_loaded_instead_of_skipped(tmp_path: Path) -> None:
    import shutil

    shutil.copytree(agents_directory(), tmp_path / "agents")
    skill = tmp_path / "agents" / "skills" / "engineering-principles.md"
    text = skill.read_text(encoding="utf-8").replace("status: needs-content", "status: draft")
    text = re.sub(
        r"(## Skill text\n\n```text\n).*?(\n```)", r"\1PRINCIPLE ONE: be kind.\2", text, flags=re.S
    )
    skill.write_text(text, encoding="utf-8")
    agent = load_agent("cto-agent", directory=tmp_path / "agents")
    assert agent.skills_skipped == []
    assert "PRINCIPLE ONE: be kind." in agent.prompt
    assert agent.skills_loaded == ["engineering-principles@0.1.0"]


def test_a_skill_the_role_may_not_use_is_refused(tmp_path: Path) -> None:
    import shutil

    shutil.copytree(agents_directory(), tmp_path / "agents")
    agent_file = tmp_path / "agents" / "reviewer.agent.md"
    agent_file.write_text(
        agent_file.read_text(encoding="utf-8").replace(
            "skills: independent-review", "skills: test-design"
        ),
        encoding="utf-8",
    )
    with pytest.raises(AgentDefinitionError, match="used_by"):
        load_agent("reviewer", directory=tmp_path / "agents")


def test_the_prompt_does_not_depend_on_line_endings(tmp_path: Path) -> None:
    import shutil

    shutil.copytree(agents_directory(), tmp_path / "agents")
    expected = load_agent("recruiter").sha256
    for path in (tmp_path / "agents").rglob("*.md"):
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert load_agent("recruiter", directory=tmp_path / "agents").sha256 == expected


def test_the_model_keys_and_tools_come_from_the_file() -> None:
    reviewer = load_agent("reviewer")
    assert reviewer.model_key == "reasoning-alternate"
    assert reviewer.tools == ["results_read", "evidence_read"]
    assert load_agent("head-of-delivery").tools == []
