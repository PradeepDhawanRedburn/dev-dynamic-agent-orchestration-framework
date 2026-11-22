"""The model catalogue and the chat models built from it (ADR-0033 points 9 to 11)."""

import os
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from pydantic import ValidationError

from orchestrator.contracts import Classification
from orchestrator.models.catalogue import (
    DEFAULT_CATALOGUE_PATH,
    ClearanceExceeded,
    ModelCatalogue,
    UnknownModel,
    load_catalogue,
    parse_catalogue,
    reviewer_is_independent,
)
from orchestrator.models.chat import FoundryNotConfigured, build_chat_model
from tests.conftest import run_async

ENTRY: dict[str, Any] = {
    "deployment": "d1",
    "api": "responses",
    "api_version": "v1",
    "reasoning_effort": "low",
    "highest_classification": "internal",
    "cost_band": "low",
    "status": "provisional",
}
BANDS: dict[str, Any] = {"low": {"input_per_1k": "1", "output_per_1k": "2"}}


def catalogue_with(**entries: dict[str, Any]) -> ModelCatalogue:
    return parse_catalogue({"version": "t", "bands": BANDS, "entries": entries})


@pytest.fixture
def catalogue() -> ModelCatalogue:
    return load_catalogue()


def test_the_shipped_catalogue_carries_every_field_adr_0033_names(
    catalogue: ModelCatalogue,
) -> None:
    assert set(catalogue.entries) >= {"reasoning-small", "reasoning-standard", "reasoning-alternate"}
    for entry in catalogue.entries.values():
        assert entry.deployment
        assert entry.api in ("chat_completions", "responses")
        assert entry.api_version in ("v1", "preview")
        assert entry.reasoning_effort is not None
        assert entry.highest_classification is Classification.INTERNAL
        assert entry.cost_band in catalogue.bands
        assert entry.status == "provisional"


def test_every_model_key_the_agent_definitions_use_is_in_the_catalogue(
    catalogue: ModelCatalogue,
) -> None:
    keys = set()
    for path in (DEFAULT_CATALOGUE_PATH.parent.parent / "agents").glob("*.agent.md"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("model_key:"):
                keys.add(line.split(":", 1)[1].strip())
    assert keys, "no model keys found in agents/"
    assert keys <= set(catalogue.entries)


def test_the_reviewer_runs_on_a_different_deployment_from_the_producers(
    catalogue: ModelCatalogue,
) -> None:
    assert reviewer_is_independent(catalogue, "reasoning-alternate", ["reasoning-standard"])
    assert not reviewer_is_independent(catalogue, "reasoning-standard", ["reasoning-standard"])


def test_an_unknown_model_is_refused(catalogue: ModelCatalogue) -> None:
    with pytest.raises(UnknownModel):
        catalogue.get("gpt-4-anything")


def test_a_model_is_refused_data_above_its_classification(catalogue: ModelCatalogue) -> None:
    catalogue.check_clearance("reasoning-standard", Classification.INTERNAL)
    with pytest.raises(ClearanceExceeded):
        catalogue.check_clearance("reasoning-standard", Classification.CONFIDENTIAL)


def test_cost_follows_the_band_rates() -> None:
    cat = catalogue_with(m=ENTRY)
    assert cat.cost("m", 1000, 500) == Decimal("2")


@pytest.mark.parametrize("version", ["2024-10-21", "2025-04-01-preview", "latest"])
def test_a_dated_api_version_is_refused_because_the_service_rejects_it(version: str) -> None:
    with pytest.raises(ValidationError, match="dated versions"):
        catalogue_with(m={**ENTRY, "api_version": version})


def test_fallbacks_must_exist_and_must_not_loop() -> None:
    with pytest.raises(ValidationError, match="not in the catalogue"):
        catalogue_with(m={**ENTRY, "fallback": "nope"})
    with pytest.raises(ValidationError, match="loop"):
        catalogue_with(a={**ENTRY, "fallback": "b"}, b={**ENTRY, "fallback": "a"})


def test_a_cost_band_without_a_rate_is_refused() -> None:
    with pytest.raises(ValidationError, match="no rate"):
        catalogue_with(m={**ENTRY, "cost_band": "high"})


def test_the_catalogue_path_can_be_set_without_a_code_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    other = tmp_path / "approved.yaml"
    other.write_text(
        "version: approved-1\nbands:\n  low: {input_per_1k: '1', output_per_1k: '1'}\n"
        "entries:\n  only-one:\n    deployment: x\n    api: chat_completions\n    api_version: v1\n"
        "    highest_classification: confidential\n    cost_band: low\n    status: approved\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ORCHESTRATOR_MODEL_CATALOGUE", str(other))
    loaded = load_catalogue()
    assert loaded.version == "approved-1" and list(loaded.entries) == ["only-one"]


# ------------------------------------------------ the call is made from the catalogue entry
@pytest.fixture
def fake_foundry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://resource.invalid/")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "not-a-real-key")


@pytest.mark.parametrize("key", ["reasoning-small", "reasoning-standard", "reasoning-alternate"])
def test_the_api_version_and_effort_of_a_call_come_from_the_entry(
    catalogue: ModelCatalogue, fake_foundry: None, key: str
) -> None:
    entry = catalogue.get(key)
    model: Any = build_chat_model(entry, max_output_tokens=321)
    assert model.model_name == entry.deployment
    assert model.use_responses_api is (entry.api == "responses")
    assert model.reasoning_effort == entry.reasoning_effort
    assert model.api_version == entry.api_version
    assert model.max_tokens == 321
    assert model.max_retries == 0, "retries belong to the retry middleware, once"
    assert model.openai_api_base == "https://resource.invalid/openai/v1"


def test_changing_the_entry_changes_the_call(fake_foundry: None) -> None:
    cat = catalogue_with(
        a={**ENTRY, "api": "chat_completions", "reasoning_effort": "high"},
        b={**ENTRY, "api": "responses", "reasoning_effort": "minimal"},
    )
    a: Any = build_chat_model(cat.get("a"), max_output_tokens=10)
    b: Any = build_chat_model(cat.get("b"), max_output_tokens=10)
    assert (a.use_responses_api, a.reasoning_effort) == (False, "high")
    assert (b.use_responses_api, b.reasoning_effort) == (True, "minimal")


def test_a_missing_endpoint_or_key_is_a_clear_error(
    catalogue: ModelCatalogue, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    with pytest.raises(FoundryNotConfigured):
        build_chat_model(catalogue.get("reasoning-small"), max_output_tokens=10)


def test_model_catalogue_read_lists_what_the_platform_enforces(catalogue: ModelCatalogue) -> None:
    from orchestrator.tools.impl.model_catalogue import ModelCatalogueRead

    tool = ModelCatalogueRead(catalogue)
    out = run_async(tool.run({}, {}))
    assert {m["model_key"] for m in out["models"]} == set(catalogue.entries)
    first = out["models"][0]
    assert set(first) == {
        "model_key",
        "deployment",
        "api",
        "api_version",
        "reasoning_effort",
        "purpose",
        "highest_classification",
        "cost_band",
        "status",
    }
    filtered = run_async(tool.run({"purpose": "independent review"}, {}))
    assert [m["model_key"] for m in filtered["models"]] == ["reasoning-alternate"]


def test_the_catalogue_tool_is_not_consequential_and_needs_no_evidence() -> None:
    from orchestrator.tools.impl.model_catalogue import MODEL_CATALOGUE_READ

    assert not MODEL_CATALOGUE_READ.consequential and not MODEL_CATALOGUE_READ.produces_evidence


# ------------------------------------------------ real Foundry
@pytest.mark.foundry
@pytest.mark.parametrize("key", ["reasoning-small", "reasoning-standard", "reasoning-alternate"])
def test_each_provisional_entry_answers_with_the_api_and_effort_it_names(key: str) -> None:
    import openai

    entry = load_catalogue().get(key)
    model = build_chat_model(entry, max_output_tokens=2000)
    try:
        reply = model.invoke("Reply with the single word: ok")
    except openai.NotFoundError:
        pytest.skip(f"could not test: no deployment named {entry.deployment!r} (404)")
    assert isinstance(reply, AIMessage)
    assert "ok" in reply.text.lower()
    assert reply.usage_metadata and reply.usage_metadata["output_tokens"] > 0
    assert os.environ.get("LANGSMITH_TRACING") is None
