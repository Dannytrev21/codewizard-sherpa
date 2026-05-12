# ADR-0014: `ObjectiveSignals` is `extra="forbid", frozen=True`; static-introspection CI test enforces ADR-0008

**Status:** Accepted
**Date:** 2026-05-12
**Tags:** trust · enforcement · type-safety
**Related:** [ADR-0003](0003-trustscorer-extension-via-signal-kind-registry.md), [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md)

## Context

[Production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md) forbids LLM self-confidence as a trust-score input — the strict-AND consumes objective facts only, not the LLM's opinion of its own work. Three risks for Phase 5: (a) a future contributor adds a `confidence` field to a signal sub-model; (b) a `details` dict contains `{"llm_self_assessment": "high"}`; (c) a new signal kind sneaks in a hidden judgment field. Prose enforcement (the ADR) is too weak; the synthesis: enforce by code via Pydantic `extra="forbid", frozen=True` plus a CI introspection test that walks every field name reachable from `ObjectiveSignals` and rejects forbidden substrings. See [phase-arch-design.md §Component design — `SandboxSpec`/`SandboxRun`/`ObjectiveSignals`](../phase-arch-design.md#sandboxspec--sandboxrun--objectivesignals-pydantic-models) and [final-design.md §Load-bearing commitments §2.2](../final-design.md#load-bearing-commitments-check).

## Options considered

- **Prose ADR only** — ADR-0008 is the enforcement. Trust contributors. Fails at the first PR that adds a `confidence` field with a "but it's just for logging" excuse.
- **Runtime check** — At evaluation time, scan signal dicts for forbidden keys. Easy to bypass (skipped on test paths; performance cost).
- **Pydantic `extra="forbid"` + CI introspection** — Compile-time enforcement (`extra="forbid"` rejects unknown fields); CI test walks every field name (recursive type walk through `model_fields`) and asserts no field name contains `confidence`, `llm`, `self_reported`, `model_says`.

## Decision

Every Phase 5 signal sub-model and `ObjectiveSignals` itself carries `model_config = ConfigDict(extra="forbid", frozen=True)`. `details: dict[str, str | int | bool]` — no nested dict, no float, no list. `tests/sandbox/test_objective_signals_static.py` walks every field reachable from `ObjectiveSignals` recursively (including dict value types) and asserts no field name contains any of the four forbidden substrings.

## Tradeoffs

| Gain | Cost |
|---|---|
| ADR-0008 is enforced by code; a PR adding a `confidence` field fails CI loudly | Adding a legitimate field whose name happens to contain a forbidden substring requires renaming (open Q9: `coverage_evidence_strength` instead of `coverage_confidence`) |
| Type-system rigor: `extra="forbid"` + `frozen=True` means signals cannot be mutated post-construction or carry hidden fields | Pydantic's `extra="forbid"` is per-model; the test walks the full type tree to enforce transitively |
| `details: dict[str, str | int | bool]` prevents structural smuggling (e.g., `{"meta": {"confidence": ...}}` is rejected) | Some legitimate details (durations as floats, lists of failing tests) must serialize to strings/ints |
| Introspection test is fast (<1 s) and runs every CI build | Test must be kept in sync with the Pydantic model structure — adding a new sub-model adds a path to walk |

## Consequences

- `src/codegenie/sandbox/signals/models.py` defines `ObjectiveSignals` and six sub-models, all with `extra="forbid", frozen=True`.
- `tests/sandbox/test_objective_signals_static.py` is the load-bearing static test (walks recursively through `pydantic.fields.FieldInfo`).
- The honest-confidence pattern (signal evidence weak) is expressed by `details["coverage_evidence_strength"] = "low"` — *not* `coverage_confidence` (forbidden substring).
- New signal kinds register via decorator and add a new optional field on `ObjectiveSignals`; their sub-model also gets `extra="forbid", frozen=True`.
- The static test is part of the Phase 5 PR; it will block any Phase 7+ PR that adds a banned-substring field.
- New invariant: a Phase 5+ contributor cannot smuggle an LLM self-assessment into a trust signal — by either field name or nesting depth.

## Reversibility

**Low.** Relaxing `extra="forbid"` re-opens silent field addition. Relaxing the introspection test re-opens the `confidence` smuggle. The constraints are intentionally rigid and aligned with the load-bearing ADR-0008.

## Evidence / sources

- [final-design.md §Load-bearing commitments §2.2](../final-design.md#load-bearing-commitments-check)
- [phase-arch-design.md §Goals 8](../phase-arch-design.md#goals)
- [phase-arch-design.md §Component design — `SandboxSpec`/`SandboxRun`/`ObjectiveSignals`](../phase-arch-design.md#sandboxspec--sandboxrun--objectivesignals-pydantic-models)
- [phase-arch-design.md §Agentic best practices — Confidence handling for ADR-0008](../phase-arch-design.md#agentic-best-practices)
- [phase-arch-design.md §Open Q9](../phase-arch-design.md#open-questions-deferred-to-implementation)
- [production ADR-0008](../../../production/adrs/0008-objective-signal-trust-score.md)
