# Story S3-05 — Coordinator + prelude pass + resource budget

**Step:** Step 3 — Build the harness internals (cache, coordinator, validator, sanitizer, writer, config)
**Status:** Ready (Hardened)
**Effort:** L
**Depends on:** S3-01, S3-02, S3-03, S3-04
**See also:** S4-01 (`LanguageDetectionProbe` — first real `tier="base"` probe); S3-06 (audit-writer reads `executions[name].key` on cache hits)
**ADRs honored:** ADR-0005, ADR-0007, ADR-0008, ADR-0009, ADR-0010, ADR-0011, ADR-0012

## Validation notes

Hardened on 2026-05-13 by `phase-story-validator` v1. Three critics returned **42 findings** (12 block, 26 harden, 4 nit; 0 `NEEDS RESEARCH` after synthesis — every gap was answerable from in-repo docs and the existing S3-01/02/03/04 code). Material changes applied here:

- **Pinned the type-flow** `probe.run() → ProbeOutput → _ProbeOutputValidator.model_validate(...) (validates, does not transform) → OutputSanitizer.scrub(po, snapshot.root) → SanitizedProbeOutput → cache.put(key, sanitized) → Ran/CacheHit.output: SanitizedProbeOutput → outputs[name]: SanitizedProbeOutput`. The arch §Data model literal `Ran(output: ProbeOutput)` is contradicted by `src/codegenie/output/sanitizer.py:50` (`SanitizedProbeOutput` is a distinct frozen dataclass with the exact field shape of `ProbeOutput`); the implementer note in the prior version was right, the literal contract wasn't. `SanitizedProbeOutput` and `ProbeOutput` have byte-identical JSON serialization (same fields in same order — see `cache/store.py:68-99`), so cache.put/get's `ProbeOutput`-typed signature is compatible at runtime; on cache hit, the coordinator rewraps the deserialized `ProbeOutput` as `SanitizedProbeOutput(**fields)` to restore the typed signal. This is named follow-up #1 in the report — an ADR amendment to update arch §Data model + the `cache.put` signature lands in a separate PR.
- **Pinned `outputs` vs `executions` cardinality.** `executions[name]` is populated for **every** dispatched probe (`Ran` | `CacheHit` | `Skipped`); `outputs[name]` is populated **iff** the execution variant carries an output (`Ran` or `CacheHit`) — `Skipped` produces no `outputs` entry. CLI exit-code policy (arch line 483) thus becomes `0 if any output in outputs has errors=[]; else 2`.
- **Resolved `Probe.timeout_seconds=300` vs `ResourceBudget.wall_clock_s=30` collision.** `wait_for` uses `min(probe.timeout_seconds, declared_resource_budget.wall_clock_s)` — the tighter wins, surfacing accidental drift loudly. A 5s probe with `timeout_seconds=300, wall_clock_s=1` times out at ~1s. Test pins both directions.
- **Pinned the `BudgetingContext` contract** as a sibling-callback (`ctx.report_bytes(n)`) — `ProbeContext.workspace: Path` stays a plain `pathlib.Path` (ADR-0007 freezes `probes/base.py:40`'s type annotation). Pat-subclassing is rejected: `PurePath`/`Path` split + `mypy --strict` friction (per ADR-0007 §Decision). Phase 0's `LanguageDetectionProbe` is metadata-only — the contract surface lands tested but unexercised by a real-probe write; Phase 1+ real artifact-writers populate `report_bytes` calls. Documented as a Phase-1-load-bearing seam.
- **Made the validator+sanitizer chain testable on the happy path.** The original `test_validator_and_sanitizer_run_in_coordinator` used a secret-shaped field that failed at the validator — sanitizer never ran. A mutant coordinator that *omits* the sanitizer call would pass. Split into two tests: validator-blocks-secret (the old shape) + sanitizer-scrubs-absolute-path-in-happy-path (probe emits `{"root_path": "<repo_abs>/foo"}`, validator passes, AC pins `outputs[name].schema_slice["root_path"]` is the relative form, and `isinstance(outputs[name], SanitizedProbeOutput)`).
- **Pinned the cache-hit short-circuit chain.** On `CacheStore.get → not None`: `probe.run` is not invoked, `_ProbeOutputValidator` is not invoked, `OutputSanitizer.scrub` is not invoked, `CacheHit.output` carries `SanitizedProbeOutput(**fields)` from the deserialized blob, `CacheHit.key` equals the SHA-256 identity tuple returned by `cache.key_for(probe, snapshot, task)` (per ADR-0009 §Decision, used by S3-06's audit writer).
- **Pinned `except Exception` (not `BaseException`).** `CancelledError`, `KeyboardInterrupt`, `SystemExit` propagate. Test injects each and asserts `gather()` re-raises. Closes a mutant `except BaseException` that the old AC-6 wording left alive.
- **Added the prelude-failure semantics.** If every `tier="base"` probe ends in `Ran(errors=[...])`, `Skipped`, or emits no `language_stack.counts` key, the coordinator emits a structured `prelude.degraded` warning carrying the prelude error list and dispatches the second pass against the **original** snapshot (empty `detected_languages`). It does NOT crash; it does NOT silently dispatch — the warning is the load-bearing fail-loud surface. Closes Rule 12 ("Fail loud") for the most common Phase 1+ failure path (LanguageDetectionProbe walks a permission-denied directory).
- **Added `probe.skip` lifecycle event** to AC-11 (was omitted; ADR-0009 line 41 + arch line 755 both require it). Phase 6's state ledger subscribes by event name; reserving it now prevents Phase 2 renames.
- **Added `run_id` structlog binding.** `gather()` generates `run_id = secrets.token_hex(8)` once and binds it via `structlog.contextvars.bind_contextvars(run_id=...)` so every `probe.*` event carries it. Phase 13's cost ledger and Phase 6's state ledger both subscribe by `run_id` (arch line 756). Closes a contract gap that would have surfaced in Phase 13 as "go back and add run_id to every coordinator event."
- **Added `applies()` filter contract.** The coordinator MUST call `probe.applies(enriched_snapshot, task)` before cache lookup; `False` → `executions[name]=Skipped(reason="applies() returned False")`, `outputs[name]` absent, `probe.skip` emitted, `run()` not called, `cache.get` not called. Phase 0's `LanguageDetectionProbe` always returns `True`; the test uses a fake probe. Phase 2's `IndexHealthProbe` and Phase 1's language-filtered probes light this up for real.
- **Rewrote every TDD test with concrete runnable Python.** All 10 `...` bodies replaced. Same antipattern S3-02/S3-03/S3-04 validations burned. The dense L-effort story is now the densest *concrete* test block in Phase 0.
- **Replaced `caplog` with `structlog.testing.capture_logs`** in the RSS-warning test (`tests/unit/test_exec.py:285` precedent; structlog with `WriteLoggerFactory` does NOT route through stdlib logging — `caplog` silently no-ops).
- **Parametrized failure-isolation over `[ValueError, PermissionError, RuntimeError, KeyError, OSError]` + a negative `CancelledError` case.** Arch §Edge cases row 1 names `PermissionError` specifically; the original `ValueError`-only test would pass on a narrow `except ValueError`. Negative test pins `BaseException` carve-out.
- **Pinned `PydanticCustomError` unwrap shape.** Validator (`validator.py:165-168`) raises `PydanticCustomError("secret_likely_field_name", ..., {"error": SecretLikelyFieldNameError(...), "key": "...", "path": (...)})`. Coordinator catches `ValidationError`, walks `e.errors()[0]["ctx"]["error"]` to retrieve the typed instance, and stores `f"SecretLikelyFieldNameError: <key> at <path>"` in `output.errors[0]`. Pinned via regex on the stored error string. Closes an unrunnable assertion (`"errors mentioning SecretLikelyFieldNameError"` doesn't survive Pydantic's stock `ValidationError.__str__`).
- **Replaced timing-prone concurrency test** with deterministic `asyncio.Event` synchronization. 4 probes each `await event.wait()` before incrementing a peer-counter; the test releases events in controlled order. Peak == 2 (not `≤ 2`); a `Semaphore(1)` mutant fails the equality assertion. Second parametrization with `max_concurrent_probes=1` pins peak == 1.
- **Parametrized prelude test over `[{"python": 3}, {"javascript": 5, "typescript": 2}, {}]`** — a constant-hardcoding mutant fails 2 of 3 cases.
- **Added boundary-case raw-artifact tests** at `[0.5 MB, 1.0 MB, 1.5 MB]` — closes the "always-error" mutant and pins the `>` vs `>=` boundary.
- **Added `os.cpu_count() is None` test** via `monkeypatch.setattr(os, "cpu_count", lambda: None)` — closes a `min(None, ...)` `TypeError` on cgroup-constrained containers.
- **Added metamorphic invariants:** (a) order invariance — `gather([p1, p2, p3])` and `gather([p3, p1, p2])` produce equal `outputs` + equal-keyed `executions`; (b) idempotent re-run — a second `gather()` call with identical inputs produces all `CacheHit` executions and `outputs` equal to the first. Both stay within Phase 0's "no hypothesis" rule (manual permutations).
- **Added the `executions` dict invariant test** — a single 4-probe heterogeneous mix (success, fail, timeout, cache-hit) asserts `set(result.executions.keys()) == {p.name for p in probes}` and `set(result.outputs.keys()) == {p.name for p in probes if isinstance(result.executions[p.name], (Ran, CacheHit))}`.
- **Added a sanitizer-`repo_root` AC.** `OutputSanitizer.scrub` requires `repo_root: Path`; the coordinator threads `snapshot.root` (pre-resolved by `build_snapshot`).
- **Added a snapshot-isolation test.** Probe-A mutates its `snapshot.detected_languages` in-place; Probe-B (dispatched in the same gather, against the prelude-enriched snapshot) sees an unmutated view. `RepoSnapshot` is NOT `frozen=True` in `probes/base.py` (ADR-0007 freezes the field set, not the `frozen` keyword); the coordinator's `dataclasses.replace` produces a fresh instance per dispatch pass, isolating downstream probes from upstream mutations.

Three architectural follow-ups surfaced (not auto-fixed — outside this story's surgical scope per Rule 3):

1. **Arch §Data model lines 661-680 still declares `Ran(output: ProbeOutput)` literally** — should be amended to `Ran(output: SanitizedProbeOutput)` to match the implementation. Same for `GatherResult.outputs`. Separate ADR-amendment PR.
2. **`cache.put`/`cache.get` type signature** — currently typed `ProbeOutput`. Either widen to `ProbeOutput | SanitizedProbeOutput` (cheap, since fields match) or change to `SanitizedProbeOutput` (more correct; requires touching S3-01 code). Defer to a Phase 1 cleanup PR.
3. **ADR-0010 §Consequences line 50** says `_ProbeOutputValidator` is lazy-imported from `cli.py`'s `gather` click-command body; the actual coordinator dispatch is inside `coordinator.gather`. These are different module boundaries. Either amend ADR-0010 to allow the lazy import inside `coordinator.gather`, or add an explicit CLI-imports-coordinator-lazily rule. Filed as Phase 0 cleanup.

## Context

This story is the densest piece of harness internals in Phase 0. It assembles the async-bounded `Coordinator` that dispatches probes, the validator+sanitizer chain that lives **inside** the coordinator (the trust boundary), the `GatherResult` + `ProbeExecution = Ran | CacheHit | Skipped` shape that Phase 14 inherits unchanged (ADR-0009), and it closes **two Architect Gaps**:

- **Gap 4 — Coordinator prelude pass** (`../phase-arch-design.md §Gap analysis & improvements §Gap 4`): `LanguageDetectionProbe` runs in a first pass; the Coordinator enriches the `RepoSnapshot` via `dataclasses.replace(snapshot, detected_languages=...)`; downstream probes dispatch against the enriched snapshot. Without this, Phase 1's `NodeManifestProbe.applies_to_languages = ["javascript", "typescript"]` always sees `{}` and the filter never engages.
- **Gap 3 — Per-probe resource budget** (`../phase-arch-design.md §Gap analysis & improvements §Gap 3`): `Probe.declared_resource_budget` is enforced for `wall_clock_s` (already via `asyncio.wait_for`) and `raw_artifact_mb` (via a `BudgetingContext` injected as `ProbeContext.workspace`); RSS is **advisory** in Phase 0 (`probe.rss.warn` event). Without this, Phase 2's runtime-trace probes can OOM without defense.

This is the only L-effort story in Phase 0. Read both Gap entries before starting.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design / Coordinator` — full surface
  - `../phase-arch-design.md §Gap analysis & improvements §Gap 3` — per-probe resource budget (this story closes)
  - `../phase-arch-design.md §Gap analysis & improvements §Gap 4` — coordinator prelude pass (this story closes)
  - `../phase-arch-design.md §Scenarios / Scenario 1, 2, 3, 4` — cold/warm/failure/secret paths through the coordinator
  - `../phase-arch-design.md §Data model` — `Ran | CacheHit | Skipped`, `GatherResult`
  - `../phase-arch-design.md §Edge cases` rows 1, 2 — `PermissionError` mid-walk → `confidence="low"`; timeout → `cancel + 100ms grace + SIGKILL via exec.py weakref table` (the `1.5×` window belongs to `exec.py`'s subprocess escalation, not the coordinator's grace — see Note 3 below)
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0005-coordinator-async-from-day-one.md` — ADR-0005 — `asyncio.Semaphore(min(cpu, max_concurrent, 8))`, per-probe `wait_for`, **coordinator-level**: `cancel() + 100ms grace`; **subprocess-level**: `SIGKILL at 1.5× timeout_seconds` via `exec.py`'s weakref process table
  - `../ADRs/0009-cache-hit-pass-through-coordinator-output.md` — ADR-0009 — `GatherResult(outputs, executions)` with tagged-union `ProbeExecution`
  - `../ADRs/0010-pydantic-probe-output-validator.md` — ADR-0010 — coordinator constructs `_ProbeOutputValidator` from each `ProbeOutput` post-`run()`, pre-`scrub`
  - `../ADRs/0008-output-sanitizer-two-pass-chokepoint.md` — ADR-0008 — `OutputSanitizer.scrub` runs in the coordinator after the validator
- **Source design:**
  - `../final-design.md §2.6` — Coordinator (the synthesis source)
- **Existing code:**
  - `src/codegenie/cache/store.py` (S3-01) — `CacheStore.get/put/key_for`
  - `src/codegenie/coordinator/validator.py` (S3-02) — `_ProbeOutputValidator`
  - `src/codegenie/output/sanitizer.py` (S3-03) — `OutputSanitizer.scrub`
  - `src/codegenie/config/loader.py` (S3-04) — `Config.max_concurrent_probes`
  - `src/codegenie/exec.py` (S2-04) — `run_allowlisted` (used by `snapshot.py` for `git rev-parse HEAD`)
  - `src/codegenie/probes/base.py` (S2-02) — `Probe` ABC; **do not edit** (snapshot-frozen)

## Goal

`await coordinator.gather(snapshot, task, probes, config, cache, sanitizer)` returns a `GatherResult(outputs: dict[str, SanitizedProbeOutput], executions: dict[str, ProbeExecution])`; dispatch is bounded by `asyncio.Semaphore(min(os.cpu_count() or 1, config.max_concurrent_probes, 8))` (ADR-0005); `tier="base"` probes run in a prelude pass and enrich the snapshot for downstream probes via `dataclasses.replace` (Gap 4); per-probe `wall_clock_s` and `raw_artifact_mb` budgets are enforced (Gap 3); every `ProbeOutput` flows through `_ProbeOutputValidator` then `OutputSanitizer.scrub` inside the coordinator (ADR-0010 → ADR-0008); cache hits short-circuit the chain (ADR-0009); failures are isolated into `ProbeOutput(errors=..., confidence="low")` (Edge case #1) with the gather continuing; lifecycle events (`probe.start | success | cache_hit | skip | failure | timeout | rss.warn`) are emitted under a `run_id`-bound structlog context (arch line 756).

## Acceptance criteria

ACs are grouped (A–J) so each section maps to a TDD test cluster and traces back to a Goal clause + an ADR / arch line.

### A — Module surface + frozen dataclasses

- [ ] **AC-1.** `src/codegenie/coordinator/snapshot.py` exports `build_snapshot(repo_root: Path, config: Config) -> RepoSnapshot` calling `await exec.run_allowlisted(["git", "rev-parse", "HEAD"], cwd=repo_root, timeout_s=10)`; on `DisallowedSubprocessError | ToolMissingError | ProbeTimeoutError | non-zero returncode` it returns `RepoSnapshot(git_commit=None, ...)`. `repo_root` is `.resolve()`d before being assigned to `RepoSnapshot.root`; downstream callers rely on `snapshot.root` being absolute (used by `OutputSanitizer.scrub`, AC-12).
- [ ] **AC-2.** `src/codegenie/coordinator/coordinator.py` exports the frozen dataclasses `Ran(output: SanitizedProbeOutput)`, `CacheHit(output: SanitizedProbeOutput, key: str)`, `Skipped(reason: str)`, the union alias `ProbeExecution = Ran | CacheHit | Skipped`, and `GatherResult(outputs: dict[str, SanitizedProbeOutput], executions: dict[str, ProbeExecution])`. **`SanitizedProbeOutput` (not `ProbeOutput`)** is the carried type — `src/codegenie/output/sanitizer.py:50` is the producer; the arch §Data model line 661-680 literal `ProbeOutput` claim is documented in the Validation notes as follow-up #1.
- [ ] **AC-3.** `async def gather(snapshot: RepoSnapshot, task: Task, probes: list[type[Probe]], config: Config, cache: CacheStore, sanitizer: OutputSanitizer) -> GatherResult` is the public surface; signature freezes here (ADR-0005 §Decision).
- [ ] **AC-4.** `outputs` vs `executions` **cardinality** is pinned: `executions[name]` is populated for every probe the coordinator was asked to dispatch; `outputs[name]` is populated **iff** `isinstance(executions[name], (Ran, CacheHit))` — `Skipped` produces no entry in `outputs`. CLI exit policy (arch line 483) reads `outputs` as `0 if any output.errors == [] else 2`.

### B — Bounded concurrency (ADR-0005)

- [ ] **AC-5.** Dispatch is bounded by `asyncio.Semaphore(min(os.cpu_count() or 1, config.max_concurrent_probes, 8))`. The `or 1` branch is exercised on platforms where `os.cpu_count()` returns `None` (cgroup-constrained containers); `min(None, ...)` would raise `TypeError`.
- [ ] **AC-6.** Peak concurrent dispatch equals — not just `≤` — the semaphore value under saturation. Tested with `asyncio.Event` synchronization, not `asyncio.sleep` timing.

### C — Failure isolation + cancellation (ADR-0005 + Edge case #1)

- [ ] **AC-7.** Probe exceptions are caught into `Ran(output=SanitizedProbeOutput(..., errors=[<repr>], confidence="low"))` for the **`Exception` hierarchy only** — `CancelledError`, `KeyboardInterrupt`, `SystemExit` propagate. A failed probe does NOT abort the gather; remaining probes complete. The error string carries the exception class name + the exception's `str()` so log/audit consumers can grep.
- [ ] **AC-8.** Failure-isolation contract is tested over `[ValueError, PermissionError, RuntimeError, KeyError, OSError]` (arch Edge case #1 names `PermissionError` specifically) plus a negative case asserting `raise KeyboardInterrupt` propagates out of `gather()`.
- [ ] **AC-9.** **Timeout window:** `await asyncio.wait_for(probe.run(snap, ctx), timeout=min(probe.timeout_seconds, probe.declared_resource_budget.wall_clock_s))`. The **tighter of the two** wins — a probe with `timeout_seconds=300, wall_clock_s=1` times out at ~1s. This resolves the `Probe.timeout_seconds=300` (frozen in `probes/base.py:62`) vs `ResourceBudget.wall_clock_s=30` collision.
- [ ] **AC-10.** **On timeout:** the task is `cancel()`'d, a 100ms grace window is awaited, then any tracked subprocess in `exec._RUNNING_PROCS` is SIGKILL'd by the coordinator. The resulting record is `Ran(output=SanitizedProbeOutput(errors=["timeout: <repr>"], confidence="low"))`. Phase 0 has no subprocess-shelling probe in the dispatch set, so the SIGKILL path is exercised via a fake probe that registers a `Mock` into `_RUNNING_PROCS` and asserts `proc.kill` was called.

### D — Validator → sanitizer chain (ADR-0010 → ADR-0008)

- [ ] **AC-11.** On cache-**miss** every `ProbeOutput` flows through `_ProbeOutputValidator.model_validate(...)` **then** `OutputSanitizer.scrub(po, repo_root=snapshot.root)` *inside* the coordinator (post-`run()`, pre-`cache.put`). `_ProbeOutputValidator` is lazy-imported inside `gather` (no `import pydantic` at module top — closes a CLI cold-start regression). Order is invariant: validator first (raises on secret-shaped keys before scrub gets the chance), sanitizer second.
- [ ] **AC-12.** `OutputSanitizer.scrub` receives `snapshot.root` (already absolute + `.resolve()`d by `build_snapshot`). A probe that emits `schema_slice={"root_path": str(snapshot.root / "foo")}` (a happy-path absolute path under the repo) lands in `outputs[name].schema_slice["root_path"]` as the **relative** form (`"foo"`). This is the load-bearing happy-path test: a mutant that omits the sanitizer call would still pass the secret-shaped test (because validator caught it), but fails here.
- [ ] **AC-13.** `_ProbeOutputValidator`'s `PydanticCustomError` wrapping (`validator.py:165-168`) is unwrapped by the coordinator: catch `pydantic.ValidationError`, walk `e.errors()[0]["ctx"]["error"]` to retrieve the typed `SecretLikelyFieldNameError`, and store `f"SecretLikelyFieldNameError: {key} at {path}"` in `output.errors[0]`. Test asserts the exact regex `^SecretLikelyFieldNameError: .+ at \(.+\)$` on the stored string.

### E — Cache hit short-circuit (ADR-0009)

- [ ] **AC-14.** On cache hit (`cache.get(key) is not None`): `probe.run` is NOT awaited, `_ProbeOutputValidator` is NOT invoked, `OutputSanitizer.scrub` is NOT invoked, `probe.applies` IS still consulted before the cache lookup (per ADR-0009 ordering: applies → cache → run). The `outputs[name]` value is `SanitizedProbeOutput(**asdict(po))` where `po` is the deserialized cached `ProbeOutput` (the field set is identical — `sanitizer.py:50` "mirrors `ProbeOutput` field-for-field").
- [ ] **AC-15.** `CacheHit.key` carries the SHA-256 identity tuple returned by `cache.key_for(probe, snapshot, task)` (per ADR-0009 line 41; used by S3-06's audit writer). Assertion: `result.executions[name].key == cache.key_for(probe, snapshot, task)`.

### F — Prelude pass (Gap 4)

- [ ] **AC-16.** The coordinator partitions probes by `tier`; all `tier == "base"` probes complete (via `asyncio.gather(..., return_exceptions=False)` — they pass through the normal try/except as in AC-7); the coordinator then constructs `enriched_snapshot = dataclasses.replace(snapshot, detected_languages=prelude_output["language_stack"]["counts"])` and dispatches the remaining probes against `enriched_snapshot`. The coordinator docstring documents the seam, citing Gap 4 and naming this `dataclasses.replace` line as the load-bearing point.
- [ ] **AC-17.** **Prelude failure / missing-key semantics (fail-loud).** If every prelude probe ends in `Ran(errors=[...])`, `Skipped`, or emits no `language_stack.counts` key (or emits an empty dict), the coordinator: (a) emits `prelude.degraded` structlog event carrying `prelude_errors=[...]` and `prelude_skipped=[...]` lists, (b) dispatches the second pass against the **original** `snapshot` (empty `detected_languages={}`). It does NOT crash with `KeyError`; it does NOT silently dispatch with `{}` (the explicit warning is the load-bearing fail-loud surface per Rule 12).
- [ ] **AC-18.** **Snapshot isolation.** Each probe's `RepoSnapshot` argument is the result of `dataclasses.replace(...)` (a fresh instance per dispatch pass), so a probe that mutates its `snapshot.detected_languages` in-place during `run()` cannot leak state into another probe's view. `RepoSnapshot` is not `frozen=True` in `probes/base.py:24` (ADR-0007 freezes the field set, not the keyword); this is the runtime defense.

### G — `applies()` filter + Skipped (ADR-0009)

- [ ] **AC-19.** Before cache lookup, the coordinator calls `probe.applies(enriched_snapshot, task)` (or `snapshot` for prelude probes); `False` → `executions[name] = Skipped(reason="applies() returned False")`, no `outputs[name]` entry, `probe.skip` event emitted, `cache.get` not called, `probe.run` not called. Tested with a fake probe whose `applies` returns `False`; assertion: `probe.run.await_count == 0` and `cache.get.call_count == 0`.

### H — Resource budget (Gap 3)

- [ ] **AC-20.** **`ResourceBudget` + `BudgetingContext` contract pin.** `coordinator/budget.py` exports the frozen dataclasses `ResourceBudget(rss_mb=200, raw_artifact_mb=10, wall_clock_s=30)` (the default) and `BudgetingContext(workspace: Path, raw_artifact_mb: int)`. **The contract is callback-based**: the probe writes to `ProbeContext.workspace` (a plain `pathlib.Path`, ADR-0007-frozen) and MUST call `ctx.report_bytes(n)` before/after every artifact write; `report_bytes` increments a `bytes_written` counter and raises `ProbeBudgetExceeded` when `bytes_written / (1024 * 1024) > raw_artifact_mb`. The default lives in `coordinator/budget.py`, NOT in `probes/base.py` (ADR-0007 forbids editing the ABC); the coordinator reads `getattr(probe_cls, "declared_resource_budget", DEFAULT_RESOURCE_BUDGET)`.
- [ ] **AC-21.** `raw_artifact_mb` boundary behavior is parametrized over `[(0.5 MB, no_error), (1.0 MB, no_error), (1.5 MB, errors_mention_raw_artifact_mb)]`. Pins `>` vs `>=` ambiguity and kills the "always-error" mutant.
- [ ] **AC-22.** **RSS is advisory only** in Phase 0: a high-water-mark crossing emits a `probe.rss.warn` structlog event carrying `peak_rss_mb`, `budget_mb`, and `probe=<name>`; the gather considers the probe successful (`Ran(output)`, no entry added to `output.errors`, original `output.confidence` preserved). Tested with `structlog.testing.capture_logs()` (NOT `caplog` — structlog's `WriteLoggerFactory` does not route through stdlib logging; `tests/unit/test_exec.py:285` is the precedent).

### I — Lifecycle events + run_id (arch line 755-756, ADR-0009)

- [ ] **AC-23.** `gather()` generates `run_id = secrets.token_hex(8)` once at entry and binds it via `structlog.contextvars.bind_contextvars(run_id=run_id)` so every `probe.*` event emitted within the gather carries `run_id=...`. Test captures the event stream and asserts every event carries the same `run_id`.
- [ ] **AC-24.** Lifecycle structlog events emitted (names match arch §Harness engineering / Logging line 755 + ADR-0009 line 41 exactly): `probe.start`, `probe.success`, `probe.cache_hit`, **`probe.skip`** (the previously omitted one), `probe.failure`, `probe.timeout`, `probe.rss.warn`. Each event carries `probe=<name>`, `run_id=<...>`, and where relevant `duration_ms`, `cache_key`, `reason`.

### J — Code hygiene + metamorphic invariants

- [ ] **AC-25.** `ruff check . && ruff format --check .`, `mypy --strict src/codegenie/coordinator/`, and `pytest tests/unit/test_coordinator*.py` are clean on the touched files. `pydantic.mypy` plugin is enabled (per S1-02). No `import pydantic` at the top of `coordinator.py` — only inside `gather`'s body — and an AST-scan test (`test_coordinator_no_top_level_pydantic_import`) enforces this.
- [ ] **AC-26.** **Order invariance (metamorphic):** `await gather(snap, task, [p1, p2, p3], cfg, cache, san)` and `await gather(snap, task, [p3, p1, p2], cfg, cache, san)` produce equal `outputs` dicts and equal key sets in `executions`. Closes the "secretly order-dependent state" mutant class.
- [ ] **AC-27.** **Idempotent re-run (metamorphic):** a second call to `gather()` with identical inputs produces `executions` where every entry is `CacheHit` (Phase 0 has one probe; this is the canonical second-run shape) and `outputs[name]` equals the first call's value field-for-field.
- [ ] **AC-28.** **Empty probe list:** `await gather(snap, task, [], cfg, cache, san)` returns `GatherResult({}, {})`; `run_id` is still generated; no `probe.*` events are emitted (only a single `gather.start` / `gather.end` envelope event, optional).
- [ ] **AC-29.** **`executions` dict full invariant** (single test, heterogeneous 4-probe mix — success, fail, timeout, cache-hit): `set(result.executions.keys()) == {p.name for p in probes}` AND `set(result.outputs.keys()) == {p.name for p in probes if isinstance(result.executions[p.name], (Ran, CacheHit))}`. Kills the "omit-failed-from-executions" mutant.

## Implementation outline

1. Author `src/codegenie/coordinator/snapshot.py`: `build_snapshot(repo_root, config) -> RepoSnapshot`. `repo_root` is `.resolve()`'d up front. Catches `DisallowedSubprocessError`/`ToolMissingError`/`ProbeTimeoutError` plus a non-zero `git rev-parse` exit cleanly and falls back to `git_commit=None`. Returns a `RepoSnapshot` with empty `detected_languages={}` initially (`RepoSnapshot` is not actually `frozen=True` in `probes/base.py`, ADR-0007 freezes the field set, not the keyword — see Validation notes follow-up).
2. Author `src/codegenie/coordinator/budget.py`:
   - `ResourceBudget(rss_mb=200, raw_artifact_mb=10, wall_clock_s=30)` — frozen dataclass; the **default**.
   - `BudgetingContext(workspace: Path, raw_artifact_mb: int)` — non-frozen helper with a `bytes_written: int` accumulator and a `report_bytes(n: int) -> None` callback. `workspace` stays a plain `pathlib.Path` (ADR-0007 freezes `ProbeContext.workspace: Path` in `probes/base.py:40`). `report_bytes` raises `ProbeBudgetExceeded` (subclass of `CodegenieError`) when cumulative `bytes_written / (1024 * 1024) > raw_artifact_mb`.
   - The default budget lives here; the coordinator reads `getattr(probe_cls, "declared_resource_budget", DEFAULT_RESOURCE_BUDGET)`.
3. Author `src/codegenie/coordinator/coordinator.py`:
   - Frozen dataclasses: `Ran(output: SanitizedProbeOutput)`, `CacheHit(output: SanitizedProbeOutput, key: str)`, `Skipped(reason: str)`. Type alias `ProbeExecution = Ran | CacheHit | Skipped`. `GatherResult(outputs: dict[str, SanitizedProbeOutput], executions: dict[str, ProbeExecution])`.
   - `_dispatch_one(probe, snapshot, task, sem, cache, sanitizer)`:
     1. `if not probe.applies(snapshot, task)` → emit `probe.skip(reason=...)`, return `(name, None, Skipped(reason=...))`.
     2. `key = cache.key_for(probe, snapshot, task)`.
     3. `cached = cache.get(key)`. **Hit:** wrap `SanitizedProbeOutput(**asdict(cached))`, emit `probe.cache_hit`, return `(name, sanitized, CacheHit(sanitized, key))`. **Miss:** continue.
     4. Build `BudgetingContext(workspace=ctx_workspace, raw_artifact_mb=budget.raw_artifact_mb)`; build `ProbeContext`.
     5. `timeout = min(probe.timeout_seconds, budget.wall_clock_s)`.
     6. `try: po = await asyncio.wait_for(probe.run(snapshot, ctx), timeout=timeout)`.
        - `except asyncio.TimeoutError:` cancel task, await 100ms grace, kill any tracked `exec._RUNNING_PROCS` whose `proc.returncode is None`, build `ProbeOutput(errors=[f"timeout: {timeout}s"], confidence="low", ...)`.
        - `except ProbeBudgetExceeded as e:` build `ProbeOutput(errors=[f"raw_artifact_mb exceeded: ..."], confidence="low", ...)`.
        - `except pydantic.ValidationError as e:` — re-raised from validator step (5). Unwrap `e.errors()[0]["ctx"]["error"]` → typed `SecretLikelyFieldNameError`. Build `ProbeOutput(errors=[f"SecretLikelyFieldNameError: <key> at <path>"], confidence="low", ...)`.
        - `except Exception as e:` build `ProbeOutput(errors=[f"{type(e).__name__}: {e}"], confidence="low", ...)`. **`CancelledError`, `KeyboardInterrupt`, `SystemExit` are not caught** — they propagate.
     7. On success: validate via lazy-imported `_ProbeOutputValidator.model_validate({"schema_slice": po.schema_slice, "confidence": po.confidence})` (Pydantic-wraps `PydanticCustomError` for secret keys; the try/except in step 6 catches `ValidationError`).
     8. `sanitized = sanitizer.scrub(po, repo_root=snapshot.root)`.
     9. `cache.put(key, sanitized)` (cache.put currently accepts `ProbeOutput`; `SanitizedProbeOutput` has the same field shape — see Validation notes follow-up #2).
     10. Return `(name, sanitized, Ran(sanitized))`.
   - `_dispatch_one` runs entirely inside the semaphore.
   - `gather(...)`:
     - Generate `run_id = secrets.token_hex(8)`.
     - `with structlog.contextvars.bound_contextvars(run_id=run_id):` (or `bind_contextvars` + reset).
     - Build the `Semaphore(min(os.cpu_count() or 1, config.max_concurrent_probes, 8))`.
     - Partition probes by `tier`: `base = [p for p in probes if p.tier == "base"]`, `rest = [p for p in probes if p.tier != "base"]`.
     - Run base via `asyncio.gather(*[_dispatch_one(...) for cls in base])`. Compute `enriched_snapshot`:
       - For each base probe whose execution is `Ran(output)` with a `language_stack.counts` dict, merge counts.
       - If no base probe produced counts (all failed/skipped/missing-key), emit `prelude.degraded` with the prelude error list, use the original snapshot.
     - Run rest via `asyncio.gather(*[_dispatch_one(cls, enriched_snapshot, task, ...) for cls in rest])`.
     - Merge dicts (`Skipped` execs add no `outputs` entry).
     - Return `GatherResult(outputs, executions)`.
4. RSS sampling: introduce a hook `_sample_rss_mb() -> int` (uses `resource.getrusage` on Unix; returns `0` on Windows; test-monkeypatchable). The coordinator calls it after each probe completes; if `peak > budget.rss_mb`, emits `probe.rss.warn(peak_rss_mb=..., budget_mb=..., probe=...)` — never raises.
5. Write tests covering each anchored behavior. The Section A/B/C/E/I/J tests share fixtures (`fresh_cache`, `fresh_sanitizer`, `fresh_config`) defined in `tests/unit/conftest.py`.

## TDD plan — red / green / refactor

Test file paths: `tests/unit/test_coordinator.py` (sections A/B/C/D/E/G/I/J), `tests/unit/test_coordinator_prelude.py` (section F), `tests/unit/test_coordinator_budget.py` (section H).

A shared `tests/unit/_coordinator_fixtures.py` carries the fakes (the real `LanguageDetectionProbe` ships in S4-01, so Phase 0 tests use injectable fakes).

### Shared fixtures — `tests/unit/_coordinator_fixtures.py`

```python
"""Test fakes for S3-05. Real probes ship in S4-01."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable
from pathlib import Path
from logging import getLogger

from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot, Task


def make_snapshot(tmp_path: Path, **overrides: Any) -> RepoSnapshot:
    defaults: dict[str, Any] = dict(
        root=tmp_path.resolve(),
        git_commit=None,
        detected_languages={},
        config={},
    )
    defaults.update(overrides)
    return RepoSnapshot(**defaults)


def make_task() -> Task:
    return Task(type="__bullet_tracer__", options={})


@dataclass
class FakeProbe(Probe):
    """Configurable probe for coordinator tests. NOT @register_probe-d."""
    name: str = "fake"
    layer: str = "A"
    tier: str = "task_specific"  # set to "base" for prelude probes
    applies_to_tasks: list[str] = field(default_factory=lambda: ["*"])
    applies_to_languages: list[str] = field(default_factory=lambda: ["*"])
    requires: list[str] = field(default_factory=list)
    declared_inputs: list[str] = field(default_factory=list)
    timeout_seconds: int = 5
    cache_strategy: str = "none"

    # Test hooks:
    _run: Callable[[RepoSnapshot, ProbeContext], "asyncio.Awaitable[ProbeOutput]"] | None = None
    _applies: bool = True
    _seen_snapshots: list[RepoSnapshot] = field(default_factory=list)

    def applies(self, repo: RepoSnapshot, task: Task) -> bool:
        return self._applies

    def cache_key(self, repo: RepoSnapshot, task: Task) -> str:
        return f"sha256:{self.name}"

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:
        self._seen_snapshots.append(repo)
        if self._run is None:
            return ProbeOutput(
                schema_slice={self.name: True},
                raw_artifacts=[],
                confidence="high",
                duration_ms=1,
                warnings=[],
                errors=[],
            )
        return await self._run(repo, ctx)


def make_probe_context(tmp_path: Path) -> ProbeContext:
    return ProbeContext(
        cache_dir=tmp_path / "cache",
        output_dir=tmp_path / "out",
        workspace=tmp_path / "ws",
        logger=getLogger("test"),
        config={},
    )
```

### Red — write the failing tests first

```python
# tests/unit/test_coordinator.py
from __future__ import annotations

import asyncio
import os
import re
import time
from dataclasses import asdict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import structlog

from codegenie.coordinator.coordinator import (
    CacheHit, GatherResult, Ran, Skipped, gather,
)
from codegenie.output.sanitizer import OutputSanitizer, SanitizedProbeOutput
from codegenie.probes.base import ProbeOutput
from tests.unit._coordinator_fixtures import (
    FakeProbe, make_probe_context, make_snapshot, make_task,
)

# ---------- Section A: surface --------------------------------------------

@pytest.mark.asyncio
async def test_single_probe_dispatch_returns_ran(tmp_path, fresh_cache, fresh_sanitizer, fresh_config):
    """AC-2, AC-3 — happy path lands a SanitizedProbeOutput inside Ran."""
    probe = FakeProbe(name="p1")
    snap, task = make_snapshot(tmp_path), make_task()

    result = await gather(snap, task, [probe], fresh_config, fresh_cache, fresh_sanitizer)

    assert isinstance(result, GatherResult)
    assert isinstance(result.executions["p1"], Ran)
    assert isinstance(result.outputs["p1"], SanitizedProbeOutput)
    assert result.outputs["p1"].schema_slice == {"p1": True}


@pytest.mark.asyncio
async def test_outputs_dict_omits_skipped_probes(tmp_path, fresh_cache, fresh_sanitizer, fresh_config):
    """AC-4, AC-19 — Skipped probes populate executions, NOT outputs."""
    yes, no = FakeProbe(name="y"), FakeProbe(name="n", _applies=False)
    snap, task = make_snapshot(tmp_path), make_task()

    result = await gather(snap, task, [yes, no], fresh_config, fresh_cache, fresh_sanitizer)

    assert set(result.executions.keys()) == {"y", "n"}
    assert isinstance(result.executions["n"], Skipped)
    assert "applies()" in result.executions["n"].reason
    assert set(result.outputs.keys()) == {"y"}  # n absent from outputs

# ---------- Section B: bounded concurrency --------------------------------

@pytest.mark.asyncio
async def test_concurrency_peak_equals_semaphore_value(tmp_path, fresh_cache, fresh_sanitizer, fresh_config):
    """AC-5, AC-6 — deterministic peak-equality via asyncio.Event."""
    fresh_config.max_concurrent_probes = 2
    release = asyncio.Event()
    in_flight = 0
    peak = 0

    async def slow_run(_snap, _ctx):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await release.wait()
        in_flight -= 1
        return ProbeOutput({"ok": True}, [], "high", 1, [], [])

    probes = [FakeProbe(name=f"p{i}", _run=slow_run) for i in range(4)]
    snap, task = make_snapshot(tmp_path), make_task()

    gather_task = asyncio.create_task(
        gather(snap, task, probes, fresh_config, fresh_cache, fresh_sanitizer)
    )
    # Let scheduler interleave; then release.
    await asyncio.sleep(0.05)
    release.set()
    await gather_task

    assert peak == 2, f"expected peak==2 with Semaphore(2), got {peak}"


@pytest.mark.asyncio
async def test_cpu_count_none_falls_back_to_one(tmp_path, monkeypatch, fresh_cache, fresh_sanitizer, fresh_config):
    """AC-5 — `os.cpu_count() or 1` branch under cgroup-constrained envs."""
    monkeypatch.setattr(os, "cpu_count", lambda: None)
    fresh_config.max_concurrent_probes = 8
    probe = FakeProbe(name="p")
    snap, task = make_snapshot(tmp_path), make_task()

    result = await gather(snap, task, [probe], fresh_config, fresh_cache, fresh_sanitizer)

    assert isinstance(result.executions["p"], Ran)  # no TypeError from min(None, ...)

# ---------- Section C: failure isolation + cancellation -------------------

@pytest.mark.parametrize("exc_cls", [ValueError, PermissionError, RuntimeError, KeyError, OSError])
@pytest.mark.asyncio
async def test_failure_isolation_over_exception_types(tmp_path, fresh_cache, fresh_sanitizer, fresh_config, exc_cls):
    """AC-7, AC-8 — every Exception subclass is isolated into ProbeOutput.errors."""

    async def boom(_snap, _ctx):
        raise exc_cls("synthetic")

    raising = FakeProbe(name="bad", _run=boom)
    healthy = FakeProbe(name="ok")
    snap, task = make_snapshot(tmp_path), make_task()

    result = await gather(snap, task, [raising, healthy], fresh_config, fresh_cache, fresh_sanitizer)

    assert isinstance(result.executions["bad"], Ran)
    assert result.outputs["bad"].confidence == "low"
    assert any(exc_cls.__name__ in e for e in result.outputs["bad"].errors), result.outputs["bad"].errors
    assert isinstance(result.executions["ok"], Ran)
    assert result.outputs["ok"].errors == []


@pytest.mark.asyncio
async def test_keyboard_interrupt_propagates(tmp_path, fresh_cache, fresh_sanitizer, fresh_config):
    """AC-8 — BaseException (KeyboardInterrupt) MUST propagate, NOT be swallowed."""

    async def ctrl_c(_snap, _ctx):
        raise KeyboardInterrupt()

    probe = FakeProbe(name="boom", _run=ctrl_c)
    snap, task = make_snapshot(tmp_path), make_task()

    with pytest.raises(KeyboardInterrupt):
        await gather(snap, task, [probe], fresh_config, fresh_cache, fresh_sanitizer)


@pytest.mark.asyncio
async def test_timeout_uses_min_of_timeout_and_wall_clock_budget(tmp_path, fresh_cache, fresh_sanitizer, fresh_config):
    """AC-9 — tighter of probe.timeout_seconds vs declared_resource_budget.wall_clock_s wins."""
    from codegenie.coordinator.budget import ResourceBudget

    async def slow(_snap, _ctx):
        await asyncio.sleep(10)
        return ProbeOutput({}, [], "high", 0, [], [])

    probe = FakeProbe(name="slow", _run=slow, timeout_seconds=300)
    probe.declared_resource_budget = ResourceBudget(rss_mb=200, raw_artifact_mb=10, wall_clock_s=1)
    snap, task = make_snapshot(tmp_path), make_task()

    t0 = time.monotonic()
    result = await gather(snap, task, [probe], fresh_config, fresh_cache, fresh_sanitizer)
    elapsed = time.monotonic() - t0

    assert 0.95 < elapsed < 1.8, f"expected ~1s + grace, got {elapsed:.2f}"
    assert any("timeout" in e for e in result.outputs["slow"].errors)
    assert result.outputs["slow"].confidence == "low"


@pytest.mark.asyncio
async def test_timeout_invokes_sigkill_hook(tmp_path, fresh_cache, fresh_sanitizer, fresh_config):
    """AC-10 — on timeout, tracked subprocesses in exec._RUNNING_PROCS are SIGKILL'd."""
    import codegenie.exec as exec_mod

    fake_proc = MagicMock()
    fake_proc.returncode = None  # alive

    async def register_then_sleep(_snap, _ctx):
        exec_mod._RUNNING_PROCS[424242] = fake_proc
        await asyncio.sleep(10)
        return ProbeOutput({}, [], "high", 0, [], [])

    probe = FakeProbe(name="tk", _run=register_then_sleep, timeout_seconds=1)
    snap, task = make_snapshot(tmp_path), make_task()

    await gather(snap, task, [probe], fresh_config, fresh_cache, fresh_sanitizer)

    fake_proc.kill.assert_called()  # coordinator killed the tracked child

# ---------- Section D: validator → sanitizer chain ------------------------

@pytest.mark.asyncio
async def test_validator_blocks_secret_shaped_field(tmp_path, fresh_cache, fresh_sanitizer, fresh_config):
    """AC-11, AC-13 — _ProbeOutputValidator catches secret-shaped keys before scrub."""

    async def emit_secret(_snap, _ctx):
        return ProbeOutput({"api_key": "abc"}, [], "high", 1, [], [])

    probe = FakeProbe(name="leak", _run=emit_secret)
    snap, task = make_snapshot(tmp_path), make_task()

    result = await gather(snap, task, [probe], fresh_config, fresh_cache, fresh_sanitizer)

    assert isinstance(result.executions["leak"], Ran)
    assert result.outputs["leak"].confidence == "low"
    err = result.outputs["leak"].errors[0]
    assert re.match(r"^SecretLikelyFieldNameError: .+ at \(.+\)$", err), err


@pytest.mark.asyncio
async def test_sanitizer_scrubs_absolute_paths_on_happy_path(tmp_path, fresh_cache, fresh_sanitizer, fresh_config):
    """AC-12 — sanitizer rewrites <repo>/foo → foo. Kills the omit-sanitizer mutant."""
    snap, task = make_snapshot(tmp_path), make_task()
    abs_path = str(snap.root / "deep" / "thing.json")

    async def emit_path(_snap, _ctx):
        return ProbeOutput({"root_path": abs_path}, [], "high", 1, [], [])

    probe = FakeProbe(name="pathy", _run=emit_path)

    result = await gather(snap, task, [probe], fresh_config, fresh_cache, fresh_sanitizer)

    out = result.outputs["pathy"]
    assert isinstance(out, SanitizedProbeOutput)
    assert out.schema_slice["root_path"] == "deep/thing.json"  # repo-relative
    assert str(snap.root) not in out.schema_slice["root_path"]


@pytest.mark.asyncio
async def test_no_top_level_pydantic_import_in_coordinator():
    """AC-25 — `import pydantic` must not appear at top of coordinator.py."""
    import ast
    import pathlib
    src = pathlib.Path("src/codegenie/coordinator/coordinator.py").read_text()
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "pydantic" not in alias.name, f"top-level import of {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            assert node.module is None or "pydantic" not in node.module, node.module

# ---------- Section E: cache-hit short-circuit ----------------------------

@pytest.mark.asyncio
async def test_cache_hit_short_circuits_chain(tmp_path, fresh_cache, fresh_sanitizer, fresh_config):
    """AC-14 — on hit, run/validator/sanitizer all skipped; outputs is SanitizedProbeOutput."""
    cached = ProbeOutput({"hit": True}, [], "high", 1, [], [])
    probe = FakeProbe(name="warm")
    probe.run = AsyncMock(side_effect=AssertionError("run must not be called"))

    snap, task = make_snapshot(tmp_path), make_task()
    key = fresh_cache.key_for(probe, snap, task)
    fresh_cache.put(key, cached)

    with patch("codegenie.coordinator.validator._ProbeOutputValidator.model_validate") as mv, \
         patch.object(fresh_sanitizer, "scrub", wraps=fresh_sanitizer.scrub) as sp:
        result = await gather(snap, task, [probe], fresh_config, fresh_cache, fresh_sanitizer)

    assert mv.call_count == 0  # validator skipped
    assert sp.call_count == 0  # sanitizer skipped
    assert probe.run.await_count == 0
    assert isinstance(result.executions["warm"], CacheHit)
    assert result.executions["warm"].key == key
    assert isinstance(result.outputs["warm"], SanitizedProbeOutput)
    assert result.outputs["warm"].schema_slice == {"hit": True}

# ---------- Section I: lifecycle events + run_id --------------------------

@pytest.mark.asyncio
async def test_every_lifecycle_event_carries_run_id(tmp_path, fresh_cache, fresh_sanitizer, fresh_config):
    """AC-23, AC-24 — run_id is bound once and on every probe.* event."""
    probes = [FakeProbe(name=f"p{i}") for i in range(3)]
    snap, task = make_snapshot(tmp_path), make_task()

    with structlog.testing.capture_logs() as captured:
        await gather(snap, task, probes, fresh_config, fresh_cache, fresh_sanitizer)

    probe_events = [e for e in captured if e["event"].startswith("probe.")]
    assert probe_events, "no probe.* events emitted"
    run_ids = {e.get("run_id") for e in probe_events}
    assert len(run_ids) == 1 and next(iter(run_ids)), f"run_id drift: {run_ids}"


@pytest.mark.asyncio
async def test_probe_skip_event_emitted_with_reason(tmp_path, fresh_cache, fresh_sanitizer, fresh_config):
    """AC-19, AC-24 — applies()-False → probe.skip event + Skipped execution."""
    probe = FakeProbe(name="n", _applies=False)
    snap, task = make_snapshot(tmp_path), make_task()

    with structlog.testing.capture_logs() as captured:
        await gather(snap, task, [probe], fresh_config, fresh_cache, fresh_sanitizer)

    skips = [e for e in captured if e["event"] == "probe.skip"]
    assert len(skips) == 1
    assert skips[0]["probe"] == "n"
    assert "applies()" in skips[0]["reason"]

# ---------- Section J: metamorphic + invariants ---------------------------

@pytest.mark.asyncio
async def test_gather_is_order_invariant(tmp_path, fresh_cache, fresh_sanitizer, fresh_config):
    """AC-26 — same probe set in different order → same outputs + execution keys."""
    def mk(name): return FakeProbe(name=name)
    snap, task = make_snapshot(tmp_path), make_task()

    r1 = await gather(snap, task, [mk("a"), mk("b"), mk("c")], fresh_config, fresh_cache, fresh_sanitizer)
    fresh_cache.clear()  # reset to compare runs from scratch
    r2 = await gather(snap, task, [mk("c"), mk("a"), mk("b")], fresh_config, fresh_cache, fresh_sanitizer)

    assert {k: asdict(v) for k, v in r1.outputs.items()} == \
           {k: asdict(v) for k, v in r2.outputs.items()}
    assert set(r1.executions.keys()) == set(r2.executions.keys())


@pytest.mark.asyncio
async def test_second_gather_is_all_cache_hits(tmp_path, fresh_cache, fresh_sanitizer, fresh_config):
    """AC-27 — idempotent re-run lands all CacheHits, outputs field-equal."""
    probes = [FakeProbe(name=f"p{i}") for i in range(2)]
    snap, task = make_snapshot(tmp_path), make_task()

    r1 = await gather(snap, task, probes, fresh_config, fresh_cache, fresh_sanitizer)
    # Re-create probes (run() is single-shot in this fake) but same names + cache.
    probes2 = [FakeProbe(name=f"p{i}") for i in range(2)]
    r2 = await gather(snap, task, probes2, fresh_config, fresh_cache, fresh_sanitizer)

    assert all(isinstance(e, CacheHit) for e in r2.executions.values())
    assert {k: asdict(v) for k, v in r1.outputs.items()} == \
           {k: asdict(v) for k, v in r2.outputs.items()}


@pytest.mark.asyncio
async def test_empty_probe_list_returns_empty_gather_result(tmp_path, fresh_cache, fresh_sanitizer, fresh_config):
    """AC-28 — gather([], ...) returns GatherResult({}, {}) without crashing."""
    snap, task = make_snapshot(tmp_path), make_task()

    result = await gather(snap, task, [], fresh_config, fresh_cache, fresh_sanitizer)

    assert result.outputs == {}
    assert result.executions == {}


@pytest.mark.asyncio
async def test_executions_dict_covers_all_dispatched_probes(tmp_path, fresh_cache, fresh_sanitizer, fresh_config):
    """AC-29 — heterogeneous mix: success + failure + timeout + cache-hit."""
    from codegenie.coordinator.budget import ResourceBudget

    async def ok(_s, _c): return ProbeOutput({"ok": True}, [], "high", 1, [], [])
    async def bad(_s, _c): raise RuntimeError("nope")
    async def slow(_s, _c): await asyncio.sleep(10); return ProbeOutput({}, [], "high", 0, [], [])

    p_ok = FakeProbe(name="ok", _run=ok)
    p_bad = FakeProbe(name="bad", _run=bad)
    p_to = FakeProbe(name="to", _run=slow, timeout_seconds=1)
    p_to.declared_resource_budget = ResourceBudget(rss_mb=200, raw_artifact_mb=10, wall_clock_s=1)
    p_hit = FakeProbe(name="hit")
    snap, task = make_snapshot(tmp_path), make_task()
    fresh_cache.put(fresh_cache.key_for(p_hit, snap, task),
                    ProbeOutput({"warm": True}, [], "high", 1, [], []))

    result = await gather(snap, task, [p_ok, p_bad, p_to, p_hit],
                          fresh_config, fresh_cache, fresh_sanitizer)

    assert set(result.executions.keys()) == {"ok", "bad", "to", "hit"}
    assert set(result.outputs.keys()) == {"ok", "bad", "to", "hit"}  # all Ran/CacheHit
    assert isinstance(result.executions["hit"], CacheHit)
    assert isinstance(result.executions["ok"], Ran)
    assert result.outputs["bad"].confidence == "low"
    assert any("timeout" in e for e in result.outputs["to"].errors)
```

```python
# tests/unit/test_coordinator_prelude.py — Section F (Gap 4)
from __future__ import annotations

import pytest

from codegenie.coordinator.coordinator import Ran, Skipped, gather
from codegenie.probes.base import ProbeOutput
from tests.unit._coordinator_fixtures import FakeProbe, make_snapshot, make_task


@pytest.mark.parametrize("counts", [
    {"javascript": 5, "typescript": 2},
    {"python": 3},
    {},
])
@pytest.mark.asyncio
async def test_prelude_pass_enriches_snapshot_for_downstream_probes(
    tmp_path, fresh_cache, fresh_sanitizer, fresh_config, counts
):
    """AC-16 — parametrized: prelude output drives enriched_snapshot.detected_languages."""
    async def base_run(_s, _c):
        return ProbeOutput({"language_stack": {"counts": counts}}, [], "high", 1, [], [])

    base = FakeProbe(name="lang", tier="base", _run=base_run)
    downstream = FakeProbe(name="ds", tier="task_specific")
    snap, task = make_snapshot(tmp_path), make_task()

    await gather(snap, task, [base, downstream], fresh_config, fresh_cache, fresh_sanitizer)

    assert downstream._seen_snapshots, "downstream never dispatched"
    assert downstream._seen_snapshots[0].detected_languages == counts


@pytest.mark.asyncio
async def test_no_base_tier_means_empty_enriched_languages(
    tmp_path, fresh_cache, fresh_sanitizer, fresh_config
):
    """AC-16 — no base-tier probe → downstream sees the original empty dict."""
    downstream = FakeProbe(name="ds", tier="task_specific")
    snap, task = make_snapshot(tmp_path), make_task()

    await gather(snap, task, [downstream], fresh_config, fresh_cache, fresh_sanitizer)

    assert downstream._seen_snapshots[0].detected_languages == {}


@pytest.mark.parametrize("scenario", [
    "prelude_failed",
    "missing_language_stack_key",
    "empty_counts",
])
@pytest.mark.asyncio
async def test_prelude_degraded_warns_and_continues_with_empty_languages(
    tmp_path, fresh_cache, fresh_sanitizer, fresh_config, scenario
):
    """AC-17 — fail-loud: when prelude can't supply counts, warn + dispatch with {}."""
    import structlog

    async def base_run(_s, _c):
        if scenario == "prelude_failed":
            raise PermissionError("/forbidden")
        if scenario == "missing_language_stack_key":
            return ProbeOutput({}, [], "low", 1, [], [])
        if scenario == "empty_counts":
            return ProbeOutput({"language_stack": {"counts": {}}}, [], "high", 1, [], [])
        raise AssertionError("unreachable")

    base = FakeProbe(name="lang", tier="base", _run=base_run)
    downstream = FakeProbe(name="ds", tier="task_specific")
    snap, task = make_snapshot(tmp_path), make_task()

    with structlog.testing.capture_logs() as captured:
        await gather(snap, task, [base, downstream], fresh_config, fresh_cache, fresh_sanitizer)

    # Downstream still dispatched, against empty detected_languages.
    assert downstream._seen_snapshots[0].detected_languages == {}
    # Warning event was emitted.
    if scenario != "empty_counts":
        assert any(e["event"] == "prelude.degraded" for e in captured), captured


@pytest.mark.asyncio
async def test_probe_mutation_of_snapshot_does_not_leak(
    tmp_path, fresh_cache, fresh_sanitizer, fresh_config
):
    """AC-18 — Probe-A mutating its snapshot.detected_languages cannot affect Probe-B."""
    async def malicious(_snap, _ctx):
        _snap.detected_languages["evil"] = 1
        return ProbeOutput({}, [], "high", 1, [], [])

    a = FakeProbe(name="a", _run=malicious)
    b = FakeProbe(name="b")
    snap, task = make_snapshot(tmp_path, detected_languages={"javascript": 1}), make_task()

    await gather(snap, task, [a, b], fresh_config, fresh_cache, fresh_sanitizer)

    # B's snapshot view does not contain "evil".
    assert "evil" not in b._seen_snapshots[0].detected_languages
```

```python
# tests/unit/test_coordinator_budget.py — Section H (Gap 3)
from __future__ import annotations

import pytest
import structlog

from codegenie.coordinator.budget import (
    BudgetingContext, ProbeBudgetExceeded, ResourceBudget,
)
from codegenie.coordinator.coordinator import Ran, gather
from codegenie.errors import CodegenieError
from codegenie.probes.base import ProbeContext, ProbeOutput
from tests.unit._coordinator_fixtures import FakeProbe, make_snapshot, make_task


# ---- Unit-level BudgetingContext contract --------------------------------

def test_budgeting_context_blocks_overrun(tmp_path):
    """AC-20 — direct unit test of the callback contract."""
    bc = BudgetingContext(workspace=tmp_path, raw_artifact_mb=1)
    bc.report_bytes(512 * 1024)  # 0.5 MB — ok
    bc.report_bytes(512 * 1024)  # cumulative 1.0 MB — at limit, ok
    with pytest.raises(ProbeBudgetExceeded):
        bc.report_bytes(1)  # one byte over → raise


def test_budgeting_context_workspace_stays_path(tmp_path):
    """AC-20 — `ProbeContext.workspace` MUST remain a plain pathlib.Path (ADR-0007 freeze)."""
    bc = BudgetingContext(workspace=tmp_path, raw_artifact_mb=1)
    assert isinstance(bc.workspace, type(tmp_path))


# ---- Coordinator-level enforcement ---------------------------------------

@pytest.mark.parametrize("mb_written,should_error", [
    (0.5, False),
    (1.0, False),
    (1.5, True),
])
@pytest.mark.asyncio
async def test_raw_artifact_budget_boundaries(
    tmp_path, fresh_cache, fresh_sanitizer, fresh_config,
    mb_written, should_error,
):
    """AC-21 — boundary parametrization kills always-error and >/>= mutants."""
    async def write_n(_snap, ctx):
        ctx.report_bytes(int(mb_written * 1024 * 1024))
        return ProbeOutput({"ok": True}, [], "high", 1, [], [])

    probe = FakeProbe(name="bg", _run=write_n)
    probe.declared_resource_budget = ResourceBudget(rss_mb=200, raw_artifact_mb=1, wall_clock_s=30)
    snap, task = make_snapshot(tmp_path), make_task()

    result = await gather(snap, task, [probe], fresh_config, fresh_cache, fresh_sanitizer)

    has_budget_err = any("raw_artifact_mb" in e for e in result.outputs["bg"].errors)
    assert has_budget_err == should_error
    if should_error:
        assert result.outputs["bg"].confidence == "low"


@pytest.mark.asyncio
async def test_rss_warning_is_advisory_not_fatal(
    tmp_path, fresh_cache, fresh_sanitizer, fresh_config, monkeypatch
):
    """AC-22 — probe.rss.warn emits, gather considers probe successful, no err appended."""
    # Coordinator uses a `_sample_rss()` hook (mockable) for advisory RSS checks.
    monkeypatch.setattr(
        "codegenie.coordinator.coordinator._sample_rss_mb",
        lambda: 999,  # well over the 200MB default
    )

    probe = FakeProbe(name="rssy")
    snap, task = make_snapshot(tmp_path), make_task()

    with structlog.testing.capture_logs() as captured:
        result = await gather(snap, task, [probe], fresh_config, fresh_cache, fresh_sanitizer)

    warns = [e for e in captured if e["event"] == "probe.rss.warn"]
    assert warns and warns[0]["probe"] == "rssy"
    assert warns[0]["peak_rss_mb"] >= 200
    assert isinstance(result.executions["rssy"], Ran)
    assert result.outputs["rssy"].errors == []  # advisory only — NO error appended
    assert result.outputs["rssy"].confidence == "high"  # preserved
```

Run all three test files; confirm `ImportError`/`AttributeError`. Commit as red marker.

### Green — make it pass

1. `coordinator/budget.py` first (small, no async).
2. `coordinator/snapshot.py` next (no async; pure async-subprocess call).
3. `coordinator/coordinator.py` last — this is the big one. Implement `_dispatch_one` first (single-probe path), then `gather` (prelude partition + main pass).
4. Wire `dataclasses.replace` for the prelude enrichment.
5. Make sure structlog events fire on every state transition.

Keep the prelude implementation **simple**: partition probes by `tier`, await `asyncio.gather` over the base-tier set, build `enriched_snapshot`, await `asyncio.gather` over the remainder. **Resist** building a generalized DAG scheduler (`phase-arch-design.md §Step 3 — risks`).

### Refactor — clean up

- Type hints throughout. `mypy --strict` clean on `src/codegenie/coordinator/` — `pydantic.mypy` plugin enabled (per S1-02 config; arch implementation-level risk #5).
- Docstrings on `gather`, every dataclass variant (`Ran`, `CacheHit`, `Skipped`, `GatherResult`), `BudgetingContext`, `ResourceBudget`, `build_snapshot`, `_dispatch_one`.
- Module docstring on `coordinator.py` cites ADR-0005, ADR-0007, ADR-0008, ADR-0009, ADR-0010 and walks the type-flow (`probe.run → ProbeOutput → validator → sanitizer → SanitizedProbeOutput → cache → Ran/CacheHit/Skipped`).
- The prelude-pass logic gets its own docstring section citing Gap 4, naming the `dataclasses.replace` line as the seam, AND naming the `prelude.degraded` warning as the fail-loud surface for AC-17.
- The budget logic gets its own docstring section citing Gap 3 and naming `BudgetingContext.report_bytes` as the probe-side enforcement point (the workspace stays a plain `Path`; the callback is the contract).
- Verify lifecycle event names match `phase-arch-design.md §Harness engineering / Logging` (line 755) + ADR-0009 (line 41) exactly: `probe.start`, `probe.success`, `probe.cache_hit`, `probe.skip`, `probe.failure`, `probe.timeout`, `probe.rss.warn`. No drift. AST-scan test (`test_lifecycle_event_names_match_arch`) reads the source file and asserts the literal strings are present.
- `_ProbeOutputValidator` is imported only inside `gather`'s body (lazy from CLI, per ADR-0010 §Consequences — see Validation notes follow-up #3 about the cli.py-vs-coordinator.gather module-boundary nuance). The top-of-file `import pydantic` ban is enforced by an AST-scan test (AC-25 + `test_coordinator_no_top_level_pydantic_import`).
- `run_id` is bound via `structlog.contextvars.bind_contextvars(run_id=...)` at the top of `gather`'s body and `clear_contextvars()` in a `finally` block so it does not leak into other event loops in the same process.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/coordinator/coordinator.py` | New — `gather`, `GatherResult`, `Ran/CacheHit/Skipped`, `_dispatch_one`, prelude partition, `_sample_rss_mb` hook, structlog event emission |
| `src/codegenie/coordinator/snapshot.py` | New — `build_snapshot` via `exec.run_allowlisted("git", ["rev-parse", "HEAD"], ...)`, falls back to `git_commit=None` cleanly |
| `src/codegenie/coordinator/budget.py` | New — `ResourceBudget`, `BudgetingContext.report_bytes`, `ProbeBudgetExceeded` (subclass of `CodegenieError`), `DEFAULT_RESOURCE_BUDGET` |
| `src/codegenie/errors.py` | **Edit (minor)** — add `ProbeBudgetExceeded(CodegenieError)` class. No other change. |
| `tests/unit/_coordinator_fixtures.py` | New — `FakeProbe`, `make_snapshot`, `make_task`, `make_probe_context` |
| `tests/unit/conftest.py` | **Edit** — add `fresh_cache`, `fresh_sanitizer`, `fresh_config` fixtures (pytest scope=`function`, hermetic) |
| `tests/unit/test_coordinator.py` | New — sections A, B, C, D, E, I, J (surface, concurrency, isolation, validator/sanitizer chain, cache-hit, lifecycle, metamorphic) |
| `tests/unit/test_coordinator_prelude.py` | New — section F (Gap 4 anchor + degraded-prelude scenarios + snapshot-isolation) |
| `tests/unit/test_coordinator_budget.py` | New — section H (Gap 3 anchor + boundary parametrization + advisory RSS) |

## Out of scope

- **`AuditWriter.record(...)` integration** — handled by S3-06 (which reads `CacheHit.key` from `executions` and the SHA-256 audit anchor).
- **`LanguageDetectionProbe` implementation** — handled by S4-01. Phase 0 coordinator tests use `FakeProbe(tier="base")` fakes.
- **CLI dispatch path** (parsing argv, exit codes, prompt-for-`.gitignore`, exit-code policy mapping `outputs` empty → 2) — handled by S4-02.
- **`cache gc` semantics** — stubbed in S4-02; not in this story.
- **RSS hard enforcement** — deferred to Phase 14 per `phase-arch-design.md §Gap analysis / Gap 3`. This story emits `probe.rss.warn` only; no error is appended; the probe is considered successful.
- **`Probe.applies()` filtering driving `Skipped` from a real probe** — Phase 0 has no probe whose `applies()` returns `False`. The coordinator contract is wired (AC-19) and tested with a fake probe; Phase 2's `IndexHealthProbe` and Phase 1's language-filtered probes light up real `Skipped` paths.
- **Editing `probes/base.py` to add `declared_resource_budget` to the `Probe` ABC** — explicitly forbidden by ADR-0007. The default lives in `coordinator/budget.py`; probes that need a non-default budget set the attribute on their subclass (e.g., Phase 2's trace probes). Phase 0 probes inherit the default via `getattr`.
- **`Path`-subclass `BudgetingContext`** — rejected (mypy/strict friction with `PurePath`/`Path` split). The callback approach (`ctx.report_bytes(n)`) is the Phase 0 contract; the trade-off is that a misbehaving probe that writes to `workspace` without calling `report_bytes` is unmonitored. Phase 0 has no artifact-writing probe; Phase 1+ probe-authoring guide MUST document the callback convention.
- **Cache.put/get type widening to `SanitizedProbeOutput`** — separate PR (Validation notes follow-up #2). `SanitizedProbeOutput` has identical fields to `ProbeOutput`; runtime serialization is unchanged.
- **Arch §Data model `Ran(output: ProbeOutput)` literal correction** — separate ADR amendment (Validation notes follow-up #1). The story implements the correct type; the doc lags.
- **OpenTelemetry / OTel span construction** from lifecycle events — Phase 13 (`run_id` is the seam being reserved here).
- **`probe.applies()` and prelude-failure semantics interaction** when an `applies()`-filtered probe sits in `tier="base"`: a base probe that returns `False` from `applies()` is `Skipped`; it contributes no counts to enrichment. Tested in AC-19 via fake; no special branching in coordinator.
- **Property-based testing via `hypothesis`** — explicitly excluded by `phase-arch-design.md §Property tests` (line 808). AC-26/27 use manual permutations (no fuzzing).
- **`cache.put` partial-write atomicity stress** — S3-01 covers, S5-01 stresses concurrent gather. This story trusts S3-01's `O_APPEND` + atomic-replace invariants.

## Notes for the implementer

1. **This story closes two Architect Gaps. Both are load-bearing for Phase 1+ — write the gap tests FIRST.** Per `phase-arch-design.md §Implementation-level risks` #2: "Land the four gap tests first (red), then the implementation (green) — TDD discipline on the gap items specifically, not on the rest of Step 3."
2. **Prelude pass is a single line:** `enriched = dataclasses.replace(snapshot, detected_languages=counts)` — do NOT over-engineer. `phase-arch-design.md §Step 3 — risks`: "Resist building a generalized DAG scheduler; that lands in Phase 1 if the six Layer A probes actually need it."
3. **Two timeout windows, two scopes — do NOT confuse them.**
   - **Coordinator-level (this story):** `asyncio.wait_for(timeout=min(probe.timeout_seconds, budget.wall_clock_s))` + `task.cancel()` + 100ms grace.
   - **Subprocess-level (S2-04's `exec.py`):** if a probe calls `exec.run_allowlisted`, that wrapper imposes its own SIGKILL at `1.5 × timeout_s` on the spawned binary. The coordinator's job on its own `wait_for` timeout is also to SIGKILL anything left in `exec._RUNNING_PROCS` that's still alive (AC-10).
4. **Type-flow:** `probe.run() → ProbeOutput → _ProbeOutputValidator.model_validate(...) → sanitizer.scrub(po, repo_root=snapshot.root) → SanitizedProbeOutput → cache.put(key, sanitized) → Ran(sanitized) / CacheHit(sanitized, key)`. Everywhere in `outputs[name]`, the type is `SanitizedProbeOutput`. The arch §Data model line 661-680 says `ProbeOutput` literally — that's a doc-lags-implementation gap (follow-up #1 in Validation notes).
5. **Cache hit short-circuits the validator + sanitizer.** The cache blob is the post-sanitize form; re-running validator+sanitizer would be wasteful and would change the cache-hit perf envelope (≤ 2 ms p95, arch line 482). On hit, the coordinator deserializes `cache.get` → `ProbeOutput` → `SanitizedProbeOutput(**asdict(po))` (cheap field copy; both have identical fields per `sanitizer.py:50`).
6. **`_ProbeOutputValidator` is lazy-imported** inside `gather`'s body (ADR-0010 §Consequences). At the top of `coordinator.py`, do not `import pydantic` and do not `from codegenie.coordinator.validator import _ProbeOutputValidator`. AST-scan test (AC-25) enforces.
7. **Edge case #5 (secret-shaped field) unwrap shape:** `_ProbeOutputValidator` raises `PydanticCustomError("secret_likely_field_name", ..., {"error": SecretLikelyFieldNameError(...), "key": key, "path": path_tuple})` from inside a `field_validator`. Pydantic wraps it in `ValidationError`. The coordinator catches `ValidationError`, walks `e.errors()[0]["ctx"]["error"]` to retrieve the typed instance, and writes `f"SecretLikelyFieldNameError: {key} at {path}"` into `output.errors[0]`. The error-string regex `^SecretLikelyFieldNameError: .+ at \(.+\)$` is pinned in AC-13.
8. **Failure isolation is `except Exception`** — `CancelledError`, `KeyboardInterrupt`, `SystemExit` propagate (AC-7/AC-8). The single positive failure-isolation test that exercises this is `test_keyboard_interrupt_propagates` (the negative-coverage case).
9. **`BudgetingContext` contract is callback-based** (AC-20). The probe writes to `ProbeContext.workspace` (`pathlib.Path`, untouched per ADR-0007) AND calls `ctx.report_bytes(n)` before/after each write. The probe-authoring guide (Phase 1) will codify the convention. A probe that writes without reporting bytes is unmonitored — Phase 0's `LanguageDetectionProbe` is metadata-only and never writes artifacts.
10. **RSS sampling hook (`_sample_rss_mb`)** is a module-level function the test can monkeypatch. Use `resource.getrusage(resource.RUSAGE_SELF).ru_maxrss` on Unix; return 0 on platforms that lack `resource` (Windows). The unit on `ru_maxrss` is platform-dependent (KB on Linux, bytes on macOS) — normalize to MB and document the formula.
11. **`run_id` lifetime.** Generated at `gather` entry, bound via `structlog.contextvars.bind_contextvars(run_id=run_id)`, cleared in a `finally` via `clear_contextvars()`. Without the finally clause, subsequent unit tests in the same process inherit the binding and the per-test event-stream isolation breaks.
12. **Strict mypy + pydantic v2 + `dataclasses.replace` friction** (`phase-arch-design.md §Implementation-level risks` #5). `pydantic.mypy` plugin is already in S1-02 config. Keep frozen-pydantic (`_ProbeOutputValidator`) and frozen-dataclass (`Ran`/`CacheHit`/`Skipped`) types segregated by module — never compose them in the same generic signature.
13. **`fresh_cache`/`fresh_sanitizer`/`fresh_config` fixtures** (added in `conftest.py`) construct hermetic instances under `tmp_path`. `fresh_config` uses default values + `max_concurrent_probes=4`; tests that need 1 or 2 mutate the field in place (the dataclass is frozen, but the fixture returns a fresh non-frozen wrapper to keep tests simple — adjust if `Config` was made fully frozen in S3-04).
14. **`Probe.applies()` ordering:** call `applies()` BEFORE `cache.key_for`/`cache.get`. A `False` `applies` short-circuits everything — no cache lookup, no `run()`, no chain. ADR-0009 §Decision specifies this ordering implicitly (Skipped → no output → no cache traffic).
15. **`probe.skip` event payload:** carries `probe=<name>`, `reason=<str>`, `run_id=<...>`. No `duration_ms` (the probe never ran). No `cache_key` (cache was never consulted).
