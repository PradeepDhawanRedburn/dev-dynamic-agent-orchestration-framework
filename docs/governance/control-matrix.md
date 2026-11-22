# Control matrix

Each control, what provides it, the evidence it leaves, and where it is built. **Status of every
row: designed, not built, except the rows listed under "Built so far" below.** A row becomes
"built" when its work package is merged with passing tests, and "operating" only after your own
assurance testing.

Functions: IT sec, InfoSec, Arch (architecture), Legal, Compliance, AI gov (AI governance).

| Area | Concern | Control | Provided by | Evidence | Built in | Of interest to |
| --- | --- | --- | --- | --- | --- | --- |
| Flow | A model cannot alter the workflow | Graph compiled from code; agents are data | Platform design; LangGraph | Graph version on every run; generated diagram | WP-04, WP-05 | Arch, AI gov |
| Flow | Requirement approved before any work | Discovery stage; baseline required by the Recruiter | Platform code | Decision register; refused requests in audit | WP-05 | Compliance, AI gov |
| Decisions | Humans hold binding decisions | Gates raised as interrupts; identity verified before resume | LangGraph interrupt; interaction API; Entra ID | Decision register | WP-05, WP-09 | Compliance, AI gov |
| Decisions | Agents ask instead of guessing; silence is never an answer | Question queue; provisional marking; gap on expiry | Platform code (ADR-0031) | Question store; decision register | WP-14 | AI gov, Compliance |
| Decisions | A person can overrule an agent, visibly | Override with role check and mandatory reason; fixed list of what cannot be overridden | Platform code (ADR-0032) | Decision register; overrides listed on the deliverable | WP-14 | Compliance, AI gov, InfoSec |
| Decisions | A timeout is never an approval | Safe default per gate | Platform code | Decision register | WP-05 | Compliance |
| Traceability | Every action attributable | Append-only, hash-chained audit | Platform code; PostgreSQL | Audit store; chain verification | WP-02 | InfoSec, Compliance |
| Traceability | Every claim backed by a captured source | Evidence ids issued only by the gateway | Platform code | Evidence store | WP-02, WP-03 | AI gov, Legal |
| Traceability | Runs can be diagnosed | Traces with common identifiers | LangChain run trees; Foundry tracer; Application Insights | Traces | WP-10 | Arch, IT sec |
| Security | Agents cannot change the estate | No consequential tool; pull requests only | Platform design; GitHub branch protection | Tool registry tests; repository settings | WP-03, WP-08 | IT sec, InfoSec |
| Security | Least privilege per agent | Grants per task; scoped short-lived tokens | Tool gateway | Permission decisions in audit | WP-03 | InfoSec |
| Security | Data stays in the tenant | Azure only; private endpoints; egress proxy | Azure configuration | Terraform; network policy tests | WP-12 | IT sec, Legal |
| Security | State and evidence protected at rest | Disk encryption; optional checkpoint encryption | Azure; LangGraph encrypted serialiser | Configuration | WP-02, WP-12 | InfoSec |
| Security | Sensitive content not in traces | Hide or mask by classification | Tracer settings or collector | Trace scan test | WP-10 | InfoSec, Legal |
| Security | Retrieval respects the person's access | Access check on every read | Platform code (ADR-0024) | Permission decisions | After proof of concept | InfoSec, Legal |
| Guardrails | An agent acting outside its task is stopped | Rule engine; suspension; human resumes | Platform code; Guardrail Manager | Guardrail events; decision register | WP-06 | InfoSec, AI gov |
| Guardrails | Runaway cost or loops | Budget ledger; call limits | Platform code; LangChain limit middleware | Ledger; limit events | WP-02, WP-03 | Arch |
| Guardrails | Prompt injection through content | Content treated as data; grants limit damage; injection rule; provider detection | Prompts; gateway; Foundry filters | Adversarial test set results | WP-06, WP-10 | InfoSec, AI gov |
| Guardrails | Personal data handling | PII middleware; classification; redaction | LangChain `PIIMiddleware`; platform code | Tests; trace scan | WP-03, WP-10 | Legal, Compliance |
| Quality | Output is tested before acceptance | Tester checks written first; evidence gate | Platform code; Tester | Test reports | WP-04 | AI gov |
| Quality | Independent challenge | Reviewer on a different model deployment | Platform code; Foundry | Review findings; deployment ids | WP-11 | AI gov |
| Quality | Changes to prompts or models are measured | Evaluation gate in CI; versions pinned per run | CI; evaluation tooling | Evaluation results; prompt hashes | WP-10 | AI gov, Compliance |
| Change | Prompts, skills, rules change only by review | Versioned files; pull requests | GitHub | Pull request history | WP-00 | Arch, Compliance |
| Resilience | Faults handled without improvisation | Approved runbooks, then a person | Platform code (ADR-0015) | Incident events | WP-07 | IT sec |
| Stop | Everything can be halted | Kill switch; cancellation; credential freeze | Platform code | Audit | WP-06 | InfoSec, AI gov |

## Built so far

Updated by each work package. "Built" means the code exists and its tests pass; none is
"operating".

| Control | Status | What exists | Tests |
| --- | --- | --- | --- |
| Every action attributable: append-only, hash-chained audit | Built in WP-02 (store only; nothing writes to it yet) | PostgreSQL audit log; each event stores the trace id and span id current when written; the application role has INSERT and SELECT only, and triggers refuse UPDATE, DELETE and TRUNCATE for every role; `verify_chain` | `tests/integration/test_audit.py`, `test_postgres_guarantees.py`, `tests/unit/test_properties.py` |
| Every claim backed by a captured source: evidence ids issued only by the gateway | Built in WP-02 (store) and WP-03 (gateway) | Immutable evidence metadata; the gateway stores each item an evidence tool returns under an id derived from the call, so a repeated call gives the same id; the worker builds an `AgentResult` from the evidence issued to that agent and refuses a result citing any other id | `tests/integration/test_evidence.py`, `tests/unit/test_gateway.py`, `tests/unit/test_worker.py` |
| State protected at rest: encrypted checkpoint serialiser | Built in WP-02 (serialiser); Azure configuration is WP-12 | AES serialiser, strict msgpack, no pickle fallback, autocommit connection, key from `LANGGRAPH_AES_KEY` | `tests/integration/test_checkpointer.py` |
| State holds identifiers, statuses and counters only | Rule and test built in WP-02; no graph state model exists yet to apply it to (WP-05) | `free_text_fields` and `@state_model` | `tests/unit/test_state_policy.py` |
| Runaway cost: budget ledger with reservations | Built in WP-02 (ledger) and WP-03 (metering, limits) | Row-locked PostgreSQL ledger; concurrent reservations never overspend; settlement idempotent; a released reservation stays readable and cannot be settled (migration 0002); every model call is metered from the provider's token counts and priced from the catalogue; the run stops before the next model call when the token or cost budget is spent; call limits from LangChain's limit middleware | `tests/integration/test_ledger.py`, `test_migration_0002.py`, `test_postgres_guarantees.py`, `test_properties_postgres.py`, `tests/unit/test_worker.py`, `tests/unit/test_middleware.py` |
| Every budget limit change is attributable | Built in WP-03 | `open_scope` writes `budget.scope_opened` or `budget.limit_changed` naming who made the change, with the old and new limit, in the same transaction as the change | `tests/integration/test_ledger.py` |
| The ledger and the agent record cannot be quietly rewritten | Built in WP-03 (migration 0002) | Reservations and agent transitions are append-only; an agent's specification and request hash cannot be updated; the application role cannot delete reservations | `tests/integration/test_migration_0002.py` |
| Graph code cannot block the event loop on the database | Built in WP-03 (ADR-0034) | Async facade over the stores on a fixed thread pool, carrying the trace context; a test fails if a module under `orchestrator.graph` imports a synchronous store | `tests/integration/test_facade.py` |
| Least privilege per agent: tool grants checked by the gateway | Built in WP-03 (gateway); the real tools are WP-04 onwards | Every call passes the gateway: kill switch, agent status (suspended, retired or finished agents are stopped), grant, shared call counter (a refused call still counts), argument schema, self-healing, clearance, evidence, audit; every refusal is an audit event | `tests/unit/test_gateway.py` |
| Agents cannot change the estate: no consequential tool | Gateway refusal built in WP-03; repository settings are WP-08 | The gateway refuses a consequential tool even if one were granted | `tests/unit/test_gateway.py` |
| Limits, retries and error handling are the fixed middleware list | Built in WP-03 | A built specialist contains only allow-listed middleware classes, checked by class name, in the ADR-0033 order; the check runs on every build; a content-filter block is never retried and ends the task with a guardrail event; tool failures become content naming the exception type only, except a stop ordered by governance code (`AgentStopped`), which is never turned into content and ends the run; the registry status is re-read before every model call, so a suspended or retired agent sends no further prompt; any exception nobody planned for ends in outcome `failed` (type name only) with a `worker.unhandled_failure` event, and the spend is settled in a `finally`; structured-output validation errors are counted by our code | `tests/unit/test_middleware.py`, `tests/unit/test_worker.py` |
| Personal data handling: PII at the result boundary and in free-text replies | Built in WP-03 (ADR-0035) **for three kinds only**: email address, payment card number (Luhn checked, 16 digits) and IPv4 address | A deterministic step redacts every free-text field of a specialist's validated result before it becomes an `AgentResult`; identifier fields are never altered; each redaction writes `guardrail.pii_redacted` with counts per kind and field names, never a value; a redaction that breaks the schema fails the task closed. `PIIMiddleware` (redact, input off, output on, tool results off, each stated explicitly) still covers free-text replies. Detectors are the library's own `detect_email`, `detect_credit_card` and `detect_ip` | `tests/unit/test_pii_boundary.py`, `tests/unit/test_middleware.py` |
| Models are approved and carry their own settings | Built in WP-03 (provisional entries; the approved list is H-03, H-14) | Model catalogue in `policy/model_catalogue.yaml`: deployment, API to use, API version, reasoning effort, highest data classification, cost band, status; a model is refused data above its classification; the API and effort of every call come from the entry | `tests/unit/test_model_catalogue.py`, `tests/integration/test_worker_foundry.py` |
| Prompts come from `agents/` and are hashed | Built in WP-03 | The loader assembles each permanent agent's prompt, skips skills marked `needs-content` and records the skip, and hashes the result; golden files for all twelve roles and five profiles show every change in a pull request. Both loaders (this one and the compiler) read the directory named by `ORCHESTRATOR_AGENTS_DIR`, and a missing directory stops the process at startup with a message naming the variable and the path (ADR-0035) | `tests/golden/test_agent_prompts.py`, `tests/unit/test_agents_location.py` |
| Committed text files are UTF-8, no byte-order mark, LF | Built in WP-03 | `scripts/check_text_files.py` reads the committed files, not the working copy, and runs in CI. A tool that adds a BOM or CRLF would change the bytes of a prompt, a migration or a golden file, and with them a hash | `tests/unit/test_text_files.py` |
| No code constructs a LangSmith client | Built in WP-03 | A source-reading test fails on any LangSmith import, tracer, client or tracing variable under `src/` | `tests/security/test_no_langsmith.py` |
| A timeout is never an approval | Register rule built in WP-02; the gates that use it are WP-05 | Decision register: a timeout is stored as a timeout with the default taken, by a rule; an agent's recommendation is never a decision; an override is its own row with a reason; the database repeats these as CHECK constraints | `tests/integration/test_decisions.py` |

## Known gaps

Stated so that no reviewer has to find them.

| Gap | Why it exists | Position |
| --- | --- | --- |
| No model-based watcher over the permanent agents | Owner's decision (ADR-0010) | Rule engine and the security owner cover them; revisit after the proof of concept |
| Pull requests are opened without prior approval | Owner's decision (ADR-0021) | Six mandatory conditions; the security owner should review before any repository is allow-listed |
| The LangSmith client library is present although LangSmith is not adopted | It is a dependency of LangChain | Tested in WP-01: silent when unconfigured, except that constructing its client or using its test marker calls out. Both are banned by tests; its hosts are blocked at the egress proxy (WP-12) |
| Checkpoint encryption does not cover simple values held directly in state | Library behaviour, found in WP-01 | State holds identifiers and statuses only, enforced by a test; database encryption covers the rest (ADR-0033) |
| Trace content is recorded fully or not at all | Tracer behaviour, found in WP-01 | Off by default; on per run by classification; masking later in the collector (H-19) |
| The PostgreSQL driver is LGPL-3.0 | Required by the LangGraph checkpointer | For Legal to assess (H-18, issue 7) |
| One request reached LangSmith's public endpoint during the spike | The architect's reference draft created a client on import | No key or data was sent and the call failed. The file is deleted and the pattern is banned by test (issue 8) |
| Web search sends queries outside the network | Inherent to research | Egress allow-list; an approved service (H-10); queries must not contain confidential content, enforced by classification |
| The model provider processes prompts | Inherent to using a model | Foundry deployments in the tenant; terms to be confirmed by Legal |
| A person can release work over a failed check or a review finding | Owner's requirement (ADR-0032) | Always recorded with a reason and shown on the deliverable; override counts reported |
| Prompts and skills are unevaluated drafts | No evaluation data yet (H-13) | Nothing is promoted without passing the evaluation gate |
| The database owner can switch the append-only triggers off, and the application role can append events and move the stored chain head | PostgreSQL gives a superuser and the writer these rights | Changing or removing an existing event is detected by chain verification, and the application role cannot do it. Forging a new event is not prevented. Separate owner and application credentials, and exporting the chain head to immutable storage on a schedule, are WP-12 |
| Personal data is covered for three kinds only | ADR-0035: the detectors find email addresses, 16-digit payment card numbers (Luhn checked) and IPv4 addresses. The library's `detect_ip` finds IPv4 only and `detect_credit_card` 16-digit cards only, whatever their docstrings say | Names, postal addresses, national identifiers, IPv6 addresses and 13 to 19 digit cards are not detected. Detection of these is a separate decision for the AI lead and the data protection officer. Captured evidence bodies are tool results and are not altered (ADR-0033 point 20) |
| The sponsor's request reaches an agent unredacted | Owner's choice (ADR-0035 point 8): input scanning is off so the request stays verbatim; tool results are not altered | Personal data in a request or a tool result reaches the Foundry deployment. The data protection officer and Legal should confirm the position (H-29). Until then the catalogue's Internal ceiling limits exposure |
| Model approvals and cost rates are provisional | The approved list and the real prices are the organisation's to supply (H-03, H-14) | Entries are marked `provisional`; the rates are illustrative placeholders used to meter and enforce budgets; replacing `policy/model_catalogue.yaml` needs no code change |
| Per-agent usage is metered in process | The durable per-agent meter is not part of WP-03 | A run's spend is settled against its reservation when it ends, in a `finally`, and acknowledged only after the ledger has it; a process that dies mid-run loses the in-flight count, and the reservation stays `reserved` because nothing releases a stale one yet. Releasing stale reservations is a WP-05 and WP-07 item: the controller must do it |
| Budget overshoot is bounded by one model call | The stop is checked before the next model call, so the call that crosses the limit is already spent | Settlement adds the actual cost even if it exceeds the reservation |
| Model fallback is untested against Foundry | No catalogue entry has a fallback today | Stack construction is tested with scripted models only. Fallback calls are priced at the primary model's cost band; this matters once a fallback entry exists |
| Nothing has been run against the real libraries | Design stage | WP-01 exists for this |
| No penetration test, threat-model review or red-team exercise | Not yet scheduled | Required before production; phase 5 of the roadmap |
