# Working in this repository

These rules apply to every implementer, human or coding agent.

## Before you write code

1. Read [docs/architecture/overview.md](docs/architecture/overview.md) once.
2. Open the work package you were given in `docs/plan/work-packages/`.
3. Read every ADR that the work package lists under "Read first".
4. Check the work package's dependencies are merged.

## Rules

- **One work package per pull request.** Name the branch `wp-NN-short-name`.
- **Follow the ADRs.** If an ADR looks wrong or cannot be implemented as written, stop and open
  an issue labelled `architecture-question`. Do not work around it and do not edit an Accepted ADR.
- **`reference/` is read-only.** Copy from it into `src/`; never import from it and never edit it.
  It records what the architect tested.
- **Production code lives in `src/orchestrator/`**, tests in `tests/`, using the layout in
  [docs/architecture/overview.md](docs/architecture/overview.md#repository-layout).
- **No model in a control decision.** Routing, permissions, budgets, approvals, retries and
  lifecycle moves are code. A model returns a draft in a narrow schema; code decides what follows.
- **No generated code at runtime.** Specialists are built from specifications and registered
  parts. No `eval`, no dynamic import, no runtime-created graph nodes.
- **No consequential tool for an agent.** A tool that changes anything outside the platform is
  never granted to an agent. See ADR-0006.
- **Every side effect is idempotent.** Nodes can be retried and are re-run from the top when an
  interrupt resumes.
- **Prompts live in `agents/`,** not in code. Change one by pull request, bump its version and run `python3 scripts/check_agents.py` (ADR-0025).
- **Controls are documented.** A change that adds, removes or alters a control updates `docs/governance/control-matrix.md` in the same pull request.
- **Middleware is a fixed list.** Use only what `docs/governance/lang-family-controls.md` allows; never the ones it forbids.
- **No secrets in the repository,** in prompts, in graph state or in traces.

## Definition of done for a pull request

- Every acceptance criterion in the work package is met and listed in the pull request description.
- Unit tests pass, and the 52 reference tests still pass against the copied modules.
- New behaviour has tests. Deterministic code is tested without a model.
- Anything the work package asked you to verify against a real library has a recorded result in
  `docs/plan/spike-findings.md`.
- Public functions and Pydantic models have type hints. `ruff` and `mypy` pass.
- The pull request says what was not done and why.

## Reporting back to the architect

Use issues, with one of these labels:

| Label | Use it when |
| --- | --- |
| `architecture-question` | An ADR is unclear, contradictory or cannot be implemented |
| `spike-finding` | A library behaves differently from an assumption in the spike checklist |
| `scope-question` | A work package is ambiguous or too large |
| `risk` | You found a security, cost or reliability risk the documents do not mention |

State what you observed, the library versions, and a minimal reproduction. Do not propose a new
architecture in the issue; describe the problem and the options you see.

## Honesty rules

- Do not mark something done that you have not run.
- Do not invent library behaviour. If you have not verified a call against the installed version,
  say so in the pull request.
- Report failures and skipped steps plainly.
