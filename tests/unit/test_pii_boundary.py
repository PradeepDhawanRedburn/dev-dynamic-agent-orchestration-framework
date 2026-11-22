"""Personal data at the result boundary (ADR-0035): email, Luhn-checked card and IP address are
redacted from a specialist's result; identifiers are never altered; the audit event carries counts
and field names, never values."""

import json
from typing import Any

import pytest

from orchestrator.contracts import SpecialistOutput
from orchestrator.governance.pii import DETECTORS, redact_output, redact_text
from tests.conftest import run_async
from tests.scripted import specialist_output_args, tool_call_message
from tests.unit.test_worker import run
from tests.worker_env import make_env, make_spec

VALID_CARD = "4111 1111 1111 1111"  # passes the Luhn test
INVALID_CARD = "4111 1111 1111 1112"  # sixteen digits, fails it


def output(**over: Any) -> SpecialistOutput:
    args = specialist_output_args(1, ["ev_1"])
    args.update(over)
    return SpecialistOutput.model_validate(args)


# ------------------------------------------------------------------ detection and redaction
def test_an_email_address_is_redacted() -> None:
    text, counts = redact_text("Write to jane.doe@example.com today.")
    assert text == "Write to [REDACTED_EMAIL] today." and counts == {"email": 1}


def test_a_card_number_is_redacted_only_if_it_passes_the_luhn_test() -> None:
    text, counts = redact_text(f"paid with {VALID_CARD}")
    assert text == "paid with [REDACTED_CREDIT_CARD]" and counts == {"credit_card": 1}
    text, counts = redact_text(f"order number {INVALID_CARD}")
    assert text == f"order number {INVALID_CARD}" and counts == {}


def test_an_ip_address_is_redacted_and_an_invalid_one_is_not() -> None:
    text, counts = redact_text("host 10.20.30.40, not 999.1.1.1")
    assert text == "host [REDACTED_IP], not 999.1.1.1" and counts == {"ip": 1}


def test_several_kinds_and_repeats_are_counted_per_kind() -> None:
    text, counts = redact_text(f"a@b.co and c@d.org, {VALID_CARD}, 192.168.0.1")
    assert counts == {"email": 2, "credit_card": 1, "ip": 1}
    assert "@" not in text and "192.168" not in text and "4111" not in text


def test_text_without_personal_data_is_returned_unchanged() -> None:
    text = "Version 1.2.3 of the API, build 20260101, ticket INC-4411."
    assert redact_text(text) == (text, {})


# ------------------------------------------------------------------ the whole output
def test_every_free_text_field_is_scanned_including_nested_ones() -> None:
    args = specialist_output_args(2, ["ev_1", "ev_2"])
    args["executive_summary"] = "Contact a@b.co"
    args["findings"] = ["clean", f"card {VALID_CARD}"]
    args["assumptions"] = ["host 10.0.0.1"]
    args["limitations"] = ["x@y.com"]
    args["risks"] = ["r@s.io"]
    args["recommended_next_action"] = "Email n@m.net"
    args["claims"][1]["statement"] = "Claim from p@q.com"
    cleaned, report = redact_output(SpecialistOutput.model_validate(args))
    assert report.counts == {"email": 5, "credit_card": 1, "ip": 1}
    assert report.fields == [
        "executive_summary",
        "findings[1]",
        "claims[1].statement",
        "assumptions[0]",
        "limitations[0]",
        "risks[0]",
        "recommended_next_action",
    ]
    dumped = json.dumps(cleaned.model_dump(mode="json"))
    for leaked in ("a@b.co", "4111", "10.0.0.1", "x@y.com", "r@s.io", "n@m.net", "p@q.com"):
        assert leaked not in dumped
    assert cleaned.claims[0].statement == "claim 0", "an untouched field is untouched"


def test_identifier_fields_are_never_altered() -> None:
    args = specialist_output_args(1, ["ev_a@b.co"])
    args["claims"][0]["claim_id"] = "cl_x@y.com"
    args["claims"][0]["contradicting_evidence_ids"] = ["ev_192.168.0.1"]
    args["claims"][0]["statement"] = "see a@b.co"
    cleaned, report = redact_output(SpecialistOutput.model_validate(args))
    claim = cleaned.claims[0]
    assert claim.claim_id == "cl_x@y.com"
    assert claim.evidence_ids == ["ev_a@b.co"]
    assert claim.contradicting_evidence_ids == ["ev_192.168.0.1"]
    assert claim.statement == "see [REDACTED_EMAIL]"
    assert report.counts == {"email": 1} and report.fields == ["claims[0].statement"]


def test_enumerated_values_survive_and_the_output_still_validates() -> None:
    cleaned, _ = redact_output(output(executive_summary="mail a@b.co"))
    assert cleaned.completion_status == "complete" and cleaned.overall_confidence.value == "medium"
    assert SpecialistOutput.model_validate(cleaned.model_dump()) == cleaned


def test_an_output_with_nothing_to_redact_is_returned_as_it_was() -> None:
    original = output()
    cleaned, report = redact_output(original)
    assert cleaned is original and not report.redacted and report.fields == []


def test_the_detectors_are_the_librarys_and_three_kinds_only() -> None:
    assert set(DETECTORS) == {"email", "credit_card", "ip"}


def test_the_library_detectors_behave_as_this_step_assumes() -> None:
    """Pinned for langchain 1.5.2: IPv4 only, and 16-digit cards only, despite the docstrings.
    If this fails after an upgrade, read the control-matrix wording again."""
    assert DETECTORS["ip"]("2001:db8::1 and ::1") == []
    assert DETECTORS["credit_card"]("378282246310005") == []  # a 15-digit Amex test number


def test_names_addresses_and_national_identifiers_are_not_detected() -> None:
    """Stated in ADR-0035 point 7 and the control matrix; this test keeps the limit visible."""
    text = "Alice Smith, 12 High Street, London; NI number QQ 12 34 56 C"
    assert redact_text(text) == (text, {})


def test_a_redaction_that_no_longer_fits_the_schema_is_an_error() -> None:
    from pydantic import ValidationError

    near_limit = "x" * 1490 + " a@b.co"  # 1497 characters; the placeholder is longer than the value
    assert len(near_limit) <= 1500
    with pytest.raises(ValidationError):
        redact_output(output(executive_summary=near_limit))


# ------------------------------------------------------------------ through the worker
def personal_answer() -> Any:
    args = specialist_output_args(1)
    args["claims"] = []
    args["executive_summary"] = f"Contact jane.doe@example.com; card {VALID_CARD}."
    args["findings"] = ["Gateway at 10.1.2.3"]
    return tool_call_message("SpecialistOutput", args)


def test_the_agent_result_holds_the_redacted_text_and_the_event_has_counts_and_fields_only() -> (
    None
):
    env = make_env()
    spec = make_spec(tools=[])
    outcome, audit, _ = run(env, spec, [personal_answer()])
    assert outcome.status == "awaiting_review" and outcome.result is not None
    summary = outcome.result.output.executive_summary
    assert summary == "Contact [REDACTED_EMAIL]; card [REDACTED_CREDIT_CARD]."
    assert outcome.result.output.findings == ["Gateway at [REDACTED_IP]"]
    assert audit == ["guardrail.pii_redacted"]
    events = run_async(env.stores.audit.events(kind="guardrail.pii_redacted"))
    details = dict(events[0].details)
    assert details == {
        "counts": {"email": 1, "credit_card": 1, "ip": 1},
        "fields": ["executive_summary", "findings[0]"],
    }
    everything = json.dumps(details) + events[0].model_dump_json()
    for value in ("jane.doe", "4111", "10.1.2.3"):
        assert value not in everything, "an audit event never holds the value"


def test_a_clean_result_writes_no_pii_event() -> None:
    env = make_env()
    spec = make_spec(tools=[])
    args = specialist_output_args(1)
    args["claims"] = []
    _, audit, _ = run(env, spec, [tool_call_message("SpecialistOutput", args)])
    assert "guardrail.pii_redacted" not in audit


def test_a_result_whose_redaction_breaks_the_schema_fails_closed() -> None:
    env = make_env()
    spec = make_spec(tools=[])
    args = specialist_output_args(1)
    args["claims"] = []
    args["executive_summary"] = "x" * 1490 + " a@b.co"
    outcome, audit, registry = run(env, spec, [tool_call_message("SpecialistOutput", args)])
    assert outcome.status == "failed" and outcome.error == "pii_redaction_failed"
    assert outcome.result is None and audit == ["guardrail.pii_redaction_failed"]
    assert registry.value == "failed"
