# WP-09: Interaction layer, first version

- **Status:** Not started
- **Depends on:** WP-05

## Goal

People clarify, decide, ask and steer through one API and a minimal page.

## Read first

- ADR-0008
- ADR-0016
- docs/architecture/interaction-layer.md

## Tasks

1. Implement the decision card with its seven fields.
2. Implement an API to list pending decisions, answer one, ask for status, and request a change or a stop.
3. Verify the approver's Entra identity and role before resuming a run.
4. Schedule a deadline for each gate and apply the safe default.
5. Answer status and 'why' questions from the audit record and the ledger.

## Acceptance criteria

- [ ] Every gate in the runtime design is answerable through the API.
- [ ] An answer from someone without the role is refused and audited (tested).
- [ ] A scope change re-plans only the affected workstream (tested).

## Out of scope

The Teams bot.
