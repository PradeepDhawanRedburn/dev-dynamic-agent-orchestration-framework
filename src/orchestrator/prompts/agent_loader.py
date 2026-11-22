"""Load a permanent agent's prompt from `agents/` (ADR-0025, ADR-0027; agents/README.md).

The prompt is never written in code. This module reads the role's file and builds the system prompt
in the order the README fixes:

1. the `System prompt` block of `agents/<role>.agent.md`;
2. `{{organisational-policy}}` replaced by `agents/_shared/organisational-policy.md`, which always
   comes first;
3. `{{domain-profile}}` (Lead, Tester, Guardrail Manager only) replaced by the profile's Scope
   block, plus its Lead focus (Lead) or Tester focus (Tester); the Guardrail Manager gets the scope
   only;
4. each skill in the file's `skills` list appended in order. A skill marked `needs-content` is
   skipped, and the skip is recorded, never hidden (ADR-0027);
5. the result is hashed (SHA-256 of the UTF-8 text, line endings normalised to LF).

The hash and the versions of every file used are returned so a run can record them. The
`business-research` profile is deferred (ADR-0022) and loads only when asked for explicitly."""

import hashlib
import os
import re
from pathlib import Path

from pydantic import Field

from orchestrator.contracts import Contract

AGENTS_DIRECTORY_VARIABLE = "ORCHESTRATOR_AGENTS_DIR"
DEFAULT_AGENTS_DIRECTORY = Path(__file__).resolve().parents[3] / "agents"
PROFILED_ROLES = frozenset({"lead", "tester", "guardrail-manager"})
FOCUS_BLOCK = {"lead": "Lead focus", "tester": "Tester focus", "guardrail-manager": None}
NEEDS_CONTENT = "needs-content"
POLICY_PLACEHOLDER = "{{organisational-policy}}"
PROFILE_PLACEHOLDER = "{{domain-profile}}"

_FRONT_MATTER = re.compile(r"---\n(.*?)\n---\n(.*)", re.S)
_PLACEHOLDER = re.compile(r"\{\{[a-z-]+\}\}")


class AgentDefinitionError(ValueError):
    """A definition file is missing, malformed, or asks for something the rules forbid."""


class SkippedSkill(Contract):
    name: str
    version: str
    reason: str


class LoadedAgent(Contract):
    role: str
    title: str
    version: str
    status: str
    model_key: str
    tools: list[str]
    output_schemas: list[str]
    profile: str | None = None
    skills_loaded: list[str] = Field(description="name@version, in the order they were appended")
    skills_skipped: list[SkippedSkill]
    file_versions: dict[str, str] = Field(
        description="Version of every file the prompt was built from"
    )
    prompt: str
    sha256: str


def agents_directory() -> Path:
    return Path(os.environ.get(AGENTS_DIRECTORY_VARIABLE) or DEFAULT_AGENTS_DIRECTORY)


def _read(path: Path) -> str:
    if not path.is_file():
        raise AgentDefinitionError(f"{path.name}: file not found")
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _front_matter(path: Path, text: str) -> tuple[dict[str, str], str]:
    match = _FRONT_MATTER.match(text)
    if match is None:
        raise AgentDefinitionError(f"{path.name}: no front matter")
    pairs = [line.split(":", 1) for line in match.group(1).splitlines() if ":" in line]
    return {key.strip(): value.strip() for key, value in pairs}, match.group(2)


def _text_block(path: Path, body: str, heading: str) -> str:
    found = re.search(rf"## {re.escape(heading)}\n\n```text\n(.*?)\n```", body, re.S)
    if found is None:
        raise AgentDefinitionError(f"{path.name}: no ```text block under '## {heading}'")
    return found.group(1)


def _names(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip() and item.strip() != "none"]


def load_agent(
    role: str,
    *,
    profile: str | None = None,
    allow_deferred_profile: bool = False,
    directory: Path | None = None,
) -> LoadedAgent:
    root = directory or agents_directory()
    path = root / f"{role}.agent.md"
    meta, body = _front_matter(path, _read(path))
    if meta.get("name") != role:
        raise AgentDefinitionError(f"{path.name}: name must be {role!r}")

    if (role in PROFILED_ROLES) != (profile is not None):
        raise AgentDefinitionError(
            f"{role}: a domain profile is required for lead, tester and guardrail-manager, "
            "and for no other role"
        )

    versions = {f"{role}.agent.md": meta["version"]}
    prompt = _text_block(path, body, "System prompt")

    policy_path = root / "_shared" / "organisational-policy.md"
    policy_text = _read(policy_path)
    policy_version = re.search(r"\*\*Version:\*\*\s*(\S+)", policy_text)
    versions["_shared/organisational-policy.md"] = policy_version.group(1) if policy_version else ""
    if POLICY_PLACEHOLDER not in prompt:
        raise AgentDefinitionError(f"{path.name}: the prompt has no {POLICY_PLACEHOLDER}")
    prompt = prompt.replace(POLICY_PLACEHOLDER, _policy(policy_path, policy_text))

    if profile is not None:
        prompt = _with_profile(
            root, role, prompt, profile, versions, allow_deferred=allow_deferred_profile
        )

    loaded: list[str] = []
    skipped: list[SkippedSkill] = []
    for name in _names(meta.get("skills", "none")):
        skill_path = root / "skills" / f"{name}.md"
        skill_meta, skill_body = _front_matter(skill_path, _read(skill_path))
        if role not in _names(skill_meta.get("used_by", "")):
            raise AgentDefinitionError(f"skill {name!r} does not list {role} in used_by")
        version = skill_meta["version"]
        if skill_meta.get("status") == NEEDS_CONTENT:
            skipped.append(
                SkippedSkill(
                    name=name,
                    version=version,
                    reason="needs-content: the owner has not supplied it",
                )
            )
            continue
        prompt = f"{prompt}\n\n{_text_block(skill_path, skill_body, 'Skill text')}"
        loaded.append(f"{name}@{version}")
        versions[f"skills/{name}.md"] = version

    leftover = _PLACEHOLDER.findall(prompt)
    if leftover:
        raise AgentDefinitionError(f"{path.name}: unresolved placeholders {sorted(set(leftover))}")

    return LoadedAgent(
        role=role,
        title=meta["title"],
        version=meta["version"],
        status=meta["status"],
        model_key=meta["model_key"],
        tools=_names(meta.get("tools", "none")),
        output_schemas=_names(meta.get("output_schemas", "")),
        profile=profile,
        skills_loaded=loaded,
        skills_skipped=skipped,
        file_versions=versions,
        prompt=prompt,
        sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
    )


def _policy(path: Path, text: str) -> str:
    found = re.search(r"```text\n(.*?)\n```", text, re.S)
    if found is None:
        raise AgentDefinitionError(f"{path.name}: no ```text block")
    return found.group(1)


def _with_profile(
    root: Path,
    role: str,
    prompt: str,
    profile: str,
    versions: dict[str, str],
    *,
    allow_deferred: bool,
) -> str:
    path = root / "profiles" / f"{profile}.md"
    meta, body = _front_matter(path, _read(path))
    if "deferred" in meta.get("status", "").lower() and not allow_deferred:
        raise AgentDefinitionError(f"profile {profile!r} is deferred and not loaded by default")
    if PROFILE_PLACEHOLDER not in prompt:
        raise AgentDefinitionError(f"{role}: the prompt has no {PROFILE_PLACEHOLDER}")
    blocks = [_text_block(path, body, "Scope")]
    focus = FOCUS_BLOCK[role]
    if focus is not None:
        blocks.append(_text_block(path, body, focus))
    versions[f"profiles/{profile}.md"] = meta["version"]
    return prompt.replace(PROFILE_PLACEHOLDER, "\n\n".join(blocks))
