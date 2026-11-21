"""Checks that the pinned dependencies and the package import in a clean environment."""

import importlib

import pytest

PINNED_MODULES = ["orchestrator", "pydantic", "langgraph", "langchain", "langchain_azure_ai"]


@pytest.mark.parametrize("module", PINNED_MODULES)
def test_module_imports(module: str) -> None:
    assert importlib.import_module(module) is not None
