# WP-13: Reasoning patterns: ReAct, Self-Refine and test-driven flows

- **Status:** Not started. Final work package; do not begin before WP-11 is done
- **Depends on:** WP-10, WP-11
- **Raised by:** the repository owner, 21 November 2026

## Goal

Find out, by measurement, whether three published agent patterns improve results here, and adopt
only those that do. Nothing in the current design changes until this work package reports.

## The architect's position

[ADR-0030](../../adr/0030-reasoning-patterns.md), Proposed: keep ReAct for specialists with a short plan first; add one self-check pass before submission; add a test-driven flow for code and configuration tasks; leave permanent agents single-call. If the owner accepts it, tasks 1 to 3 below build and measure those. Until then they are experiments.

## Where the design stands today

Using LangGraph makes loops possible. It does not by itself mean these patterns are followed.

| Pattern | Paper | Followed today? | Detail |
| --- | --- | --- | --- |
| ReAct: reasoning interleaved with actions | [Yao et al., arXiv 2210.03629](https://arxiv.org/abs/2210.03629) | Partly | A specialist runs a bounded loop of model call, tool call, observation. Whether that loop exposes explicit reasoning between actions depends on LangChain's agent and the model, and is not verified. Permanent agents do not loop: each makes one call into a narrow schema, by design |
| Self-Refine: the same model critiques and revises its own output | [Madaan et al., arXiv 2303.17651](https://arxiv.org/abs/2303.17651) | No, deliberately different | Refinement loops exist (two revisions per task, three refinement rounds in discovery), but the feedback comes from someone else: the Tester, the Reviewer on a different model, or the sponsor. The design rule is that no function checks its own work |
| AlphaCodium: a test-based, multi-stage, iterative flow for code | [Ridnik et al., arXiv 2401.08500](https://arxiv.org/abs/2401.08500) | In spirit, not in detail | Shared: a fixed flow instead of one large prompt, structured outputs, tests written before the work (ADR-0012), options generated and one chosen (ADR-0028). Missing: a run-and-fix loop against tests for code, extra generated tests, and test anchors |

## Tasks

Each is an experiment behind a switch, off by default, compared with the current behaviour on
the evaluation sets from WP-10.

1. **ReAct.** Establish what the specialist loop actually does in the pinned LangChain version. Then test whether asking a specialist to state a short plan and to note what each observation changes improves evidence coverage and task completion. Record the reasoning as trace content, never as evidence.
2. **Self-critique before submission.** Give a specialist one pass to check its own draft against the acceptance criteria and revise, before the Tester sees it. Limit: one pass. Measure first-time pass rate at the Tester, cost and time.
3. **Test-driven flow for code tasks.** For tasks that produce code or configuration (Software and DevOps profiles): reflect on the task; take the Tester's checks and propose additional ones; produce the work; run the checks in the sandbox; fix and re-run within a limit; a fix must keep passing every check that already passed.
4. For each experiment, report quality, cost, latency and failure modes against the baseline, with the data.
5. For each pattern worth adopting, draft an ADR for the architect. Adopt nothing without an Accepted ADR.

## Rules these experiments must not break

- Self-critique never replaces the Tester or the Reviewer, and never counts as a test (ADR-0009, ADR-0012).
- Every loop has a hard limit in code and is charged to the budget ledger.
- No new tool, and no consequential tool (ADR-0006). The run-and-fix loop uses only the sandbox.
- Additional checks proposed by a specialist are suggestions to the Tester, who owns the checks.
- A model's stated reasoning is not evidence and is not trusted as an account of what it did.
- Permanent agents stay single-call unless an experiment shows a clear gain for a specific role.

## Acceptance criteria

- [ ] What the specialist loop does today is documented from a run, not from memory.
- [ ] Each experiment has a result on the evaluation sets with cost and latency, or a stated reason it could not be run.
- [ ] Every loop introduced is bounded and metered (tested).
- [ ] With all switches off, behaviour is unchanged (tested).
- [ ] A recommendation per pattern: adopt, adopt for named task types, or do not adopt.

## Out of scope

Changing human gates, the Tester's authority, or the roles. Fine-tuning a model.

## Notes from the architect

- The papers' results are on their own benchmarks and older models. They are a reason to test, not evidence that the same gain appears here.
- Expect a trade: these patterns add model calls. The question for each is whether fewer rejected results pay for them.
