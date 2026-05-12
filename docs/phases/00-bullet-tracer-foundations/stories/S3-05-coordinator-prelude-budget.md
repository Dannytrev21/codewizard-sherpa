# Story S3-05 — Coordinator + prelude pass + resource budget

**Step:** Step 3 — Build the harness internals (cache, coordinator, validator, sanitizer, writer, config)
**Status:** Ready
**Effort:** L
**Depends on:** S3-01, S3-02, S3-03, S3-04
**ADRs honored:** ADR-0005, ADR-0009, ADR-0010, ADR-0008

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
  - `../phase-arch-design.md §Edge cases` rows 1, 2 — `PermissionError` mid-walk → `confidence="low"`; timeout → SIGKILL at `1.5×`
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0005-coordinator-async-from-day-one.md` — ADR-0005 — `asyncio.Semaphore(min(cpu, max_concurrent, 8))`, per-probe `wait_for`, cancel + 100ms grace + SIGKILL at `1.5×`
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

`await coordinator.gather(snapshot, task, probes, config, cache, sanitizer)` returns a `GatherResult(outputs, executions)`; `tier="base"` probes run in a prelude pass and enrich the snapshot for downstream probes; per-probe `wall_clock_s` and `raw_artifact_mb` budgets are enforced; failures are isolated into `ProbeOutput(errors=..., confidence="low")` with the gather continuing.

## Acceptance criteria

- [ ] `src/codegenie/coordinator/snapshot.py` exports `build_snapshot(repo_root, config) -> RepoSnapshot` calling `exec.run_allowlisted("git", ["rev-parse", "HEAD"], cwd=repo_root, timeout_s=10)`; non-git repos yield `git_commit=None`.
- [ ] `src/codegenie/coordinator/coordinator.py` exports the frozen dataclasses `Ran(output)`, `CacheHit(output, key)`, `Skipped(reason)`, the union alias `ProbeExecution`, and `GatherResult(outputs: dict[str, ProbeOutput], executions: dict[str, ProbeExecution])`.
- [ ] `async def gather(snapshot, task, probes, config, cache, sanitizer) -> GatherResult` is the public surface; the signature is the one ADR-0005 freezes.
- [ ] Bounded concurrency: `asyncio.Semaphore(min(os.cpu_count() or 1, config.max_concurrent_probes, 8))`.
- [ ] Per-probe `asyncio.wait_for(probe.timeout_seconds)`; on timeout, `cancel()` + 100ms grace, then SIGKILL through the `exec.py` weakref process table; the probe becomes `ProbeOutput(errors=["timeout"], confidence="low")`, `ProbeExecution=Ran`.
- [ ] Probe exceptions (non-`CodegenieError`) are caught into `ProbeOutput(errors=[...], confidence="low")`; the coordinator **never re-raises** (`final-design.md §2.6`).
- [ ] Each `ProbeOutput` flows through `_ProbeOutputValidator` **then** `OutputSanitizer.scrub` *inside* the coordinator (post-`run()`, pre-`cache.put`) — ADR-0010 + ADR-0008 chain.
- [ ] **Prelude pass (Gap 4):** the coordinator runs all probes whose `tier == "base"` first; constructs `enriched_snapshot = dataclasses.replace(snapshot, detected_languages=prelude_output["language_stack"]["counts"])` after the prelude completes; dispatches remaining probes against `enriched_snapshot`. Documented in the coordinator docstring.
- [ ] **Resource budget (Gap 3):** `Probe.declared_resource_budget` (`ResourceBudget(rss_mb=200, raw_artifact_mb=10, wall_clock_s=30)` default) is honored — `wall_clock_s` already via `wait_for`; `raw_artifact_mb` enforced by a `BudgetingContext` injected as `ProbeContext.workspace` tracking cumulative bytes; **RSS is advisory only** — log `probe.rss.warn` on high-water-mark crossing, do not abort.
- [ ] `executions[probe.name]` is populated for every probe the coordinator was asked to dispatch — `Ran`, `CacheHit`, or `Skipped`.
- [ ] Lifecycle structlog events emitted: `probe.start`, `probe.success`, `probe.cache_hit`, `probe.failure`, `probe.timeout`, `probe.rss.warn` (advisory only) — names match `phase-arch-design.md §Harness engineering / Logging`.
- [ ] All red tests below are green; `ruff`, `mypy --strict`, `pytest` clean on touched files.

## Implementation outline

1. Author `src/codegenie/coordinator/snapshot.py`: `build_snapshot(repo_root, config) -> RepoSnapshot`. Catches `DisallowedSubprocessError`/`ToolMissingError` cleanly and falls back to `git_commit=None`. Returns a frozen `RepoSnapshot` with empty `detected_languages={}` initially.
2. Author `src/codegenie/coordinator/budget.py` (small helper module): `ResourceBudget` frozen dataclass, `BudgetingContext` that wraps a `workspace: Path` and tracks bytes written; raises `ProbeBudgetExceeded` when `raw_artifact_mb` is breached.
3. Author `src/codegenie/coordinator/coordinator.py`:
   - Define `Ran`, `CacheHit`, `Skipped`, `ProbeExecution`, `GatherResult` as frozen dataclasses.
   - `_dispatch_one(probe, snapshot, task, sem, cache, sanitizer)`: cache key → cache.get → on hit emit `CacheHit` event + return; on miss create the `BudgetingContext`, build `ProbeContext`, `asyncio.wait_for(probe.run(snapshot, ctx), probe.timeout_seconds)`, validate, sanitize, `cache.put`, return `Ran`.
   - `_dispatch_one` runs entirely inside the semaphore.
   - `gather(...)`: partition probes by `tier` → run base-tier probes first (prelude); after all are done, build `enriched_snapshot`; dispatch the rest; merge `executions` + `outputs`.
4. Build `Probe.declared_resource_budget` as a class attribute default on the ABC (CAREFUL: do **not** edit `probes/base.py` because it's snapshot-frozen). Instead, declare the default in `coordinator/budget.py` and the coordinator reads `getattr(probe, "declared_resource_budget", DEFAULT)`. Document this as the intended seam.
5. Write tests covering each anchored behavior.

## TDD plan — red / green / refactor

The Coordinator has six anchored behaviors; write one red test per behavior.

### Red — write the failing tests first

Test file paths: `tests/unit/test_coordinator.py` (most behaviors), `tests/unit/test_coordinator_prelude.py` (Gap 4), `tests/unit/test_coordinator_budget.py` (Gap 3).

```python
# tests/unit/test_coordinator.py
import pytest
from codegenie.coordinator.coordinator import gather, Ran, CacheHit, Skipped, GatherResult

@pytest.mark.asyncio
async def test_single_probe_dispatch_returns_ran(tmp_path):
    # arrange: one trivial probe that returns ProbeOutput(...)
    # act: result = await gather(snapshot, task, [Probe], config, cache, sanitizer)
    # assert: result.outputs["probe_name"] is a ProbeOutput; result.executions["probe_name"] is Ran
    ...

@pytest.mark.asyncio
async def test_failure_isolation_continues_gather(tmp_path):
    # arrange: two probes — one raises ValueError mid-run, one returns OK
    # act: gather([raising, ok])
    # assert: raising is recorded as ProbeOutput(errors=[..."ValueError"...], confidence="low");
    #         ok produced normal output; coordinator did not re-raise.
    ...

@pytest.mark.asyncio
async def test_timeout_cancel_grace_then_sigkill(tmp_path):
    # arrange: probe whose run() awaits asyncio.sleep(100); timeout_seconds=1.
    # act: gather([probe])
    # assert: result.executions[name] is Ran with errors containing "timeout";
    #         total elapsed wall-clock <= 1.5s + small slack;
    #         the (mocked) subprocess kill path was invoked.
    ...

@pytest.mark.asyncio
async def test_cache_hit_returns_cachehit_variant(tmp_path):
    # arrange: pre-populate cache for probe's key
    # act: gather([probe])
    # assert: result.executions[name] is CacheHit; probe.run was NOT invoked;
    #         probe.cache_hit structlog event was emitted exactly once.
    ...

@pytest.mark.asyncio
async def test_validator_and_sanitizer_run_in_coordinator(tmp_path):
    # arrange: a probe that emits schema_slice={"api_key": "X"} (secret field)
    # act: gather([probe])
    # assert: result.executions[name] is Ran with errors mentioning SecretLikelyFieldNameError;
    #         the OutputSanitizer was invoked (mock or trace) for non-failing probes.
    ...

@pytest.mark.asyncio
async def test_bounded_concurrency_respects_config(tmp_path, monkeypatch):
    # arrange: 4 long-running probes; config.max_concurrent_probes=2;
    #          each probe records its concurrent-peer count via a shared counter.
    # assert: peak concurrent dispatch <= 2 at any time.
    ...
```

```python
# tests/unit/test_coordinator_prelude.py  (Gap 4 anchor)
@pytest.mark.asyncio
async def test_prelude_pass_enriches_snapshot_for_downstream_probes(tmp_path):
    """Gap 4: tier='base' probes run first; downstream probes see enriched detected_languages."""
    # arrange:
    #   - one base-tier probe that emits schema_slice={"language_stack":{"counts":{"javascript":5}}}
    #   - one downstream probe that records snapshot.detected_languages it received in a list
    # act: gather([base, downstream])
    # assert: downstream's recorded snapshot.detected_languages == {"javascript": 5}
    ...

@pytest.mark.asyncio
async def test_no_base_tier_probe_means_empty_enriched_languages(tmp_path):
    # arrange: only one non-base probe
    # act: gather([downstream])
    # assert: downstream saw detected_languages == {} (no prelude enrichment happened)
    ...
```

```python
# tests/unit/test_coordinator_budget.py  (Gap 3 anchor)
@pytest.mark.asyncio
async def test_raw_artifact_budget_cuts_off_overrunning_probe(tmp_path):
    """Gap 3: raw_artifact_mb is hard-enforced via BudgetingContext."""
    # arrange: probe.declared_resource_budget = ResourceBudget(raw_artifact_mb=1, ...).
    #          probe writes >1 MB to ProbeContext.workspace.
    # act: gather([probe])
    # assert: result.executions[name] is Ran with errors mentioning "raw_artifact_mb";
    #         only the budget'd amount actually landed under workspace (or no file at all);
    #         confidence == "low".
    ...

@pytest.mark.asyncio
async def test_rss_warning_is_advisory_not_fatal(tmp_path, caplog):
    """Gap 3: RSS enforcement is advisory in Phase 0; warn event only."""
    # arrange: probe whose simulated peak RSS exceeds budget (use a fake high-water-mark hook)
    # act: gather([probe])
    # assert: caplog contains a "probe.rss.warn" event; result.executions[name] is Ran with
    #         no error; gather considered the probe successful.
    ...
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

- Type hints throughout. `mypy --strict` clean — pydantic plugin enabled (per implementation risk #5).
- Docstrings on `gather`, every dataclass variant, `BudgetingContext`, `ResourceBudget`.
- Module docstring on `coordinator.py` cites ADR-0005, ADR-0009, ADR-0010, ADR-0008 and explains the validator+sanitizer chain.
- The prelude-pass logic gets its own docstring section citing Gap 4 and naming the `dataclasses.replace` line as the seam.
- The budget logic gets its own docstring section citing Gap 3 and naming `BudgetingContext` as the enforcement point.
- Verify lifecycle event names match `phase-arch-design.md §Harness engineering / Logging` exactly: `probe.start`, `probe.success`, `probe.cache_hit`, `probe.failure`, `probe.timeout`, `probe.rss.warn`. No drift.
- Re-confirm `_ProbeOutputValidator` is imported only inside `gather` (lazy from CLI), per ADR-0010 §Consequences.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/coordinator/coordinator.py` | New — async `gather`, `GatherResult`, `Ran/CacheHit/Skipped`, prelude pass, budget enforcement |
| `src/codegenie/coordinator/snapshot.py` | New — `build_snapshot` via `exec.run_allowlisted` |
| `src/codegenie/coordinator/budget.py` | New — `ResourceBudget`, `BudgetingContext`, `ProbeBudgetExceeded` (or reuse `errors.ProbeError`) |
| `tests/unit/test_coordinator.py` | New — base behaviors (dispatch, isolation, timeout, cache hit, validator chain, bounded concurrency) |
| `tests/unit/test_coordinator_prelude.py` | New — Gap 4 anchor |
| `tests/unit/test_coordinator_budget.py` | New — Gap 3 anchor |

## Out of scope

- **`AuditWriter.record(...)` integration** — handled by S3-06 (which wires it into the coordinator's output).
- **`LanguageDetectionProbe` implementation** — handled by S4-01.
- **CLI dispatch path** (parsing argv, exit codes, etc.) — handled by S4-02.
- **`cache gc` semantics** — stubbed in S4-02; not in this story.
- **RSS hard enforcement** — explicitly deferred to Phase 14 per `phase-arch-design.md §Gap analysis / Gap 3`. This story emits warnings only.
- **`Probe.applies()` filtering returning `Skipped`** — Phase 0 has no probe that returns `False` from `applies()`; the `Skipped` variant is defined but exercised only by tests that fake it. Phase 2 lights up real `Skipped` paths.
- **Reading `probes/base.py` to **edit** the ABC for `declared_resource_budget`** — explicitly forbidden by ADR-0007. The default lives in `coordinator/budget.py`; probes set the attribute on their subclass.

## Notes for the implementer

- **This story closes two Architect Gaps. Both are load-bearing for Phase 1+ — write the gap tests FIRST.** Per `phase-arch-design.md §Implementation-level risks` #2: "Land the four gap tests first (red), then the implementation (green) — TDD discipline on the gap items specifically, not on the rest of Step 3."
- The prelude pass is a single line: `enriched = dataclasses.replace(snapshot, detected_languages=prelude_output["language_stack"]["counts"])` — do not over-engineer. `phase-arch-design.md §Step 3 — risks` is explicit: "Resist building a generalized DAG scheduler; that lands in Phase 1 if the six Layer A probes actually need it."
- The `1.5 × timeout_seconds` SIGKILL window is encoded in `exec.py`'s `run_allowlisted` (already shipped by S2-04). The coordinator's job on `wait_for` timeout is to call `task.cancel()` + 100ms grace; the SIGKILL of subprocess children happens via `exec.py`'s weakref table.
- `_ProbeOutputValidator` is **lazy-imported** inside `gather` (per ADR-0010 §Consequences). At the top of `coordinator.py`, do not `import pydantic`. The CLI's cold-start budget depends on this.
- `OutputSanitizer.scrub` returns a `SanitizedProbeOutput`. The coordinator stores the sanitized form in `outputs` (so the CLI never sees a non-sanitized `ProbeOutput`). The `Ran(output)` variant carries the sanitized output.
- `CacheHit(output, key)` carries the **key** explicitly (ADR-0009 §Decision). S3-06 reads `key` from this variant when writing the audit record.
- Edge case #5 (secret-shaped field): `_ProbeOutputValidator` raises `SecretLikelyFieldNameError` (wrapped by Pydantic's `ValidationError` in a `field_validator`). The coordinator's `try/except` must unwrap or catch the wrapped form — the test will tell you which.
- Failure isolation means catching **everything except `CancelledError`** from a probe's `run()`. `BaseException`s (KeyboardInterrupt, SystemExit) should propagate. Use `except Exception as e` (not `except BaseException`).
- The `BudgetingContext` is a small class with a `bytes_written: int` counter and a `write(name, data)` method that the probe calls via `ProbeContext.workspace` (`probes/base.py` types `workspace: Path` — Phase 0's BudgetingContext is a *subclass-or-wrapper* that exposes the `Path` interface plus a bookkeeping method). Concretely, the probe writes via `Path.write_bytes` and the coordinator hooks the `Path` via a `pathlib.Path`-subclass or a `PathLike` adapter. Simpler: provide `ctx.workspace` as a `Path` and have the coordinator pre-pass a callback the probe should call (`ctx.report_bytes(n)`). Pick one and document it; tests pin the contract you chose.
- Strict mypy + pydantic v2 + `dataclasses.replace` can have friction (`phase-arch-design.md §Implementation-level risks` #5). Use the `pydantic.mypy` plugin (already in S1-02 config) and keep frozen-pydantic vs frozen-dataclass types segregated module-by-module.
