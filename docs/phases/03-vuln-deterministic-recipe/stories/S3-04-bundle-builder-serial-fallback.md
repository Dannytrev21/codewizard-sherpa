# Story S3-04 — `BundleBuilder` with `asyncio.Semaphore` concurrency + deterministic serial fallback (ADR-0008)

**Step:** Step 3 — TCCM, BundleBuilder, VulnIndex, content-addressed cache
**Status:** HARDENED
**Effort:** M
**Depends on:** S3-01
**ADRs honored:** Phase 3 ADR-0008 (deterministic serial fallback; NOT hedged-race — production commitment §2.4 is veto-strength), Phase 3 ADR-0010 (tagged-union / Literal discipline; sum-type dispatch via `match` + `assert_never`), Phase 3 ADR-0011 (honest framing — `SandboxedPath` is audit-grade), production ADR-0029 (TCCM `must_read`/`should_read`/`may_read`), production ADR-0030 (graph-aware query primitives), production ADR-0032 (language search adapters provide `AdapterConfidence`)

## Validation notes (2026-05-18 — `/phase-story-validator` HARDENED)

Four parallel critics (Coverage, Test-Quality, Consistency, Design-Patterns) produced 40+ findings; 4 blockers, 27 harden-level, the rest nits. Key changes applied in-place (full report at [`_validation/S3-04-bundle-builder-serial-fallback.md`](_validation/S3-04-bundle-builder-serial-fallback.md)):

- **`AdapterConfidence` is a tagged union (`Trusted | Degraded | Unavailable`), not an enum.** All `AdapterConfidence.High` references replaced with `Trusted`; all `confidence in {Degraded, Unavailable}` set-membership checks replaced with `match` + `assert_never` dispatch (Phase 3 ADR-0010). The set-membership form would always evaluate False (instance vs class identity) — block-level fix.
- **Adapter surface is `.confidence()` method + a typed `AdapterResult`, not `.confidence` attribute.** Phase 2 protocols (`src/codegenie/adapters/protocols.py`) expose `confidence(self) -> AdapterConfidence` as a callable. Also: no shared `.query(args)` method exists across protocols (each has `refs` / `consumers` / `reverse_lookup` / `tests_exercising`). S3-04 introduces a typed `AdapterDispatch` callable seam consumed via `resolution.composed_dispatch[primitive]`; the spy adapter exposes the same shape. Production wiring lives in S7-02.
- **`BundleBuilderError` is a frozen Pydantic `BaseModel` with `reason: Literal[...]`, not an `Exception` subclass.** Mirrors the S3-01 HARDENED resolution for `TCCMParseError` — markers-only + typed `.reason` reads were contradictory.
- **Semaphore is acquired per *band-level task*, not inside recursive `_run_one`.** The original prescription nested `async with semaphore:` inside the recursive fallback walker — a 4-deep degraded chain would have reserved 4 slots simultaneously, silently halving effective concurrency. Now: `build()` wraps each top-level query in a single `_acquire_then_dispatch` coroutine; the fallback walker (`_resolve_chain`) is iterative and never reacquires.
- **Fallback chain is iterative (`_resolve_chain`), not recursive.** Functional-core / imperative-shell preference (CLAUDE.md); also makes the depth-cap check explicit and avoids stack-holding-the-lock surprises.
- **Determinism property test now injects seeded scheduler jitter and is paired with an `xfail` meta-test against a deliberately broken hedged-race reference.** Without scheduler entropy the test is tautological — a future regression introducing hedged-race could pass 100/100 on a normal asyncio loop.
- **AST static defense widened to a positive allowlist:** no `asyncio.gather` / `asyncio.wait` / `asyncio.as_completed` / `asyncio.TaskGroup` inside `_resolve_chain`'s body; exactly one call site to `dispatch(adapter, query)` exists in the module.
- **Coverage gaps closed by new ACs:** empty TCCM bands; `os.cpu_count() is None`; entry order = concatenated band order; `AdapterDegradedEvent.reason = primary.confidence.reason`; per-call semaphore (not shared across concurrent `build()` invocations); env-var parsing edge cases (`""`, `"  "`, `"3.5"`, `"0x4"`, `"-1"`, `"1e2"`) parametrized; depth=4 succeeds & depth=5 raises (boundary, not just overflow); 3-deep two-fallback chain succeeds (recursion correctness at depth ≥ 2); `event_emitter` raising propagates (Rule 12, fail loud); adapter `query()` raising propagates unchanged; `args_canonical` exact format pinned with a literal-string assertion; JSON round-trip stability for `Bundle`.
- **Design-pattern opportunities surfaced** (not all elevated to ACs — Rule 2 / rule-of-three):
  - `CanonicalArgsJson` smart constructor — recommended in Notes; not an AC (S3-05 may consolidate canonicalization at the cache-key layer).
  - `AdapterDispatch` seam → elevated to AC (third concrete consumer threshold met — `query`, `confidence`, `adapter_name` are three protocol surfaces this story already needs to bridge).
  - `BundleBuilderEvent` tagged union (vs concrete `AdapterDegradedEvent` Callable type) — elevated to AC (Rule of three met: `AdapterDegraded` shipped here, `FallbackChainTooDeep` shipped here for operator visibility, S6-04 will add a third).
  - Pure `_compose_entry(primary_result, fallback_result | None) -> BundleEntry` extraction → AC + AST test (functional-core spirit of ADR-0008).
- **`tests/property/` is flat in this repo** — story originally specified `tests/property/plugins/`; corrected to flat layout (Rule 11 — match codebase conventions).
- **`SandboxedPath` for `cache_dir`** — Phase 3 arch §C7 contract; ADR-0011 honest framing. `SandboxedPath` is currently `TypeAlias = pathlib.Path` in `codegenie.transforms._forward` — import from there, do not redeclare.

## Context

`BundleBuilder` dispatches a plugin's TCCM `must_read` / `should_read` / `may_read` queries through Phase 2's language search adapters and returns a typed `Bundle`. Concurrency is bounded by `asyncio.Semaphore(min(4, os.cpu_count() or 1))` overridable via `CODEGENIE_BUNDLE_CONCURRENCY`. **Fallback semantics is the load-bearing decision** — ADR-0008 explicitly *rejects* hedged-race composition because two runs against the same inputs would return different Bundle bytes (scheduler noise), violating production design §2.4's "same inputs → same Transform bytes" veto-strength commitment. The TCCM-declared `fallback` query fires **only** when the primary's `confidence()` returns `Degraded` or `Unavailable` (the two non-`Trusted` variants of the `AdapterConfidence` tagged union — `Trusted | Degraded | Unavailable`) — never raced, never both. Property-tested across 100 Hypothesis runs **under seeded scheduler jitter** for byte-identical output; a deliberately-broken hedged-race reference impl is exercised in an `xfail` meta-test to prove the property has bite.

This story ships the builder's structure, the per-call semaphore, the iterative serial-fallback walker (`_resolve_chain`), the typed `AdapterDispatch` seam that bridges the spy + production adapter surfaces, and the `BundleBuilderEvent` two-variant tagged union (`AdapterDegraded` + `FallbackChainTooDeep`) for operator visibility. The cache key (which includes `vuln_index.digest`) and the `BundleCacheGc` GC mechanism land in S3-05 (Gap 4).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C7. BundleBuilder` — public interface, cache key shape, concurrency bound, fallback semantics, performance envelope (warm 3 ms, cold 220 ms, degraded ~180 ms).
  - `../phase-arch-design.md §Patterns considered and deliberately rejected — "No hedged-race in BundleBuilder"` — the rejection rationale; cite in module docstring.
  - `../phase-arch-design.md §Goals G4 + G8` — determinism (G4) + confidence propagation (G8).
- **Phase ADRs (load-bearing — read before implementing):**
  - `../ADRs/0008-bundlebuilder-deterministic-serial-fallback-and-vuln-index-digest-cache-key.md §Decision + §Tradeoffs` — "Adopt Option C — declarative serial fallback (fire fallback only when primary returns `Degraded`/`Unavailable`), AND `vuln_index.digest` included in the Bundle cache key."
- **Production ADRs:**
  - `../../../production/adrs/0032-language-search-adapters.md` — `confidence() → AdapterConfidence` is mandatory across adapters.
  - `../../../production/adrs/0030-graph-aware-context-queries.md` — primitive set the adapters expose.
- **Implementation plan:**
  - `../High-level-impl.md §Step 3` — done criteria: "cache-hit / cache-miss / `vuln_index.digest` invalidation; degraded adapter triggers declared fallback deterministically" + property test "across 100 runs with a `Degraded` primary adapter, the fallback is invoked exactly once per query (never raced)."
- **Existing code:**
  - `src/codegenie/plugins/tccm.py` (S3-01) — `ContextQuery` with `fallback: ContextQuery | None`; consumed here.
  - `src/codegenie/adapters/confidence.py` — `AdapterConfidence = Annotated[Trusted | Degraded | Unavailable, Field(discriminator="kind")]` (Pydantic tagged union; `Degraded` and `Unavailable` each carry `reason: str`). **NOT an enum** — dispatch via `match` + `assert_never`, never set-membership.
  - `src/codegenie/adapters/protocols.py` — four `@runtime_checkable` protocols (`ScipAdapter.refs`, `DepGraphAdapter.consumers`/`producers`, `ImportGraphAdapter.reverse_lookup`, `TestInventoryAdapter.tests_exercising`); each exposes `confidence(self) -> AdapterConfidence` as a **method**, not an attribute. No shared `.query(args)` surface — S3-04 introduces the typed `AdapterDispatch` callable seam to bridge primitive names to per-protocol methods.
  - `src/codegenie/types/identifiers.py` — `PluginId`, `PrimitiveName`, `BlobDigest`.
  - `src/codegenie/transforms/_forward.py` — `SandboxedPath: TypeAlias = pathlib.Path` (import from here; do **not** redeclare).
  - `src/codegenie/errors.py` — `CodegenieError` exists but is markers-only. `BundleBuilderError` is **not** an `Exception` subclass; see AC-2.
- **Sibling validation report (precedent):**
  - `docs/phases/03-vuln-deterministic-recipe/stories/_validation/S3-01-tccm-context-query-models.md` §"TCCMParseError shape conflict" — pinned the Pydantic-BaseModel-with-`Literal`-reason pattern; reused here for `BundleBuilderError`.

## Goal

`codegenie.plugins.bundle.BundleBuilder` exposes `async def build(resolution, repo_ctx, vuln, vuln_index) -> Bundle`; dispatch is bounded by a **per-call** `asyncio.Semaphore(min(4, os.cpu_count() or 1))` (overridable via `CODEGENIE_BUNDLE_CONCURRENCY`; two concurrent `build()` invocations get independent semaphores); the TCCM-declared `fallback` chain fires **deterministically and serially** *only* when the primary's `confidence()` matches `Degraded() | Unavailable()` — never raced, never speculatively fired, never reacquires the semaphore on recursion. An `AdapterDegraded` event is emitted on every fallback firing (with `reason = primary.confidence.reason`) for `TrustScorer.confidence` folding (Goal G8); a `FallbackChainTooDeep` event is emitted before the depth-cap raise (operator visibility). Property-tested for byte-identical `Bundle` output across 100 Hypothesis runs **with seeded scheduler jitter injected at every adapter dispatch**.

## Acceptance criteria

### Module + types

- [ ] **AC-1 — Module surface.** New module `src/codegenie/plugins/bundle.py` exports exactly `BundleBuilder`, `Bundle`, `BundleEntry`, `BundleBuilderError`, `BundleBuilderEvent`, `AdapterDegraded`, `FallbackChainTooDeep`, `AdapterDispatch`, `AdapterResult`. `__all__` pins this set with set-equality (not `⊇`). Module docstring cites ADR-0008 §Decision and the rejection of hedged-race; a static test (`tests/static/test_bundle_module_docstring.py`) asserts `ast.get_docstring(tree)` contains both literal substrings `"ADR-0008"` and `"hedged-race"`.
- [ ] **AC-2 — `BundleBuilderError` is a frozen Pydantic `BaseModel`, not an `Exception` subclass** (mirrors S3-01's `TCCMParseError` precedent). Fields: `reason: Literal["invalid_concurrency_env", "fallback_chain_too_deep"]`, `details: dict[str, str | int] = {}`. Tests assert `isinstance(BundleBuilderError(...), BaseModel)` and that constructing with an unknown `reason` raises `pydantic.ValidationError`. Where the codebase needs an *exception* (e.g., `build()` must signal an unrecoverable env-parse), raise `BundleBuilderRaise(error=BundleBuilderError(reason=...))` where `BundleBuilderRaise(CodegenieError)` is a thin one-line exception wrapping the model (so `raise` semantics work without polluting the typed `BundleBuilderError` with markers-only discipline). Tests use `with pytest.raises(BundleBuilderRaise) as exc: ...; assert exc.value.error.reason == "..."`.
- [ ] **AC-3 — `AdapterResult` Pydantic** with `frozen=True, extra="forbid"`: `payload: dict[str, str | int | bool | list[str]]` (primitive-only; matches `TrustSignal.details` discipline), `confidence: AdapterConfidence`, `adapter_name: str`. **This is the value `AdapterDispatch` returns** and the shape spy adapters in tests construct directly.
- [ ] **AC-4 — `AdapterDispatch` callable seam.** `AdapterDispatch = Callable[[ContextQuery], Awaitable[AdapterResult]]`. `resolution.composed_dispatch: dict[PrimitiveName, AdapterDispatch]` (consumed; **not constructed here** — production wiring is S7-02, spy fixtures construct it in tests). A type-only consistency test asserts `resolution.composed_dispatch` has one entry per primitive named by any `ContextQuery.primitive` referenced in the composed TCCM (missing key → `BundleBuilderRaise(error=BundleBuilderError(reason="...", details={"primitive": str(p)}))`; rationale: surface mis-wiring at the boundary, not at the await site).
- [ ] **AC-5 — `BundleEntry` Pydantic** with `frozen=True, extra="forbid"`: `primitive: PrimitiveName`, `args_canonical: str` (canonicalized JSON of `ContextQuery.args` per AC-13), `payload: dict[str, str | int | bool | list[str]]`, `confidence: AdapterConfidence`, `fallback_used: bool`, `adapter_name: str`.
- [ ] **AC-6 — `Bundle` Pydantic** with `frozen=True, extra="forbid"`: `entries: tuple[BundleEntry, ...]` (tuple for hash-stability), `plugin_id: PluginId`, `vuln_index_digest: BlobDigest`.
- [ ] **AC-7 — `BundleBuilderEvent` tagged union.** `AdapterDegraded` (fields: `kind: Literal["adapter_degraded"]`, `primitive: PrimitiveName`, `adapter_name: str`, `reason: str`) and `FallbackChainTooDeep` (fields: `kind: Literal["fallback_chain_too_deep"]`, `primitive: PrimitiveName`, `depth: int`); `BundleBuilderEvent = Annotated[AdapterDegraded | FallbackChainTooDeep, Field(discriminator="kind")]`. (Three event kinds total at Phase 3 lifetime — rule-of-three met. S6-04 will add cancellation variants via extension-by-addition.)

### Constructor + concurrency

- [ ] **AC-8 — `BundleBuilder.__init__(self, cache_dir: SandboxedPath, *, event_emitter: Callable[[BundleBuilderEvent], None] | None = None)`** — `event_emitter` accepts the *union* (forward-compatible) and defaults to no-op so this story is testable without S6-01's `EventLog`. `cache_dir` is typed `SandboxedPath` (imported from `codegenie.transforms._forward`); raw `pathlib.Path` is rejected at the type-check boundary (mypy --strict will reject because the alias is currently identical to `Path` but the imports/annotation differ across modules — a unit test asserts `BundleBuilder.__init__.__annotations__["cache_dir"]` is `SandboxedPath`, not `Path`). Reads `_read_concurrency_bound()` at construction (fail-loud per Rule 12).
- [ ] **AC-9 — Concurrency bound function `_read_concurrency_bound()`** is a pure helper called from `__init__` (NOT a module-level constant — that would defeat `monkeypatch.setattr(os, "cpu_count", ...)` and `monkeypatch.delenv(...)` tests). Behavior:
  - If `CODEGENIE_BUNDLE_CONCURRENCY` unset / empty / whitespace-only → return `min(4, os.cpu_count() or 1)`.
  - If set to a value `int(value)` parses as a positive integer (including `"+4"`) → return that int.
  - Otherwise → raise `BundleBuilderRaise(error=BundleBuilderError(reason="invalid_concurrency_env", details={"value": value}))`.
  - **Parametrized rejection test** over `{"", "  ", "0", "-1", "3.5", "0x4", "1e2", "not-a-number"}`; **parametrized acceptance test** over `{"1", "+4", "128"}` (rejection of zero is veto-strength — `Semaphore(0)` would deadlock).
- [ ] **AC-10 — `os.cpu_count() is None` path.** Unit test: `monkeypatch.delenv("CODEGENIE_BUNDLE_CONCURRENCY", raising=False); monkeypatch.setattr(os, "cpu_count", lambda: None)` → `BundleBuilder(cache_dir=...)._concurrency == 1` (no `TypeError`, no silent default to 4). Pins the `or 1` fallback.
- [ ] **AC-11 — Per-call semaphore.** The `asyncio.Semaphore(n)` is constructed **inside `build()` per call**, NOT at module level NOR on the builder instance. Verified by a test that spawns two concurrent `build()` coroutines on the *same* `BundleBuilder` instance, each with 4 queries that block on a shared `asyncio.Event`; assert peak concurrent in-flight dispatches reaches `2 * concurrency_bound`, not `concurrency_bound`. (Phase 6.5+ commitment — a shared semaphore silently serializes workflows.)

### Iteration order + entry ordering

- [ ] **AC-12 — `build()` iterates `resolution.composed_tccm.must_read` THEN `should_read` THEN `may_read`** (Phase 3 executes all three eagerly; ADR-0029's deferred `may_read` is out of scope and called out in the module docstring). `bundle.entries` length equals the sum of the three band lengths; `bundle.entries[i].primitive` equals the `i`-th query's primitive in the concatenated `must + should + may` sequence. Test: bands `[q1, q2]`/`[q3]`/`[q4]` with adapters that complete at varying delays — assert `entries` index order matches **task index**, not completion time.
- [ ] **AC-13 — `args_canonical` exact format.** Computed by `_canonicalize_args(args)` = `json.dumps(args, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`. Pin literal: for `args = {"b": 1, "a": [2, 3]}`, `args_canonical == '{"a":[2,3],"b":1}'` exactly. Test: build `BundleEntry`s from two `ContextQuery` instances with the same dict but different *insertion order* — assert their `args_canonical` strings are byte-equal. (S3-05's BLAKE3 cache key depends on this byte-stability.)

### Fallback semantics — the load-bearing decision

- [ ] **AC-14 — Sum-type dispatch via `match` + `assert_never`.** The fallback decision uses a `match` block on `primary.confidence` — `case Trusted(): no fallback`; `case Degraded() | Unavailable(): fire fallback`; `case _ as never: assert_never(never)`. A static AST test (`tests/static/test_bundle_dispatch_pattern.py`) asserts the module contains exactly one `Match` node whose subject is `*.confidence` and whose cases include both `Trusted`-pattern and `Degraded | Unavailable`-pattern arms with an `assert_never` final arm. Phase 3 ADR-0010 conformance.
- [ ] **AC-15 — Deterministic serial fallback (NOT hedged race — ADR-0008):** for each `ContextQuery`, invoke `dispatch(query)` where `dispatch = resolution.composed_dispatch[query.primitive]`. Match on `result.confidence`; ONLY if `Degraded() | Unavailable()` AND `query.fallback is not None`, invoke the fallback query via the iterative `_resolve_chain`. Fallback runs *after* the primary completes — never concurrently. Three explicit tests: (a) primary `Trusted` → fallback adapter never invoked, `fallback_used=False`; (b) primary `Degraded` → fallback invoked exactly once, `fallback_used=True`; (c) order-recorder test (see AC-19 mutation-resistance).
- [ ] **AC-16 — Fallback chain is iterative, not recursive.** `_resolve_chain(query: ContextQuery, dispatch_table, emit) -> BundleEntry` iterates `while query is not None: ...` over the chain. The semaphore is acquired **once per top-level band-level task** (via `_acquire_then_dispatch` in `build()`) — `_resolve_chain` does **NOT** acquire the semaphore on its inner loop. A property test verifies: with `concurrency_bound=2` and 4 top-level queries each on a depth-4 degraded chain (16 total dispatch calls), peak concurrent dispatches ≤ 2 *and* the chain completes (no deadlock — would deadlock if every recursion frame held the semaphore).
- [ ] **AC-17 — Fallback chain depth cap.** Cap at depth `4` (mirrors `extends`-chain cap in S2-04). At depth `5`, before raising, emit `FallbackChainTooDeep(primitive=root.primitive, depth=5)` so operators see the trigger; then raise `BundleBuilderRaise(error=BundleBuilderError(reason="fallback_chain_too_deep", details={"primitive": str(p), "depth": 5}))`. Boundary tests:
  - **Depth exactly 4 succeeds** (4-deep chain of `Degraded → Degraded → Degraded → Trusted` → returns a `BundleEntry` with `fallback_used=True`, 3 `AdapterDegraded` events emitted).
  - **Depth 5 raises** (5-deep chain — last variant unreachable; emits 4 `AdapterDegraded` then 1 `FallbackChainTooDeep`, then raises).
- [ ] **AC-18 — Recursion-correctness at depth ≥ 2.** Test: 3-deep chain `primary Degraded → fallback1 Degraded → fallback2 Trusted` — assert all three dispatches called exactly once *in chain order*; assert `bundle.entries[0].adapter_name == "fallback2"`; assert exactly 2 `AdapterDegraded` events emitted (one per `Degraded` step). Catches off-by-one mutations on the depth counter (`_depth=_depth` vs `_depth+1`).

### AdapterDegraded event hand-off

- [ ] **AC-19 — Event emission ordering & reason propagation.** On every fallback firing, emit `AdapterDegraded(primitive=query.primitive, adapter_name=primary_result.adapter_name, reason=primary_result.confidence.reason)` **before** the fallback dispatch is invoked (operator sees "we're falling back" not "we fell back"). The `reason` field is the verbatim string from the variant's `reason` (only `Degraded` and `Unavailable` reach this branch — the type narrows after `match`). Test pins both branches: a `Degraded(reason="scip_index_stale")` primary emits an event with `reason="scip_index_stale"`; an `Unavailable(reason="tool_missing")` primary emits an event with `reason="tool_missing"`. Order-recorder test pins event-emit before fallback dispatch via a shared `order: list[str]` that the spy adapter and the emitter both append to.

### Error propagation (fail loud — Rule 12)

- [ ] **AC-20 — Adapter raises propagate unchanged.** If any `dispatch(query)` raises (any exception class), `build()` re-raises the original exception unchanged — no swallowing, no wrapping in `BundleBuilderError`, no conversion to `Degraded`. Test: `dispatch_table["scip.refs"] = AsyncMock(side_effect=RuntimeError("boom"))`; `pytest.raises(RuntimeError, match="boom")`.
- [ ] **AC-21 — `event_emitter` raises propagate.** If `event_emitter(event)` raises, `build()` propagates the exception (fail-loud per Rule 12 — a buggy `EventLog.emit_internal` must not silently swallow degradation signals → `TrustScorer.confidence` would otherwise report `High` while reality is `Degraded`). Test: `event_emitter=lambda e: (_ for _ in ()).throw(ValueError("buggy emitter"))` with a degraded primary → `pytest.raises(ValueError)`.

### Determinism property tests

- [ ] **AC-22 — Determinism property test under seeded scheduler jitter.** `tests/property/test_bundle_determinism.py`: 100 Hypothesis runs against `BundleBuilder.build(...)` with identical inputs and spy dispatches that inject `await asyncio.sleep(random.Random(seed).uniform(0, 0.002))` *seeded by Hypothesis-generated `seed`* — the same `seed` reproduces the same scheduler order in two runs, different seeds produce different orders, **and the resulting `Bundle.model_dump_json()` is byte-identical regardless of seed**. Failures attach the diff.
- [ ] **AC-23 — `xfail` meta-test against a deliberately-broken hedged-race reference.** `tests/property/test_bundle_determinism.py` includes a `@pytest.mark.xfail(strict=True, reason="hedged-race violates ADR-0008")` test that imports a fixture-only `_HedgedRaceBundleBuilder` (defined in `tests/property/_hedged_race_reference.py`, **never imported by production code** — a fence test verifies this) and asserts the SAME determinism property over it. The `xfail(strict=True)` means a future regression that makes the broken impl pass would **fail the test suite** — proves the property has bite.
- [ ] **AC-24 — Serial-fallback property test.** `tests/property/test_bundle_serial_fallback.py`: 100 runs with seeded jitter; primary always `Degraded`, fallback always `Trusted`. Assertions per run:
  - `primary_dispatch.calls == n_queries` AND `fallback_dispatch.calls == n_queries` (exact counts).
  - For each query, `primary:start` appears in the order log strictly before `fallback:start` (index comparison, robust to inter-query interleaving).
  - `len([e for e in events if isinstance(e, AdapterDegraded)]) == n_queries`.
- [ ] **AC-25 — JSON round-trip stability for `Bundle`.** Property: `Bundle.model_validate_json(b.model_dump_json()).model_dump_json() == b.model_dump_json()` for every Bundle produced by AC-22. Catches Pydantic v2 `tuple[BundleEntry, ...]` serialization edge cases (Notes line ~260 hints at this — promoted to AC).

### Empty bands + structural defenses

- [ ] **AC-26 — Empty TCCM bands.** `must_read=[] AND should_read=[] AND may_read=[]` → `Bundle(entries=(), plugin_id=..., vuln_index_digest=...)` constructs cleanly; zero dispatch calls; zero events emitted; `frozen=True` Pydantic validates the empty tuple.
- [ ] **AC-27 — AST positive structural defense.** `tests/static/test_no_hedged_race_in_bundle.py` walks `src/codegenie/plugins/bundle.py` and asserts:
  - **(a)** No call to `asyncio.gather`, `asyncio.wait`, `asyncio.as_completed`, or `asyncio.TaskGroup` appears within the AST subtree of the `async def _resolve_chain` function. (The top-level `asyncio.gather` in `build()` over the flattened band tasks is permitted and located by name.)
  - **(b)** Exactly **one** AST `Call` site invokes a callable named `dispatch` (the single dispatch site — extension of refactor §line 225 promoted to AC). A future refactor introducing a second dispatch site (e.g., a speculative pre-fetch) fails this test.
  - **(c)** `_compose_entry(...)` is a `def` (not `async def`) and its function body contains zero `Await` nodes and zero references to `asyncio` — proves the pure-fold extraction (functional-core / imperative-shell).
- [ ] **AC-28 — Pure `_compose_entry`.** `_compose_entry(primary: AdapterResult, fallback: AdapterResult | None, query: ContextQuery) -> BundleEntry` is pure (no I/O, no async, no event emission). When `fallback is None`, returns `BundleEntry(... confidence=primary.confidence, fallback_used=False)`. When `fallback is not None`, returns `BundleEntry(... confidence=fallback.confidence, fallback_used=True, adapter_name=fallback.adapter_name)`. Six-row parametrized unit test covers every combination of (primary in {Trusted, Degraded, Unavailable}) × (fallback in {None, AdapterResult}).

### Gate

- [ ] **AC-29 —** `mypy --strict` clean.
- [ ] **AC-30 —** `ruff format`, `ruff check` clean.
- [ ] **AC-31 —** TDD red test exists, committed, green.

## Implementation outline

1. Create `src/codegenie/plugins/bundle.py`:
   - Imports: `asyncio`, `json`, `os`, `typing.{Annotated, Awaitable, Callable, Final, Literal, assert_never}`; `BaseModel, ConfigDict, Field` from `pydantic`; `PluginId, PrimitiveName, BlobDigest` from `codegenie.types.identifiers`; `Trusted, Degraded, Unavailable, AdapterConfidence` from `codegenie.adapters.confidence`; `ContextQuery` from `codegenie.plugins.tccm`; `SandboxedPath` from `codegenie.transforms._forward`; `CodegenieError` from `codegenie.errors`.
   - Module-level constants: `_MAX_FALLBACK_DEPTH: Final[int] = 4`. **NO** `_DEFAULT_CONCURRENCY_BOUND` global — bound is read per-construction.
   - `def _read_concurrency_bound() -> int` — pure: reads `os.environ.get("CODEGENIE_BUNDLE_CONCURRENCY")`; strips whitespace; if empty → `min(4, os.cpu_count() or 1)`; else attempts `int(value)` (allows `"+4"`); validates positive; on any failure raises `BundleBuilderRaise(error=BundleBuilderError(reason="invalid_concurrency_env", details={"value": value}))`.
   - `def _canonicalize_args(args: dict[str, str | int | bool | list[str]]) -> str` — pure: `json.dumps(args, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`.
   - `class BundleBuilderError(BaseModel)` frozen, `extra="forbid"`: `reason: Literal["invalid_concurrency_env", "fallback_chain_too_deep"]`, `details: dict[str, str | int] = {}`. **NOT** an exception.
   - `class BundleBuilderRaise(CodegenieError)` one-liner: `def __init__(self, *, error: BundleBuilderError) -> None: self.error = error; super().__init__(error.model_dump_json())`.
   - `class AdapterResult(BaseModel)` frozen, `extra="forbid"`: `payload`, `confidence: AdapterConfidence`, `adapter_name: str`.
   - `AdapterDispatch = Callable[[ContextQuery], Awaitable[AdapterResult]]`.
   - `class AdapterDegraded(BaseModel)` frozen, `extra="forbid"`: `kind: Literal["adapter_degraded"] = "adapter_degraded"`, `primitive: PrimitiveName`, `adapter_name: str`, `reason: str`.
   - `class FallbackChainTooDeep(BaseModel)` frozen, `extra="forbid"`: `kind: Literal["fallback_chain_too_deep"] = "fallback_chain_too_deep"`, `primitive: PrimitiveName`, `depth: int`.
   - `BundleBuilderEvent = Annotated[AdapterDegraded | FallbackChainTooDeep, Field(discriminator="kind")]`.
   - `class BundleEntry(BaseModel)`, `class Bundle(BaseModel)` per AC-5/AC-6.
2. Pure helper `def _compose_entry(query: ContextQuery, primary: AdapterResult, fallback: AdapterResult | None) -> BundleEntry` — sync, no `await`, no I/O. Returns the right `BundleEntry` per AC-28.
3. Async helper `async def _resolve_chain(query: ContextQuery, dispatch_table: dict[PrimitiveName, AdapterDispatch], emit: Callable[[BundleBuilderEvent], None]) -> BundleEntry` — **iterative**, no recursion, never touches the semaphore. Walks `current = query` with a `depth: int = 0` counter. At each step:
   - Look up `dispatch = dispatch_table[current.primitive]` (raise `BundleBuilderRaise` if missing per AC-4).
   - `primary_result = await dispatch(current)`.
   - `match primary_result.confidence:`
     - `case Trusted(): return _compose_entry(current, primary_result, fallback=None)`.
     - `case Degraded() | Unavailable() as failed:`
       - If `current.fallback is None` → return `_compose_entry(current, primary_result, fallback=None)` (best-effort with `fallback_used=False`).
       - `depth += 1`; if `depth >= _MAX_FALLBACK_DEPTH`: `emit(FallbackChainTooDeep(primitive=query.primitive, depth=depth))`; raise.
       - `emit(AdapterDegraded(primitive=current.primitive, adapter_name=primary_result.adapter_name, reason=failed.reason))`.
       - `fallback_query = current.fallback`. Recompute: dispatch the fallback; loop back. (If the fallback ALSO degrades, the loop iterates again with `depth += 1`.)
     - `case _ as never: assert_never(never)`.
   - On the *final* loop exit (either Trusted reached, or fallback exhausted), return `_compose_entry(root_query, last_primary, fallback=last_dispatch_result_when_used)` — `fallback_used=True` iff at least one fallback step executed.
4. `class BundleBuilder:`
   - `__init__(self, cache_dir: SandboxedPath, *, event_emitter: Callable[[BundleBuilderEvent], None] | None = None)` — store; call `self._concurrency = _read_concurrency_bound()` (fail-loud).
   - `async def build(self, resolution, repo_ctx, vuln, vuln_index) -> Bundle`:
     - `semaphore = asyncio.Semaphore(self._concurrency)` (**per-call**, per AC-11).
     - `emit = self._event_emitter or (lambda _e: None)`.
     - `queries: list[ContextQuery] = [*tccm.must_read, *tccm.should_read, *tccm.may_read]`.
     - For each `q` in `queries`, build `task = _acquire_then_dispatch(semaphore, q, resolution.composed_dispatch, emit)`.
     - `entries = await asyncio.gather(*tasks)` — preserves task index = `queries` index (AC-12).
     - Return `Bundle(entries=tuple(entries), plugin_id=resolution.plugin.manifest.name, vuln_index_digest=vuln_index.digest)`.
   - `async def _acquire_then_dispatch(semaphore, query, dispatch_table, emit) -> BundleEntry`:
     - `async with semaphore: return await _resolve_chain(query, dispatch_table, emit)`.
     - **The semaphore is acquired exactly here, ONCE per top-level query, and never inside `_resolve_chain`.** This is the AC-16 invariant.
5. `tests/property/test_bundle_determinism.py` + `tests/property/test_bundle_serial_fallback.py` (flat — match codebase convention, Rule 11) + `tests/property/_hedged_race_reference.py` (fixture-only broken impl for AC-23).
6. `tests/static/test_no_hedged_race_in_bundle.py` (AC-27) — three-part AST walker.
7. `tests/static/test_bundle_dispatch_pattern.py` (AC-14) — assert exactly one `Match` node on `*.confidence` with the expected case shape.
8. `tests/static/test_bundle_module_docstring.py` (AC-1) — assert docstring contains `"ADR-0008"` and `"hedged-race"`.

## TDD plan — red / green / refactor

### Red

Test file: `tests/unit/plugins/test_bundle_builder.py`

```python
import os
import asyncio
import random
import pytest
from pydantic import BaseModel, ValidationError
from codegenie.plugins.bundle import (
    BundleBuilder, Bundle, BundleEntry, BundleBuilderError, BundleBuilderRaise,
    AdapterDegraded, FallbackChainTooDeep, AdapterResult, _canonicalize_args,
    _compose_entry, _read_concurrency_bound,
)
from codegenie.plugins.tccm import ContextQuery, TCCM
from codegenie.adapters.confidence import Trusted, Degraded, Unavailable
from codegenie.types.identifiers import PrimitiveName

def _make_dispatch(name: str, confidence, payload=None, order_log=None, jitter_rng=None):
    """Spy dispatch: counts invocations, records ordering, returns AdapterResult."""
    calls = 0
    async def dispatch(query: ContextQuery) -> AdapterResult:
        nonlocal calls
        calls += 1
        if order_log is not None:
            order_log.append(f"{name}:start")
        if jitter_rng is not None:
            await asyncio.sleep(jitter_rng.uniform(0, 0.002))
        else:
            await asyncio.sleep(0)
        if order_log is not None:
            order_log.append(f"{name}:done")
        return AdapterResult(payload=payload or {"hit": "ok"}, confidence=confidence, adapter_name=name)
    dispatch.__name__ = f"dispatch_{name}"  # for AST test inspection
    dispatch.calls = lambda: calls          # closure-counter accessor
    dispatch._increment_tracker = lambda: calls  # noqa — sketch
    return dispatch

# --- AC-2: BundleBuilderError is a frozen Pydantic BaseModel, not an Exception ---
class TestBundleBuilderErrorShape:
    def test_is_basemodel_not_exception(self):
        err = BundleBuilderError(reason="invalid_concurrency_env", details={"value": "x"})
        assert isinstance(err, BaseModel)
        assert not isinstance(err, Exception)
    def test_unknown_reason_rejected(self):
        with pytest.raises(ValidationError):
            BundleBuilderError(reason="nope")  # type: ignore[arg-type]
    def test_frozen(self):
        err = BundleBuilderError(reason="invalid_concurrency_env")
        with pytest.raises(ValidationError):
            err.reason = "fallback_chain_too_deep"  # type: ignore[misc]

# --- AC-9: parametrized rejection/acceptance of env var ---
class TestConcurrencyEnv:
    @pytest.mark.parametrize("value", ["", "  ", "0", "-1", "3.5", "0x4", "1e2", "not-a-number"])
    def test_invalid_env_raises_with_typed_reason(self, monkeypatch, value, tmp_path):
        monkeypatch.setenv("CODEGENIE_BUNDLE_CONCURRENCY", value)
        with pytest.raises(BundleBuilderRaise) as exc:
            BundleBuilder(cache_dir=tmp_path)
        assert exc.value.error.reason == "invalid_concurrency_env"

    @pytest.mark.parametrize("value,expected", [("1", 1), ("+4", 4), ("128", 128)])
    def test_valid_env_accepted(self, monkeypatch, value, expected, tmp_path):
        monkeypatch.setenv("CODEGENIE_BUNDLE_CONCURRENCY", value)
        builder = BundleBuilder(cache_dir=tmp_path)
        assert builder._concurrency == expected

    def test_cpu_count_none_falls_back_to_1(self, monkeypatch, tmp_path):  # AC-10
        monkeypatch.delenv("CODEGENIE_BUNDLE_CONCURRENCY", raising=False)
        monkeypatch.setattr(os, "cpu_count", lambda: None)
        builder = BundleBuilder(cache_dir=tmp_path)
        assert builder._concurrency == 1

# --- AC-11: per-call semaphore (not shared across build() invocations) ---
class TestPerCallSemaphore:
    @pytest.mark.asyncio
    async def test_two_concurrent_builds_do_not_share_bound(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CODEGENIE_BUNDLE_CONCURRENCY", "2")
        in_flight = 0
        peak = 0
        gate = asyncio.Event()
        async def gated_dispatch(query):
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await gate.wait()
            in_flight -= 1
            return AdapterResult(payload={}, confidence=Trusted(), adapter_name="g")
        # Two builds, 4 queries each → if shared bound=2, peak=2; if per-call, peak=4.
        b = BundleBuilder(cache_dir=tmp_path)
        coros = [b.build(_resolution_with_n_queries(4, dispatch=gated_dispatch), ...),
                 b.build(_resolution_with_n_queries(4, dispatch=gated_dispatch), ...)]
        task = asyncio.gather(*coros)
        await asyncio.sleep(0.05)   # let coroutines reach the gate
        assert peak == 4            # per-call semaphores; would be 2 if shared
        gate.set()
        await task

# --- AC-14, AC-15: sum-type dispatch + serial fallback ---
class TestSerialFallbackSemantics:
    """ADR-0008: serial fallback, NOT hedged-race."""

    @pytest.mark.asyncio
    async def test_no_fallback_when_primary_trusted(self, tmp_path):
        primary = _make_dispatch("scip.refs", Trusted())
        fallback = _make_dispatch("dep_graph.consumers", Trusted())
        resolution = _resolution_with_one_query_and_fallback(primary, fallback)
        b = BundleBuilder(cache_dir=tmp_path)
        bundle = await b.build(resolution, ..., ..., _vuln_index_fixture())
        assert primary.calls() == 1 and fallback.calls() == 0
        assert bundle.entries[0].fallback_used is False

    @pytest.mark.asyncio
    async def test_fallback_invoked_once_when_primary_degraded(self, tmp_path):
        primary = _make_dispatch("scip.refs", Degraded(reason="scip_index_stale"))
        fallback = _make_dispatch("dep_graph.consumers", Trusted())
        events: list = []
        b = BundleBuilder(cache_dir=tmp_path, event_emitter=events.append)
        bundle = await b.build(_resolution_with_one_query_and_fallback(primary, fallback), ..., ..., _vuln_index_fixture())
        assert primary.calls() == 1 and fallback.calls() == 1
        assert bundle.entries[0].fallback_used is True
        # AC-19: AdapterDegraded with reason propagated from Degraded(reason=...)
        degraded_events = [e for e in events if isinstance(e, AdapterDegraded)]
        assert len(degraded_events) == 1
        assert degraded_events[0].reason == "scip_index_stale"
        assert degraded_events[0].adapter_name == "scip.refs"

    @pytest.mark.asyncio
    async def test_unavailable_also_triggers_fallback_with_reason(self, tmp_path):
        primary = _make_dispatch("scip.refs", Unavailable(reason="tool_missing"))
        fallback = _make_dispatch("dep_graph.consumers", Trusted())
        events: list = []
        b = BundleBuilder(cache_dir=tmp_path, event_emitter=events.append)
        await b.build(_resolution_with_one_query_and_fallback(primary, fallback), ..., ..., _vuln_index_fixture())
        assert [e for e in events if isinstance(e, AdapterDegraded)][0].reason == "tool_missing"

    @pytest.mark.asyncio
    async def test_primary_strictly_before_fallback_via_order_log(self, tmp_path):
        # Order-recording with shared jitter; hedged-race impl would interleave.
        rng = random.Random(0xC0DE)
        order: list[str] = []
        primary = _make_dispatch("primary", Degraded(reason="x"), order_log=order, jitter_rng=rng)
        fallback = _make_dispatch("fallback", Trusted(), order_log=order, jitter_rng=rng)
        b = BundleBuilder(cache_dir=tmp_path)
        await b.build(_resolution_with_one_query_and_fallback(primary, fallback), ..., ..., _vuln_index_fixture())
        # Robust to extra log entries from future logging — index-based, not equality.
        i_pdone = order.index("primary:done")
        i_fstart = order.index("fallback:start")
        assert i_pdone < i_fstart, f"hedged-race smell — order: {order}"

    @pytest.mark.asyncio
    async def test_two_level_fallback_chain_succeeds(self, tmp_path):  # AC-18
        a = _make_dispatch("a", Degraded(reason="r1"))
        b_disp = _make_dispatch("b", Degraded(reason="r2"))
        c = _make_dispatch("c", Trusted())
        events: list = []
        builder = BundleBuilder(cache_dir=tmp_path, event_emitter=events.append)
        bundle = await builder.build(_resolution_with_chain([a, b_disp, c]), ..., ..., _vuln_index_fixture())
        assert a.calls() == 1 and b_disp.calls() == 1 and c.calls() == 1
        assert bundle.entries[0].adapter_name == "c"
        assert bundle.entries[0].fallback_used is True
        assert len([e for e in events if isinstance(e, AdapterDegraded)]) == 2
        assert [e.reason for e in events if isinstance(e, AdapterDegraded)] == ["r1", "r2"]

    @pytest.mark.asyncio
    async def test_depth_exactly_4_succeeds(self, tmp_path):  # AC-17 boundary
        chain = [_make_dispatch(f"d{i}", Degraded(reason=str(i))) for i in range(3)] + [_make_dispatch("d3", Trusted())]
        events: list = []
        b = BundleBuilder(cache_dir=tmp_path, event_emitter=events.append)
        bundle = await b.build(_resolution_with_chain(chain), ..., ..., _vuln_index_fixture())
        assert bundle.entries[0].adapter_name == "d3"
        assert len([e for e in events if isinstance(e, AdapterDegraded)]) == 3

    @pytest.mark.asyncio
    async def test_depth_5_emits_and_raises(self, tmp_path):  # AC-17 overflow
        chain = [_make_dispatch(f"d{i}", Degraded(reason=str(i))) for i in range(5)]
        events: list = []
        b = BundleBuilder(cache_dir=tmp_path, event_emitter=events.append)
        with pytest.raises(BundleBuilderRaise) as exc:
            await b.build(_resolution_with_chain(chain), ..., ..., _vuln_index_fixture())
        assert exc.value.error.reason == "fallback_chain_too_deep"
        assert exc.value.error.details["depth"] == 5
        # FallbackChainTooDeep emitted BEFORE the raise
        assert any(isinstance(e, FallbackChainTooDeep) for e in events)

# --- AC-12: entry order = concatenated band order, not completion order ---
class TestEntryOrder:
    @pytest.mark.asyncio
    async def test_entries_ordered_by_task_index_not_completion(self, tmp_path):
        # Slow-then-fast adapters; assert index order, not completion order.
        ...

# --- AC-13: args_canonical exact format ---
class TestCanonicalArgs:
    def test_literal_format(self):
        assert _canonicalize_args({"b": 1, "a": [2, 3]}) == '{"a":[2,3],"b":1}'
    def test_insertion_order_independent(self):
        assert _canonicalize_args({"a": 1, "b": 2}) == _canonicalize_args({"b": 2, "a": 1})

# --- AC-20, AC-21: fail-loud error propagation ---
class TestErrorPropagation:
    @pytest.mark.asyncio
    async def test_adapter_raise_propagates_unchanged(self, tmp_path):
        async def boom(_q): raise RuntimeError("boom from adapter")
        b = BundleBuilder(cache_dir=tmp_path)
        with pytest.raises(RuntimeError, match="boom from adapter"):
            await b.build(_resolution_with_dispatch({"scip.refs": boom}, queries=[_q("scip.refs")]), ..., ..., _vuln_index_fixture())

    @pytest.mark.asyncio
    async def test_event_emitter_raise_propagates(self, tmp_path):
        primary = _make_dispatch("scip.refs", Degraded(reason="x"))
        fallback = _make_dispatch("dep_graph.consumers", Trusted())
        def buggy(_e): raise ValueError("buggy emitter")
        b = BundleBuilder(cache_dir=tmp_path, event_emitter=buggy)
        with pytest.raises(ValueError, match="buggy emitter"):
            await b.build(_resolution_with_one_query_and_fallback(primary, fallback), ..., ..., _vuln_index_fixture())

# --- AC-26: empty TCCM bands ---
class TestEmptyBands:
    @pytest.mark.asyncio
    async def test_all_empty_bands(self, tmp_path):
        events: list = []
        b = BundleBuilder(cache_dir=tmp_path, event_emitter=events.append)
        bundle = await b.build(_resolution_with_empty_tccm(), ..., ..., _vuln_index_fixture())
        assert bundle.entries == ()
        assert events == []

# --- AC-28: pure _compose_entry ---
class TestComposeEntry:
    @pytest.mark.parametrize("confidence,fallback,expected_fallback_used", [
        (Trusted(), None, False),
        (Degraded(reason="r"), None, False),  # fallback exhausted / not declared
        (Unavailable(reason="r"), None, False),
        (Trusted(), AdapterResult(payload={}, confidence=Trusted(), adapter_name="f"), True),
        (Degraded(reason="r"), AdapterResult(payload={}, confidence=Trusted(), adapter_name="f"), True),
        (Unavailable(reason="r"), AdapterResult(payload={}, confidence=Trusted(), adapter_name="f"), True),
    ])
    def test_compose_entry_combinations(self, confidence, fallback, expected_fallback_used):
        primary = AdapterResult(payload={"k": "v"}, confidence=confidence, adapter_name="p")
        query = ContextQuery.create(primitive="scip.refs", args={"x": 1}).unwrap()
        entry = _compose_entry(query, primary, fallback)
        assert entry.fallback_used is expected_fallback_used
```

Property test (`tests/property/test_bundle_determinism.py`):

```python
import random
from hypothesis import given, settings, strategies as st

@settings(max_examples=100, deadline=None)
@given(seed=st.integers(min_value=0, max_value=10**9))
def test_bundle_byte_identical_under_seeded_jitter(seed, tmp_path_factory):
    """Goal G4 + ADR-0008: same inputs + same seed → same Bundle bytes EVEN UNDER scheduler jitter.

    Different seeds may produce different scheduler orders; result must still be byte-identical
    because the implementation is a pure fold over typed inputs. A hedged-race impl would
    fail under varying seeds because completion order changes which result becomes the entry."""
    # Two independent builds with shared seed; spy dispatches sleep for rng-driven jitter.
    bundles = [_run_build_with_seed(seed, tmp_path_factory.mktemp(str(i))) for i in range(2)]
    assert bundles[0].model_dump_json() == bundles[1].model_dump_json()

    # AC-25: JSON round-trip stability
    rebuilt = Bundle.model_validate_json(bundles[0].model_dump_json())
    assert rebuilt.model_dump_json() == bundles[0].model_dump_json()


# AC-23: xfail meta-test — proves the property has bite
@pytest.mark.xfail(strict=True, reason="hedged-race violates ADR-0008 — broken reference must fail")
@settings(max_examples=20, deadline=None)
@given(seed=st.integers(min_value=0, max_value=10**9))
def test_hedged_race_reference_fails_determinism(seed, tmp_path_factory):
    from tests.property._hedged_race_reference import _HedgedRaceBundleBuilder
    bundles = [_run_build_with_seed_using(_HedgedRaceBundleBuilder, seed, tmp_path_factory.mktemp(str(i))) for i in range(2)]
    assert bundles[0].model_dump_json() == bundles[1].model_dump_json()  # expected to fail
```

Property test (`tests/property/test_bundle_serial_fallback.py`):

```python
@settings(max_examples=100, deadline=None)
@given(seed=st.integers(min_value=0, max_value=10**9), n_queries=st.integers(min_value=1, max_value=5))
def test_fallback_invoked_exactly_once_with_seeded_jitter(seed, n_queries, tmp_path_factory):
    """AC-24: per-query counts are exact; primary precedes fallback in order log;
    one AdapterDegraded event per query."""
    rng = random.Random(seed)
    order, events, primary, fallback = _setup_serial_fallback_spies(rng=rng)
    bundle, events = _run_build_with_chain(primary, fallback, n=n_queries, tmp_path=tmp_path_factory.mktemp(str(seed)))
    assert primary.calls() == n_queries
    assert fallback.calls() == n_queries
    # Per-query index check: every primary:done precedes the *same query*'s fallback:start
    for q in range(n_queries):
        i_pdone = order.index(f"q{q}-primary:done")
        i_fstart = order.index(f"q{q}-fallback:start")
        assert i_pdone < i_fstart
    assert len([e for e in events if isinstance(e, AdapterDegraded)]) == n_queries
```

Static (`tests/static/test_no_hedged_race_in_bundle.py`):

```python
import ast
from pathlib import Path

_FORBIDDEN_RACE = {"gather", "wait", "as_completed", "TaskGroup"}

def _find_function(tree: ast.Module, name: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in bundle.py")

def test_resolve_chain_has_no_race_primitives():
    """AC-27 (a): no asyncio.gather/wait/as_completed/TaskGroup inside _resolve_chain.

    Belt-and-suspenders for the ADR-0008 veto-strength rejection of hedged-race."""
    tree = ast.parse(Path("src/codegenie/plugins/bundle.py").read_text())
    fn = _find_function(tree, "_resolve_chain")
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in _FORBIDDEN_RACE, (
                f"hedged-race anti-pattern in _resolve_chain: {ast.unparse(node)}"
            )

def test_exactly_one_dispatch_call_site():
    """AC-27 (b): exactly one site calls a `dispatch`-named callable.

    A future contributor introducing a speculative pre-fetch (second dispatch site) fails this."""
    tree = ast.parse(Path("src/codegenie/plugins/bundle.py").read_text())
    dispatch_calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = ast.unparse(node.func)
            if target == "dispatch" or target.endswith(".dispatch"):
                dispatch_calls.append(ast.unparse(node))
    # The one site is inside _resolve_chain: `await dispatch(current)`.
    assert len(dispatch_calls) == 1, f"expected exactly one dispatch site, found: {dispatch_calls}"

def test_compose_entry_is_pure_sync():
    """AC-27 (c): _compose_entry has no awaits, no asyncio references — functional-core proof."""
    tree = ast.parse(Path("src/codegenie/plugins/bundle.py").read_text())
    fn = _find_function(tree, "_compose_entry")
    assert isinstance(fn, ast.FunctionDef), "_compose_entry must be `def`, not `async def`"
    for node in ast.walk(fn):
        assert not isinstance(node, ast.Await), "_compose_entry must contain no Await nodes"
        if isinstance(node, ast.Name):
            assert node.id != "asyncio", "_compose_entry must not reference asyncio"
```

Static (`tests/static/test_bundle_dispatch_pattern.py`):

```python
def test_confidence_match_has_assert_never_arm():
    """AC-14: dispatch on AdapterConfidence uses match + assert_never (ADR-0010)."""
    tree = ast.parse(Path("src/codegenie/plugins/bundle.py").read_text())
    match_nodes = [n for n in ast.walk(tree) if isinstance(n, ast.Match)]
    on_confidence = [m for m in match_nodes if ast.unparse(m.subject).endswith(".confidence")]
    assert len(on_confidence) >= 1, "no Match on confidence subject"
    m = on_confidence[0]
    case_names = [ast.unparse(c.pattern) for c in m.cases]
    assert any("Trusted()" in p for p in case_names)
    assert any("Degraded()" in p and "Unavailable()" in p for p in case_names), \
        "expected combined Degraded() | Unavailable() arm"
    # assert_never final arm
    final = m.cases[-1]
    body_src = "\n".join(ast.unparse(s) for s in final.body)
    assert "assert_never" in body_src
```

Static (`tests/static/test_bundle_module_docstring.py`):

```python
def test_module_docstring_cites_adr_and_rejection():
    tree = ast.parse(Path("src/codegenie/plugins/bundle.py").read_text())
    doc = ast.get_docstring(tree) or ""
    assert "ADR-0008" in doc
    assert "hedged-race" in doc
```

### Green

Smallest impl: §Implementation outline; ~140 lines.

### Refactor

- (Already mandated by ACs — leave only nice-to-haves here.)
- Add structlog `bundle.query_dispatched` info per query at the `_acquire_then_dispatch` boundary (operator visibility; do not log inside `_compose_entry` — keep the pure fold pure).
- Consider a `BundleBuilderConfig` dataclass to pass `(concurrency_bound, max_fallback_depth)` rather than env-vars + module constants — Phase 14 may want per-workflow overrides. YAGNI for Phase 3 (one knob, one constant) — flag in module docstring only.
- Add a `tests/integration/plugins/test_bundle_with_real_phase02_adapters.py` once Phase 2 adapters are wired (S7-02). Out-of-scope here; leave a TODO comment.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/plugins/bundle.py` | New module — `BundleBuilder`, `Bundle`, `BundleEntry`, `BundleBuilderError`, `BundleBuilderRaise`, `BundleBuilderEvent` (`AdapterDegraded` + `FallbackChainTooDeep`), `AdapterDispatch`, `AdapterResult`, `_canonicalize_args`, `_compose_entry`, `_resolve_chain`, `_read_concurrency_bound` |
| `tests/unit/plugins/test_bundle_builder.py` | Unit tests for concurrency + serial-fallback semantics + error propagation + empty bands + `_compose_entry` purity |
| `tests/unit/plugins/conftest.py` | Spy-resolution fixtures (`_resolution_with_one_query_and_fallback`, `_resolution_with_chain`, `_resolution_with_empty_tccm`, `_vuln_index_fixture`) |
| `tests/property/test_bundle_determinism.py` | 100-run determinism property test under seeded scheduler jitter + `xfail` meta-test |
| `tests/property/test_bundle_serial_fallback.py` | 100-run serial-fallback property test |
| `tests/property/_hedged_race_reference.py` | Fixture-only deliberately-broken hedged-race builder for AC-23 (never imported by production code; fence test verifies) |
| `tests/static/test_no_hedged_race_in_bundle.py` | AST positive structural defense (AC-27) |
| `tests/static/test_bundle_dispatch_pattern.py` | AST: `match` + `assert_never` on `AdapterConfidence` (AC-14) |
| `tests/static/test_bundle_module_docstring.py` | AST: docstring cites ADR-0008 + "hedged-race" (AC-1) |

## Out of scope

- **Cache key composition + cache lookup** — S3-05 ships the BLAKE3 key (including `vuln_index.digest`) and the on-disk cache; this story builds the in-memory `Bundle` only.
- **`BundleCacheGc`** — S3-05 (Gap 4 fix).
- **`composed_dispatch` *construction*.** S3-04 *consumes* `resolution.composed_dispatch: dict[PrimitiveName, AdapterDispatch]` (via the new typed seam) but does NOT build it. Production wiring (mapping `"scip.refs" → scip_adapter.refs`, etc.) is S7-02. Tests construct the dispatch table directly.
- **Real Phase 2 search-adapter wiring** — Phase 2's `ScipAdapter`/`DepGraphAdapter`/`ImportGraphAdapter`/`TestInventoryAdapter` protocols are plumbed by S7-02; this story uses spy `AdapterDispatch` callables in tests.
- **`TrustScorer.confidence` folding** — S6-02 reads `AdapterDegraded` events from the `EventLog`; this story just emits them via the seam.
- **Deferred `may_read` execution** — ADR-0029 allows worker nodes to lazily request `may_read`; Phase 3 executes all three bands eagerly. Document the deviation in the module docstring; Phase 6 may revisit.
- **Cancellation on partial failure** — `asyncio.gather` (default behavior) propagates the first exception and cancels siblings; richer `return_exceptions=True` + per-entry error variants are an S6-04 concern.
- **`CanonicalArgsJson` newtype.** Smart-constructor wrapping of `args_canonical` is recommended by the design-patterns critic but deferred: S3-05 will derive the BLAKE3 cache key from `BundleEntry.args_canonical` and is the natural owner of a canonical-JSON value type. If S3-05 needs it, S3-05 lands it; for now `args_canonical: str` plus the pinned format AC (AC-13) is the contract.

## Notes for the implementer

- **The hedged-race rejection is a hard line.** Production design §2.4 is **veto-strength**; the determinism property test (S8-03) will fail by construction if you ever race `(primary, fallback)`. The AST positive structural defense (AC-27) is belt-and-suspenders; do not weaken it. If you find yourself wanting to add `asyncio.gather` inside `_resolve_chain`, stop and re-read ADR-0008 §Decision.
- **`AdapterConfidence` is a tagged union, NOT an enum.** Variants are `Trusted | Degraded | Unavailable` (Pydantic `BaseModel`s discriminated by `kind`). `Trusted()` has no `reason`; `Degraded(reason=...)` and `Unavailable(reason=...)` do. Dispatch via `match` + `assert_never` (ADR-0010). The (wrong) set-membership form `confidence in {Degraded, Unavailable}` always evaluates `False` — instance against class identity — and would silently never fire any fallback.
- **`AdapterDispatch` is a typed Callable, not a Protocol.** `Callable[[ContextQuery], Awaitable[AdapterResult]]`. The reason it's a callable (not a `Protocol` with a `__call__` method): per-primitive functions adapt naturally to per-protocol Phase 2 methods (`scip_adapter.refs`, `dep_graph.consumers`). The `composed_dispatch` table is the registry — open/closed by addition of a new primitive entry.
- **The semaphore is per-call AND per-band-task — NOT inside `_resolve_chain`.** This is the AC-16 invariant. Picture it: `build()` spawns N coroutines, each is `_acquire_then_dispatch(semaphore, query)`; `_acquire_then_dispatch` `async with`s the semaphore exactly once, then calls `_resolve_chain` which walks the fallback chain inside the held slot. **`_resolve_chain` never `async with`s the semaphore.** If it did, a depth-4 chain would hold 4 slots; with `concurrency_bound=4` and 4 degraded queries you'd silently deadlock.
- **`_resolve_chain` is iterative, not recursive.** Use a `while query is not None and depth < _MAX_FALLBACK_DEPTH:` loop. The depth-cap check must be `>= 4` to raise after the 4th degraded step (matches `_MAX_FALLBACK_DEPTH = 4`; off-by-one is the classic silent bug — AC-17 + AC-18 boundary tests pin both sides).
- **`_compose_entry` is pure.** No `await`, no event emission, no logging, no I/O. Just packs `(query, primary_result, fallback_result | None)` into a `BundleEntry`. The AST test (AC-27 (c)) enforces this structurally. This is the "Functional core / imperative shell" spirit of ADR-0008 §Pattern fit — keep it pure and you get the determinism property almost for free.
- **`AdapterDegradedEvent` placement.** S6-01 will land the workflow `EventLog` taxonomy. Define `AdapterDegraded`, `FallbackChainTooDeep`, and `BundleBuilderEvent` in `bundle.py` for now; S6-01 will absorb them by re-export from a future `codegenie.events.bundle` module — no rename needed. Cite this in a comment near the event class definitions.
- **`_MAX_FALLBACK_DEPTH = 4` matches the `extends`-chain cap in S2-04** — same intuition: human-authored YAML, deeper than 4 is almost always a mistake. Keep symmetric. If you change one, change both (and amend the ADR).
- **`event_emitter=None` default** keeps this story testable without S6-01's `EventLog`. The orchestrator (S6-04) wires `event_emitter=event_log.emit_internal` at construction. Do NOT make `EventLog` a required dep — that would block this story on S6-01. The seam takes `BundleBuilderEvent` (the union), not just `AdapterDegraded` — this is extension-by-addition for S6-04's future cancellation events.
- **Fail-loud on `event_emitter` raising (AC-21).** Do NOT wrap the emit call in `try/except`. If the emitter is buggy, the build must fail with the original exception — otherwise `TrustScorer.confidence` silently reports `High` while reality is `Degraded`, which is exactly the failure mode ADR-0008 / Goal G8 are guarding against.
- **`canonicalize(args)`** — `json.dumps(args, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`. Pinned by AC-13 with a literal-string assertion; do not skip `sort_keys`, do not change separators. S3-05 hashes this.
- **`os.cpu_count() or 1`** — on weird hosts (containers without cpu-affinity, restricted cgroups) `cpu_count()` returns `None`; the `or 1` keeps the bound positive. AC-10 pins the test (monkeypatch `os.cpu_count`).
- **`SandboxedPath` import** — currently `TypeAlias = pathlib.Path` in `codegenie.transforms._forward`. Import from there; do not redeclare. The `__annotations__` test in AC-8 catches a regression where the import is replaced by raw `Path`.
- **Beware Pydantic v2 `tuple[BundleEntry, ...]`** — sometimes needs `Annotated[tuple[BundleEntry, ...], ...]` for proper serialization round-trip. AC-25 pins the round-trip property; if it fails, switch to `Sequence[BundleEntry]` + convert to tuple in a `model_validator(mode="after")`.
- **`_hedged_race_reference.py` is fixture-only** — it implements the broken hedged-race variant for AC-23's `xfail(strict=True)` meta-test. Add a fence test (`tests/unit/test_pyproject_fence.py` or a new `tests/static/test_hedged_race_reference_not_imported_by_production.py`) that asserts no module under `src/codegenie/` imports it.
