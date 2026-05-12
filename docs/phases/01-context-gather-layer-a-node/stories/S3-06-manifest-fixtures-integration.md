# Story S3-06 — Manifest fixtures + integration tests + catalog-invalidation scope test

**Step:** Step 3 — Ship `NodeManifestProbe` and the three lockfile parsers
**Status:** Ready
**Effort:** M
**Depends on:** S3-05 (`NodeManifestProbe` on disk)
**ADRs honored:** ADR-0006 (catalog versioning + cache invalidation scope), ADR-0003 (yarn parity exercised via both code paths on the legacy fixture)

## Context

S3-05 ships `NodeManifestProbe`'s code; this story ships the **portfolio + end-to-end evidence** that the probe behaves as designed against realistic Node repos. Three concrete proofs:

1. **`node_pnpm_native/`** — a pnpm-locked repo declaring `bcrypt` + `sharp` (both in the seed native-module catalog). The integration test asserts the catalog cross-reference produces `native_modules.detected == True` with both entries flagged `requires_node_gyp: true`. This is the **closest proxy to a Phase 7 distroless input** the Phase 1 portfolio carries.
2. **`node_yarn_legacy/`** — a yarn-classic repo with `yarn.lock`. The integration test runs `NodeManifestProbe` once with `_HAS_PYARN` left alone and once with it monkeypatched to `False`, asserting both produce **identical** `manifests` slices. This is the production-time evidence backing ADR-0003's "Reversibility: high" claim.
3. **Catalog-invalidation scope** — editing `native_modules.yaml` invalidates **only** `node_manifest` cache entries. Other probes' caches stay warm. This pins ADR-0006's promised invariant; without this test the cache-invalidation scope is documentation, not code.
4. **Raw-artifact budget exercise** — a synthetic 30 MB `pnpm-lock.yaml` triggers truncation at 25 MB with the `probe.raw_artifact.truncated` event. This is the **first realistic exercise** of S1-09's mechanism on a real probe.

This is the densest Step 3 integration-PR; it's the test-and-fixture mirror of S3-05's implementation.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #4 NodeManifestProbe` — interface this story validates.
  - `../phase-arch-design.md §"Component design" #9 Lockfile parsers` — yarn dual-path behavior.
  - `../phase-arch-design.md §"Edge cases"` rows 3, 8 — multi-lockfile, catalog gap.
  - `../phase-arch-design.md §"Gap analysis" Gap 2` — raw-artifact budget; this story is the first real probe exercising the 25 MB override.
- **Phase ADRs:**
  - `../ADRs/0006-native-module-catalog-versioning.md` — cache-invalidation scope; **this story's load-bearing test**.
  - `../ADRs/0003-yarn-lock-parser-choice.md` — both code paths must produce identical output on the yarn-legacy fixture.
- **Source design:**
  - `../final-design.md §"Risks"` #1 — silent catalog staleness; this story is the structural mitigation's CI evidence.
  - `../High-level-impl.md §"Step 3"` — fixtures + integration tests + invalidation-scope test.
- **Existing code:**
  - `src/codegenie/probes/node_manifest.py` (S3-05).
  - `src/codegenie/probes/_lockfiles/_yarn.py` (S3-03, including `_HAS_PYARN`).
  - `src/codegenie/coordinator/coordinator.py` — `gather()` entry point; raw-artifact write path from S1-09.
  - `tests/unit/test_cache_invalidation_scope.py` — base file from Phase 0; this story **extends** it (additive new test functions; doesn't edit existing).
  - `tests/fixtures/node_typescript_helm/` — S2-03 reference for fixture shape.

## Goal

Land two new fixtures (`node_pnpm_native/`, `node_yarn_legacy/`), three integration tests, and the catalog-invalidation-scope unit-test extension so `NodeManifestProbe`'s behavior is verified end-to-end with realistic inputs and ADR-0006's cache-scope claim has CI evidence.

## Acceptance criteria

- [ ] `tests/fixtures/node_pnpm_native/` exists with:
  - `package.json` declaring `bcrypt`, `sharp` in `dependencies` (and at least one non-native dep for control).
  - A valid `pnpm-lock.yaml` resolving `bcrypt@5.x.x` and `sharp@0.32+` (use real-shaped versions; can be synthesized from `pnpm install --lockfile-only` in a scratch repo).
  - A `README.md` documenting what this fixture exercises (native-module catalog cross-reference; both `requires_node_gyp: true` entries).
- [ ] `tests/fixtures/node_yarn_legacy/` exists with:
  - `package.json` (declaring at least one dep so `yarn.lock` is non-empty).
  - A valid `yarn.lock` (yarn classic v1 format).
  - A `README.md` documenting the parity-exercise purpose.
- [ ] `tests/integration/probes/test_node_manifest_pnpm_native.py` runs `codegenie gather` against `node_pnpm_native/` and asserts:
  - `manifests.primary.native_modules.detected is True`.
  - `packages` contains entries for both `bcrypt` and `sharp`.
  - Each native-module hit has `requires_node_gyp: true` (matches catalog).
  - `manifests.catalog_version` is a positive integer (matches `NATIVE_MODULES_CATALOG_VERSION`).
  - `confidence == "high"` (no warnings; single pnpm lockfile).
- [ ] `tests/integration/probes/test_node_manifest_yarn_legacy.py` runs `codegenie gather` against `node_yarn_legacy/` **twice**:
  - Once with `_HAS_PYARN` left to its computed value (whatever the install state is).
  - Once with `monkeypatch.setattr("codegenie.probes._lockfiles._yarn._HAS_PYARN", False)` forcing the hand-rolled path.
  - Asserts the two `manifests` slices are byte-equal (post-deterministic serialization).
  - Skips the `_HAS_PYARN=True` case if `pyarn` isn't installed (with a clear skip reason), but **never skips the hand-rolled case**.
- [ ] `tests/unit/test_cache_invalidation_scope.py` is extended (additively) with:
  - A test that gathers a fixture, edits `src/codegenie/catalogs/native_modules.yaml` (in a temp-copy of the source tree to keep the test hermetic), and re-gathers; asserts `node_manifest` reports a cache miss while at least one other Phase 0 / Phase 1 probe (e.g., `ci`, `deployment`, `test_inventory`) reports a cache hit on the second run.
  - Note: the edit must change the file bytes meaningfully (e.g., bump `catalog_version` by 1) so `(path, size)` cache-key derivation observes the change.
- [ ] `tests/integration/probes/test_node_manifest_raw_artifact_budget.py` (or co-located in S3-05's test file — implementer's choice) exercises:
  - A synthetic 30 MB `pnpm-lock.yaml` fixture (generated at test setup, not checked in) parsed under `NodeManifestProbe`.
  - The raw artifact under `.codegenie/context/raw/node_manifest.json` is truncated at 25 MB (with a marker per S1-09's contract).
  - A `probe.raw_artifact.truncated` event is emitted with the original byte count.
- [ ] All four tests pass on Python 3.11 and 3.12 in CI.
- [ ] No fixture file is larger than 10 MB checked-in (the 30 MB synthetic fixture is generated at test setup).
- [ ] `ruff`, `mypy --strict`, full test suite all pass.

## Implementation outline

1. **Generate the fixtures**:
   - For `node_pnpm_native/`: create a real `package.json` with `bcrypt`, `sharp`, plus a small non-native dep (e.g., `lodash`). Run `pnpm install --lockfile-only` in a scratch directory; copy the resulting `pnpm-lock.yaml` into the fixture. Sanity-check the lockfile parses with `_pnpm.parse(...)`.
   - For `node_yarn_legacy/`: same shape with `yarn install --no-progress`. Verify it parses with `_yarn._parse_handrolled` and (if installed) `pyarn.parse`. The parity tests in S3-04 may already use a corpus-fixture; co-locate if the shapes overlap, but **don't** alias.
2. **Write the integration tests** under `tests/integration/probes/`, importing the CLI entry-point (`codegenie.cli.main`) and invoking against the fixture's path. Use `tmp_path` to redirect `.codegenie/` outputs.
3. **Write the parity integration test** using `monkeypatch.setattr` to force the hand-rolled path. The skip condition is `not _yarn._HAS_PYARN` for the `pyarn` arm only.
4. **Extend `test_cache_invalidation_scope.py`** — copy the fixture into `tmp_path`, copy `native_modules.yaml` into a temp catalog location, monkeypatch the catalog loader's path, gather twice (with a catalog-bump between), assert per-probe cache hit/miss.
5. **Write the raw-artifact-budget test** — generate the synthetic 30 MB lockfile in `tmp_path`, run the probe, assert truncation marker presence + event emission. Use a structlog event capture (the convention from S2-04).

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/probes/test_node_manifest_pnpm_native.py`.

```python
# tests/integration/probes/test_node_manifest_pnpm_native.py
from pathlib import Path
import shutil
import pytest
import yaml

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "node_pnpm_native"


@pytest.mark.asyncio
async def test_pnpm_native_modules_detected(tmp_path: Path):
    # arrange: copy fixture into hermetic tmp_path
    repo = tmp_path / "repo"
    shutil.copytree(FIXTURE, repo)
    from codegenie.cli import gather as cli_gather

    # act: run the CLI entry point against the copied fixture
    await cli_gather(repo, output_dir=repo / ".codegenie")

    # assert: repo-context.yaml contains the expected manifests slice
    ctx_path = repo / ".codegenie" / "context" / "repo-context.yaml"
    ctx = yaml.safe_load(ctx_path.read_text())
    manifests = ctx["probes"]["node_manifest"]["primary"]
    assert manifests["native_modules"]["detected"] is True
    names = {pkg["name"] for pkg in manifests["native_modules"]["packages"]}
    assert {"bcrypt", "sharp"} <= names
    for pkg in manifests["native_modules"]["packages"]:
        if pkg["name"] in {"bcrypt", "sharp"}:
            assert pkg["requires_node_gyp"] is True
    assert ctx["probes"]["node_manifest"]["catalog_version"] >= 1
```

Mirror tests for `test_node_manifest_yarn_legacy.py` and the invalidation-scope extension. Commit red.

### Green — make it pass

1. Land the fixtures with real lockfile content.
2. The probe code from S3-05 should already pass these tests if the cross-reference logic is correct — if not, surface the gap in this PR as a callout: "S3-05 didn't cover the X case; fixed here."
3. The catalog-invalidation-scope test requires care: copying the live `native_modules.yaml` source into `tmp_path` and pointing the catalog loader at the copy means temporarily diverging from the production import-time-load model. Acceptable strategies:
   - Monkeypatch `codegenie.catalogs.__init__._load_catalogs` to read from a `tmp_path` location.
   - Provide a `CATALOG_DIR` environment-variable override on the loader (would require a small additive edit to S1-05; surface in PR).
   - Pick whichever is less invasive; document the choice in the PR body.

### Refactor

- The integration tests share a "copy fixture → tmp_path → run CLI → read repo-context.yaml" pattern. Extract a `_run_gather_on_fixture(fixture: Path, tmp_path: Path) -> dict` helper in `tests/integration/conftest.py` if it appears in ≥ 2 tests; otherwise inline.
- The synthetic 30 MB lockfile generator belongs in a helper next to its test — not in `conftest.py` (it's used exactly once).
- Per the cross-cutting convention, structlog event assertions should be assertions of **count**, not just presence; the raw-artifact-truncated test asserts exactly one truncation event.

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/node_pnpm_native/package.json` | New — real `bcrypt` + `sharp` declarations. |
| `tests/fixtures/node_pnpm_native/pnpm-lock.yaml` | New — pnpm-generated lockfile resolving both natives. |
| `tests/fixtures/node_pnpm_native/README.md` | New — what the fixture exercises. |
| `tests/fixtures/node_yarn_legacy/package.json` | New — at least one dep declared. |
| `tests/fixtures/node_yarn_legacy/yarn.lock` | New — yarn classic v1 format. |
| `tests/fixtures/node_yarn_legacy/README.md` | New — what the fixture exercises (parity proof). |
| `tests/integration/probes/test_node_manifest_pnpm_native.py` | New — pnpm + native modules detected. |
| `tests/integration/probes/test_node_manifest_yarn_legacy.py` | New — `_HAS_PYARN` True vs. False parity. |
| `tests/integration/probes/test_node_manifest_raw_artifact_budget.py` | New — 30 MB synthetic lockfile → truncation at 25 MB. |
| `tests/unit/test_cache_invalidation_scope.py` | Edit (additive) — catalog-edit-invalidates-only-`node_manifest` test. |

## Out of scope

- **End-to-end Layer A integration test** (`test_layer_a_end_to_end.py`) — S5-05; uses `node_typescript_helm` not these fixtures.
- **`node_monorepo_turbo/` and `non_node_go/` fixtures** — S5-04.
- **Adversarial lockfile fixtures (regex-DoS, billion-laughs, oversized)** — S5-01, S5-02 under `tests/adv/`.
- **Yarn-corpus parity fixtures** — S3-04 owns `tests/fixtures/_yarn_corpus/`; this story owns `tests/fixtures/node_yarn_legacy/`. The two are not the same: corpus is for parser-level tests; this fixture is for probe-level integration.
- **`bun.lockb` fixture** — bun is out of scope per S3-05.
- **`pyarn` install-state verification in CI matrix** — S3-03's PR-body checklist; this story assumes it's in place.

## Notes for the implementer

- **Real lockfiles, not handcrafted ones.** Generate `pnpm-lock.yaml` via `pnpm install --lockfile-only` and `yarn.lock` via `yarn install --no-progress` so the fixtures track real-world lockfile shapes. Synthesized lockfiles can pass unit tests but mask production bugs.
- The `node_pnpm_native/package.json` should pin specific versions (`"bcrypt": "5.1.1"`, `"sharp": "0.32.6"`) rather than ranges (`"^5.1.0"`) so the test assertions stay stable across re-installs.
- The catalog-invalidation-scope test is **the load-bearing CI evidence for ADR-0006**. If you can't make it hermetic (e.g., the catalog loader has a module-level import-time load that can't be redirected), surface that in this PR's body as a blocker requiring an S1-05 amendment — don't skip the test.
- For the `_HAS_PYARN` parity integration test, if `pyarn` isn't in the CI matrix's `gather` extras, the `_HAS_PYARN=True` arm skips silently. **Verify the matrix** during PR review — at least one job must install `gather` extras so the parity arm exercises. Surface skip rate in PR body.
- The raw-artifact-budget test uses the synthetic-fixture pattern (generate-at-setup, not check-in) per `High-level-impl.md §"Implementation-level risks"` mention of CI disk budgets. The lockfile must be **structurally parseable** at 30 MB (so the budget code runs); just pad it with valid YAML repetition (`packages:\n  /pkg-N: {}\n` × N).
- ADR-0006 explicitly mentions the "two same-size YAML edits won't invalidate" Phase 1 limitation (final-design Risk #4). The catalog-bump in the invalidation test must change size (not just contents) — easiest is incrementing `catalog_version` from `1` to `10` or appending a new entry; document the chosen edit in the test docstring.
- `bcrypt` and `sharp` are the natural fixture choices because both are in the 10-entry seed catalog (S1-05). Using `keytar` or `node-canvas` would also work but `bcrypt` + `sharp` are the most-installed npm natives and the most likely Phase 7 inputs.
- This PR is the **first end-to-end Phase 1 evidence on a multi-probe gather**. If `LanguageDetectionProbe` or `NodeBuildSystemProbe` produces unexpected output on either fixture (e.g., wrong `framework_hints`), surface as a callout — Step 5's end-to-end test (S5-05) is too late to discover Phase-1-wide issues.
- Per cross-cutting convention #6, per-probe coverage for `node_manifest` is reported in this PR's body — the fixtures here are what drives that number up from S3-05's baseline.
