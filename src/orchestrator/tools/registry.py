"""Governed tool registry. Definitions are data; implementations are reviewed code
registered at deploy time. Nothing here is created at runtime by an LLM."""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import Field

from orchestrator.contracts import AgentRequest, Classification, Contract, LeadRole, ToolPermission


class ToolDefinition(Contract):
    name: str
    version: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    required_permission: str  # Entra app role or scope
    max_classification: Classification  # highest data class the tool may touch
    network_scope: Literal["none", "internal", "internet_egress_proxy"]
    cost_per_call: float = 0.0
    timeout_seconds: int = Field(gt=0, le=600)
    max_retries: int = Field(ge=0, le=3)
    audit: Literal["metadata", "full_io"] = "full_io"
    permitted_lead_roles: set[LeadRole]
    capability_tags: set[str]
    consequential: bool = False  # True = changes state outside the platform
    produces_evidence: bool = False


class ToolImpl(Protocol):
    """A reviewed implementation. `args_model` is the Pydantic model for its input."""

    args_model: type

    async def run(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]: ...


class PermissionDenied(Exception):
    pass


class ToolRegistry:
    def __init__(self) -> None:
        self._defs: dict[tuple[str, str], ToolDefinition] = {}
        self._impls: dict[tuple[str, str], ToolImpl] = {}

    def register(self, definition: ToolDefinition, impl: ToolImpl) -> None:
        key = (definition.name, definition.version)
        if key in self._defs:
            raise ValueError(f"{key} already registered; publish a new version instead")
        self._defs[key] = definition
        self._impls[key] = impl

    def definition(self, name: str, version: str) -> ToolDefinition:
        return self._defs[(name, version)]

    def latest(self, name: str) -> ToolDefinition:
        versions = [d for (n, _), d in self._defs.items() if n == name]
        if not versions:
            raise KeyError(name)
        return max(versions, key=lambda d: tuple(int(p) for p in d.version.split(".")))

    def resolve_grants(self, request: AgentRequest) -> list[ToolPermission]:
        """Least privilege: one tool per requested capability, each one checked
        against role, classification and the consequential-tool ban."""
        grants: list[ToolPermission] = []
        for capability in request.capabilities_needed:
            candidates = [d for d in self._defs.values() if capability in d.capability_tags]
            if not candidates:
                raise PermissionDenied(f"no registered tool provides '{capability}'")
            tool = self.latest(sorted(candidates, key=lambda d: d.name)[0].name)
            self.check(tool, request.requested_by, request.data_classification)
            if tool.name not in {g.tool_name for g in grants}:
                grants.append(
                    ToolPermission(
                        tool_name=tool.name,
                        tool_version=tool.version,
                        max_calls=min(request.budget.max_tool_calls or 1, 50),
                        justification=f"capability '{capability}' for task {request.task_id}",
                    )
                )
        return grants

    @staticmethod
    def check(tool: ToolDefinition, lead: LeadRole, data_class: Classification) -> None:
        if tool.consequential:
            raise PermissionDenied(
                f"{tool.name} is consequential and is never granted to a dynamic agent"
            )
        if lead not in tool.permitted_lead_roles:
            raise PermissionDenied(f"{lead} may not grant {tool.name}")
        if data_class.rank > tool.max_classification.rank:
            raise PermissionDenied(f"{tool.name} is not cleared for {data_class} data")

    def implementation(self, grant: ToolPermission) -> tuple[ToolDefinition, ToolImpl]:
        key = (grant.tool_name, grant.tool_version)
        return self._defs[key], self._impls[key]
