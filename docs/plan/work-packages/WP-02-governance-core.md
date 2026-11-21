# WP-02: Governance core on PostgreSQL

- **Status:** Not started
- **Depends on:** WP-01

## Goal

The tested reference modules, moved into `src/` with real persistence.

## Read first

- ADR-0003
- ADR-0004
- ADR-0005
- ADR-0007
- docs/architecture/governance-and-security.md
- ADR-0033
- docs/plan/spike-findings.md

## Tasks

1. Copy `contracts`, `messages`, `tool_registry`, `prompt_compiler`, `budget`, `recruiter`, `guardrails`, `resilience` and `skills` from `reference/` into the package layout, with the 52 tests.
2. Rename roles in code and comments to the names in ADR-0007.
3. Implement PostgreSQL versions of the ledger, agent registry, evidence metadata and audit log behind the existing interfaces. The ledger uses row locks; the audit log is append-only and hash-chained.
4. Add migrations.
5. Add property-based tests for the ledger and the lifecycle transition table.
6. Apply ADR-0033 points 4, 6 to 8 and 14. Move `pycryptodome` to the runtime dependencies. Set up the checkpointer with an autocommit connection, as the spike found it needs.

## Acceptance criteria

- [ ] The decision register exists with the fields in `docs/governance/traceability-and-decisions.md`; a timeout is stored as a timeout (tested).
- [ ] Checkpoints use the encrypted serialiser, strict msgpack is on, and pickle fallback is not enabled (tested).
- [ ] No state model has a free-text field: identifiers, statuses and counters only (tested, ADR-0033).
- [ ] Every audit event can store a trace id and span id.
- [ ] The 52 reference tests pass against the in-memory implementations.
- [ ] The same behavioural tests pass against PostgreSQL in CI.
- [ ] Concurrent reservations never overspend a scope (tested).
- [ ] An audit row cannot be updated or deleted by the application role (tested).

## Out of scope

Graph code.
