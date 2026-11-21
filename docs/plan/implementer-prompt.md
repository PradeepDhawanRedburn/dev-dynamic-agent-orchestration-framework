# Prompts for the implementing agent

Paste these into the coding agent on the implementation machine, from the root of the cloned
repository. They contain no architecture; they point the agent at the documents that do.

## 1. First session: orientation and WP-00

```text
You are the implementer for this repository. An architect owns the design; you build it.

Before doing anything else, read these in order and do not skim:
1. AGENTS.md  (the working agreement; it binds you)
2. README.md
3. docs/architecture/overview.md
4. docs/architecture/delivery-lifecycle.md
5. docs/governance/README.md and docs/governance/lang-family-controls.md
6. docs/adr/README.md  (the index; read an ADR in full when a work package lists it)
7. docs/plan/roadmap.md and docs/plan/work-packages/README.md
8. docs/requirements/open-decisions.md and docs/plan/human-actions.md

Then tell me, briefly:
- what you understand the system to be, in five sentences;
- which ADRs are Proposed or Deferred, and which work packages they block;
- which human actions (H-xx) block WP-00 and WP-01;
- anything in the documents that contradicts something else. Do not resolve it; list it.

Then do work package WP-00 only (docs/plan/work-packages/WP-00-bootstrap.md).

Rules for all work, in addition to AGENTS.md:
- Stack: Python, LangGraph, LangChain, langchain-azure-ai, Pydantic, PostgreSQL. Azure and Microsoft Foundry only. Do not add LangSmith Cloud or any service outside Azure.
- Before using any LangGraph, LangChain or Azure API, check it against the documentation for the version you pinned. Do not write a call from memory. If you could not verify a call, say so in the pull request.
- reference/ is read-only and partly out of date. Where it disagrees with docs/, docs/ wins. The lg/ part of it never ran against the real libraries.
- Do not edit docs/adr/, docs/requirements/, docs/architecture/, docs/governance/ (except control-matrix status and files a work package tells you to create) or agents/. If one is wrong or unclear, open an issue with the label AGENTS.md specifies and stop that part of the work.
- Do not start a work package whose "Depends on" is not merged, or that is blocked by a Proposed ADR or an open human action. Tell me instead.
- One work package per branch and pull request, named as AGENTS.md says. List every acceptance criterion in the pull request with how you met it, and what you did not do.
- Never mark something done that you did not run. Report failures plainly.
- No secrets, keys or connection strings in the repository, in prompts, in state or in logs.

Stop after WP-00's pull request is open and report.
```

## 2. The architecture spike (WP-01)

Run this only after WP-00 is merged and Microsoft Foundry is provisioned (action H-14).

```text
Do work package WP-01 (docs/plan/work-packages/WP-01-architecture-spike.md).

This is a spike: its product is knowledge, not production code. For every row in
docs/plan/spike-checklist.md (S-01 onwards):
- write the smallest runnable test that proves or disproves the assumption against the pinned versions;
- record in docs/plan/spike-findings.md: the versions, what you ran, what happened, and pass, fail or could not test;
- if an assumption is false, do not redesign. Record the finding, open an issue labelled spike-finding, and move to the next row.

Also do the measurements listed under "Also in the spike".

If Foundry or any credential is not available, do the rows that need none, mark the rest
"could not test" with the reason, and tell me what you need.

Stop when the findings file is complete and the pull request is open. Do not start WP-02; the
architect must review the findings and amend ADRs first.
```

## 3. Every later work package

Replace NN. Use one session per work package.

```text
Do work package WP-NN (open the matching file in docs/plan/work-packages/).

First:
- confirm its dependencies are merged and nothing it reads is Proposed or blocked by an open human action; if not, stop and tell me;
- read every item under "Read first", and docs/plan/spike-findings.md for anything that changes how it must be built;
- give me a short plan: files you will create, the tests for each acceptance criterion, and any question. Wait for my go-ahead.

Then implement it under the rules in AGENTS.md and the rules I gave you in the first session.

If the work package builds or changes a control, update its row in docs/governance/control-matrix.md
from "designed" to "built", in the same pull request.

Finish with: the pull request, each acceptance criterion and how it is evidenced, what was not
done and why, and any issue you opened.
```

## Notes for the person running these

- WP-00 can start now. WP-01 needs Foundry (H-14). WP-03 needs decisions on ADR-0027 and ADR-0029. WP-05 needs H-06 and H-08.
- After WP-01, bring the findings back to the architect before continuing. Several ADRs rest on unverified library behaviour.
- The prompts assume an agent that can read files, run commands and open pull requests. Adjust the last line of each if yours cannot open pull requests.
