"""PostgreSQL implementations of the stores (ADR-0003).

Each class implements the interface of its in-memory twin, so the same behavioural tests run
against both. Calls are synchronous and each opens its own short transaction on a pooled
connection; an async node calls them through `asyncio.to_thread`.

Every method is safe to repeat, because a graph node can be retried or re-run when an interrupt
resumes. The schema is created by `persistence/migrate.py`; the application connects as a member
of `orchestrator_app`, which cannot update or delete audit events or decisions."""

from collections.abc import Iterable, Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from psycopg import errors, sql
from psycopg.types.json import Jsonb
from pydantic import JsonValue

from orchestrator.contracts import (
    AgentSpecification,
    AgentStatus,
    Evidence,
    RetirementRecord,
    Usage,
    assert_transition,
    new_id,
    utcnow,
)
from orchestrator.governance.approvals import (
    DecisionCard,
    DecisionConflict,
    DecisionRecord,
    card_hash,
)
from orchestrator.governance.budget import BudgetExceeded, BudgetSnapshot
from orchestrator.governance.recruiter import AgentRecord
from orchestrator.observability.tracing import current_trace_ids
from orchestrator.persistence.audit import (
    AuditEvent,
    ChainReport,
    check_chain,
    seal,
)
from orchestrator.persistence.db import Pool
from orchestrator.persistence.evidence import EvidenceConflict


class StoredDataCorrupt(Exception):
    """A stored row no longer matches the hash or value it was written with."""


# ---------------------------------------------------------------- budget ledger
class PostgresLedger:
    """Scopes form a chain, for example ['prj_1', 'prj_1/ws_2']. A reservation takes row locks on
    every scope in the chain, in name order so two reservations cannot deadlock, and fits only if
    committed plus reserved plus the new amount stays within every limit."""

    def __init__(self, pool: Pool, warn_fraction: Decimal = Decimal("0.8")) -> None:
        self._pool, self._warn = pool, warn_fraction

    def open_scope(self, scope: str, limit: Decimal) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO budget_scopes (scope, limit_amount) VALUES (%s, %s) "
                "ON CONFLICT (scope) DO UPDATE SET limit_amount = EXCLUDED.limit_amount",
                (scope, limit),
            )

    def reserve(self, reservation_id: str, chain: list[str], amount: Decimal) -> None:
        with self._pool.connection() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (reservation_id,))
            rows = conn.execute(
                "SELECT scope, limit_amount, committed FROM budget_scopes "
                "WHERE scope = ANY(%s) ORDER BY scope FOR UPDATE",
                (chain,),
            ).fetchall()
            if conn.execute(
                "SELECT 1 FROM budget_reservations WHERE reservation_id = %s", (reservation_id,)
            ).fetchone():
                return  # idempotent on retry, whether still reserved or already settled
            scopes = {row["scope"]: row for row in rows}
            for scope in chain:
                if scope not in scopes:
                    raise KeyError(scope)
                reserved = self._reserved(conn, scope)
                used = scopes[scope]["committed"] + reserved + amount
                if used > scopes[scope]["limit_amount"]:
                    raise BudgetExceeded(scope, scopes[scope]["limit_amount"], used)
            conn.execute(
                "INSERT INTO budget_reservations (reservation_id, chain, amount, state) "
                "VALUES (%s, %s, %s, 'reserved') "
                "ON CONFLICT (reservation_id) DO NOTHING",
                (reservation_id, chain, amount),
            )

    @staticmethod
    def _reserved(conn: Any, scope: str) -> Decimal:
        row = conn.execute(
            "SELECT coalesce(sum(amount), 0) AS reserved FROM budget_reservations "
            "WHERE state = 'reserved' AND %s = ANY(chain)",
            (scope,),
        ).fetchone()
        reserved: Decimal = row["reserved"]
        return reserved

    def settle(self, reservation_id: str, usage: Usage) -> None:
        """Replace the reservation with the actual cost. Safe to call twice."""
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT chain, state FROM budget_reservations WHERE reservation_id = %s FOR UPDATE",
                (reservation_id,),
            ).fetchone()
            if row is None:
                raise KeyError(reservation_id)
            if row["state"] == "settled":
                return
            conn.execute(
                "SELECT scope FROM budget_scopes WHERE scope = ANY(%s) ORDER BY scope FOR UPDATE",
                (row["chain"],),
            )
            for scope in row["chain"]:
                conn.execute(
                    "UPDATE budget_scopes SET committed = committed + %s WHERE scope = %s",
                    (usage.cost, scope),
                )
            conn.execute(
                "UPDATE budget_reservations SET state = 'settled', settled_amount = %s "
                "WHERE reservation_id = %s",
                (usage.cost, reservation_id),
            )

    def release(self, reservation_id: str) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "DELETE FROM budget_reservations WHERE reservation_id = %s AND state = 'reserved'",
                (reservation_id,),
            )

    def snapshot(self, scope: str) -> BudgetSnapshot:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT limit_amount, committed, "
                "(SELECT coalesce(sum(amount), 0) FROM budget_reservations "
                " WHERE state = 'reserved' AND %s = ANY(chain)) AS reserved "
                "FROM budget_scopes WHERE scope = %s",
                (scope, scope),
            ).fetchone()
        if row is None:
            raise KeyError(scope)
        limit, committed, reserved = row["limit_amount"], row["committed"], row["reserved"]
        used = committed + reserved
        state: Literal["ok", "warning", "exhausted"] = (
            "exhausted" if used >= limit else "warning" if used >= limit * self._warn else "ok"
        )
        return BudgetSnapshot(
            scope=scope, limit=limit, committed=committed, reserved=reserved, state=state
        )


# ---------------------------------------------------------------- agent registry
class PostgresAgentRegistry:
    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    def add(self, record: AgentRecord) -> None:
        with self._pool.connection() as conn:
            created = conn.execute(
                "INSERT INTO agent_records (agent_id, project_id, request_hash, status, spec) "
                "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (agent_id) DO NOTHING",
                (
                    record.spec.agent_id,
                    record.spec.project_id,
                    record.request_hash,
                    record.status.value,
                    Jsonb(record.spec.model_dump(mode="json")),
                ),
            ).rowcount
            if created:
                for seq, (status, at) in enumerate(record.history, start=1):
                    conn.execute(
                        "INSERT INTO agent_transitions (agent_id, seq, status, at) "
                        "VALUES (%s, %s, %s, %s)",
                        (record.spec.agent_id, seq, status.value, at),
                    )

    def get(self, agent_id: str) -> AgentRecord:
        with self._pool.connection() as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            row = conn.execute(
                "SELECT agent_id, request_hash, status, spec, retirement "
                "FROM agent_records WHERE agent_id = %s",
                (agent_id,),
            ).fetchone()
            if row is None:
                raise KeyError(agent_id)
            history = conn.execute(
                "SELECT status, at FROM agent_transitions WHERE agent_id = %s ORDER BY seq",
                (agent_id,),
            ).fetchall()
        return self._record(row, history)

    def for_project(self, project_id: str) -> list[AgentRecord]:
        with self._pool.connection() as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            rows = conn.execute(
                "SELECT agent_id, request_hash, status, spec, retirement "
                "FROM agent_records WHERE project_id = %s ORDER BY created_at, agent_id",
                (project_id,),
            ).fetchall()
            history = conn.execute(
                "SELECT t.agent_id, t.status, t.at FROM agent_transitions t "
                "JOIN agent_records r USING (agent_id) WHERE r.project_id = %s "
                "ORDER BY t.agent_id, t.seq",
                (project_id,),
            ).fetchall()
        by_agent: dict[str, list[dict[str, Any]]] = {}
        for item in history:
            by_agent.setdefault(item["agent_id"], []).append(item)
        return [self._record(row, by_agent.get(row["agent_id"], [])) for row in rows]

    @staticmethod
    def _record(row: dict[str, Any], history: list[dict[str, Any]]) -> AgentRecord:
        status = AgentStatus(row["status"])
        spec = AgentSpecification.model_validate(row["spec"]).model_copy(update={"status": status})
        retirement = (
            RetirementRecord.model_validate(row["retirement"])
            if row["retirement"] is not None
            else None
        )
        return AgentRecord(
            spec=spec,
            status=status,
            request_hash=row["request_hash"],
            history=[(AgentStatus(h["status"]), h["at"]) for h in history],
            retirement=retirement,
        )

    def transition(self, agent_id: str, new: AgentStatus) -> None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT status FROM agent_records WHERE agent_id = %s FOR UPDATE", (agent_id,)
            ).fetchone()
            if row is None:
                raise KeyError(agent_id)
            current = AgentStatus(row["status"])
            if current == new:
                return  # idempotent: a retried node repeats this
            assert_transition(current, new)
            conn.execute(
                "UPDATE agent_records SET status = %s WHERE agent_id = %s", (new.value, agent_id)
            )
            conn.execute(
                "INSERT INTO agent_transitions (agent_id, seq, status) "
                "SELECT %s, coalesce(max(seq), 0) + 1, %s FROM agent_transitions "
                "WHERE agent_id = %s",
                (agent_id, new.value, agent_id),
            )

    def set_retirement(self, agent_id: str, retirement: RetirementRecord) -> None:
        with self._pool.connection() as conn:
            updated = conn.execute(
                "UPDATE agent_records SET retirement = %s WHERE agent_id = %s",
                (Jsonb(retirement.model_dump(mode="json")), agent_id),
            ).rowcount
        if not updated:
            raise KeyError(agent_id)

    def retire_atomically(
        self, agent_id: str, retirement: RetirementRecord, final_status: AgentStatus
    ) -> None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT status FROM agent_records WHERE agent_id = %s FOR UPDATE", (agent_id,)
            ).fetchone()
            if row is None:
                raise KeyError(agent_id)
            current = AgentStatus(row["status"])
            if current != final_status:
                assert_transition(current, final_status)
            conn.execute(
                "UPDATE agent_records SET status = %s, retirement = %s WHERE agent_id = %s",
                (
                    final_status.value,
                    Jsonb(retirement.model_dump(mode="json")),
                    agent_id,
                ),
            )
            if current != final_status:
                conn.execute(
                    "INSERT INTO agent_transitions (agent_id, seq, status) "
                    "SELECT %s, coalesce(max(seq), 0) + 1, %s FROM agent_transitions "
                    "WHERE agent_id = %s",
                    (agent_id, final_status.value, agent_id),
                )


# ---------------------------------------------------------------- evidence
EVIDENCE_COLUMNS = (
    "evidence_id, project_id, captured_by_agent, captured_by_tool, source_type, reference, "
    "title, extract, content_sha256, published_at, retrieved_at, classification, quality_score"
)


class PostgresEvidenceStore:
    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    def put(self, evidence: Evidence) -> None:
        with self._pool.connection() as conn:
            created = conn.execute(
                "INSERT INTO evidence (evidence_id, project_id, captured_by_agent, "
                "captured_by_tool, source_type, reference, title, extract, content_sha256, "
                "published_at, retrieved_at, classification, quality_score) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (evidence_id) DO NOTHING",
                (
                    evidence.evidence_id,
                    evidence.project_id,
                    evidence.captured_by_agent,
                    evidence.captured_by_tool,
                    evidence.source_type.value,
                    evidence.reference,
                    evidence.title,
                    evidence.extract,
                    evidence.content_sha256,
                    evidence.published_at,
                    evidence.retrieved_at,
                    evidence.classification.value,
                    evidence.quality_score,
                ),
            ).rowcount
        if not created and self.get(evidence.evidence_id) != evidence:
            raise EvidenceConflict(f"{evidence.evidence_id} already exists with other content")

    def get(self, evidence_id: str) -> Evidence:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT evidence_id, project_id, captured_by_agent, captured_by_tool, source_type, "
                "reference, title, extract, content_sha256, published_at, retrieved_at, "
                "classification, quality_score FROM evidence WHERE evidence_id = %s",
                (evidence_id,),
            ).fetchone()
        if row is None:
            raise KeyError(evidence_id)
        return Evidence(**row)

    def for_agent(self, project_id: str, agent_id: str) -> list[Evidence]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT evidence_id, project_id, captured_by_agent, captured_by_tool, source_type, "
                "reference, title, extract, content_sha256, published_at, retrieved_at, "
                "classification, quality_score FROM evidence "
                "WHERE project_id = %s AND captured_by_agent = %s "
                "ORDER BY retrieved_at, evidence_id",
                (project_id, agent_id),
            ).fetchall()
        return [Evidence(**row) for row in rows]

    def not_issued_to(
        self, project_id: str, agent_id: str, evidence_ids: Iterable[str]
    ) -> set[str]:
        wanted = list(evidence_ids)
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT evidence_id FROM evidence WHERE project_id = %s AND captured_by_agent = %s "
                "AND evidence_id = ANY(%s)",
                (project_id, agent_id, wanted),
            ).fetchall()
        return set(wanted) - {row["evidence_id"] for row in rows}


# ---------------------------------------------------------------- audit log
AUDIT_COLUMNS = sql.SQL(
    "seq, event_id, occurred_at, kind, actor, project_id, workstream_id, task_id, agent_id, "
    "correlation_id, details, trace_id, span_id, prev_hash, hash"
)


class PostgresAuditLog:
    """Writers take a lock on the single audit_head row, so events have one order and each links
    to the one before. The application role has INSERT and SELECT on the events, never UPDATE or
    DELETE."""

    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    def append(
        self,
        kind: str,
        *,
        actor: str,
        project_id: str | None = None,
        workstream_id: str | None = None,
        task_id: str | None = None,
        agent_id: str | None = None,
        correlation_id: str | None = None,
        details: Mapping[str, JsonValue] | None = None,
        event_id: str | None = None,
    ) -> AuditEvent:
        trace_id, span_id = current_trace_ids()
        with self._pool.connection() as conn:
            head = conn.execute(
                "SELECT last_seq, last_hash FROM audit_head WHERE id = 1 FOR UPDATE"
            ).fetchone()
            if head is None:
                raise StoredDataCorrupt("audit_head row is missing")
            if event_id is not None:
                existing = conn.execute(
                    sql.SQL("SELECT {} FROM audit_events WHERE event_id = %s").format(
                        AUDIT_COLUMNS
                    ),
                    (event_id,),
                ).fetchone()
                if existing is not None:
                    return AuditEvent(**existing)
            event = seal(
                AuditEvent(
                    seq=head["last_seq"] + 1,
                    event_id=event_id or new_id("aud"),
                    occurred_at=utcnow(),
                    kind=kind,
                    actor=actor,
                    project_id=project_id,
                    workstream_id=workstream_id,
                    task_id=task_id,
                    agent_id=agent_id,
                    correlation_id=correlation_id,
                    details=dict(details or {}),
                    trace_id=trace_id,
                    span_id=span_id,
                    prev_hash=head["last_hash"],
                    hash="",
                )
            )
            conn.execute(
                sql.SQL("INSERT INTO audit_events ({}) VALUES ({})").format(
                    AUDIT_COLUMNS, sql.SQL(", ").join([sql.Placeholder()] * 15)
                ),
                (
                    event.seq,
                    event.event_id,
                    event.occurred_at,
                    event.kind,
                    event.actor,
                    event.project_id,
                    event.workstream_id,
                    event.task_id,
                    event.agent_id,
                    event.correlation_id,
                    Jsonb(event.details),
                    event.trace_id,
                    event.span_id,
                    event.prev_hash,
                    event.hash,
                ),
            )
            conn.execute(
                "UPDATE audit_head SET last_seq = %s, last_hash = %s WHERE id = 1",
                (event.seq, event.hash),
            )
        return event

    def events(
        self, *, project_id: str | None = None, agent_id: str | None = None, kind: str | None = None
    ) -> list[AuditEvent]:
        conditions: list[sql.Composable] = []
        params: list[str] = []
        for column, value in (("project_id", project_id), ("agent_id", agent_id), ("kind", kind)):
            if value is not None:
                conditions.append(sql.SQL("{} = %s").format(sql.Identifier(column)))
                params.append(value)
        where = (
            sql.SQL(" WHERE ") + sql.SQL(" AND ").join(conditions) if conditions else sql.SQL("")
        )
        query = sql.SQL("SELECT {} FROM audit_events{} ORDER BY seq").format(AUDIT_COLUMNS, where)
        with self._pool.connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [AuditEvent(**row) for row in rows]

    def verify_chain(self) -> ChainReport:
        with self._pool.connection() as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            rows = conn.execute(
                sql.SQL("SELECT {} FROM audit_events ORDER BY seq").format(AUDIT_COLUMNS)
            ).fetchall()
            head = conn.execute(
                "SELECT last_seq, last_hash FROM audit_head WHERE id = 1"
            ).fetchone()
        if head is None:
            raise StoredDataCorrupt("audit_head row is missing")
        stored = (head["last_seq"], head["last_hash"])
        return check_chain([AuditEvent(**row) for row in rows], stored)


# ---------------------------------------------------------------- decision register
DECISION_COLUMNS = (
    "decision_id, project_id, decided_at, type, decided_by_kind, decided_by, decided_by_role, "
    "card, card_hash, outcome, comment, default_taken, overrides_decision_id, checkpoint_id, "
    "baseline_version"
)


class PostgresDecisionRegister:
    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    def record(self, decision: DecisionRecord) -> DecisionRecord:
        try:
            with self._pool.connection() as conn:
                created = conn.execute(
                    "INSERT INTO decisions (decision_id, project_id, decided_at, type, "
                    "decided_by_kind, decided_by, decided_by_role, card, card_hash, outcome, "
                    "comment, default_taken, overrides_decision_id, checkpoint_id, "
                    "baseline_version) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (decision_id) DO NOTHING",
                    (
                        decision.decision_id,
                        decision.project_id,
                        decision.decided_at,
                        decision.type,
                        decision.decided_by_kind,
                        decision.decided_by,
                        decision.decided_by_role,
                        Jsonb(decision.card.model_dump(mode="json")),
                        decision.card_hash,
                        decision.outcome,
                        decision.comment,
                        decision.default_taken,
                        decision.overrides_decision_id,
                        decision.checkpoint_id,
                        decision.baseline_version,
                    ),
                ).rowcount
        except errors.ForeignKeyViolation as error:
            raise KeyError(decision.overrides_decision_id) from error
        if created:
            return decision
        stored = self.get(decision.decision_id)
        if stored != decision:
            raise DecisionConflict(f"{decision.decision_id} already exists")
        return stored

    def get(self, decision_id: str) -> DecisionRecord:
        with self._pool.connection() as conn:
            row = conn.execute(
                sql.SQL("SELECT {} FROM decisions WHERE decision_id = %s").format(
                    sql.SQL(DECISION_COLUMNS)
                ),
                (decision_id,),
            ).fetchone()
        if row is None:
            raise KeyError(decision_id)
        return self._decision(row)

    def for_project(self, project_id: str) -> list[DecisionRecord]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                sql.SQL(
                    "SELECT {} FROM decisions WHERE project_id = %s "
                    "ORDER BY decided_at, decision_id"
                ).format(sql.SQL(DECISION_COLUMNS)),
                (project_id,),
            ).fetchall()
        return [self._decision(row) for row in rows]

    @staticmethod
    def _decision(row: dict[str, Any]) -> DecisionRecord:
        card = DecisionCard.model_validate(row["card"])
        if card_hash(card) != row["card_hash"]:
            raise StoredDataCorrupt(f"decision {row['decision_id']}: the card no longer matches")
        decided_at: datetime = row["decided_at"]
        return DecisionRecord(
            decision_id=row["decision_id"],
            project_id=row["project_id"],
            decided_at=decided_at,
            type=row["type"],
            decided_by_kind=row["decided_by_kind"],
            decided_by=row["decided_by"],
            decided_by_role=row["decided_by_role"],
            card=card,
            outcome=row["outcome"],
            comment=row["comment"],
            default_taken=row["default_taken"],
            overrides_decision_id=row["overrides_decision_id"],
            checkpoint_id=row["checkpoint_id"],
            baseline_version=row["baseline_version"],
        )

    def add_followup(self, decision_id: str, audit_event_id: str) -> None:
        try:
            with self._pool.connection() as conn:
                conn.execute(
                    "INSERT INTO decision_followups (decision_id, audit_event_id) "
                    "VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (decision_id, audit_event_id),
                )
        except errors.ForeignKeyViolation as error:
            raise KeyError(decision_id) from error

    def followups(self, decision_id: str) -> list[str]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT audit_event_id FROM decision_followups WHERE decision_id = %s "
                "ORDER BY audit_event_id",
                (decision_id,),
            ).fetchall()
        return [row["audit_event_id"] for row in rows]
