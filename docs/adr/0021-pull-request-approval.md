# ADR-0021: The platform opens pull requests without per-request human approval

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

A specialist's accepted change reaches the estate as a pull request (ADR-0006). The architect
proposed that a human approve each pull request before it is opened. The repository owner
decided that this approval is not required: the human control is the review and merge.

Opening a pull request is not a no-op. It starts CI workflows, and those workflows run code
written by an agent.

## Decision

Once a Lead has accepted a change and its Tester's checks have passed, the action executor
opens the pull request without asking a human first.

Because the human gate has moved to the merge, these conditions are mandatory:

1. **People merge.** Branch protection requires at least one human review. The platform's
   identity cannot approve or merge, and cannot push to a protected branch.
2. **Allow-list.** The executor opens pull requests only in repositories on an allow-list in
   policy, from a branch it created.
3. **Workflows triggered by an agent's pull request are read-only.** They run with an identity
   that can read and plan but cannot change anything, and they receive no deployment secrets.
   Anything with write access runs only after a human merges, behind a protected environment.
4. **Labelled and traceable.** Every such pull request is labelled as agent-authored and links
   to the project, task, agent and evidence.
5. **Rate limited.** A limit on open agent-authored pull requests per repository.
6. **Kill switch.** Suspending or cancelling stops the executor opening further pull requests.

Other consequential actions, such as creating a ticket or sending a message, still need human
approval per ADR-0006.

## Consequences

- Faster flow, and review happens where engineers already review.
- This amends ADR-0006 for pull requests only: the approval step before the executor acts is removed.
- Condition 3 is the important one. A Terraform plan or a build executes code from the pull
  request. If a workflow triggered by an agent's pull request holds write credentials or
  secrets, an agent could change the estate without a human merging. WP-08 must prove this
  cannot happen, and WP-12 must configure the identities accordingly.
- The security owner should review this decision before the first real repository is added to the allow-list.

## Alternatives considered

- Human approval before every pull request: the architect's recommendation; not chosen.
