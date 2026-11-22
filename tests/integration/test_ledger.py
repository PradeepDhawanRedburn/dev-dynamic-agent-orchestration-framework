"""The budget ledger (ADR-0005, ADR-0034): the same behaviour from the in-memory and PostgreSQL
versions."""

from decimal import Decimal

import pytest

from orchestrator.contracts import Usage
from orchestrator.governance.budget import BudgetExceeded, ReservationClosed
from tests.integration.conftest import Stores

D = Decimal
WHO = "00000000-aaaa-bbbb-cccc-000000000001"


def open_chain(
    stores: Stores, project: Decimal = Decimal("10"), workstream: Decimal = Decimal("4")
) -> list[str]:
    stores.ledger.open_scope("prj_1", project, changed_by=WHO)
    stores.ledger.open_scope("prj_1/ws_1", workstream, changed_by=WHO)
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
    stores.ledger.open_scope("prj_1", D("5"), changed_by=WHO)
    stores.ledger.open_scope("prj_1/ws_1", D("4"), changed_by=WHO)
    stores.ledger.open_scope("prj_1/ws_2", D("4"), changed_by=WHO)
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
    record = stores.ledger.reservation("r1")
    assert (record.state, record.settled_amount) == ("settled", D("1.2345"))


def test_releasing_frees_the_amount_but_keeps_the_reservation_readable(stores: Stores) -> None:
    chain = open_chain(stores)
    stores.ledger.reserve("r1", chain, D("4"))
    stores.ledger.release("r1")
    stores.ledger.release("r1")  # safe to repeat
    assert stores.ledger.snapshot("prj_1/ws_1").reserved == D("0")
    record = stores.ledger.reservation("r1")
    assert (record.state, record.amount, record.chain) == ("released", D("4"), chain)


def test_a_released_id_is_not_reserved_again_and_cannot_be_settled(stores: Stores) -> None:
    chain = open_chain(stores)
    stores.ledger.reserve("r1", chain, D("4"))
    stores.ledger.release("r1")
    stores.ledger.reserve("r1", chain, D("4"))  # a retry: nothing happens
    assert stores.ledger.snapshot("prj_1/ws_1").reserved == D("0")
    with pytest.raises(ReservationClosed):
        stores.ledger.settle("r1", Usage(cost=D("1")))
    assert stores.ledger.snapshot("prj_1").committed == D("0")
    stores.ledger.reserve("r2", chain, D("4"))  # the freed amount is available under a new id
    assert stores.ledger.snapshot("prj_1/ws_1").reserved == D("4")


def test_releasing_a_settled_or_unknown_reservation_changes_nothing(stores: Stores) -> None:
    chain = open_chain(stores)
    stores.ledger.reserve("r1", chain, D("2"))
    stores.ledger.settle("r1", Usage(cost=D("1")))
    stores.ledger.release("r1")
    stores.ledger.release("never-reserved")
    assert stores.ledger.reservation("r1").state == "settled"
    with pytest.raises(KeyError):
        stores.ledger.reservation("never-reserved")


def test_snapshot_states_follow_the_warning_fraction(stores: Stores) -> None:
    stores.ledger.open_scope("s", D("10"), changed_by=WHO)
    assert stores.ledger.snapshot("s").state == "ok"
    stores.ledger.reserve("a", ["s"], D("8"))
    assert stores.ledger.snapshot("s").state == "warning"
    stores.ledger.reserve("b", ["s"], D("2"))
    snap = stores.ledger.snapshot("s")
    assert snap.state == "exhausted" and snap.available == D("0")


def test_unknown_scopes_and_reservations_are_errors(stores: Stores) -> None:
    stores.ledger.open_scope("s", D("1"), changed_by=WHO)
    with pytest.raises(KeyError):
        stores.ledger.snapshot("nope")
    with pytest.raises(KeyError):
        stores.ledger.reserve("r", ["s", "nope"], D("0.1"))
    with pytest.raises(KeyError):
        stores.ledger.settle("never-reserved", Usage())


def test_amounts_keep_full_decimal_precision(stores: Stores) -> None:
    stores.ledger.open_scope("s", D("0.000001"), changed_by=WHO)
    stores.ledger.reserve("a", ["s"], D("0.000001"))
    with pytest.raises(BudgetExceeded):
        stores.ledger.reserve("b", ["s"], D("0.0000001"))


def test_reopening_a_scope_changes_its_limit_and_keeps_what_was_committed(stores: Stores) -> None:
    stores.ledger.open_scope("s", D("5"), changed_by=WHO)
    stores.ledger.reserve("a", ["s"], D("2"))
    stores.ledger.settle("a", Usage(cost=D("2")))
    stores.ledger.open_scope("s", D("9"), changed_by=WHO)
    snap = stores.ledger.snapshot("s")
    assert (snap.limit, snap.committed) == (D("9"), D("2"))


# ---------------------------------------------------------------- limit changes are audited
def test_opening_a_scope_and_changing_its_limit_are_audited_with_who_did_it(
    stores: Stores,
) -> None:
    stores.ledger.open_scope("prj_1/ws_1", D("5"), changed_by="system:planner")
    stores.ledger.open_scope("prj_1/ws_1", D("8"), changed_by=WHO)
    opened, changed = stores.audit.events(project_id="prj_1")
    assert (opened.kind, opened.actor) == ("budget.scope_opened", "system:planner")
    assert opened.details == {"scope": "prj_1/ws_1", "old_limit": None, "new_limit": "5"}
    assert (changed.kind, changed.actor) == ("budget.limit_changed", WHO)
    assert changed.details == {"scope": "prj_1/ws_1", "old_limit": "5", "new_limit": "8"}
    assert stores.audit.verify_chain().ok


def test_setting_the_limit_it_already_has_writes_nothing(stores: Stores) -> None:
    stores.ledger.open_scope("prj_1", D("5"), changed_by=WHO)
    stores.ledger.open_scope("prj_1", D("5"), changed_by="someone-else")  # a retried node
    assert len(stores.audit.events()) == 1


def test_a_limit_without_a_named_person_or_service_is_refused(stores: Stores) -> None:
    with pytest.raises(Exception):  # noqa: B017  (the audit model rejects an empty actor)
        stores.ledger.open_scope("prj_1", D("5"), changed_by="")
    with pytest.raises(KeyError):
        stores.ledger.snapshot("prj_1")


def test_a_returned_reservation_is_a_copy_so_the_record_cannot_be_rewritten(
    stores: Stores,
) -> None:
    chain = open_chain(stores)
    stores.ledger.reserve("res_1", chain, D("1"))
    stores.ledger.release("res_1")
    record = stores.ledger.reservation("res_1")
    record.state = "reserved"
    record.amount = D("9")
    record.chain.append("prj_other")
    again = stores.ledger.reservation("res_1")
    assert (again.state, again.amount, again.chain) == ("released", D("1"), chain)
    with pytest.raises(ReservationClosed):
        stores.ledger.settle("res_1", Usage(cost=D("1")))


def test_opening_a_scope_waits_for_whoever_else_is_changing_that_scope(stores: Stores) -> None:
    """Deterministic: the scope's advisory lock is taken on another connection, and `open_scope`
    must not read the old limit until it is released. (`FOR UPDATE` alone locks nothing while the
    scope does not exist, so two first opens could both see no limit.)"""
    if stores.dsn is None:
        pytest.skip("PostgreSQL only")
    import threading
    import time

    import psycopg

    done = threading.Event()

    def attempt() -> None:
        stores.ledger.open_scope("prj_lock", D("5"), changed_by=WHO)
        done.set()

    with psycopg.connect(stores.dsn) as blocker:
        blocker.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ("scope:prj_lock",))
        worker = threading.Thread(target=attempt)
        worker.start()
        time.sleep(1.0)
        assert not done.is_set(), "open_scope went ahead while the scope was locked"
        blocker.rollback()
    worker.join(timeout=10)
    assert done.is_set()
    assert [e.kind for e in stores.audit.events(project_id="prj_lock")] == ["budget.scope_opened"]


def test_concurrent_first_opens_of_one_scope_write_one_event_and_agree_on_the_limit(
    stores: Stores,
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(8) as pool:
        futures = [
            pool.submit(stores.ledger.open_scope, "prj_race", D(str(limit)), changed_by=WHO)
            for limit in (5, 5, 5, 5, 5, 5, 5, 5)
        ]
        for future in futures:
            future.result()
    events = stores.audit.events(project_id="prj_race")
    assert [e.kind for e in events] == ["budget.scope_opened"]
    assert stores.ledger.snapshot("prj_race").limit == D("5")


def test_concurrent_changes_to_one_scope_each_record_the_limit_they_replaced(
    stores: Stores,
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    stores.ledger.open_scope("prj_race", D("1"), changed_by=WHO)
    with ThreadPoolExecutor(8) as pool:
        futures = [
            pool.submit(stores.ledger.open_scope, "prj_race", D(str(limit)), changed_by=WHO)
            for limit in range(2, 10)
        ]
        for future in futures:
            future.result()
    events = stores.audit.events(project_id="prj_race")
    changes = [e for e in events if e.kind == "budget.limit_changed"]
    assert len(changes) == 8
    olds = {str(dict(e.details)["old_limit"]) for e in changes}
    news = {str(dict(e.details)["new_limit"]) for e in changes}
    assert len(olds) == 8 and len(news) == 8, "no two changes replaced the same limit"
    assert stores.audit.verify_chain().ok
