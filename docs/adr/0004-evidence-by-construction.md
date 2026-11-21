# ADR-0004: Evidence by construction

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

Models invent sources. Detecting that afterwards is unreliable.

## Decision

Tools write evidence records at retrieval time and return evidence ids. A specialist may cite ids only. `AgentResult` validation rejects any id the evidence store did not issue for that agent. Material claims without evidence fail validation.

## Consequences

- Invented citations are removed as a failure class.
- Every sentence of a deliverable traces to a tool call.
- Tools must be written to produce evidence records.
