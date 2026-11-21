# Control matrix

Each control, what provides it, the evidence it leaves, and where it is built. **Status of every
row: designed, not built.** A row becomes "built" when its work package is merged with passing
tests, and "operating" only after your own assurance testing.

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
| Nothing has been run against the real libraries | Design stage | WP-01 exists for this |
| No penetration test, threat-model review or red-team exercise | Not yet scheduled | Required before production; phase 5 of the roadmap |
