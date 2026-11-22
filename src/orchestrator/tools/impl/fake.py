"""Fake read-only tools, for tests and local runs before the real catalogue tools exist (WP-04
onwards). They change nothing outside the process and are never registered by default."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from orchestrator.contracts import Classification, LeadRole
from orchestrator.tools.registry import ToolDefinition


class SearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=200)


class FakeSearch:
    """Returns canned items. `fail_times` makes the first calls raise, to exercise self-healing."""

    args_model = SearchArgs

    def __init__(self, items: list[dict[str, Any]] | None = None, fail_times: int = 0) -> None:
        self.items = items if items is not None else [DEFAULT_ITEM]
        self.fail_times = fail_times
        self.calls = 0

    async def run(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ConnectionError("simulated network loss")
        return {"items": self.items}


DEFAULT_ITEM: dict[str, Any] = {
    "text": "Vendor documentation states that the API supports both REST and events.",
    "reference": "https://docs.example.com/integration",
    "title": "Integration overview",
    "source_type": "primary_document",
    "classification": "internal",
}


def fake_search_definition(
    name: str = "fake_search",
    *,
    max_classification: Classification = Classification.INTERNAL,
    timeout_seconds: int = 5,
    consequential: bool = False,
    tags: set[str] | None = None,
) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        version="1.0.0",
        description="Look up canned reference material (fake, read-only).",
        input_schema=SearchArgs.model_json_schema(),
        output_schema={"type": "object"},
        required_permission="Tools.Read",
        max_classification=max_classification,
        network_scope="none",
        timeout_seconds=timeout_seconds,
        max_retries=0,
        permitted_lead_roles=set(LeadRole),
        capability_tags=tags if tags is not None else {"fake_research"},
        consequential=consequential,
        produces_evidence=True,
    )
