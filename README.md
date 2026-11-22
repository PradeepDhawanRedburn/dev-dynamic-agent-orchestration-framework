# Dynamic Agent Orchestration Framework

A governed platform in which a small permanent organisation of AI agents takes a technology
requirement, creates temporary specialist agents to do the work, checks and
consolidates what they produce, and hands a human an evidence-backed result.

This repository is the working record between the **architect** and the **implementers**.
Requirements, architecture, decisions and the plan live here. Implementation is done on another
machine and arrives as pull requests.

## For IT security, information security, architecture, legal, compliance and AI governance

Start at [docs/governance/README.md](docs/governance/README.md).

## Lifecycle

Request, ideation, refinement, clarification, consultation, requirement approval, then plan,
design, build, test, review and acceptance. See
[docs/architecture/delivery-lifecycle.md](docs/architecture/delivery-lifecycle.md).

## Status (21 November 2026)

| Area | State |
| --- | --- |
| Requirements and architecture | Approved through design Revision 2, plus the decisions recorded in the ADRs |
| Open decisions | One deferred, three proposed; see [docs/requirements/open-decisions.md](docs/requirements/open-decisions.md) |
| Implementer prompts | [docs/plan/implementer-prompt.md](docs/plan/implementer-prompt.md) |
| Needed from people | Twenty-six actions; see [docs/plan/human-actions.md](docs/plan/human-actions.md) |
| Governance core (`reference/`) | Written and tested: 52 passing tests on Python 3.13, Pydantic 2 |
| LangGraph, LangChain and Foundry code (`reference/lg/`) | Draft. Never run against the real libraries. See the spike checklist |
| Permanent agents' prompts (`agents/`) | First drafts for all twelve roles. Structure checked; not yet run against a model |
| Production code (`src/`) | Not started. Begins with work package WP-00 |

**Nothing in this repository has yet run on real LangGraph.** The first implementation task is
the architecture spike, [WP-01](docs/plan/work-packages/WP-01-architecture-spike.md).

## Where things are

| You want | Go to |
| --- | --- |
| What we are building and why | [docs/requirements/requirements.md](docs/requirements/requirements.md) |
| How it is designed | [docs/architecture/overview.md](docs/architecture/overview.md) |
| Diagrams | [docs/architecture/diagrams/](docs/architecture/diagrams/README.md) |
| The system prompt and definition of each permanent agent | [agents/](agents/README.md) |
| Why a decision was made | [docs/adr/](docs/adr/README.md) |
| What to build next | [docs/plan/roadmap.md](docs/plan/roadmap.md) and [docs/plan/work-packages/](docs/plan/work-packages/README.md) |
| How to work in this repository | [AGENTS.md](AGENTS.md) |
| Tested starting code | [reference/](reference/README.md) |

## How we work

1. **Requirement.** A need is written into `docs/requirements/` with an id.
2. **Decision.** Anything architectural is decided in an ADR. An ADR is Proposed until the
   repository owner accepts it.
3. **Plan.** Accepted decisions become work packages with acceptance criteria.
4. **Implementation.** An implementer takes one work package, builds it on a branch and opens a
   pull request that cites the work package and the ADRs it follows.
5. **Feedback.** Anything the implementer finds that contradicts an ADR is raised as an issue
   labelled `architecture-question`. The architect answers by amending or superseding the ADR,
   never by a side conversation.

The architect does not write production code. The implementer does not change architecture.

## Development setup

Python 3.13 and [uv](https://docs.astral.sh/uv/). Dependencies are pinned in `pyproject.toml` and locked in `uv.lock`.

```bash
uv sync --locked                 # create .venv from the lock file
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy
uv run pytest --ignore=tests/spike   # unit and integration tests; the integration tests need Docker
python3 scripts/check_agents.py
uv run pytest tests/spike        # architecture spike; needs Docker for PostgreSQL
```

The application needs a PostgreSQL on every developer machine, not only for tests. Start one with a single
command (needs Docker; production uses Azure Database for PostgreSQL):

```bash
python scripts/dev_db.py up      # creates a git-ignored .env with a random password, starts PostgreSQL, waits until healthy
python scripts/dev_db.py down    # stop, keep the data
python scripts/dev_db.py reset   # stop and delete the data
```

It listens on `127.0.0.1:5432` only (change `POSTGRES_PORT` in `.env` if the port is taken). The application reads
`DATABASE_URL` from `.env`; `.env.example` shows the variables and `.env` is never committed. Put your Foundry settings
(`AZURE_OPENAI_*`, `AZURE_MODEL_*`) in the same `.env`; the spike tests read the `AZURE_*` ones from it.

The tests start their own throwaway PostgreSQL container by default. To run them on the local database
instead, set `TEST_POSTGRES_DSN` to the value of `DATABASE_URL`; every test creates its own database on it and drops it afterwards. The integration tests (`tests/integration`) use the same setting. Tests marked `foundry`
are skipped, with the reason shown, unless `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_API_KEY` are set in your
shell; never put them in a file in the repository. No LangSmith or LangChain tracing variable may be set.

Behind a TLS-inspecting proxy, pass `--native-tls` to uv (or set `UV_NATIVE_TLS=1`) so it trusts the
operating system's certificate store. After changing `uv.lock`, regenerate the licence list on Linux (CI
checks it is current): `uv run --locked python scripts/generate_dependency_licences.py`.

## The design in one paragraph

One fixed LangGraph supervisor graph runs twelve permanent roles grouped into five functions:
Define, Deliver, Assure, Control and Learn. Specialists are not code. Each is a validated
specification, optionally carrying skill packs such as Terraform or Argo CD, run by one shared
worker and retired after its task. Every claim must cite evidence issued by the tool gateway.
Budgets are reserved before work starts. No agent holds a tool that can change anything: changes
reach your estate as pull requests that people review and merge. Humans decide at defined gates through one
interaction layer. The platform runs only on Azure, with models and tracing from Microsoft Foundry.
