"""Personal data at the result boundary (ADR-0035 points 1 to 5).

A specialist's deliverable is a `SpecialistOutput` returned through a structured-output tool call,
so `PIIMiddleware` (which scans message text) never sees it. This step does, in code and not through
a model: it scans every free-text string of the validated output and redacts what it finds, before
the output becomes an `AgentResult`.

- Detects the same three kinds the middleware does: email address, payment card number (Luhn
  checked) and IP address. The detectors are the library's own `detect_email`,
  `detect_credit_card` and `detect_ip`, which langchain 1.5.2 exports in `pii.__all__` and its
  reference documents. They find IPv4 only and 16-digit cards only, whatever their docstrings say;
  `tests/unit/test_pii_boundary.py` pins that so a change in the library shows up.
- Redacts rather than blocks (ADR-0035 point 3). The placeholder is the middleware's:
  `[REDACTED_EMAIL]`, `[REDACTED_CREDIT_CARD]`, `[REDACTED_IP]`.
- Never alters identifier fields: a claim's id and the evidence ids it cites.
- Reports counts per kind and the names of the fields it changed, never a value.

Not covered, and stated in the control matrix: names, postal addresses and national identifiers
(ADR-0035 point 7), and the bodies of captured evidence, which are tool results and are not altered
(ADR-0033 point 20)."""

from collections.abc import Callable
from enum import Enum
from typing import Any

from langchain.agents.middleware import PIIMatch
from langchain.agents.middleware.pii import detect_credit_card, detect_email, detect_ip

from orchestrator.contracts import Contract, SpecialistOutput

DETECTORS: dict[str, Callable[[str], list[PIIMatch]]] = {
    "email": detect_email,
    "credit_card": detect_credit_card,
    "ip": detect_ip,
}
IDENTIFIER_FIELDS = frozenset({"claim_id", "evidence_ids", "contradicting_evidence_ids"})


def placeholder(kind: str) -> str:
    return f"[REDACTED_{kind.upper()}]"


class RedactionReport(Contract):
    counts: dict[str, int] = {}
    fields: list[str] = []

    @property
    def redacted(self) -> bool:
        return bool(self.counts)


def redact_text(text: str) -> tuple[str, dict[str, int]]:
    """Replace every detected value in `text`; return the new text and the count per kind."""
    found = sorted(
        (match for detect in DETECTORS.values() for match in detect(text)),
        key=lambda m: (m["start"], -m["end"]),
    )
    chosen: list[PIIMatch] = []
    for match in found:
        if not chosen or match["start"] >= chosen[-1]["end"]:  # an overlap is one value, not two
            chosen.append(match)
    counts: dict[str, int] = {}
    for match in reversed(chosen):
        text = text[: match["start"]] + placeholder(match["type"]) + text[match["end"] :]
        counts[match["type"]] = counts.get(match["type"], 0) + 1
    return text, counts


def _walk(value: Any, path: str, counts: dict[str, int], fields: list[str]) -> Any:
    if isinstance(value, Enum):
        return value
    if isinstance(value, str):
        clean, found = redact_text(value)
        if found:
            fields.append(path)
            for kind, n in found.items():
                counts[kind] = counts.get(kind, 0) + n
        return clean
    if isinstance(value, dict):
        return {
            key: value[key]
            if key in IDENTIFIER_FIELDS
            else _walk(value[key], f"{path}.{key}" if path else str(key), counts, fields)
            for key in value
        }
    if isinstance(value, list):
        return [_walk(item, f"{path}[{i}]", counts, fields) for i, item in enumerate(value)]
    return value


def redact_output(output: SpecialistOutput) -> tuple[SpecialistOutput, RedactionReport]:
    """The output with personal data redacted, and what was done. If nothing was found the output
    is returned unchanged. Raises `pydantic.ValidationError` if the redacted output no longer
    satisfies the schema (a field at its length limit); the worker then fails closed."""
    counts: dict[str, int] = {}
    fields: list[str] = []
    cleaned = _walk(output.model_dump(), "", counts, fields)
    report = RedactionReport(counts=counts, fields=fields)
    if not report.redacted:
        return output, report
    return SpecialistOutput.model_validate(cleaned), report
