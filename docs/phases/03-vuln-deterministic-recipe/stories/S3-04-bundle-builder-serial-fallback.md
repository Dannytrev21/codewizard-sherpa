# Story S3-04 — `BundleBuilder` with `asyncio.Semaphore` concurrency + deterministic serial fallback (ADR-0008)

**Step:** Step 3 — TCCM, BundleBuilder, VulnIndex, content-addressed cache
**Status:** HARDENED
**Effort:** M
**Depends on:** S3-01, S3-02, S2-04
**ADRs honored:** Phase 3 ADR-0008 (deterministic serial fallback; NOT hedged-race — production design §2.4 is veto-strength), Phase 3 ADR-0010 (sum-type / newtype discipline; smart constructors at boundaries), production ADR-0029 (TCCM `must_read`/`should_read`/`may_read`), production ADR-0030 (graph-aware query primitives), production ADR-0032 (language search adapters expose `AdapterConfidence` via `confidence()` method), production ADR-0033 (newtype every domain identifier)

## Validation notes

Hardened by `/phase-story-validator`. Findings recorded in `_validation/S3-04-bundle-builder-serial-fallback.md`. Changes applied here:

- **Adapter-shape mismatch.** Original story assumed a uniform `adapters[primitive].query(args) → Result(confidence=..., payload=...)`. Phase 02 ships per-primitive typed methods (`ScipAdapter.refs`, `ImportGraphAdapter.reverse_lookup`, `DepGraphAdapter.consumers/.producers`, `TestInventoryAdapter.tests_exercising`) and `adapter.confidence() → AdapterConfidence` is a **method on the adapter** (not the result). TDD spy adapters rewritten; new AC-7 introduces a `@register_primitive_dispatcher(PrimitiveName)` registry that decouples `BundleBuilder` from the per-primitive method names. (Coverage F2/F3, Consistency C2 BLOCK, Design-Patterns DP1 tier-1.)
- **`AdapterConfidence.High` does not exist.** Actual variants are `Trusted | Degraded | Unavailable` (`src/codegenie/adapters/confidence.py`). Every `.High` read replaced with `Trusted()` construction; "degraded" detection uses `isinstance(c, (Degraded, Unavailable))` (or `match` with `assert_never`). (Coverage F1, Consistency C1 BLOCK.)
- **`BundleBuilderError(CodegenieError)` markers-only with typed `.reason` access** — same contradiction S3-01 (`TCCMParseError`), S3-02 (`VulnIndexLookupError`/`VulnIndexConfigError`), and S3-03 (`VulnParseError`) all resolved by redesign-as-frozen-Pydantic-BaseModel + closed `Literal[...]` reason + thin `BundleBuilderException(model: BundleBuilderError)` wrapper. (Coverage F4, Consistency C3 BLOCK, Design-Patterns precedent.)
- **Semaphore-on-recursion deadlock.** Original outline acquires `asyncio.Semaphore` inside `_run_one`, then recursively calls `_run_one(query.fallback, …)` while still holding the permit. With `CODEGENIE_BUNDLE_CONCURRENCY=1` (CI tuning per ADR-0008's escape-hatch motivation) every fallback firing deadlocks. Implementation outline rewritten: semaphore is acquired at `_dispatch_query` boundary (one acquire per chain, **NOT per recursive call**); fallback resolution releases the parent's permit before re-acquiring. (Coverage F5 derived, Consistency C4 BLOCK.)
- **Per-primitive dispatcher registry as the Open/Closed seam.** Three established registry-pattern precedents in this codebase (`@register_index_freshness_check`, `@register_dep_graph_strategy`, `@register_probe`); rule-of-three crossed. AC-7 + AC-8 promote the dispatch table to a typed registry so Phase 4+ adds a sixth primitive (per future ADR-0030 amendment) in one new file with zero edits to `bundle.py`. (Design-Patterns DP1 tier-1.)
- **`AdapterDegraded` event (not `AdapterDegradedEvent`)** to match arch §C9's `WorkflowInternalEvent` taxonomy — S6-01 will register the symbol as `AdapterDegraded`. (Consistency C8.)
- **Concurrency read at builder construction, not module import.** Original AC implied module-import-time read of `CODEGENIE_BUNDLE_CONCURRENCY`, which makes `monkeypatch.setenv(...)` ineffective in tests. AC-15 explicit: read inside `BundleBuilder.__init__`. (Coverage F8.)
- **`args_canonical` canonicalization pinned** as `json.dumps(args, sort_keys=True, separators=(",", ":"))` with a collision test (`{"a":1,"b":2}` and `{"b":2,"a":1}` → identical bytes). Load-bearing for S3-05's BLAKE3 cache key. (Coverage F9.)
- **Per-call semaphore (not module-level)** — promoted from Notes to AC-14 + observable test (two concurrent `build()` coroutines on the same builder with `CONCURRENCY=1` both progress). (Coverage F7.)
- **AST scan generalized** to forbid `asyncio.{gather, wait, as_completed}` calls whose arguments mention `fallback` — not just `gather` (Test-Quality TQ-H4). Relocated to `tests/unit/plugins/test_bundle_no_hedged_race.py` per codebase precedent (`tests/unit/plugins/test_scope_purity.py`) instead of a non-existent `tests/static/` directory. (Consistency C6, Coverage F18.)
- **Module-import purity AC** added (AC-24) — fence the imports of `src/codegenie/plugins/bundle.py` to a closed allowlist, matching S3-03's fence precedent. Guards against accidental heavyweight imports (`requests`, `httpx`, `anthropic`, …).
- **Bundle.plugin_id newtype-wrapped** via explicit `PluginId(resolution.plugin.manifest.name)` cast — production ADR-0033 boundary discipline. (Consistency C7.)
- **Empty TCCM corner case** explicit (AC-22): zero queries → `Bundle(entries=(), …)` with `vuln_index_digest` populated.
- **Tier-2 design opportunities surfaced in Notes (not promoted to ACs):** tagged-union `dispatch_path: PrimaryUsed | FallbackUsed(depth)` instead of `fallback_used: bool` (DP3); typed `AdapterPayload` sum (DP4). Rule 2 (simplicity) keeps the primitive shapes at the boundary; `extra="forbid"` keeps later widening ADR-gated.
- **Tautological AC removed** (Coverage F5).

## Context

`BundleBuilder` dispatches a plugin's TCCM `must_read` / `should_read` / `may_read` queries through Phase 2's language search adapters and returns a typed `Bundle`. Concurrency is bounded by `asyncio.Semaphore(min(4, os.cpu_count() or 1))` overridable via `CODEGENIE_BUNDLE_CONCURRENCY`. **Fallback semantics is the load-bearing decision** — ADR-0008 explicitly *rejects* hedged-race composition because two runs against the same inputs would return different Bundle bytes (scheduler noise), violating production design §2.4's "same inputs → same Transform bytes" veto-strength commitment. The TCCM-declared `fallback` query fires **only** when the primary adapter's `confidence()` returns `Degraded | Unavailable` — never raced, never both. Property-tested across 100 Hypothesis runs for byte-identical output (including under random scheduling shuffle — a hedged-race impl fails the property).

Phase 02 ships `AdapterConfidence` as the discriminated union `Trusted | Degraded | Unavailable` (`src/codegenie/adapters/confidence.py`) and the four `@runtime_checkable` Protocols (`ScipAdapter`, `ImportGraphAdapter`, `DepGraphAdapter`, `TestInventoryAdapter`) — **each with its own method names**. Mapping `PrimitiveName → (adapter-method, payload-shape)` is this story's Open/Closed seam: a typed registry decorator `@register_primitive_dispatcher(PrimitiveName)` ships here (DP1 tier-1) so Phase 4+ can add a sixth primitive in one new file with zero edits to `bundle.py`.

This story ships the builder's structure, the semaphore, the serial-fallback dispatch, the per-primitive dispatcher registry, and the `AdapterDegraded` event hand-off. The cache key (which includes `vuln_index.digest`) and the `BundleCacheGc` GC mechanism land in S3-05 (Gap 4).

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §C7. BundleBuilder` — public interface, cache key shape, concurrency bound, fallback semantics, performance envelope (warm 3 ms, cold 220 ms, degraded ~180 ms).
  - `../phase-arch-design.md §Patterns considered and deliberately rejected — "No hedged-race in BundleBuilder"` — the rejection rationale; cite in module docstring.
  - `../phase-arch-design.md §C9. EventLog two-stream writer` — `WorkflowInternalEvent` taxonomy where `AdapterDegraded` lives.
  - `../phase-arch-design.md §Goals G4 + G8` — determinism (G4) + confidence propagation (G8).
- **Phase ADRs (load-bearing — read before implementing):**
  - `../ADRs/0008-bundlebuilder-deterministic-serial-fallback-and-vuln-index-digest-cache-key.md §Decision + §Tradeoffs` — "Adopt Option C — declarative serial fallback, AND `vuln_index.digest` included in the Bundle cache key."
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` — sum-type / newtype / smart-constructor discipline (drives `BundleBuilderError` shape).
- **Production ADRs:**
  - `../../../production/adrs/0032-language-search-adapters.md` — `confidence() → AdapterConfidence` is mandatory across adapters.
  - `../../../production/adrs/0030-graph-aware-context-queries.md` — primitive set the adapters expose.
  - `../../../production/adrs/0033-typed-identifiers.md` — newtype every domain identifier.
- **Implementation plan:**
  - `../High-level-impl.md §Step 3` — done criteria: "cache-hit / cache-miss / `vuln_index.digest` invalidation; degraded adapter triggers declared fallback deterministically" + property test "across 100 runs with a `Degraded` primary adapter, the fallback is invoked exactly once per query (never raced)."
- **Existing code:**
  - `src/codegenie/adapters/confidence.py` — `AdapterConfidence = Annotated[Trusted | Degraded | Unavailable, Field(discriminator="kind")]`; **note: variants are `Trusted/Degraded/Unavailable`, NOT `High`**.
  - `src/codegenie/adapters/protocols.py` — four `@runtime_checkable` Protocols, each with **its own method names** + `confidence() → AdapterConfidence`.
  - `src/codegenie/plugins/tccm.py` (S3-01) — `ContextQuery` with `fallback: ContextQuery | None`; consumed here.
  - `src/codegenie/plugins/resolver.py` (S2-04) — `ConcreteResolution.composed_adapters: dict[PrimitiveName, Adapter]` (Adapter is one of the four Protocol surfaces by-primitive).
  - `src/codegenie/types/identifiers.py` (S1-01) — `PluginId`, `PrimitiveName`, `BlobDigest`.
  - `src/codegenie/types/errors.py` (S1-01) — `ParseError` Pydantic precedent.
  - `src/codegenie/depgraph/registry.py` (Phase 02) — `@register_dep_graph_strategy(PackageManager)` registry-pattern precedent to mirror.
  - `src/codegenie/indices/freshness.py` (Phase 02) — `@register_index_freshness_check(IndexName)` precedent.
  - `src/codegenie/vuln_index/index.py` (S3-02) — `VulnIndex.digest() → BlobDigest`.

## Goal

`codegenie.plugins.bundle.BundleBuilder` exposes `async def build(resolution, repo_ctx, vuln, vuln_index) -> Bundle`; dispatch is bounded by `asyncio.Semaphore(min(4, os.cpu_count() or 1))` (overridable via `CODEGENIE_BUNDLE_CONCURRENCY`, read at builder construction); the TCCM-declared `fallback` chain fires **deterministically and serially** *only* when the primary adapter's `confidence()` returns `Degraded | Unavailable` — never raced. An `AdapterDegraded` event is emitted on every fallback firing (before the fallback's adapter method runs) for `TrustScorer.confidence` folding (Goal G8). The mapping from `PrimitiveName` to per-Protocol adapter method lives in a registry seam (`@register_primitive_dispatcher(PrimitiveName)`) so a future ADR-0030-amendment primitive lands in one new file with zero edits to `bundle.py`. Property-tested for byte-identical `Bundle` output across 100 Hypothesis runs (including under random scheduling shuffle).

## Acceptance criteria

### Module surface

- [ ] **AC-1** — New module `src/codegenie/plugins/bundle.py` exports exactly `{BundleBuilder, Bundle, BundleEntry, BundleBuilderError, BundleBuilderException, AdapterDegraded, register_primitive_dispatcher, _MAX_FALLBACK_DEPTH}` (set-equality on `__all__`, not `⊇`). Module docstring cites ADR-0008 §Decision, the rejection of hedged-race, production design §2.4 (veto-strength source), and arch §C7.

### Error model (markers-only contradiction resolved per Validation notes)

- [ ] **AC-2** — `BundleBuilderError` is a frozen Pydantic `BaseModel` (NOT a `CodegenieError` subclass — mirrors S3-01 `TCCMParseError`, S3-02 `VulnIndexLookupError`, S3-03 `VulnParseError` precedent). `model_config = ConfigDict(frozen=True, extra="forbid")`. Fields:
  - `reason: Literal["invalid_concurrency_env", "fallback_chain_too_deep", "primitive_not_dispatched", "adapter_missing_for_primitive"]` (closed set; additions require ADR amendment).
  - `details: dict[str, str | int] = {}` (carries offending value, e.g. `{"primitive": "scip.refs"}` or `{"depth": 5}`).
  `BundleBuilderException` is a thin `Exception` subclass with a single typed attribute `model: BundleBuilderError`. Production call sites construct the model then `raise BundleBuilderException(model)`. Tests assert `exc.value.model.reason == "invalid_concurrency_env"`.
- [ ] **AC-3** — mypy-strict meta-test: `BundleBuilderError(reason="typo", details={})` is rejected at runtime by Pydantic AND flagged by `mypy --strict` at the call site (parametrized mypy meta-test mirrors S3-02 AC-C4).

### Bundle + entry shape

- [ ] **AC-4** — `BundleEntry` is a frozen Pydantic `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")` and fields:
  - `primitive: PrimitiveName`
  - `args_canonical: str` (canonicalized JSON of `ContextQuery.args` per AC-12; cache-key composition surface for S3-05)
  - `payload: dict[str, str | int | bool | list[str]]` (primitive-only; matches `TrustSignal.details` discipline; typed `AdapterPayload` sum is a tier-2 deferred opportunity — see Notes)
  - `confidence: AdapterConfidence` (the full discriminated-union instance, NOT the discriminator string)
  - `fallback_used: bool` (forward-compatible with tier-2 `dispatch_path` sum — see Notes)
- [ ] **AC-5** — `Bundle` is a frozen Pydantic `BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid")` and fields:
  - `entries: tuple[BundleEntry, ...]` (tuple for hash-stability)
  - `plugin_id: PluginId` (newtype, explicit `PluginId(resolution.plugin.manifest.name)` wrap per production ADR-0033)
  - `vuln_index_digest: BlobDigest` (S3-02 `VulnIndex.digest()` result; ADR-0008 cache-key correctness surface for S3-05)

### Construction

- [ ] **AC-6** — `BundleBuilder.__init__(cache_dir: Path, *, event_emitter: Callable[[AdapterDegraded], None] | None = None)` — `event_emitter` is the seam for S6-01's `EventLog.emit_internal`; defaults to no-op so this story is testable without the full `EventLog`. The S6-04 orchestrator wires `event_emitter=lambda e: event_log.emit_internal(e)` (returned `EventId` discarded — see Notes).

### Per-primitive dispatcher registry (Open/Closed seam — DP1 tier-1)

- [ ] **AC-7** — `src/codegenie/plugins/bundle.py` ships a module-level decorator `register_primitive_dispatcher(primitive: PrimitiveName)` that registers a `Callable[[Adapter, dict[str, str | int | bool | list[str]]], Awaitable[tuple[dict[str, str | int | bool | list[str]], AdapterConfidence]]]` into a module-private `_PRIMITIVE_DISPATCHERS: Final[dict[PrimitiveName, ...]]`. Each registered dispatcher: (a) calls the appropriate typed adapter method (e.g., `await adapter.refs(args["symbol"])` wrapped in `asyncio.to_thread` if the protocol method is sync), (b) reads `adapter.confidence()`, (c) returns `(canonical_payload_dict, confidence)`. **Five dispatchers ship at module-import time**, one per `PrimitiveName` in `tccm._KNOWN_PRIMITIVES`:
  - `scip.refs` → `ScipAdapter.refs(args["symbol"]) → list[Occurrence]` → `{"refs": [...]}`
  - `import_graph.reverse_lookup` → `ImportGraphAdapter.reverse_lookup(args["module"]) → list[str]` → `{"files": [...]}`
  - `import_graph.transitive_callers` → reserved; raises `BundleBuilderException(BundleBuilderError(reason="primitive_not_dispatched", details={"primitive": "import_graph.transitive_callers"}))` until ADR-0030 amendment lands the protocol method
  - `dep_graph.consumers` → `DepGraphAdapter.consumers(args["pkg"]) → list[str]` → `{"consumers": [...]}`
  - `test_inventory.tests_exercising` → `TestInventoryAdapter.tests_exercising(args["symbol"]) → list[TestId]` → `{"tests": [str(t) for t in result]}`
  Registry-duplicate registration raises at module-import time. Mirrors `@register_dep_graph_strategy(PackageManager)` (`src/codegenie/depgraph/registry.py`) — Rule 11 (match existing convention).
- [ ] **AC-8** — `_PRIMITIVE_DISPATCHERS.keys() == frozenset(tccm._KNOWN_PRIMITIVES)` is asserted at module import time via `raise AssertionError(...)` (`forbidden-patterns` hook forbids bare `assert`). Adding a sixth primitive to `tccm._KNOWN_PRIMITIVES` without adding its dispatcher fails CI. **Observable Open/Closed test**: `tests/unit/plugins/test_bundle_extension_by_addition.py` registers a stub `_KNOWN_PRIMITIVES` 6th entry + a stub dispatcher in a fixture (monkeypatch) and asserts `BundleBuilder.build` dispatches it correctly **with zero edits to `bundle.py`**.

### `BundleBuilder.build` semantics

- [ ] **AC-9** — `async def build(self, resolution: ConcreteResolution, repo_ctx: RepoContext, vuln: VulnerabilityRecord, vuln_index: VulnIndex) -> Bundle` iterates queries in order `resolution.composed_tccm.must_read` THEN `should_read` THEN `may_read` (deferred `may_read` execution per ADR-0029 is OUT of scope — Phase 3 executes all three eagerly; module docstring records the deviation).
- [ ] **AC-10** — **Concurrency bound:** all queries run under one **per-call** `asyncio.Semaphore` (constructed inside `build`, **NOT** module-level — see AC-14). The bound is `self._concurrency` as resolved by AC-15.
- [ ] **AC-11** — **Deterministic serial fallback (NOT hedged race — ADR-0008):** for each `ContextQuery`, the dispatcher invokes the primary via `_PRIMITIVE_DISPATCHERS[query.primitive](adapter, query.args)` and reads the returned `AdapterConfidence`. ONLY if `isinstance(confidence, (Degraded, Unavailable))` AND `query.fallback is not None`, fire the fallback. The fallback runs **after** the primary completes — never concurrently. **The fallback's dispatch acquires its own semaphore permit only after the primary's permit has been released** (avoids the recursion-deadlock at `CONCURRENCY=1` — see Notes "Semaphore acquire pattern"). NEVER fire both speculatively.

### Canonicalization + ordering (load-bearing for S3-05 cache key)

- [ ] **AC-12** — `BundleEntry.args_canonical` is computed via `json.dumps(ContextQuery.args, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`. Test pins **collision**: two `ContextQuery` instances with `args={"a": 1, "b": 2}` and `args={"b": 2, "a": 1}` produce **byte-identical** `args_canonical` strings AND **byte-identical** `BundleEntry.model_dump_json()`. A dev who switches to `json.dumps(args)` (no sort) fails this test.
- [ ] **AC-13** — **Order preservation:** for a `composed_tccm` with `must_read=[Q1, Q2]`, `should_read=[Q3]`, `may_read=[Q4]`, the resulting `Bundle.entries == (entry_for_Q1, entry_for_Q2, entry_for_Q3, entry_for_Q4)` in this exact order. `asyncio.gather(*tasks, return_exceptions=False)` returns results in input order (load-bearing for determinism). Property test pins this across 100 shuffled-args inputs.

### Concurrency isolation + env-var read time

- [ ] **AC-14** — **Per-call semaphore (NOT module-level).** Test: with `CODEGENIE_BUNDLE_CONCURRENCY=1`, spawn two concurrent `BundleBuilder.build(...)` coroutines on the **same `BundleBuilder` instance**, each with a query that takes 50 ms (via a `SlowAdapter`). Wall-clock elapsed ≈ 50 ms (both progress in parallel), NOT ≈ 100 ms (which would prove a shared module-level semaphore). AST scan in `tests/unit/plugins/test_bundle_no_hedged_race.py` (AC-23) ALSO asserts no module-level `asyncio.Semaphore` assignment.
- [ ] **AC-15** — `CODEGENIE_BUNDLE_CONCURRENCY` is read **inside `BundleBuilder.__init__`**, not at module import time, so `monkeypatch.setenv(...)` in tests takes effect on the next builder constructed. The validation:
  - Empty / unset → `min(4, os.cpu_count() or 1)`.
  - Non-int (`"not-a-number"`) → `raise BundleBuilderException(BundleBuilderError(reason="invalid_concurrency_env", details={"value": <raw>}))`.
  - Non-positive int (`"0"`, `"-3"`) → same.
  - Valid positive int → use it.

### Fallback chain semantics

- [ ] **AC-16** — **Fallback chain depth cap:** `ContextQuery.fallback` is itself a `ContextQuery` (may have its own `fallback`). Cap depth at `_MAX_FALLBACK_DEPTH: Final[int] = 4` (mirrors S2-04 `extends`-chain cap — symmetric intuition). On overflow: `raise BundleBuilderException(BundleBuilderError(reason="fallback_chain_too_deep", details={"primitive": str(query.primitive), "depth": depth}))`.
- [ ] **AC-17** — Depth-cap boundary tested: depth 4 (allowed) succeeds; depth 5 (rejected) raises with `reason="fallback_chain_too_deep"` AND `details["depth"] == 5`.
- [ ] **AC-18** — `BundleEntry.fallback_used` is `True` iff **any** fallback in the chain fired for that query (i.e., the primary returned `Degraded | Unavailable` and the chain produced the final result). It is `False` iff the primary returned `Trusted`. Trivially: `entries[i].confidence` is the confidence of **whichever adapter in the chain produced the result** (the last one, on a fallback path).

### Event emission

- [ ] **AC-19** — **`AdapterDegraded` event emission:** on every fallback firing, call `event_emitter(AdapterDegraded(primitive=..., adapter_name=..., reason=...))`. The event is emitted **before** the fallback's adapter method is invoked (operators see "we're falling back" not "we fell back"). **Test (timing spy):** an event-emitter spy records `time.monotonic()` per emit; an adapter spy records `time.monotonic()` per method call; assert `emit_time < fallback_method_call_time` for every fallback firing. Property test: 100 Hypothesis runs with primary always `Degraded` → exactly `len(must_read + should_read + may_read)` events emitted, in input order, exactly once per query.
- [ ] **AC-20** — `AdapterDegraded` is a frozen Pydantic `BaseModel`: `model_config = ConfigDict(frozen=True, extra="forbid")`, fields: `kind: Literal["adapter_degraded"] = "adapter_degraded"` (discriminator for S6-01's `WorkflowInternalEvent` union), `primitive: PrimitiveName`, `adapter_name: str`, `reason: str`. Symbol name matches arch §C9 taxonomy (no `Event` suffix).

### Determinism + structural defenses (the hedged-race veto)

- [ ] **AC-21** — **Determinism property test** (`tests/property/plugins/test_bundle_determinism.py`): 100 Hypothesis runs of `BundleBuilder.build(...)` with identical inputs (and a fixed dispatcher set returning a fixed payload + `Trusted()`) return `Bundle` instances with byte-identical `model_dump_json()`. Failure attaches the diff for debugging. Includes a **timing-shuffle variant**: a `SlowAdapter` parameterized by a seed-derived RNG returns the same payload at random delays per seed; byte-identical `model_dump_json()` holds across all 100 seeds (a hedged-race impl whose primary loses to a faster fallback returns different bytes on different seeds, failing the property).
- [ ] **AC-22** — **Serial-fallback property test** (`tests/property/plugins/test_bundle_serial_fallback.py`): 100 runs with primary always `Degraded` AND fallback always `Trusted` — the fallback is invoked **exactly once per query** (spy adapter counts), the primary is invoked **exactly once per query**, and the two invocation orders are deterministic (primary BEFORE fallback for every query — NEVER both raced). Additionally: empty TCCM (`must_read=[]`, `should_read=[]`, `may_read=[]`) → `Bundle(entries=(), plugin_id=..., vuln_index_digest=...)`; zero events emitted; no error.
- [ ] **AC-23** — **AST source-scan** (`tests/unit/plugins/test_bundle_no_hedged_race.py`): walk `src/codegenie/plugins/bundle.py` AST and assert no `ast.Call` node where `func.attr ∈ {"gather", "wait", "as_completed"}` (on either `asyncio` or via a `from asyncio import …` alias) has any argument whose `ast.unparse(arg)` substring contains `"fallback"`. Mirror for `module.gather` aliases. ALSO assert no module-level `asyncio.Semaphore` assignment (AC-14 belt-and-suspenders) — i.e., `_PATTERN := re.compile(r"^\s*\w+\s*=\s*asyncio\.Semaphore\(")` matches no line outside a function body.

### Module-import purity (cold-start fence — echo S3-03)

- [ ] **AC-24** — `tests/unit/plugins/test_bundle_module_purity.py` AST-walks `src/codegenie/plugins/bundle.py`; the union of all `ast.Import` / `ast.ImportFrom` module names is a **subset of** `{"__future__", "asyncio", "json", "os", "typing", "collections.abc", "pydantic", "codegenie.adapters", "codegenie.plugins.tccm", "codegenie.plugins.resolver", "codegenie.types.identifiers", "codegenie.types.errors", "codegenie.result", "codegenie.hashing", "codegenie.errors"}`. No `requests`, `httpx`, `urllib`, `logging`, `structlog` (structlog moved to refactor / lazy if needed). Cold-start budget honored.

### Boundary discipline

- [ ] **AC-25** — `Bundle.plugin_id` is constructed via `PluginId(resolution.plugin.manifest.name)` (explicit newtype wrap at the boundary, not implicit `cast`). Test pins: `type(bundle.plugin_id) is PluginId` (PEP 484 NewType is a function at runtime — assertion uses `mypy --strict` flow narrowing, not `type()`; pin via an assert that `bundle.plugin_id == PluginId("vulnerability-remediation--node--npm")`).
- [ ] **AC-26** — `os.cpu_count() or 1` corner case tested: `monkeypatch.setattr(os, "cpu_count", lambda: None)` + no env override → bound resolves to `min(4, 1) == 1`. (The `or 1` is the safety branch.)
- [ ] **AC-27** — Exception propagation: if a primitive dispatcher raises (other than `BundleBuilderException`), `asyncio.gather(*tasks, return_exceptions=False)` propagates and `build` raises. Test pins this current behavior with a docstring comment "richer per-entry error variants are a S6-04 concern". A future ADR amendment may revisit.

### Quality gates

- [ ] **AC-28** — `mypy --strict` clean. `ruff check`, `ruff format` clean. Module purity AC-24 + AST scan AC-23 both green.

## Implementation outline

1. **Create `src/codegenie/plugins/bundle.py`**:
   - Imports per AC-24 allowlist: `asyncio`, `json`, `os`, `Final`, `Awaitable`, `Callable` from `typing`/`collections.abc`; `BaseModel`, `ConfigDict` from `pydantic`; `PluginId`, `PrimitiveName`, `BlobDigest` from `codegenie.types.identifiers`; `AdapterConfidence`, `Degraded`, `Unavailable`, `Trusted` from `codegenie.adapters`; `ContextQuery`, `_KNOWN_PRIMITIVES` from `codegenie.plugins.tccm` (or a re-exported public surface).
   - Module-level constants:
     ```python
     _MAX_FALLBACK_DEPTH: Final[int] = 4
     _DEFAULT_CONCURRENCY: Final[int] = min(4, os.cpu_count() or 1)
     _ENV_VAR: Final[str] = "CODEGENIE_BUNDLE_CONCURRENCY"
     ```
   - `def _read_concurrency() -> int` — reads env, validates, returns int; on bad value raises `BundleBuilderException(BundleBuilderError(reason="invalid_concurrency_env", details=...))`.
   - `def _canonicalize_args(args: dict[str, ...]) -> str` — `json.dumps(args, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`.
   - `class BundleBuilderError(BaseModel)`, `class BundleBuilderException(Exception)` per AC-2.
   - `class AdapterDegraded(BaseModel)` per AC-20.
   - `class BundleEntry(BaseModel)`, `class Bundle(BaseModel)` per AC-4 / AC-5.
   - **Registry seam** (mirrors `codegenie.depgraph.registry`):
     ```python
     PrimitiveDispatcher = Callable[
         [object, dict[str, str | int | bool | list[str]]],
         Awaitable[tuple[dict[str, str | int | bool | list[str]], AdapterConfidence]],
     ]
     _PRIMITIVE_DISPATCHERS: Final[dict[PrimitiveName, PrimitiveDispatcher]] = {}

     def register_primitive_dispatcher(primitive: PrimitiveName) -> Callable[[PrimitiveDispatcher], PrimitiveDispatcher]:
         def decorator(fn: PrimitiveDispatcher) -> PrimitiveDispatcher:
             if primitive in _PRIMITIVE_DISPATCHERS:
                 raise BundleBuilderException(BundleBuilderError(
                     reason="primitive_not_dispatched",
                     details={"primitive": str(primitive), "issue": "duplicate"},
                 ))
             _PRIMITIVE_DISPATCHERS[primitive] = fn
             return fn
         return decorator
     ```
   - Five dispatcher registrations inline (one per known primitive); the `import_graph.transitive_callers` dispatcher raises `primitive_not_dispatched` until the ADR-0030 amendment lands the protocol method.
   - Module-import fence:
     ```python
     if set(_PRIMITIVE_DISPATCHERS.keys()) != set(_KNOWN_PRIMITIVES):
         raise AssertionError(
             f"Primitive dispatcher drift: registered={sorted(_PRIMITIVE_DISPATCHERS)} vs known={sorted(_KNOWN_PRIMITIVES)}"
         )
     ```
   - `class BundleBuilder:`
     - `__init__(self, cache_dir, *, event_emitter=None)` — store `cache_dir`, `event_emitter` (default no-op `lambda _: None`), call `self._concurrency = _read_concurrency()`.
     - `async def build(self, resolution, repo_ctx, vuln, vuln_index) -> Bundle`:
       - Construct `semaphore = asyncio.Semaphore(self._concurrency)` (per-call — AC-14).
       - Chain `queries = [*must_read, *should_read, *may_read]`.
       - Schedule `tasks = [self._dispatch_query(q, resolution.composed_adapters, semaphore) for q in queries]`.
       - `entries = await asyncio.gather(*tasks)`.
       - Return `Bundle(entries=tuple(entries), plugin_id=PluginId(resolution.plugin.manifest.name), vuln_index_digest=vuln_index.digest())`.
     - `async def _dispatch_query(self, query, composed_adapters, semaphore, _depth=0) -> BundleEntry`:
       - `if _depth > _MAX_FALLBACK_DEPTH: raise BundleBuilderException(BundleBuilderError(reason="fallback_chain_too_deep", details={"primitive": str(query.primitive), "depth": _depth}))`
       - `dispatcher = _PRIMITIVE_DISPATCHERS.get(query.primitive)`; if `None` raise `primitive_not_dispatched`.
       - `adapter = composed_adapters.get(query.primitive)`; if `None` raise `adapter_missing_for_primitive`.
       - **Acquire semaphore for the primary call only:**
         ```python
         async with semaphore:
             payload, confidence = await dispatcher(adapter, query.args)
         ```
       - If `isinstance(confidence, (Degraded, Unavailable))` AND `query.fallback is not None`:
         - **Emit event BEFORE recursing** (AC-19): `self._event_emitter(AdapterDegraded(primitive=query.primitive, adapter_name=type(adapter).__name__, reason=confidence.reason))`.
         - **Recurse OUTSIDE the semaphore context** (avoiding the deadlock at `CONCURRENCY=1`): `fallback_entry = await self._dispatch_query(query.fallback, composed_adapters, semaphore, _depth=_depth+1)`.
         - Return a `BundleEntry` carrying the fallback's payload + the fallback's confidence + `fallback_used=True` + `primitive=query.primitive` (the *original* primitive — the entry's identity is the query, not the adapter that answered).
       - Else: return `BundleEntry(primitive=query.primitive, args_canonical=_canonicalize_args(query.args), payload=payload, confidence=confidence, fallback_used=False)`.
2. **Tests** — per AC list:
   - `tests/unit/plugins/test_bundle_builder.py` — concurrency env validation, serial-fallback semantics, depth cap, event emission, ordering, canonicalization, per-call semaphore isolation.
   - `tests/property/plugins/test_bundle_determinism.py` — AC-21 (100-run determinism + timing-shuffle).
   - `tests/property/plugins/test_bundle_serial_fallback.py` — AC-22 (100-run serial fallback + empty TCCM).
   - `tests/unit/plugins/test_bundle_no_hedged_race.py` — AC-23 (AST scan).
   - `tests/unit/plugins/test_bundle_module_purity.py` — AC-24 (import allowlist).
   - `tests/unit/plugins/test_bundle_extension_by_addition.py` — AC-8 (Open/Closed proof via 6th-primitive monkeypatch).
   - `tests/unit/plugins/conftest.py` — `fake_resolution_*` fixtures + `FakeScipAdapter` / `FakeImportGraphAdapter` / `FakeDepGraphAdapter` / `FakeTestInventoryAdapter` per actual Protocol surface.

## TDD plan — red / green / refactor

### Red

Test file: `tests/unit/plugins/test_bundle_builder.py`. The spy adapters use the **actual Protocol surface** (per-primitive methods + `confidence()` method).

```python
import json
import os
import asyncio
import pytest
from unittest.mock import MagicMock
from codegenie.plugins.bundle import (
    BundleBuilder, Bundle, BundleEntry, BundleBuilderError,
    BundleBuilderException, AdapterDegraded,
)
from codegenie.plugins.tccm import ContextQuery
from codegenie.adapters import AdapterConfidence, Trusted, Degraded, Unavailable
from codegenie.types.identifiers import PrimitiveName


class FakeScipAdapter:
    """Per-Protocol spy: matches codegenie.adapters.protocols.ScipAdapter shape."""
    def __init__(self, confidence: AdapterConfidence = Trusted(), refs_payload=None):
        self._confidence = confidence
        self._refs = refs_payload or []
        self.calls = 0

    def refs(self, symbol: str):  # Protocol method
        self.calls += 1
        return list(self._refs)

    def confidence(self) -> AdapterConfidence:  # Protocol method
        return self._confidence


class FakeDepGraphAdapter:
    """Per-Protocol spy: matches DepGraphAdapter shape."""
    def __init__(self, confidence: AdapterConfidence = Trusted(), consumers_payload=None):
        self._confidence = confidence
        self._consumers = consumers_payload or []
        self.calls = 0

    def consumers(self, pkg: str):
        self.calls += 1
        return list(self._consumers)

    def producers(self, pkg: str):
        return []

    def confidence(self) -> AdapterConfidence:
        return self._confidence


class TestConcurrencyEnv:
    def test_env_override_invalid_raises_at_construction(self, monkeypatch, tmp_path):
        # Rule 12 — fail loud at construction, not on first build()
        monkeypatch.setenv("CODEGENIE_BUNDLE_CONCURRENCY", "not-a-number")
        with pytest.raises(BundleBuilderException) as exc:
            BundleBuilder(cache_dir=tmp_path)
        assert exc.value.model.reason == "invalid_concurrency_env"
        assert exc.value.model.details["value"] == "not-a-number"

    def test_env_override_nonpositive_raises(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CODEGENIE_BUNDLE_CONCURRENCY", "0")
        with pytest.raises(BundleBuilderException) as exc:
            BundleBuilder(cache_dir=tmp_path)
        assert exc.value.model.reason == "invalid_concurrency_env"

    def test_concurrency_read_at_construction_not_module_import(self, monkeypatch, tmp_path):
        # AC-15: env read inside __init__ — monkeypatch must take effect
        monkeypatch.setenv("CODEGENIE_BUNDLE_CONCURRENCY", "2")
        b = BundleBuilder(cache_dir=tmp_path)
        assert b._concurrency == 2

    def test_cpu_count_none_falls_back_to_one(self, monkeypatch, tmp_path):
        monkeypatch.delenv("CODEGENIE_BUNDLE_CONCURRENCY", raising=False)
        monkeypatch.setattr(os, "cpu_count", lambda: None)
        b = BundleBuilder(cache_dir=tmp_path)
        assert b._concurrency == 1  # min(4, None or 1) == min(4, 1) == 1


class TestSerialFallbackSemantics:
    """ADR-0008: serial fallback, NOT hedged-race."""

    @pytest.mark.asyncio
    async def test_no_fallback_when_primary_trusted(self, tmp_path, fake_resolution_trusted_primary):
        builder = BundleBuilder(cache_dir=tmp_path)
        events: list = []
        builder = BundleBuilder(cache_dir=tmp_path, event_emitter=events.append)
        bundle = await builder.build(fake_resolution_trusted_primary, ...)
        # No fallback adapter invoked when primary is Trusted
        primary = fake_resolution_trusted_primary.composed_adapters[PrimitiveName("scip.refs")]
        assert primary.calls == 1
        assert bundle.entries[0].fallback_used is False
        assert isinstance(bundle.entries[0].confidence, Trusted)
        assert events == []  # no events when no fallback fires

    @pytest.mark.asyncio
    async def test_fallback_invoked_once_when_primary_degraded(self, tmp_path, fake_resolution_degraded_primary):
        events: list = []
        builder = BundleBuilder(cache_dir=tmp_path, event_emitter=events.append)
        bundle = await builder.build(fake_resolution_degraded_primary, ...)
        primary = fake_resolution_degraded_primary.composed_adapters[PrimitiveName("scip.refs")]
        fallback = fake_resolution_degraded_primary.composed_adapters[PrimitiveName("dep_graph.consumers")]
        assert primary.calls == 1 and fallback.calls == 1
        assert bundle.entries[0].fallback_used is True
        assert len(events) == 1 and isinstance(events[0], AdapterDegraded)
        assert events[0].primitive == PrimitiveName("scip.refs")

    @pytest.mark.asyncio
    async def test_primary_runs_strictly_before_fallback(self, tmp_path):
        order: list[str] = []

        class OrderingScipAdapter:
            def __init__(self, name, confidence):
                self._name, self._confidence = name, confidence
            def refs(self, symbol):
                order.append(f"{self._name}:start")
                # synchronous (Protocol contract); the dispatcher wraps in to_thread
                order.append(f"{self._name}:done")
                return []
            def confidence(self):
                return self._confidence

        # Build a resolution where primary=OrderingScipAdapter("p", Degraded(reason="stale"))
        # and fallback=OrderingScipAdapter("f", Trusted())
        # ...
        await builder.build(...)
        # Strict serial order — NEVER interleaved (which would prove hedged-race)
        assert order == ["p:start", "p:done", "f:start", "f:done"]

    @pytest.mark.asyncio
    async def test_event_emitted_before_fallback_call(self, tmp_path):
        # AC-19 timing spy: event time < fallback adapter call time
        import time
        emit_times: list[float] = []
        fallback_call_times: list[float] = []

        class TimingFallbackAdapter:
            def refs(self, symbol):
                fallback_call_times.append(time.monotonic())
                return []
            def confidence(self): return Trusted()

        def emitter(e):
            emit_times.append(time.monotonic())

        # ... wire builder ...
        await builder.build(...)
        assert emit_times and fallback_call_times
        assert emit_times[0] < fallback_call_times[0]

    @pytest.mark.asyncio
    async def test_fallback_chain_depth_4_succeeds(self, tmp_path):
        # Depth 4 chain: primary → fb1 → fb2 → fb3 → fb4, all Degraded except last Trusted
        # Expected: BundleEntry with fallback_used=True, confidence=Trusted()
        ...

    @pytest.mark.asyncio
    async def test_fallback_chain_depth_5_raises(self, tmp_path):
        # 5-deep chain, all Degraded
        with pytest.raises(BundleBuilderException) as exc:
            await builder.build(...)
        assert exc.value.model.reason == "fallback_chain_too_deep"
        assert exc.value.model.details["depth"] == 5


class TestCanonicalization:
    @pytest.mark.asyncio
    async def test_args_canonical_collides_on_key_order(self, tmp_path):
        # AC-12: {"a": 1, "b": 2} and {"b": 2, "a": 1} → identical args_canonical
        # Build two queries with the same args content but different insertion order
        # Assert: bundle1.entries[0].args_canonical == bundle2.entries[0].args_canonical
        # Assert: == '{"a":1,"b":2}'
        ...


class TestOrderPreservation:
    @pytest.mark.asyncio
    async def test_entries_order_matches_must_should_may(self, tmp_path):
        # AC-13: must_read=[Q1,Q2], should_read=[Q3], may_read=[Q4]
        # → bundle.entries == (e1, e2, e3, e4) in that order
        ...


class TestPerCallSemaphoreIsolation:
    @pytest.mark.asyncio
    async def test_two_concurrent_builds_share_no_semaphore(self, monkeypatch, tmp_path):
        # AC-14: CONCURRENCY=1 + two concurrent build()s on same builder
        # Wall-clock ~50ms (parallel), not ~100ms (serialized)
        monkeypatch.setenv("CODEGENIE_BUNDLE_CONCURRENCY", "1")
        builder = BundleBuilder(cache_dir=tmp_path)
        # ... two SlowAdapter resolutions, asyncio.gather two build() coroutines
        # assert elapsed < 0.08
        ...


class TestEmptyTccm:
    @pytest.mark.asyncio
    async def test_empty_tccm_returns_empty_bundle(self, tmp_path):
        # AC-22: must_read=should_read=may_read=[] → Bundle(entries=(), ...)
        ...


class TestBundleBuilderErrorTypos:
    def test_mypy_strict_rejects_typo_reason(self):
        # AC-3: parametrized mypy meta-test
        # Use the existing tests/meta/test_mypy_strict.py harness pattern (S3-02 AC-C4)
        ...
```

Property test (`tests/property/plugins/test_bundle_determinism.py`):

```python
from hypothesis import given, settings, strategies as st

@settings(max_examples=100, deadline=None)
@given(seed=st.integers(min_value=0, max_value=10**9))
def test_bundle_byte_identical_under_timing_shuffle(seed, tmp_path_factory):
    """AC-21 + ADR-0008: random per-adapter delays (seed-derived) must not change Bundle bytes.

    A hedged-race impl loses the primary's payload to a faster fallback on some seeds;
    determinism property catches it across 100 runs."""
    bundles = [
        _run_build_sync(seed, tmp_path_factory.mktemp(str(i)))
        for i in range(2)
    ]
    assert bundles[0].model_dump_json() == bundles[1].model_dump_json()
```

Property test (`tests/property/plugins/test_bundle_serial_fallback.py`):

```python
@settings(max_examples=100, deadline=None)
@given(num_queries=st.integers(min_value=0, max_value=10))
def test_fallback_invoked_exactly_once_per_query_when_primary_degraded(num_queries, tmp_path_factory):
    """AC-22: primary always Degraded, fallback always Trusted.
    For N queries: primary.calls == N, fallback.calls == N, events == N, never interleaved."""
    ...
```

AST scan (`tests/unit/plugins/test_bundle_no_hedged_race.py`):

```python
import ast
import re
from pathlib import Path

def test_no_hedged_race_composition_in_bundle():
    """AC-23: structural defense against asyncio.{gather,wait,as_completed} on (primary, fallback)."""
    src = Path("src/codegenie/plugins/bundle.py").read_text()
    tree = ast.parse(src)
    forbidden = {"gather", "wait", "as_completed"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in forbidden:
                for arg in node.args:
                    arg_src = ast.unparse(arg)
                    assert "fallback" not in arg_src, (
                        f"hedged-race smell — {node.func.attr}({arg_src}); ADR-0008 forbids"
                    )

def test_no_module_level_semaphore_in_bundle():
    """AC-14 belt-and-suspenders: per-call semaphore only — never module-level."""
    src = Path("src/codegenie/plugins/bundle.py").read_text()
    module_level_sem = re.compile(r"^[A-Za-z_]\w*\s*=\s*asyncio\.Semaphore\(", re.MULTILINE)
    assert not module_level_sem.findall(src), "module-level asyncio.Semaphore forbidden — per-call only"
```

Module purity (`tests/unit/plugins/test_bundle_module_purity.py`):

```python
import ast
from pathlib import Path

ALLOWED = frozenset({
    "__future__", "asyncio", "json", "os", "typing", "collections.abc", "pydantic",
    "codegenie.adapters", "codegenie.plugins.tccm", "codegenie.plugins.resolver",
    "codegenie.types.identifiers", "codegenie.types.errors", "codegenie.result",
    "codegenie.hashing", "codegenie.errors",
})

def test_bundle_imports_are_subset_of_allowlist():
    src = Path("src/codegenie/plugins/bundle.py").read_text()
    tree = ast.parse(src)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                found.add(n.name.split(".")[0] if "." not in n.name else ".".join(n.name.split(".")[:2]))
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            found.add(mod.split(".")[0] if "." not in mod else ".".join(mod.split(".")[:2]))
    extra = found - ALLOWED
    assert not extra, f"unexpected imports in bundle.py: {extra}"
```

Open/Closed proof (`tests/unit/plugins/test_bundle_extension_by_addition.py`):

```python
@pytest.mark.asyncio
async def test_sixth_primitive_dispatches_with_zero_edits_to_bundle_py(monkeypatch, tmp_path):
    """AC-8: adding a new (primitive, dispatcher) pair via the registry decorator works
    without editing bundle.py.

    Monkeypatches _KNOWN_PRIMITIVES (S3-01) to include 'new_primitive.demo' and
    registers a dispatcher; BundleBuilder.build dispatches it correctly."""
    from codegenie.plugins import bundle, tccm
    new_primitive = PrimitiveName("new_primitive.demo")
    monkeypatch.setitem(tccm._KNOWN_PRIMITIVES_DICT_OR_EQUIV, new_primitive, ...)

    @bundle.register_primitive_dispatcher(new_primitive)
    async def _stub(adapter, args):
        return ({"data": "demo"}, Trusted())

    # ... build a resolution with a ContextQuery(primitive=new_primitive, ...)
    bundle_result = await builder.build(...)
    assert bundle_result.entries[0].primitive == new_primitive
    assert bundle_result.entries[0].payload == {"data": "demo"}
```

### Green

Smallest impl: §Implementation outline; ~180 lines total (registry seam + 5 dispatchers + builder + error model + canonicalization).

### Refactor

- Extract `_resolve_concurrency_from_env(raw: str | None) -> int` pure helper for unit-level testing of the validation lattice.
- Tier-2 deferred opportunities (record only in module docstring):
  - **`AdapterPayload` sum type** (DP4) — replace `payload: dict[str, str | int | bool | list[str]]` with `ScipRefsResult | ImportGraphResult | DepGraphConsumersResult | TestInventoryResult` discriminated union when S6-04 / S7-02's first real consumer needs typed dispatch.
  - **`dispatch_path` sum** (DP3) — replace `fallback_used: bool` with `PrimaryUsed | FallbackUsed(depth: int, chain: tuple[PrimitiveName, ...])` if Phase 6's `TrustScorer` weighs fallback depth into confidence.
- Add structlog `bundle.query_dispatched` info per query at refactor (operator visibility); requires structlog in AC-24 allowlist OR lazy import inside `_dispatch_query`. Defer to S6-01 + S6-04 wiring.
- `BundleBuilderConfig` dataclass (`concurrency_bound`, `max_fallback_depth`) — Phase 14 per-workflow tuning seam. Out-of-scope here; promote when first cross-workflow override is needed.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/plugins/bundle.py` | NEW — `BundleBuilder`, `Bundle`, `BundleEntry`, `BundleBuilderError`, `BundleBuilderException`, `AdapterDegraded`, `register_primitive_dispatcher`, five built-in dispatchers |
| `tests/unit/plugins/test_bundle_builder.py` | Unit tests for concurrency env, serial fallback, ordering, canonicalization, depth cap, events |
| `tests/unit/plugins/test_bundle_no_hedged_race.py` | AC-23: AST scan against `asyncio.{gather, wait, as_completed}` with `fallback`-mentioning args + no module-level semaphore |
| `tests/unit/plugins/test_bundle_module_purity.py` | AC-24: import-allowlist fence |
| `tests/unit/plugins/test_bundle_extension_by_addition.py` | AC-8: Open/Closed proof via registered 6th primitive |
| `tests/property/plugins/test_bundle_determinism.py` | AC-21: 100-run + timing-shuffle determinism |
| `tests/property/plugins/test_bundle_serial_fallback.py` | AC-22: 100-run serial fallback + empty TCCM |
| `tests/unit/plugins/conftest.py` | `fake_resolution_*` fixtures + `FakeScip/ImportGraph/DepGraph/TestInventory` adapters per actual Phase-02 Protocol surface |
| `tests/meta/test_mypy_strict_bundle.py` | AC-3: mypy-strict meta-test for `BundleBuilderError(reason="typo")` (mirror S3-02 AC-C4 harness) |

## Out of scope

- **Cache key composition + cache lookup** — S3-05 ships the BLAKE3 key (including `vuln_index.digest`) and the on-disk cache; this story builds the in-memory `Bundle` only.
- **`BundleCacheGc`** — S3-05 (Gap 4 fix).
- **Real Phase 2 search-adapter wiring** — Phase 2's `dep_graph.consumers`, `import_graph.reverse_lookup`, `scip.refs`, `test_inventory.tests_exercising` adapters are plumbed by S7-02; this story uses spy adapters matching the actual Protocol surface in tests.
- **`TrustScorer.confidence` folding** — S6-02 reads `AdapterDegraded` events from the EventLog; this story just emits them via the seam.
- **Deferred `may_read` execution** — ADR-0029 allows worker nodes to lazily request `may_read`; Phase 3 executes all three bands eagerly. Document the deviation; Phase 6 may revisit.
- **Cancellation on partial failure** — if one adapter raises, `asyncio.gather(*tasks)` propagates and `build` fails (AC-27 pins this behavior). Richer `return_exceptions=True` + per-entry error variants are a S6-04 concern.
- **`import_graph.transitive_callers` dispatcher** — ADR-0030 names the primitive but the protocol method isn't shipped yet; dispatcher registered as a stub that raises `primitive_not_dispatched` so the registry contract (one dispatcher per known primitive) is honored.
- **Tagged-union `dispatch_path` (DP3) and typed `AdapterPayload` (DP4)** — recorded in module docstring as Phase-6 / Phase-7 revisit candidates; out-of-scope here per Rule 2.

## Notes for the implementer

- **The hedged-race rejection is a hard line.** Production design §2.4 is **veto-strength**; the determinism property test (AC-21 + S8-03) will fail by construction if you ever `asyncio.gather(primary, fallback)`. The AST source-scan test (AC-23) and the timing-shuffle property test (AC-21) are belt-and-suspenders; do not weaken any of them.

- **Semaphore acquire pattern (deadlock-free).** Acquire the semaphore around the **primary dispatch only**. Release it before recursing into the fallback. Reasoning: with `CONCURRENCY=1` and N queries each carrying a fallback, if every recursive call acquired its own permit, the parent's permit-hold + child's permit-wait deadlocks immediately. The correct shape:
  ```python
  async with semaphore:
      payload, conf = await dispatcher(adapter, query.args)
  # ← permit released HERE, before the fallback dispatch
  if isinstance(conf, (Degraded, Unavailable)) and query.fallback:
      self._event_emitter(AdapterDegraded(...))
      return await self._dispatch_query(query.fallback, ..., _depth=_depth+1)
  ```
  The fallback re-acquires the permit at its own primary-dispatch boundary. Permit holds are scoped to single adapter calls; the chain walks serially across permits.

- **`AdapterConfidence` is a discriminated-union of Pydantic models, NOT an enum.** `Trusted | Degraded | Unavailable`. There is **no `.High` attribute**. Detection: `isinstance(c, (Degraded, Unavailable))` OR `match c: case Trusted(): ... case Degraded(reason=r): ...`. Construction: `Trusted()`, `Degraded(reason="scip_unavailable")`, `Unavailable(reason="tool_missing")`.

- **Per-primitive dispatch lives in the registry, not in `bundle.py` switch logic.** The five dispatchers shipped in this module are the canonical first set; a sixth primitive added by Phase 4+ (per a future ADR-0030 amendment) registers via `@register_primitive_dispatcher(PrimitiveName("new.primitive"))` in its own module. `bundle.py` itself stays closed for modification (CLAUDE.md "Extension by addition").

- **`_MAX_FALLBACK_DEPTH = 4` matches the `extends`-chain cap in S2-04** — same intuition: human-authored YAML, deeper than 4 is almost always a mistake. Keep symmetric.

- **`asyncio.Semaphore(n)` is per-`build()` call, not module-level.** A module-level semaphore would serialize across concurrent workflows (Phase 6.5+ runs multiple); per-call keeps the bound per-workflow. AC-14 + AC-23's belt-and-suspenders test both enforce this.

- **`event_emitter=None` default** keeps this story testable without S6-01's `EventLog`. The orchestrator (S6-04) wires `event_emitter=lambda e: event_log.emit_internal(e)` at construction (the returned `EventId` is discarded — `BundleBuilder` doesn't need it). Do NOT make `EventLog` a required dep — that would block this story on S6-01.

- **`canonicalize(args)` shape** is `json.dumps(args, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`. Cache-key correctness depends on key-sort. S3-05 will BLAKE3-hash the canonicalized string.

- **`Bundle.plugin_id`** wraps via explicit `PluginId(resolution.plugin.manifest.name)` — production ADR-0033 newtype-at-boundary. Note that PEP 484 `NewType` is a function at runtime; `type(bundle.plugin_id) is str` will be true. Pin via value-equality, not type-equality.

- **Pure-function fold over typed inputs.** This is the spirit of ADR-0008 §Pattern fit ("Functional core / imperative shell"). `_canonicalize_args`, `_resolve_concurrency_from_env`, and the dispatcher decision logic are all pure helpers; the impure surface is the adapter method calls and the event emission. Keep the fold pure (no logging in the loop body; emit at boundaries).

- **`os.cpu_count() or 1`** — on weird hosts `cpu_count()` returns `None`; the `or 1` keeps the bound positive. AC-26 covers this.

- **Tier-2 design opportunities (deferred to ADR-amendment moment, recorded here for awareness):**
  - **`dispatch_path: PrimaryUsed | FallbackUsed(depth: int, chain: tuple[PrimitiveName, ...])`** — tagged-union over `fallback_used: bool` (DP3). Promote when Phase 6's `TrustScorer` reads fallback depth as a confidence weight.
  - **Typed `AdapterPayload` sum** — `ScipRefsResult | ImportGraphResult | DepGraphConsumersResult | TestInventoryResult` discriminated by `kind` (DP4). Promote when first real consumer (`TrustScorer.score` or recipe-application) needs typed match-dispatch on the payload.
  Both are forward-compatible because `BundleEntry` is `extra="forbid"` and frozen; later widening is a deliberate ADR amendment.

- **Tier-3 opportunities (recorded only, no action):** `VulnIndexCapability` mint (DP5); `FallbackChain` iterator (DP6); `BundleBuilderConfig` dataclass (DP7); `AdapterName` newtype (DP8).

- **Beware Pydantic v2 `tuple[BundleEntry, ...]`** — sometimes needs `Annotated[tuple[BundleEntry, ...], ...]` for proper serialization round-trip; if `model_validate(model_dump())` round-trips fail, switch to `Sequence[BundleEntry]` + convert to tuple in `__init__`.

- **`AdapterDegraded.kind: Literal["adapter_degraded"]`** discriminator pre-positions the event for S6-01's `WorkflowInternalEvent = Annotated[PluginsLoaded | PluginResolved | … | AdapterDegraded | …, Field(discriminator="kind")]` union. Symbol matches arch §C9 exactly.
