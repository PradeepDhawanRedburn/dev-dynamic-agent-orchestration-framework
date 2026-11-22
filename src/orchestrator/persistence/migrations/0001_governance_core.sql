-- 0001: governance core (WP-02).
-- The application connects as a member of orchestrator_app. That role can append to the audit
-- log and the decision register but can never update or delete them; triggers refuse the change
-- for every other role as well, so only a superuser who disables a trigger could alter a row.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'orchestrator_app') THEN
        CREATE ROLE orchestrator_app NOLOGIN;
    END IF;
END
$$;

CREATE FUNCTION forbid_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% on % is not allowed: the table is append-only', TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'restrict_violation';
END
$$;

-- ---------------------------------------------------------------- budget ledger (ADR-0005)
CREATE TABLE budget_scopes (
    scope        text PRIMARY KEY,
    limit_amount numeric NOT NULL CHECK (limit_amount >= 0),
    committed    numeric NOT NULL DEFAULT 0 CHECK (committed >= 0)
);

CREATE TABLE budget_reservations (
    reservation_id text PRIMARY KEY,
    chain          text[] NOT NULL CHECK (cardinality(chain) > 0),
    amount         numeric NOT NULL CHECK (amount >= 0),
    state          text NOT NULL CHECK (state IN ('reserved', 'settled')),
    settled_amount numeric,
    created_at     timestamptz NOT NULL DEFAULT now(),
    CHECK ((state = 'settled') = (settled_amount IS NOT NULL))
);
CREATE INDEX budget_reservations_open ON budget_reservations USING gin (chain)
    WHERE state = 'reserved';

-- ---------------------------------------------------------------- agent registry
CREATE TABLE agent_records (
    agent_id     text PRIMARY KEY,
    project_id   text NOT NULL,
    request_hash text NOT NULL,
    status       text NOT NULL,
    spec         jsonb NOT NULL,
    retirement   jsonb,
    created_at   timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX agent_records_project ON agent_records (project_id);

CREATE TABLE agent_transitions (
    agent_id text NOT NULL REFERENCES agent_records (agent_id),
    seq      integer NOT NULL,
    status   text NOT NULL,
    at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (agent_id, seq)
);

-- ---------------------------------------------------------------- evidence metadata (ADR-0004)
CREATE TABLE evidence (
    evidence_id       text PRIMARY KEY,
    project_id        text NOT NULL,
    captured_by_agent text NOT NULL,
    captured_by_tool  text NOT NULL,
    source_type       text NOT NULL,
    reference         text NOT NULL,
    title             text NOT NULL,
    extract           text NOT NULL,
    content_sha256    text NOT NULL,
    published_at      timestamptz,
    retrieved_at      timestamptz NOT NULL,
    classification    text NOT NULL,
    quality_score     double precision NOT NULL CHECK (quality_score BETWEEN 0 AND 1)
);
CREATE INDEX evidence_agent ON evidence (project_id, captured_by_agent);
CREATE TRIGGER evidence_immutable BEFORE UPDATE OR DELETE ON evidence
    FOR EACH ROW EXECUTE FUNCTION forbid_change();
CREATE TRIGGER evidence_no_truncate BEFORE TRUNCATE ON evidence
    FOR EACH STATEMENT EXECUTE FUNCTION forbid_change();

-- ---------------------------------------------------------------- audit log (hash-chained)
CREATE TABLE audit_events (
    seq            bigint PRIMARY KEY,
    event_id       text NOT NULL UNIQUE,
    occurred_at    timestamptz NOT NULL,
    kind           text NOT NULL,
    actor          text NOT NULL,
    project_id     text,
    workstream_id  text,
    task_id        text,
    agent_id       text,
    correlation_id text,
    details        jsonb NOT NULL DEFAULT '{}',
    trace_id       text CHECK (trace_id ~ '^[0-9a-f]{32}$'),
    span_id        text CHECK (span_id ~ '^[0-9a-f]{16}$'),
    prev_hash      text NOT NULL,
    hash           text NOT NULL UNIQUE
);
CREATE INDEX audit_events_project ON audit_events (project_id, seq);
CREATE INDEX audit_events_agent ON audit_events (agent_id, seq);
CREATE TRIGGER audit_events_append_only BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION forbid_change();
CREATE TRIGGER audit_events_no_truncate BEFORE TRUNCATE ON audit_events
    FOR EACH STATEMENT EXECUTE FUNCTION forbid_change();

-- The single row every writer locks, so the chain has one order.
CREATE TABLE audit_head (
    id        smallint PRIMARY KEY CHECK (id = 1),
    last_seq  bigint NOT NULL,
    last_hash text NOT NULL
);
INSERT INTO audit_head VALUES (1, 0, repeat('0', 64));

-- ---------------------------------------------------------------- decision register
CREATE TABLE decisions (
    decision_id           text PRIMARY KEY,
    project_id            text NOT NULL,
    decided_at            timestamptz NOT NULL,
    type                  text NOT NULL,
    decided_by_kind       text NOT NULL CHECK (decided_by_kind IN ('human', 'rule', 'agent')),
    decided_by            text NOT NULL,
    decided_by_role       text,
    card                  jsonb NOT NULL,
    card_hash             text NOT NULL,
    outcome               text NOT NULL,
    comment               text NOT NULL DEFAULT '',
    default_taken         text,
    overrides_decision_id text REFERENCES decisions (decision_id),
    checkpoint_id         text,
    baseline_version      integer,
    CHECK (decided_by_kind <> 'human' OR decided_by_role IS NOT NULL),
    CHECK (outcome <> 'timeout' OR (decided_by_kind = 'rule' AND default_taken IS NOT NULL)),
    CHECK (type <> 'override' OR (overrides_decision_id IS NOT NULL AND comment <> ''))
);
CREATE INDEX decisions_project ON decisions (project_id, decided_at);
CREATE TRIGGER decisions_append_only BEFORE UPDATE OR DELETE ON decisions
    FOR EACH ROW EXECUTE FUNCTION forbid_change();
CREATE TRIGGER decisions_no_truncate BEFORE TRUNCATE ON decisions
    FOR EACH STATEMENT EXECUTE FUNCTION forbid_change();

CREATE TABLE decision_followups (
    decision_id    text NOT NULL REFERENCES decisions (decision_id),
    audit_event_id text NOT NULL,
    PRIMARY KEY (decision_id, audit_event_id)
);
CREATE TRIGGER decision_followups_append_only BEFORE UPDATE OR DELETE ON decision_followups
    FOR EACH ROW EXECUTE FUNCTION forbid_change();
CREATE TRIGGER decision_followups_no_truncate BEFORE TRUNCATE ON decision_followups
    FOR EACH STATEMENT EXECUTE FUNCTION forbid_change();

-- ---------------------------------------------------------------- privileges
-- Least privilege: the application role gets exactly what each store needs.
GRANT SELECT, INSERT, UPDATE ON budget_scopes TO orchestrator_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON budget_reservations TO orchestrator_app;
GRANT SELECT, INSERT, UPDATE ON agent_records TO orchestrator_app;
GRANT SELECT, INSERT ON agent_transitions TO orchestrator_app;
GRANT SELECT, INSERT ON evidence TO orchestrator_app;
GRANT SELECT, INSERT ON audit_events TO orchestrator_app;
GRANT SELECT, UPDATE ON audit_head TO orchestrator_app;
GRANT SELECT, INSERT ON decisions TO orchestrator_app;
GRANT SELECT, INSERT ON decision_followups TO orchestrator_app;
