# Governance and assurance pack

For the functions that must be satisfied before this platform is used: IT security, information
security, architecture, legal, compliance and AI governance. It explains how the LangChain family
of tools is used for traceability, security, guardrails, flows and decision tracking, and what
each function is asked to decide.

| Document | Read it if you are |
| --- | --- |
| [lang-family-controls.md](lang-family-controls.md) | Anyone: what each tool does here, how it is switched on, and what was verified |
| [control-matrix.md](control-matrix.md) | Any function: each control, what provides it, the evidence it leaves, and its status |
| [function-briefs.md](function-briefs.md) | A reviewer from one function: your concerns, what answers them, and what we need from you |
| [traceability-and-decisions.md](traceability-and-decisions.md) | Audit, compliance, AI governance: how one request is followed end to end |

## Three things to know first

1. **Nothing is built yet.** This describes the design and how it will be evidenced. Every control has a status; none is "operating".
2. **The tools help; they are not the control.** LangGraph, LangChain and LangSmith provide mechanisms. The binding controls are platform code and Azure configuration, and the authoritative record is the platform's own audit store (ADR-0001, ADR-0014).
3. **What was checked.** Statements about the tools marked *Verified* were read in the vendor's documentation on 21 November 2026 and are linked. Everything else is marked *To verify* and is confirmed in the architecture spike (WP-01) before anything depends on it. Tools change; re-check before each release.

This pack is written by the architect. It is not legal advice, and it does not state which laws
or regulations apply to you. Those questions are listed for Legal and Compliance to answer.
