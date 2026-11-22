"""Import rule for graph code (ADR-0034 point 2): modules under `orchestrator.graph` reach the
stores through the async facade only. A synchronous store, an in-memory twin, a store interface,
the connection pool or a database driver must not be imported there, because a blocking call on
the event loop stalls every run.

`find_store_imports` reads a file's syntax tree, so it also catches an import inside a function."""

import ast
from pathlib import Path

FORBIDDEN_MODULES = (
    "orchestrator.persistence.repositories",
    "orchestrator.persistence.db",
    "orchestrator.persistence.migrate",
    "psycopg",
    "psycopg_pool",
)
FORBIDDEN_NAMES = frozenset(
    {
        "BudgetLedger",
        "AgentRegistry",
        "EvidenceStore",
        "AuditLog",
        "DecisionRegister",
        "ToolCallCounters",
        "Pool",
        "open_pool",
        "StoreExecutor",
    }
)
FORBIDDEN_PREFIXES = ("Postgres", "InMemory")
FORBIDDEN_SUBMODULES = frozenset({"repositories", "db", "migrate"})


def _module_forbidden(module: str) -> bool:
    return any(module == bad or module.startswith(bad + ".") for bad in FORBIDDEN_MODULES)


def _name_forbidden(name: str) -> bool:
    return name in FORBIDDEN_NAMES or name.startswith(FORBIDDEN_PREFIXES)


def find_store_imports(path: Path) -> list[str]:
    """Describe every forbidden import in one Python file, with its line number."""
    found: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _module_forbidden(alias.name):
                    found.append(f"{path.name}:{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            relative = "." * node.level
            if node.level == 0 and _module_forbidden(module):
                found.append(f"{path.name}:{node.lineno}: from {module} import ...")
                continue
            if node.level and module.split(".")[-1] in FORBIDDEN_SUBMODULES:
                found.append(f"{path.name}:{node.lineno}: from {relative}{module} import ...")
                continue
            for alias in node.names:
                if _name_forbidden(alias.name):
                    found.append(f"{path.name}:{node.lineno}: imports {alias.name}")
                elif (
                    module in ("orchestrator.persistence", "persistence")
                    and alias.name in FORBIDDEN_SUBMODULES
                ):
                    found.append(f"{path.name}:{node.lineno}: imports module {alias.name}")
    return found


def find_store_imports_in_package(package_dir: Path) -> list[str]:
    violations: list[str] = []
    for path in sorted(package_dir.rglob("*.py")):
        violations.extend(find_store_imports(path))
    return violations
