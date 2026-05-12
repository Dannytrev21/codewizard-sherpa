# Story S2-05 — Cache-hit-on-real-repo integration test (two probes)

**Step:** Step 2 — Extend `LanguageDetectionProbe` and ship `NodeBuildSystemProbe`
**Status:** Ready
**Effort:** M
**Depends on:** S2-03 (canonical fixture `node_typescript_helm/`)
**ADRs honored:** ADR-0002 (memo is per-gather and does not interfere with cross-gather cache behavior), ADR-0004 (envelope still validates after a cache-hit gather), ADR-0010 (slice optionality)

## Context

This story lands the **load-bearing Phase 1 exit criterion #2** in its two-probe form: cache hits on the second run for `LanguageDetectionProbe` and `NodeBuildSystemProbe`. The same test file is extended in S5-05 to cover all six probes; this is the seam test, mirroring Phase 0's bullet-tracer cache-hit-on-second-run anchor (`docs/phases/00-bullet-tracer-foundations/stories/S4-04-fixtures-smoke-cache-hit.md`).

The load-bearing technique is identical to Phase 0's: **monkeypatch `os.scandir` at the probe-module level**, run a cold gather (warm the cache), run a second gather, and assert the monkeypatched callable's invocation count is **zero** on the second run. If the cache is honoured, no probe-internal walk occurs; if the cache is broken (wrong key derivation, mtime drift, sub-schema mismatch invalidating the slice), the walk fires and the count is non-zero.

Phase 0's lesson — restated here verbatim from the bullet-tracer notes — is that the monkeypatch target name must match how the probe imports `scandir`. The Phase 0 probe documents which name to patch in its module docstring; S2-01's refactor step adds the same docstring note. This story relies on that note being correct.

The redundant `probe.cache_hit` structlog assertion is the secondary signal: even if the monkeypatch target drifts and the invocation-count assertion silently passes, the structlog event count would catch the regression. **Both** assertions are required.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Scenarios" (Phase 0 sense)` — Phase 0's `phase-arch-design.md §"Scenarios — Scenario 2: Warm gather (cache hit, the bullet tracer's load-bearing exit)"` is the structural precedent. This phase's `../phase-arch-design.md §"Control flow"` happy-path describes the same flow with five additional probes.
  - `../phase-arch-design.md §"Gap analysis & improvements" → "Gap 1"` — pre-dispatch input-snapshot pass (S1-08) is what makes the cache key TOCTOU-safe across this two-gather sequence.
  - `../phase-arch-design.md §"Edge cases"` row 16 (mid-gather mtime change) — orthogonal to this test, but adjacent: this test deliberately does **not** edit files between gathers, so the cache key is identical.
  - `../phase-arch-design.md §"Testing strategy" → "Test pyramid"` — this is in the integration tier.
- **Phase ADRs:**
  - `../ADRs/0002-parsed-manifest-memo-on-probe-context.md` — the memo is per-gather; this test runs two gathers, so the memo is constructed twice; the cache is across-gather and is what carries the load.
- **Source design:**
  - `../../../localv2.md §11` (caching layer).
- **Existing code:**
  - `tests/fixtures/node_typescript_helm/` (from S2-03).
  - `tests/integration/test_gather_cli.py` and the Phase 0 `test_cache_hit_on_second_run` (the bullet-tracer's `S4-04-fixtures-smoke-cache-hit.md`) — the canonical precedent for the monkeypatch + assertion pattern.
  - `src/codegenie/probes/language_detection.py` (the monkeypatch target lives at `codegenie.probes.language_detection.os.scandir` or `codegenie.probes.language_detection.scandir` per the module docstring set in S2-01's refactor step).
  - `src/codegenie/probes/node_build_system.py` — for the second monkeypatch target if/when the probe also calls `os.scandir` (most likely it does not; lockfile-precedence and tsconfig walks use `Path.exists()` + `jsonc.load`, not `os.scandir`).
  - `src/codegenie/cache/...` — the on-disk content-addressed cache layer.

## Goal

Running `codegenie gather <fixture>` twice in succession against `node_typescript_helm/`, with `os.scandir` monkeypatched at the `language_detection` module level, results in zero `os.scandir` invocations on the second run, and `ProbeExecution.CacheHit` reported for both `language_detection` and `node_build_system` probes — measured by both the monkeypatch invocation counter and the `probe.cache_hit` structlog event count.

## Acceptance criteria

- [ ] `tests/integration/probes/test_cache_hit_on_real_repo.py` exists with at least one test, `test_two_probes_cache_hit_on_second_run`.
- [ ] The test copies the fixture into `tmp_path / "repo"` (to avoid polluting the checked-in fixture's `.codegenie/` dir).
- [ ] First gather (cold): no monkeypatch; runs normally; populates the cache.
- [ ] Between the two gathers, **no file in the fixture is modified** (asserted by re-stat-ing every file's mtime + size pre- and post-first-gather; failing the assertion makes the second-run assertion meaningless).
- [ ] Second gather (warm): `os.scandir` is monkeypatched at `codegenie.probes.language_detection.os.scandir` (or whichever symbol name the S2-01-extension module docstring specifies — read the docstring; do **not** guess). The monkeypatch wraps the real `os.scandir` in a counter (does not block calls — failing to count is allowed only if zero invocations occur, but the counter must observe the invocation if any).
- [ ] After the second gather: the monkeypatched callable's invocation count is **zero**.
- [ ] After the second gather: the structlog event stream contains `event == "probe.cache_hit"` for both `language_detection` and `node_build_system` (asserted by `{e["probe"] for e in events if e["event"] == "probe.cache_hit"} >= {"language_detection", "node_build_system"}`).
- [ ] After the second gather: `.codegenie/context/repo-context.yaml` exists and validates against the envelope schema (the cache-hit path still produces a valid envelope — the cache stores the validated slice, not raw probe output).
- [ ] Second-run wall-clock is **not** asserted in this story (advisory benches land in S6-02).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict tests/integration/probes/test_cache_hit_on_real_repo.py`, `pytest tests/integration/probes/test_cache_hit_on_real_repo.py` all pass.

## Implementation outline

1. Add `tests/integration/probes/test_cache_hit_on_real_repo.py`.
2. Use the Phase 0 in-process CLI helper (`from codegenie.cli import gather_in_process`).
3. Copy `tests/fixtures/node_typescript_helm/` into `tmp_path / "repo"`.
4. Snapshot file mtimes + sizes pre-first-gather (`{p: (p.stat().st_mtime_ns, p.stat().st_size) for p in <walk>}`).
5. First gather: `gather_in_process([str(repo)], cwd=repo)`; assert exit 0.
6. Re-snapshot file mtimes + sizes; assert the dict is byte-equal to the pre-snapshot. **Fail loud** if any file changed (cache test is invalid otherwise).
7. Construct the `scandir` counter:
   ```python
   import codegenie.probes.language_detection as ld_mod
   real_scandir = ld_mod.os.scandir
   counter = {"n": 0}
   def counting_scandir(*a, **kw):
       counter["n"] += 1
       return real_scandir(*a, **kw)
   monkeypatch.setattr(ld_mod.os, "scandir", counting_scandir)
   ```
   (or `monkeypatch.setattr("codegenie.probes.language_detection.os.scandir", counting_scandir)` — both forms work; pick whichever Phase 0's `S4-04` chose.)
8. Capture structlog events via the `structlog_capture` fixture.
9. Second gather: `gather_in_process(...)`; assert exit 0.
10. Assert `counter["n"] == 0`.
11. Assert `{e["probe"] for e in events if e["event"] == "probe.cache_hit"} >= {"language_detection", "node_build_system"}`.
12. Re-open the post-gather `repo-context.yaml`; assert it validates against the envelope.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/probes/test_cache_hit_on_real_repo.py`

```python
# tests/integration/probes/test_cache_hit_on_real_repo.py

from pathlib import Path

FIXTURE = Path(__file__).parent.parent.parent / "fixtures" / "node_typescript_helm"


def test_two_probes_cache_hit_on_second_run(tmp_path, monkeypatch, structlog_capture):
    # arrange
    repo = tmp_path / "repo"
    _copy_tree(FIXTURE, repo)
    # snapshot pre-first-gather
    pre = _stat_snapshot(repo)
    # act 1 — cold gather, no patch
    from codegenie.cli import gather_in_process
    assert gather_in_process([str(repo)], cwd=repo) == 0
    # invariant: fixture files unchanged
    assert _stat_snapshot(repo) == pre, "fixture mtime/size drifted during first gather"
    # arrange — patch scandir at the probe module
    import codegenie.probes.language_detection as ld
    counter = {"n": 0}
    real = ld.os.scandir
    def counting(*a, **kw):
        counter["n"] += 1
        return real(*a, **kw)
    monkeypatch.setattr(ld.os, "scandir", counting)
    structlog_capture.clear()
    # act 2 — warm gather
    assert gather_in_process([str(repo)], cwd=repo) == 0
    # assert — zero scandir invocations on warm path
    assert counter["n"] == 0, f"expected 0 scandir calls, got {counter['n']}"
    # assert — both probes reported cache_hit
    hit_probes = {e["probe"] for e in structlog_capture if e["event"] == "probe.cache_hit"}
    assert {"language_detection", "node_build_system"} <= hit_probes
    # assert — envelope still validates
    import yaml
    ctx = yaml.safe_load((repo / ".codegenie" / "context" / "repo-context.yaml").read_text())
    from codegenie.schema import load_envelope_validator
    load_envelope_validator().validate(ctx)  # does not raise
```

The test must fail with a non-zero `counter["n"]` if any probe walks the fixture on the second run, **or** with a missing `probe.cache_hit` event if the cache layer silently passes through without emitting the structlog event, **or** with a `SchemaValidationError` if the cache writes back a corrupted envelope. Confirm red, commit, then Green.

### Green — make it pass

As with S2-04, this test exercises production paths already on disk. Going from red to green here means fixing the production layer that broke the contract:

- If `counter["n"] > 0`: either `LanguageDetectionProbe` walks the fixture even on cache hit (cache layer not wired right), or the monkeypatch target name is wrong (read the S2-01 module docstring).
- If `probe.cache_hit` is missing: the `CacheStore.get(...)` path doesn't emit the event, or the coordinator dispatches the probe even when the cache hits. Fix in `coordinator.py` or `cache/...`.
- If `SchemaValidationError`: the cached envelope diverges from the cached slice; likely a serialization round-trip bug in `CacheStore`.

The test is the diagnostic; the fix lives in production code.

### Refactor — clean up

- Extract `_stat_snapshot(root) -> dict[Path, tuple[int, int]]` into the integration `conftest.py` (will be reused by S5-05 when the assertion extends to all six probes).
- Document at the top of the file *why* `os.scandir` is the load-bearing target — because `LanguageDetectionProbe`'s walk is the dominant filesystem activity in Phase 1; if the cache layer fails for it, the rest of the chain falls over.
- Confirm `mypy --strict` clean.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/probes/test_cache_hit_on_real_repo.py` | New file — the test described above. Will be **extended** in S5-05 to cover all six probes. |
| `tests/integration/probes/conftest.py` (if not already created in S2-04) | Shared helpers (`_copy_tree`, `_stat_snapshot`, `_minimal_valid_envelope`). |

## Out of scope

- **Extension to all six probes** — S5-05 (the load-bearing Phase 1 exit criterion #2 in full form).
- **Wall-clock assertion** — S6-02 bench canary (`test_warm_path_latency.py`, advisory).
- **Cache-invalidation-scope test** (sub-schema bump invalidates only that probe's entries) — S3-06 extends `tests/unit/test_cache_invalidation_scope.py` for `node_manifest`'s catalog edits; the broader pattern is Phase 0's gap-#1 resolution.
- **TOCTOU-window test** (mid-gather edit) — S1-08 lands the unit test for the input-snapshot pass; this story is the integration confirmation that no mid-gather edit happens in the canonical fixture path.
- **Adversarial repo with hostile cache state** — Phase 2's adversarial corpus may extend; Phase 1 trusts the cache layer.

## Notes for the implementer

- **The monkeypatch target name is the load-bearing detail.** Read the module docstring at the top of `src/codegenie/probes/language_detection.py` (set in S2-01's refactor step). It says either "patch `codegenie.probes.language_detection.os.scandir`" or "patch `codegenie.probes.language_detection.scandir`" depending on the import style. If the docstring is missing, patch S2-01 first; don't guess. Phase 0's bullet-tracer story (`docs/phases/00-bullet-tracer-foundations/stories/S4-04-fixtures-smoke-cache-hit.md` §"Notes for the implementer") establishes the same rule.
- **The `_stat_snapshot` invariant assertion is non-optional.** Without it, a flaky filesystem (e.g., a touchy `.git` writing to the fixture between gathers) would make the second-run assertion meaningless. Catch the drift loudly and refuse to continue.
- **The redundant structlog assertion is the diagnostic.** If `counter["n"] == 0` passes but `probe.cache_hit` is missing, the monkeypatch target probably moved to a name that doesn't exist anymore (Python's `monkeypatch.setattr` raises on non-existent attributes — unless you used the string form, which doesn't always; pick the attribute form for safety). Either way, the structlog assertion catches it.
- **Don't add a `time.sleep()` between gathers.** mtime-based cache keys are TOCTOU-safe via S1-08's content-hash snapshot (Gap 1 resolution); the cache key derives from `content_hash`, not live `os.stat`. The `_stat_snapshot` check is belt-and-suspenders.
- **Don't capture structlog events across both gathers.** Clear `structlog_capture` after the first gather (or assert only on events emitted after the clear). Otherwise the first-run `probe.cache_miss` events will be in the stream and you'll have to filter by gather ordinal — fragile.
- **`gather_in_process` cwd matters.** The Phase 0 entry point treats `cwd` as the repo root resolution; passing `cwd=repo` is what makes `.codegenie/context/` land inside the fixture copy.
- **S5-05 will extend this file**, not rewrite it. Structure the test so adding four more probes to the cache-hit assertion is a one-line edit (extending the `hit_probes >= {…}` set).
