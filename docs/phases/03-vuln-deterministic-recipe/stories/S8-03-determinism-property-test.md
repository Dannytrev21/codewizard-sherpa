# Story S8-03 — Determinism property test (Hypothesis, 100 runs)

**Step:** Step 8 — Fixture portfolio, golden files, determinism property, adversarial tests
**Status:** HARDENED (validated 2026-05-20 — see [`_validation/S8-03-determinism-property-test.md`](_validation/S8-03-determinism-property-test.md))
**Effort:** M
**Depends on:** S8-01 (ships `tests/fixtures/repos/_portfolio.py` — the `PORTFOLIO` manifest this story imports — plus the 5 CVE fixtures), S8-02 (the e2e Express-CVE harness this story repeats ~100×; reuse its hermetic copytree + in-process CLI-invoke pattern), S6-05 (the `codegenie remediate` CLI the property drives — transitively pulls S6-04's `RemediationOrchestrator` + the shipped `RemediationOutcome` union)
**ADRs honored:** ADR-0008 (this is *the* test that verifies the deterministic-serial-fallback decision — a hedged-race `BundleBuilder` would fail this property by construction; AC-4 perturbs `CODEGENIE_BUNDLE_CONCURRENCY` across the run-pair so the property genuinely *stresses* the serial-fallback seam rather than merely repeating identical inputs; the `vuln_index.digest` cache-key invariant is exercised by AC-6's relevant-re-classification test), ADR-0010 (the determinism surface is derived from the **shipped** `RemediationOutcome` tagged union — `Validated` / `RemediationNotApplicable` / `RemediationFailed`, `src/codegenie/transforms/outcomes.py`; CVE ids ride as `CveId` newtypes read from the `PORTFOLIO` manifest, never raw `str`), ADR-0001 (`RemediationOrchestrator.run` is the Phase-5-named entry the `codegenie remediate` CLI drives; the property asserts on the workflow's observable output — the `git diff` of the `Validated.branch` — **not** on a non-existent `outcome.transform_id`)

## Validation notes

**Validated:** 2026-05-20 · **Verdict:** HARDENED · **Validator:** `phase-story-validator` (automated, scheduled task `story-validation-corrector`)

13 findings addressed — 2 block-class (each with a clear in-place fix), 9 harden, 2 nit. The goal — an offline-only Hypothesis determinism property over the 5 CVE fixtures — is sound and traces 1:1 to `phase-arch-design.md §Goals G4` + §Testing strategy §Property tests. Every defect is mechanism- or reconciliation-layer, not goal-layer — hence HARDENED, not RESCUE. Stage 2 ran as a single-validator synthesis pass (the four critic lenses were applied without fanning out to subagents — token economy under the scheduled-task budget; every source the four critics would read was read in Stage 1, including the shipped `outcomes.py`, the sibling `tests/property/test_bundle_determinism.py`, and the hardened S8-01/S8-02/S6-04 stories).

Key corrections:

1. **The comparison surface did not exist.** The story asserted `RemediationOrchestrator.run(...).transform.diff_bytes` / `.transform_id`. The **shipped** `RemediationOutcome` (`src/codegenie/transforms/outcomes.py`, S1-03 GREEN) is `Validated(branch, report_path, passed, failing) | RemediationNotApplicable(reason) | RemediationFailed(error, partial_report_path)` — **no variant carries `.transform` or `.transform_id`**. S6-04's own validation (note 1) already corrected this exact misconception. New AC-5 derives a `_determinism_key` from the shipped union: the `git diff` of the `Validated.branch` for Transform-bearing outcomes, the `(kind, reason)` pair for `RemediationNotApplicable`.
2. **`major-bump-required` produces no Transform.** Per S8-01 AC-1 it is `RemediationNotApplicable(MAJOR_BUMP_REFUSE)`. `assert a.transform.diff_bytes == ...` would raise `AttributeError`. `_determinism_key` (AC-5) handles the non-Transform variant — determinism of the *refuse* path is itself G4 ("replay produces identical outputs").
3. **`sampled_from` over 5 values cannot yield 100 examples.** `@given(st.sampled_from(_REPO_FIXTURES))` over a 5-element set exhausts at 5 — Hypothesis dedupes draws — so `max_examples=100` was dead and the headline "100 runs" was false. AC-2 now mirrors the established sibling `tests/property/test_bundle_determinism.py`: `@given(seed=st.integers(0, 10**9))`, where the seed selects the fixture and perturbs the run.
4. **100 plain repeats are weak.** The sibling injects seeded jitter so each run genuinely stresses the non-deterministic seam. AC-4 perturbs `CODEGENIE_BUNDLE_CONCURRENCY` (the ADR-0008 env knob) across the run-pair — a deterministic serial-fallback `BundleBuilder` must produce identical output at concurrency 1 and 4; a hedged-race one would not.
5. **The paired cache-key test was wrong by construction.** An *irrelevant* extra sqlite row only bumps the digest → cache miss → recompute → **identical** output. AC-6 now requires the seeded delta to *re-classify a CVE relevant to the fixture* (ADR-0008's actual motivation), so the transform genuinely differs.
6. **Re-declared the fixture list.** S8-01 shipped `tests/fixtures/repos/_portfolio.py` (`PORTFOLIO` tuple of `FixtureSpec`) and S8-01 AC-7 explicitly named S8-03's `_REPO_FIXTURES`/`_CVE_IDS` as the re-declaration to delete. AC-9 now derives the grid as `tuple(s for s in PORTFOLIO if s.cve_ids)`.
7. **`tests/conftest.py` does not exist** and S8-01's validation deliberately dropped that row. The property-only fixtures move to `tests/property/conftest.py`.
8. Added a mutation-guard AC (the property must fail against a no-op `_run_workflow` — Rule 9); fixed the AC-1 / `slow`-marker contradiction; added the missing S6-05 dependency; numbered the ACs AC-1..AC-15.

Full audit log: [`_validation/S8-03-determinism-property-test.md`](_validation/S8-03-determinism-property-test.md).

## Context

Goal G4 ("determinism over probabilism for structural changes") is the cardinal Phase 3 commitment — production `design.md §2.4` is veto-strength on this point. ADR-0008 records the architectural choice (deterministic serial fallback, not hedged race) and the cache-key shape (`blake3(... || vuln_index.digest)`) that make G4 *possible*; this story is what makes G4 *verified*. Without a property test, "deterministic" is an aspiration; with one, it's a CI gate.

The property is: **for each of the 5 CVE fixtures, running the full remediation workflow twice with identical inputs produces a byte-identical `_determinism_key` — the `git diff` of the patch branch for a `Validated` outcome, or the `(kind, reason)` pair for a `RemediationNotApplicable` outcome.** The "100 runs" is the headline number in `phase-arch-design.md §Testing strategy §Property tests`; this story reaches it by mirroring the established sibling `tests/property/test_bundle_determinism.py` — the Hypothesis dimension is a **large-range integer seed** (`st.integers(0, 10**9)`) with `@settings(max_examples=100)`, the seed both selects the fixture and perturbs `CODEGENIE_BUNDLE_CONCURRENCY` across the run-pair. (A `sampled_from` over the 5-element fixture set would NOT deliver 100 runs — Hypothesis dedupes draws and exhausts a 5-value space at 5 examples. See Validation note 3.)

**Reconciliation with shipped reality (validator).** The original story asserted on `RemediationOrchestrator.run(...).transform.diff_bytes` and `.transform_id`. As of validation the shipped `RemediationOutcome` (`src/codegenie/transforms/outcomes.py`, S1-03 GREEN 2026-05-18) is the tagged union `Validated(branch, report_path, passed, failing) | RemediationNotApplicable(reason) | RemediationFailed(error, partial_report_path)` — **no variant exposes a `.transform` or `.transform_id` attribute**, and the variant class names are `RemediationNotApplicable` / `RemediationFailed` (not `RemediationOutcome.NotApplicable`). S6-04's own validation surfaced exactly this. The byte-level determinism surface is therefore reconstructed from the *observable* output of the workflow: for a `Validated` outcome, the `git diff` of the created patch branch (`outcome.branch`) — which carries no timestamps and IS the byte-for-byte effect of `Transform.diff_bytes`; for a `RemediationNotApplicable` outcome, the variant tag plus its `reason`. Per S8-01 AC-1, exactly one of the 5 CVE fixtures (`major-bump-required`) yields `RemediationNotApplicable(MAJOR_BUMP_REFUSE)` — its refuse decision must be deterministic too, which is why the property compares a `_determinism_key`, not a raw `transform.diff_bytes`.

**Offline-only is non-negotiable.** Implementation-risk #2 in `High-level-impl.md` is explicit: "Determinism property test flakiness from npm registry drift. Mitigation: every fixture pins exact `package-lock.json` versions; the property test runs with `npm install --prefer-offline --offline` against a pre-warmed cache committed to the repo (not the live registry)." This story ships the pre-warmed `.npm-cache/` tarball as a test fixture and sets `npm_config_cache=<tarball-extracted-path>` on the jailed environment. If the cache miss path is ever taken, the property test fails loudly with a diagnostic event, not silently re-resolves over the network.

Hypothesis is already a Phase-allowed test dependency (Phase 1's `tests/property/` tests use it). This story adds the property file under `tests/property/test_transform_determinism.py`.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Goals G4` — "same inputs → same Transform bytes; replay produces identical outputs"; the headline cardinal commitment.
  - `../phase-arch-design.md §Testing strategy §Property tests` — "Determinism property (the headline): … byte-identical `transform.diff_bytes` across 100 runs. Hypothesis-strategy generators draw randomized inputs from a fixture grid."
  - `../phase-arch-design.md §Component design C7` — `BundleBuilder` cache-key shape including `vuln_index.digest`; AC-6's paired test verifies the cache key honors the digest (the property itself pins one digest — per-digest determinism, not cross-digest variation).
  - `../phase-arch-design.md §Component design C4` — `Transform.transform_id = blake3(diff_bytes)`; this is the *concept* of determinism the story verifies. Note the `Transform` is an internal workflow value — it is NOT a field of the returned `RemediationOutcome` (see `outcomes.py` below); the property reconstructs the Transform's byte-level effect from the `git diff` of the patch branch.
  - `../phase-arch-design.md §Implementation-level risks #2` — registry drift mitigation via pre-warmed cache.
- **Phase ADRs:**
  - `../ADRs/0008-bundlebuilder-deterministic-serial-fallback-and-vuln-index-digest-cache-key.md` — the architectural reason hedged-race was rejected; the property test is the executable form of the "Reversibility: low" claim in that ADR.
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` — the `RemediationOutcome` discriminated union (`Validated` / `RemediationNotApplicable` / `RemediationFailed`) the property `match`es on; `CveId` newtypes ride in the `PORTFOLIO` manifest, never raw `str`.
  - `../ADRs/0001-ship-phase5-contract-surface-by-name.md` — `RemediationOrchestrator.run` is the Phase-5-stable entry the property drives (via the `codegenie remediate` CLI); the property asserts on its observable output, not on a non-existent `outcome.transform_id`.
- **Existing code (read these — the determinism pattern is already established in-repo):**
  - **`tests/property/test_bundle_determinism.py` — THE canonical pattern to mirror (validator-added, load-bearing).** It already proves `BundleBuilder` determinism via Hypothesis: `@given(seed=st.integers(min_value=0, max_value=10**9))` + `@settings(max_examples=100, deadline=None)`, the seed injected as scheduler jitter, two same-seed builds asserted byte-identical. It *also* ships an `@pytest.mark.xfail(strict=True)` meta-test running the property against a deliberately-broken `_HedgedRaceBundleBuilder` (`tests/property/_hedged_race_reference.py`) — the negative control that proves the property has teeth. S8-03 is the workflow-level analogue; copy the strategy shape and the meta-test idea.
  - `src/codegenie/transforms/outcomes.py` — the **shipped** `RemediationOutcome` tagged union: `Validated(branch, report_path, passed, failing) | RemediationNotApplicable(reason) | RemediationFailed(error, partial_report_path)`. The story's `_determinism_key` (AC-5) `match`es on these exact variants. There is no `.transform` / `.transform_id` attribute on any variant — do not reference them.
  - `tests/fixtures/repos/_portfolio.py` (S8-01 AC-7) — the `PORTFOLIO` `Final` tuple of `FixtureSpec(name, path, is_adversarial, cve_ids: tuple[CveId, ...], edge_cases, expected_outcome)`. This story **imports** it; it does NOT re-declare fixture names or CVE ids (AC-9).
  - `src/codegenie/transforms/orchestrator.py` (S6-04) — `RemediationOrchestrator.run(repo, cve, context=None) -> RemediationOutcome`, the Phase-5-named entry. The `codegenie remediate` CLI (S6-05) wires it; this story drives the workflow through that CLI (reusing S8-02's in-process `CliRunner` harness) rather than hand-constructing the orchestrator's dependency graph.
  - `tests/integration/test_end_to_end_express_cve.py` (S8-02) — the single-run e2e harness: hermetic `shutil.copytree` into `tmp_path`, in-process `CliRunner().invoke(cli, ["remediate", ...])`. S8-03 repeats this run ~100× — reuse the harness, do not re-invent it.
  - `src/codegenie/plugins/bundle.py` (S3-04) — the `BundleBuilder` whose `vuln_index.digest` cache-key invariant AC-6 exercises end-to-end (the unit-level cache-key test is `tests/unit/plugins/test_bundle.py`, mandated by ADR-0008 Consequences).
  - `pyproject.toml` — confirm `hypothesis` is in `[project.optional-dependencies] dev` (it is — `tests/property/` already uses it); add the `slow` marker under `[tool.pytest.ini_options].markers` if absent.
- **High-level impl:**
  - `../High-level-impl.md §Step 8 §Done criteria` — "`pytest tests/property/test_transform_determinism.py --hypothesis-seed=0` produces identical `diff_bytes` across all 100 runs (cardinal Goal G4)."
  - `../High-level-impl.md §Implementation-level risks #2` — registry-drift mitigation; mandates pre-warmed cache.

## Goal

Land `tests/property/test_transform_determinism.py` with a Hypothesis-driven property — `@given(seed=st.integers(0, 10**9))`, `@settings(max_examples=100, deadline=None)`, mirroring `tests/property/test_bundle_determinism.py` — that, for each of the 5 CVE fixtures (read from the S8-01 `PORTFOLIO` manifest), runs the full remediation workflow twice with identical inputs but perturbed `CODEGENIE_BUNDLE_CONCURRENCY` and asserts a byte-identical `_determinism_key` (the `git diff` of the `Validated.branch`, or the `(kind, reason)` of a `RemediationNotApplicable` outcome). It runs **offline-only** via a pre-warmed npm cache, ships a teeth-check so the property cannot pass vacuously, and a paired test asserting that a vuln-index refresh which *re-classifies a CVE relevant to the fixture* produces a different `_determinism_key` (proving the Bundle cache key honors `vuln_index.digest` per ADR-0008).

## Acceptance criteria

- [ ] **AC-1 — the file exists and its CI/local visibility is unambiguous.** `tests/property/test_transform_determinism.py` exists and `pytest --collect-only` lists its test functions (not under `@pytest.mark.skip*` / `xfail`). It carries `@pytest.mark.slow`; the default `pytest -q` invocation (hence `make test` / `make check`) **excludes** `slow` via `addopts` so local dev is not blocked by a multi-minute test; CI runs it through an explicit `pytest -m slow` step. The `slow` marker is registered in `pyproject.toml [tool.pytest.ini_options].markers`. (Wiring the CI YAML to include the `-m slow` step is S9-01's job — this story only adds the marker and notes the boundary.) (validator: hardened — original AC said "runs in CI on every PR" while the Refactor said mark `slow` to opt out of `pytest -q`; the two contradicted.)
- [ ] **AC-2 — the Hypothesis dimension is a large-range integer seed, NOT `sampled_from` over the fixtures.** The strategy is `@given(seed=st.integers(min_value=0, max_value=10**9))` — exactly mirroring `tests/property/test_bundle_determinism.py`. The seed selects the fixture (`_CVE_FIXTURES[seed % len(_CVE_FIXTURES)]`) and derives the per-run perturbation. A `st.sampled_from(_CVE_FIXTURES)` strategy is **forbidden**: Hypothesis dedupes draws and exhausts a 5-element space at 5 examples, so `max_examples=100` would be silently dead and the headline "100 runs" false. (validator: hardened — block-class; the original `@given(st.sampled_from(_REPO_FIXTURES))` could never deliver 100 runs.)
- [ ] **AC-3 — `@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])`** — 100 examples, no per-example deadline (each example is a real jailed workflow), `too_slow` suppressed (runtime budget is the bench harness's concern, not Hypothesis').
- [ ] **AC-4 — the property body runs the workflow twice with perturbed concurrency.** For each example: run the full remediation workflow **twice** against the seed-selected fixture with identical `(repo, cve, vuln_index)` inputs but a **different `CODEGENIE_BUNDLE_CONCURRENCY`** per run (run A at `1`, run B at `min(4, os.cpu_count() or 1)`). Assert `_determinism_key(run_a) == _determinism_key(run_b)`. A deterministic serial-fallback `BundleBuilder` (ADR-0008) MUST produce identical output regardless of concurrency; a hedged-race one would not — so the perturbation makes the 100 runs *stress* the seam, not merely repeat it. (validator: hardened — original body asserted `transform.diff_bytes == transform.diff_bytes` between two *identical* runs, which is a weak repeat; concurrency perturbation mirrors the seeded-jitter philosophy of `test_bundle_determinism.py`.)
- [ ] **AC-5 — the determinism surface is derived from the shipped `RemediationOutcome` union.** A helper `_determinism_key(repo: Path, outcome: RemediationOutcome) -> bytes` produces the byte-level comparison surface by `match`ing the **shipped** variants (`src/codegenie/transforms/outcomes.py`): `Validated` → the `git diff` bytes of the patch branch (`outcome.branch`) against its base — the deterministic, timestamp-free, byte-for-byte reconstruction of `Transform.diff_bytes`; `RemediationNotApplicable` → `b"remediation_not_applicable:" + reason` (the refuse path must be deterministic too — G4); `RemediationFailed` → the test fails loudly (a CVE fixture must not error). The story references **no** `outcome.transform` / `outcome.transform_id` — no `RemediationOutcome` variant carries them. (validator: added — block-class; the original comparison surface did not exist on the shipped union, per S6-04 validation note 1.)
- [ ] **AC-6 — paired cache-key test uses a *relevant* re-classification.** A non-property test `test_vuln_index_refresh_changes_transform` asserts that when the vuln index is refreshed so a CVE **relevant to `express-cve-2024-21501`** is re-classified (e.g. its affected range widened to cover the installed version, or a new applicable CVE record added for an installed package), the *same* `(repo, cve)` produces a **different** `_determinism_key`. The seeded delta MUST change a fixture-relevant classification — an *irrelevant* extra row only bumps `vuln_index.digest`, causing a cache miss whose recompute yields byte-*identical* output (the test would then fail). This is ADR-0008's "a CVE-feed refresh that re-classifies a CVE must not return a stale cache hit" in executable e2e form; the unit-level cache-key check remains `tests/unit/plugins/test_bundle.py` (ADR-0008 Consequences). (validator: hardened — original test seeded "one extra irrelevant row" and expected a different transform, which is wrong by construction.)
- [ ] **AC-7 — offline-only.** A `tests/property/conftest.py` session-scoped fixture `prewarmed_npm_cache` extracts `tests/fixtures/npm-cache.tar.zst` into a session tmp dir and returns the path; each workflow run points the jailed npm at it (`npm_config_cache`) and the jailed `npm install` runs `--prefer-offline --offline --ignore-scripts`. If `--offline` ever falls through to a network lookup, npm exits non-zero (`ENOTCACHED`) and the test fails loudly — never silently re-resolves. (validator: hardened — fixture relocated from a non-existent root `tests/conftest.py` to `tests/property/conftest.py`; see AC-13 / Files to touch.)
- [ ] **AC-8 — the pre-warmed cache tarball is committed and size-capped.** `tests/fixtures/npm-cache.tar.zst` is checked in, ≤ 4 MiB compressed; a `tests/fixtures/test_npm_cache_size.py` fence asserts the cap (`pytest`-collected, fails if exceeded).
- [ ] **AC-9 — the fixture grid is derived from the S8-01 manifest, never re-declared.** `_CVE_FIXTURES` is computed as `tuple(s for s in PORTFOLIO if s.cve_ids)` where `PORTFOLIO` is imported from `tests/fixtures/repos/_portfolio.py` (S8-01 AC-7). This yields exactly the 5 CVE-carrying fixtures (`express-cve-2024-21501`, `monorepo-workspaces`, `transitive-only-cve`, `major-bump-required`, `breaking-test-suite`); each fixture's directory comes from `FixtureSpec.path` and its CVE ids from `FixtureSpec.cve_ids` (`CveId` newtypes). The test file declares **no** literal fixture-name tuple and **no** `_CVE_BY_FIXTURE` dict. (validator: hardened — S8-01 AC-7 explicitly named S8-03's `_REPO_FIXTURES`/`_CVE_IDS` as the re-declaration to eliminate; the rule-of-three is conclusively past.)
- [ ] **AC-10 — runs are isolated AND cold.** Run A and run B of every example use separate `tmp_path_factory.mktemp(...)` directories, each with its **own** `BundleBuilder` `cache_dir`, its own npm-cache extraction target, and its own `.codegenie/` output root — so the property tests *compute* determinism, not cache-read determinism (a shared `cache_dir` would make run B a cache hit and silently weaken the test). Example-to-example isolation follows from the fresh `mktemp`. (validator: hardened — original AC covered only example-to-example isolation; the cold-cache requirement is what makes the property meaningful.)
- [ ] **AC-11 — actionable failure diagnostic.** On failure the assertion message includes the seed, the fixture name, the two `_determinism_key` BLAKE3 digests, and the byte-offset of the first divergence with ±32 bytes of context quoted around it — diagnostic enough to localize the non-determinism without re-running.
- [ ] **AC-12 — the property has teeth (mutation guard).** The property cannot pass vacuously. For every `Validated`-outcome example the test asserts the `git diff` is **non-empty** (the workflow actually patched the lockfile) before comparing keys — a property that passes against a no-op `_run_workflow` is worthless (Rule 9). Additionally, an `@pytest.mark.xfail(strict=True)` meta-test runs the determinism assertion against a deliberately non-deterministic shim (e.g. a `_run_workflow` variant that injects a random byte into the diff), mirroring `test_bundle_determinism.py`'s hedged-race meta-test — if a future regression makes the broken shim pass, CI fails loud. (validator: added — the original story had no negative control; the sibling determinism test has one.)
- [ ] **AC-13 — `tests/property/conftest.py` carries the property's fixtures.** `prewarmed_npm_cache` (AC-7) and `vuln_index_reclassifying_express` (AC-6 — a sqlite index with the relevant CVE re-classification) live in a NEW `tests/property/conftest.py`, scoped to the property suite. They are **not** placed in a root `tests/conftest.py` (which does not exist, and would force session-scoped tarball extraction onto the entire ~2,300-test suite). (validator: added — S8-01's validation explicitly dropped a `tests/conftest.py` row; fixtures consumed only by this test belong beside it.)
- [ ] **AC-14 — `pytest tests/property/test_transform_determinism.py --hypothesis-seed=0` is reproducible** run-to-run: the strategy is `st.integers` (deterministic given the seed), the workflow is offline, and the only intentional variation (`CODEGENIE_BUNDLE_CONCURRENCY`) is a pure function of the Hypothesis seed. Committing `--hypothesis-seed=0` to the CI `pytest -m slow` step makes a day-1 flake reproducible.
- [ ] **AC-15 — `make check` clean; `mypy --strict` clean** on `tests/property/test_transform_determinism.py`, `tests/property/conftest.py`, and `tests/fixtures/test_npm_cache_size.py` (typed helpers, no `Any`, no untyped functions); TDD plan's red test exists, was committed failing, and is green after the Green step.

## Implementation outline

1. Add `tests/fixtures/npm-cache.tar.zst` (one-time author task: run `npm install --prefer-offline` against each of the 5 CVE fixtures with `npm_config_cache=tmp` then `tar -I 'zstd -19' -cf npm-cache.tar.zst tmp/`); commit. Cap at 4 MiB or split. Document the regen recipe in the test module docstring.
2. Create `tests/property/conftest.py` with two fixtures: `prewarmed_npm_cache(tmp_path_factory)` — session-scoped, extracts the tarball once and returns the path; `vuln_index_reclassifying_express(tmp_path_factory)` — a sqlite `VulnIndex` whose contents re-classify a CVE relevant to `express-cve-2024-21501` (AC-6). Do **not** create a root `tests/conftest.py`.
3. Write the `_run_workflow` helper. It drives the full remediation workflow against a copied fixture and returns a small frozen result `_WorkflowRun(outcome: RemediationOutcome, key: bytes)`. Reuse S8-02's hermetic harness — `shutil.copytree` the fixture into the run dir, then `CliRunner().invoke(cli, ["remediate", str(repo), "--cve", cve])` (the CLI wires the orchestrator; do not hand-construct `RemediationOrchestrator`). Set, per run: `CODEGENIE_BUNDLE_CONCURRENCY` (the AC-4 perturbation), `npm_config_cache` → the pre-warmed cache, `npm_config_offline=true`, and `CODEGENIE_VULN_INDEX_PATH` when AC-6 needs the re-classifying index. Parse the produced `remediation-report.yaml` (and/or the returned `RemediationOutcome`) to recover the outcome variant, then compute `key = _determinism_key(repo, outcome)`.
4. Write `_determinism_key(repo, outcome)` per AC-5 — a `match` over the shipped `RemediationOutcome` union (`Validated` → `git diff` of the patch branch; `RemediationNotApplicable` → `b"remediation_not_applicable:" + reason`; `RemediationFailed` → `raise AssertionError`).
5. Write the property `test_transform_output_deterministic(seed, prewarmed_npm_cache, tmp_path_factory)` — `@given(seed=st.integers(0, 10**9))`, `@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])`. Select the fixture by `seed % len(_CVE_FIXTURES)`; run twice with perturbed concurrency; mutation-guard (AC-12); assert `key` equality with `_diff_diagnostic`.
6. Write the paired `test_vuln_index_refresh_changes_transform` (AC-6) and the `@pytest.mark.xfail(strict=True)` teeth meta-test (AC-12).
7. Write `_diff_diagnostic(run_a, run_b, fixture_name, seed) -> str` returning a multi-line message naming the seed, fixture, both BLAKE3 key digests, and the byte offset of the first divergence with ±32 bytes of context.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/property/test_transform_determinism.py`

```python
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from codegenie.transforms.outcomes import (
    RemediationFailed,
    RemediationNotApplicable,
    Validated,
)
from tests.fixtures.repos._portfolio import PORTFOLIO  # S8-01 AC-7 — single source of truth

# The grid IS the 5 CVE-carrying fixtures — DERIVED, never re-declared (S8-01 AC-7).
_CVE_FIXTURES = tuple(s for s in PORTFOLIO if s.cve_ids)


@dataclass(frozen=True)
class _WorkflowRun:
    outcome: object          # a shipped RemediationOutcome variant
    key: bytes               # _determinism_key(repo, outcome)


def _determinism_key(repo: Path, outcome: object) -> bytes:
    """Byte-level determinism surface, derived from the SHIPPED RemediationOutcome union.

    No RemediationOutcome variant exposes `.transform` / `.transform_id`
    (src/codegenie/transforms/outcomes.py). The observable, byte-stable surface:
      - Validated                -> `git diff` of the patch branch (timestamp-free;
                                    the byte-for-byte effect of Transform.diff_bytes).
      - RemediationNotApplicable -> the variant tag + reason (the refuse path must be
                                    deterministic too -- G4 "replay produces identical outputs").
      - RemediationFailed        -> a CVE fixture must not error; fail loud.
    """
    match outcome:
        case Validated(branch=branch):
            return subprocess.run(
                ["git", "-C", str(repo), "diff", f"{branch}^..{branch}"],
                capture_output=True, check=True,
            ).stdout
        case RemediationNotApplicable(reason=reason):
            return b"remediation_not_applicable:" + str(reason).encode()
        case RemediationFailed() as failed:
            raise AssertionError(f"unexpected RemediationFailed for a CVE fixture: {failed}")
        case _:
            raise AssertionError(f"unhandled RemediationOutcome variant: {outcome!r}")


@pytest.mark.slow
@given(seed=st.integers(min_value=0, max_value=10**9))
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
def test_transform_output_deterministic(
    seed: int, prewarmed_npm_cache: Path, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Goal G4 — same inputs -> byte-identical workflow output. ADR-0008 cardinal property.

    Mirrors tests/property/test_bundle_determinism.py: the Hypothesis dimension is a
    large-range integer seed (a `sampled_from` over the 5-fixture set would exhaust
    at 5 examples). The seed selects the fixture and perturbs CODEGENIE_BUNDLE_CONCURRENCY.
    """
    spec = _CVE_FIXTURES[seed % len(_CVE_FIXTURES)]
    a = _run_workflow(spec, prewarmed_npm_cache, tmp_path_factory.mktemp("a"), concurrency=1)
    b = _run_workflow(
        spec, prewarmed_npm_cache, tmp_path_factory.mktemp("b"),
        concurrency=min(4, os.cpu_count() or 1),
    )

    # AC-12 mutation guard: a property that passes against a no-op workflow is worthless.
    if isinstance(a.outcome, Validated):
        assert a.key, f"{spec.name}: empty git diff -- workflow did no work"

    assert a.key == b.key, _diff_diagnostic(a, b, spec.name, seed)


def test_vuln_index_refresh_changes_transform(
    prewarmed_npm_cache: Path,
    tmp_path_factory: pytest.TempPathFactory,
    vuln_index_reclassifying_express: Path,
) -> None:
    """ADR-0008 -- a vuln-index refresh that RE-CLASSIFIES a relevant CVE changes output.

    An *irrelevant* extra row only bumps the digest -> cache miss -> recompute ->
    identical output. The seeded delta must re-classify CVE-2024-21501.
    """
    spec = next(s for s in _CVE_FIXTURES if s.name == "express-cve-2024-21501")
    baseline = _run_workflow(spec, prewarmed_npm_cache, tmp_path_factory.mktemp("base"))
    refreshed = _run_workflow(
        spec, prewarmed_npm_cache, tmp_path_factory.mktemp("refr"),
        vuln_index_path=vuln_index_reclassifying_express,
    )
    assert baseline.key != refreshed.key, (
        "vuln_index.digest is not honoured in the Bundle cache key (ADR-0008)"
    )
```

State why it fails (red): `tests/property/conftest.py` (with `prewarmed_npm_cache` / `vuln_index_reclassifying_express`) does not exist; the `_run_workflow` and `_diff_diagnostic` helpers are unwritten; `tests/fixtures/npm-cache.tar.zst` is not committed; `tests/fixtures/repos/_portfolio.py` lands with S8-01. Every example errors at import / fixture resolution.

A sibling `@pytest.mark.xfail(strict=True)` teeth meta-test (AC-12) runs the determinism assertion against a deliberately non-deterministic `_run_workflow` variant (injects a random byte into the diff) — it must fail; if a regression makes it pass, `xfail(strict=True)` flips CI red.

### Green — minimal pass

- Commit `tests/fixtures/npm-cache.tar.zst` (≤ 4 MiB) and the `tests/fixtures/test_npm_cache_size.py` fence.
- Create `tests/property/conftest.py` with `prewarmed_npm_cache` and `vuln_index_reclassifying_express`.
- Write `_run_workflow(spec, cache, run_dir, *, concurrency=..., vuln_index_path=...) -> _WorkflowRun` — `shutil.copytree` the fixture (`spec.path`) into `run_dir`, set `CODEGENIE_BUNDLE_CONCURRENCY` / `npm_config_cache` / `npm_config_offline` / `CODEGENIE_VULN_INDEX_PATH`, drive `CliRunner().invoke(cli, ["remediate", ...])`, recover the `RemediationOutcome`, compute `key = _determinism_key(run_dir/"repo", outcome)`.
- Register the `slow` marker in `pyproject.toml [tool.pytest.ini_options].markers`; confirm `addopts` excludes `slow` from the default run.
- Run `pytest -m slow tests/property/test_transform_determinism.py --hypothesis-seed=0`; expect 100 examples × 2 runs, all passing.

### Refactor

- Land the `_diff_diagnostic` helper producing the seed / fixture / both-BLAKE3-digests / byte-offset-of-first-divergence message (±32 bytes of context).
- Land the paired `test_vuln_index_refresh_changes_transform` (one example, not Hypothesis) and the `xfail(strict=True)` teeth meta-test.
- Edge cases from §Edge cases that this code touches: E6 (`major-bump-required` — `RemediationNotApplicable(MAJOR_BUMP_REFUSE)`, exercised via the `_determinism_key` non-Transform branch; the refuse decision must be deterministic); E18 (degraded adapter — `stale-scip` is NOT a CVE fixture so it is out of this grid, but the `CODEGENIE_BUNDLE_CONCURRENCY` perturbation in AC-4 stresses the same serial-fallback seam a degraded adapter would). E11 (`cve_delta`) is an S8-04 concern and is not in this grid.

## Files to touch

| Path | Why |
|---|---|
| `tests/property/test_transform_determinism.py` | NEW — the Hypothesis property + the paired cache-key test + the `xfail` teeth meta-test. |
| `tests/property/conftest.py` | NEW — `prewarmed_npm_cache` (session-scoped) + `vuln_index_reclassifying_express` fixtures, scoped to the property suite. (validator: was `tests/conftest.py` — no root conftest exists; a root conftest would force session tarball extraction onto the whole ~2,300-test suite.) |
| `tests/fixtures/npm-cache.tar.zst` | NEW — pre-warmed offline npm cache (≤ 4 MiB compressed). |
| `tests/fixtures/test_npm_cache_size.py` | NEW — fence asserting the cache tarball stays ≤ 4 MiB. |
| `pyproject.toml` (edit) | Register the `slow` marker under `[tool.pytest.ini_options].markers`; confirm `addopts` excludes `-m "not slow"` from the default run; confirm `hypothesis` is in `dev` deps (it is). |

## Out of scope

- **Fuzzing the inputs** with random strings/bytes — this is a *sampled grid*, not a fuzz test. Random inputs would mostly produce uninteresting `RecipeOutcome.NotApplicable` returns and waste runtime; the value is in repeating real fixture inputs.
- **Cross-fixture determinism** (asserting `express-cve-2024-21501.diff_bytes != monorepo-workspaces.diff_bytes`) — obvious from the inputs; not interesting to test.
- **Determinism across plugin/recipe version *changes*** — by design, a recipe version bump must change the output, otherwise versioning is meaningless. The property is per-version determinism, not cross-version invariance.
- **Network-online mode** — explicitly out of scope; ADR-0008's Reversibility note pins offline+pre-warmed-cache as the only mode for this test.
- **A hard performance budget for the property test** — S9-03 owns formal bench budgets. 100 examples × 2 perturbed runs is up to 200 jailed `npm install` + `npm test` executions; the "~3 s warm" estimate is optimistic for a real express tree even offline. The executor measures the actual wall-time once `_run_workflow` exists; if 200 jailed runs are disproportionate for a per-PR `slow` job, `max_examples` may be reduced **with a documented rationale in the attempt log** — the `CODEGENIE_BUNDLE_CONCURRENCY` perturbation (AC-4) preserves the test's determinism-stressing power at lower N (each run still exercises a different scheduler regime). The marker (`slow`) and the offline cache keep the cost off the default `make check`.
- **`vuln_index.digest` *content* changes** beyond the paired cache-key test — Phase 4+ will likely add more granular invariants.

## Notes for the implementer

- **Mirror `tests/property/test_bundle_determinism.py` — it is the established pattern.** Read it before writing a line. The Hypothesis dimension is `seed=st.integers(min_value=0, max_value=10**9)` with `@settings(max_examples=100, deadline=None)`; a `sampled_from` over the 5-fixture set would exhaust at 5 examples (Hypothesis dedupes draws) and silently make `max_examples=100` a no-op. The seed selects the fixture and derives the per-run perturbation. The sibling also ships an `xfail(strict=True)` meta-test against a deliberately-broken reference — copy that idea (AC-12).
- **The comparison surface is the shipped `RemediationOutcome` union — there is no `.transform` / `.transform_id`.** `RemediationOrchestrator.run(...)` returns `Validated(branch, report_path, passed, failing) | RemediationNotApplicable(reason) | RemediationFailed(error, partial_report_path)` (`src/codegenie/transforms/outcomes.py`). `_determinism_key` `match`es those variants. ADR-0008's invariant is over the *Transform's effect*; the `git diff` of the `Validated.branch` IS that effect, byte-for-byte, and `git diff` carries no timestamps so it is deterministic. For `RemediationNotApplicable` (the `major-bump-required` fixture — `MAJOR_BUMP_REFUSE`) there is no Transform at all; the refuse decision itself must be deterministic, so the key is the variant + reason.
- **Drive the workflow through the CLI, not a hand-built orchestrator.** `RemediationOrchestrator.__init__` needs a large dependency graph (event log, trust scorer, sandbox jail, plugin registry, vuln index). The `codegenie remediate` CLI (S6-05) wires all of it. Reuse S8-02's in-process `CliRunner` harness — `shutil.copytree` the fixture, `CliRunner().invoke(cli, ["remediate", str(repo), "--cve", cve])`. Per-run knobs (`CODEGENIE_BUNDLE_CONCURRENCY`, `npm_config_cache`, `npm_config_offline`, `CODEGENIE_VULN_INDEX_PATH`) are all environment variables — no code seam needed.
- **`CODEGENIE_BUNDLE_CONCURRENCY` perturbation is what gives the 100 runs teeth.** Two identical runs at the same concurrency mostly just repeat. Running run A at concurrency 1 and run B at `min(4, cpu)` forces the `BundleBuilder` semaphore through two different scheduling regimes — a deterministic serial-fallback builder is invariant to it; a hedged-race builder is not. This is the workflow-level analogue of the sibling's seeded jitter.
- **Cold caches per run.** Run A and run B must use *independent* `BundleBuilder` `cache_dir`s — if they share one, run B is a cache hit and you are testing cache-read determinism, not compute determinism. `tmp_path_factory.mktemp("a")` / `mktemp("b")` give distinct trees; keep every cache + `.codegenie/` output under the per-run tree.
- **`deadline=None` is non-negotiable.** A multi-second jailed workflow against Hypothesis' default 200 ms deadline produces immediate `Flaky` failures. The bench harness (S9-03) owns timing; this test owns correctness.
- **`--offline` must fail loudly.** If jailed `npm install --offline` ever falls through to a network call, npm exits with `ENOTCACHED: request was forced offline`. Let it propagate; do not catch + skip. Verify how the `SubprocessJail` plumbs `npm_config_*` into the jailed environment (S4-02/S4-03/S6-04) — the offline-ness must be real, not aspirational.
- **The cache-key test needs a *relevant* re-classification.** `vuln_index.digest` being part of the Bundle cache key (ADR-0008) means a digest change → cache *miss* → recompute. Recompute with identical inputs yields identical output. To observe a *different* `_determinism_key`, the seeded `vuln_index_reclassifying_express` index must re-classify a CVE that the `express-cve-2024-21501` workflow actually consults (widen an affected range, or add an applicable CVE for an installed package). An "extra irrelevant row" proves nothing.
- **The byte-offset diagnostic matters more than the property message.** When this fails 6 months from now, the engineer needs to know *where* the divergence is. Use `next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), -1)` and quote ±32 bytes around it.
- **Hypothesis seed pinning.** `@settings(...)` does not pin the seed; the CLI flag `--hypothesis-seed=0` does. The CI `pytest -m slow` step must pass it. Without seed pinning a day-1 flake is unreproducible.
- **If `_run_workflow` ever has to mock something to make the test pass, the test is wrong.** The property is over the *real* offline workflow; mocks would mean testing the mocks' determinism. The teeth meta-test (AC-12) and the non-empty-diff guard exist precisely to catch a property that has gone vacuous.
- **The masking helper opportunity.** S8-02 ships `_mask_nondeterministic_fields` inside its test module; if this story ends up needing report masking, that is the rule-of-three — extract the helper to a shared `tests/_e2e_support.py` rather than importing test-module-from-test-module. If the `git diff` surface (AC-5) is sufficient, no masking is needed at all — prefer that.
