"""No code constructs a LangSmith client or turns tracing on (ADR-0013, ADR-0033 point 13).

Tracing goes through OpenTelemetry to Azure. Nothing under `src/` may import `langsmith`, build a
`LangChainTracer` or a LangSmith `Client`, or set a LangSmith or LangChain tracing variable. The
check reads the source, so it also catches code that is never run in a test."""

import ast
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "src"
FORBIDDEN_NAMES = {"LangChainTracer", "LangSmithClient", "tracing_v2_enabled", "RunTree"}
FORBIDDEN_PREFIXES = ("LANGSMITH_", "LANGCHAIN_TRACING", "LANGCHAIN_ENDPOINT", "LANGCHAIN_API_KEY")


def violations(source: str) -> list[str]:
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [f"import {a.name}" for a in node.names if a.name.split(".")[0] == "langsmith"]
        elif isinstance(node, ast.ImportFrom):
            module = (node.module or "").split(".")[0]
            if module == "langsmith":
                found.append(f"from {node.module} import ...")
            found += [f"imports {a.name}" for a in node.names if a.name in FORBIDDEN_NAMES]
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            found.append(f"uses {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_NAMES:
            found.append(f"uses {node.attr}")
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.startswith(FORBIDDEN_PREFIXES)
        ):
            found.append(f"names the variable {node.value}")
    return found


def test_nothing_under_src_touches_langsmith() -> None:
    problems = {
        str(path.relative_to(SOURCE)): violations(path.read_text(encoding="utf-8"))
        for path in SOURCE.rglob("*.py")
    }
    assert {k: v for k, v in problems.items() if v} == {}


@pytest.mark.parametrize(
    "source",
    [
        "import langsmith",
        "from langsmith import Client",
        "from langsmith.run_trees import RunTree",
        "from langchain_core.tracers import LangChainTracer",
        "t = langchain_core.tracers.LangChainTracer()",
        "import os\nos.environ['LANGSMITH_TRACING'] = 'true'",
        "os.environ.setdefault('LANGCHAIN_TRACING_V2', 'true')",
        "with tracing_v2_enabled(): pass",
    ],
)
def test_the_check_catches_each_way_of_turning_langsmith_on(source: str) -> None:
    assert violations(source)


def test_the_check_leaves_ordinary_code_alone() -> None:
    assert violations("import os\nx = os.environ.get('AZURE_OPENAI_ENDPOINT')") == []
