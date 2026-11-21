# Reference code

Code the architect wrote and tested while designing the platform. **Read-only.** Copy from it
into `src/`; do not import from it or edit it.

## What is tested

Pure Python and Pydantic. No LangGraph, LangChain or Azure packages needed.

```bash
cd reference && python3 -m pytest -q        # 52 passed on Python 3.13, Pydantic 2.13
```

| Module | What it is |
| --- | --- |
| `contracts.py` | Every Pydantic contract and the agent lifecycle transition table |
| `messages.py` | The typed message envelope |
| `tool_registry.py` | Tool definitions and least-privilege grants |
| `prompt_compiler.py` | System-prompt compiler for temporary specialists |
| `budget.py` | Budget ledger with reservations (in-memory) |
| `recruiter.py` | Provision, suspend, resume and retire specialists (in-memory stores) |
| `guardrails.py` | Guardrail rule engine |
| `resilience.py` | Self-healing runbooks |
| `skills.py` | Skill packs, including four illustrative DevOps packs |
| `test_*.py` | The tests |

## What is only a draft

`lg/` holds the LangGraph and LangChain code. **It has never run against the real libraries.**

| File | What it is |
| --- | --- |
| `lg/state.py`, `lg/worker.py`, `lg/lead.py`, `lg/supervisor.py` | Graph state, worker and tool gateway, Lead subgraph, supervisor |
| `lg/app.py` | **Deleted.** It created a LangSmith client when imported, which makes a network call (issue 8, ADR-0033). The composition root is written in WP-05 from the ADRs |
| `lg/stubs/` | A minimal stand-in for LangGraph and LangChain. It is not those libraries and proves nothing about them |
| `lg/dryrun.py` | Runs the node logic end to end through the stand-in with scripted models |

```bash
cd reference/lg && python3 dryrun.py
```

The dry run shows the node logic and routing are coherent. It found and fixed four defects during
design. Expect the real libraries to reveal more; that is what WP-01 is for.

## Where the draft lags the approved design

- Role names: uses Head of Development and Project Manager, not Head of Delivery and Delivery Controller.
- Organisation: implements the Revision 1 shape (Tester and Guardrail judgement per Lead), not the ten roles of ADR-0007. No Product Manager, Knowledge Steward or permanent Reviewer.
- Human gates: the guardrail gate pauses inside the Lead subgraph; ADR-0016 moves it to the supervisor.
- Tester: tests after the work only; ADR-0012 adds checks first.
- State: carries full results; ADR-0018 requires references.
- Permanent agents' prompts: placeholders passed in by the harness; the real ones are in `agents/`.
- No tiers, interaction layer, requester access filtering or artefact contract.
