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

## Tasks

1. Copy `contracts`, `messages`, `tool_registry`, `prompt_compiler`, `budget`, `recruiter`, `guardrails`, `resilience` and `skills` from `reference/` into the package layout, with the 52 tests.
2. Rename roles in code and comments to the names in ADR-0007.
3. Implement PostgreSQL versions of the ledger, agent registry, evidence metadata and audit log behind the existing interfaces. The ledger uses row locks; the audit log is append-only and hash-chained.
4. Add migrations.
5. Add property-based tests for the ledger and the lifecycle transition table.

## Acceptance criteria

- [ ] The 52 reference tests pass against the in-memory implementations.
- [ ] The same behavioural tests pass against PostgreSQL in CI.
- [ ] Concurrent reservations never overspend a scope (tested).
- [ ] An audit row cannot be updated or deleted by the application role (tested).

## Out of scope

Graph code.
