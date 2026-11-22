"""System-prompt compiler. Prompts are assembled from versioned, reviewed sections.
Lead-authored text fills bounded slots only and is linted before use."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Sequence
from pathlib import Path
from string import Template

from orchestrator.contracts import (
    AgentRequest,
    BudgetPolicy,
    PromptSection,
    SystemPromptSpecification,
    ToolPermission,
)
from orchestrator.prompts.location import (
    AGENTS_DIRECTORY_VARIABLE,
    AgentsDirectoryError,
    agents_directory,
)

COMPILER_VERSION = "1.0.0"

_SECTION_VERSIONS = {
    "organisational_policy": "1.2.0",
    "role": "1.0.0",
    "standards": "1.0.0",
    "task": "1.0.0",
    "tools": "1.1.0",
    "memory_and_communication": "1.0.0",
    "evidence": "1.0.0",
    "output": "1.0.0",
    "limits": "1.0.0",
    "escalation_and_completion": "1.0.0",
}
_SECTION_DIR_NAME = Path("_shared") / "compiler_sections"


def _load_sections() -> list[tuple[str, str, str]]:
    """Read at import, so a wrong ORCHESTRATOR_AGENTS_DIR stops the process at startup."""
    section_dir = agents_directory() / _SECTION_DIR_NAME
    loaded: list[tuple[str, str, str]] = []
    for name, version in _SECTION_VERSIONS.items():
        path = section_dir / f"{name}.md"
        if not path.is_file():
            raise AgentsDirectoryError(
                f"Prompt section file not found: {path}. Check {AGENTS_DIRECTORY_VARIABLE}."
            )
        loaded.append((name, version, path.read_text(encoding="utf-8").strip()))
    return loaded


SECTIONS = _load_sections()

MAX_SLOT_CHARS = 1500
MAX_PROMPT_CHARS = 12_000
_DENY = re.compile(
    r"(ignore (all |any )?(previous|prior|above)|disregard (the )?(rules|policy)|"
    r"you are now|system prompt|developer message|</?(system|assistant|tool)>|"
    r"create (an? )?(new )?agent|grant (yourself|me)|\bsudo\b)",
    re.IGNORECASE,
)


class PromptValidationError(ValueError):
    pass


def _clean(value: str, slot: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = "".join(ch for ch in value if ch == "\n" or unicodedata.category(ch)[0] != "C")
    value = value.replace("$", "")  # slot text can never introduce a placeholder
    if len(value) > MAX_SLOT_CHARS:
        raise PromptValidationError(f"slot '{slot}' exceeds {MAX_SLOT_CHARS} characters")
    if _DENY.search(value):
        raise PromptValidationError(f"slot '{slot}' contains a disallowed instruction pattern")
    return value.strip()


def _bullets(items: list[str], slot: str) -> str:
    return "\n".join(f"- {_clean(i, slot)}" for i in items) or "- none"


def compile_prompt(
    request: AgentRequest,
    grants: list[ToolPermission],
    *,
    namespace: str,
    tool_descriptions: dict[str, str],
    completion: list[str],
    escalation: list[str],
    budget: BudgetPolicy,
    standards: Sequence[str] = (),
    forbidden: Sequence[str] = (),
) -> SystemPromptSpecification:
    values = {
        "lead": request.requested_by.value,
        "role_title": _clean(request.role_title, "role_title"),
        "expertise": ", ".join(_clean(e, "expertise") for e in request.required_expertise),
        "standards": "\n".join(f"- {s}" for s in standards) or "- none specific to this task",
        "forbidden": "\n".join(f"- {f}" for f in forbidden) or "- nothing beyond the rules above",
        "objective": _clean(request.task_objective, "objective"),
        "scope": _bullets(request.scope, "scope"),
        "exclusions": _bullets(request.exclusions, "exclusions"),
        "inputs": _bullets(request.input_refs, "inputs"),
        "tools": "\n".join(
            f"- {g.tool_name} v{g.tool_version} (max {g.max_calls} calls): "
            f"{tool_descriptions[g.tool_name]}"
            for g in grants
        )
        or "- none",
        "namespace": namespace,
        "evidence_requirements": _bullets(request.evidence_requirements, "evidence"),
        "output_schema": "SpecialistOutput.v1",
        "max_model_calls": str(budget.max_model_calls),
        "max_tool_calls": str(budget.max_tool_calls),
        "timeout_seconds": str(budget.timeout_seconds),
        "escalation": _bullets(escalation, "escalation"),
        "completion": _bullets(completion, "completion"),
    }
    sections = [
        PromptSection(
            name=name,
            template_id=f"specialist/{name}",
            template_version=version,
            text=Template(body).substitute(values),
        )  # KeyError if a slot is missing
        for name, version, body in SECTIONS
    ]
    rendered = "\n\n".join(s.text for s in sections)
    spec = SystemPromptSpecification(
        compiler_version=COMPILER_VERSION,
        sections=sections,
        rendered=rendered,
        sha256=hashlib.sha256(rendered.encode()).hexdigest(),
    )
    validate_prompt(spec, grants)
    return spec


def validate_prompt(spec: SystemPromptSpecification, grants: list[ToolPermission]) -> None:
    expected = [name for name, _, _ in SECTIONS]
    if [s.name for s in spec.sections] != expected:
        raise PromptValidationError("sections missing or out of order")
    if not spec.rendered.startswith(spec.sections[0].text):
        raise PromptValidationError("organisational policy must come first")
    if "$" in spec.rendered:
        raise PromptValidationError("unresolved placeholder")
    if len(spec.rendered) > MAX_PROMPT_CHARS:
        raise PromptValidationError("prompt too long")
    granted = {g.tool_name for g in grants}
    tools_text = next(s.text for s in spec.sections if s.name == "tools")
    listed = set(re.findall(r"^- (\S+) v", tools_text, flags=re.MULTILINE))
    if listed != granted:
        raise PromptValidationError("prompt lists tools that differ from the grants")
