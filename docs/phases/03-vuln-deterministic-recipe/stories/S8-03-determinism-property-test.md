# Story S8-03 — Determinism property test (Hypothesis, 100 runs)

**Step:** Step 8 — Fixture portfolio, golden files, determinism property, adversarial tests
**Status:** Ready
**Effort:** M
**Depends on:** S8-01, S8-02
**ADRs honored:** ADR-0008 (this is *the* test that verifies the deterministic-serial-fallback decision — hedged-race would fail this property by construction; cache key must include `vuln_index.digest`, asserted indirectly by varying the digest in the input grid and observing different outputs), ADR-0010 (the input tuple is composed of `BlobDigest`, `CveId`, `WorkflowId`, etc. newtypes — never raw `str` — and `transform.diff_bytes` is byte-compared via `TransformId = blake3(diff_bytes)` newtype equality), ADR-0001 (the property is asserted against `Transform.diff_bytes` exposed via `RemediationOrchestrator.run(...).transform_id` — the Phase-5-named surface; if Phase 5's `GateRunner` ever changes the surface, this test breaks before Phase 5 lands)

## Context

Goal G4 ("determinism over probabilism for structural changes") is the cardinal Phase 3 commitment — production `design.md §2.4` is veto-strength on this point. ADR-0008 records the architectural choice (deterministic serial fallback, not hedged race) and the cache-key shape (`blake3(... || vuln_index.digest)`) that make G4 *possible*; this story is what makes G4 *verified*. Without a property test, "deterministic" is an aspiration; with one, it's a CI gate.

The property is: **for all `(repo_snapshot_sha, cve_record_digest, plugin_version, recipe_version, vuln_index_digest)`, `apply_transform(...)` produces byte-identical `transform.diff_bytes` across 100 runs.** The Hypothesis strategy draws each tuple element from a discrete grid (the fixture portfolio S8-01 ships) rather than from a continuous random space — we're not fuzzing the inputs; we're sampling repeatable input combinations and asserting determinism. The 100-run count is the headline number in `phase-arch-design.md §Testing strategy §Property tests`; Hypothesis's default `max_examples=100` matches.

**Offline-only is non-negotiable.** Implementation-risk #2 in `High-level-impl.md` is explicit: "Determinism property test flakiness from npm registry drift. Mitigation: every fixture pins exact `package-lock.json` versions; the property test runs with `npm install --prefer-offline --offline` against a pre-warmed cache committed to the repo (not the live registry)." This story ships the pre-warmed `.npm-cache/` tarball as a test fixture and sets `npm_config_cache=<tarball-extracted-path>` on the jailed environment. If the cache miss path is ever taken, the property test fails loudly with a diagnostic event, not silently re-resolves over the network.

Hypothesis is already a Phase-allowed test dependency (Phase 1's `tests/property/` tests use it). This story adds the property file under `tests/property/test_transform_determinism.py`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals G4` — "same inputs → same Transform bytes; replay produces identical outputs"; the headline cardinal commitment.
  - `../phase-arch-design.md §Testing strategy §Property tests` — "Determinism property (the headline): … byte-identical `transform.diff_bytes` across 100 runs. Hypothesis-strategy generators draw randomized inputs from a fixture grid."
  - `../phase-arch-design.md §Component design C7` — `BundleBuilder` cache-key shape including `vuln_index.digest`; the test indirectly verifies the cache key honors the digest by varying it in the input grid.
  - `../phase-arch-design.md §Component design C4` — `Transform.transform_id = blake3(diff_bytes)`; byte-equal `diff_bytes` ⇒ equal `transform_id`; the test can compare either.
  - `../phase-arch-design.md §Implementation-level risks #2` — registry drift mitigation via pre-warmed cache.
- **Phase ADRs:**
  - `../ADRs/0008-bundlebuilder-deterministic-serial-fallback-and-vuln-index-digest-cache-key.md` — the architectural reason hedged-race was rejected; the property test is the executable form of the "Reversibility: low" claim in that ADR.
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` — `BlobDigest`, `CveId`, `WorkflowId` newtypes for the input tuple.
  - `../ADRs/0001-ship-phase5-contract-surface-by-name.md` — the property test consumes `RemediationOrchestrator.run` and `Transform.diff_bytes` — the Phase-5-stable surface.
- **Existing code:**
  - `tests/property/` — Phase 1/2 Hypothesis tests demonstrating the conventions (`@given(...)`, `settings(deadline=...)`); mirror the structure.
  - `tests/fixtures/repos/` (S8-01) — the input substrate the strategy samples from.
  - `src/codegenie/transforms/orchestrator.py` (S6-04) — the `RemediationOrchestrator` whose `run` method is invoked.
  - `src/codegenie/plugins/bundle.py` (S3-04) — the `BundleBuilder` whose cache key the test indirectly exercises via the `vuln_index_digest` input dimension.
  - `pyproject.toml` — confirm `hypothesis` is in `[project.optional-dependencies] dev`; if not, this story adds it.
- **High-level impl:**
  - `../High-level-impl.md §Step 8 §Done criteria` — "`pytest tests/property/test_transform_determinism.py --hypothesis-seed=0` produces identical `diff_bytes` across all 100 runs (cardinal Goal G4)."
  - `../High-level-impl.md §Implementation-level risks #2` — registry-drift mitigation; mandates pre-warmed cache.

## Goal

Land `tests/property/test_transform_determinism.py` with a Hypothesis-driven property over `(repo_snapshot_sha, cve_record_digest, plugin_version, recipe_version, vuln_index_digest)` that asserts byte-identical `Transform.diff_bytes` across 100 runs **offline-only** via a pre-warmed npm cache, and a paired test asserting that *varying* the `vuln_index_digest` produces different outputs (proving the cache key honors the digest per ADR-0008).

## Acceptance criteria

- [ ] `tests/property/test_transform_determinism.py` exists; collected by pytest; runs in CI on every PR.
- [ ] The test uses `@hypothesis.given(input_tuple_strategy)` where `input_tuple_strategy` draws a 5-tuple from discrete `hypothesis.strategies.sampled_from(...)` strategies — NOT from `text()`/`integers()` (we don't fuzz; we sample the fixture grid).
- [ ] `settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])` — 100 runs, no per-example deadline (each run is a real workflow), explicitly suppress `too_slow` (the budget is the bench harness's job, not Hypothesis').
- [ ] The property body: for each `(repo_sha, cve_digest, plugin_ver, recipe_ver, vuln_digest)` tuple, run `RemediationOrchestrator.run(...)` **twice** with identical inputs and assert `transform.diff_bytes == transform.diff_bytes` (byte-equal). Hypothesis × 100 examples × 2 runs = up to 200 workflow executions; the test takes ≤ 5 minutes on CI (the in-process workflow against a warm cache is ~3 s).
- [ ] A **paired** non-property test `test_vuln_index_digest_is_part_of_cache_key` asserts that when `vuln_index.digest()` returns a different `BlobDigest` (test seeds the sqlite with one extra row to bump the digest), the *same* `(repo, cve, plugin, recipe)` produces a **different** `transform.diff_bytes`. This is the ADR-0008 cache-key invariant in executable form.
- [ ] The test runs **offline-only**: a session-scoped fixture extracts `tests/fixtures/npm-cache.tar.zst` into `tmp_path / "npm-cache"`, sets `npm_config_cache=<that path>`, and the `SubprocessJail.run(...)` invocation uses `npm install --prefer-offline --offline --ignore-scripts`. If `--offline` ever falls through to a network lookup, npm exits non-zero — the test fails loudly.
- [ ] The pre-warmed cache tarball `tests/fixtures/npm-cache.tar.zst` is checked into the repo; size ≤ 4 MiB (compressed); a `tests/fixtures/test_npm_cache_size.py` fence asserts the size cap.
- [ ] The Hypothesis input grid covers AT LEAST the 5 CVE-carrying fixtures from S8-01 in the `repo_snapshot_sha` dimension: `express-cve-2024-21501`, `monorepo-workspaces`, `transitive-only-cve`, `major-bump-required`, `breaking-test-suite`. The `plugin_version` and `recipe_version` dimensions are pinned to the current shipped versions (one element each); the `vuln_index_digest` dimension is pinned to one digest (the property is per-digest determinism, not cross-digest invariance).
- [ ] Repeat-runs are **isolated**: each example uses a fresh `tmp_path` so workflow side effects (branch creation, `.codegenie/` writes) do not pollute the next example.
- [ ] On failure, the assertion message includes the input tuple, the two `transform_id` BLAKE3 digests, and the byte-diff offset of the first divergence — diagnostic enough to identify the source of non-determinism without re-running.
- [ ] `pytest tests/property/test_transform_determinism.py --hypothesis-seed=0` is deterministic across runs (the strategy uses `sampled_from`, not `random`); committing `--hypothesis-seed=0` to CI is sufficient.
- [ ] `make check` clean; `mypy --strict` clean on the new test file.
- [ ] TDD plan's red test exists, committed, green.

## Implementation outline

1. Add `tests/fixtures/npm-cache.tar.zst` (one-time author task: run `npm install --prefer-offline` against each of the 5 CVE fixtures with `npm_config_cache=tmp` then `tar -I 'zstd -19' -cf npm-cache.tar.zst tmp/`); commit. Cap at 4 MiB or split.
2. Add `tests/conftest.py` session-scoped fixture `prewarmed_npm_cache(tmp_path_factory)` that extracts the tarball once per session and returns the path.
3. Write the Hypothesis strategy:
   ```python
   from hypothesis import strategies as st

   _REPO_FIXTURES = ("express-cve-2024-21501", "monorepo-workspaces", "transitive-only-cve", "major-bump-required", "breaking-test-suite")
   _CVE_IDS = {"express-cve-2024-21501": "CVE-2024-21501", ...}  # one per fixture
   _PLUGIN_VERSIONS = ("1.0.0",)
   _RECIPE_VERSIONS = ("1.0.0",)

   input_tuple_strategy = st.tuples(
       st.sampled_from(_REPO_FIXTURES),
       st.sampled_from(_PLUGIN_VERSIONS),
       st.sampled_from(_RECIPE_VERSIONS),
   )
   ```
4. Write the property:
   ```python
   @given(input_tuple_strategy)
   @settings(max_examples=100, deadline=None, ...)
   def test_transform_diff_bytes_deterministic(t, prewarmed_npm_cache, tmp_path_factory):
       run_a = _run_workflow(t, prewarmed_npm_cache, tmp_path_factory.mktemp("a"))
       run_b = _run_workflow(t, prewarmed_npm_cache, tmp_path_factory.mktemp("b"))
       assert run_a.transform.diff_bytes == run_b.transform.diff_bytes, _diff_diagnostic(run_a, run_b, t)
   ```
5. Write the paired cache-key test: seed the `VulnIndex` sqlite with one extra (irrelevant) row, run the workflow, compare against a baseline; assert `diff_bytes` differs (proving `vuln_index.digest` is part of the cache key per ADR-0008).
6. Write `_diff_diagnostic(run_a, run_b, t) -> str` returning a multi-line message naming the input tuple, both BLAKE3 transform IDs, and the byte offset of the first divergence.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/property/test_transform_determinism.py`

```python
from __future__ import annotations
import shutil
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from codegenie.transforms.orchestrator import RemediationOrchestrator
from codegenie.types.identifiers import CveId

_REPO_FIXTURES: tuple[str, ...] = (
    "express-cve-2024-21501",
    "monorepo-workspaces",
    "transitive-only-cve",
    "major-bump-required",
    "breaking-test-suite",
)
_CVE_BY_FIXTURE = {
    "express-cve-2024-21501": "CVE-2024-21501",
    # ... seeded by the implementer from S8-01 README.fixture.md files
}

@given(st.sampled_from(_REPO_FIXTURES))
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_transform_diff_bytes_deterministic(fixture_name, prewarmed_npm_cache, tmp_path_factory):
    """Goal G4 — same inputs → same Transform bytes. ADR-0008 / property test cardinal."""
    cve = CveId(_CVE_BY_FIXTURE[fixture_name])
    run_a_dir = tmp_path_factory.mktemp("a")
    run_b_dir = tmp_path_factory.mktemp("b")
    src = Path(__file__).parent.parent / "fixtures" / "repos" / fixture_name
    shutil.copytree(src, run_a_dir / "repo")
    shutil.copytree(src, run_b_dir / "repo")

    a = _run_workflow(run_a_dir / "repo", cve, prewarmed_npm_cache)
    b = _run_workflow(run_b_dir / "repo", cve, prewarmed_npm_cache)

    assert a.transform.diff_bytes == b.transform.diff_bytes, (
        f"non-determinism on {fixture_name} / {cve}: "
        f"transform_id_a={a.transform.transform_id} transform_id_b={b.transform.transform_id}"
    )


def test_vuln_index_digest_is_part_of_cache_key(tmp_path, prewarmed_npm_cache, seeded_vuln_index):
    """ADR-0008 — vuln_index.digest is part of the Bundle cache key; a different digest must produce a different transform."""
    # ... seed sqlite with one extra irrelevant row, re-run workflow, assert diff_bytes differs
```

State why it fails: `prewarmed_npm_cache` fixture doesn't exist; `seeded_vuln_index` fixture doesn't exist; the `_run_workflow` helper isn't written; `tests/fixtures/npm-cache.tar.zst` isn't committed.

### Green — minimal pass

- Commit `tests/fixtures/npm-cache.tar.zst` (≤ 4 MiB).
- Add `prewarmed_npm_cache` and `seeded_vuln_index` fixtures to `tests/conftest.py`.
- Write `_run_workflow(repo, cve, cache) -> RemediationOutcome` helper that instantiates `RemediationOrchestrator` with an offline-jail config (`SubprocessJail` env carries `npm_config_cache=<cache>`, `npm_config_offline=true`) and invokes `run`.
- Run with `--hypothesis-seed=0`; expect 100 examples × 2 runs each, all passing.

### Refactor

- Add the paired `test_vuln_index_digest_is_part_of_cache_key` test (one example, not Hypothesis).
- Add the diff-diagnostic helper producing the byte-offset-of-divergence message.
- Add a CI-only marker `@pytest.mark.slow` to opt this test out of the default `pytest -q` invocation if it's prohibitively slow during local dev (mark `tests/property/test_transform_determinism.py` and document the marker in `pyproject.toml`'s `[tool.pytest.ini_options].markers`).
- Edge cases from §Edge cases that this code touches: E18 (degraded adapter — if `stale-scip` is added to the fixture grid, the property must still hold across runs that take the degraded path); E11 (cve_delta — orthogonal but the test should not include fixtures that produce `cve_delta_introduced` in this property, since those don't produce a `Transform` at all).

## Files to touch

| Path | Why |
|---|---|
| `tests/property/test_transform_determinism.py` | NEW — the Hypothesis property + the paired cache-key test. |
| `tests/fixtures/npm-cache.tar.zst` | NEW — pre-warmed offline npm cache (≤ 4 MiB compressed). |
| `tests/fixtures/test_npm_cache_size.py` | NEW — fence asserting the cache tarball stays ≤ 4 MiB. |
| `tests/conftest.py` (extend) | Add `prewarmed_npm_cache` session fixture; add `seeded_vuln_index` fixture. |
| `pyproject.toml` (verify) | Confirm `hypothesis` in `dev` deps; add `slow` marker definition if not present. |

## Out of scope

- **Fuzzing the inputs** with random strings/bytes — this is a *sampled grid*, not a fuzz test. Random inputs would mostly produce uninteresting `RecipeOutcome.NotApplicable` returns and waste runtime; the value is in repeating real fixture inputs.
- **Cross-fixture determinism** (asserting `express-cve-2024-21501.diff_bytes != monorepo-workspaces.diff_bytes`) — obvious from the inputs; not interesting to test.
- **Determinism across plugin/recipe version *changes*** — by design, a recipe version bump must change the output, otherwise versioning is meaningless. The property is per-version determinism, not cross-version invariance.
- **Network-online mode** — explicitly out of scope; ADR-0008's Reversibility note pins offline+pre-warmed-cache as the only mode for this test.
- **Performance budget for the property test** — S9-03 owns bench budgets; this story's only timing constraint is "≤ 5 minutes on CI" for the whole property.
- **`vuln_index.digest` *content* changes** beyond the paired cache-key test — Phase 4+ will likely add more granular invariants.

## Notes for the implementer

- **`sampled_from` over `text()`.** The grid IS the input space. Hypothesis is here for the bookkeeping (100 examples, shrinking on failure to a minimal reproducer), not for random generation. Using `text()` would draw nonsense fixture names that don't exist and produce `FileNotFoundError`, not a determinism violation.
- **`deadline=None` is non-negotiable.** A 3-second workflow run with Hypothesis' default 200 ms deadline produces immediate `Flaky` failures. The bench harness (S9-03) owns timing; this test owns correctness.
- **Pre-warmed cache must be regenerable.** Document the recipe in the test's module docstring: `python tooling/scripts/warm_npm_cache.py tests/fixtures/repos --out tests/fixtures/npm-cache.tar.zst` (whether or not that script exists today — Step 9 may ship it). Without a regen path, a transitive-dep bump means hand-rebuilding the cache.
- **`--offline` must fail loudly.** If `npm install --offline` ever falls through to a network call (it shouldn't, but bugs happen), npm exits with a clear error like `ENOTCACHED: request was forced offline`. Let it propagate; do not catch + skip.
- **The cache-key invariant test is the *companion* test, not the property.** Resist the urge to make `vuln_index.digest` a Hypothesis dimension — varying it across 100 examples would re-resolve every time and explode the runtime. One paired test is enough.
- **The byte-diff offset diagnostic matters more than the property message.** When the property fails 6 months from now, the engineer needs to know *where in `diff_bytes`* the divergence is, not just *that* it diverged. Use `next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), -1)` and quote ±32 bytes around it.
- **Hypothesis seed pinning.** `@settings(...)` does not pin the seed; the CLI flag `--hypothesis-seed=0` does. CI must pass this flag; document it in `tests/property/conftest.py` or `pyproject.toml`'s pytest `addopts` if needed. Without seed pinning, a flaky day-1 failure is unreproducible.
- **`Transform.diff_bytes` is the right comparison surface.** ADR-0008's invariant is over `transform.diff_bytes`, not `transform_id` — they're equivalent (`transform_id = blake3(diff_bytes)`), but byte-comparing the raw bytes preserves the offset diagnostic. Compare bytes, then assert `transform_id` equality as a sanity check.
- **If `_run_workflow` ever has to mock something to make the test pass, the test is wrong.** The property is over the *real* workflow; mocks would mean we're testing the mocks' determinism, not the system's.
