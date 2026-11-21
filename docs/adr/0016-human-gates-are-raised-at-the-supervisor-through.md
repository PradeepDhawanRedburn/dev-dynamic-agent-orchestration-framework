# ADR-0016: Human gates are raised at the supervisor through one interaction layer

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

The earlier draft paused inside parallel subgraph branches, which is the LangGraph behaviour the architect is least sure of, and the only human interface was a web form.

## Decision

Subgraphs return `decision_needed` to the supervisor, which raises one interrupt and presents a standard decision card. People interact in four ways: clarify, decide, inform, steer or stop. Approvers are verified by Entra identity. Every gate has a deadline and a safe default; a timeout never means approved.

## Consequences

- One decision queue per project.
- Removes the riskiest unverified LangGraph assumption.
- The reference draft still pauses inside the Lead subgraph; WP-05 and WP-06 change it.
