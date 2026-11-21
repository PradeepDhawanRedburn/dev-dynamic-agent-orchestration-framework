---
name: test-design
title: Test design
kind: method
version: 1.0.0
status: draft
owner: Architect
used_by: tester
---
# Test design

## Skill text

```text
SKILL: TEST DESIGN
- Write checks from the acceptance criteria before the work starts. One or more checks per criterion; each check names its criterion id.
- A check states what is examined, how, and what counts as pass. Another tester would reach the same verdict.
- Prefer a check that runs (in the sandbox, or a re-fetch of the source) over a check that reads.
- For each material claim: does the cited evidence say this, is the source what it claims to be, is it current enough for the claim?
- Include at least one check for what should not be there: unsupported claims, forbidden actions, content outside scope.
- Report pass, fail or could not check. "Could not check" is never a pass.
- Do not repair the work. Describe the failure precisely enough that the specialist can.
```
