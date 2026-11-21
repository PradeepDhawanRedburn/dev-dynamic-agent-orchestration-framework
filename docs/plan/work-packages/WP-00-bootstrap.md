# WP-00: Bootstrap the implementation project

- **Status:** In review; architect approved pull request 1 on 21 November 2026. Python 3.13 only was accepted in place of 3.12 or later
- **Depends on:** None

## Goal

A Python project that builds, lints and tests in CI, so every later work package has somewhere to land.

## Read first

- AGENTS.md
- ADR-0020

## Tasks

1. Create `pyproject.toml` for Python 3.12 or later with pinned dependencies: pydantic, langgraph, langchain, langchain-azure-ai, pytest, ruff, mypy. Record the exact versions resolved.
2. Create `src/orchestrator/` and `tests/` using the layout in the architecture overview.
3. Add a GitHub Actions workflow that runs ruff, mypy, pytest and `python3 scripts/check_agents.py` on every pull request. Pin third-party actions to a commit SHA and grant least token permissions.
4. Add the issue labels named in AGENTS.md.
5. Generate a list of every resolved dependency with its licence, and commit it as `docs/governance/dependency-licences.md` for Legal.

## Acceptance criteria

- [ ] CI is green on an empty test suite.
- [ ] `scripts/check_agents.py` runs in CI and passes.
- [ ] Resolved dependency versions are committed in a lock file.

## Out of scope

Any application code.
