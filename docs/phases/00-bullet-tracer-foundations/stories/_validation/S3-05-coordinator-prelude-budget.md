# Validation report: S3-05 — Coordinator + prelude pass + resource budget

**Validated:** 2026-05-13
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1
**Story:** [`../S3-05-coordinator-prelude-budget.md`](../S3-05-coordinator-prelude-budget.md)

## Summary

S3-05 is the only L-effort story in Phase 0 and the densest harness-internals story in the phase. It assembles the async-bounded `Coordinator` that dispatches probes through the validator+sanitizer chain (the trust boundary), defines the `GatherResult` + `ProbeExecution = Ran | CacheHit | Skipped` shape that Phase 14 inherits unchanged, and closes **Architect Gap 3** (per-probe resource budget) and **Gap 4** (coordinator prelude pass). The story's bones — module surface, dispatch shape, gap-closure framing — were directionally right, but the AC set + TDD plan had **seven** load-bearing weaknesses and a constellation of smaller drift:

1. **Type-flow ambiguity across three sources.** Arch §Data model lines 661-680 literally declared `Ran(output: ProbeOutput)` and `GatherResult(outputs: dict[str, ProbeOutput], ...)`. ADR-0008 + `src/codegenie/output/sanitizer.py:50` mandates the carried type is `SanitizedProbeOutput`. The implementer note line 226 hedged "the sanitized form" without committing. `cache/store.py:88,246` types `ProbeOutput` for `put`/`get`. Three sources, three claims. An implementer reading only the AC would have shipped `Ran(output: ProbeOutput)`; reading only the implementer note would have shipped `Ran(output: SanitizedProbeOutput)`; either way some test breaks. Pinned the type as `SanitizedProbeOutput` (AC-2, AC-12, AC-14); filed two follow-ups (arch amendment + cache.put widening).
2. **Probe.timeout_seconds=300 vs ResourceBudget.wall_clock_s=30 collision.** AC-5 enforced `wait_for(probe.timeout_seconds)`, AC-9 said `wall_clock_s` was "already via wait_for." Two different defaults, same primitive — only one could win. Resolved: `wait_for(timeout=min(probe.timeout_seconds, budget.wall_clock_s))` (AC-9); test pins both directions.
3. **BudgetingContext contract punted to implementer.** Implementer note line 230 said "Pick one and document it." `ProbeContext.workspace: Path` is ADR-0007-frozen; the two options (Path subclass vs `ctx.report_bytes(n)` callback) have wildly different surfaces. Path subclassing fights `mypy --strict` and the `PurePath`/`Path` split. Pinned the callback approach (AC-20); workspace stays a plain `pathlib.Path`.
4. **Validator+sanitizer chain test was unrunnable.** `test_validator_and_sanitizer_run_in_coordinator` used a secret-shaped field → validator raises → sanitizer never runs. A mutant coordinator that *omits* the sanitizer entirely passes this test. Split into two ACs: AC-11 (validator blocks) + AC-12 (sanitizer scrubs `<repo>/foo` → `foo` on the happy path). The happy-path test asserts both the scrub result AND `isinstance(outputs[name], SanitizedProbeOutput)` — kills both the omit-sanitizer mutant and the wrong-output-stored mutant.
5. **Prelude-failure semantics undefined.** Implementation outline silently assumed `prelude_output["language_stack"]["counts"]` always exists. Reality: prelude probe can fail, emit no `language_stack` key, or emit empty counts. Three failure modes, three potential crashes. Pinned AC-17 (`prelude.degraded` warning + continue against original snapshot). Rule 12 — fail loud — was at risk.
6. **`...` test bodies across the entire TDD plan.** All 10 tests were pseudocode. S3-02/S3-03/S3-04 validations explicitly burned this antipattern (each rewrote the bodies as concrete runnable Python before greenlight). S3-05 — the **densest** L-effort story — had the **least** concrete test code. Rewrote every test body inline (~410 lines of real Python).
7. **`caplog` instead of `structlog.testing.capture_logs`.** `test_rss_warning_is_advisory_not_fatal(tmp_path, caplog)`. structlog's `WriteLoggerFactory` does not route through stdlib logging — `caplog` silently no-ops. Same trap S3-04 fell into and got fixed by the validator. `tests/unit/test_exec.py:285` is the precedent. Replaced.

Plus a constellation of smaller findings: `probe.skip` lifecycle event missing from AC-11 (ADR-0009 line 41 + arch line 755 both require it); `run_id` structlog binding absent (arch line 756 requires it for Phase 13's cost ledger and Phase 6's state ledger); `applies()` filter contract unenforced; `outputs[name]` vs `executions[name]` cardinality unpinned (Skipped → no output, Ran/CacheHit → output); `BaseException` carve-out missing from failure isolation; `PermissionError` (arch's named edge case) untested; `os.cpu_count() is None` branch untested; concurrency test timing-prone and satisfied by `Semaphore(1)` mutant; prelude pass single-shaped, satisfied by hardcoded constant; raw-artifact budget missing at-budget control case; SIGKILL/`1.5×` window misattributed to coordinator (it lives in `exec.py`); `OutputSanitizer.scrub`'s `repo_root` argument never threaded; snapshot-mutation isolation undefended; `import pydantic` AST-scan absent; metamorphic invariants (order invariance, idempotent re-run) absent; empty-probe-list edge case undefined; full executions-dict invariant test absent; cache-hit chain-skip behavior partially specified.

Three critics returned **42 findings** total (12 block, 26 harden, 4 nit) with **zero `NEEDS RESEARCH` tags** after the synthesizer cross-checked each finding against arch / ADR / existing code. Every gap was answerable from in-repo authoritative sources.

The validator applied edits in place:

- **Rewrote ACs from 11 (ungrouped) to 29 (grouped A–J).** Every AC names one observable behavior, traces back to a Goal clause + an ADR / arch line + an existing-code reference where relevant.
- **Expanded Goal** to cite ADR-0005/0007/0008/0009/0010 and the load-bearing rules (bounded concurrency, validator+sanitizer chain, lifecycle events, run_id binding, fail-loud on prelude degradation).
- **Rewrote the TDD plan end-to-end as ~410 lines of concrete runnable Python.** Three test files, shared `_coordinator_fixtures.py`, every test body executable.
- **Added a Validation notes block** under the story header (the 20-bullet detailed change log + 3 architectural follow-ups).
- **Pinned the type-flow** with a single canonical statement repeated across the Validation notes, Goal, AC-2/AC-12/AC-14, the implementation outline, and implementer note #4.
- **Fixed the `1.5×` misattribution** in the References block — the coordinator's grace window is 100ms; the `1.5× timeout_seconds` SIGKILL window lives in `exec.py`'s subprocess escalation.
- **Promoted three implementer-notes to ACs:** `BudgetingContext` callback shape (note → AC-20); `_ProbeOutputValidator` lazy-import + AST-scan ban (note → AC-25 + `test_coordinator_no_top_level_pydantic_import`); `applies()` filter ordering (out-of-scope → AC-19).
- **Added boundary-case parametrization** for the resource budget (`[0.5 MB, 1.0 MB, 1.5 MB]`) — kills the always-error mutant and pins the `>` vs `>=` boundary.
- **Added prelude-degradation parametrization** over three failure modes: probe failed (`PermissionError`), missing `language_stack` key, empty `counts` dict. All three must continue without crashing; the first two emit `prelude.degraded`.
- **Added snapshot-isolation test** — Probe-A mutates `snapshot.detected_languages` in-place; Probe-B sees an unmutated view via `dataclasses.replace`-fresh snapshot.
- **Added metamorphic invariants** (AC-26: order invariance; AC-27: idempotent re-run) using manual permutations — within Phase 0's "no hypothesis" rule.
- **Added the executions/outputs invariant test** (AC-29) — heterogeneous 4-probe mix (success + fail + timeout + cache-hit) asserts both dict keys.
- **Added the empty-probe-list edge case** (AC-28).
- **Added the `os.cpu_count() is None` branch test** (AC-5).
- **Added the `KeyboardInterrupt` propagation test** (AC-8) — closes the `except BaseException` mutant.
- **Added the `PermissionError` parametrization** to failure-isolation (AC-8) — arch §Edge cases row 1 names this specifically.
- **Replaced `caplog` with `structlog.testing.capture_logs`** in the RSS warning test (AC-22) — matches `tests/unit/test_exec.py:285`.
- **Replaced timing-prone concurrency test with `asyncio.Event` synchronization** (AC-6) — peak == 2 (not `≤`); a `Semaphore(1)` mutant fails.
- **Pinned the `PydanticCustomError` unwrap shape** (AC-13) — coordinator catches `ValidationError`, walks `e.errors()[0]["ctx"]["error"]` to retrieve the typed `SecretLikelyFieldNameError`, stores a regex-pinned error string.
- **Pinned the cache-hit short-circuit chain** (AC-14, AC-15) — validator/sanitizer/run all skipped; output is `SanitizedProbeOutput(**asdict(cached))`; `CacheHit.key` equals `cache.key_for(...)` for S3-06's audit anchor.
- **Pinned the lifecycle event set** (AC-24) — adds `probe.skip` (was missing), plus `run_id` + `probe` + relevant fields on every event.
- **Expanded the Implementation outline** with the explicit `_dispatch_one` step-by-step, the `_sample_rss_mb` hook, and the `bound_contextvars(run_id=...)` finally-clear pattern.
- **Expanded Files to touch** from 6 to 9 (added `_coordinator_fixtures.py`, `conftest.py` edit, `errors.py` edit for `ProbeBudgetExceeded`).
- **Expanded Out-of-scope** from 7 deferrals to 12 — explicit on RSS hard enforcement (Phase 14), `Path`-subclass rejection, cache.put type widening (separate PR), arch §Data model literal correction (separate ADR amendment), OTel deferred to Phase 13, `hypothesis`/`property-based` explicitly excluded per arch line 808.
- **Rewrote the implementer notes from 9 narrative paragraphs to 15 numbered notes** — each note answers a question an implementer would otherwise have to invent an answer to.

Three architectural follow-ups surfaced (not auto-fixed — outside this story's surgical scope per Rule 3):

1. **Arch §Data model lines 661-680 literal `Ran(output: ProbeOutput)`** should be amended to `Ran(output: SanitizedProbeOutput)` to match the implementation. Same for `GatherResult.outputs`. Separate ADR amendment PR (template at `docs/phases/00-bullet-tracer-foundations/ADRs/templates/adr-amendment.md`).
2. **`cache.put`/`cache.get` type signature** currently is `ProbeOutput`. Either widen to `ProbeOutput | SanitizedProbeOutput` or change to `SanitizedProbeOutput` (more correct; requires touching S3-01 code). Defer to a Phase 1 cleanup PR. Runtime serialization is unchanged because both dataclasses have identical field shapes.
3. **ADR-0010 §Consequences line 50** says `_ProbeOutputValidator` is lazy-imported from `cli.py`'s `gather` click-command body. The actual coordinator dispatch is inside `coordinator.gather`. Either amend ADR-0010 to allow the lazy import inside `coordinator.gather`, or add an explicit CLI-imports-coordinator-lazily rule to S4-02. Filed as Phase 0 cleanup (low-priority — both paths preserve cold-start as long as nothing else top-level-imports pydantic).

## Findings by critic

### Coverage critic — 18 findings (5 block, 12 harden, 1 nit; 0 needs-research after synthesis)

- **F1 (block)** — `Ran.output` / `outputs[name]` type ambiguity (`ProbeOutput` vs `SanitizedProbeOutput`). **→ AC-2, AC-12, AC-14 + follow-up #1.**
- **F2 (block)** — `outputs` vs `executions` cardinality contract unspecified for Skipped + errored Ran. **→ AC-4.**
- **F3 (harden)** — `probe.skip` lifecycle event missing. **→ AC-24.**
- **F4 (harden)** — `Probe.applies()` filter contract unenforced. **→ AC-19 + `test_probe_skip_event_emitted_with_reason`.**
- **F5 (harden)** — `run_id` structlog binding missing. **→ AC-23 + `test_every_lifecycle_event_carries_run_id`.**
- **F6 (block)** — Happy-path sanitizer test missing; existing test would pass on no-op sanitizer. **→ AC-12 + `test_sanitizer_scrubs_absolute_paths_on_happy_path`.**
- **F7 (harden)** — Cache-hit short-circuit chain unpinned. **→ AC-14, AC-15 + `test_cache_hit_short_circuits_chain`.**
- **F8 (harden)** — `BaseException` carve-out missing. **→ AC-7, AC-8 + `test_keyboard_interrupt_propagates`.**
- **F9 (harden)** — `PermissionError` (arch's named edge case) untested. **→ AC-8 parametrization over `[ValueError, PermissionError, RuntimeError, KeyError, OSError]`.**
- **F10 (block)** — Prelude-probe failure semantics unspecified. **→ AC-17 + `test_prelude_degraded_warns_and_continues_with_empty_languages`.**
- **F11 (block)** — `Probe.timeout_seconds` vs `ResourceBudget.wall_clock_s` collision. **→ AC-9 with `min(...)` + `test_timeout_uses_min_of_timeout_and_wall_clock_budget`.**
- **F12 (harden)** — Empty-probe-list edge case. **→ AC-28 + `test_empty_probe_list_returns_empty_gather_result`.**
- **F13 (harden)** — `RepoSnapshot` not actually `frozen=True`; mutation isolation undefended. **→ AC-18 + `test_probe_mutation_of_snapshot_does_not_leak`.**
- **F14 (block)** — `BudgetingContext` contract two-roads-not-taken (Path subclass vs callback). **→ AC-20 (callback) + `test_budgeting_context_blocks_overrun`.**
- **F15 (harden)** — SIGKILL-via-weakref AC-5 unverifiable in Phase 0. **→ AC-10 + `test_timeout_invokes_sigkill_hook` (fake-process registration).**
- **F16 (nit)** — Cache-key invariance under prelude enrichment not noted. **→ Implementer note #2 + #14.**
- **F17 (harden)** — All-probes-failed CLI exit-code policy contract. **→ AC-4 (`0 if any output.errors == [] else 2`).**
- **F18 (harden)** — Cumulative-gather budget deferral not noted. **→ Out-of-scope expansion.**

### Test-quality critic — 15 findings (4 block, 10 harden, 1 nit; 0 needs-research)

- **F1 (block)** — All 10 `...` test bodies. **→ Full TDD-plan rewrite (~410 lines real Python).**
- **F2 (block)** — `caplog` silently no-ops for structlog. **→ `structlog.testing.capture_logs` everywhere.**
- **F3 (block)** — `PydanticCustomError` wrapping unrunnable; "errors mentioning SecretLikelyFieldNameError" doesn't survive Pydantic's `__str__`. **→ AC-13 regex pin + `test_validator_blocks_secret_shaped_field`.**
- **F4 (harden)** — Failure-isolation uses `ValueError`; arch Edge case #1 names `PermissionError`. **→ AC-8 parametrization.**
- **F5 (harden)** — Cache-hit test missing call-count assertion. **→ `test_cache_hit_short_circuits_chain` with `mv.call_count == 0`, `sp.call_count == 0`, `probe.run.await_count == 0`.**
- **F6 (block)** — Validator+sanitizer "chain" test never exercises sanitizer. **→ Split into AC-11 + AC-12.**
- **F7 (harden)** — Timeout "small slack" unspecified. **→ AC-9 bounds `0.95 < elapsed < 1.8` + lower-bound assertion.**
- **F8 (harden)** — Prelude pass single-shaped. **→ AC-16 parametrization over `[{"python": 3}, {"javascript": 5, "typescript": 2}, {}]`.**
- **F9 (harden)** — Empty/failed/malformed base-tier branches missing. **→ AC-17 + `test_prelude_degraded_warns_and_continues_with_empty_languages`.**
- **F10 (harden)** — Raw-artifact budget no at-budget control. **→ AC-21 parametrization at `[0.5 MB, 1.0 MB, 1.5 MB]`.**
- **F11 (nit)** — `os.cpu_count() = None` branch untested. **→ AC-5 + `test_cpu_count_none_falls_back_to_one`.**
- **F12 (harden)** — Bounded-concurrency test relies on `asyncio.sleep` racing; satisfied by `Semaphore(1)` mutant. **→ AC-6 deterministic `asyncio.Event` synchronization, peak == 2 (not `≤`).**
- **F13 (harden)** — `executions` dict invariant never pinned as a whole. **→ AC-29 + `test_executions_dict_covers_all_dispatched_probes`.**
- **F14 (harden)** — No order-invariance / idempotent-re-run metamorphic tests. **→ AC-26, AC-27 + `test_gather_is_order_invariant` + `test_second_gather_is_all_cache_hits`.**
- **F15 (harden)** — `BudgetingContext` contract not pinned at unit level. **→ AC-20 + `test_budgeting_context_blocks_overrun` + `test_budgeting_context_workspace_stays_path`.**

### Consistency critic — 12 findings (4 block, 6 harden, 2 nit; 1 deferral)

- **F1 (block)** — `Ran.output` / `outputs[name]` / `cache.put` triple type collision. **→ AC-2 + follow-up #1, #2.**
- **F2 (block)** — Validate-then-cache-then-sanitize ordering incompatible with cache.put signature. **→ AC-11 + AC-14 reconciliation: cache stores sanitized form (field shapes match); cache-hit reconstructs typed signal.**
- **F3 (block)** — `BudgetingContext` cannot be `ProbeContext.workspace` because `workspace: Path` is ADR-0007-frozen. **→ AC-20 callback approach; workspace stays plain `Path`.**
- **F4 (harden)** — SIGKILL window: arch says `1.5×`, ADR-0005 says `100ms grace`, AC-5 mixed them. **→ References fix + Implementer note #3.**
- **F5 (harden)** — `Probe.timeout_seconds=300` vs `ResourceBudget.wall_clock_s=30` collision. **→ AC-9 `min(...)`.**
- **F6 (harden)** — `_ProbeOutputValidator` lazy-import location: ADR-0010 says `cli.py`, story says `coordinator.py`. **→ Follow-up #3 + AC-25 + AST-scan test.**
- **F7 (harden)** — `RepoSnapshot` not actually `frozen=True`. **→ Implementation outline correction + AC-18 + Implementer note #4.**
- **F8 (harden)** — `probe.skip` lifecycle event missing. **→ AC-24.**
- **F9 (harden)** — Sanitizer needs `repo_root`; coordinator dispatch didn't thread it. **→ AC-12 (`OutputSanitizer.scrub(po, repo_root=snapshot.root)`).**
- **F10 (harden)** — `run_id` required by arch, absent from every AC. **→ AC-23.**
- **F11 (nit)** — Cache key invariance under prelude enrichment unstated. **→ Implementer note #14.**
- **F12 (nit)** — Goal-to-AC trace gap. **→ Goal expansion.**

## Edits applied to the story file

### Edit 1 — References block (line ~26)

Removed the "SIGKILL at `1.5×`" misattribution at the coordinator level; clarified the two scopes (coordinator-level: `cancel + 100ms grace`; subprocess-level: SIGKILL at `1.5×` in `exec.py`).

### Edit 2 — Validation notes block (NEW, ~50 lines under header)

Added the standard "Hardened on 2026-05-13 by `phase-story-validator` v1" block with the 20-bullet detailed change log + 3 architectural follow-ups + finding-count summary.

### Edit 3 — Goal expansion

Expanded from a 60-word single sentence to a ~120-word multi-clause statement covering all load-bearing ADRs (0005, 0007, 0008, 0009, 0010) and the run_id / lifecycle-events contract.

### Edit 4 — Acceptance criteria rewrite (11 → 29)

Grouped into sections A-J (surface, concurrency, isolation, validator/sanitizer chain, cache hit, prelude, applies()/Skipped, budget, lifecycle, metamorphic). Every AC traces back to a Goal clause + an authoritative source. Listed line-by-line in the "Findings by critic" section above.

### Edit 5 — TDD plan rewrite (10 `...` tests → ~410 lines real Python)

Added `tests/unit/_coordinator_fixtures.py` block (`FakeProbe`, `make_snapshot`, `make_task`, `make_probe_context`). Rewrote every test with concrete assertions: imports, parametrization, fixtures (`fresh_cache`, `fresh_sanitizer`, `fresh_config`), exception-class parametrization, deterministic-event-based concurrency, time bounds, mock call-count assertions, AST scans, monkeypatched `os.cpu_count`/`_sample_rss_mb`, structlog capture, metamorphic permutations, idempotent-re-run.

### Edit 6 — Implementation outline expansion

From 5 narrative paragraphs to a 5-step plan with `_dispatch_one` broken into 10 sub-steps. Made the exception-handling pattern explicit (`except asyncio.TimeoutError` / `except ProbeBudgetExceeded` / `except pydantic.ValidationError` / `except Exception`, with `CancelledError`/`KeyboardInterrupt`/`SystemExit` not caught). Added the RSS sampling hook explicitly.

### Edit 7 — Refactor section

Tightened from 7 bullets to 7 sharper bullets with explicit line-citations (`phase-arch-design.md §Harness engineering / Logging` line 755; ADR-0009 line 41; ADR-0010 §Consequences). Added the `clear_contextvars()` finally-clause rule for `run_id` lifetime hygiene.

### Edit 8 — Files to touch

From 6 rows to 9 rows: added `tests/unit/_coordinator_fixtures.py`, `tests/unit/conftest.py` edit (fixtures), `src/codegenie/errors.py` edit (`ProbeBudgetExceeded`).

### Edit 9 — Out of scope

From 7 deferrals to 12: added explicit deferrals for `Path`-subclass `BudgetingContext` (rejected), cache.put type widening (separate PR), arch §Data model literal correction (separate ADR amendment), OTel (Phase 13), `hypothesis`-based property tests (excluded per arch line 808), `cache.put` partial-write atomicity (S3-01 / S5-01 territory), and the `applies()`-in-tier="base" interaction.

### Edit 10 — Notes for the implementer

From 9 narrative bullets to 15 numbered notes. Every note answers a question that the implementer would otherwise have to invent an answer to: two-scope timeout windows, type-flow walk-through, cache-hit short-circuit rationale, lazy-import location, `PydanticCustomError` unwrap shape, `except Exception` vs `BaseException`, `BudgetingContext` callback contract + the unmonitored-write trade-off, `_sample_rss_mb` hook + Linux/macOS `ru_maxrss` units, `run_id` lifecycle with `clear_contextvars`, mypy/pydantic friction, fixture scopes, `applies()` ordering, `probe.skip` event payload.

## Verdict

**HARDENED** — story had real but fixable weaknesses across all three critic lenses (coverage, test quality, consistency). 42 findings (12 block, 26 harden, 4 nit) applied as ~840 lines of new/changed story text. Story file has been edited in place and is ready for `phase-story-executor`. Three architectural follow-ups (arch §Data model literal, cache.put type widening, ADR-0010 lazy-import-location) are out-of-scope for this story per Rule 3 and surfaced in the Validation notes block for separate action.
