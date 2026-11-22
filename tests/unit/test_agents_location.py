"""Where the prompt files are found (ADR-0035 points 9 and 10): both loaders honour
ORCHESTRATOR_AGENTS_DIR, and a missing directory stops the process at once with a message that names
the variable and the path tried."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from orchestrator.prompts.agent_loader import load_agent
from orchestrator.prompts.location import (
    AGENTS_DIRECTORY_VARIABLE,
    SOURCE_TREE_DIRECTORY,
    AgentsDirectoryError,
    agents_directory,
    check_agents_directory,
)

MISSING = "does-not-exist"


def python(code: str, directory: Path | None) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != AGENTS_DIRECTORY_VARIABLE}
    if directory is not None:
        env[AGENTS_DIRECTORY_VARIABLE] = str(directory)
    return subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=120
    )


@pytest.fixture
def copy_of_agents(tmp_path: Path) -> Path:
    target = tmp_path / "agents"
    shutil.copytree(SOURCE_TREE_DIRECTORY, target)
    return target


def test_the_source_tree_is_the_default_when_the_variable_is_not_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(AGENTS_DIRECTORY_VARIABLE, raising=False)
    assert agents_directory() == SOURCE_TREE_DIRECTORY and check_agents_directory()


def test_the_variable_wins_over_the_source_tree(
    monkeypatch: pytest.MonkeyPatch, copy_of_agents: Path
) -> None:
    monkeypatch.setenv(AGENTS_DIRECTORY_VARIABLE, str(copy_of_agents))
    assert agents_directory() == copy_of_agents


def test_a_missing_directory_names_the_variable_and_the_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    wrong = tmp_path / MISSING
    monkeypatch.setenv(AGENTS_DIRECTORY_VARIABLE, str(wrong))
    with pytest.raises(AgentsDirectoryError) as caught:
        agents_directory()
    assert AGENTS_DIRECTORY_VARIABLE in str(caught.value) and str(wrong) in str(caught.value)


def test_an_incomplete_directory_is_refused_at_the_startup_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "empty").mkdir()
    monkeypatch.setenv(AGENTS_DIRECTORY_VARIABLE, str(tmp_path / "empty"))
    with pytest.raises(AgentsDirectoryError, match="organisational-policy"):
        check_agents_directory()


def test_the_new_loader_reads_the_prompts_from_the_configured_directory(
    monkeypatch: pytest.MonkeyPatch, copy_of_agents: Path
) -> None:
    marker = "MARKER-FROM-THE-CONFIGURED-DIRECTORY"
    policy = copy_of_agents / "_shared" / "organisational-policy.md"
    policy.write_text(
        policy.read_text(encoding="utf-8").replace(
            "You are a permanent agent", f"{marker}. You are a permanent agent"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(AGENTS_DIRECTORY_VARIABLE, str(copy_of_agents))
    assert marker in load_agent("recruiter").prompt


def test_the_compiler_reads_its_sections_from_the_configured_directory(
    copy_of_agents: Path,
) -> None:
    marker = "MARKER-IN-A-COMPILER-SECTION"
    section = copy_of_agents / "_shared" / "compiler_sections" / "limits.md"
    section.write_text(section.read_text(encoding="utf-8") + f"\n{marker}\n", encoding="utf-8")
    code = (
        "from orchestrator.prompts.compiler import SECTIONS\n"
        "print(any('MARKER-IN-A-COMPILER-SECTION' in text for _, _, text in SECTIONS))"
    )
    done = python(code, copy_of_agents)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "True"
    assert marker in section.read_text(encoding="utf-8")


def test_the_compiler_fails_at_import_with_a_clear_message_when_the_directory_is_missing(
    tmp_path: Path,
) -> None:
    wrong = tmp_path / MISSING
    done = python("import orchestrator.prompts.compiler", wrong)
    assert done.returncode != 0
    assert AGENTS_DIRECTORY_VARIABLE in done.stderr and str(wrong) in done.stderr
    assert "AgentsDirectoryError" in done.stderr


def test_the_compiler_names_a_missing_section_file(copy_of_agents: Path) -> None:
    (copy_of_agents / "_shared" / "compiler_sections" / "limits.md").unlink()
    done = python("import orchestrator.prompts.compiler", copy_of_agents)
    assert done.returncode != 0
    assert "limits.md" in done.stderr and AGENTS_DIRECTORY_VARIABLE in done.stderr


def test_the_new_loader_stays_importable_without_agents_and_fails_when_asked_to_load(
    tmp_path: Path,
) -> None:
    code = (
        "from orchestrator.prompts.agent_loader import load_agent, AgentsDirectoryError\n"
        "try:\n    load_agent('recruiter')\nexcept AgentsDirectoryError as e:\n    print(e)"
    )
    done = python(code, tmp_path / MISSING)
    assert done.returncode == 0, done.stderr
    assert AGENTS_DIRECTORY_VARIABLE in done.stdout and MISSING in done.stdout
