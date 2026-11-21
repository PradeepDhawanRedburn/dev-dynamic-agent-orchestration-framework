# ADR-0029: How the LangChain family of tools is used

- **Status:** Proposed; points 3 and 6 amended by [ADR-0033](0033-decisions-from-the-architecture-spike.md) after the spike
- **Date:** 2026-11-21

## Context

The owner asked that the project use and enable the LangChain family for traceability, security,
guardrails, flows and decision tracking, documented for IT security, information security,
architecture, legal, compliance and AI governance. ADR-0014 keeps everything inside Azure.
LangSmith Cloud has no Azure or UK region; self-hosting is an Enterprise add-on.

## Decision

1. **LangGraph and LangChain are used fully,** as open-source libraries inside the platform: graphs, the PostgreSQL checkpointer, interrupts for human gates, and LangChain middleware for limits, retries and redaction.
2. **A fixed middleware allow-list and deny-list** apply to every specialist, as listed in `docs/governance/lang-family-controls.md`, and are tested.
3. **Tracing is OpenTelemetry into Application Insights.** No component may depend on LangSmith being present.
4. **LangSmith is not adopted yet.** Self-hosted LangSmith is evaluated during the proof of concept if a licence can be obtained. LangSmith Cloud is not used.
5. **The tools are mechanisms, not the control.** The audit store and decision register remain the record; platform code and Azure configuration remain the binding controls.
6. **Checkpoint encryption is on,** and pickle fallback in serialisation is never enabled.
7. **Flow diagrams are generated from the compiled graphs in CI,** if the spike confirms the export works.
8. **`docs/governance/` is maintained with the design.** A change to a control updates the control matrix in the same pull request.

## Consequences

- Without LangSmith, evaluation and human review tooling must come from Foundry or be built. WP-10 carries that.
- Points 2, 6 and 7 add tests and spike items.
- The `langsmith` client library is installed regardless, as a dependency of `langchain` (found in WP-00). It must stay unconfigured: no tracing or endpoint variables, verified by a test, and its hosts are not on the egress allow-list. Spike item S-24 confirms it is silent by default.
- Six functions have named actions (H-17 to H-21, and earlier ones).

## Alternatives considered

- LangSmith Cloud in the EU region: rejected; data would leave Azure, contrary to ADR-0014.
- Self-hosted LangSmith from the start: deferred; licence, cost and four more services before any value is shown.
- Avoid LangChain middleware and write every limit in platform code: rejected; the limits exist, are documented, and the platform's own budget ledger still sits above them.
