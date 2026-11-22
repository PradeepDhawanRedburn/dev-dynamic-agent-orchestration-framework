"""The budget ledger (ADR-0005): the same behaviour from the in-memory and PostgreSQL versions."""

from decimal import Decimal

import pytest

from orchestrator.contracts import Usage
from orchestrator.governance.budget import BudgetExceeded
from tests.integration.conftest import Stores

D = Decimal


def open_chain(
    stores: Stores, project: Decimal = Decimal("10"), workstream: Decimal = Decimal("4")
) -> list[str]:
    stores.ledger.open_scope("prj_1", project)
    stores.ledger.open_scope("prj_1/ws_1", workstream)
    return ["prj_1", "prj_1/ws_1"]


def test_a_reservation_must_fit_every_scope_in_its_chain(stores: Stores) -> None:
    chain = open_chain(stores)
    stores.ledger.reserve("r1", chain, D("3"))
    with pytest.raises(BudgetExceeded) as caught:
        stores.ledger.reserve("r2", chain, D("1.5"))  # the workstream would hold 4.5 of 4
    assert caught.value.scope == "prj_1/ws_1"
    assert caught.value.limit == D("4") and caught.value.attempted == D("4.5")
    assert stores.ledger.snapshot("prj_1/ws_1").reserved == D("3"), "nothing was reserved"


def test_a_workstream_cannot_exceed_its_project(stores: Stores) -> None:
    stores.ledger.open_scope("prj_1", D("5"))
    stores.ledger.open_scope("prj_1/ws_1", D("4"))
    stores.ledger.open_scope("prj_1/ws_2", D("4"))
    stores.ledger.reserve("a", ["prj_1", "prj_1/ws_1"], D("4"))
    with pytest.raises(BudgetExceeded) as caught:
        stores.ledger.reserve("b", ["prj_1", "prj_1/ws_2"], D("2"))
    assert caught.value.scope == "prj_1"


def test_reserving_twice_with_the_same_id_reserves_once(stores: Stores) -> None:
    chain = open_chain(stores)
    stores.ledger.reserve("r1", chain, D("2"))
    stores.ledger.reserve("r1", chain, D("2"))
    assert stores.ledger.snapshot("prj_1").reserved == D("2")


def test_settling_replaces_the_reservation_with_the_actual_cost_and_is_idempotent(
    stores: Stores,
) -> None:
    chain = open_chain(stores)
    stores.ledger.reserve("r1", chain, D("3"))
    usage = Usage(cost=D("1.2345"), model_calls=2)
    stores.ledger.settle("r1", usage)
    stores.ledger.settle("r1", Usage(cost=D("99")))  # a retry: ignored
    for scope in chain:
        snap = stores.ledger.snapshot(scope)
        assert (snap.committed, snap.reserved) == (D("1.2345"), D("0"))
    stores.ledger.reserve("r1", chain, D("3"))  # a settled id is never reserved again
    assert stores.ledger.snapshot("prj_1").reserved == D("0")


def test_releasing_frees_the_amount_and_allows_the_id_again(stores: Stores) -> None:
    chain = open_chain(stores)
    stores.ledger.reserve("r1", chain, D("4"))
    stores.ledger.release("r1")
    stores.ledger.release("r1")  # safe to repeat
    assert stores.ledger.snapshot("prj_1/ws_1").reserved == D("0")
    stores.ledger.reserve("r1", chain, D("4"))
    assert stores.ledger.snapshot("prj_1/ws_1").reserved == D("4")


def test_snapshot_states_follow_the_warning_fraction(stores: Stores) -> None:
    stores.ledger.open_scope("s", D("10"))
    assert stores.ledger.snapshot("s").state == "ok"
    stores.ledger.reserve("a", ["s"], D("8"))
    assert stores.ledger.snapshot("s").state == "warning"
    stores.ledger.reserve("b", ["s"], D("2"))
    snap = stores.ledger.snapshot("s")
    assert snap.state == "exhausted" and snap.available == D("0")


def test_unknown_scopes_and_reservations_are_errors(stores: Stores) -> None:
    stores.ledger.open_scope("s", D("1"))
    with pytest.raises(KeyError):
        stores.ledger.snapshot("nope")
    with pytest.raises(KeyError):
        stores.ledger.reserve("r", ["s", "nope"], D("0.1"))
    with pytest.raises(KeyError):
        stores.ledger.settle("never-reserved", Usage())


def test_amounts_keep_full_decimal_precision(stores: Stores) -> None:
    stores.ledger.open_scope("s", D("0.000001"))
    stores.ledger.reserve("a", ["s"], D("0.000001"))
    with pytest.raises(BudgetExceeded):
        stores.ledger.reserve("b", ["s"], D("0.0000001"))


def test_reopening_a_scope_changes_its_limit_and_keeps_what_was_committed(stores: Stores) -> None:
    stores.ledger.open_scope("s", D("5"))
    stores.ledger.reserve("a", ["s"], D("2"))
    stores.ledger.settle("a", Usage(cost=D("2")))
    stores.ledger.open_scope("s", D("9"))
    snap = stores.ledger.snapshot("s")
    assert (snap.limit, snap.committed) == (D("9"), D("2"))
