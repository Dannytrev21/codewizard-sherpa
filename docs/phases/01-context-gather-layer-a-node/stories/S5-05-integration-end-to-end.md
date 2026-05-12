# Story S5-05 — Layer A end-to-end integration + cache-hit-all-six + non-Node + prelude pass

**Step:** Step 5 — Adversarial corpus + integration end-to-end + fixture portfolio
**Status:** Ready
**Effort:** M
**Depends on:** S5-01, S5-02, S5-03, S5-04
**ADRs honored:** ADR-0004 (per-probe sub-schema `additionalProperties: false`), ADR-0010 (Layer A slices optional at envelope), ADR-0002 (`ParsedManifestMemo` + `input_snapshot` on `ProbeContext`)

## Context

This story lands the five integration tests that make the **roadmap Phase 1 exit criteria** demonstrably green in CI. Each test runs `codegenie gather` end-to-end through the CLI against a fixture and asserts a load-bearing structural property.

- `test_layer_a_end_to_end.py` — **roadmap exit criterion #1**: "useful `repo-context.yaml` produced on a real Node.js repo" — proxied by `node_typescript_helm`. All six Layer A slices populated; envelope + six sub-schemas pass; audit anchor re-computes.
- `test_cache_hit_on_real_repo.py` — **roadmap exit criterion #2** extension: gather twice; **all six** probes report `ProbeExecution.CacheHit` on the second run. S2-05 covered two probes; this story extends to six. The `os.scandir` monkeypatch and `probe.cache_hit` structlog assertion both hold.
- `test_non_node_repo.py` — ADR-0010 contract test: a Go-only repo produces an envelope with **only** `language_stack` populated; the five Phase-1 Node-only probes are filtered out by `Registry.for_task`.
- `test_monorepo_turbo.py` — `LanguageDetectionProbe.monorepo` populated when the fixture has both `turbo.json` and `package.json#workspaces`; the root-level `node_build_system` slice produced (workspace-member traversal is Phase 2's concern, not asserted here).
- `test_coordinator_prelude.py` — Phase 0 Gap-#4 + Phase 1 reinforcement: Wave-1 `LanguageDetectionProbe` completes before Wave-2 dispatch, and `enriched_snapshot.detected_languages` is populated when Wave-2 probes run.

This is the convergence point of Step 5: S5-01/-02/-03 prove the defenses; S5-04 ships the fixture portfolio; this story exercises the whole stack end-to-end.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Goals"` — Phase 1 exit criteria.
  - `../phase-arch-design.md §"Scenarios"` Scenario 1 (cold gather), Scenario 2 (warm cache hit), Scenario 4 (non-Node) — the runtime paths this story asserts.
  - `../phase-arch-design.md §"Testing strategy" → "Integration tests"` — the five-test inventory.
  - `../phase-arch-design.md §"Component design" — Coordinator prelude pass`.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0004-per-probe-subschema-additional-properties-false.md` — the envelope + six sub-schemas all pass validation.
  - `../ADRs/0010-layer-a-slices-optional-at-envelope.md` — the non-Node case validates with only `language_stack`.
  - `../ADRs/0002-parsed-manifest-memo-on-probe-context.md` — the memo seam is what makes the warm-path test green.
- **Source design:**
  - `../final-design.md §"Test plan"` → "Integration tests" — the canonical five-test list.
  - `../final-design.md §"Failure modes & recovery"` — informs negative-case integration coverage.
  - `../High-level-impl.md §"Step 5"` — integration-test list with assertions.
- **Existing code (lands earlier — must be on disk before this story starts):**
  - All six Layer A probes (S2-01 + S2-02 + S3-05 + S4-01 + S4-02 + S4-03).
  - All five fixtures (S2-03, S3-06 ×2, S5-04 ×2).
  - Coordinator prelude pass (S1-07 + S1-08 wiring).
  - `tests/integration/probes/test_cache_hit_on_real_repo.py` (S2-05) — this story **extends** the existing file, not creates anew.
- **Style reference:** `../../00-bullet-tracer-foundations/stories/S4-02-cli-gather-audit-verify.md` (Phase 0 integration-test pattern + style).

## Goal

Five integration tests under `tests/integration/probes/` are green in CI, asserting Phase 1's load-bearing structural commitments end-to-end through the CLI against the fixture portfolio.

## Acceptance criteria

- [ ] `tests/integration/probes/test_layer_a_end_to_end.py` exists; runs `codegenie gather tests/fixtures/node_typescript_helm/` cold (clean `.codegenie/` cache); asserts (i) exit 0; (ii) all six slices populated in `repo-context.yaml` — `language_stack`, `build_system`, `manifests`, `ci`, `deployment`, `test_inventory`; (iii) envelope + six per-probe sub-schemas pass `Draft202012Validator` validation; (iv) the audit anchor (Phase 0) re-computes successfully (verify-anchor exits 0 on the written audit record).
- [ ] `tests/integration/probes/test_cache_hit_on_real_repo.py` (the file landed in S2-05) is **extended**: the existing two-probe assertion (`LanguageDetectionProbe` + `NodeBuildSystemProbe`) becomes a six-probe assertion (add `NodeManifestProbe`, `CIProbe`, `DeploymentProbe`, `TestInventoryProbe`); the `os.scandir`-zero-invocations assertion on the second run holds; the `probe.cache_hit` structlog event count equals 6 on the second run.
- [ ] `tests/integration/probes/test_non_node_repo.py` exists; runs `codegenie gather tests/fixtures/non_node_go/`; asserts (i) exit 0; (ii) `repo-context.yaml` contains the `language_stack` slice with `primary: "go"`; (iii) the `probes` block does **not** contain any of `build_system`, `manifests`, `ci`, `deployment`, `test_inventory` keys (absent, not null — per ADR-0010); (iv) envelope passes schema validation; (v) the five Node-only probes recorded `ProbeExecution.Skipped` in the audit run-record (verified via `Registry.for_task` filtering on `applies_to_languages`).
- [ ] `tests/integration/probes/test_monorepo_turbo.py` exists; runs `codegenie gather tests/fixtures/node_monorepo_turbo/`; asserts (i) exit 0; (ii) `language_stack.monorepo` is non-null and populated; (iii) `language_stack.monorepo.markers` (or whatever the S2-01 sub-schema names the field) contains both `turbo.json` and `package.json#workspaces`; (iv) the root-level `build_system` slice is populated (root-level `package.json`'s `scripts`, lockfile detection, etc.); (v) no assertion is made about workspace-member traversal — explicitly Phase 2's concern.
- [ ] `tests/integration/probes/test_coordinator_prelude.py` exists; runs `codegenie gather tests/fixtures/node_typescript_helm/`; captures the structlog event stream; asserts (i) the `language_detection` probe's `probe.success` event precedes every Wave-2 probe's `probe.start` event (timestamp ordering); (ii) the `enriched_snapshot.detected_languages` field is populated when Wave-2 probes run (verified by inspecting one Wave-2 probe's input via a debug hook or by reading the audit record's snapshot fingerprint); (iii) the prelude completes in the order documented in `phase-arch-design.md §"Scenarios"` Scenario 1.
- [ ] Each test passes on Python 3.11 and 3.12 (CI matrix).
- [ ] The five integration tests together complete in under 30 s wall-clock on the developer's machine (the test_layer_a_end_to_end is the long pole; budget it ~10 s).
- [ ] At least one test (`test_layer_a_end_to_end.py` is the natural fit) emits a structured PR-body summary line: "Phase 1 exit criterion #1: GREEN — all six slices populated, envelope + 6 sub-schemas validated." This is a docstring-as-contract — the line is grep-able from the PR body for the Step 6 PR.

## Implementation outline

1. **`tests/integration/probes/test_layer_a_end_to_end.py`:** Use the Phase-0 `run_gather` fixture (or whichever fixture invokes the CLI and returns parsed output). Run cold by setting `--cache-dir` to a `tmp_path` location. Read the output `repo-context.yaml`; assert every slice key is present and non-empty. Re-validate the envelope + per-probe sub-schemas using `jsonschema.Draft202012Validator` directly (don't rely on the CLI's validator alone). Run `codegenie verify-anchor` against the audit record and assert exit 0.
2. **Extend `tests/integration/probes/test_cache_hit_on_real_repo.py`:** Read the existing file. The two-probe assertion lives there from S2-05. Replace the literal `{"language_detection", "node_build_system"}` set with `{"language_detection", "node_build_system", "node_manifest", "ci", "deployment", "test_inventory"}`. Verify the `os.scandir` monkeypatch is at the `codegenie.probes.language_detection.os.scandir` namespace (S2-05 documented the right path); add monkeypatches for any other probe that uses `os.scandir` if necessary (`TestInventoryProbe` uses `os.walk`, which uses `os.scandir` internally — verify whether the cache-hit path skips it entirely or if it needs its own monkeypatch). Adjust the `probe.cache_hit` event-count assertion from 2 to 6.
3. **`tests/integration/probes/test_non_node_repo.py`:** Run gather against `non_node_go/`. Read the output YAML. Assert the `probes` mapping contains exactly `{"language_stack"}` (or the broader subset Phase 0 also writes — confirm at land-time). Inspect the audit record for `ProbeExecution.Skipped` entries for the five Node probes. Validate the envelope (it must pass — ADR-0010's contract).
4. **`tests/integration/probes/test_monorepo_turbo.py`:** Run gather against `node_monorepo_turbo/`. Read the output. Assert `language_stack.monorepo` is non-null (the S2-01 sub-schema's optional block). Assert both markers are recorded. Assert the root-level `build_system` slice is non-null (Phase 1 doesn't recurse into workspaces, but it does process the root).
5. **`tests/integration/probes/test_coordinator_prelude.py`:** This is the structurally novel test. Approach:
   - Install a structlog capture (Phase-0 fixture pattern).
   - Run gather; collect all logged events in order.
   - Filter to `probe.start` and `probe.success` events; assert `language_detection`'s `probe.success` timestamp is `<` every other probe's `probe.start` timestamp.
   - For `enriched_snapshot.detected_languages` population: the cleanest way is to find one Wave-2 probe (e.g. `NodeBuildSystemProbe`) that logs its `snapshot.detected_languages` on `probe.start` (a Phase-0 structlog context binding) and assert the field is non-empty.
   - If no such binding exists, **add a debug-only structlog field** in S1-07's coordinator wiring to expose it; surface that as a small follow-up in the PR body.

## TDD plan — red / green / refactor

### Red — write the failing test first

Start with `test_layer_a_end_to_end.py` (the most direct exit-criterion assertion); then the cache-hit extension; then `test_non_node_repo.py`; then `test_monorepo_turbo.py`; then `test_coordinator_prelude.py`.

```python
# tests/integration/probes/test_layer_a_end_to_end.py
"""Roadmap Phase 1 exit criterion #1: GREEN — all six Layer A slices populated."""
from pathlib import Path

import jsonschema
import pytest
import yaml

PHASE_1_SLICES = (
    "language_stack",
    "build_system",
    "manifests",
    "ci",
    "deployment",
    "test_inventory",
)


def test_layer_a_end_to_end_node_typescript_helm(tmp_path, run_gather):
    fixture = Path("tests/fixtures/node_typescript_helm").resolve()
    result = run_gather(fixture, cache_dir=tmp_path / "cache")
    assert result.exit_code == 0
    probes = result.context["probes"]
    for slice_name in PHASE_1_SLICES:
        assert slice_name in probes, f"missing slice: {slice_name}"
        assert probes[slice_name], f"empty slice: {slice_name}"

    # Envelope + per-probe sub-schemas validate
    envelope_schema = yaml.safe_load(Path("src/codegenie/schema/repo_context.schema.json").read_bytes())
    jsonschema.Draft202012Validator(envelope_schema).validate(result.context)
    for slice_name in PHASE_1_SLICES:
        sub_schema_path = Path(f"src/codegenie/schema/probes/{slice_name}.schema.json")
        # language_stack lives under language_detection.schema.json — adjust at land-time
        if not sub_schema_path.exists():
            continue
        sub_schema = yaml.safe_load(sub_schema_path.read_bytes())
        jsonschema.Draft202012Validator(sub_schema).validate(probes[slice_name])
```

```python
# tests/integration/probes/test_non_node_repo.py (ADR-0010 contract test)
from pathlib import Path


def test_non_node_go_validates_with_only_language_stack(tmp_path, run_gather):
    fixture = Path("tests/fixtures/non_node_go").resolve()
    result = run_gather(fixture, cache_dir=tmp_path / "cache")
    assert result.exit_code == 0
    probes = result.context["probes"]
    assert "language_stack" in probes
    assert probes["language_stack"]["primary"] == "go"
    # The five Node-only probes are absent (key not present)
    for k in ("build_system", "manifests", "test_inventory"):
        assert k not in probes, f"{k} should be absent on a non-Node repo (ADR-0010)"
    # ci/deployment may run if the repo has those markers; non_node_go has neither
    assert "ci" not in probes
    assert "deployment" not in probes
```

```python
# tests/integration/probes/test_coordinator_prelude.py
from pathlib import Path


def test_wave_1_language_detection_precedes_wave_2(tmp_path, run_gather, structlog_capture):
    fixture = Path("tests/fixtures/node_typescript_helm").resolve()
    result = run_gather(fixture, cache_dir=tmp_path / "cache")
    assert result.exit_code == 0
    events = structlog_capture.events
    ld_success_idx = next(
        i for i, e in enumerate(events)
        if e.get("event") == "probe.success" and e.get("probe") == "language_detection"
    )
    wave_2_starts = [
        i for i, e in enumerate(events)
        if e.get("event") == "probe.start" and e.get("probe") != "language_detection"
    ]
    assert wave_2_starts, "no Wave-2 probe started — fixture isn't exercising the path"
    assert all(i > ld_success_idx for i in wave_2_starts), \
        "Wave-2 probes started before LD completed — prelude pass broken"
```

Each red asserts a structural property the current code may or may not deliver. The probable failure modes:
- `test_layer_a_end_to_end`: a slice is empty (probe failed silently) — surface in PR; investigate which probe and fix.
- `test_non_node_repo`: a probe ran when it shouldn't (`applies_to_languages` filter wrong) — fix in S2-02 / S3-05 / S4-03.
- `test_coordinator_prelude`: Wave-2 probe started before LD — S1-07's prelude wiring is broken.

### Green — make it pass

If a red fails because a probe is broken in a way that's not "the test is wrong," fix the probe and surface the fix in the PR body as a "S2-XX follow-up" / "S3-XX follow-up" reference. The five integration tests are the final QA gate for Phase 1; expect to surface 1–3 small fixes during this story.

For the extended cache-hit test: the `os.scandir` monkeypatch may need to be applied at additional module paths if probes outside `language_detection` use `os.scandir` directly. Check `node_manifest.py`, `test_inventory.py`, `deployment.py` — any direct `os.scandir`/`os.walk` call needs the same monkeypatch. The cache-hit path should skip all of them; the test's job is to assert that.

### Refactor — clean up

After green:

- Add the docstring summary lines to each test (the PR-body-grep contract).
- Verify each test's wall-clock locally; if `test_layer_a_end_to_end` exceeds 10 s, profile via `pytest --durations=5` and identify the slow probe (likely deployment + Helm chart parsing).
- Ensure each test cleans up `.codegenie/` cache (use `tmp_path` for cache-dir, never the repo's `.codegenie/`).
- Verify the structlog capture fixture's events are deterministic across runs (no race-condition reordering in async code) — if Wave-2 events occasionally interleave with LD in an unexpected way, `test_coordinator_prelude` may flake. Use `--count=10` locally to confirm stability before opening the PR.
- Confirm each test passes both on macOS and Linux (CI matrix).

## Files to touch

| Path | Why |
|---|---|
| `tests/integration/probes/test_layer_a_end_to_end.py` | New — roadmap exit criterion #1 |
| `tests/integration/probes/test_cache_hit_on_real_repo.py` | **Extend** the S2-05 file from 2 probes to all 6 (exit criterion #2) |
| `tests/integration/probes/test_non_node_repo.py` | New — ADR-0010 contract test |
| `tests/integration/probes/test_monorepo_turbo.py` | New — S2-01 monorepo block exercised |
| `tests/integration/probes/test_coordinator_prelude.py` | New — Phase 0 Gap-#4 + Phase 1 reinforcement |

## Out of scope

- **Golden-file diffing against `node_typescript_helm`** — owned by S6-01.
- **Bench canaries (warm-path latency, per-probe RSS)** — owned by S6-02.
- **Coverage ratchet to 90/80** — owned by S6-02.
- **Real-OSS-repo integration test** (e.g. cloning `expressjs/express` at a pinned SHA) — explicitly deferred per `final-design.md §"Tests explicitly not in Phase 1"`; the `node_typescript_helm` fixture is the proxy.
- **Multi-language monorepo integration test** — Phase 2 concern.
- **Workspace-member-level probe assertion** in `test_monorepo_turbo.py` — explicit Phase 2 carve-out.

## Notes for the implementer

- **The "all six slices" assertion in `test_layer_a_end_to_end.py` is the single most important assertion in Phase 1.** If any one slice is empty on `node_typescript_helm`, the roadmap exit criterion #1 is not met. Treat a failure here as P0; the fix may be in any of S2-01 / S2-02 / S3-05 / S4-01 / S4-02 / S4-03. The S5-05 PR may legitimately need to land a small follow-up to a probe to make the slice non-empty.
- **The cache-hit-all-six test is the load-bearing test for `phase-arch-design.md §"Goals"` — "Cache hits on second run (all six Layer A probes)."** S2-05 covered 2; this story covers 6. If a probe's `os.scandir` invocation count is non-zero on the second run (despite `ProbeExecution.CacheHit`), the cache is being looked up but the walker still ran — that's a Phase-0 / Step-1 wiring bug. Surface explicitly.
- **`test_non_node_repo.py`'s "absent, not null" assertion (ADR-0010).** A slice that's been filtered out by `Registry.for_task` should not appear as a key in `probes`. If a probe ran but produced an empty slice, the key would be present with empty contents — that's a different failure mode (probe should have been filtered, but wasn't). The test asserts `"build_system" not in probes`, not `probes["build_system"] is None`.
- **`test_monorepo_turbo.py` does NOT assert workspace-member traversal.** `phase-arch-design.md §"Open questions"` lists workspace traversal as Phase 2's concern. Resist adding assertions about `packages/app-web/package.json` being individually probed; that's not Phase 1's contract.
- **`test_coordinator_prelude.py` may need a small coordinator extension** (S1-07) to expose `enriched_snapshot.detected_languages` to structlog. If the field isn't observable, add a `logger.bind(detected_languages=...)` call in the coordinator's Wave-2-dispatch path. That's an in-scope extension of S1-07's deliverable, not a contract change.
- **The PR-body grep contract** ("Phase 1 exit criterion #1: GREEN — ...") is what makes the Step 6 (`S6-03`) close-out story's job mechanical. Don't omit the line; it's how the team confirms the criterion is hit without re-running every test manually.
- **Watch for flakiness in `test_coordinator_prelude.py`.** Async code with concurrent probes can interleave structlog events in surprising ways. The assertion is "LD completes before any Wave-2 starts," which is structurally correct under the prelude pass — but if S1-07's wiring dispatches Wave-2 *concurrently* with LD's success-logging (race condition), the test can flake. Stabilize by asserting on the **probe's own success/start log lines**, not the coordinator's dispatch events.
- **Walltime budget for this story's tests:** 30 s total. `test_layer_a_end_to_end` is the long pole (~10 s for a full cold gather on a 6-probe fixture); the other four are sub-3 s each. If the total exceeds 30 s locally, profile with `pytest --durations=10` and consider whether the fixture can be slimmed (without breaking S2-03's contract — coordinate with that story's owner if needed).
