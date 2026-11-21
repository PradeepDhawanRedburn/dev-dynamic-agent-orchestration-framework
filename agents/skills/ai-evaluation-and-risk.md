---
name: ai-evaluation-and-risk
title: AI evaluation and risk
kind: method
version: 1.0.0
status: draft
owner: Architect
used_by: ai-specialist
---
# AI evaluation and risk

## Skill text

```text
SKILL: AI EVALUATION AND RISK
- Need: establish what the AI part must do, for whom, and the cost of a wrong output. That cost sets how much checking is needed.
- Simplest first: rules or search, then one model call with retrieval, then multi-step agents. Recommend the lowest rung that meets the criteria.
- Evaluation before build: a test set of real examples with expected outcomes, a measure for each success criterion, a pass threshold, and a named person who judges disputed cases.
- Retrieval: evaluate whether the right material is retrieved separately from whether the answer is right.
- Grounding: answers must cite retrieved material; say what the system does when nothing relevant is found.
- Risks to assess each time: invented output, prompt injection through retrieved or user content, confidential data sent to a model, access rights not respected in retrieval, bias, drift after a model change, cost growth, dependence on one model.
- Operation: what is logged, how quality is watched after release, and what triggers re-evaluation.
```
