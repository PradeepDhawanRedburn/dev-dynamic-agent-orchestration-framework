"""The decision register: the same behaviour from both, and the rules the model enforces."""

from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from pydantic import ValidationError

from orchestrator.governance.approvals import (
    TIMEOUT_RULE,
    DecisionCard,
    DecisionConflict,
    DecisionRecord,
    card_hash,
)
from orchestrator.persistence.repositories import StoredDataCorrupt
from tests.integration.conftest import Stores

PROJECT = "prj_ab12"
CARD = DecisionCard(
    question="Approve the requirement baseline?",
    options=["approve", "request changes"],
    recommendation="approve",
    recommended_by="product_manager",
    evidence_ids=["ev_1"],
    default="request changes",
    deadline=datetime(2026, 12, 1, 9, 0, tzinfo=UTC),
)


def human(**over: object) -> DecisionRecord:
    base: dict[str, object] = dict(
        project_id=PROJECT,
        type="approve_requirement",
        decided_by_kind="human",
        decided_by="00000000-aaaa-bbbb-cccc-000000000001",
        decided_by_role="sponsor",
        card=CARD,
        outcome="approved",
        comment="Looks right.",
        checkpoint_id="1ef4f797-8335-6428-8001-8a1503f9b875",
        baseline_version=1,
    )
    base.update(over)
    return DecisionRecord(**base)  # type: ignore[arg-type]


def timeout(**over: object) -> DecisionRecord:
    base: dict[str, object] = dict(
        project_id=PROJECT,
        type="approve_requirement",
        decided_by_kind="rule",
        decided_by=TIMEOUT_RULE,
        card=CARD,
        outcome="timeout",
        default_taken="request changes",
        comment="No answer by the deadline.",
    )
    base.update(over)
    return DecisionRecord(**base)  # type: ignore[arg-type]


def test_a_decision_round_trips_with_everything_it_was_based_on(stores: Stores) -> None:
    decision = human()
    stores.decisions.record(decision)
    stored = stores.decisions.get(decision.decision_id)
    assert stored == decision
    assert stored.card == CARD and stored.card_hash == card_hash(CARD)
    assert (stored.checkpoint_id, stored.baseline_version) == (decision.checkpoint_id, 1)
    assert stored.decided_by_role == "sponsor"


def test_a_timeout_is_stored_as_a_timeout_with_the_default_taken(stores: Stores) -> None:
    decision = timeout()
    stores.decisions.record(decision)
    stored = stores.decisions.get(decision.decision_id)
    assert stored.outcome == "timeout"
    assert stored.decided_by_kind == "rule" and stored.decided_by == TIMEOUT_RULE
    assert stored.default_taken == "request changes"
    assert stored.decided_by_role is None, "no person is named: nobody decided"


def test_a_timeout_cannot_be_recorded_as_an_approval() -> None:
    with pytest.raises(ValidationError, match="never recorded as anything but a timeout"):
        timeout(outcome="approved")
    with pytest.raises(ValidationError, match="recorded by a rule"):
        timeout(decided_by_kind="human", decided_by="oid", decided_by_role="sponsor")
    with pytest.raises(ValidationError, match="default that was taken"):
        timeout(default_taken=None)


def test_a_human_decision_names_the_role() -> None:
    with pytest.raises(ValidationError, match="role"):
        human(decided_by_role=None)


def test_an_agent_may_answer_a_question_but_never_decide(stores: Stores) -> None:
    answer = human(
        type="answer_to_question",
        decided_by_kind="agent",
        decided_by="agt_1",
        decided_by_role=None,
        outcome="answered",
    )
    assert stores.decisions.record(answer) == answer
    with pytest.raises(ValidationError, match="not a decision"):
        human(decided_by_kind="agent", decided_by="agt_1", decided_by_role=None)


def test_an_override_is_a_persons_own_row_naming_what_it_overrides(stores: Stores) -> None:
    original = human(
        type="answer_to_question",
        decided_by_kind="agent",
        decided_by="agt_1",
        decided_by_role=None,
        outcome="answered",
    )
    stores.decisions.record(original)
    override = human(
        type="override",
        outcome="overridden",
        overrides_decision_id=original.decision_id,
        comment="The agent assumed the wrong region.",
    )
    stores.decisions.record(override)
    assert stores.decisions.get(override.decision_id).overrides_decision_id == original.decision_id
    assert stores.decisions.get(original.decision_id).outcome == "answered", "unchanged"


def test_an_override_needs_a_reason_a_person_and_an_existing_target(stores: Stores) -> None:
    with pytest.raises(ValidationError, match="gives a reason"):
        human(type="override", outcome="overridden", overrides_decision_id="dec_x", comment=" ")
    with pytest.raises(ValidationError, match="gives a reason"):
        human(type="override", outcome="overridden", comment="why")
    dangling = human(
        type="override", outcome="overridden", overrides_decision_id="dec_missing", comment="why"
    )
    with pytest.raises(KeyError):
        stores.decisions.record(dangling)


def test_recording_the_same_decision_again_changes_nothing(stores: Stores) -> None:
    decision = human()
    stores.decisions.record(decision)
    assert stores.decisions.record(decision) == decision
    assert len(stores.decisions.for_project(PROJECT)) == 1
    with pytest.raises(DecisionConflict):
        stores.decisions.record(decision.model_copy(update={"outcome": "rejected"}))
    assert stores.decisions.get(decision.decision_id).outcome == "approved"


def test_a_project_lists_its_decisions_in_the_order_they_were_made(stores: Stores) -> None:
    now = datetime(2026, 11, 21, 12, 0, tzinfo=UTC)
    later = human(decided_at=now + timedelta(minutes=5), outcome="rejected")
    earlier = human(decided_at=now)
    elsewhere = human(project_id="prj_ab13", decided_at=now)
    for decision in (later, earlier, elsewhere):
        stores.decisions.record(decision)
    assert [d.decision_id for d in stores.decisions.for_project(PROJECT)] == [
        earlier.decision_id,
        later.decision_id,
    ]


def test_followups_link_the_audit_events_that_came_next(stores: Stores) -> None:
    decision = human()
    stores.decisions.record(decision)
    first = stores.audit.append("plan.drafted", actor="system:supervisor")
    second = stores.audit.append("plan.approved", actor="system:supervisor")
    for event in (first, second, first):
        stores.decisions.add_followup(decision.decision_id, event.event_id)
    assert sorted(stores.decisions.followups(decision.decision_id)) == sorted(
        [first.event_id, second.event_id]
    )
    with pytest.raises(KeyError):
        stores.decisions.add_followup("dec_missing", first.event_id)


def test_the_card_hash_changes_with_what_the_decider_saw() -> None:
    other = CARD.model_copy(update={"recommendation": "request changes"})
    assert card_hash(CARD) == card_hash(CARD.model_copy())
    assert card_hash(CARD) != card_hash(other)


def test_a_card_that_no_longer_matches_its_hash_is_reported(stores: Stores) -> None:
    if stores.dsn is None:
        pytest.skip("only the PostgreSQL register keeps a stored hash to compare")
    decision = human()
    stores.decisions.record(decision)
    with psycopg.connect(stores.dsn, autocommit=True) as conn:
        conn.execute("ALTER TABLE decisions DISABLE TRIGGER USER")
        conn.execute(
            "UPDATE decisions SET card = jsonb_set(card, '{recommendation}', '\"reject\"') "
            "WHERE decision_id = %s",
            (decision.decision_id,),
        )
        conn.execute("ALTER TABLE decisions ENABLE TRIGGER USER")
    with pytest.raises(StoredDataCorrupt):
        stores.decisions.get(decision.decision_id)
