"""`model_catalogue_read`: list the models approved for use, with their limits (tool-catalogue
section A, ADR-0033). Read-only. It reads the configuration the platform itself uses, so what an
agent is told is what the platform enforces."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from orchestrator.contracts import Classification, LeadRole
from orchestrator.models.catalogue import ModelCatalogue
from orchestrator.tools.registry import ToolDefinition


class ModelCatalogueArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: str | None = Field(default=None, max_length=100, description="Optional filter")


class ModelCatalogueRead:
    args_model = ModelCatalogueArgs

    def __init__(self, catalogue: ModelCatalogue) -> None:
        self._catalogue = catalogue

    async def run(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        entries = self._catalogue.list(args.get("purpose"))
        return {
            "version": self._catalogue.version,
            "models": [
                {
                    "model_key": e.model_key,
                    "deployment": e.deployment,
                    "api": e.api,
                    "api_version": e.api_version,
                    "reasoning_effort": e.reasoning_effort,
                    "purpose": e.purpose,
                    "highest_classification": e.highest_classification.value,
                    "cost_band": e.cost_band,
                    "status": e.status,
                }
                for e in entries
            ],
        }


MODEL_CATALOGUE_READ = ToolDefinition(
    name="model_catalogue_read",
    version="1.0.0",
    description="List the approved models with their deployment, API, effort and limits.",
    input_schema=ModelCatalogueArgs.model_json_schema(),
    output_schema={"type": "object"},
    required_permission="Tools.ModelCatalogue.Read",
    # It touches no project data, so it is usable at every classification.
    max_classification=Classification.RESTRICTED,
    network_scope="none",
    timeout_seconds=10,
    max_retries=0,
    permitted_lead_roles=set(LeadRole),
    capability_tags={"model_catalogue"},
    produces_evidence=False,
)
