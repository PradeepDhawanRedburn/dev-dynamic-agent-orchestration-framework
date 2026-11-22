"""The model catalogue (ADR-0033 points 9 to 11).

A specification and an agent definition name a model by catalogue key, never by deployment or
endpoint. For each key the catalogue records the deployment, which API to call (chat completions or
Responses), the API version value, the reasoning effort, the highest data classification the model
may receive, a cost band and a status. Code reads these values; nothing is hard-coded.

The catalogue is configuration (`policy/model_catalogue.yaml`). Today every entry is
`provisional`: the approved list is the AI lead's to supply (H-03, H-14) and replaces the file
without a code change."""

import os
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Self

import yaml
from pydantic import Field, model_validator

from orchestrator.contracts import Classification, Contract

CATALOGUE_VARIABLE = "ORCHESTRATOR_MODEL_CATALOGUE"
DEFAULT_CATALOGUE_PATH = Path(__file__).resolve().parents[3] / "policy" / "model_catalogue.yaml"

Api = Literal["chat_completions", "responses"]
ReasoningEffort = Literal["none", "minimal", "low", "medium", "high"]
CostBand = Literal["low", "medium", "high"]
ModelStatus = Literal["provisional", "approved"]


class UnknownModel(KeyError):
    """The key is not in the catalogue, so the model is not approved for use."""


class ClearanceExceeded(ValueError):
    """The data is classified above what the model may receive."""


class CostRate(Contract):
    """Money per thousand tokens. Reasoning tokens are part of the output count."""

    input_per_1k: Decimal = Field(ge=0)
    output_per_1k: Decimal = Field(ge=0)


class ModelEntry(Contract):
    model_key: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    deployment: str = Field(min_length=1)
    api: Api
    api_version: str = Field(min_length=1, description="`v1` or `preview`; dated versions fail")
    reasoning_effort: ReasoningEffort | None = None
    highest_classification: Classification
    cost_band: CostBand
    status: ModelStatus
    purpose: str = ""
    fallback: str | None = Field(
        default=None, description="Another key to switch to if this deployment fails"
    )

    @model_validator(mode="after")
    def _dated_versions_are_refused(self) -> Self:
        if self.api_version not in ("v1", "preview"):
            raise ValueError(
                f"api_version {self.api_version!r}: dated versions are rejected on the /openai/v1 "
                "path (spike S-12); use v1 or preview"
            )
        return self


class ModelCatalogue(Contract):
    version: str
    currency: str = "USD"
    bands: dict[CostBand, CostRate]
    entries: dict[str, ModelEntry]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        for key, entry in self.entries.items():
            if entry.model_key != key:
                raise ValueError(f"entry {key!r} says its key is {entry.model_key!r}")
            if entry.cost_band not in self.bands:
                raise ValueError(f"{key}: no rate for cost band {entry.cost_band!r}")
            seen = {key}
            link = entry.fallback
            while link is not None:
                if link not in self.entries:
                    raise ValueError(f"{key}: fallback {link!r} is not in the catalogue")
                if link in seen:
                    raise ValueError(f"{key}: fallbacks form a loop")
                seen.add(link)
                link = self.entries[link].fallback
        return self

    def get(self, model_key: str) -> ModelEntry:
        try:
            return self.entries[model_key]
        except KeyError:
            raise UnknownModel(f"{model_key!r} is not an approved model") from None

    def list(self, purpose: str | None = None) -> list[ModelEntry]:
        found = list(self.entries.values())
        if purpose is not None:
            found = [e for e in found if purpose.lower() in e.purpose.lower()]
        return found

    def check_clearance(self, model_key: str, classification: Classification) -> ModelEntry:
        entry = self.get(model_key)
        if classification.rank > entry.highest_classification.rank:
            raise ClearanceExceeded(
                f"{model_key} may receive up to {entry.highest_classification.value}, "
                f"not {classification.value}"
            )
        return entry

    def cost(self, model_key: str, input_tokens: int, output_tokens: int) -> Decimal:
        rate = self.bands[self.get(model_key).cost_band]
        return (
            Decimal(input_tokens) * rate.input_per_1k + Decimal(output_tokens) * rate.output_per_1k
        ) / Decimal(1000)

    def distinct_deployments(self, key_a: str, key_b: str) -> bool:
        return self.get(key_a).deployment != self.get(key_b).deployment


def reviewer_is_independent(
    catalogue: ModelCatalogue, reviewer_key: str, producer_keys: list[str]
) -> bool:
    """ADR-0009: the Reviewer runs on a different deployment from the one that produced the work."""
    return all(catalogue.distinct_deployments(reviewer_key, key) for key in producer_keys)


def parse_catalogue(data: dict[str, Any]) -> ModelCatalogue:
    entries = {key: {"model_key": key, **value} for key, value in data.get("entries", {}).items()}
    return ModelCatalogue(**{**data, "entries": entries})


def load_catalogue(path: Path | None = None) -> ModelCatalogue:
    """Read the catalogue from `path`, from ORCHESTRATOR_MODEL_CATALOGUE, or from the default."""
    chosen = path or Path(os.environ.get(CATALOGUE_VARIABLE) or DEFAULT_CATALOGUE_PATH)
    data = yaml.safe_load(chosen.read_text(encoding="utf-8"))
    return parse_catalogue(data)
