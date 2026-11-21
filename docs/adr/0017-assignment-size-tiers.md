# ADR-0017: Assignment size tiers

- **Status:** Accepted
- **Date:** 2026-11-21

## Context

In the dry run the permanent agents made more model calls than the specialists. Every assignment used every layer.

## Decision

Rules assign a tier from the framed request: Small, Standard or Major. The tier decides which roles and gates apply. A human can raise the tier. The first release implements Small only.

## Consequences

- Cost follows the size of the work.
- Tier thresholds are policy values to set with the owner.
