#!/usr/bin/env python3
"""Consistency check for agent definitions. Standard library only.
Run from the repository root:  python3 scripts/check_agents.py"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent / "agents"
KEYS = ["name", "title", "function", "version", "status", "model_key", "tiers",
        "reports_to", "output_schemas", "tools", "skills", "metric"]
SECTIONS = ["Purpose", "System prompt", "Inputs", "May", "May not", "Escalates when",
            "Done by code, not by this agent"]
FUNCTIONS = {"Define", "Deliver", "Assure", "Control", "Learn"}
EXPECTED = {"product-manager", "cto-agent", "head-of-delivery", "lead", "tester", "reviewer",
            "guardrail-manager", "delivery-controller", "recruiter", "knowledge-steward",
            "solution-architect", "ai-specialist"}
PROFILED = {"lead", "tester", "guardrail-manager"}
MAX_PROMPT_CHARS = 6000
MAX_SKILL_CHARS = 2500
TOOLS = {"org_memory_read", "org_memory_search", "deliverables_read", "results_read",
         "evidence_read", "source_refetch", "sandbox_test_run", "audit_read", "ledger_read",
         "plan_read", "registry_read", "model_catalogue_read"}


def front_matter(text: str) -> tuple[list[str], dict[str, str], str]:
    match = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    if not match:
        return [], {}, text
    pairs = [line.split(":", 1) for line in match.group(1).splitlines() if ":" in line]
    return [k.strip() for k, _ in pairs], {k.strip(): v.strip() for k, v in pairs}, match.group(2)


def check(path: pathlib.Path) -> list[str]:
    errors = []
    order, meta, body = front_matter(path.read_text())
    if order != KEYS:
        errors.append(f"front matter keys must be exactly {KEYS}, in that order")
    if meta.get("name") != path.name.removesuffix(".agent.md"):
        errors.append("name must match the file name")
    if meta.get("function") not in FUNCTIONS:
        errors.append(f"function must be one of {sorted(FUNCTIONS)}")
    if not re.fullmatch(r"\d+\.\d+\.\d+", meta.get("version", "")):
        errors.append("version must be semantic, e.g. 1.0.0")
    if re.findall(r"^## (.+)$", body, re.M) != SECTIONS:
        errors.append(f"sections must be exactly {SECTIONS}, in that order")
    block = re.search(r"## System prompt\n\n```text\n(.*?)\n```", body, re.S)
    if not block:
        errors.append("System prompt must be one ```text block")
        return errors
    prompt = block.group(1)
    if not prompt.startswith("{{organisational-policy}}"):
        errors.append("the prompt must start with {{organisational-policy}}")
    if ("{{domain-profile}}" in prompt) != (meta.get("name") in PROFILED):
        errors.append("{{domain-profile}} belongs in lead, tester and guardrail-manager, and only there")
    if "\nROLE\n" not in prompt:
        errors.append("the prompt needs a ROLE section")
    named = set(re.findall(r"\(output: (\w+)\)", prompt))
    declared = {s.strip() for s in meta.get("output_schemas", "").split(",") if s.strip()}
    if named != declared:
        errors.append(f"output schemas differ: prompt names {sorted(named)}, front matter {sorted(declared)}")
    if len(prompt) > MAX_PROMPT_CHARS:
        errors.append(f"prompt is {len(prompt)} characters; limit {MAX_PROMPT_CHARS}")
    for tool in [t.strip() for t in meta.get("tools", "").split(",")]:
        if tool != "none" and tool not in TOOLS:
            errors.append(f"tool '{tool}' is not in docs/architecture/tool-catalogue.md")
    for skill in [s.strip() for s in meta.get("skills", "").split(",")]:
        if skill == "none":
            continue
        skill_file = ROOT / "skills" / f"{skill}.md"
        if not skill_file.exists():
            errors.append(f"skill '{skill}' has no file in agents/skills/")
            continue
        _, smeta, sbody = front_matter(skill_file.read_text())
        if meta.get("name") not in [u.strip() for u in smeta.get("used_by", "").split(",")]:
            errors.append(f"skill '{skill}' does not list this role in used_by")
        text = re.search(r"## Skill text\n\n```text\n(.*?)\n```", sbody, re.S)
        if not text:
            errors.append(f"skill '{skill}' needs a Skill text ```text block")
        elif len(text.group(1)) > MAX_SKILL_CHARS:
            errors.append(f"skill '{skill}' is over {MAX_SKILL_CHARS} characters")
    return errors


def main() -> int:
    files = sorted(ROOT.glob("*.agent.md"))
    found = {f.name.removesuffix(".agent.md") for f in files}
    failed = False
    if found != EXPECTED:
        print(f"roles differ from the twelve in ADR-0007 and ADR-0026: missing {sorted(EXPECTED - found)}, "
              f"unexpected {sorted(found - EXPECTED)}")
        failed = True
    policy = (ROOT / "_shared" / "organisational-policy.md").read_text()
    if "```text" not in policy:
        print("organisational-policy.md needs a ```text block")
        failed = True
    for profile in sorted((ROOT / "profiles").glob("*.md")):
        text = profile.read_text()
        for heading in ("## Scope", "## Lead focus", "## Tester focus"):
            if heading not in text:
                print(f"{profile.name}: missing '{heading}'")
                failed = True
    for path in files:
        for error in check(path):
            print(f"{path.name}: {error}")
            failed = True
    print("FAILED" if failed else f"OK: {len(files)} agent definitions, "
          f"{len(list((ROOT / 'profiles').glob('*.md')))} profiles")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
