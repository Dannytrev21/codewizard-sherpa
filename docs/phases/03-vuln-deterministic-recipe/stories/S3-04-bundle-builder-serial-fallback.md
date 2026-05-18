# Story S3-04 — `BundleBuilder` with `asyncio.Semaphore` concurrency + deterministic serial fallback (ADR-0008)

**Step:** Step 3 — TCCM, BundleBuilder, VulnIndex, content-addressed cache
**Status:** Ready
**Effort:** M
**Depends on:** S3-01
**ADRs honored:** Phase 3 ADR-0008 (deterministic serial fallback; NOT hedged-race — production commitment §2.4 is veto-strength), production ADR-0029 (TCCM `must_read`/`should_read`/`may_read`), production ADR-0030 (graph-aware query primitives), production ADR-0032 (language search adapters provide `AdapterConfidence`)

## Context

`BundleBuilder` dispatches a plugin's TCCM `must_read` / `should_read` / `may_read` queries through Phase 2's language search adapters and returns a typed `Bundle`. Concurrency is bounded by `asyncio.Semaphore(min(4, os.cpu_count()))` overridable via `CODEGENIE_BUNDLE_CONCURRENCY`. **Fallback semantics is the load-bearing decision** — ADR-0008 explicitly *rejects* hedged-race composition because two runs against the same inputs would return different Bundle bytes (scheduler noise), violating production design §2.4's "same inputs → same Transform bytes" veto-strength commitment. The TCCM-declared `fallback` query fires **only** when the primary returns `AdapterConfidence ∈ {Degraded, Unavailable}` — never raced, never both. Property-tested across 100 Hypothesis runs for byte-identical output.

This story ships the builder's structure, the semaphore, the serial-fallback dispatch, and the `AdapterDegraded` event hand-off. The cache key (which includes `vuln_index.digest`) and the `BundleCacheGc` GC mechanism land in S3-05 (Gap 4).

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
  - `src/codegenie/adapters/` — Phase 02's `AdapterConfidence` enum; reuse `Degraded | Unavailable | High` variants.
  - `src/codegenie/types/identifiers.py` — `PluginId`, `PrimitiveName`, `BlobDigest`.

## Goal

`codegenie.plugins.bundle.BundleBuilder` exposes `async def build(resolution, repo_ctx, vuln, vuln_index) -> Bundle`; dispatch is bounded by `asyncio.Semaphore(min(4, os.cpu_count()))` (overridable via `CODEGENIE_BUNDLE_CONCURRENCY`); the TCCM-declared `fallback` chain fires **deterministically and serially** *only* on `AdapterConfidence ∈ {Degraded, Unavailable}` from the primary — never raced. An `AdapterDegraded` event is emitted on every fallback firing for `TrustScorer.confidence` folding (Goal G8). Property-tested for byte-identical `Bundle` output across 100 Hypothesis runs.

## Acceptance criteria

- [ ] New module `src/codegenie/plugins/bundle.py` exports `BundleBuilder`, `Bundle`, `BundleEntry`, `BundleBuilderError`. Module docstring cites ADR-0008 §Decision and the rejection of hedged-race.
- [ ] `BundleEntry` Pydantic with `frozen=True, extra="forbid"`: `primitive: PrimitiveName`, `args_canonical: str` (canonicalized JSON of `ContextQuery.args`, used for cache-key composition in S3-05), `payload: dict[str, str | int | bool | list[str]]` (primitive-only; matches `TrustSignal.details` discipline), `confidence: AdapterConfidence`, `fallback_used: bool`.
- [ ] `Bundle` Pydantic with `frozen=True, extra="forbid"`: `entries: tuple[BundleEntry, ...]` (tuple for hash-stability), `plugin_id: PluginId`, `vuln_index_digest: BlobDigest` (recorded for ADR-0008 cache-key correctness; S3-05 reads this).
- [ ] `BundleBuilder.__init__(cache_dir: Path, *, event_emitter: Callable[[AdapterDegradedEvent], None] | None = None)` — `event_emitter` is the seam for `EventLog.emit_internal` (S6-01); defaults to no-op so this story is testable without the full EventLog.
- [ ] `async def build(resolution, repo_ctx, vuln, vuln_index) -> Bundle` iterates `resolution.composed_tccm.must_read` THEN `should_read` THEN `may_read` (deferred `may_read` execution per ADR-0029 is OUT of scope here — Phase 3 executes all three eagerly; mark in module docstring).
- [ ] **Concurrency bound:** all queries run under one `asyncio.Semaphore`. The bound is `min(4, os.cpu_count() or 1)` at module import time, overridable by `CODEGENIE_BUNDLE_CONCURRENCY=N` (positive int; non-positive or non-int raises `BundleBuilderError(reason="invalid_concurrency_env")` at builder construction time — fail loud).
- [ ] **Deterministic serial fallback (NOT hedged race — ADR-0008):** for each `ContextQuery`, invoke the primary via `resolution.composed_adapters[primitive].query(args)`. Read `.confidence`. ONLY if `confidence in {AdapterConfidence.Degraded, AdapterConfidence.Unavailable}` AND `query.fallback is not None`, invoke the fallback query. The fallback runs *after* the primary completes — never concurrently. NEVER fire both speculatively.
- [ ] **Fallback chain depth cap:** `ContextQuery.fallback` is itself a `ContextQuery` (may have its own `fallback`). Cap the chain at depth `4` to prevent pathological YAML; on overflow raise `BundleBuilderError(reason="fallback_chain_too_deep", primitive=..., depth=...)`.
- [ ] **`AdapterDegraded` event emission:** on every fallback firing, call `event_emitter(AdapterDegradedEvent(primitive=..., adapter_name=..., reason=...))` so `TrustScorer.confidence` (S6-02) folds it. The event is fired *before* the fallback runs (operators see "we're falling back" not "we fell back").
- [ ] **Determinism property test:** 100 Hypothesis runs against `BundleBuilder.build(...)` with identical inputs (and a fixed adapter that returns a fixed `AdapterConfidence.High` payload) return `Bundle` instances with byte-identical `model_dump_json()`. Failures attach the diff for debugging.
- [ ] **Serial-fallback property test:** 100 runs against a primary that ALWAYS returns `Degraded` and a fallback that ALWAYS returns `High` — the fallback is invoked exactly **once per query** (counted via a spy adapter); the primary is invoked exactly **once per query**; the two invocation orders are deterministic (primary BEFORE fallback, always — NEVER both raced).
- [ ] `mypy --strict` clean; AST source-scan asserts no `asyncio.gather` of `(primary, fallback)` pair in the module (the hedged-race anti-pattern is structurally absent).
- [ ] TDD red test exists, committed, green.
- [ ] `ruff format`, `ruff check` clean.

## Implementation outline

1. Create `src/codegenie/plugins/bundle.py`:
   - Imports: `asyncio`, `os`, `Final` from `typing`, `Callable`; `BaseModel, ConfigDict` from `pydantic`; `PluginId, PrimitiveName, BlobDigest` from `codegenie.types.identifiers`; `AdapterConfidence` from `codegenie.adapters`; `ContextQuery` from `codegenie.plugins.tccm`.
   - Module-level: `_MAX_FALLBACK_DEPTH: Final[int] = 4`; `_DEFAULT_CONCURRENCY_BOUND = min(4, os.cpu_count() or 1)`.
   - `def _read_concurrency_bound() -> int` — reads env, validates positive int.
   - `class BundleBuilderError(CodegenieError)` markers-only.
   - `class AdapterDegradedEvent(BaseModel)` frozen, `extra="forbid"`: `primitive: PrimitiveName`, `adapter_name: str`, `reason: str`.
   - `class BundleEntry(BaseModel)`, `class Bundle(BaseModel)` per ACs.
   - `class BundleBuilder:`
     - `__init__(self, cache_dir, *, event_emitter=None)` — store + validate env at construction.
     - `async def build(self, resolution, repo_ctx, vuln, vuln_index) -> Bundle`:
       - Construct `semaphore = asyncio.Semaphore(self._concurrency)`.
       - For each query in chained `must_read + should_read + may_read`, schedule `self._run_one(query, resolution.composed_adapters, semaphore)`.
       - `entries = await asyncio.gather(*tasks)`.
       - Return `Bundle(entries=tuple(entries), plugin_id=resolution.plugin.manifest.name, vuln_index_digest=vuln_index.digest())`.
     - `async def _run_one(self, query, adapters, semaphore, _depth=0) -> BundleEntry`:
       - `async with semaphore:` invoke `primary = await adapters[query.primitive].query(query.args)`.
       - If `primary.confidence not in {Degraded, Unavailable}` OR `query.fallback is None`: return `BundleEntry(... fallback_used=False)`.
       - Else (fallback): check `_depth >= _MAX_FALLBACK_DEPTH` → raise. Emit `AdapterDegradedEvent`. **Recursively** call `_run_one(query.fallback, adapters, semaphore, _depth=_depth+1)`; mark the resulting entry's `fallback_used=True`.
2. Add `tests/property/plugins/test_bundle_determinism.py` and `tests/property/plugins/test_bundle_serial_fallback.py` per ACs.
3. Add an AST source-scan test `tests/static/test_no_hedged_race_in_bundle.py` that walks `src/codegenie/plugins/bundle.py` AST and asserts no `Call` node with `func.attr == "gather"` has BOTH a primary and a fallback argument (heuristic: no `gather` call where any arg expression mentions `.fallback`).

## TDD plan — red / green / refactor

### Red

Test file: `tests/unit/plugins/test_bundle_builder.py`

```python
import os
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from codegenie.plugins.bundle import BundleBuilder, Bundle, BundleEntry, BundleBuilderError, AdapterDegradedEvent
from codegenie.plugins.tccm import ContextQuery, TCCM
from codegenie.adapters import AdapterConfidence

class FakeAdapter:
    """Spy adapter: counts query invocations + returns a fixed confidence."""
    def __init__(self, confidence=AdapterConfidence.High, payload=None):
        self.confidence = confidence
        self.payload = payload or {"hit": "ok"}
        self.calls = 0
    async def query(self, args):
        self.calls += 1
        return MagicMock(confidence=self.confidence, payload=self.payload, adapter_name="fake")

class TestConcurrencyBound:
    def test_env_override_invalid_raises_at_construction(self, monkeypatch, tmp_path):
        # Fail loud: Rule 12 — operators typing bad env values must see it immediately
        monkeypatch.setenv("CODEGENIE_BUNDLE_CONCURRENCY", "not-a-number")
        with pytest.raises(BundleBuilderError) as exc:
            BundleBuilder(cache_dir=tmp_path)
        assert exc.value.reason == "invalid_concurrency_env"

    def test_env_override_nonpositive_raises(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CODEGENIE_BUNDLE_CONCURRENCY", "0")
        with pytest.raises(BundleBuilderError):
            BundleBuilder(cache_dir=tmp_path)

    @pytest.mark.asyncio
    async def test_default_concurrency_min_4_or_cpu_count(self, monkeypatch, tmp_path, fake_resolution_with_5_queries):
        # Verify the semaphore bound by counting concurrent in-flight queries
        ...

class TestSerialFallbackSemantics:
    """ADR-0008: serial fallback, NOT hedged-race."""

    @pytest.mark.asyncio
    async def test_no_fallback_when_primary_confidence_high(self, tmp_path, fake_resolution_with_fallback):
        primary = fake_resolution_with_fallback.composed_adapters["scip.refs"]  # FakeAdapter(High)
        fallback = fake_resolution_with_fallback.composed_adapters["dep_graph.consumers"]
        builder = BundleBuilder(cache_dir=tmp_path)
        bundle = await builder.build(fake_resolution_with_fallback, ...)
        # Fallback adapter NEVER invoked when primary is High
        assert primary.calls == 1 and fallback.calls == 0
        assert bundle.entries[0].fallback_used is False

    @pytest.mark.asyncio
    async def test_fallback_invoked_once_when_primary_degraded(self, tmp_path, fake_resolution_with_degraded_primary):
        primary = fake_resolution_with_degraded_primary.composed_adapters["scip.refs"]   # FakeAdapter(Degraded)
        fallback = fake_resolution_with_degraded_primary.composed_adapters["dep_graph.consumers"]
        events: list = []
        builder = BundleBuilder(cache_dir=tmp_path, event_emitter=events.append)
        bundle = await builder.build(fake_resolution_with_degraded_primary, ...)
        # Primary fires once; fallback fires once; never raced
        assert primary.calls == 1 and fallback.calls == 1
        assert bundle.entries[0].fallback_used is True
        # AdapterDegraded event emitted before fallback (operator visibility)
        assert any(isinstance(e, AdapterDegradedEvent) for e in events)

    @pytest.mark.asyncio
    async def test_primary_runs_strictly_before_fallback(self, tmp_path):
        # Order-recording adapter pair confirms primary completes before fallback starts
        order: list[str] = []

        class OrderingAdapter:
            def __init__(self, name, confidence): self.name, self.confidence = name, confidence
            async def query(self, args):
                order.append(f"{self.name}:start")
                await asyncio.sleep(0)
                order.append(f"{self.name}:done")
                return MagicMock(confidence=self.confidence, payload={}, adapter_name=self.name)

        ...
        # Assert: ["primary:start", "primary:done", "fallback:start", "fallback:done"]
        # NEVER interleaved (which would prove hedged-race)
        assert order == ["primary:start", "primary:done", "fallback:start", "fallback:done"]

    @pytest.mark.asyncio
    async def test_fallback_chain_depth_capped_at_4(self, tmp_path):
        # Build a 5-deep fallback chain; assert BundleBuilderError(reason="fallback_chain_too_deep")
        ...

class TestEventEmission:
    @pytest.mark.asyncio
    async def test_adapter_degraded_event_carries_primitive_and_adapter_name(self, tmp_path):
        ...
```

Property test (`tests/property/plugins/test_bundle_determinism.py`):

```python
from hypothesis import given, settings, strategies as st

@settings(max_examples=100, deadline=None)
@given(seed=st.integers(min_value=0, max_value=10**9))
def test_bundle_is_byte_identical_across_runs(seed, tmp_path_factory):
    """Goal G4 + ADR-0008: same inputs → same Bundle bytes; hedged-race would fail this."""
    # Arrange: fixed resolution, fixed adapters, fixed vuln_index — only randomized
    # scheduling-shuffle through the asyncio loop. A hedged-race builder fails here.
    bundles = [_run_build_sync(seed, tmp_path_factory.mktemp(str(i))) for i in range(2)]
    assert bundles[0].model_dump_json() == bundles[1].model_dump_json()
```

Property test (`tests/property/plugins/test_bundle_serial_fallback.py`):

```python
@settings(max_examples=100, deadline=None)
@given(...)
def test_fallback_invoked_exactly_once_when_primary_degraded(...):
    # Primary always Degraded → fallback always fires; never raced; counts are exact
    ...
```

Static (`tests/static/test_no_hedged_race_in_bundle.py`):

```python
import ast
from pathlib import Path

def test_bundle_module_has_no_hedged_race():
    """Structural defense: no asyncio.gather(primary, fallback) pair in bundle.py.

    ADR-0008 rejects hedged-race; this AST test guarantees the anti-pattern is structurally absent."""
    src = Path("src/codegenie/plugins/bundle.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "gather":
                arg_src = ast.unparse(node)
                assert "fallback" not in arg_src, f"hedged-race smell: {arg_src}"
```

### Green

Smallest impl: §Implementation outline; ~140 lines.

### Refactor

- Extract `_dispatch_single(query, adapter, args) -> AdapterResult` for clarity at the await site.
- Add a structlog `bundle.query_dispatched` info per query (operator visibility).
- Consider a `BundleBuilderConfig` dataclass to pass `(concurrency_bound, max_fallback_depth)` rather than module globals — Phase 14 may want per-workflow overrides.
- Add a `tests/integration/plugins/test_bundle_with_real_phase02_adapters.py` once Phase 2 adapters are wired (S7-02). Out-of-scope here; leave a TODO comment.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/plugins/bundle.py` | New module — `BundleBuilder`, `Bundle`, `BundleEntry`, `AdapterDegradedEvent` |
| `tests/unit/plugins/test_bundle_builder.py` | Unit tests for concurrency + serial-fallback semantics |
| `tests/property/plugins/test_bundle_determinism.py` | 100-run determinism property test |
| `tests/property/plugins/test_bundle_serial_fallback.py` | 100-run serial-fallback property test |
| `tests/static/test_no_hedged_race_in_bundle.py` | AST source-scan: no hedged-race anti-pattern |
| `tests/unit/plugins/conftest.py` | `fake_resolution_*` fixtures |

## Out of scope

- **Cache key composition + cache lookup** — S3-05 ships the BLAKE3 key (including `vuln_index.digest`) and the on-disk cache; this story builds the in-memory `Bundle` only.
- **`BundleCacheGc`** — S3-05 (Gap 4 fix).
- **Real Phase 2 search-adapter wiring** — Phase 2's `dep_graph.consumers`, `import_graph.reverse_lookup`, `scip.refs`, `test_inventory.tests_exercising` adapters are plumbed by S7-02; this story uses spy adapters in tests.
- **`TrustScorer.confidence` folding** — S6-02 reads `AdapterDegraded` events from the EventLog; this story just emits them via the seam.
- **Deferred `may_read` execution** — ADR-0029 allows worker nodes to lazily request `may_read`; Phase 3 executes all three bands eagerly. Document the deviation; Phase 6 may revisit.
- **Cancellation on partial failure** — if one adapter raises, current shape lets `asyncio.gather` propagate; richer `return_exceptions=True` + per-entry error variants are a S6-04 concern.

## Notes for the implementer

- **The hedged-race rejection is a hard line.** Production design §2.4 is **veto-strength**; the determinism property test (S8-03) will fail by construction if you ever `asyncio.gather(primary, fallback)`. The AST source-scan test is belt-and-suspenders; do not weaken it.
- **`_MAX_FALLBACK_DEPTH = 4` matches the `extends`-chain cap in S2-04** — same intuition: human-authored YAML, deeper than 4 is almost always a mistake. Keep symmetric.
- **`asyncio.Semaphore(n)` is per-`build()` call, not module-level.** A module-level semaphore would serialize across concurrent workflows (Phase 6.5+ runs multiple); per-call keeps the bound per-workflow. Tests should verify this is per-call (spawn two `build()` coroutines, expect them not to share the bound).
- **`AdapterConfidence` import path** — Phase 02 owns `codegenie.adapters.AdapterConfidence`. Verify it exports `High`, `Degraded`, `Unavailable` variants; if any is missing, surface to the implementer of S1-03 (tagged-union outcomes) rather than adding here.
- **`event_emitter=None` default** keeps this story testable without S6-01's `EventLog`. The orchestrator (S6-04) wires `event_emitter=event_log.emit_internal` at construction. Do NOT make `EventLog` a required dep — that would block this story on S6-01.
- **`canonicalize(args)` for `BundleEntry.args_canonical`** — `json.dumps(args, sort_keys=True, separators=(",", ":"))`. Sort dict keys; cache-key correctness depends on this. S3-05 will hash it.
- **Pure-function fold over typed inputs.** This is the spirit of ADR-0008 §Pattern fit ("Functional core / imperative shell"). The `build` method is "the pure fold"; the I/O is the adapter `query` calls. Keep the fold pure (no logging in the loop body; emit at boundaries).
- **`os.cpu_count() or 1`** — on weird hosts `cpu_count()` returns `None`; the `or 1` keeps the bound positive. Tests should cover `cpu_count() is None` via `monkeypatch`.
- **Beware Pydantic v2 `tuple[BundleEntry, ...]`** — sometimes needs `Annotated[tuple[BundleEntry, ...], ...]` for proper serialization round-trip; if `model_validate(model_dump())` round-trips fail, switch to `Sequence[BundleEntry]` + convert to tuple in `__init__`.
