# Validation report — S3-04 `BundleBuilder` with bounded concurrency + deterministic serial fallback (ADR-0008)

**Story:** [`docs/phases/03-vuln-deterministic-recipe/stories/S3-04-bundle-builder-serial-fallback.md`](../S3-04-bundle-builder-serial-fallback.md)
**Date:** 2026-05-18
**Verdict:** **HARDENED**
**Validator:** `/phase-story-validator` skill (Opus 4.7)

## Context brief

S3-04 ships `codegenie.plugins.bundle.BundleBuilder` — the load-bearing executor of every plugin's TCCM `must_read` / `should_read` / `may_read` queries. ADR-0008 §Decision is veto-strength: dispatch is **bounded by an `asyncio.Semaphore(min(4, os.cpu_count() or 1))`** (overridable by `CODEGENIE_BUNDLE_CONCURRENCY`); each `ContextQuery`'s declared `fallback` fires **only** when the primary returns `AdapterConfidence ∈ {Degraded, Unavailable}` — **never raced** (production design §2.4 vetoes hedged-race). An `AdapterDegraded` event is emitted on every fallback firing so `TrustScorer` (S6-02) can fold confidence later. The cache key + on-disk cache + GC land in S3-05.

Reading the original story against the **actual code in `src/codegenie/adapters/`** surfaced a fundamental contract mismatch that drove the bulk of the validation: the story's TDD plan assumes a uniform `adapters[primitive].query(args) → Result(confidence=..., payload=...)` surface, but Phase 02 ships a **per-Protocol** adapter surface where:

1. `AdapterConfidence` is the discriminated union `Trusted | Degraded | Unavailable` (Pydantic models with `kind` discriminator) — there is **no `High` variant**. The story's `FakeAdapter(confidence=AdapterConfidence.High)` and `primary.confidence not in {Degraded, Unavailable}` reads would `AttributeError` at import.
2. Adapters do **not** expose a uniform `.query(args) → Result`. They expose **per-primitive methods**: `ScipAdapter.refs(symbol)`, `ImportGraphAdapter.reverse_lookup(module)`, `DepGraphAdapter.consumers(pkg)` / `.producers(pkg)`, `TestInventoryAdapter.tests_exercising(symbol)`. Each returns the typed payload directly; **`adapter.confidence()` is a method on the adapter object** (not on the result).
3. The dispatch from `PrimitiveName` to `(adapter, method)` is **the** open seam this story has to land — and the codebase has three established registry-pattern precedents (`@register_index_freshness_check`, `@register_dep_graph_strategy`, `@register_probe`) for exactly this shape. Without a registry seam, Phase 4+ adding a sixth primitive (per ADR-0030 amendment path) would force edits to `bundle.py` — violating CLAUDE.md "Extension by addition" / Open/Closed.

A second structural finding — independent of the adapter shape — surfaced: the original Implementation outline recurses `_run_one(query.fallback, ...)` **while holding the semaphore**. With `CODEGENIE_BUNDLE_CONCURRENCY=1` (CI tuning per ADR-0008's escape-hatch motivation) and any query with a declared fallback, every fallback call recursively re-acquires the same semaphore that its parent still holds → **classical recursion-deadlock**. The fallback dispatch must release the permit before recursing OR acquire only at the top of the chain.

A third finding aligned this story with established Phase-3 precedent: `BundleBuilderError(CodegenieError)` markers-only with attribute access on `.reason` is the *same* contradiction S3-01 (`TCCMParseError`), S3-02 (`VulnIndexLookupError`/`VulnIndexConfigError`), and S3-03 (`VulnParseError`) all resolved by redesign-as-frozen-Pydantic-BaseModel + `Literal[...]` reason + a thin `Exception` wrapper (`VulnIndexException(model: VulnIndexLookupError | VulnIndexConfigError)`). The Phase-3 family is now 4-strong on this pattern; S3-04 had to land it too.

## Stage 2 — four critics (synthesis)

Findings consolidated from in-context analysis grounded in:

- `src/codegenie/adapters/confidence.py` + `src/codegenie/adapters/protocols.py` — the actual adapter surface Phase 02 shipped (BLOCK source).
- S3-01, S3-02, S3-03 `_validation/` reports — Pydantic-error precedent + registry-pattern precedent + AC-numbering style.
- CLAUDE.md "Open/Closed seams" + "Extension by addition" + "Newtype identifiers" + "Functional core / imperative shell" + Rule 9 "Tests verify intent, not just behavior".
- Phase 3 arch §C7, ADR-0008, production design §2.4 (veto-strength determinism).
- `src/codegenie/depgraph/registry.py` + `src/codegenie/indices/freshness.py` — the existing registry-pattern home; rule-of-three already crossed.

Tagged `block` / `harden` / `nit`.

### Coverage critic — 5 block, 10 harden, 4 nit

| # | Tag | Issue |
|---|---|---|
| F1 | block | `AdapterConfidence.High` referenced in TDD plan (`FakeAdapter(confidence=AdapterConfidence.High)`) — `AdapterConfidence` is `Trusted \| Degraded \| Unavailable`; `.High` does not exist (`AttributeError` at import). |
| F2 | block | `primary.confidence not in {Degraded, Unavailable}` — `primary` is the adapter method's return (e.g., `list[str]` from `consumers(pkg)`), not a `MagicMock(confidence=..., payload=...)`. Confidence is queried *separately* via `adapter.confidence()`. |
| F3 | block | `adapters[primitive].query(args)` — Phase 02 Protocol surface has per-primitive typed methods (`refs`, `reverse_lookup`, `consumers`, `producers`, `tests_exercising`), NOT a uniform `.query(args)`. Story must define an explicit dispatch table or registry. |
| F4 | block | `BundleBuilderError(CodegenieError)` markers-only with `.reason` attribute access — same contradiction S3-01/S3-02/S3-03 resolved. Must be frozen Pydantic `BaseModel` + thin `BundleBuilderException` wrapper. |
| F5 | block | "TDD red test exists, committed, green" AC is tautological (echo S3-02 F3 / S3-03 F4). |
| F6 | harden | No AC pins `must_read → should_read → may_read` order preservation in `Bundle.entries` — load-bearing for the determinism property test. |
| F7 | harden | No AC pins per-call (not module-level) semaphore — Notes for the implementer call this out but no AC enforces; executor could ship a module-level `_SEMAPHORE` and pass tests. |
| F8 | harden | No AC pins when `CODEGENIE_BUNDLE_CONCURRENCY` is read — story implies module-import time, which makes `monkeypatch.setenv(...)` ineffective after first import (cached `_DEFAULT_CONCURRENCY_BOUND`). Must read at builder construction. |
| F9 | harden | No AC pins `args_canonical` canonicalization (`json.dumps(args, sort_keys=True, separators=(",", ":"))`) — load-bearing for S3-05's cache key. Notes mention; promote to AC + collision test. |
| F10 | harden | `BundleBuilderError.reason` set is open `str` — must be closed `Literal["invalid_concurrency_env", "fallback_chain_too_deep", "primitive_not_dispatched", "adapter_missing_for_primitive"]` per ADR-0010 sum-type discipline. mypy --strict cannot catch typos otherwise. |
| F11 | harden | No mypy-strict meta-test for `BundleBuilderError(reason="typo")` rejection (echo S3-01/S3-02 AC-C4 / S3-03 H1). |
| F12 | harden | Exception-propagation behavior on partial failure unspecified — "out of scope" Notes line does not constitute a contract. Pin current behavior: if any primary raises, `asyncio.gather` propagates and the whole `build` fails; richer error variants are a S6-04 concern. |
| F13 | harden | Empty TCCM (zero queries across `must_read`/`should_read`/`may_read`) — observable corner case; no AC. Should return `Bundle(entries=(), ...)` with `vuln_index_digest` populated. |
| F14 | harden | No AC pins event-emission semantics: emitted **exactly once per fallback firing** (not once per query, not zero times when primary returns `Trusted`). Spy-emitter assertion. |
| F15 | harden | No AC pins fallback-chain depth: at depth `4` the chain is allowed; at depth `5` it raises. Boundary at `_MAX_FALLBACK_DEPTH` exactly. |
| F16 | nit | `os.cpu_count() or 1` corner case (`None` return on weird hosts) — Notes mention; promote to a single explicit AC. |
| F17 | nit | `Bundle.plugin_id` source ambiguity — `resolution.plugin.manifest.name` per Implementation outline, but `manifest.name` is the bare string; should explicitly cast through `PluginId(...)` for newtype discipline. |
| F18 | nit | `tests/static/` directory does not exist in the repo; AST source-scan test lives under `tests/unit/plugins/test_bundle_*_purity.py` per codebase precedent (`tests/unit/plugins/test_scope_purity.py`). |
| F19 | nit | AC numbering style mismatch — sibling HARDENED stories use `AC-N:` format; this story uses bare checkboxes. |

### Test-Quality critic — 4 block, 8 harden, 2 nit

| # | Tag | Issue |
|---|---|---|
| TQ-B1 | block | `MagicMock(confidence=self.confidence, payload=self.payload, adapter_name="fake")` — wrong shape. Adapter methods return typed payloads (`list[str]`, `list[Occurrence]`, `list[TestId]`); the spy must expose `consumers(pkg)`/`refs(sym)`/etc. + `confidence() → AdapterConfidence` separately. (Mirrors F2/F3.) |
| TQ-B2 | block | `FakeAdapter.confidence = AdapterConfidence.High` — `High` does not exist (echo F1). Spy must use `Trusted()` / `Degraded(reason="...")` / `Unavailable(reason="...")` Pydantic instances. |
| TQ-B3 | block | TDD stub `...` bodies (e.g., `test_default_concurrency_min_4_or_cpu_count`, `test_fallback_chain_depth_capped_at_4`, `TestEventEmission`) violate Rule 9 — no executable arrange/act/assert. Same pattern S3-02 TQ-B2 / S3-03 TQ-B3 caught. |
| TQ-B4 | block | `fake_resolution_with_5_queries`, `fake_resolution_with_fallback`, `fake_resolution_with_degraded_primary` fixtures referenced but never defined — same dangling-fixture pattern S3-02 TQ-B6 caught. Must specify the fixture shape (resolution type, queries used, spy adapters wired) or land them in `tests/unit/plugins/conftest.py` per Files-to-Touch. |
| TQ-H1 | harden | No mutation-test for hedged-race: a wrong impl `asyncio.gather(primary(), fallback())` returning first-completed would pass `fallback.calls == 1, primary.calls == 1`. Hardening: add a **timing-shuffle** property test where the fallback is *faster* than the primary on some seeds; a hedged-race impl returns the fallback's payload while the serial impl always returns the primary's payload. Byte-identical `model_dump_json()` across timing-shuffled seeds is the catch. |
| TQ-H2 | harden | No property test for **deterministic event-emission count**: 100 runs with primary always `Degraded` → exactly `len(must_read + should_read + may_read)` events emitted, in deterministic order. |
| TQ-H3 | harden | No semaphore-deadlock regression test: `CODEGENIE_BUNDLE_CONCURRENCY=1` with a query carrying a fallback. A naive "acquire on every call" implementation deadlocks; story must specify the dispatch shape that avoids this AND test it. |
| TQ-H4 | harden | AST scan only forbids `asyncio.gather` with a `fallback` arg — easily evaded by `asyncio.wait(...)` / `asyncio.as_completed(...)`. Generalize to forbid `asyncio.{gather,wait,as_completed}` where any call argument's source mentions `fallback`. |
| TQ-H5 | harden | No cold-start / module-purity test for `src/codegenie/plugins/bundle.py` — should not import `requests`, `httpx`, `urllib`, `anthropic`, `langchain`, etc. (echo S3-03 TQ-H5/H6 fence precedent). The fence test asserts the import set is a subset of `{__future__, asyncio, os, typing, collections.abc, pydantic, codegenie.adapters, codegenie.plugins.tccm, codegenie.plugins.resolver, codegenie.types.identifiers, codegenie.types.errors, codegenie.result, codegenie.hashing, codegenie.errors}`. |
| TQ-H6 | harden | No test pins **per-call semaphore isolation**: spawn two concurrent `BundleBuilder.build(...)` coroutines on the same `BundleBuilder` instance with `CODEGENIE_BUNDLE_CONCURRENCY=1`; observe that both progress (each has its own permit) rather than one blocking the other. |
| TQ-H7 | harden | No test pins **`AdapterDegraded` event ordering relative to fallback dispatch**: the event must be observable **before** the fallback's primitive method is called. Use an event-emitter spy that records `time.monotonic()` and an adapter spy that records `time.monotonic()` on entry; assert emit-time < fallback-call-time. |
| TQ-H8 | harden | Property-test seed-shuffle implementation is vague (`# only randomized scheduling-shuffle through the asyncio loop`). Specify the concrete shuffle: a `SlowAdapter` that `await asyncio.sleep(random_delay)` parametrized by a `seed`-derived RNG; this is what forces a hedged-race impl to diverge. |
| TQ-N1 | nit | Decompose `TestSerialFallbackSemantics` into a parametrized matrix `(primary_confidence, has_fallback) → expected_fallback_calls` rather than four bespoke tests — 6 cells, one parametrize block. |
| TQ-N2 | nit | `test_fallback_chain_depth_capped_at_4` should also test depth 4 succeeds (boundary) AND depth 5 fails. |

### Consistency critic — 4 block, 5 harden, 2 nit

| # | Tag | Issue |
|---|---|---|
| C1 | **BLOCK** | `AdapterConfidence.High` directly contradicts `src/codegenie/adapters/confidence.py` (`Trusted \| Degraded \| Unavailable`). |
| C2 | **BLOCK** | Uniform `.query(args) → result(confidence, payload)` adapter shape contradicts `src/codegenie/adapters/protocols.py` per-primitive method surface. |
| C3 | **BLOCK** | `BundleBuilderError(CodegenieError)` markers-only with `.reason` contradicts S3-01/S3-02/S3-03 precedent (frozen Pydantic + thin Exception wrapper). |
| C4 | **BLOCK** | Recursive `_run_one` acquires semaphore on every recursive call → deadlock at `CODEGENIE_BUNDLE_CONCURRENCY=1` when any fallback fires. Implementation outline must specify acquire-once-per-chain semantics. |
| C5 | harden | Phase 3 ADR-0008 §Decision pins `os.cpu_count()` → must be `os.cpu_count() or 1` (story Notes mention; AC missing). |
| C6 | harden | `tests/static/` location for the AST scan does not exist; codebase precedent is `tests/unit/.../test_*_purity.py` (Rule 11 — match existing convention). |
| C7 | harden | `Bundle.plugin_id` field: `resolution.plugin.manifest.name` is a bare `str`; production ADR-0033 + Phase-3 ADR-0010 require newtype `PluginId(...)` at module boundaries. |
| C8 | harden | `AdapterDegradedEvent` model name vs arch §C9 `AdapterDegraded` `WorkflowInternalEvent` taxonomy: S6-01 will register `AdapterDegraded` (not `…Event` suffix). Pick a name that survives unchanged into S6-01 — drop the `Event` suffix OR document the suffix-strip in Notes. |
| C9 | harden | The "`composed_adapters: dict[PrimitiveName, Adapter]`" assumption inherited from S2-04 needs explicit reconciliation: S2-04 ships a *stub* `Adapter` placeholder. This story must specify what the dispatch table key resolves to (one of the four Protocol surfaces from `codegenie.adapters.protocols`). |
| C10 | nit | Cite production design §2.4 directly in module docstring (not just ADR-0008 §Decision) — §2.4 is the veto-strength commitment source. |
| C11 | nit | `event_emitter: Callable[[AdapterDegradedEvent], None] \| None` — when wired to S6-01's `event_log.emit_internal`, the signature is `Callable[[WorkflowInternalEvent], EventId]`. Surface this gap in Notes; the impl may use a thin adapter `lambda e: event_log.emit_internal(e)` ignoring the returned `EventId`. |

### Design-Patterns critic — 1 tier-1, 3 tier-2, 4 tier-3

| # | Tier | Issue |
|---|---|---|
| DP1 | **tier-1** | **Registry pattern (Open/Closed) for per-primitive dispatch.** Three established precedents — `@register_index_freshness_check`, `@register_dep_graph_strategy`, `@register_probe` — exactly cover the shape "PrimitiveName Literal → typed function over typed adapter". Hardcoding `match primitive: case "scip.refs": adapter.refs(args["symbol"]) ... ` violates CLAUDE.md "Open/Closed seams" + rule-of-three. **Land `@register_primitive_dispatcher(PrimitiveName)` as the canonical seam** so Phase 4+ adds a sixth primitive in one new file (`dispatchers/<x>.py`) with zero edits to `bundle.py`. The dispatcher signature: `Callable[[Adapter, dict[str, str \| int \| bool \| list[str]]], Awaitable[tuple[AdapterPayload, AdapterConfidence]]]`. Mirrors `DepGraphStrategy` Callable + `_REGISTRY: dict[PackageManager, …]`. |
| DP2 | tier-2 | **Functional core / imperative shell split.** Decompose `_run_one` into a pure `_decide_dispatch(query, primary_confidence) -> DispatchDecision` (which decides "use primary result" vs "recurse to fallback") and an impure `_dispatch_once(query, adapter, semaphore)` (which calls into the typed adapter method and reads `adapter.confidence()`). Mirrors S2-04's pure-helper decomposition (`_lift_candidates`, `_filter_matches`, `_sort_by_keys`, `_compose_extends_chain`) and ADR-0008 §Pattern fit. The pure decision function is the unit-testable core; AST-walking tests can assert no I/O in the helper. |
| DP3 | tier-2 | **Tagged union for `BundleEntry.dispatch_path` (sum type) over anaemic `fallback_used: bool`.** `fallback_used: bool` collapses two distinct truths (was a fallback invoked? how deep?). Phase 6's `TrustScorer` consumes degradation depth as a confidence signal; a bool loses that. Pattern: `dispatch_path: PrimaryUsed \| FallbackUsed(depth: int, chain: tuple[PrimitiveName, ...])`. Mirrors S1-03's tagged-union outcomes precedent. Tier-2 (not tier-1) because Phase 6 may not need the depth in its first cut; the bool is forward-compatible if we keep `BundleEntry`'s `extra="forbid"` strict so adding the typed field later is a deliberate ADR amendment. **Recorded as a tier-2 design opportunity in Notes; not promoted to AC.** |
| DP4 | tier-2 | **Adapter-payload sum type (`AdapterPayload`).** Current `payload: dict[str, str \| int \| bool \| list[str]]` is primitive-friendly for JSON serialization but anaemic on read (consumers don't know whether to read `payload["refs"]` or `payload["modules"]` etc.). A typed `AdapterPayload = ScipRefsResult \| ImportGraphResult \| DepGraphConsumersResult \| TestInventoryResult` with Pydantic discriminator unlocks `match payload: case ScipRefsResult(refs): …` consumer-side. Defer to S6-04 / S7-02 when the first real consumer arrives. **Recorded as tier-2 in Notes; the boundary stays primitive-friendly for S3-05 cache-key hashing.** |
| DP5 | tier-3 | **Capability pattern** — `BundleBuilder.build(...)` takes `vuln_index: VulnIndex` directly. Pattern alternative: take a `VulnIndexCapability` minted at orchestrator construction (mirrors `NpmInstallCapability` per arch §C10). Tier-3 because the audit-trail benefit doesn't kick in until Phase 5's gate machinery; record in Notes as a Phase-5 revisit. |
| DP6 | tier-3 | **Chain of responsibility** for fallback resolution. Express the primary → fallback1 → fallback2 → … chain as an explicit `FallbackChain` iterator that yields `ContextQuery` instances in order; the dispatcher takes `next(chain)` and stops when one returns `Trusted`. Tier-3 because the current recursive shape is fine at depth 4; chain-iterator is over-engineering today. |
| DP7 | tier-3 | **Configuration object** for `(concurrency_bound, max_fallback_depth)` instead of module globals — already mentioned in story's Refactor section; promote to tier-3 design opportunity (no AC) so Phase 14's per-workflow tuning has a clean place to land. |
| DP8 | tier-3 | **Newtype `AdapterName`** for `AdapterDegradedEvent.adapter_name: str` — single consumer today (the event); skip until S6-02 has a second consumer. |

## Stage 3 — Researcher (NOT FIRED)

No critic finding tagged `NEEDS RESEARCH`. The Pydantic-error precedent, the registry-pattern precedent, and the functional-core/imperative-shell precedent are all in-repo (S3-01/02/03 reports + `src/codegenie/depgraph/registry.py`); the hedged-race veto is in ADR-0008; the deadlock failure mode is mechanical (recursion + bounded semaphore). Synthesizer can proceed without external lookup.

## Stage 4 — Synthesizer + Editor

### Conflict resolution

- **F1/C1 (`AdapterConfidence.High` doesn't exist) > tier-1 design pattern.** Consistency wins — the story is rewritten to use `Trusted | Degraded | Unavailable` everywhere; AC adds an explicit "AdapterConfidence imported from `codegenie.adapters`" check.
- **F3/C2 (uniform `.query(args)` doesn't exist) → DP1 (registry pattern).** Coverage + Consistency BLOCK forces the issue, AND Design-Patterns finds the canonical registry seam. Both fire in the same direction. **Promoted to AC.**
- **F4/C3 (markers-only error) > everything else.** Consistency wins; the Pydantic-error precedent is now 4-strong (S3-01, S3-02, S3-03, this story). AC adds `BundleBuilderError` frozen Pydantic + `BundleBuilderException` thin wrapper.
- **C4 (semaphore deadlock) > performance.** Implementation outline rewritten: acquire semaphore at the dispatch-helper boundary (not inside `_run_one`); recursion releases the parent's permit before entering the fallback call.
- **DP3/DP4 (tagged-union payload + dispatch_path) vs Rule 2 (simplicity).** Rule 2 wins — `fallback_used: bool` + `payload: dict` are forward-compatible (frozen + `extra="forbid"` means later widening is a deliberate ADR-gated change). Tier-2 design opportunities **surfaced in Notes**, not promoted to ACs.
- **DP5/DP6/DP7/DP8 (tier-3 patterns) — all deferred to Notes**, no ACs.

### Edits applied

1. **Validation notes block** added after the story header documenting every change with rationale linking to this report.
2. **Status flip** to `HARDENED`.
3. **AC renumbering** (AC-1, AC-2, …) to match S3-01/02/03 HARDENED style.
4. **Major rewrite of TDD plan** — spy adapters now match the actual Phase-02 Protocol surface; `AdapterConfidence` instances replace the non-existent `.High` enum-attribute access.
5. **New ACs added**:
   - AC-2: `BundleBuilderError` frozen Pydantic + `BundleBuilderException` wrapper + closed `reason: Literal[...]`.
   - AC-3: mypy-strict meta-test for typo'd `reason`.
   - AC-7: per-primitive dispatcher registry `@register_primitive_dispatcher(PrimitiveName)` — Open/Closed seam.
   - AC-8: registry uses S1-01 `PrimitiveName` newtype as key + closed set asserted against `_KNOWN_PRIMITIVES`.
   - AC-12: `args_canonical` canonicalization pinned + collision test.
   - AC-13: `must_read → should_read → may_read` order preserved in `Bundle.entries`.
   - AC-14: per-call semaphore (not module-level) — observable via two concurrent `build()` coroutines.
   - AC-15: concurrency read at builder construction (so `monkeypatch.setenv` works).
   - AC-19: `AdapterDegraded` event fired **exactly once per fallback firing** AND **before** the fallback's adapter method runs (operator-visibility ordering).
   - AC-20: fallback chain depth = 4 succeeds, 5 raises (boundary test).
   - AC-22: empty TCCM → `Bundle(entries=(), …)` with `vuln_index_digest` populated.
   - AC-23: AST scan generalized to `asyncio.{gather, wait, as_completed}` with any arg referencing `fallback`.
   - AC-24: module-import purity (allowlist), per S3-03 fence precedent.
   - AC-25: `Bundle.plugin_id` typed as `PluginId(...)` (newtype discipline).
   - AC-26: `os.cpu_count() or 1` corner case explicit.
   - AC-27: exception-propagation behavior pinned (current: propagate; richer variants → S6-04).
6. **Removed tautological** "TDD red test exists, committed, green" AC (echo S3-02 F3 / S3-03 F4).
7. **AST scan relocated** from `tests/static/` to `tests/unit/plugins/test_bundle_no_hedged_race.py` (Rule 11 — match existing precedent at `tests/unit/plugins/test_scope_purity.py`).
8. **Notes for the implementer** updated to record DP3 (tagged-union dispatch_path) and DP4 (typed `AdapterPayload` sum) as Phase-6 / Phase-7 revisit candidates, and DP5/DP6/DP7/DP8 as out-of-scope tier-3 opportunities.
9. **`AdapterDegradedEvent` → `AdapterDegraded`** model rename to align with S6-01's `WorkflowInternalEvent` taxonomy (arch §C9 names the event `AdapterDegraded`, no `Event` suffix).
10. **`Bundle.plugin_id`** explicit cast via `PluginId(resolution.plugin.manifest.name)`.
11. **Property test specifics tightened**: timing-shuffle implementation made concrete via a `SlowAdapter` parameterized by a seed-derived RNG; the byte-identical `model_dump_json()` invariant is the hedged-race catch.

### Final verdict

**HARDENED.** Four BLOCKs resolved (adapter-shape mismatch, error pattern, semaphore deadlock, AC tautology). The story now matches the actual Phase-02 adapter surface, follows the established Pydantic-error precedent (4th time this Phase), and lands the per-primitive dispatcher registry as the Open/Closed seam Phase 4+ needs. The hedged-race veto (ADR-0008 / production §2.4) is structurally defended by:

1. A generalized AST source-scan that forbids `asyncio.{gather, wait, as_completed}` on any argument mentioning `fallback`.
2. A timing-shuffle property test (100 Hypothesis runs) that catches a hedged-race impl returning the wrong payload when the fallback is faster than the primary on a given seed.
3. The byte-identical `model_dump_json()` determinism property test.

Together these three structural defenses are the belt-and-suspenders the ADR demands.
