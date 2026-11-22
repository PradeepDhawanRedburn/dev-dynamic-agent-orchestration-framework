"""Where the prompt files are (ADR-0035 points 9 and 10).

`agents/` sits outside the Python package, so it is found from the environment first and from the
source tree second. The container image copies `agents/` and sets `ORCHESTRATOR_AGENTS_DIR`;
packaging the files as package data is deferred to WP-12 and done only if a wheel install is needed.

Both prompt loaders (`agent_loader` and the compiler) use `agents_directory()`. If the directory
does not exist the process fails at once, with a message that names the variable and the path
tried, instead of failing later at the first prompt load."""

import os
from pathlib import Path

AGENTS_DIRECTORY_VARIABLE = "ORCHESTRATOR_AGENTS_DIR"
SOURCE_TREE_DIRECTORY = Path(__file__).resolve().parents[3] / "agents"
REQUIRED_FILES = ("_shared/organisational-policy.md", "_shared/compiler_sections")


class AgentsDirectoryError(RuntimeError):
    """The directory of prompt files is missing or incomplete."""


def agents_directory() -> Path:
    """The directory of prompt files. Raises `AgentsDirectoryError` if it does not exist."""
    configured = os.environ.get(AGENTS_DIRECTORY_VARIABLE)
    path = Path(configured) if configured else SOURCE_TREE_DIRECTORY
    if not path.is_dir():
        origin = (
            f"{AGENTS_DIRECTORY_VARIABLE} is set to it"
            if configured
            else f"{AGENTS_DIRECTORY_VARIABLE} is not set, so the source-tree default was used"
        )
        raise AgentsDirectoryError(
            f"The directory of prompt files does not exist: {path} ({origin}). "
            f"Set {AGENTS_DIRECTORY_VARIABLE} to the directory that holds the `agents/` files."
        )
    return path


def check_agents_directory() -> Path:
    """Startup check: the directory exists and holds what every prompt build needs."""
    path = agents_directory()
    missing = [name for name in REQUIRED_FILES if not (path / name).exists()]
    if missing:
        raise AgentsDirectoryError(
            f"The directory of prompt files {path} is missing {missing}. "
            f"Check {AGENTS_DIRECTORY_VARIABLE}."
        )
    return path
