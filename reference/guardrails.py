"""Guardrail rules. Deterministic: the rule engine decides from audit events alone.
A Guardrail Manager's model may tighten a verdict (flag -> suspend), never loosen one."""
from __future__ import annotations

from collections import Counter
from typing import Callable, Literal

from contracts import Contract

# event kind -> (flag at this count, suspend at this count); None = never
DEFAULT_RULES: dict[str, tuple[int | None, int | None]] = {
    "tool.denied": (1, 3),               # asked for something it was not granted
    "tool.withheld": (None, 1),          # reached for data above its clearance
    "tool.injection_flag": (1, 3),       # tool output looked like instructions
    "result.invalid_citation": (1, 2),   # cited evidence the gateway never issued
    "agent.spawn_attempt": (None, 1),    # tried to create or contact another agent
    "prompt.hash_mismatch": (None, 1),   # its prompt is not the one that was approved
    "budget.stopped": (1, None),         # ran into its limit
    "scope.exceeded": (1, 2),            # output addresses excluded scope (set by the model check)
}
_RANK = {"none": 0, "flag": 1, "suspend": 2}


class Verdict(Contract):
    agent_id: str
    action: Literal["none", "flag", "suspend"]
    rule: str = ""
    count: int = 0


def evaluate(counts: Counter, agent_id: str,
             rules: dict[str, tuple[int | None, int | None]] = DEFAULT_RULES) -> Verdict:
    """Strongest verdict across all rules for one agent."""
    best = Verdict(agent_id=agent_id, action="none")
    for kind, (flag_at, suspend_at) in rules.items():
        n = counts.get(kind, 0)
        action = ("suspend" if suspend_at is not None and n >= suspend_at
                  else "flag" if flag_at is not None and n >= flag_at else "none")
        if _RANK[action] > _RANK[best.action]:
            best = Verdict(agent_id=agent_id, action=action, rule=kind, count=n)
    return best


def tighten(rule_verdict: Verdict, model_wants_suspend: bool) -> Verdict:
    """Combine the rule verdict with a Guardrail Manager's judgement. One-way."""
    if rule_verdict.action == "flag" and model_wants_suspend:
        return rule_verdict.model_copy(update={"action": "suspend"})
    return rule_verdict


class GuardrailMonitor:
    """Fed by the audit sink in real time, so a suspension does not wait for the
    next graph step. `suspend` is the Recruiter's suspend method."""

    def __init__(self, suspend: Callable[[str, str], None],
                 rules: dict[str, tuple[int | None, int | None]] = DEFAULT_RULES) -> None:
        self._suspend, self._rules = suspend, rules
        self._counts: dict[str, Counter] = {}
        self._suspended: set[str] = set()

    def observe(self, agent_id: str, kind: str) -> Verdict:
        counts = self._counts.setdefault(agent_id, Counter())
        counts[kind] += 1
        verdict = evaluate(counts, agent_id, self._rules)
        if verdict.action == "suspend" and agent_id not in self._suspended:
            self._suspended.add(agent_id)
            self._suspend(agent_id, f"{verdict.rule} x{verdict.count}")
        return verdict

    def verdict(self, agent_id: str) -> Verdict:
        return evaluate(self._counts.get(agent_id, Counter()), agent_id, self._rules)

    def cleared(self, agent_id: str) -> None:
        """A human resumed the agent: counts restart, so one more event does not re-suspend."""
        self._counts.pop(agent_id, None)
        self._suspended.discard(agent_id)
