# Story S7-03 — Determinism canary: 5× byte-identical diff + branch SHA

**Step:** Step 7 — Harden — ≥ 30 adversarial fixtures, determinism canary, perf canaries, Phase-2 regression hard-gate, Phase-4 handoff verification, CI gates
**Status:** Ready
**Effort:** M
**Depends on:** S7-01 (express bundle + recorded resolution + pinned mirror — the canary's input), S5-05 (full `codegenie remediate` CLI vertical — what the canary runs), S3-09 (`LockfileCanonicalizer` — the load-bearing primitive), S3-03 (`tools/digests.yaml` extension pinning `npm` minor digest — the other load-bearing primitive)
**ADRs honored:** ADR-0011 (lockfile canonicalization + pinned `npm` minor digest + `--no-audit --no-fund --ignore-scripts` + `LC_ALL=C` — the four mechanisms whose joint correctness this canary verifies), ADR-0012 (pinned local registry mirror — removes registry drift as a flake axis), ADR-0014 (`npm` is the only `ALLOWED_BINARIES` surface touching the canary path), ADR-0010 (audit chain extension — the canary's audit slice across 5 runs must show consistent event ordering)

## Context

Phase 3's exit criterion includes a **byte-deterministic diff** (`final-design.md §"Determinism" #19`). The determinism canary is the load-bearing CI gate that proves it: it runs `codegenie remediate` 5× back-to-back against the `express` canary fixture and asserts that all five runs produce **byte-identical diffs** and **byte-identical branch tree SHAs**. ADR-0011 enumerates the four mechanisms whose joint correctness this canary verifies — pinned `npm` minor digest, `LockfileCanonicalizer` (LC_ALL=C + key sort + LF), `--no-audit --no-fund` on every install invocation, and `--ignore-scripts` (S3-01 wrapper-level invariant). ADR-0012's pinned local registry mirror removes the registry-drift axis.

A canary failure is **diagnostically narrow**: the cause is necessarily one of (a) `npm` minor-version drift on the host (silently bumped past the pinned digest), (b) a regression in `LockfileCanonicalizer` (idempotence violated), (c) `ncu` non-determinism (peer-dep resolution order drift — rare but real), or (d) the recipe digest changed without the manifest being updated (S3-04 invariant). The test's red-fail output must surface which of these four applies; the worst outcome is a canary that flakes without surfacing the cause, which would teach the team to ignore it.

This story ships `tests/integration/test_byte_identical_diff_5x.py` + a small helper that runs the pipeline 5× under a fresh `tmp_path` per run (no cache shared across the five runs — that would be testing the cache, not the pipeline) and asserts byte-identical outputs. The CI job `determinism_canary` (wired in S7-07) gates merge.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Testing strategy" §"Determinism canary"` — the canary definition: 5× full pipeline, byte-identical diff + branch SHA.
  - `../phase-arch-design.md §"Risks (top 5)" §"Risk #2"` — determinism flake risk; this canary is the mitigation.
  - `../phase-arch-design.md §"Harness engineering" §"Determinism"` — the four mechanisms enumerated.
  - `../phase-arch-design.md §"Component design" #6 "LockfileCanonicalizer"` — the helper this canary depends on.
- **Phase ADRs:**
  - `../ADRs/0011-lockfile-canonicalization-and-npm-digest-pin-for-deterministic-diffs.md` — read end-to-end; this canary is its acceptance test.
  - `../ADRs/0012-test-fixture-bundle-plus-resolution-plus-pinned-mirror.md` — the mirror is what makes the canary offline + deterministic.
  - `../ADRs/0014-allowed-binaries-additions-npm-ncu-java.md` — `npm` is allow-listed; the canary's invocations go through S3-01.
- **Production ADRs:** `../../../production/adrs/` — no direct dependency.
- **Source design:**
  - `../final-design.md §"Determinism" #19` — exit criterion.
  - `../final-design.md §"Test plan" §"Determinism canary"` — `test_byte_identical_diff_5x.py` named.
  - `../final-design.md §"Risks (top 5)"` — Risk #2 (determinism flake).
  - `../High-level-impl.md §"Step 7"` — story row.
- **Existing code:**
  - `src/codegenie/recipes/canonicalize.py` (S3-09) — the canonicalizer; idempotence property test already shipped there.
  - `src/codegenie/recipes/digests.yaml` (S3-04) — recipe digest the cache key includes.
  - `src/codegenie/tools/npm.py` (S3-01) — the wrapper that sets `LC_ALL=C` + `--no-audit --no-fund` + `--ignore-scripts`.
  - `src/codegenie/transforms/coordinator.py` (S5-03) — the orchestrator that runs end-to-end.
  - `src/codegenie/cli.py` (S5-05) — `codegenie remediate` entry point.
- **Style reference:**
  - `../../02-context-gather-layers-b-g/stories/S8-05-bench-canaries.md` (if present; otherwise S8-01) — Phase 2's bench/canary story shape.

## Goal

Land `tests/integration/test_byte_identical_diff_5x.py` that runs the full `codegenie remediate` pipeline 5× back-to-back against the `express` bundle from S7-01, asserts byte-identical diffs across all five runs and byte-identical branch tree SHAs, and provides a diagnostically narrow red-fail output that surfaces which of the four determinism mechanisms regressed.

## Acceptance criteria

- [ ] `tests/integration/test_byte_identical_diff_5x.py` exists and is green on `main`.
- [ ] The test runs `codegenie remediate <express bundle> --cve <CVE-XXXX-YYYYY>` (the canary CVE; see implementation outline step 1) exactly **5 times** in sequence, each under a fresh `tmp_path/run_N/` directory; no cache is shared across runs.
- [ ] Each of the five runs produces a `diff.patch` and a `branch_handoff.json` (the latter recording the branch tree SHA per `PatchBranchWriter` output).
- [ ] The test asserts **byte-identical** equality across all five `diff.patch` files (SHA-256 of each compared to run 1).
- [ ] The test asserts **byte-identical** equality across all five branch tree SHAs (the tree SHA recorded by `PatchBranchWriter` in `branch_handoff.json` matches across all five runs).
- [ ] On red-fail, the test surfaces **which of the four determinism mechanisms** regressed: (a) print the `npm --version` observed vs the `tools/digests.yaml` pin; (b) print the `LockfileCanonicalizer` idempotence check result; (c) print the `ncu` invocation's package-resolution output diff across runs; (d) print the recipe digest observed vs the `recipes/digests.yaml` pin. At least three of the four diagnostics surface inline in the failure message; the fourth (`ncu` non-determinism) is documented as a hand-debug step in a docstring + linked runbook.
- [ ] The canary's wall-clock budget is **≤ 5 × the single-run hot-path p95** (S7-04 establishes ~30 s; the canary budget is ≤ 150 s on CI). Each run is timed; the test surfaces the per-run wall-clock in the output for trend monitoring.
- [ ] The test is registered under `pytest.mark.determinism_canary` so the S7-07 CI job (`determinism_canary`) can select it as the sole `pytest` invocation for that workflow.
- [ ] The canary uses **only** the `express` bundle from S7-01 + the `express` recorded resolution + the pinned mirror; no other fixtures are touched. This pins the failure surface (a single bundle + a single recipe + a single engine).
- [ ] A docstring at the top of the test file enumerates the four determinism mechanisms (npm minor pin / canonicalizer / install flags / scripts blocked) and which red-fail output corresponds to each — the failure-mode runbook is **inline in the test**, not in a separate file.
- [ ] The test does **not** rely on the lockfile cache being warm or cold; each run uses its own `tmp_path/run_N/.codegenie/cache/`. The cache is intentionally not shared — the canary tests pipeline determinism, not cache replay determinism (the latter is covered by S7-02's `test_cache_replay_back_references_original_chain_head.py`).

## Implementation outline

1. **Pick the canary CVE.** The `express` bundle from S7-01 carries a known patchable npm CVE — e.g., a `body-parser` or `qs` advisory that `ncu` can resolve to a fixed version in the pinned mirror. The exact CVE id is captured in `tests/fixtures/repos_bundles/express.metadata.yaml` (one-liner — `canary_cve: CVE-XXXX-YYYYY`). The test reads it from the metadata file so the CVE can rotate quarterly without touching the test code.
2. **Build the runner helper.** Under `tests/integration/conftest.py` (extend), add a `run_remediate_into(tmp_path: Path, bundle_name: str, cve_id: str) -> RemediationOutcome` fixture that (a) unpacks the bundle into `tmp_path/work`, (b) sets `LC_ALL=C` + `npm config set registry <mirror_url>`, (c) invokes the CLI via `subprocess.run(["codegenie", "remediate", ...])` capturing exit code + stdout + stderr + the `.codegenie/remediation/<run-id>/` artifact tree, (d) returns a typed `RemediationOutcome(exit_code, diff_path, branch_handoff_path, audit_dir, wall_ms)`.
3. **Write the test body.** Iterate `for i in range(5)`, accumulate outcomes, then assert:
   - `outcomes[0].exit_code == 0` (sanity — happy path).
   - `all(o.exit_code == 0 for o in outcomes)` (all five succeed).
   - For each `i in range(1, 5)`: `sha256(outcomes[i].diff_path.read_bytes()) == sha256(outcomes[0].diff_path.read_bytes())` with a structured failure message naming which run regressed.
   - For each `i in range(1, 5)`: `json.loads(outcomes[i].branch_handoff_path)["tree_sha"] == json.loads(outcomes[0].branch_handoff_path)["tree_sha"]` with the same structured failure message.
4. **Surface the diagnostic on failure.** Wrap the byte-identity assertions in a custom helper `assert_byte_identical_or_diagnose(outcomes)` that, on mismatch, captures and prints:
   - The `npm --version` output from each run's audit slice (look for `npm.install.run` events; record `npm_version` in the payload — extend S3-01's audit emission if needed).
   - The `LockfileCanonicalizer` idempotence check: re-canonicalize each run's lockfile; if not a fixed point, surface the keys that differ.
   - The recipe digest observed in each run's `recipe.selected` audit event; cross-check against `recipes/digests.yaml`.
   - A unified diff of `outcomes[0].diff_path` vs the first divergent run's `diff_path` — the first 200 lines max.
5. **Wire the `determinism_canary` marker.** Register `determinism_canary` in `pyproject.toml`'s `[tool.pytest.ini_options]` `markers` list (S7-07 will reference it). Apply `pytest.mark.determinism_canary` to the test.
6. **Document the failure-mode runbook in the test docstring.** A 30-line docstring at the top of the file enumerates: (a) npm minor pin drift — check `tools/digests.yaml`; (b) canonicalizer regression — run `pytest tests/unit/test_lockfile_canonicalize_idempotent.py`; (c) install-flag regression — grep `tools/npm.py` for `--no-audit`/`--no-fund`/`--ignore-scripts`; (d) recipe digest drift — run `pytest tests/adv/test_recipes_digests_yaml_drift_breaks_load.py`. The runbook is inline so red-fails are self-documenting.

## TDD plan — red / green / refactor

### Red — write the failing test first

Path: `tests/integration/test_byte_identical_diff_5x.py`

```python
"""ADR-0011 | Invariant: codegenie remediate produces byte-identical diff + branch tree SHA on 5 back-to-back runs against the same fixture.

Determinism mechanisms whose joint correctness this canary verifies:

1. Pinned `npm` minor digest in `tools/digests.yaml`.
2. `LockfileCanonicalizer` post-resolve (LC_ALL=C, key sort, LF).
3. `--no-audit --no-fund --ignore-scripts` on every npm install.
4. Pinned local registry mirror (ADR-0012) — removes registry drift.

Red-fail diagnostics (in order of probability):
- npm-version drift → check `tools/digests.yaml` vs host `npm --version`.
- Canonicalizer regression → run `tests/unit/test_lockfile_canonicalize_idempotent.py`.
- Install-flag regression → grep `tools/npm.py` for `--no-audit`, `--no-fund`, `--ignore-scripts`.
- Recipe digest drift → run `tests/adv/test_recipes_digests_yaml_drift_breaks_load.py`.
"""

@pytest.mark.determinism_canary
def test_five_runs_produce_byte_identical_diff(tmp_path, bundle_fixture, npm_mirror_url, run_remediate_into) -> None: ...

@pytest.mark.determinism_canary
def test_five_runs_produce_byte_identical_branch_tree_sha(tmp_path, bundle_fixture, npm_mirror_url, run_remediate_into) -> None: ...

@pytest.mark.determinism_canary
def test_diagnostic_surfaces_npm_version_on_mismatch(monkeypatch, tmp_path, bundle_fixture, npm_mirror_url, run_remediate_into) -> None:
    """If the canary red-fails, the npm version observed in each run is in the failure message."""
```

The third test exercises the diagnostic path: monkeypatch the canonicalizer to introduce a deliberate non-idempotence between runs 2 and 3, and assert the failure message contains the canonicalizer-regression diagnostic.

### Green — make each one pass

Green requires three things to align:

1. **The pipeline is actually deterministic.** This is the load-bearing prerequisite shipped by S3-01 / S3-03 / S3-09 / S5-01 / S5-04. If the canary red-fails on first run, **do not** weaken the test; instead, root-cause to one of the four mechanisms and fix the production code (or, if the cause is environmental drift on the dev laptop, document and fix the CI runner's `npm` install).
2. **The runner helper is faithful.** `run_remediate_into` must invoke the actual CLI subprocess (not the orchestrator function directly), because differences in subprocess env (LC_ALL, PATH ordering, locale) are exactly what this canary is designed to catch. Direct-function invocation would silently bypass the env layer.
3. **The diagnostic helper actually emits the diagnostic on red.** Test 3 (`test_diagnostic_surfaces_npm_version_on_mismatch`) is what verifies this; without it, a future regression that silently drops the diagnostic would be invisible.

The most common first failure: the runner helper invokes the orchestrator function directly instead of the CLI subprocess, and the canary green-passes for the wrong reason (the function-level invocation inherits the test process's LC_ALL=C). Fix: always go through `subprocess.run`.

### Refactor — clean up

After green:

- **Wall-clock budget.** Confirm the canary completes in ≤ 150 s on the CI runner. If it exceeds 150 s, S7-04's hot-path canary is also at risk; surface as a perf-fix follow-up in the PR body. Do **not** raise the canary budget without raising S7-04's budget in lock-step.
- **Confirm the diagnostic-on-failure is actually triggered.** Run a deliberately-broken canary locally (introduce a non-idempotence into the canonicalizer); assert the failure message contains all four diagnostic lines; revert the break.
- **Confirm `pytest.mark.determinism_canary` is registered in `pyproject.toml`** so S7-07 can `pytest -m determinism_canary` cleanly.
- **Open the PR with the canary's wall-clock + per-run breakdown.** Reviewers should see "5 runs, p95 = 28 s, total 142 s" without re-deriving from CI logs.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_byte_identical_diff_5x.py` | The canary; the load-bearing determinism CI gate. |
| `tests/integration/conftest.py` (extend) | New `run_remediate_into` fixture wrapping the CLI subprocess. |
| `tests/fixtures/repos_bundles/express.metadata.yaml` | One-liner pinning the canary CVE id (`canary_cve: CVE-XXXX-YYYYY`) so the CVE can rotate without test edits. |
| `pyproject.toml` (extend) | Register `determinism_canary` pytest marker; S7-07 references it. |

## Out of scope

- **The express bundle + mirror.** S7-01 ships them.
- **The hot-path latency canary.** S7-04 lands `test_hot_path_latency.py`.
- **The cache-hit-rate canary.** S7-04 lands `test_lockfile_cache_hit_rate.py`.
- **The memory regression canary.** S7-04 lands the `resource.getrusage(RUSAGE_CHILDREN)` peak-RSS check.
- **CI workflow wiring.** S7-07 wires the `determinism_canary` job into `.github/workflows/`.
- **Determinism on non-express bundles.** The canary intentionally pins to one bundle to keep the failure surface diagnostically narrow. Multi-bundle determinism is covered indirectly by the perf canary's cache-hit-rate test (S7-04), which runs across the portfolio.
- **Production code changes.** If a determinism mechanism regresses, the fix is in the originating story's production code (S3-01 / S3-03 / S3-09 / S5-01), not in this canary. Surface as a separate PR.

## Notes for the implementer

- **The canary is diagnostically narrow on purpose.** One bundle, one recipe, one engine, one CVE — when it red-fails, you know exactly where to look. Adding more bundles dilutes the signal; resist the urge.
- **`subprocess.run` invocation is load-bearing.** A function-level invocation inherits the test process's environment (LC_ALL, PATH) and silently green-passes the canary for the wrong reason. The canary must invoke the CLI as a subprocess to catch env-layer regressions.
- **The pinned npm minor digest is the most common drift axis.** CI runners update `npm` regularly; without the pin, the canary flakes on the first patch bump. The S7-07 CI job must install the pinned npm binary explicitly; the canary's red-fail diagnostic surfaces the version mismatch so the operator knows to update `tools/digests.yaml` (and re-warm the mirror).
- **`LockfileCanonicalizer` idempotence is checked redundantly.** It's already pinned by S3-09's Hypothesis property test; this canary's diagnostic re-checks at canary-time as a belt-and-braces gate. The redundancy is intentional — the canary's red-fail must surface the cause inline.
- **Wall-clock budget is 5× the hot-path p95.** If S7-04's hot-path budget drifts up, this canary's budget must drift up in lock-step. The two budgets are linked; document the link in the PR body so future budget bumps land together.
- **A canary failure is never "flaky".** It is always a regression in one of the four mechanisms. Treat it like a security alert: the first response is root-cause, not a re-run. Add a runbook entry in `docs/runbooks/canary-fail.md` (if it doesn't exist, S7-07 wires it as part of the operator runbook) describing the "first response" procedure.
- **The diagnostic-on-failure test (#3 above) is what prevents the canary from silently degrading.** Without it, a future PR that drops the diagnostic emission is invisible until the canary actually red-fails — and by then the diagnostic is gone. Pin the diagnostic shape with its own test.
- **The CVE id is in metadata, not in the test code.** Quarterly fixture rotation may swap the canary CVE; the test reads it from `express.metadata.yaml` so the rotation doesn't ripple into the test source. This is the same discipline as the `tests/fixtures/REGENERATION-LOG.md` from S7-01.
- **Do not share `.codegenie/cache/` across the five runs.** The cache hit rate is what S7-04 tests; the canary tests pipeline determinism *without* the cache. Each of the five runs gets a fresh `tmp_path/run_N/.codegenie/cache/`; this is explicit in the runner helper. Mixing the two would conflate two separate guarantees.
