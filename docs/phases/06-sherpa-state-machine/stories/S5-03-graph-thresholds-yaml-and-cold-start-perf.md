# S5-03 — Ship `tools/policy/graph-thresholds.yaml` with digest pin + cold-start perf gate

**Step:** Step 5 — Implement `build_vuln_loop()` lazy-singleton factory + topology golden + `interrupt_before`
**Effort:** S
**Depends on:** S5-02 (topology golden + reachability tests green)
**Status:** Backlog
**ADRs honored:** ADR-0001 (lazy-singleton factory — the cold-start canary is exactly what justifies the ADR's "compile once per worker" claim), ADR-0007 (BLAKE3 chain extension — the YAML digest is pinned via the same BLAKE3 mechanism)

## Context

Step 5 lands the factory and the topology golden but leaves two seams open:

1. **Routing thresholds are hard-coded in `graph/edges.py` from Step 3.** `route_after_rag` uses `0.85` for the RAG-score cutoff; `route_after_attempt` uses `2` for the same-signature flake window; `VulnLedger.max_attempts` defaults to `3`. These values appear in arch §Configuration as "Pydantic `Settings` from `tools/policy/graph-thresholds.yaml`, digest-pinned at startup." Until that YAML exists and is loaded, any operator-driven retuning requires a code edit + redeploy, and the digest-pinned audit trail (mirror of Phase 5's policy posture) is absent.
2. **ADR-0001's "80 ms compile cost paid once per worker" is unverified.** Without a perf canary, a future PR that imports a heavyweight module at `_build()` time or adds an O(n²) topology pass could silently push the cold-start past acceptable bounds. The arch §Performance regression tests section explicitly names `tests/perf/test_compile_cold_start.py` with a p50 target of < 200 ms (baseline ~80 ms; loose ceiling to absorb CI-runner noise).

This story ships both. The YAML is read by `graph/edges.py` (and by `route_after_attempt` for the same-signature window) via a typed loader; its BLAKE3 digest is pinned in `tools/digests.yaml` so any silent edit to the policy file is caught at startup. The cold-start canary measures `build_vuln_loop(force_rebuild=True)` wall-clock across N invocations and asserts p50 < 200 ms.

The values are **not new policy** — they're the same defaults Step 3 already coded into the edge predicates. This story extracts them into the YAML and adds the digest pin; the edge predicates change from `0.85` literal to `settings.rag_score_threshold` (one-line refactor per consumer).

## References — where to look

- `docs/phases/06-sherpa-state-machine/phase-arch-design.md` §Configuration — precedence chain (CLI > env > YAML > hard-coded), digest-pin posture mirroring Phase 5.
- `docs/phases/06-sherpa-state-machine/phase-arch-design.md` §Testing strategy — "Performance regression tests" subsection lists `tests/perf/test_compile_cold_start.py` with the < 200 ms p50 target.
- `docs/phases/06-sherpa-state-machine/phase-arch-design.md` §Component 2 "Performance envelope" — "First call ≤ 80 ms (compile cost, measured by canary); subsequent calls with same key < 1 µs (dict lookup)."
- `docs/phases/06-sherpa-state-machine/ADRs/0001-lazy-singleton-build-vuln-loop-factory.md` — the claim this canary verifies.
- `docs/phases/06-sherpa-state-machine/High-level-impl.md` §Step 5 done criteria item 4 — `tests/perf/test_compile_cold_start.py` p50 < 200 ms.
- `docs/phases/06-sherpa-state-machine/final-design.md` §Synthesis ledger — for the policy-digest posture (mirrors Phase 5's existing `tools/digests.yaml`).
- Phase 5 reference: `tools/digests.yaml` already exists for Phase 5 policy files; this story **adds** an entry, doesn't reinvent the file format. If Phase 5's exact file shape is unclear, grep for `digests.yaml` in `docs/phases/05-*` first.

## Goal (one sentence)

Ship `tools/policy/graph-thresholds.yaml` with `max_attempts: 3`, `rag_score_threshold: 0.85`, `same_signature_window: 2`, pin its BLAKE3 digest in `tools/digests.yaml`, wire a typed Pydantic `GraphThresholds` Settings loader read by `graph/edges.py`, and add `tests/perf/test_compile_cold_start.py` asserting `build_vuln_loop(force_rebuild=True)` p50 < 200 ms across 11 invocations.

## Acceptance criteria

- [ ] `tools/policy/graph-thresholds.yaml` exists with exactly three keys (`max_attempts: 3`, `rag_score_threshold: 0.85`, `same_signature_window: 2`), valid YAML 1.2, UTF-8, with a one-paragraph header comment naming the consumers (`graph/edges.py:route_after_rag`, `graph/edges.py:route_after_attempt`).
- [ ] `tools/digests.yaml` gains a new entry mapping `tools/policy/graph-thresholds.yaml` → its BLAKE3 hex digest. Format matches Phase 5's existing entries (do **not** invent a new format — Rule 11 — match the codebase).
- [ ] `src/codegenie/graph/_thresholds.py` (or wherever the project keeps Pydantic Settings — surface the choice and pick one) exports a `GraphThresholds(BaseModel)` with the three typed fields (`max_attempts: int`, `rag_score_threshold: float`, `same_signature_window: int`) and `load_graph_thresholds() -> GraphThresholds` that (a) reads the YAML, (b) verifies the BLAKE3 against `tools/digests.yaml`, raising a typed exception on mismatch, (c) returns the validated model.
- [ ] `graph/edges.py` reads `rag_score_threshold` and `same_signature_window` from `GraphThresholds` instead of literals. The change is a one-line-per-consumer swap; no other edge logic changes.
- [ ] `tests/perf/test_compile_cold_start.py` measures `build_vuln_loop(checkpointer=InMemorySaver(), force_rebuild=True)` 11 times, computes the median (p50) of the 11 durations, and asserts `p50_ms < 200`. First sample is discarded as warm-up (CPython JIT/import warmth). The remaining 10 form the statistic.
- [ ] `tests/graph/test_thresholds_digest_pin.py` confirms (a) the loader returns the three correct values on the unmodified YAML, (b) corrupting the YAML by appending a byte raises a typed `ThresholdsDigestMismatch` (or whatever the chosen name is — pick one and surface it), (c) missing entry in `tools/digests.yaml` raises a typed exception with a remediation hint.
- [ ] **Red test exists and was committed before the implementation** (see TDD plan); it now passes.
- [ ] `ruff format`, `ruff check`, `mypy --strict src/codegenie/graph/`, and `pytest tests/graph/ tests/perf/test_compile_cold_start.py` are clean.

## Implementation outline

1. **Author the YAML.** `tools/policy/graph-thresholds.yaml`:
   ```yaml
   # Phase 6 — vuln-loop routing thresholds.
   # Consumers:
   #   src/codegenie/graph/edges.py::route_after_rag       (rag_score_threshold)
   #   src/codegenie/graph/edges.py::route_after_attempt   (same_signature_window)
   #   src/codegenie/graph/state.py::VulnLedger.max_attempts default
   # Edits require updating the BLAKE3 digest in tools/digests.yaml.
   max_attempts: 3
   rag_score_threshold: 0.85
   same_signature_window: 2
   ```
2. **Compute the digest and pin it.** From the repo root:
   ```bash
   blake3sum tools/policy/graph-thresholds.yaml
   ```
   (or use the project's existing digest-pin script — check `tools/` first; do not introduce a new BLAKE3 invocation if Phase 5 already has one). Add the entry to `tools/digests.yaml` matching the existing schema.
3. **Implement `GraphThresholds` + loader.** Place: `src/codegenie/graph/_thresholds.py` (private — leading underscore — internal-only contract). Use Pydantic v2 `BaseModel` with `model_config = ConfigDict(extra="forbid", frozen=True)`. `load_graph_thresholds()` reads the YAML, computes BLAKE3, looks up the expected digest in `tools/digests.yaml`, raises a typed exception on mismatch, and returns the model. Cache via `functools.lru_cache(maxsize=1)` so the digest verification cost is paid once per process — but **not** so aggressively that test isolation breaks (every test that swaps the YAML should call `load_graph_thresholds.cache_clear()`).
4. **Wire `graph/edges.py`.** Replace the `0.85` literal in `route_after_rag` with `_thresholds().rag_score_threshold`; replace the `2` window in `route_after_attempt`'s same-signature helper with `_thresholds().same_signature_window`. Surgical edits per Rule 3 — touch only those two lines and import the loader at module top. The Step 3 property tests should still pass byte-identically (the values are unchanged).
5. **Write the perf canary.** `tests/perf/test_compile_cold_start.py`:
   - Import `build_vuln_loop`, `InMemorySaver`, `time.perf_counter_ns`.
   - Marked `@pytest.mark.perf` (so it can be skipped on dev iterations if a `perf` mark is registered; check `pyproject.toml`).
   - 11 iterations of `(InMemorySaver(), force_rebuild=True)` invocation; record `(t_end - t_start) // 1_000_000` ms.
   - **Discard the first sample** (warm-up); take median of the remaining 10.
   - `assert p50_ms < 200, f"cold-start p50 regressed to {p50_ms} ms (ADR-0001 target ≤ 80 ms, ceiling 200 ms)"`.
   - Print all 10 samples on failure for triage.
6. **Add a typed exception.** `src/codegenie/graph/events.py` (which already houses the exception hierarchy from S1-04) gains `class ThresholdsDigestMismatch(RuntimeError): ...` with a constructor that takes `(expected, actual, path)` and renders a clear message. Per ADR-0007 spirit (BLAKE3 tamper evidence), the exception is loud and unambiguous.

## TDD plan (red → green → refactor)

**Red — three tests committed before implementation:**

```python
# tests/graph/test_thresholds_loader.py
import pytest
from codegenie.graph._thresholds import load_graph_thresholds, ThresholdsDigestMismatch


def test_load_graph_thresholds_returns_pinned_values():
    """The YAML's pinned values are the ones the edge predicates rely on.

    Why this matters: a silent value drift (e.g., someone editing the YAML
    from 0.85 to 0.80 without updating the digest) would change routing
    behavior across the whole vuln loop. The loader's digest verification
    is what makes the YAML safer than a hard-coded constant.
    """
    t = load_graph_thresholds()
    assert t.max_attempts == 3
    assert t.rag_score_threshold == 0.85
    assert t.same_signature_window == 2


def test_corrupted_yaml_raises_digest_mismatch(tmp_path, monkeypatch):
    """Editing the YAML without bumping the digest fails loudly."""
    import shutil, codegenie.graph._thresholds as m
    src = m.YAML_PATH  # public-ish module-level constant
    dst = tmp_path / "graph-thresholds.yaml"
    shutil.copy(src, dst)
    dst.write_bytes(dst.read_bytes() + b"\n# tampered\n")
    monkeypatch.setattr(m, "YAML_PATH", dst)
    load_graph_thresholds.cache_clear()
    with pytest.raises(ThresholdsDigestMismatch):
        load_graph_thresholds()


def test_missing_digest_entry_raises(monkeypatch, tmp_path):
    """If tools/digests.yaml has no entry for this YAML, fail with a hint."""
    import codegenie.graph._thresholds as m
    empty = tmp_path / "digests.yaml"
    empty.write_text("{}\n")
    monkeypatch.setattr(m, "DIGESTS_PATH", empty)
    load_graph_thresholds.cache_clear()
    with pytest.raises(Exception) as ei:
        load_graph_thresholds()
    assert "tools/digests.yaml" in str(ei.value) or "digest" in str(ei.value).lower()
```

```python
# tests/perf/test_compile_cold_start.py
import time
import statistics
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from codegenie.graph import build_vuln_loop


@pytest.mark.perf
def test_compile_cold_start_p50_under_200ms():
    """Cold-start compile p50 stays under the ADR-0001 budget.

    Why this matters: ADR-0001 justifies the lazy-singleton factory on the
    grounds that compile is ~80 ms once per worker. If that drifts (e.g.,
    an expensive import sneaks into `_build()`), the ADR's tradeoff math
    breaks silently. 200 ms is a loose ceiling sized for CI-runner noise.
    """
    samples_ms: list[float] = []
    for i in range(11):
        saver = InMemorySaver()
        t0 = time.perf_counter_ns()
        build_vuln_loop(checkpointer=saver, force_rebuild=True)
        t1 = time.perf_counter_ns()
        samples_ms.append((t1 - t0) / 1_000_000)
    # Discard warm-up sample.
    measured = samples_ms[1:]
    p50 = statistics.median(measured)
    assert p50 < 200, (
        f"cold-start p50 regressed to {p50:.1f} ms (target ≤ 80 ms, "
        f"ceiling 200 ms). All samples (ms, excl. warm-up): {measured}"
    )
```

Commit message: `test(graph): red — thresholds digest pin + cold-start perf canary (S5-03)`.

**Green — implementation.** Create the YAML, compute the digest, pin it, ship `_thresholds.py`, wire edges, add `ThresholdsDigestMismatch` to `events.py`. Verify the Step 3 property tests still pass byte-identically (the literal-to-settings swap is value-neutral).

**Refactor.** Two specific tidies:

- If `tools/digests.yaml` did not exist before this PR (i.e., Phase 5 used a different mechanism), surface that in the PR description and pick one of: (a) ship a new `tools/digests.yaml` matching the Phase 5 pattern documented elsewhere, (b) extend whatever Phase 5 actually uses. Do not invent a third pattern. Rule 7 — surface conflicts, don't average them.
- If `load_graph_thresholds.cache_clear()` ends up sprinkled across tests, promote it to an autouse fixture in `tests/graph/conftest.py` that clears caches between tests. One source of truth.

## Files to touch

- **New:** `tools/policy/graph-thresholds.yaml`.
- **New:** `src/codegenie/graph/_thresholds.py` (Pydantic Settings + digest-verifying loader).
- **New:** `tests/graph/test_thresholds_loader.py`.
- **New:** `tests/perf/test_compile_cold_start.py`.
- **New (if it doesn't exist):** `tests/perf/__init__.py` + `tests/perf/conftest.py` (register `perf` mark in `pyproject.toml` or `conftest.py`).
- **Edit (additive only, one line):** `tools/digests.yaml` — add the BLAKE3 entry.
- **Edit (surgical, ≤ 2 lines + 1 import each):** `src/codegenie/graph/edges.py` — replace the `0.85` literal in `route_after_rag` and the `2` window literal in `route_after_attempt` with calls to the loader.
- **Edit (additive only):** `src/codegenie/graph/events.py` — add `ThresholdsDigestMismatch`.

## Out of scope

- **CLI `--rag-score-threshold` / `--same-signature-window` flags.** Operator overrides via CLI flag arrive in Step 6 (`cli/loop.py`); precedence is documented in arch §Configuration but not implemented in this story.
- **Hot-reload of the YAML mid-workflow.** Per arch §Component 2 "No mid-run topology mutation"; the loader caches and stays cached for the worker's lifetime.
- **Phase 5 contract changes.** This story does not touch Phase 5's existing digest-pin machinery; it only adds a new entry consumed by `tools/digests.yaml`.
- **Updating ADR-0001's "80 ms" number.** The canary measures it; if the number is consistently 120 ms on CI, that's worth surfacing in a follow-up — but adjusting the ADR is not this story.
- **Throughput canaries.** Step 9 ships `tests/perf/test_canary_overhead.py` (per-node overhead) and `tests/perf/test_checkpoint_throughput.py` (SQLite throughput). Different concerns, different stories.

## Notes for the implementer

- **Do not invent a digest format.** Read Phase 5's `tools/digests.yaml` once (or whatever Phase 5 actually shipped — verify before assuming) and copy the format exactly. If the format is "path → hex digest" map, mirror it. If it's a YAML list of objects, mirror it. Rule 11.
- **The cold-start canary will be noisy on first run.** 200 ms is the documented ceiling; 80 ms is the target. If you see a p50 of 150 ms on a CI runner, the test still passes — that's intentional. Do **not** tighten to < 100 ms in this story; the looseness is what makes the gate green on Renovate PRs that bump unrelated dependencies. If the gate goes red, the failing-print of all 10 samples gives the next engineer enough signal to triage.
- **`InMemorySaver` is the right choice for the canary**, not `AuditedSqliteSaver`. The canary measures compile cost, not checkpoint-write cost; using a real file-backed saver pollutes the measurement.
- **Each canary iteration constructs a fresh `InMemorySaver`** so that `id(checkpointer)` changes — guaranteeing the cache busts even without `force_rebuild`. The `force_rebuild=True` argument is belt-and-suspenders.
- **Pydantic v2 `BaseModel.model_config = ConfigDict(extra="forbid", frozen=True)`** matches the project convention from `VulnLedger`. Don't use Pydantic v1 `Config` class or `BaseSettings` (the project standardized on v2 in earlier phases).
- **`statistics.median` of 10 samples** gives an integer-step result on small N but is the standard p50 approximation; don't reach for `numpy` for one number.
- **Mark the perf test `@pytest.mark.perf`** and ensure `pyproject.toml` registers the mark to avoid `PytestUnknownMarkWarning`. If `perf` isn't already registered (it likely isn't in Phase 6), register it.
- **Avoid mocking `time.perf_counter_ns`.** The canary's whole value is that it observes real wall-clock. If CI noise becomes a problem in practice, add a `@pytest.mark.flaky` retry in a follow-up rather than mocking the clock.
- **The digest mismatch path must surface remediation.** Operator-facing error message: include the path that mismatched, the expected digest, and the actual digest. Operator-facing instructions: "If this YAML edit was intentional, recompute the digest with `blake3sum tools/policy/graph-thresholds.yaml` and update `tools/digests.yaml`." Rule 12 — fail loud.
- **`load_graph_thresholds()` is called from `graph/edges.py` at module import time?** Probably yes — the edge predicates are module-level callables — but verify. If the call happens per-predicate-invocation, the digest verification runs on every routing decision; the `lru_cache` makes that cheap, but `route_after_attempt` is called inside Hypothesis property tests at 10k rate. If the perf shows up, hoist the call to module scope and bind to a module-level constant; either way works, but probe before assuming.
