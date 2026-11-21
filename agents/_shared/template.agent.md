---
name: role-name
title: Role Title
function: Define | Deliver | Assure | Control | Learn
version: 1.0.0
status: draft
model_key: reasoning-standard
tiers: small, standard, major
reports_to: Who this role answers to
output_schemas: SchemaOne, SchemaTwo
tools: none
metric: The number that shows this role is earning its place
---
# Role Title

## Purpose

One or two sentences: what this role is accountable for.

## System prompt

```text
{{organisational-policy}}

ROLE
You are the <Role>. <What you are accountable for.>

WHEN <SITUATION> (output: SchemaOne)
- <Instruction.>
```

## Inputs

- What the role is given.

## May

- What the role is permitted to do.

## May not

- What it is not permitted to do.

## Escalates when

- Conditions it must flag.

## Done by code, not by this agent

- The control decisions around this role that are deterministic.
