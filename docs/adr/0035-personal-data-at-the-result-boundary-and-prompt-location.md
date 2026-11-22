# ADR-0035: Personal data at the result boundary, and where prompt files are found

- **Status:** Accepted
- **Date:** 2026-11-22
- **Decided by:** the architect, under the authority the repository owner delegated on 22 November 2026.
- **Amends:** ADR-0033 point 12.

## Context

WP-03 raised two issues. Issue 19: the personal-data middleware redacts the text of a model's reply
but not a specialist's structured result, which is the only output that leaves the agent. Issue 20:
prompt files are found from the source file's location, which fails if the package is installed as
a wheel.

## Decision

**Personal data in a specialist's result (issue 19)**

1. A deterministic step in code, not a model and not middleware, scans the validated
   `SpecialistOutput` before it becomes an `AgentResult`. It redacts every free-text string field.
   Identifier fields (task, agent and evidence ids, and the references of citations) are never
   altered.
2. It detects the same three kinds the middleware does: email address, payment card number (checked
   with the Luhn test) and IP address. The implementer reuses the library's detectors only if they
   are a documented, public interface in the installed version; otherwise the step carries its own
   patterns. This is to be verified in the current documentation, not assumed.
3. Redaction is chosen over blocking. Failing a whole task, and spending its budget again, because
   an email address appears in a summary is a worse outcome than a placeholder.
4. Each redaction writes an audit event, `guardrail.pii_redacted`, with the count per kind and the
   field names. It never records the value.
5. The step also covers any later path by which a result reaches the sponsor.
6. The middleware stays as built. It still covers free-text replies.

**What this does not cover (stated in the control matrix, not left implicit)**

7. Names, postal addresses and national identifiers are not detected. Detection of these is a
   separate decision for the AI lead and the data protection officer.
8. Input is not scanned, by the owner's choice: the sponsor's request reaches the model verbatim.
   Tool results are not altered. Personal data in a request or a tool result therefore reaches the
   Foundry deployment unredacted. The data protection officer and Legal should confirm that
   position (H-29). Until they do, the catalogue's Internal ceiling for every provisional model is
   what limits exposure.

**Where prompt files are found (issue 20)**

9. The container image copies `agents/` and sets `ORCHESTRATOR_AGENTS_DIR`. Packaging `agents/` as
   package data is deferred to WP-12 and only done if a wheel install is needed.
10. Both loaders, the new one and the ported compiler, honour the environment variable. If the
    directory does not exist, startup fails at once with a message that names the variable and
    the path tried. A missing file at the first prompt load is not acceptable.

## Consequences

- WP-03 gains a small follow-up in the same pull request: the result-boundary step, its tests, the
  clearer startup error, and the matching control-matrix wording.
- The known gap recorded against issue 19 changes from "not covered" to "covered for three kinds,
  not for names, addresses or identifiers".
