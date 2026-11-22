"""Evidence by construction (ADR-0004): the same behaviour from both evidence stores."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from orchestrator.contracts import (
    AgentResult,
    Claim,
    Classification,
    Confidence,
    Evidence,
    SourceType,
    SpecialistOutput,
    Usage,
)
from orchestrator.persistence.evidence import EvidenceConflict
from tests.integration.conftest import Stores

PROJECT = "prj_ab12"


def evidence(agent: str = "agt_1", **over: object) -> Evidence:
    base: dict[str, object] = dict(
        project_id=PROJECT,
        captured_by_agent=agent,
        captured_by_tool="web_search@1.0.0",
        source_type=SourceType.PRIMARY_DOCUMENT,
        reference="https://learn.microsoft.com/example",
        title="A source",
        extract="The service supports change capture.",
        content_sha256="a" * 64,
        published_at=datetime(2026, 1, 2, 3, 4, 5, 678901, tzinfo=UTC),
        classification=Classification.INTERNAL,
        quality_score=0.8,
    )
    base.update(over)
    return Evidence(**base)  # type: ignore[arg-type]


def test_evidence_round_trips_exactly(stores: Stores) -> None:
    item = evidence()
    stores.evidence.put(item)
    assert stores.evidence.get(item.evidence_id) == item


def test_saving_the_same_evidence_again_changes_nothing(stores: Stores) -> None:
    item = evidence()
    stores.evidence.put(item)
    stores.evidence.put(item)
    assert stores.evidence.for_agent(PROJECT, "agt_1") == [item]


def test_other_content_under_an_existing_id_is_refused(stores: Stores) -> None:
    item = evidence()
    stores.evidence.put(item)
    with pytest.raises(EvidenceConflict):
        stores.evidence.put(item.model_copy(update={"extract": "Something else entirely."}))
    assert stores.evidence.get(item.evidence_id).extract == item.extract


def test_evidence_is_listed_only_for_the_agent_and_project_it_was_issued_to(
    stores: Stores,
) -> None:
    mine, theirs = evidence("agt_1"), evidence("agt_2")
    elsewhere = evidence("agt_1", project_id="prj_ab13")
    for item in (mine, theirs, elsewhere):
        stores.evidence.put(item)
    assert stores.evidence.for_agent(PROJECT, "agt_1") == [mine]
    assert stores.evidence.for_agent(PROJECT, "agt_2") == [theirs]


def test_an_agent_cannot_cite_evidence_issued_to_another_agent(stores: Stores) -> None:
    mine, theirs = evidence("agt_1"), evidence("agt_2")
    stores.evidence.put(mine)
    stores.evidence.put(theirs)
    cited = [mine.evidence_id, theirs.evidence_id, "ev_invented"]
    assert stores.evidence.not_issued_to(PROJECT, "agt_1", cited) == {
        theirs.evidence_id,
        "ev_invented",
    }
    assert stores.evidence.not_issued_to(PROJECT, "agt_1", []) == set()


def test_a_result_is_valid_only_with_the_evidence_the_store_issued_to_the_agent(
    stores: Stores,
) -> None:
    item = evidence()
    stores.evidence.put(item)

    def result_citing(*ids: str) -> AgentResult:
        output = SpecialistOutput(
            executive_summary="Done.",
            findings=["f"],
            claims=[
                Claim(statement="A claim.", evidence_ids=list(ids), confidence=Confidence.HIGH)
            ],
            recommended_next_action="Hand to the lead.",
            completion_status="complete",
            overall_confidence=Confidence.MEDIUM,
        )
        return AgentResult(
            task_id="task_1",
            agent_id="agt_1",
            output=output,
            evidence=stores.evidence.for_agent(PROJECT, "agt_1"),
            usage=Usage(),
        )

    assert result_citing(item.evidence_id).output.claims[0].evidence_ids == [item.evidence_id]
    with pytest.raises(ValidationError, match="unknown evidence ids"):
        result_citing("ev_invented")


def test_evidence_with_an_out_of_range_score_is_refused_before_storage() -> None:
    with pytest.raises(ValidationError):
        evidence(quality_score=1.5)
