# ADR-008: Type Annotation Completeness

**Status:** accepted
**Date:** 2026-05-07
**Enforcement:** blocking hook (pre-edit-validate.py) + pyright strict

## Context

Sprint retrospective issues #1-5: bare Any in test parameters, dict[str, Any] in
public interfaces, object return types, and return values flowing as Any through
untyped sources. These issues caused incorrect fakes, undetected Protocol
mismatches, and mypy-silent type gaps.

## Decision

Three rules enforced by the pre-edit hook:

1. No bare Any in function signatures: blocks `: Any` and `-> Any` in def lines.
   Use `object`, a Protocol, or a TypedDict.

2. No dict[str, Any] in public interfaces: blocks `dict[str, Any]` in function
   signatures. Use TypedDict, a Protocol, or a Pydantic model.

3. No object return types in functions with a body: -> object is valid only in
   Protocol stubs (... body). Concrete functions declare the actual return type.

TYPE_CHECKING-guarded imports are exempted from the deferred-import check.

## Consequences

Fakes must use typed dataclasses that structurally satisfy their target Protocols.
The Anthropic SDK's ToolParam TypedDict is used instead of dict[str, Any] for tool
definitions. Protocol chains use Iterable[_Entry] (covariant) instead of
list[_Entry] (invariant) at SDK boundaries.
