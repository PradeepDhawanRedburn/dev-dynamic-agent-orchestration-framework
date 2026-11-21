# Requirements

Source: the repository owner's brief and design reviews of 21 November 2026. Each requirement has
an id that ADRs and work packages cite.

## Goal

A production-grade platform that takes any complex technology requirement, breaks it
into workstreams, staffs each with temporary specialist agents, validates and consolidates their
work, and returns an evidence-backed result to a human, under enforced limits on cost, access and
autonomy.

## Functional requirements

| Id | Requirement |
| --- | --- |
| F-01 | A small permanent organisation of agents receives, plans, staffs, checks and consolidates each assignment |
| F-02 | Specialist agents are created at runtime for one task and retired afterwards. No specialist agent exists before it is requested |
| F-03 | Only a Lead may request a specialist. Only the Recruiter may create one. A specialist cannot create or contact another agent |
| F-04 | Every specialist has: one accountable Lead, a bounded task, a validated system prompt, an approved model, an allow-listed toolset, a private memory namespace, limits on tokens, cost, time and retries, and a retirement policy |
| F-05 | Only the Leads relevant to an assignment are invoked |
| F-06 | Every material claim in any result cites evidence that the platform itself captured |
| F-07 | Specialist output is tested against its acceptance criteria before the Lead may accept it |
| F-08 | The consolidated answer receives an independent challenge before it reaches a human |
| F-09 | A product owner role frames the problem, clarifies with the human before planning, and checks the result against the need |
| F-10 | Specialists can be given governed expertise for a technology. First set: Azure, Terraform, Argo CD, GitHub Actions |
| F-11 | Every agent diagnoses and fixes routine faults (network loss, timeouts, throttling, expired credentials) by approved steps, and asks a human when those are exhausted |
| F-12 | Humans interact through one front door: clarify, decide, be informed, steer or stop |
| F-13 | The organisation reuses prior answers and records lessons after each assignment |
| F-15 | A solution architect role drafts one design across workstreams before the Leads plan, and checks the result against it (ADR-0026) |
| F-16 | A permanent AI adviser role advises on the AI parts of an assignment (ADR-0026) |
| F-17 | Every assignment passes ideation, refinement, clarification and consultation, and a human approves the requirement, before any planning, design or build starts (ADR-0028) |
| F-18 | A change to an approved requirement is a recorded change request that a human approves, producing a new version |
| F-19 | Any agent can leave a question for a person. Only work that depends on the answer waits; other work, including the same agent's, continues (ADR-0031) |
| F-20 | A person is given options, may answer in their own words, and may override an agent's outcome with a recorded reason (ADR-0032) |
| F-14 | Outputs other than text (code, diagrams, files) are recorded as artefacts with provenance |

## Control requirements

| Id | Requirement |
| --- | --- |
| C-01 | Routing, permissions, budgets, approvals, retries and lifecycle are deterministic code. Models are used only for interpretation, planning, research, synthesis and judgement |
| C-02 | No agent can change anything outside the platform. Proposed changes reach the estate as pull requests that people merge |
| C-03 | Humans hold every binding decision: plan approval, budget or deadline overrun, merging any pull request, any other proposed change, resuming or terminating a suspended agent, and final acceptance. The platform may open a pull request without asking first (ADR-0021) |
| C-04 | Every agent and tool action is recorded in an audit store that does not depend on the tracing tool |
| C-05 | Budgets are enforced before, during and after work. A task cannot overspend its workstream or project |
| C-06 | An agent behaving outside what was approved is suspended automatically. Suspension is reversible; only a human resumes or terminates |
| C-07 | A project can be cancelled at any time, with every temporary permission revoked at once |
| C-08 | Retrieval and deliverables respect the access rights of the human who made the request |
| C-09 | Agent creation never generates or executes source code. Agents are assembled from registered, reviewed parts |
| C-10 | No function checks its own work |

## Platform constraints

| Id | Constraint |
| --- | --- |
| P-01 | Azure only. Nothing runs or is stored outside the tenant |
| P-02 | Models and tracing come from Microsoft Foundry |
| P-03 | Orchestration uses LangGraph; agent components use LangChain; contracts use Pydantic; implementation is Python |
| P-04 | Platform delivery toolchain: Terraform, GitHub Actions, Argo CD |
| P-05 | LangSmith is optional and, if used, self-hosted in the tenant |

## Out of scope

- Business assignments, for now (ADR-0022). Technology assignments only.
- Applying any change to an environment, protected branch or system of record.
- Decisions about individual people or customers.
- Advice the firm treats as regulated, without a qualified human author.
- Data classed Restricted.
- Anything the requesting human could not see or do themselves.

## Quality attributes

Lean (cost proportional to the size of the assignment), observable, auditable, resilient to
failure, horizontally scalable, and reusable across unrelated assignments without changing the
permanent organisation.

## Not yet done

The design has not been mapped to the firm's model-risk, outsourcing, records or
operational-resilience policies. That mapping is part of [WP-01](../plan/work-packages/WP-01-architecture-spike.md).
