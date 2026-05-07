# ADR-003: Assessment 3-gate model

**Status:** accepted
**Date:** 2026-05-07
**Enforcement:** agent

## Context

JARVIS had no validation step -- it applied templates and hoped for the best.
Failed deployments left ServiceNow instances in an unknown intermediate state
with no way to determine what succeeded and what did not.

## Decision

Assessment runs in three phases:
  Gate 1 (readiness): checks prerequisites before deploying a template
  Gate 2 (validation): verifies everything was created correctly after deploy
  Standalone: `nexus assess` runs a health scan against any instance at any time

Each gate is a separate, stateless RuleEngine evaluation pass.

## Consequences

Every template deployment requires two assessment passes (Gate 1 + Gate 2).
The RuleEngine must be stateless and re-runnable without side effects.
Rollback logic is scoped to the execution layer, not the assessment layer --
the assessment layer only reports; it never mutates instance state. The
standalone scan can be run independently of any deployment workflow.
