# Story S3-06 — Manifest fixtures + integration tests + catalog-invalidation scope test

**Step:** Step 3 — Ship `NodeManifestProbe` and the three lockfile parsers
**Status:** GREEN — all AC groups 1–6 land green (2026-05-14 attempt 2). The three follow-ups blocking AC group 5 in attempt 1 (B-1 `.codegenie/`-rglob collision; B-2 `os.fstat` vs. `Path.read_bytes()`; B-3 filename mismatch) landed via `declared_inputs_for` `.codegenie/` exclusion, `NodeManifestProbe.raw_artifacts` emission, cli `os.open`+`os.fstat` size pre-check, and `apply_raw_artifact_truncation(original_bytes=...)` extension. AC-9 filename deviation (D-7) is documented in `_attempts/S3-06.md`.
**Effort:** L  *(was M — re-sized after validation: 4 new test files + 1 unit-test extension + 1 new fixture + monkeypatch + spy choreography pushes this past M)*
**Validated:** 2026-05-14 — see `_validation/S3-06-manifest-fixtures-integration.md`
**Depends on:** S3-05 (`NodeManifestProbe` on disk), S3-03 (`_yarn._HAS_PYARN` symbol monkey-patched here), S3-04 (yarn-parity oracle pattern of record reused), S1-05 (catalog loader + `NATIVE_MODULES_CATALOG_VERSION`), S1-09 (`ResourceBudget.raw_artifact_truncate_mb` truncation marker shape)
**ADRs honored:** ADR-0006 (catalog versioning + cache invalidation scope), ADR-0003 (yarn dispatch integrates correctly into the probe slice — *not* parser parity, which S3-04 owns)

## Validation notes (2026-05-14 — phase-story-validator HARDENED)

Six **block-level** corrections applied (see `_validation/S3-06-manifest-fixtures-integration.md` for full audit):

1. **`node_yarn_legacy/` already exists.** Created by S2-02a / S3-03 with `lodash@^4.17.21` + `packageManager: "yarn@1.22.19"` + classic `yarn.lock`. Original AC-2 + Files-to-touch tagged the three files as "**New**" — would have either overwritten upstream working state or failed the AC. Rewritten as **reuse**; only `README.md` is extended additively. Lockfile non-emptiness now pinned by AC.
2. **Catalog-bump test contradicted ADR-0006's `(path, size)` cache key.** Original guidance "bump `catalog_version` by 1" produces `1` → `2` (size unchanged); per ADR-0006 §Tradeoffs row 4, a same-size YAML edit does NOT invalidate. Rewritten: bump `1` → `10` (size +1) OR append a new entry; `assert path.stat().st_size != original_size` BEFORE the second gather (Rule 12 — fail loud).
3. **Invalidation-scope test was "at least one sibling" — survived surgical-flush mutants.** A buggy invalidation that flushed everything except `ci` would have passed. Rewritten as `pytest.parametrize` over **all** Phase 0 + Phase 1 sibling probes; aggregate assertion `{p for p, s in cache_state.items() if s == "miss"} == {"node_manifest"}` pins both directions of the ADR-0006 invariant.
4. **Parity test would pass under silent-fallback mutation.** Byte-equal output is trivially satisfied if both arms use the same parser. Rewritten with `mocker.spy(pyarn, "parse")` and `mocker.spy(_yarn, "_parse_handrolled")` proving the two arms exercise observably-distinct code paths *before* the byte-equal assertion.
5. **Raw-artifact budget test underspecified.** AC didn't pin (a) marker shape (`__truncated_at_budget__: True`, `original_bytes`, `budget_bytes`), (b) "exactly one" event count, (c) truncated artifact remains valid JSON, (d) the synthetic 30 MB lockfile must be **structurally parseable** (else the parse-cap fires before the raw-artifact write). All four are now ACs; truncation event captured via `structlog.testing.capture_logs()` (not `caplog` — burned in S1-07/S1-08/S3-04). The 30 MB fixture is exercised via `os.fstat` monkey-patch per S3-01/S3-02/S3-03/S3-05 pattern of record — NOT a 30 MB tmpfs write (CI disk budget).
6. **CLI invocation drift.** Original Red snippet called `cli_gather` directly, which bypasses `tests/integration/probes/conftest.py`'s `_disable_cli_configure_logging` autouse seam — `capture_logs()` would silently capture zero events (S2-05 burned this). Rewritten to use `CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo)])` per the conftest precedent and to consume `_copy_tree`, `_load_envelope` from `tests/integration/probes/conftest.py` instead of proposing a new helper at a different path.

Five harden-tier additions:

- **H-1 — Multi-lockfile case (Edge case #7) added** as a parametrized variant of the pnpm-native test: drops a stray `yarn.lock` next to `pnpm-lock.yaml`, asserts `confidence == "low"` + `lockfile.multi_present` warning. First end-to-end exercise of the multi-lockfile drop-confidence path.
- **H-2 — Multi-probe end-to-end claim now backed by ACs.** The Notes claim "first end-to-end Phase 1 evidence on multi-probe gather" was previously unbacked. Pnpm-native test now also asserts `language_detection.primary == "javascript"` and `node_build_system.package_manager == "pnpm"` slices.
- **H-3 — Tautology kill on the pnpm sample test.** Previous assertion `{"bcrypt", "sharp"} <= names` would survive a probe that hardcoded those two names. Added `assert "lodash" in names` (the non-native control) and `assert len(names) >= 3` to force-prove the lockfile was actually parsed.
- **H-4 — Catalog-loader redirection strategy pinned.** Original gave two options (monkeypatch `_load_catalogs` private symbol OR amend S1-05 with a `CATALOG_DIR` env var). Per Rule 3 (surgical changes) + extension-by-addition: monkeypatch is the only in-scope strategy. If it can't be made hermetic (catalog loaded once at import time), this story BLOCKS on a separate S1-05 amendment story — does NOT silently widen scope to edit upstream landed work.
- **H-5 — Catalog-invalidation parametrize seam noted for future.** A `CATALOG_INVALIDATION_TARGETS: frozenset[tuple[str, Path]]` (probe_name → catalog_path) seam will be the right shape when CIProbe's `ci_providers.yaml` lands its own invalidation test (Phase 2) and again for Phase 3's replacement catalogs. Recorded in Notes-for-implementer; do NOT extract now (Rule 2 — single application).

Three design-pattern caveats (not applied — Rule 2 / Rule 11 dominates):

- **No `RepoRoot` newtype.** Codebase uses raw `pathlib.Path` (`RepoSnapshot.root: Path`); Rule 11 says match it.
- **No functional-core/imperative-shell split** for the 30 MB lockfile generator (5-line test helper, single use).
- **No `_run_gather_on_fixture`** new helper — `tests/integration/probes/conftest.py` already exposes `_copy_tree` + `_load_envelope` at this exact level. Reuse, don't extend the helper module.

One follow-up surfaced (not in this story's scope):

- **Re-framing of the yarn-legacy parity claim.** S3-04 already lands `tests/unit/probes/_lockfiles/test_yarn_parser_parity.py` with a CI-enforced mutation gate (commit `6f77ff8`) — that, not S3-06, is the load-bearing evidence for ADR-0003 reversibility. S3-06's yarn-legacy test is a **probe-level integration smoke** (proves the dispatcher integrates correctly with `manifests` slice plumbing on yarn-classic), not parser correctness. Context §2 below now reflects this.

No `NEEDS RESEARCH` findings. Stage 3 skipped.

## Context

S3-05 ships `NodeManifestProbe`'s code; this story ships the **portfolio + end-to-end evidence** that the probe behaves as designed against realistic Node repos. Three concrete proofs:

1. **`node_pnpm_native/`** — a pnpm-locked repo declaring `bcrypt` + `sharp` (both in the seed native-module catalog). The integration test asserts the catalog cross-reference produces `native_modules.detected == True` with both entries flagged `requires_node_gyp: true`. This is the **closest proxy to a Phase 7 distroless input** the Phase 1 portfolio carries.
2. **`node_yarn_legacy/`** (already exists from S2-02a / S3-03) — a yarn-classic repo with `yarn.lock`. The integration test runs `NodeManifestProbe` once with `_HAS_PYARN` left alone and once with it monkey-patched to `False`, asserting both produce **identical** `manifests` slices. This is a **probe-level integration smoke** proving the dispatcher integrates correctly with the probe's `manifests` slice plumbing on yarn-classic — *not* parser correctness, which S3-04's `test_yarn_parser_parity.py` (with its CI-enforced mutation gate, commit `6f77ff8`) is the load-bearing evidence for. Mutation-resistant via two mocker spies (per `mocker.spy(pyarn, "parse")` and `mocker.spy(_yarn, "_parse_handrolled")`) that prove the two arms exercised observably-distinct code paths *before* the byte-equal assertion.
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

Land one new fixture (`node_pnpm_native/`), reuse `node_yarn_legacy/`, ship four integration tests + one unit-test extension so `NodeManifestProbe`'s behavior is verified end-to-end with realistic inputs; ADR-0006's cache-scope claim ("only `node_manifest` invalidates on `native_modules.yaml` edit; every sibling stays warm") has CI evidence in **both directions** (under-invalidation AND over-invalidation are caught); S1-09's raw-artifact truncation is exercised on a real probe with marker-shape pinning; and the multi-lockfile drop-confidence path (Edge case #7) gets its first end-to-end exercise.

## Acceptance criteria

### AC group 1 — Fixtures

- [ ] **AC-1: `tests/fixtures/node_pnpm_native/` is NEW** with:
  - `package.json` pinning specific versions (e.g., `"bcrypt": "5.1.1"`, `"sharp": "0.32.6"`, plus a non-native control dep `"lodash": "4.17.21"`) — not ranges (`^5.x.x`), so test assertions stay stable across re-installs.
  - A valid `pnpm-lock.yaml` resolving all three deps (synthesize via `pnpm install --lockfile-only` in a scratch directory; copy result in).
  - `README.md` documenting what this fixture exercises (native-module catalog cross-reference; both `requires_node_gyp: true` entries; `lodash` is the control proving lockfile was actually parsed).
- [ ] **AC-2: `tests/fixtures/node_yarn_legacy/` is REUSED** (already exists from S2-02a / S3-03 with `lodash@^4.17.21` + `packageManager: "yarn@1.22.19"` + classic `yarn.lock`):
  - Do **NOT** overwrite `package.json` or `yarn.lock` — the S2-02a / S3-03 / S3-04 tests depend on the current shape.
  - Append (additively) to `README.md` a paragraph documenting that S3-06's parity integration test also exercises this fixture.
  - Pin in test setup: `assert _yarn._parse_handrolled(fixture / "yarn.lock") != {}` AND (if `_HAS_PYARN`) `assert pyarn.parse(...) != {}` — i.e., the lockfile is **non-empty** for parity to be a meaningful test.

### AC group 2 — Pnpm-native integration test (`tests/integration/probes/test_node_manifest_pnpm_native.py`)

Invocation: `CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo)])` per `tests/integration/probes/conftest.py` precedent. Helpers `_copy_tree` and `_load_envelope` from that conftest are reused (do **not** introduce a new `_run_gather_on_fixture`).

- [ ] **AC-3: Native-modules block correctly populated.**
  - `manifests.primary.native_modules.detected is True`.
  - The set of names in `native_modules.packages` is a **superset** of `{"bcrypt", "sharp"}`. Tautology kill: `assert "lodash" in {pkg["name"] for pkg in manifests.primary.packages}` (the non-native control proves the lockfile was parsed, not a hardcoded native-only constant); `assert len({pkg["name"] for pkg in manifests.primary.packages}) >= 3`.
  - For each entry where `name in {"bcrypt", "sharp"}`: `pkg["requires_node_gyp"] is True`.
  - `manifests.catalog_version == NATIVE_MODULES_CATALOG_VERSION` (import the constant explicitly; not "is positive integer").
  - `confidence == "high"`; `warnings == []`.
- [ ] **AC-4: Multi-probe end-to-end signal pinned** (delivers on the "first end-to-end Phase 1 evidence on multi-probe gather" claim):
  - Same envelope additionally contains a `language_detection` slice with `primary == "javascript"` (or `"typescript"` if the fixture uses TS).
  - Same envelope contains `node_build_system` slice with `package_manager == "pnpm"`.
- [ ] **AC-5: Multi-lockfile case (Edge case #7) — parametrized variant.**
  - `pytest.parametrize("stray_lockfile", [None, "yarn.lock"])`.
  - When `stray_lockfile == "yarn.lock"`: drop a copy of `tests/fixtures/node_yarn_legacy/yarn.lock` into the pnpm-native fixture's tmp_path copy *before* the gather. Assert `confidence == "low"`; `lockfile.multi_present` warning ID present in `warnings`.
  - When `stray_lockfile is None`: original AC-3 behavior (`confidence == "high"`).
  - Mutation killer: a probe that ignored the multi-lockfile signal would pass the `None` arm but fail the `"yarn.lock"` arm.

### AC group 3 — Yarn-legacy parity integration test (`tests/integration/probes/test_node_manifest_yarn_legacy.py`)

Invocation: `CliRunner` per AC-2 setup. **Probe-level integration smoke** — *not* parser correctness (owned by S3-04).

- [ ] **AC-6: Both arms exercise observably-distinct parsers.**
  - **Arm 1** (`_HAS_PYARN=True`, computed): `with mocker.spy(pyarn, "parse") as pyarn_spy, mocker.spy(_yarn, "_parse_handrolled") as hr_spy: <gather>`. Then `assert pyarn_spy.call_count >= 1` AND `assert hr_spy.call_count == 0`. Skip the entire arm with a CLEAR skip reason (`pyarn extra not installed`) if `not _yarn._HAS_PYARN`.
  - **Arm 2** (forced hand-rolled): `monkeypatch.setattr("codegenie.probes._lockfiles._yarn._HAS_PYARN", False)`. Then `with mocker.spy(_yarn, "_parse_handrolled") as hr_spy: <gather>`. `assert hr_spy.call_count >= 1`. **Never skipped** — runs in every CI matrix entry.
  - **Byte-equal assertion** runs only after BOTH arms confirmed observably-distinct: `arm1.manifests_slice_bytes == arm2.manifests_slice_bytes` (post deterministic-serialization).
  - Mutation killer 1: a refactor that aliased both arms to the same parser would fail the spy assertion (the `pyarn_spy.call_count` would mismatch the path expected for each arm).
  - Mutation killer 2: a silent fallback inside `_yarn.parse` (`_HAS_PYARN=True` but actually using hand-rolled) would fail Arm 1's `hr_spy.call_count == 0`.

### AC group 4 — Catalog-invalidation-scope unit-test extension (`tests/unit/test_cache_invalidation_scope.py`)

- [ ] **AC-7: Catalog-edit invalidates `node_manifest` AND ONLY `node_manifest`.**
  - Setup: gather `tests/fixtures/node_pnpm_native/` (in `tmp_path`-copy) once; record per-probe cache state.
  - Edit: redirect catalog loader to a `tmp_path`-copy of `src/codegenie/catalogs/native_modules.yaml`, then **size-changing** edit: bump `catalog_version: 1` → `catalog_version: 10` (size +1 byte) OR append a new entry. Assert size change up front: `assert catalog_path.stat().st_size != original_size, "ADR-0006 (path,size) cache key requires a size change; bump 1→2 is forbidden (same size)"` (Rule 12 — fail loud).
  - Re-gather; capture per-probe cache state.
  - **Both directions** asserted via a single aggregate: `assert {p for p, s in cache_state.items() if s == "miss"} == {"node_manifest"}`. Surgical-flush mutants (e.g., a buggy invalidation that flushed everything except `ci`) are caught.
  - Per-sibling assertions via `pytest.parametrize("sibling", [...])` over **all** Phase 0 + Phase 1 probes registered for the fixture: `language_detection`, `node_build_system`, `ci`, `deployment`, `test_inventory`. Each: `cache_state[sibling] == "hit"`.
  - Loader-redirection strategy: monkey-patch `codegenie.catalogs.__init__._load_catalogs` (the private helper) to read from `tmp_path`. **Do NOT** add a `CATALOG_DIR` env var to S1-05 — that would silently widen S3-06's scope (Rule 3 / extension-by-addition). If the loader is import-time-only and cannot be redirected hermetically, this story BLOCKS on a separate S1-05 amendment story; do not edit S1-05 from here.
  - Companion `xfail`-marked test: a same-size edit (`catalog_version: 1` → `2`) does NOT invalidate. Pins ADR-0006 §Tradeoffs row 4's accepted Phase 1 limitation as a regression-pinned invariant, not just documentation.

### AC group 5 — Raw-artifact-budget integration test (`tests/integration/probes/test_node_manifest_raw_artifact_budget.py`)

- [ ] **AC-8: Synthetic 30 MB lockfile triggers truncation, NOT parse-cap.**
  - Write a small **structurally parseable** `pnpm-lock.yaml` to `tmp_path` (real YAML, not bytes). Verify in test setup: `assert _pnpm.parse(path) is not None` BEFORE running the probe — so the truncation comes from the raw-artifact write path, not from a `SizeCapExceeded` rejection.
  - Use `monkeypatch.setattr(os, "fstat", lambda fd: stat_result(st_size=30*1024*1024, ...))` so the budget code triggers without writing 30 MB to tmpfs (CI disk budget). **Pattern of record:** `_validation/S3-05-node-manifest-probe.md` T-9 + `_validation/S3-01/02/03`. **Do NOT** write 30 MB of real bytes to tmpfs.
- [ ] **AC-9: Truncated artifact has the correct marker shape AND is valid JSON.**
  - `json.loads((repo / ".codegenie/context/raw/node_manifest.json").read_text())` succeeds (parses to dict).
  - `parsed["__truncated_at_budget__"] is True` (boolean, not `1`, not `"True"` — pins the no-coerce mutant).
  - `parsed["original_bytes"] >= 30*1024*1024`.
  - `parsed["budget_bytes"] == 25*1024*1024`.
  - `parsed["original_bytes"] >= parsed["budget_bytes"]` (property — a truncation by definition exceeded budget).
- [ ] **AC-10: Exactly one `probe.raw_artifact.truncated` event** (not `>= 1` — kills loop-bug mutants emitting one event per MB).
  - Capture via `with structlog.testing.capture_logs() as logs: <gather>`. **Not** `caplog` (burned in S1-07 / S1-08 / S3-04).
  - `assert sum(1 for e in logs if e["event"] == "probe.raw_artifact.truncated") == 1`.
  - The captured event has `probe == "node_manifest"`; `original_bytes >= 30*1024*1024`; `budget_bytes == 25*1024*1024`.
  - The autouse `_disable_cli_configure_logging` fixture in `tests/integration/probes/conftest.py` is in scope (the gather runs through `CliRunner` which would otherwise reset structlog's processor chain and silently drop every event).

### AC group 6 — Cross-cutting

- [ ] **AC-11: All five tests pass on Python 3.11 AND 3.12 in CI.** The CI matrix must include at least one job with `gather` extras (so the `_HAS_PYARN=True` arm of AC-6 actually exercises in CI, not just locally). Surface skip rate in PR body.
- [ ] **AC-12: No fixture file > 10 MB checked-in.** The 30 MB synthetic fixture is `os.fstat`-monkey-patched, never written to disk.
- [ ] **AC-13: `ruff`, `mypy --strict`, full test suite all pass.**

## Implementation outline

1. **Generate `node_pnpm_native/`**: create a real `package.json` with `bcrypt`, `sharp`, `lodash` pinned to specific versions. Run `pnpm install --lockfile-only` in a scratch directory; copy the resulting `pnpm-lock.yaml` into the fixture. Sanity-check parse with `_pnpm.parse(...)`.
2. **Reuse `node_yarn_legacy/`** as-is (already on disk from S2-02a / S3-03). Append a paragraph to its `README.md` documenting S3-06's parity-integration use; do NOT touch `package.json` or `yarn.lock`. Sanity-check the existing lockfile parses with `_yarn._parse_handrolled` (and `pyarn.parse` if installed).
3. **Write the integration tests** under `tests/integration/probes/` using `CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo)])` per the established `tests/integration/probes/conftest.py` precedent. Reuse `_copy_tree`, `_load_envelope`, and the autouse `_disable_cli_configure_logging` fixture from that conftest.
4. **Write the parity integration test** using `monkeypatch.setattr("codegenie.probes._lockfiles._yarn._HAS_PYARN", False)` to force the hand-rolled path. Use `mocker.spy(pyarn, "parse")` and `mocker.spy(_yarn, "_parse_handrolled")` to **prove** each arm exercised observably-distinct code paths *before* the byte-equal assertion. Skip the `_HAS_PYARN=True` arm only when `not _yarn._HAS_PYARN`; never skip the hand-rolled arm.
5. **Extend `test_cache_invalidation_scope.py`** — copy `tests/fixtures/node_pnpm_native/` into `tmp_path`; copy `native_modules.yaml` into a `tmp_path` catalog location; monkey-patch `codegenie.catalogs.__init__._load_catalogs` to read from the copy; size-changing catalog bump (`1` → `10` or append entry); assert size change up front; gather twice; aggregate-assert `{p for p, s in cache_state.items() if s == "miss"} == {"node_manifest"}`. Add a parametrized per-sibling assertion AND a companion `xfail` test for the same-size edit (ADR-0006 limitation).
6. **Write the raw-artifact-budget test** — write a small structurally-parseable `pnpm-lock.yaml` to `tmp_path`; verify it parses; monkey-patch `os.fstat` to return `st_size=30*1024*1024` (per S3-05 T-9 pattern); run the probe via `CliRunner` inside `with structlog.testing.capture_logs() as logs:`; assert exactly-one truncation event AND marker-shape ACs; assert the truncated raw artifact loads as JSON with the correct `__truncated_at_budget__` / `original_bytes` / `budget_bytes` keys.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/integration/probes/test_node_manifest_pnpm_native.py`.

```python
# tests/integration/probes/test_node_manifest_pnpm_native.py
from pathlib import Path

import pytest
import structlog
from click.testing import CliRunner

from codegenie.catalogs import NATIVE_MODULES_CATALOG_VERSION
from codegenie.cli import cli
from tests.integration.probes.conftest import _copy_tree, _load_envelope

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "node_pnpm_native"


@pytest.mark.parametrize("stray_lockfile", [None, "yarn.lock"])
def test_pnpm_native_modules_detected(tmp_path: Path, stray_lockfile: str | None) -> None:
    # arrange: copy fixture into hermetic tmp_path
    repo = _copy_tree(FIXTURE, tmp_path / "repo")
    if stray_lockfile == "yarn.lock":
        # Edge case #7 — multi-lockfile: drop a stray yarn.lock alongside pnpm-lock
        legacy = Path(__file__).resolve().parents[2] / "fixtures" / "node_yarn_legacy"
        (repo / "yarn.lock").write_bytes((legacy / "yarn.lock").read_bytes())

    # act: run the CLI entry point against the copied fixture
    result = CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo)])
    assert result.exit_code == 0, result.output

    # assert: repo-context.yaml contains the expected manifests slice
    ctx = _load_envelope(repo)
    nm = ctx["probes"]["node_manifest"]
    primary = nm["primary"]
    names = {pkg["name"] for pkg in primary["native_modules"]["packages"]}

    # AC-3 — native modules detected (multi-probe baseline)
    assert primary["native_modules"]["detected"] is True
    assert {"bcrypt", "sharp"} <= names
    # tautology kill (AC-3): non-native control proves the lockfile was parsed
    assert "lodash" in names
    assert len(names) >= 3
    for pkg in primary["native_modules"]["packages"]:
        if pkg["name"] in {"bcrypt", "sharp"}:
            assert pkg["requires_node_gyp"] is True
    # equality, not "positive int" (AC-3)
    assert nm["catalog_version"] == NATIVE_MODULES_CATALOG_VERSION

    if stray_lockfile is None:
        # AC-3: clean-fixture confidence
        assert nm["confidence"] == "high"
        assert nm.get("warnings", []) == []
    else:
        # AC-5: multi-lockfile drop-confidence path
        assert nm["confidence"] == "low"
        assert "lockfile.multi_present" in nm["warnings"]

    # AC-4: multi-probe end-to-end pinned
    assert ctx["probes"]["language_detection"]["primary"] == "javascript"
    assert ctx["probes"]["node_build_system"]["package_manager"] == "pnpm"
```

Yarn-legacy parity (AC-6 sketch):

```python
# tests/integration/probes/test_node_manifest_yarn_legacy.py
import pytest
from click.testing import CliRunner
from codegenie.cli import cli
from codegenie.probes._lockfiles import _yarn
from tests.integration.probes.conftest import _copy_tree, _load_envelope

FIXTURE = ...  # tests/fixtures/node_yarn_legacy/


@pytest.mark.skipif(not _yarn._HAS_PYARN, reason="pyarn extra not installed")
def test_pyarn_arm_uses_pyarn(tmp_path, mocker):
    import pyarn
    pyarn_spy = mocker.spy(pyarn, "parse")
    hr_spy = mocker.spy(_yarn, "_parse_handrolled")
    repo = _copy_tree(FIXTURE, tmp_path / "repo")
    CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo)])
    assert pyarn_spy.call_count >= 1
    assert hr_spy.call_count == 0  # AC-6 mutation killer 2: no silent fallback


def test_handrolled_arm_uses_handrolled(tmp_path, monkeypatch, mocker):
    monkeypatch.setattr("codegenie.probes._lockfiles._yarn._HAS_PYARN", False)
    hr_spy = mocker.spy(_yarn, "_parse_handrolled")
    repo = _copy_tree(FIXTURE, tmp_path / "repo")
    CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo)])
    assert hr_spy.call_count >= 1


def test_two_arms_produce_byte_equal_manifests(tmp_path):
    # Run twice (once unforced, once forced hand-rolled), capture manifests slice bytes,
    # assert byte-equal AFTER the per-arm spy assertions above have proven distinctness.
    ...
```

Catalog-invalidation-scope extension (AC-7 sketch — appended to `tests/unit/test_cache_invalidation_scope.py`):

```python
@pytest.mark.parametrize(
    "sibling",
    ["language_detection", "node_build_system", "ci", "deployment", "test_inventory"],
)
def test_catalog_edit_invalidates_only_node_manifest(tmp_path, monkeypatch, sibling):
    # ... setup: copy fixture, copy catalog, monkey-patch _load_catalogs
    original_size = catalog_path.stat().st_size
    # ADR-0006 (path,size) cache key — bump must change SIZE, not just bytes
    text = catalog_path.read_text().replace("catalog_version: 1", "catalog_version: 10")
    catalog_path.write_text(text)
    assert catalog_path.stat().st_size != original_size, (
        "ADR-0006 (path,size) cache key requires a size change; "
        "bump 1->2 is forbidden (same byte count)"
    )
    # gather, capture cache_state, then:
    assert {p for p, s in cache_state.items() if s == "miss"} == {"node_manifest"}
    assert cache_state[sibling] == "hit"


@pytest.mark.xfail(
    reason="ADR-0006 §Tradeoffs row 4: same-size YAML edit does NOT invalidate "
           "(accepted Phase 1 limitation). xfail pins it as a regression invariant."
)
def test_same_size_catalog_edit_does_not_invalidate(tmp_path, monkeypatch):
    # ... bump catalog_version: 1 -> 2 (same size); assert node_manifest stays hit
    ...
```

Raw-artifact-budget (AC-8/9/10 sketch):

```python
import json, os
from os import stat_result
import structlog
from click.testing import CliRunner

def test_30mb_lockfile_truncates_at_25mb(tmp_path, monkeypatch):
    # AC-8: small structurally-parseable lockfile + os.fstat monkey-patch
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "package.json").write_text('{"name":"x","dependencies":{"a":"1.0.0"}}')
    lock = repo / "pnpm-lock.yaml"
    lock.write_text("lockfileVersion: '6.0'\npackages:\n  /a@1.0.0: {}\n")
    from codegenie.probes._lockfiles import _pnpm
    assert _pnpm.parse(lock) is not None  # parses BEFORE the probe runs

    real_fstat = os.fstat
    def fake_fstat(fd):
        s = real_fstat(fd)
        return stat_result((s.st_mode, s.st_ino, s.st_dev, s.st_nlink,
                            s.st_uid, s.st_gid, 30 * 1024 * 1024,
                            s.st_atime, s.st_mtime, s.st_ctime))
    monkeypatch.setattr(os, "fstat", fake_fstat)

    with structlog.testing.capture_logs() as logs:
        result = CliRunner().invoke(cli, ["--no-gitignore", "gather", str(repo)])
        assert result.exit_code == 0

    # AC-9: marker-shape + valid JSON
    artifact = json.loads((repo / ".codegenie/context/raw/node_manifest.json").read_text())
    assert artifact["__truncated_at_budget__"] is True
    assert artifact["original_bytes"] >= 30 * 1024 * 1024
    assert artifact["budget_bytes"] == 25 * 1024 * 1024
    assert artifact["original_bytes"] >= artifact["budget_bytes"]

    # AC-10: exactly-one event
    truncations = [e for e in logs if e["event"] == "probe.raw_artifact.truncated"]
    assert len(truncations) == 1
    assert truncations[0]["probe"] == "node_manifest"
    assert truncations[0]["original_bytes"] >= 30 * 1024 * 1024
    assert truncations[0]["budget_bytes"] == 25 * 1024 * 1024
```

Commit red.

### Green — make it pass

1. Land the `node_pnpm_native/` fixture with real `pnpm install --lockfile-only` output.
2. The probe code from S3-05 should already pass these tests if the cross-reference logic is correct — if not, surface the gap in this PR as a callout: "S3-05 didn't cover the X case; fixed here." Do **NOT** modify S3-05's probe code from this PR unless a callout is documented.
3. Catalog-invalidation-scope test: monkey-patch `codegenie.catalogs.__init__._load_catalogs` only. If the loader is import-time-only and the monkey-patch can't be made hermetic, **fail loud** (Rule 12) and BLOCK on a separate S1-05 amendment story — do NOT silently widen S3-06's scope to edit S1-05.

### Refactor

- The integration tests share a "copy fixture → tmp_path → run CLI → read envelope" pattern. **Reuse** `_copy_tree` and `_load_envelope` from `tests/integration/probes/conftest.py` (already at this exact level since S2-04). Do **NOT** introduce a new `_run_gather_on_fixture` helper at a different path.
- The synthetic 30 MB lockfile generator belongs as a private function in its test file — not in `conftest.py` (single use; Rule 2). Promote only when a second probe needs it.
- Per the cross-cutting convention from S3-05's hardening, structlog event assertions are assertions of **exact count**, not just presence (AC-10).

## Files to touch

| Path | Why |
|---|---|
| `tests/fixtures/node_pnpm_native/package.json` | New — pinned `bcrypt`/`sharp`/`lodash` declarations. |
| `tests/fixtures/node_pnpm_native/pnpm-lock.yaml` | New — pnpm-generated lockfile resolving all three. |
| `tests/fixtures/node_pnpm_native/README.md` | New — what the fixture exercises. |
| `tests/fixtures/node_yarn_legacy/README.md` | **Edit (additive append only)** — append a paragraph documenting S3-06's parity-integration use. **Do NOT** touch `package.json` or `yarn.lock` — the existing files are load-bearing for S2-02a / S3-03 / S3-04. |
| `tests/integration/probes/test_node_manifest_pnpm_native.py` | New — pnpm + native modules + multi-probe + multi-lockfile parametrize (AC-3 / AC-4 / AC-5). |
| `tests/integration/probes/test_node_manifest_yarn_legacy.py` | New — `_HAS_PYARN` True vs. False parity with mocker.spy distinctness assertions (AC-6). |
| `tests/integration/probes/test_node_manifest_raw_artifact_budget.py` | New — `os.fstat` monkey-patch → truncation marker shape (AC-8 / AC-9 / AC-10). |
| `tests/unit/test_cache_invalidation_scope.py` | Edit (additive) — catalog-edit-invalidates-ONLY-`node_manifest` parametrized test + xfail companion for the same-size-edit ADR-0006 limitation (AC-7). |

## Out of scope

- **End-to-end Layer A integration test** (`test_layer_a_end_to_end.py`) — S5-05; uses `node_typescript_helm` not these fixtures.
- **`node_monorepo_turbo/` and `non_node_go/` fixtures** — S5-04.
- **Adversarial lockfile fixtures (regex-DoS, billion-laughs, oversized)** — S5-01, S5-02 under `tests/adv/`.
- **Yarn parser parity / oracle invariants** — S3-04 owns `tests/unit/probes/_lockfiles/test_yarn_parser_parity.py` with the CI-enforced mutation gate. S3-06's yarn-legacy test is a **probe-level integration smoke** (proves the dispatcher integrates correctly with `manifests` slice plumbing on yarn-classic), not parser correctness.
- **Yarn-corpus parity fixtures** — S3-04 owns `tests/fixtures/_yarn_corpus/`; this story uses `tests/fixtures/node_yarn_legacy/` (already on disk).
- **`bun.lockb` fixture** — bun is out of scope per S3-05.
- **`pyarn` install-state verification in CI matrix** — S3-03's PR-body checklist; this story assumes it's in place but surfaces the skip-rate in PR body (AC-11).
- **Lockfile-absent fixture** (only `package.json`, no lockfile) — owned by S5-04. Not exercised here.
- **`CATALOG_DIR` env-var override on the catalog loader** — would silently widen scope (Rule 3). If the in-scope monkey-patch isn't hermetic, BLOCK on a separate S1-05 amendment story; do NOT edit S1-05 from here.
- **`CATALOG_INVALIDATION_TARGETS` registry seam** — premature for one consumer (Rule 2). Recorded in Notes-for-implementer for the second consumer (CIProbe + `ci_providers.yaml` in Phase 2 / replacement catalogs in Phase 3).

## Notes for the implementer

- **Real lockfile for `node_pnpm_native/`.** Generate `pnpm-lock.yaml` via `pnpm install --lockfile-only` so it tracks real-world lockfile shape. Synthesized lockfiles can pass unit tests but mask production bugs. Pin specific versions in `package.json` (`"bcrypt": "5.1.1"`, `"sharp": "0.32.6"`, `"lodash": "4.17.21"`) — not ranges — so test assertions stay stable across re-installs.
- **`node_yarn_legacy/` is REUSE, not creation.** It already exists from S2-02a / S3-03 with `lodash@^4.17.21` + `packageManager: "yarn@1.22.19"` + classic `yarn.lock`. **Do NOT** overwrite `package.json` or `yarn.lock` — S2-02a / S3-03 / S3-04 tests depend on the current shape. Only the `README.md` is appended additively.
- **Catalog-loader redirection: monkey-patch ONLY** (`codegenie.catalogs.__init__._load_catalogs`). The "amend S1-05 with `CATALOG_DIR` env var" alternative is OUT OF SCOPE — it would silently widen this story's scope and edit a Step-1 / DONE story (Rule 3 — surgical changes; "extension by addition"). If monkey-patch can't be hermetic (loader is import-time-only, no swap-in seam), **fail loud** (Rule 12) and BLOCK on a separate S1-05 amendment story.
- **The catalog-invalidation-scope test is the load-bearing CI evidence for ADR-0006.** Both directions matter: under-invalidation (catalog edit doesn't invalidate `node_manifest`) AND over-invalidation (catalog edit flushes other probes). The aggregate `assert {p for p, s in cache_state.items() if s == "miss"} == {"node_manifest"}` catches both; the `pytest.parametrize` over each sibling kills surgical-flush mutants.
- **Catalog edit MUST change file size**, not just bytes. ADR-0006 §Tradeoffs row 4 explicitly says same-size YAML edits don't invalidate (the cache key is `(path, size)`). Bumping `1` → `2` is forbidden (same byte count); bump `1` → `10` (size +1) or append a new entry. The test asserts `path.stat().st_size != original_size` BEFORE the second gather (Rule 12). The companion `xfail` test (`test_same_size_catalog_edit_does_not_invalidate`) pins the ADR-0006 limitation as a regression-tracked invariant.
- **For the parity integration test**, the `mocker.spy(pyarn, "parse")` + `mocker.spy(_yarn, "_parse_handrolled")` pattern is the only way to prove the two arms exercised observably-distinct code paths. A naive byte-equal-only test passes trivially under "both arms used the same parser" mutations. If `pyarn` isn't in the CI matrix's `gather` extras, the `_HAS_PYARN=True` arm skips. **Verify the matrix** during PR review — at least one job must install `gather` extras so the pyarn arm exercises (AC-11). Surface skip rate in PR body.
- **`_HAS_PYARN` symbol coupling is brittle.** If S3-03's `_HAS_PYARN` is ever renamed or relocated, this story's parity test breaks silently. The rename should grep for `_HAS_PYARN` first.
- **30 MB raw-artifact test pattern of record: `os.fstat` monkey-patch.** `_validation/S3-05-node-manifest-probe.md` T-9 + S3-01/02/03's parser-cap tests all use this pattern. **Do NOT** write 30 MB of real bytes to tmpfs — CI disk budget. The lockfile written to `tmp_path` must be **small AND structurally parseable** (a real, parseable, ~100-byte `pnpm-lock.yaml` works); the size cap is what `os.fstat` simulates.
- **Truncation marker shape pinned by AC-9** matches `_validation/S1-09-raw-artifact-budget.md` §"Marker invariants": `__truncated_at_budget__: True` (boolean, no coerce), `original_bytes: int`, `budget_bytes: int`, `data: <prefix>`. The marker keeps the file as valid JSON.
- **Capture truncation events with `structlog.testing.capture_logs()`, NOT `caplog`.** The `caplog` route is unreliable under the project's `WriteLoggerFactory` config (S1-07 / S1-08 / S3-04 burned this).
- **Use `CliRunner` for gather invocation, NOT direct `cli_gather` import.** Direct invocation bypasses `tests/integration/probes/conftest.py`'s `_disable_cli_configure_logging` autouse fixture; without it the CliRunner re-runs `configure_logging` and silently drops every captured event (S2-05 burned this).
- **Multi-lockfile parametrize (AC-5)** is the first end-to-end exercise of Edge case #7 (`phase-arch-design.md "Edge cases" row 7`). If S3-05's probe code didn't already implement the `lockfile.multi_present` warning + `confidence: low` drop correctly, this AC will fail RED before green; surface in PR body as "S3-05 follow-up — multi-lockfile path needed correction" if so.
- **Multi-probe end-to-end claim** (AC-4) is the first exercise of `language_detection` + `node_build_system` + `node_manifest` together on a real fixture. If `LanguageDetectionProbe` or `NodeBuildSystemProbe` produces unexpected output (e.g., wrong `framework_hints`, wrong `package_manager`), surface as a callout — S5-05 is too late.
- **`CATALOG_INVALIDATION_TARGETS: frozenset[tuple[str, Path]]` seam** (probe_name → catalog_path) is the right shape for Phase 2 (CIProbe + `ci_providers.yaml`) and Phase 3 (replacement catalogs). **Do NOT extract** during S3-06 (Rule 2 — single application). Add a TODO in the test file pointing future catalog-bearing probes at this story's pattern; promote at the second consumer.
- `bcrypt` and `sharp` are the natural fixture choices because both are in the 10-entry seed catalog (S1-05). Using `keytar` or `node-canvas` would also work but `bcrypt` + `sharp` are the most-installed npm natives and the most likely Phase 7 inputs.
- Per cross-cutting convention #6, per-probe coverage for `node_manifest` is reported in this PR's body — the fixtures here are what drives that number up from S3-05's baseline.
