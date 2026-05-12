# Story S7-05 — `TestCoverageMappingProbe` reads SCIP + lcov

**Step:** Step 7 — Ship Layer D, Layer E (real + stubs), Layer G; plant per-file findings sub-caches
**Status:** Ready
**Effort:** S
**Depends on:** S4-01
**ADRs honored:** `final-design.md` "Architecture" (SCIP binary at `.codegenie/index/scip-index.scip`, not under `cache/`)

## Context

`TestCoverageMappingProbe` (G3) joins two index streams: SCIP symbols (from S4-01's `SCIPIndexProbe`, written to `.codegenie/index/scip-index.scip` as a per-repo binary) and lcov coverage data (from `coverage/lcov.info`, parsed via the Phase 1 lcov parser reused). The output is a `symbol → coverage_percentage` mapping that downstream Planner stages use to prioritize "modify with test coverage" over "modify uncovered". The probe is small (Tier-0 read + join + emit); the load-bearing pieces are: (1) reading the SCIP binary in the per-repo namespace (never under `cache/`); (2) reusing the Phase 1 lcov parser rather than re-implementing.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #7 SCIPIndexProbe` — SCIP binary lifecycle; per-repo, rewritten in place, never under `cache/`.
  - `../phase-arch-design.md §"Component design" #17` — `.codegenie/index/` namespace.
  - `../phase-arch-design.md §"Logical view"` — `TestCoverageMappingProbe → SCIPIndexNamespace : reads scip-index.scip`.
- **Source design:**
  - `../final-design.md §"Architecture"` — per-repo binary at `.codegenie/index/scip-index.scip`; `cache gc` preserves it; `cache prune-index` is manual.
  - `../final-design.md §"Components" §7 Layer G` — G3 summary.
- **Existing code:**
  - `src/codegenie/probes/scip_index.py` (S4-01) — writes `.codegenie/index/scip-index.scip`.
  - `src/codegenie/parsers/lcov.py` (Phase 1 origin per `phase-arch-design.md`) — or its equivalent under `tests/probes/_lcov_parser/`. Reuse rather than re-implement.
  - `src/codegenie/probes/__init__.py` — registration target.

## Goal

Ship `src/codegenie/probes/test_coverage_map.py` and `src/codegenie/schema/probes/test_coverage_map.schema.json` — reads `.codegenie/index/scip-index.scip` (per-repo binary), parses `coverage/lcov.info` via the existing Phase 1 lcov parser, emits a `symbol_coverage: list[{symbol, file, line_range, coverage_pct}]` mapping; `applies_to_languages = ["typescript", "javascript"]`.

## Acceptance criteria

- [ ] `src/codegenie/probes/test_coverage_map.py` exports `TestCoverageMappingProbe(Probe)` with `name="test_coverage_map"`, `declared_inputs=[".codegenie/index/scip-index.scip", "coverage/lcov.info", "coverage/coverage.lcov"]`, `requires=["scip_index"]`, `applies_to_languages=["typescript", "javascript"]`, `timeout_seconds=30`.
- [ ] On `run`:
  1. Resolve the SCIP binary path: `<repo_root>/.codegenie/index/scip-index.scip`. If missing → `confidence: low`, `errors=["scip_index.binary_missing"]`, return.
  2. Resolve the lcov file: first `coverage/lcov.info`, fallback `coverage/coverage.lcov`. If both missing → `confidence: low`, `errors=["test_coverage_map.lcov_missing"]`, return.
  3. Parse SCIP via the upstream `scip-python` Python binding or the SCIP protobuf schema (reuse S4-01's load helper — if S4-01 exposes `load_scip_index(path) -> SCIPIndex`, use it; otherwise add the helper to `scip_index.py` and import).
  4. Parse lcov via the Phase 1 parser at `src/codegenie/parsers/lcov.py` (or wherever the Phase 1 spec places it).
  5. Join: for each SCIP symbol with a `range` referencing a file path, look up lcov coverage for that file's line range; compute `coverage_pct: float` in `[0.0, 1.0]`.
  6. Emit `slice = {"symbol_coverage": [...], "total_symbols": int, "covered_symbols": int, "uncovered_symbols": int, "scip_index_path": ".codegenie/index/scip-index.scip", "lcov_source": <path>}`.
- [ ] The SCIP binary is **never** read from under `.codegenie/cache/` — the probe's path resolution explicitly uses `.codegenie/index/`. A test asserts that pointing the probe at `cache/blobs/...` for the SCIP binary fails with a typed error.
- [ ] `src/codegenie/schema/probes/test_coverage_map.schema.json` — `additionalProperties: false`; `schema_version: "v1"`; matches the slice 1:1.
- [ ] `tests/unit/probes/test_test_coverage_map.py` — happy path on `tests/fixtures/coverage_fixture/` (synthetic SCIP + lcov pair); SCIP missing → `confidence: low`; lcov missing → `confidence: low`; SCIP-binary-from-cache-namespace explicitly rejected.
- [ ] `tests/golden/test_coverage_map/happy/expected.json` — golden with stable `symbol_coverage` ordering (sort by symbol name).
- [ ] TDD red test exists, committed, green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, `pytest` pass on touched files.

## Implementation outline

1. Create `src/codegenie/probes/test_coverage_map.py`:
   - `TestCoverageMappingProbe(Probe)` with class attributes per acceptance criteria.
   - `async run(self, snapshot, ctx) -> ProbeOutput`:
     1. `scip_path = snapshot.root / ".codegenie" / "index" / "scip-index.scip"`. Existence check.
     2. `lcov_path = snapshot.root / "coverage" / "lcov.info"` (then fallback `coverage/coverage.lcov`).
     3. `from codegenie.probes.scip_index import load_scip_index; index = load_scip_index(scip_path)`.
     4. `from codegenie.parsers.lcov import parse_lcov; coverage = parse_lcov(lcov_path)`.
     5. Join (one-pass): walk SCIP symbols; for each, look up lcov by `(file, line_range)`; compute `coverage_pct`.
     6. Build `ProbeOutput`.
2. Create `src/codegenie/schema/probes/test_coverage_map.schema.json`.
3. Plant `tests/fixtures/coverage_fixture/` with a synthetic 3-symbol SCIP binary + matching lcov (use a small Python helper to write the SCIP via `scip-python`'s protobuf — pinned in `tools/digests.yaml`).
4. Register probe in `probes/__init__.py`.

## TDD plan — red / green / refactor

### Red

Path: `tests/unit/probes/test_test_coverage_map.py`.

```python
import pytest
from codegenie.probes.test_coverage_map import TestCoverageMappingProbe

async def test_happy_path_emits_symbol_coverage(coverage_fixture, ctx):
    out = await TestCoverageMappingProbe().run(coverage_fixture.snapshot, ctx)
    assert out.confidence == "high"
    assert out.slice["total_symbols"] == 3
    assert all(0.0 <= s["coverage_pct"] <= 1.0 for s in out.slice["symbol_coverage"])

async def test_missing_scip_returns_low_confidence(tmp_repo_no_scip, ctx):
    out = await TestCoverageMappingProbe().run(tmp_repo_no_scip.snapshot, ctx)
    assert out.confidence == "low"
    assert any("scip_index.binary_missing" in e for e in out.errors)

async def test_missing_lcov_returns_low_confidence(scip_only_repo, ctx):
    out = await TestCoverageMappingProbe().run(scip_only_repo.snapshot, ctx)
    assert out.confidence == "low"
    assert any("test_coverage_map.lcov_missing" in e for e in out.errors)

async def test_scip_binary_only_from_index_namespace(coverage_fixture_with_misplaced_scip, ctx):
    # Plant a SCIP binary under .codegenie/cache/ — assert the probe does NOT use it.
    out = await TestCoverageMappingProbe().run(coverage_fixture_with_misplaced_scip.snapshot, ctx)
    assert "scip_index.binary_missing" in " ".join(out.errors)
```

### Green

Minimal impl per outline. The SCIP loader helper from S4-01 is the unit-of-reuse; the lcov parser from Phase 1 is the other. If `load_scip_index` doesn't exist yet (S4-01 ships first), this story adds it as a small helper in `scip_index.py` — surgical addition.

### Refactor

- Module docstring naming `phase-arch-design.md §"Component design" #7` (SCIP path discipline), `final-design.md "Architecture"` (per-repo binary).
- The path-resolution helper `_resolve_scip_path(snapshot) -> Path` is testable in isolation — the `cache/`-namespace rejection lives here.
- The join algorithm is one function: `_join_coverage(scip_symbols, lcov_map) -> list[SymbolCoverage]`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/test_coverage_map.py` | New — `TestCoverageMappingProbe`. |
| `src/codegenie/schema/probes/test_coverage_map.schema.json` | New — sub-schema. |
| `src/codegenie/probes/__init__.py` | Register `TestCoverageMappingProbe`. |
| `src/codegenie/probes/scip_index.py` | Surgical — expose `load_scip_index(path) -> SCIPIndex` if not already exposed by S4-01. |
| `tests/unit/probes/test_test_coverage_map.py` | New — 4 unit tests. |
| `tests/fixtures/coverage_fixture/` | New — synthetic SCIP + lcov pair. |
| `tests/golden/test_coverage_map/happy/expected.json` | New — golden file. |

## Out of scope

- **Coverage-driven test-impact analysis** — Phase 8 owns the "which tests to run for this change" decision.
- **Branch / function / line-level coverage variants** — Phase 2 emits `coverage_pct` only; finer-grained metrics in Phase 14.
- **Other coverage formats** (Cobertura, JaCoCo, Istanbul nyc JSON) — lcov only in Phase 2; other formats per task-type when they earn it.
- **SCIP binary lifecycle management** — `cache gc` preservation logic lives in S4-01 + S7-01; this probe only reads.

## Notes for the implementer

- **Never read SCIP from `cache/`.** The whole point of `final-design.md "Architecture"`'s separate namespace is that the SCIP binary outlives any single gather (`cache gc` cleans `cache/`, doesn't touch `.codegenie/index/`). Hardcode the path discipline; surface a typed error if a future contributor "helpfully" tries to consolidate.
- **Reuse, don't re-implement, lcov parsing.** Phase 1's parser is the source of truth. If it's under `tests/probes/_lcov_parser/` rather than `src/codegenie/parsers/`, that's a Phase 1 bug — flag it but use what's there. Don't write a new lcov parser; the format has edge cases (continuation lines, multiple DA records per line, BRDA branches) that are easy to get wrong.
- **`coverage_pct` is a float in `[0.0, 1.0]`, not `[0, 100]`.** Schema enforces; pick one early.
- **SCIP symbol ranges may not align 1:1 with lcov line ranges.** A function spanning lines 10-30 with line-level coverage may show 8/20 lines hit → `coverage_pct = 0.4`. Don't over-engineer the matching; line-range-intersection is enough for Phase 2.
- **`requires=["scip_index"]`** triggers the coordinator's wave-ordering — `SCIPIndexProbe` runs first. If `SCIPIndexProbe` failed (no SCIP binary written), this probe's `requires` check passes (the probe ran, even if low-confidence), but the binary path won't exist — the existence check in this probe's `run` is the second defense.
- **Stable ordering in goldens.** Sort `symbol_coverage` by `symbol` ascending. Without this, golden files churn across runs (SCIP iteration order is implementation-defined).
- **The fixture's synthetic SCIP binary** can be tiny: 3 symbols, 1 file. Don't try to commit a real-OSS SCIP binary — it bloats the repo and pins a tree-sitter / scip-typescript version. The integration test (Step 8) uses real-OSS.
