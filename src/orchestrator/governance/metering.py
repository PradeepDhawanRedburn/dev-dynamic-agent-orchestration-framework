"""Per-agent usage metering (ADR-0005, ADR-0033 points 18 and 21).

The meter counts what a run has spent: tokens and money for each model call, money for each tool
call, and structured-output validation errors. Code counts them. The tool that reports a
validation error is not trusted to be the counter, and nothing here asks a model.

A meter lives for the life of an agent, so the cost of a revision adds to the cost of the first
run. Money is worked out from the catalogue's cost band for the model the agent runs on."""

import threading
from decimal import Decimal
from typing import Literal

from orchestrator.contracts import BudgetPolicy, Usage
from orchestrator.models.catalogue import ModelCatalogue

StopReason = Literal["cost", "tokens", "validation_errors"]


class UsageMeter:
    def __init__(self, catalogue: ModelCatalogue, model_key: str, budget: BudgetPolicy) -> None:
        self._catalogue, self._model_key, self._budget = catalogue, model_key, budget
        self._usage = Usage()
        self._settled = Usage()
        self._validation_errors = 0
        self._lock = threading.Lock()

    def record_model_call(self, input_tokens: int, output_tokens: int) -> Decimal:
        cost = self._catalogue.cost(self._model_key, input_tokens, output_tokens)
        with self._lock:
            self._usage = self._usage.model_copy(
                update={
                    "input_tokens": self._usage.input_tokens + input_tokens,
                    "output_tokens": self._usage.output_tokens + output_tokens,
                    "model_calls": self._usage.model_calls + 1,
                    "cost": self._usage.cost + cost,
                }
            )
        return cost

    def record_tool_call(self, cost: Decimal) -> None:
        with self._lock:
            self._usage = self._usage.model_copy(
                update={"tool_calls": self._usage.tool_calls + 1, "cost": self._usage.cost + cost}
            )

    def record_validation_error(self) -> int:
        with self._lock:
            self._validation_errors += 1
            return self._validation_errors

    @property
    def validation_errors(self) -> int:
        return self._validation_errors

    def usage(self) -> Usage:
        with self._lock:
            return self._usage.model_copy()

    def take_unsettled(self) -> Usage:
        """What was spent since the last call, so a revision settles only its own spend."""
        with self._lock:
            now, before = self._usage, self._settled
            self._settled = now.model_copy()
            return Usage(
                input_tokens=now.input_tokens - before.input_tokens,
                output_tokens=now.output_tokens - before.output_tokens,
                model_calls=now.model_calls - before.model_calls,
                tool_calls=now.tool_calls - before.tool_calls,
                cost=now.cost - before.cost,
            )

    def exhausted(self) -> StopReason | None:
        """The first limit that has been reached, or None. Checked before every model call."""
        with self._lock:
            used = self._usage
            if used.cost >= self._budget.max_cost:
                return "cost"
            if used.input_tokens + used.output_tokens >= self._budget.max_tokens:
                return "tokens"
            if self._validation_errors > self._budget.max_retries:
                return "validation_errors"
            return None


class MeterBook:
    """One meter per agent."""

    def __init__(self, catalogue: ModelCatalogue) -> None:
        self._catalogue = catalogue
        self._meters: dict[str, UsageMeter] = {}
        self._lock = threading.Lock()

    def for_agent(self, agent_id: str, model_key: str, budget: BudgetPolicy) -> UsageMeter:
        with self._lock:
            meter = self._meters.get(agent_id)
            if meter is None:
                meter = self._meters[agent_id] = UsageMeter(self._catalogue, model_key, budget)
            return meter

    def get(self, agent_id: str) -> UsageMeter | None:
        return self._meters.get(agent_id)
