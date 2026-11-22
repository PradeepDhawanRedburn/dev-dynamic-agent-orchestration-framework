# ADR-0034: Store access from async nodes, and what the audit record proves

- **Status:** Accepted
- **Date:** 2026-11-22

## Context

WP-02 built the governance stores on PostgreSQL and raised three questions (issues 12, 13, 14),
and the architect's review found two points in the reference design worth correcting.

## Decision

**Store access (issue 13)**

1. The stores stay synchronous. One async facade wraps them and owns the hand-off to a worker thread. Graph nodes and middleware use the facade only.
2. A test fails if a module under the graph package imports a synchronous store directly.
3. The connection pool is sized to the number of worker threads, and both are configuration.

**State models (issue 12)**

4. The free-text rule and its test are accepted as built. Every graph state model is registered with it; this becomes an acceptance criterion of WP-04 and WP-05. A work package that adds a state model without registering it does not pass review.

**What the audit record proves (issue 14)**

5. The record proves: no stored event or decision has been changed, removed or reordered since it was written, provided the chain verifies against an anchor held outside the database.
6. It does not prove that every event is true. A compromised governance service could append a false event with a valid hash. This is stated in the governance pack and is a residual risk.
7. The chain head (last sequence number and hash) is exported to immutable Blob Storage on a schedule and when a project closes. Verification compares the chain with the latest anchor, so removing the tail of the log together with the head is detected.
8. The database owner and the application use separate credentials. Migrations run under the owner identity in the deployment pipeline. The running application never holds rights to alter a table or a trigger.
9. Only governance services hold the role that can append to the audit log and the decision register. The specialist worker does not.
10. Chain verification runs on a schedule and raises an incident on failure.

**Corrections to the reference design**

11. A released budget reservation is kept with the state `released`; it is not deleted. The application role loses DELETE on reservations. The ledger is a financial record.
12. Agent transitions are append-only, and an agent's specification and request hash cannot be changed after the record is created. Both are enforced by the database.
13. A change to a budget limit is written to the audit log with who changed it.

## Consequences

- Items 11 to 13 are a second migration, done at the start of WP-03.
- Items 7, 8 and 10 are WP-12. Until then the limits in item 6 and issue 14 apply to any environment.
- The facade is built in WP-03, before the first async caller.
- The decision card needs two more fields before WP-09: what waiting costs, and for a question why it matters and its kind. The card is stored as JSON, so no migration is needed.

## Alternatives considered

- Async stores throughout: rejected; it doubles the stores and their tests for no gain over one facade.
- Signing each audit event with a key the application cannot read: deferred; the external anchor addresses removal, and a signing service is a larger change. Revisit after the security review (action H-20).
