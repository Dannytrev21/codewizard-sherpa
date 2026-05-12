# Story S8-04 — Per-probe goldens for every Phase 2 probe + `regen_golden.py` extension

**Step:** Step 8 — Adversarial corpus + integration end-to-end + seeded-staleness + goldens + CI gates + Phase 3 handoff
**Status:** Ready
**Effort:** M
**Depends on:** S8-02
**ADRs honored:** ADR-0004 (digest pin manifest stabilizes external-tool output across runs), ADR-0006 (sanitizer Pass 4 + Pass 5 produce deterministic outputs given deterministic inputs — Pass 4 fingerprints are content-derived; Pass 5 marker counts are integer-valued), ADR-0011 (B2 `confidence_summary` is a function of peer-output snapshot only — deterministic), ADR-0012 (golden excludes the rolling chain head and audit timestamps; Phase-1 risk #8 carried forward)

## Context

Every Phase 2 probe ships **at least one golden** under `tests/golden/<probe>/<fixture>/expected.json`. The golden is the byte-for-byte expected output of the probe's slice (after sanitizer Pass 1–5, before envelope merging) given a fixed input. CI diffs the live output against the golden; any drift is a hard fail.

The Phase 1 `scripts/regen_golden.py` already exists for the six Layer A probes; this story **extends** it for the 17 Phase 2 probes — `IndexHealthProbe`, `BuildGraphProbe`, `SCIPIndexProbe`, `NodeReflectionProbe`, `GeneratedCodeProbe`, `DockerfileProbe`, `ShellUsageProbe`, `CertificateProbe`, `EntrypointProbe`, `RuntimeTraceProbe` (the deferred constant-content slice), `SyftSBOMProbe`, `GrypeCVEProbe`, `SemgrepProbe`, `GitleaksProbe`, `AstGrepProbe`, `InvariantHintProbe`, `GrepProbe`, `TestCoverageMappingProbe`, the 7 Layer D probes, `OwnershipProbe`, the 4 Layer E stubs (each stub has a trivial golden — `{"status": "not_applicable", "reason": "..."}`) — count = 22 probe goldens minimum.

The non-determinism risk (`High-level-impl.md §"Implementation-level risks"` #8) is real and Phase-1-carried: wall-clock fields, audit timestamps, and the rolling BLAKE3 chain head must be **excluded** by the regen script. The story's safety check is: run regen **twice locally** and verify byte-identical output before opening the PR.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Testing strategy" → "Golden tests"` — per-probe golden discipline.
  - `../phase-arch-design.md §"Component design"` (every probe section names its slice shape — the golden is the slice).
- **Phase ADRs:**
  - `../ADRs/0004-tools-digests-yaml-pin-manifest.md` — the pinned tool digests are what make `semgrep`/`syft`/`grype` outputs deterministic across runs.
  - `../ADRs/0006-output-sanitizer-passes-4-5.md` — Pass 4 BLAKE3 fingerprint + Pass 5 marker count are deterministic in content; the golden captures the post-sanitized shape.
  - `../ADRs/0011-index-health-advisory-budget-and-strict-flag.md` — B2's golden excludes `budget_exceeded` (a wall-clock-derived field, environmentally non-deterministic); the rest of the slice is deterministic given the snapshot.
  - `../ADRs/0012-audit-chain-blake3-rolling-head.md` — the chain head is per-run state, never in the golden.
- **Source design:**
  - `../final-design.md §"Test plan" → "Golden tests"` — the canonical golden inventory.
- **Implementation plan:**
  - `../High-level-impl.md §"Step 8"` — Done criterion #6: "every Phase 2 probe has ≥ 1 golden under `tests/golden/`; CI diff is a hard gate."
  - `../High-level-impl.md §"Implementation-level risks"` #8 — exclude wall-clock + audit timestamps + chain head; run regen twice locally before opening the PR.
- **Existing code:**
  - `scripts/regen_golden.py` (Phase 1) — extend, do not rewrite.
  - `tests/golden/<phase-1-probe>/<fixture>/expected.json` — pattern reference.
  - The Phase 1 golden-diff CI gate (the same machinery — extended scope, not new shape).
- **Style reference:** `../../01-context-gather-layer-a-node/stories/S6-01-golden-file-regen.md` (Phase 1 golden story — the direct template).

## Goal

Land at least **22 per-probe goldens** under `tests/golden/<probe>/<fixture>/expected.json` (one per Phase 2 probe registered) and extend `scripts/regen_golden.py` so `pytest --update-goldens` regenerates them byte-for-byte; CI diff is the hard gate.

## Acceptance criteria

- [ ] Every Phase 2 probe has **≥ 1 golden file** under `tests/golden/<probe-name>/<fixture-slug>/expected.json` (22 minimum — one per registered probe; the four Layer E stubs each get a trivial `{"status": "not_applicable", ...}` golden).
- [ ] `scripts/regen_golden.py` is extended to discover every Phase 2 probe via the registry; for each (probe, fixture) pair, it runs the probe on the fixture and writes the post-sanitized slice to `tests/golden/<probe>/<fixture>/expected.json`.
- [ ] The regen script **excludes**: (a) wall-clock fields (`wall_clock_ms`, `started_at`, `ended_at`); (b) audit timestamps; (c) the rolling BLAKE3 chain head; (d) `tool_digest` per-invocation overrides (the manifest digest is captured separately via `tools/digests.yaml`). The exclusion list is a module constant `GOLDEN_EXCLUDED_FIELDS: frozenset[str]`; the test suite asserts every Phase 2 golden has **none** of these keys.
- [ ] Running the regen script **twice** in succession produces byte-identical output for every golden file (the determinism check); this is asserted by `tests/golden/test_regen_deterministic.py` which runs the regen, snapshots, regens again, and diffs.
- [ ] The golden-diff CI gate (Phase 1 origin) covers every Phase 2 golden — any change to a probe's output that is not accompanied by a `--update-goldens` regen fails the `test` job.
- [ ] Each golden file is < 100 KB on disk; the heavy probes (`syft_sbom`, `grype_cve`, `scip_index`) use a **stripped-down fixture** rather than the full `nestjs/nest` snapshot, to keep goldens reviewable.
- [ ] `tests/golden/README.md` (new or extended from Phase 1) documents (a) the regen recipe, (b) the exclusion-list rationale, (c) the determinism check, (d) how to add a new probe's golden.
- [ ] All goldens pass on Python 3.11 and 3.12 (same byte output; the only Python-version-sensitive surface is dict ordering, and `json.dumps(..., sort_keys=True)` plus consistent `indent` neutralizes it).

## Implementation outline

1. **Audit Phase 1's `scripts/regen_golden.py`.** Read end-to-end; identify the (probe, fixture) iteration shape; identify the field-exclusion mechanism. The Phase 2 extension follows the same shape.
2. **Extend the script's probe discovery.** Replace the hardcoded Phase 1 list with `registry.all_probes()` (or whatever the public registry surface is); for each probe, pick its golden fixture from a `GOLDEN_FIXTURES: dict[str, str]` mapping in the script (probe name → fixture path).
3. **Extend `GOLDEN_EXCLUDED_FIELDS`** to cover the Phase 2 surface: `{"wall_clock_ms", "started_at", "ended_at", "chain_head", "previous_hash", "tool_digest", "_invocation_id"}`. The exclusion is recursive (any nested dict's matching key is dropped).
4. **Land the goldens.** For each probe:
   - Pick a small fixture (50–500 KB) that exercises the probe's interesting path. Phase 1 has `node_typescript_helm`; Phase 2 needs a per-probe small fixture for the heavy probes:
     - `syft_sbom`: `tests/fixtures/syft_sbom_minimal/` — a 1-stage Dockerfile + a 2-package `package.json`.
     - `grype_cve`: same fixture; uses the SBOM golden as input.
     - `scip_index`: `tests/fixtures/scip_index_minimal/` — 5 TS files, no `node_modules`.
     - `index_health`: a synthetic peer-output snapshot fixture (not a repo) — write `tests/golden/index_health/synthetic_snapshot/input.json` + `expected.json` where the input is the snapshot the test feeds.
     - Every other probe: a single per-probe fixture or reuse `node_typescript_with_b_through_g`.
   - Run the regen script.
   - Inspect each golden by eye for shape sanity (the slice's shape matches the sub-schema; no excluded fields present).
   - Commit.
5. **`tests/golden/test_regen_deterministic.py`:** runs the regen script via `subprocess`, snapshots the goldens directory, runs the script again, diffs. The test is a Phase-1-origin pattern (S6-01) extended in scope.
6. **`tests/golden/README.md`:** if Phase 1 already shipped one, extend; otherwise create. Document the four points in the acceptance criterion.
7. **Update the CI `test` job** (in S8-06; this story leaves a comment in the regen script noting the wiring).

## TDD plan — red / green / refactor

### Red — write the failing test first

The "test" for goldens is the golden-diff CI gate itself: if the regen output doesn't match the committed golden, the gate red-fails. The story's first red is the determinism test:

Path: `tests/golden/test_regen_deterministic.py`

```python
"""ADR-0012 risk #8 carryover: golden regen must be byte-deterministic across runs."""
from pathlib import Path
import shutil
import subprocess
import sys


def test_regen_golden_is_byte_deterministic(tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    golden_dir = repo_root / "tests" / "golden"
    snapshot_a = tmp_path / "a"
    snapshot_b = tmp_path / "b"

    subprocess.run(
        [sys.executable, "scripts/regen_golden.py"],
        check=True, cwd=repo_root,
    )
    shutil.copytree(golden_dir, snapshot_a)

    subprocess.run(
        [sys.executable, "scripts/regen_golden.py"],
        check=True, cwd=repo_root,
    )
    shutil.copytree(golden_dir, snapshot_b)

    a_files = sorted(p.relative_to(snapshot_a) for p in snapshot_a.rglob("*.json"))
    b_files = sorted(p.relative_to(snapshot_b) for p in snapshot_b.rglob("*.json"))
    assert a_files == b_files, "regen changed the golden file set across runs"

    for rel in a_files:
        a_bytes = (snapshot_a / rel).read_bytes()
        b_bytes = (snapshot_b / rel).read_bytes()
        assert a_bytes == b_bytes, f"non-deterministic golden: {rel}"
```

Path: `tests/golden/test_no_excluded_fields.py`

```python
"""Every committed golden must have no wall-clock / chain-head / per-invocation tool_digest field."""
from pathlib import Path
import json

EXCLUDED = frozenset({
    "wall_clock_ms", "started_at", "ended_at",
    "chain_head", "previous_hash", "_invocation_id",
})


def _walk(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def test_no_excluded_fields_in_any_golden():
    root = Path("tests/golden")
    for golden in root.rglob("expected.json"):
        data = json.loads(golden.read_text())
        keys = set(_walk(data))
        leaked = keys & EXCLUDED
        assert not leaked, f"{golden} contains excluded field(s): {leaked}"
```

### Green — make it pass

The determinism test red-fails first if `regen_golden.py` emits a wall-clock field, sorts dicts inconsistently, or includes a process-level random ID. Fix in the regen script:

- Always `json.dumps(..., sort_keys=True, indent=2)`.
- Filter dict keys against `GOLDEN_EXCLUDED_FIELDS` recursively before dump.
- Pin the structlog timestamp seed (or simply drop timestamp fields, which is the safer path).

The no-excluded-fields test red-fails if any committed golden has a wall-clock or chain-head key. After the regen runs cleanly, the goldens are clean by construction; the test is the regression catch.

### Refactor — clean up

After green:

- Run `python scripts/regen_golden.py` twice locally; `git diff tests/golden/` must show no changes after the second run.
- For each golden, eyeball the JSON for shape sanity — does the slice match the sub-schema? If not, the probe likely emits a field not in the schema (and S2-07's `additionalProperties: false` discipline would catch at envelope validation).
- Update `tests/golden/README.md` with the new probe list.
- Confirm the goldens directory disk footprint is < 5 MB total (22 goldens × ~100 KB ceiling = 2.2 MB envelope).
- Verify all goldens pass on Python 3.11 and 3.12 — most likely sensitivity is `json.dumps` dict ordering (already neutralized by `sort_keys=True`).

## Files to touch

| Path | Why |
|---|---|
| `scripts/regen_golden.py` | **Extend** — probe-discovery via registry; Phase 2 fixture mapping; exclusion-list recursion. |
| `tests/golden/<probe>/<fixture>/expected.json` × 22 | New — one per Phase 2 probe. |
| `tests/golden/syft_sbom/minimal/expected.json` + fixture | New — heavy probe, small fixture. |
| `tests/golden/grype_cve/minimal/expected.json` + fixture | New — heavy probe, reuses SBOM fixture. |
| `tests/golden/scip_index/minimal/expected.json` + fixture | New — heavy probe, small TS source tree. |
| `tests/golden/index_health/synthetic_snapshot/expected.json` + `input.json` | New — B2's golden is on a synthetic peer-output snapshot (not a repo). |
| `tests/golden/runtime_trace/deferred/expected.json` | New — trivial constant-content golden per S5-04. |
| `tests/golden/<each-layer-e-stub>/none/expected.json` × 4 | New — trivial `{"status": "not_applicable", ...}` goldens. |
| `tests/golden/test_regen_deterministic.py` | New — determinism check. |
| `tests/golden/test_no_excluded_fields.py` | New — regression catch. |
| `tests/golden/README.md` | New (or extended from Phase 1) — regen recipe + exclusion rationale + add-a-probe-golden recipe. |
| `tests/fixtures/syft_sbom_minimal/` | New — small Dockerfile + package.json fixture. |
| `tests/fixtures/scip_index_minimal/` | New — 5-file TS source tree. |

## Out of scope

- **Bench canaries** — handled by **S8-05**.
- **CI workflow wiring** — handled by **S8-06**.
- **Modifying probe output to make a golden cleaner** — if a probe emits a non-deterministic field that should be deterministic, surface as a Step 3–7 follow-up; this story does not patch probe behavior.
- **Real-OSS golden** (`nestjs/nest`) — explicit Phase 2 carve-out. Goldens are on small fixtures for reviewability. The real-OSS path is covered by **S8-02**'s integration test, which asserts shape, not byte-for-byte content.
- **Re-generating Phase 1 goldens.** Phase 1's goldens stay as-shipped; this story does not touch them.

## Notes for the implementer

- **Determinism is the entire game.** A golden that flakes is worse than no golden — it erodes trust in the gate. Run the regen **at least twice** locally before opening the PR; `git diff tests/golden/` on the second run must be empty.
- **`sort_keys=True` is mandatory.** Python's dict insertion order is preserved since 3.7, but the regen script may walk a dict in a different order if the upstream probe constructs it from different code paths (cache hit vs miss). Sorting by key neutralizes this.
- **Excluding `tool_digest` per-invocation is subtle.** The pin manifest digest is what we want to capture (deterministic per-version); the per-invocation `tool_digest` field on `ToolResult` is identical when the tool version matches the manifest, but excluding it is the safer path — the manifest itself is committed.
- **Index Health's golden is on a *synthetic snapshot*, not a repo.** B2 reads a frozen peer-output snapshot; its output is a pure function of that snapshot + the tool-digest manifest. The golden captures (snapshot input → expected B2 slice), which is faster and more deterministic than running every probe to populate a real snapshot. Document this clearly in `tests/golden/README.md`.
- **The four Layer E stubs each get a trivial golden.** Each stub's `applies()` returns `False`; its slice is `{"status": "not_applicable", "reason": "..."}`. The golden is < 200 bytes. Do not omit them — every probe ships ≥ 1 golden, including stubs.
- **Heavy-probe fixtures are small.** Do not use `nestjs/nest` as a golden fixture — the diff is unreviewable. The committed-fixture approach (`syft_sbom_minimal/`, `scip_index_minimal/`) keeps the golden small enough to eyeball in a code review.
- **`test_no_excluded_fields.py` is the regression catch.** If a future probe adds a `wall_clock_ms` field to its slice and forgets to add it to the exclusion list, this test red-fails. Surface; either drop the field from the slice or extend the exclusion list (the former is preferred — wall-clock belongs in audit metadata, not in the slice).
- **Phase 1's `scripts/regen_golden.py` is the canonical extension target.** Do not rewrite; extend. The Phase 1 story (S6-01) is the direct template.
