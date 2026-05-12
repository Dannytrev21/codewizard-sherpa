# Story S8-02 — Integration: end-to-end + cache-hit-no-relaunch + real-OSS `nestjs/nest`

**Step:** Step 8 — Adversarial corpus + integration end-to-end + seeded-staleness + goldens + CI gates + Phase 3 handoff
**Status:** Ready
**Effort:** L
**Depends on:** S8-01
**ADRs honored:** ADR-0001 (`consumes_peer_outputs` frozen-snapshot path is exercised end-to-end), ADR-0003 (`network="none"` default; `scoped` only for grype DB + base-image pull), ADR-0004 (`tools/digests.yaml` pin manifest is the only digest surface), ADR-0006 (Pass 4 + Pass 5 round-trip through full pipeline), ADR-0009 (`ExternalDocsProbe` filesystem-only — no URL fetcher launches), ADR-0011 (B2 advisory budget surfaces in `confidence_summary`), ADR-0012 (audit chain head advances exactly once per gather), ADR-0013 (`SCIPIndexProbe` honors existing `node_modules`, never creates one)

## Context

The three load-bearing Phase 2 integration tests land here. They are the **only** tests that exercise the full CLI → coordinator → every probe → sanitizer → audit chain pipeline against a non-trivial repo:

- `tests/integration/test_phase2_end_to_end_node.py` — every Phase 2 slice populated (except `runtime_trace` which is deferred-by-design per ADR-0002); envelope + all 17 sub-schemas validate; cross-probe `if/then` rule (S3-03) fires.
- `tests/integration/test_phase2_cache_hit_no_subprocess_relaunch.py` — gather twice on the same commit; on the second run, **zero subprocess invocations** and every Phase 2 probe records `ProbeExecution.CacheHit`. This is the Phase 1 cache-hit test scaled up to all 22 Phase 2 probe registrations.
- `tests/integration/test_phase2_real_oss.py` — clone `nestjs/nest` at a pinned SHA from a constant; CI setup runs `npm ci --ignore-scripts` outside the gather; commit the matching lockfile snapshot under `tests/fixtures/nestjs_nest_pinned/`. This is **roadmap exit criterion #1** — the proof that a useful `repo-context.yaml` lands on a real Node.js TS repo.

The real-OSS test is the single most brittle CI piece in Phase 2 (`High-level-impl.md §"Implementation-level risks"` #6) — pin the SHA hard, commit the lockfile snapshot, and gate behind a `[real-oss]` pytest marker so a registry hiccup does not block PRs unrelated to Phase 2. The gather runs **without `--strict`**; `IndexHealthProbe` is expected to report `high` across all populated domains for an unstale, unpolluted `nestjs/nest` snapshot.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Goals"` — Phase 2 exit criteria; #1 is `repo-context.yaml` on real OSS; #2 is staleness (handled in S8-03).
  - `../phase-arch-design.md §"Scenarios"` — cold gather, warm cache hit, hostile fixture.
  - `../phase-arch-design.md §"Testing strategy" → "Integration tests"` — the canonical seven-test list (this story lands the first three; S8-03 lands the remaining four).
- **Phase ADRs:**
  - `../ADRs/0001-peer-outputs-binding.md` — exercised end-to-end by `IndexHealthProbe` reading the frozen snapshot.
  - `../ADRs/0003-subprocess-sandbox-profile-extension.md` — `network="none"` is the default; gather must not trigger any scoped-egress except `grype db update` + base-image pull.
  - `../ADRs/0006-output-sanitizer-passes-4-5.md` — every slice goes through Pass 4 + Pass 5.
  - `../ADRs/0009-external-docs-filesystem-only-phase-2.md` — `ExternalDocsProbe` never launches a URL fetcher on this fixture.
  - `../ADRs/0011-index-health-advisory-budget-and-strict-flag.md` — gather runs without `--strict`; B2 returns `confidence: high` on the real-OSS fixture.
  - `../ADRs/0012-audit-chain-blake3-rolling-head.md` — chain head advances exactly once per gather.
  - `../ADRs/0013-scip-node-modules-conditional-mount.md` — `node_modules` is present (CI populated it pre-gather); `SCIPIndexProbe` mounts read-only.
- **Source design:**
  - `../final-design.md §"Roadmap exit criterion #1"` — useful `repo-context.yaml` on a real Node.js TS repo.
  - `../final-design.md §"Synthesis ledger row 9"` — SBOM via `docker build` + `syft`; ledger pins the cache-key shape this test validates is honored.
- **Implementation plan:**
  - `../High-level-impl.md §"Step 8"` — integration test list with assertions; Done criteria #3 ("`test_phase2_real_oss.py` passes against `nestjs/nest` at pinned SHA").
  - `../High-level-impl.md §"Implementation-level risks"` #6 (SHA pin + lockfile commit + `[real-oss]` marker).
- **Existing code:**
  - Every Phase 2 probe under `src/codegenie/probes/`.
  - `tests/integration/test_phase2_external_docs_disabled_by_default.py` (S7-08) — model for the "no URL fetcher" check style.
  - `tests/integration/probes/test_cache_hit_on_real_repo.py` (Phase 1 S2-05 + S5-05) — the `os.scandir` monkeypatch / zero-subprocess approach to extend.
  - `tests/fixtures/node_typescript_with_b_through_g/` (lands earlier in Step 8 if not already; otherwise the integration test creates it as a small Phase 2 fixture upgrading the Phase 1 `node_typescript_helm` with a `Dockerfile`, `.semgrepignore`, etc.).
- **Style reference:** `../../01-context-gather-layer-a-node/stories/S5-05-integration-end-to-end.md` (Phase 1 integration-test pattern: docstring summary lines + `run_gather` fixture + envelope re-validation).

## Goal

Land the three load-bearing Phase 2 integration tests under `tests/integration/` so the end-to-end pipeline is exercised cold (every slice populated), warm (zero subprocess invocations), and on a real OSS repo (roadmap exit criterion #1), and so the CLI is callable from CI on Python 3.11 + 3.12.

## Acceptance criteria

- [ ] `tests/integration/test_phase2_end_to_end_node.py` exists; runs `codegenie gather tests/fixtures/node_typescript_with_b_through_g/` cold; asserts (i) exit 0; (ii) every Phase 2 slice **except** `runtime_trace` is populated (`runtime_trace` carries `{status: "deferred_to_phase_5", reason: ...}`); (iii) the envelope passes `Draft202012Validator`; (iv) each of the 17 Phase 2 sub-schemas validates the matching slice; (v) the cross-probe `if/then` rule (S3-03) holds — `if cve_scan present then index_health.cve.confidence present`; (vi) `audit.chain_head.advanced` fired exactly once; (vii) the docstring opens with `"""Phase 2 exit criterion: every B/C-except-C4/D/E-stub-or-real/G slice populated."""` (PR-body grep contract).
- [ ] `tests/integration/test_phase2_cache_hit_no_subprocess_relaunch.py` exists; gathers the same fixture **twice**; on the second run asserts (i) `ProbeExecution.CacheHit` for every Phase 2 probe registered with a non-`none` `cache_strategy` (probes with `cache_strategy="none"` like `IndexHealthProbe` re-run); (ii) **zero subprocess invocations** on the second run — monkeypatch `codegenie.exec.run_in_sandbox` (or its private equivalent) and assert call_count == 0; (iii) the second-run wall-clock is ≤ 5% of the first-run wall-clock (advisory; matches the warm-path bench in S8-05 but here as a CI-gating sanity check, not the bench).
- [ ] `tests/integration/test_phase2_real_oss.py` exists, gated behind `pytest.mark.real_oss`; (i) the `nestjs/nest` SHA is a **top-level module constant** `NESTJS_NEST_SHA = "<sha>"` (not embedded mid-test); (ii) CI setup (via `conftest.py` or a `pytest-bdd`-style `@pytest.fixture(scope="module")`) clones the repo at that SHA into `tmp_path` and runs `npm ci --ignore-scripts` **outside** the gather; (iii) the matching `package-lock.json` snapshot is committed under `tests/fixtures/nestjs_nest_pinned/package-lock.json` to make CI deterministic; (iv) `codegenie gather` runs **without `--strict`**; (v) exit 0; (vi) the produced `repo-context.yaml` contains: `index_health.cve.confidence == "high"`, `index_health.scip.confidence in {"high", "medium"}`, `sbom.packages` non-empty, `cve.matches` is a list (may be empty), `semgrep.findings_summary` populated, `gitleaks.findings_summary` populated, `build_graph.resolution_status in {"static_only", "resolved"}`; (vii) the docstring opens with `"""Roadmap exit criterion #1: GREEN — useful repo-context.yaml on nestjs/nest at <SHA>."""`.
- [ ] `tests/fixtures/nestjs_nest_pinned/README.md` documents (a) the pinned SHA, (b) how to regenerate `package-lock.json` for a SHA bump, (c) why the SHA is pinned (CI determinism + roadmap exit criterion #1); the README is the cited source when a future contributor proposes a SHA bump.
- [ ] All three tests pass on **Python 3.11 and 3.12** (CI matrix).
- [ ] `tests/integration/test_phase2_real_oss.py` is **excluded** from the default `pytest` selector and runs only when `pytest -m real_oss` is invoked (CI workflow has a separate `real_oss` job — wired in S8-06).
- [ ] The three integration tests together complete in **< 180 s wall-clock** on the CI runner (real-OSS is the long pole — ~120 s for `nestjs/nest` + ~60 s for the other two combined).
- [ ] No new top-level dep introduced. The `nestjs/nest` clone uses `git` (already on `ALLOWED_BINARIES`); no `gitpython` for the clone step (test-only stdlib `subprocess` is fine because the **test harness** is allowed to invoke `git` — only `codegenie/` source code is bound by `ALLOWED_BINARIES`).

## Implementation outline

1. **Build `tests/fixtures/node_typescript_with_b_through_g/`** if Step 7 has not already. The Phase 1 `node_typescript_helm` fixture is the seed; extend with: a minimal `Dockerfile` (Node 20 base image, `WORKDIR /app`, `COPY package.json package-lock.json ./`, `RUN npm ci --ignore-scripts`, `COPY . .`, `CMD ["node", "dist/index.js"]`), a `.semgrepignore`, a top-level `CODEOWNERS`, a `docs/external/` directory with one markdown file (for `ExternalDocsProbe`), and a `SKILL.md` under `.codegenie/skills/` (for `SkillsIndexProbe`). The fixture stays under 500 KB on disk.
2. **`test_phase2_end_to_end_node.py`:**
   - Use the Phase 0/1 `run_gather` pytest fixture.
   - Run cold; assert exit 0.
   - Read `repo-context.yaml`; iterate `EXPECTED_PHASE_2_SLICES = (...)` (define as a module constant — every B/C-except-C4/D/E-real/G slice + the 5 Layer D + 4 Layer E stubs + `runtime_trace` deferred).
   - For each slice (a) assert presence, (b) validate against `src/codegenie/schema/probes/<slice>.schema.json` via `jsonschema.Draft202012Validator`, (c) for `runtime_trace` specifically assert `status == "deferred_to_phase_5"`.
   - Re-validate the envelope schema separately.
   - Capture structlog and assert `audit.chain_head.advanced` count == 1.
   - Verify the cross-probe `if/then` rule by reading the envelope and asserting `cve_scan` present ⇒ `index_health.cve.confidence` present.
3. **`test_phase2_cache_hit_no_subprocess_relaunch.py`:**
   - Run gather once cold; verify exit 0.
   - Patch `src/codegenie/exec.run_in_sandbox` to a `MagicMock(wraps=real_run_in_sandbox)` for the second run; alternative: patch at the `tools.<x>.run` seam (cleaner but more wrappers).
   - Run gather a second time **without** clearing `.codegenie/cache/`.
   - Assert `mock_run_in_sandbox.call_count == 0` on the second run.
   - Assert the audit record's `ProbeExecution` enum value is `CacheHit` for every probe with `cache_strategy != "none"`.
   - Time both runs; assert `t2 < 0.05 * t1` (advisory ratio; if fails locally, profile via `pytest --durations=20`).
4. **`test_phase2_real_oss.py`:**
   - Define `NESTJS_NEST_SHA` at module top — pick a recent stable-tag SHA (e.g. a v10.x tag's commit) and document the pick in `tests/fixtures/nestjs_nest_pinned/README.md`.
   - `@pytest.fixture(scope="module")` clones the repo into `tmp_path_factory.mktemp("nestjs")` at the pinned SHA; copies the committed `package-lock.json` over the repo's; runs `npm ci --ignore-scripts` outside the gather.
   - Run `codegenie gather` against the cloned path.
   - Assert each slice's expected shape (the criterion (vi) list).
   - Mark the test with `@pytest.mark.real_oss`.
5. **`tests/fixtures/nestjs_nest_pinned/package-lock.json`** — generated locally once by checking out the pinned SHA and running `npm ci --ignore-scripts --package-lock-only`; commit the result. Document in the README how to regenerate.
6. **`tests/conftest.py`** registers the `real_oss` marker via `pytest.ini_options` (or `pyproject.toml` `[tool.pytest.ini_options]`) so `pytest --strict-markers` does not fail.

## TDD plan — red / green / refactor

### Red — write the failing test first

Start with `test_phase2_end_to_end_node.py` because it surfaces every Phase 2 probe at once; if any one slice fails to populate, the red points at the probe.

Path: `tests/integration/test_phase2_end_to_end_node.py`

```python
"""Phase 2 exit criterion: every B/C-except-C4/D/E-stub-or-real/G slice populated."""
from pathlib import Path

import jsonschema
import yaml

EXPECTED_PHASE_2_SLICES = (
    "build_graph", "index_health", "scip_index", "node_reflection", "generated_code",
    "dockerfile", "shell_usage", "certificate", "entrypoint", "runtime_trace",
    "sbom", "cve",
    "semgrep", "gitleaks", "ast_grep", "invariant_hints", "grep", "test_coverage_map",
    "repo_config", "adr", "convention", "policy", "exception",
    "skills_index", "repo_notes", "external_docs", "external_docs_index", "ownership",
    "service_topology", "service_contract", "slo", "production_config",
)


def test_every_phase_2_slice_populated(tmp_path, run_gather, structlog_capture):
    fixture = Path("tests/fixtures/node_typescript_with_b_through_g").resolve()
    result = run_gather(fixture, cache_dir=tmp_path / "cache")
    assert result.exit_code == 0
    probes = result.context["probes"]

    for slice_name in EXPECTED_PHASE_2_SLICES:
        assert slice_name in probes, f"missing slice: {slice_name}"

    assert probes["runtime_trace"]["status"] == "deferred_to_phase_5"

    envelope = yaml.safe_load(Path("src/codegenie/schema/repo_context.schema.json").read_bytes())
    jsonschema.Draft202012Validator(envelope).validate(result.context)

    if "cve_scan" in probes:
        assert "confidence" in probes["index_health"]["cve"], (
            "cross-probe if/then rule (S3-03) violated"
        )

    advanced = [e for e in structlog_capture.events if e.get("event") == "audit.chain_head.advanced"]
    assert len(advanced) == 1
```

Path: `tests/integration/test_phase2_cache_hit_no_subprocess_relaunch.py`

```python
"""Phase 2 warm-path: zero subprocess invocations on the second gather."""
from pathlib import Path
from unittest.mock import patch


def test_second_run_invokes_no_subprocess(tmp_path, run_gather):
    fixture = Path("tests/fixtures/node_typescript_with_b_through_g").resolve()
    first = run_gather(fixture, cache_dir=tmp_path / "cache")
    assert first.exit_code == 0

    with patch("codegenie.exec.run_in_sandbox") as mock_run:
        mock_run.side_effect = AssertionError("ADR-0001 warm-path: no subprocess on second gather")
        second = run_gather(fixture, cache_dir=tmp_path / "cache")
    assert second.exit_code == 0
    assert mock_run.call_count == 0
```

### Green — make it pass

For `test_phase2_end_to_end_node.py`, a slice that fails to populate points at the responsible probe (Step 3–7 follow-up). If `runtime_trace` is missing entirely, S5-04's "constant-content `ProbeOutput`" path is broken. If `cve.confidence` is missing when `cve_scan` is present, S3-01 or S3-03 needs the dependency rule.

For the cache-hit test, a subprocess invocation on the second run typically means a wrapper is bypassing the cache; trace via `pytest --capture=no` and identify which probe re-invoked.

For the real-OSS test, the most likely first failure is the `npm ci --ignore-scripts` step at the test fixture's clone step — verify the lockfile snapshot is byte-identical to what `nestjs/nest`'s pinned SHA would produce. The README documents the regeneration recipe.

### Refactor — clean up

After green:

- Confirm each test's PR-body grep contract docstring is present.
- Verify the `real_oss` marker is registered in `pyproject.toml` `[tool.pytest.ini_options]`.
- Verify the three tests run on Python 3.11 and 3.12 (CI matrix). Local `tox -e py311,py312` if available.
- Profile the real-OSS test; if it exceeds 180 s, the `npm ci` step is probably re-resolving rather than honoring the lockfile — verify the `--prefer-offline --no-audit --no-fund` flags are set in the fixture's setup.
- Run the cache-hit test under `-c1` (single-worker) to confirm no async race-condition flake.

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/test_phase2_end_to_end_node.py` | New — every-slice exit criterion. |
| `tests/integration/test_phase2_cache_hit_no_subprocess_relaunch.py` | New — warm-path zero-subprocess. |
| `tests/integration/test_phase2_real_oss.py` | New — roadmap exit criterion #1. |
| `tests/fixtures/nestjs_nest_pinned/package-lock.json` | New — committed deterministic lockfile snapshot. |
| `tests/fixtures/nestjs_nest_pinned/README.md` | New — SHA pin rationale + regeneration recipe. |
| `tests/fixtures/node_typescript_with_b_through_g/` | New (or extended from Phase 1 helm fixture) — populates every Phase 2 slice. |
| `pyproject.toml` | Register `real_oss` marker under `[tool.pytest.ini_options].markers`. |
| `tests/conftest.py` (extend) | Module-scoped `nestjs_nest_clone` fixture; structlog capture if not already. |

## Out of scope

- **Seeded-staleness fixtures + `--strict` integration** — handled by **S8-03**.
- **Per-probe goldens** — handled by **S8-04**.
- **Bench canaries** (warm-path, B2 budget, SCIP re-index, cold e2e) — handled by **S8-05**.
- **CI workflow wiring of the `real_oss` job** — handled by **S8-06**.
- **Adversarial corpus expansion** — handled by **S8-01** (precedes this story).
- **Modifying probe behavior** to make a slice populate. If a probe fails to populate its slice on the integration fixture, file as a Step 3–7 follow-up in the PR body; do not patch the probe here.

## Notes for the implementer

- **The real-OSS test is the most brittle CI piece in Phase 2.** Pin the SHA. Commit the lockfile. Use the `real_oss` marker. The cost of getting this wrong is a CI failure on a PR unrelated to Phase 2 because the registry threw a 503 — and that erodes trust in the gate. The marker isolation is non-negotiable.
- **`runtime_trace` is `deferred_to_phase_5`, not missing.** The `EXPECTED_PHASE_2_SLICES` constant must include `runtime_trace`; the assertion is on the **status**, not on presence-vs-absence. S5-04's constant-content contract is what makes this test green.
- **The cache-hit test's `MagicMock(side_effect=AssertionError(...))` is intentional.** If any subprocess fires on the second run, the assertion error surfaces with a clear message rather than a silent wrong-answer. Do not weaken to `mock_run.call_count == 0` only — the side-effect is the defense.
- **`IndexHealthProbe.cache_strategy == "none"`** — the cache-hit test must not assert `CacheHit` for B2; it always re-runs on a fresh snapshot. The `EXPECTED_CACHEABLE_PROBES` filter is `{p for p in registered if p.cache_strategy != "none"}` — derive this dynamically, do not hand-list.
- **`nestjs/nest` is the canonical Phase 2 real-OSS fixture.** It exercises every Layer B/C-except-C4/D/G probe meaningfully. Do not substitute a smaller repo — the exit criterion specifically names a "real Node.js TS repo with every B/C-except-C4/D/E-stub-or-real/G slice." A toy substitute is not the criterion.
- **The `npm ci --ignore-scripts` step runs *outside* the gather.** The gather itself never invokes `npm install` (ADR-0013). The fixture is set up before the gather is invoked; the gather then observes a populated `node_modules/`.
- **PR-body grep contracts.** The two docstring-as-contract lines (`"""Phase 2 exit criterion: ..."""` and `"""Roadmap exit criterion #1: GREEN — ..."""`) make S8-06's exit-criteria checklist mechanical. Include them; they are how the team confirms the criterion is hit without re-running every test by hand.
- **The cross-probe `if/then` assertion** in the end-to-end test must not be silently skipped when `cve_scan` is absent. If the test fixture does not produce a `cve_scan` slice (e.g., grype DB is offline in dev), the test's assertion line is dead. Add a `pytest.skip` with a clear message if `cve_scan` is genuinely absent, and ensure the **real-OSS test** confirms the rule fires (the OSS fixture **does** produce `cve_scan`).
