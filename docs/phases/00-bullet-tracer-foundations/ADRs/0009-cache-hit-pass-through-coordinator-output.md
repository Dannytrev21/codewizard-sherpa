# ADR-0009: Cache-hit pass-through as a first-class coordinator output (`ProbeExecution = Ran \| CacheHit \| Skipped`)

**Status:** Accepted
**Date:** 2026-05-11
**Tags:** coordinator · cache · interface · phase-evolution
**Related:** [ADR-0005](0005-coordinator-async-from-day-one.md), [production ADR-0006](../../../production/adrs/0006-continuous-deterministic-gather.md)

## Context

`../critique.md §6.5` flags a shared blind spot across all three lens designs: each one describes the coordinator's cache interaction as `cache.get → run probe → cache.put`. None of the three Phase 0 designs implements the skip-and-pass-through path where a cache hit returns a cached `ProbeOutput` *without* running the probe and the coordinator records the cache hit as a distinct event from a fresh run.

Phase 14's continuous-gather model ([production ADR-0006](../../../production/adrs/0006-continuous-deterministic-gather.md)) is built on incremental gathers: only probes with changed `declared_inputs` re-run; the rest pass through. The coordinator must report which probes ran fresh, which were cache hits, and which were skipped for some other reason. Phase 13's cost ledger ([ADR-0004](0004-probe-execution-audit-anchor.md)) attributes spend differently depending on this distinction — a cache hit costs effectively zero; a `Ran` execution carries the probe's compute cost.

If the coordinator returns just `dict[str, ProbeOutput]` (lens-design default), Phase 14 cannot tell the difference between "this probe ran fresh in this gather" and "we returned the cached result of a prior gather." That distinction is load-bearing for both cost attribution and incremental gather.

## Options considered

- **`dict[str, ProbeOutput]` only (lens-design default).** Coordinator returns just the outputs. Phase 14 has to infer cache-vs-fresh from cache state at gather time — a separate query, racy, lossy.
- **Side channel via structured logging.** Emit `probe.cache_hit` and `probe.success` events; consumers correlate them with outputs by name. Works for monitoring; brittle for cost attribution (events can be lost).
- **`ProbeExecution = Ran \| CacheHit \| Skipped` alongside outputs (synth gap-fix).** Coordinator returns `GatherResult(outputs, executions)`. `Ran(output)` carries the freshly-run output; `CacheHit(output, key)` carries the cached output and the key it came from; `Skipped(reason)` covers cases like "applies() returned False" or "preconditions not met." Phase 14 reads `executions` for incremental decisions; Phase 13 reads it for cost attribution; the audit writer reads it for per-probe records.

## Decision

**The Coordinator returns `GatherResult(outputs: dict[str, ProbeOutput], executions: dict[str, ProbeExecution])`. `ProbeExecution` is a tagged union: `Ran(output: ProbeOutput) | CacheHit(output: ProbeOutput, key: str) | Skipped(reason: str)`.** All three variants are frozen dataclasses. The `executions` dict is populated for every probe the coordinator was asked to dispatch — including those that produced no output (Skipped). Phase 0 ships one probe; the cache-hit smoke test (`test_cli_end_to_end.py::test_cache_hit_on_second_run`) asserts `executions["language_detection"]` is a `CacheHit` on the second invocation.

## Tradeoffs

| Gain | Cost |
|---|---|
| Phase 14's incremental-gather model has the coordinator interface it needs — no contract extension when continuous gather lands | Two-channel output (outputs + executions) instead of one — callers must consume both; mitigated by `GatherResult` carrying them together as a frozen dataclass |
| Phase 13's cost attribution distinguishes free cache hits from probe runs — accurate spend per probe execution | Tagged-union pattern is more Python-3.10+-ish (`match` statement-friendly) than the average codebase; readers must learn the variants |
| The audit writer ([ADR-0004](0004-probe-execution-audit-anchor.md)) populates `ProbeExecutionRecord` cleanly from each variant — Ran/CacheHit carry the key and blob hash; Skipped marks `exit_status="skipped"` | `Skipped` is over-engineered for Phase 0 (no probe is ever skipped — `LanguageDetectionProbe.applies()` returns True for everything). The variant exists for Phase 1+ |
| Phase 14's "extension by addition" (`production/design.md §2.5`) holds — the *contract* freezes here; later phases consume more variants, not different shapes | Three variants instead of two — `Skipped` might have been deferred; the synthesis chose to encode it now because Phase 1's `applies_to_languages` filter is the first consumer |
| The structured-logging events `probe.cache_hit` / `probe.success` / `probe.skip` line up with the variants — same names, same semantics, dual surface for both consumers and audit writers | Two surfaces (events + dataclass) emit equivalent information; mitigated by them being constructed at the same code point, never independently |

## Consequences

- `src/codegenie/coordinator/coordinator.py` exports `GatherResult`, `Ran`, `CacheHit`, `Skipped`, `ProbeExecution`. Frozen dataclasses throughout.
- The CLI exit policy in `cli.py` reads `executions` to compute exit codes: 0 if ≥1 probe in `outputs`; 2 if all probes have errors or are `Skipped`.
- The audit writer reads `executions[probe_name]` to populate `ProbeExecutionRecord` — `Ran` → `exit_status="ok"`, `CacheHit` → `exit_status="ok", cache_hit=True`, `Skipped` → `exit_status="skipped"` ([ADR-0004](0004-probe-execution-audit-anchor.md)).
- The lifecycle event names align: `probe.cache_hit` is emitted on `CacheHit`, `probe.success` on `Ran` success, `probe.skip` on `Skipped`. Phase 6's state ledger subscribes to the events; Phase 13's cost ledger consumes the `executions` dict.
- Phase 1's six probes will produce a mix of `Ran` and `CacheHit` results; Phase 2 introduces the first `applies()` filter that returns `Skipped(reason="language not detected")`. None of these phases edits `ProbeExecution`.
- `test_cli_end_to_end.py::test_cache_hit_on_second_run` is the Phase 0 exit criterion #4 verifier (`../final-design.md §11`): second run reports `CacheHit`, and `os.scandir` is never re-entered (verified via `monkeypatch`).

## Reversibility

**Medium.** Collapsing back to `dict[str, ProbeOutput]` only is mechanically cheap (delete the executions dict; consumers fall back to log events) but loses the audit-record fidelity ([ADR-0004](0004-probe-execution-audit-anchor.md)'s `cache_key` and `blob_sha256` populate from this output) and breaks Phase 14's incremental-gather plan. After Phase 1, every probe set tested has this contract; removal is multi-phase coordinated work.

## Evidence / sources

- `../final-design.md §2.6` (Cache-hit pass-through is first-class)
- `../final-design.md §L4 row 5` (Shared blind spot resolution: cache-hit pass-through in coordinator output)
- `../critique.md §6.5` (Shared blind spot — no skip-and-pass-through path)
- `../phase-arch-design.md §Component design / Coordinator` (`GatherResult` shape)
- `../phase-arch-design.md §Data model` (`Ran | CacheHit | Skipped` dataclasses)
- [production ADR-0006](../../../production/adrs/0006-continuous-deterministic-gather.md) — incremental gather depends on this distinction
- [ADR-0004](0004-probe-execution-audit-anchor.md) — audit anchors populate from `ProbeExecution` variants
- [ADR-0005](0005-coordinator-async-from-day-one.md) — coordinator contract this completes
