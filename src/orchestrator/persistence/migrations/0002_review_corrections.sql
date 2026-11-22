-- 0002: corrections from the architect's review of WP-02 (ADR-0034 points 11 to 13), plus the
-- shared tool-call counters the tool gateway needs (WP-03).

-- ---------------------------------------------------------------- reservations are never deleted
DO $$
DECLARE c record;
BEGIN
    FOR c IN SELECT conname FROM pg_constraint
             WHERE conrelid = 'budget_reservations'::regclass AND contype = 'c'
    LOOP
        EXECUTE format('ALTER TABLE budget_reservations DROP CONSTRAINT %I', c.conname);
    END LOOP;
END
$$;

ALTER TABLE budget_reservations ADD COLUMN released_at timestamptz;
ALTER TABLE budget_reservations
    ADD CONSTRAINT budget_reservations_chain_check CHECK (cardinality(chain) > 0),
    ADD CONSTRAINT budget_reservations_amount_check CHECK (amount >= 0),
    ADD CONSTRAINT budget_reservations_state_check
        CHECK (state IN ('reserved', 'settled', 'released')),
    ADD CONSTRAINT budget_reservations_settled_check
        CHECK ((state = 'settled') = (settled_amount IS NOT NULL)),
    ADD CONSTRAINT budget_reservations_released_check
        CHECK ((state = 'released') = (released_at IS NOT NULL));

CREATE FUNCTION budget_reservation_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.state <> 'reserved' THEN
        RAISE EXCEPTION 'a % reservation cannot change', OLD.state
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF NEW.reservation_id <> OLD.reservation_id OR NEW.chain <> OLD.chain
       OR NEW.amount <> OLD.amount THEN
        RAISE EXCEPTION 'the id, chain and amount of a reservation cannot change'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER budget_reservations_guard BEFORE UPDATE ON budget_reservations
    FOR EACH ROW EXECUTE FUNCTION budget_reservation_guard();
CREATE TRIGGER budget_reservations_no_delete BEFORE DELETE ON budget_reservations
    FOR EACH ROW EXECUTE FUNCTION forbid_change();
CREATE TRIGGER budget_reservations_no_truncate BEFORE TRUNCATE ON budget_reservations
    FOR EACH STATEMENT EXECUTE FUNCTION forbid_change();
REVOKE DELETE ON budget_reservations FROM orchestrator_app;

-- ---------------------------------------------------------------- agent records
CREATE TRIGGER agent_transitions_append_only BEFORE UPDATE OR DELETE ON agent_transitions
    FOR EACH ROW EXECUTE FUNCTION forbid_change();
CREATE TRIGGER agent_transitions_no_truncate BEFORE TRUNCATE ON agent_transitions
    FOR EACH STATEMENT EXECUTE FUNCTION forbid_change();

CREATE FUNCTION agent_record_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.agent_id <> OLD.agent_id OR NEW.project_id <> OLD.project_id
       OR NEW.request_hash <> OLD.request_hash OR NEW.spec IS DISTINCT FROM OLD.spec THEN
        RAISE EXCEPTION 'an agent''s specification and request hash cannot be changed'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER agent_records_guard BEFORE UPDATE ON agent_records
    FOR EACH ROW EXECUTE FUNCTION agent_record_guard();
CREATE TRIGGER agent_records_no_delete BEFORE DELETE ON agent_records
    FOR EACH ROW EXECUTE FUNCTION forbid_change();
CREATE TRIGGER agent_records_no_truncate BEFORE TRUNCATE ON agent_records
    FOR EACH STATEMENT EXECUTE FUNCTION forbid_change();

-- ---------------------------------------------------------------- tool-call counters (WP-03)
-- Shared, so any replica enforces the same call limit.
CREATE TABLE tool_call_counters (
    agent_id  text NOT NULL,
    tool_name text NOT NULL,
    calls     integer NOT NULL CHECK (calls >= 0),
    PRIMARY KEY (agent_id, tool_name)
);
GRANT SELECT, INSERT, UPDATE ON tool_call_counters TO orchestrator_app;
