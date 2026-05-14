# Story S6-08 — `TestCoverageMapping` + Layer D/E/G sub-schemas + freshness registrations

**Step:** Step 6 — Ship Layer D + E + G probes (skills, conventions, ADRs, ownership, scanners)
**Status:** Ready
**Effort:** M
**Depends on:** S6-03 (Layer D marker probes — `conventions` slice exists so its catalog version is a real freshness signal), S6-07 (`GitleaksProbe` + the four-scanner Layer G shape is settled; this story extends it with the fifth — `TestCoverageMappingProbe` — and lands the Layer D/E/G sub-schemas + the three freshness registrations)
**ADRs honored:** 02-ADR-0001 (any coverage-tooling CLI lands in `ALLOWED_BINARIES`), 02-ADR-0003 (`heaviness="medium"` is a registry kwarg, not a `Probe` ABC field), 02-ADR-0005 (no plaintext persistence — coverage findings flow through `SecretRedactor` at the writer chokepoint), 02-ADR-0006 (`IndexFreshness` registry; rule-pack-versioned scanners register their own freshness check via `@register_index_freshness_check` in their own module — never in `index_health.py`)
**Phase-2 load-bearing design discipline:** [`../phase-arch-design.md` §"Design patterns applied"](../phase-arch-design.md) **row 7** — *"One file per Layer G scanner; no shared `ScannerRunner` abstraction"* — extended to the fifth scanner here. [`../phase-arch-design.md` §"Gap analysis & improvements" Gap 3](../phase-arch-design.md) — `@register_index_freshness_check` is the Open/Closed seam; this story is the final exercise of that seam in Phase 2. **B2 (`IndexHealthProbe`) gets zero new code for these three indices.**

## Context

S6-06 and S6-07 land the four-scanner Layer G shape (`semgrep`, `ast_grep`, `ripgrep_curated`, `gitleaks`). This story closes Step 6 with three concerns that *cannot* be relaxed to a later step without leaving Phase 2 incomplete:

1. **`TestCoverageMappingProbe`** (the fifth Layer G probe per `localv2.md` §5.6 G3 and `phase-arch-design.md §"Component design"` #5) — reads `coverage/lcov.info` or `coverage/coverage-final.json` if present and emits a `test_coverage_map` slice. It is the raw artifact that Phase 3's `TestInventoryAdapter.tests_exercising` (`production/adrs/0030-graph-aware-context-queries.md`) projects against. Per-line attribution and the Phase-3 adapter projection are explicitly **out of scope** here — Phase 2 only ships the raw evidence.
2. **Layer D / E / G sub-schemas** under `src/codegenie/schema/probes/layer_{d,e,g}/`. S6-01..S6-06 (Layer D + E + four Layer G scanners) and this story's `test_coverage_mapping` collectively define ~14 slice shapes; they all land here as JSON Schemas with `additionalProperties: false` at every level (Phase 1 ADR-0004 convention). The sub-schemas are *referenced by* `S4-07`'s Layer-B subschemas + S5's Layer-C subschemas via the merged-envelope schema in Phase 0.
3. **`@register_index_freshness_check` registrations** for the three Phase-2 rule-pack/catalog-versioned indices — `semgrep` (rule-pack version), `gitleaks` (rule-pack version), `conventions` (catalog version). Each registration lives in *its own module* (the scanner / loader's file), not in `index_health.py`. That's the Open/Closed promise of S1-02's registry: `IndexHealthProbe` loops `default_freshness_registry.dispatch_all()` and learns about new indices via import side-effect, never via edit.

The load-bearing test of the third concern is the **rule-pack-drift integration test**: a fixture captures `rule_pack_version="v1"` on one gather, the rule pack bumps to `"v2"`, the next gather's `IndexHealthProbe` constructs `IndexFreshness.Stale(reason=DigestMismatch(expected="v1", actual="v2"))` *without B2 having been edited*. The same test pattern S5-05 lands for `runtime_trace`'s image-digest signal; this story is its analogue for rule-pack signals.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md` §"Component design" #5 Layer G scanners](../phase-arch-design.md) — one file per scanner, ≤ 200 LOC; this story adds the fifth file.
  - [`../phase-arch-design.md` §"Component design" #1 `IndexHealthProbe`](../phase-arch-design.md) — B2 reads `rule_pack_version` from sibling slices; this story is where that metadata becomes typed.
  - [`../phase-arch-design.md` §"Testing strategy"](../phase-arch-design.md) — sub-schema round-trip + rule-pack-drift integration test are the load-bearing freshness tests for Phase 2.
  - [`../phase-arch-design.md` §"Edge cases"](../phase-arch-design.md) rows 1–3 + row 13 — tool missing, non-zero exit, bad JSON, hostile coverage file (truncated lcov, malformed Istanbul JSON).
  - [`../phase-arch-design.md` §"Gap analysis & improvements" Gap 3](../phase-arch-design.md) — `@register_index_freshness_check` Open/Closed extension; this story is the third+fourth+fifth registration exercising it.
- **Phase ADRs:**
  - [`../ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md`](../ADRs/0001-add-docker-and-security-cli-tools-to-allowed-binaries.md) — ADR-0001 — any coverage CLI added to `ALLOWED_BINARIES` (Phase 2 only reads on-disk lcov/Istanbul JSON; no new CLI required, but if a future ecosystem needs `bun test --coverage`, the binary lands here).
  - [`../ADRs/0003-coordinator-heaviness-sort-annotation.md`](../ADRs/0003-coordinator-heaviness-sort-annotation.md) — ADR-0003 — `heaviness="medium"` is a registry kwarg; the `Probe` ABC is untouched.
  - [`../ADRs/0005-secret-findings-no-plaintext-persistence.md`](../ADRs/0005-secret-findings-no-plaintext-persistence.md) — ADR-0005 — coverage data may inline file paths under sensitive directories; the writer's `SecretRedactor` is the chokepoint, not the probe.
  - [`../ADRs/0006-index-freshness-sum-type-location.md`](../ADRs/0006-index-freshness-sum-type-location.md) — ADR-0006 — `IndexFreshness` lives in `codegenie/indices/freshness.py`; new freshness checks register via `@register_index_freshness_check` in their own module.
- **Production ADRs:**
  - [`../../../production/adrs/0030-graph-aware-context-queries.md`](../../../production/adrs/0030-graph-aware-context-queries.md) — `TestInventoryAdapter.tests_exercising(symbol)` is the Phase 3 consumer; the `test_coverage_map` slice this story emits is its raw artifact.
- **Source design:**
  - [`../High-level-impl.md` §"Step 6"](../High-level-impl.md) — `@register_probe(heaviness="medium")` on `test_coverage_mapping`; sub-schemas under `src/codegenie/schema/probes/layer_{d,e,g}/`; freshness registrations for `semgrep`/`gitleaks`/`conventions`.
  - [`../../localv2.md` §5.6 G3](../../../localv2.md) — `test_coverage_map` slice shape; lcov + Istanbul parsers.
- **Existing kernel:**
  - `src/codegenie/probes/layer_g/semgrep.py` (S6-06) — pattern to mirror (≤ 200 LOC; Pydantic smart constructor; `ScannerOutcome`).
  - `src/codegenie/probes/layer_g/gitleaks.py` (S6-07) — pattern to mirror.
  - `src/codegenie/indices/registry.py` (S1-02) — `@register_index_freshness_check(index_name)`; `FreshnessCheck = Callable[[dict[str, JSONValue], str], IndexFreshness]`.
  - `src/codegenie/indices/freshness.py` (S1-01) — `IndexFreshness = Fresh | Stale(reason)`; `StaleReason` variants including `DigestMismatch(expected, actual)`.
  - `src/codegenie/probes/layer_b/index_health.py` (S4-01) — loops `default_freshness_registry.dispatch_all()`; **this story must NOT edit it**.
  - `src/codegenie/exec.py` (S1-07) — `run_external_cli`; only used if a coverage CLI is needed (Phase 2 ships file-only readers — no new binary).

## Goal

Land three concerns in one story:

1. `src/codegenie/probes/layer_g/test_coverage_mapping.py` — `@register_probe(heaviness="medium")`, ≤ 200 LOC, no shared base class, parses `coverage/lcov.info` and/or `coverage/coverage-final.json` into a `TestCoverageSlice` whose payload is `ScannerOutcome`. Tool-missing path (no coverage file present) → `ScannerSkipped`; bad-parse → `ScannerFailed`.
2. Sub-schemas under `src/codegenie/schema/probes/layer_d/`, `layer_e/`, `layer_g/` — one JSON Schema per slice shipped in Step 6, all with `additionalProperties: false` at every nested level; `ScannerOutcome`'s discriminator field is `kind` ∈ {`"ran"`, `"skipped"`, `"failed"`}.
3. `@register_index_freshness_check` registrations for `semgrep` (rule-pack version, in `semgrep.py`), `gitleaks` (rule-pack version, in `gitleaks.py`), `conventions` (catalog version, in `src/codegenie/conventions/loader.py`). Each registered at **module-import time** — not lazily. Verified end-to-end by an integration test that mutates rule-pack version between two gathers and asserts `IndexHealthProbe` emits `Stale(DigestMismatch(...))` for each index *without B2 itself being edited*.

## Acceptance criteria

**Numbered for traceability to the TDD plan.**

- [ ] **AC-1.** `src/codegenie/probes/layer_g/test_coverage_mapping.py` exists; `__all__` declares exactly `TestCoverageMappingProbe`, `TestCoverageSlice`, `CoverageRecord`.
- [ ] **AC-2.** The file is **≤ 200 LOC** including Pydantic models, imports, docstring. Verified by `tests/unit/probes/layer_g/test_scanner_loc_ceiling.py` (the parametrized ceiling test from S6-06; this story extends the `SCANNER_MODULES` list to include the fifth file).
- [ ] **AC-3.** Probe is `@register_probe(heaviness="medium")`; `probe_id = ProbeId("test_coverage_mapping")`; `applies_to_tasks=("*",)`; `applies_to_languages=("*",)`; `timeout_seconds = 30`.
- [ ] **AC-4.** **No shared `ScannerRunner` base class.** The S6-06 architectural test extends to this file: imports `Probe` from `codegenie.probes.base` only; never imports a `ScannerRunner` / `BaseScanner` / `AbstractScanner` symbol; never imports another scanner module in this set. The shared types remain `ScannerOutcome` (S5-01) and `run_external_cli` (S1-07) — both kernel-level, not scanner-family-level.
- [ ] **AC-5.** **Pydantic smart constructor.** `parse_lcov_bytes(raw: bytes) -> Result[tuple[CoverageRecord, ...], ParseError]` and `parse_istanbul_bytes(raw: bytes) -> Result[tuple[CoverageRecord, ...], ParseError]` are private functions; each is a smart constructor that either yields a frozen tuple of `CoverageRecord(test_file, source_file, lines_covered)` or a typed `ParseError`. Mutation caught: silent swallow of `ValidationError` / `UnicodeDecodeError`.
- [ ] **AC-6.** **No coverage file → `ScannerSkipped`.** When neither `coverage/lcov.info` nor `coverage/coverage-final.json` exists under `ctx.repo_root`, the probe returns `ScannerOutcome.ScannerSkipped(reason="no_coverage_artifact")` with `confidence="low"`. This is the dominant path in production repos; the test pins it. Mutation caught: any code path that raises past the probe boundary on this dominant case.
- [ ] **AC-7.** **Malformed coverage file → `ScannerFailed`.** When the on-disk file fails the smart constructor (truncated lcov, malformed Istanbul JSON, billion-laughs Istanbul JSON, file larger than 64 MB), the probe returns `ScannerFailed(exit_code=0, stderr_tail="<concise reason>")` with `confidence="low"`. Mutation caught: any `try: ... except: pass` swallow.
- [ ] **AC-8.** **All scanner invocations route through `run_external_cli`** — *if* a CLI is invoked. Phase 2's implementation reads files only; no new binary is added. Architectural test (extension of S6-06's AC-16): the file does not call `subprocess.run` / `subprocess.Popen` / `asyncio.create_subprocess_exec` directly. If a future contributor adds `bun test --coverage` invocation, it MUST route through `run_external_cli` and `bun` MUST already be in `ALLOWED_BINARIES`.
- [ ] **AC-9.** Sub-schemas land at `src/codegenie/schema/probes/layer_d/*.schema.json` (7 schemas — one per S6-01..S6-04 + S6-05 Layer D probe), `src/codegenie/schema/probes/layer_e/*.schema.json` (3 schemas — `ownership`, `service_topology_stub`, `slo_stub`), and `src/codegenie/schema/probes/layer_g/*.schema.json` (5 schemas — `semgrep`, `ast_grep`, `ripgrep_curated`, `gitleaks`, `test_coverage_mapping`). **Every schema declares `additionalProperties: false` at every nested-object level** (Phase 1 ADR-0004 convention — `tests/unit/schema/test_layer_d_e_g_subschemas_no_extra.py` walks the JSON tree and fires on any object without the property).
- [ ] **AC-10.** Each scanner slice's `outcome` field in the JSON Schema uses `oneOf` with `kind` ∈ {`"ran"`, `"skipped"`, `"failed"`} as the discriminator — matching the Pydantic `ScannerOutcome` tagged union. Round-trip test: feed a known `ScannerOutcome.ScannerSkipped(reason="tool_missing")` through `model_dump(mode="json")` → assert the produced JSON validates against the sub-schema.
- [ ] **AC-11.** `@register_index_freshness_check("semgrep")` is registered in `src/codegenie/probes/layer_g/semgrep.py` — at module-import time, top-level. The function reads `slice["rule_pack_version"]` from the just-written slice, compares it to `slice.get("expected_rule_pack_version", slice["rule_pack_version"])` (the freshness baseline lands as a separate slice key written by the scanner itself), and constructs `IndexFreshness.Fresh()` on match / `Stale(DigestMismatch(expected, actual))` on drift. Same shape for `@register_index_freshness_check("gitleaks")` in `gitleaks.py`. Same shape for `@register_index_freshness_check("conventions")` in `src/codegenie/conventions/loader.py` — reads `catalog_version` instead of `rule_pack_version`.
- [ ] **AC-12.** **Registrations happen at module-import time, NOT lazily.** Architectural test: `tests/unit/indices/test_phase2_freshness_registrations.py` imports the three modules and asserts `"semgrep" in default_freshness_registry.registered_names()`, `"gitleaks" in ...`, `"conventions" in ...`. Mutation caught: any future "register on first call" pattern would silently fail the next clause.
- [ ] **AC-13.** **`IndexHealthProbe` is unchanged.** Architectural test: `tests/unit/indices/test_phase2_freshness_registrations.py` records the BLAKE3 of `src/codegenie/probes/layer_b/index_health.py` before this story's PR and asserts it is *not* in the changed-files list of this PR. (Operational form: `git diff --name-only` excludes `index_health.py`; the assertion is on the PR's file list and lands in the CI `forbidden-patterns` job.) **The Open/Closed promise of S1-02 is the deliverable — adding three new indices must require zero edits to B2.**
- [ ] **AC-14.** **Rule-pack-drift integration test** at `tests/integration/probes/test_rule_pack_drift_marks_stale.py` — parametrized across the three indices. Fixture: a synthetic repo with a recorded `semgrep` slice whose `rule_pack_version` is `"v1"`. Test runs `IndexHealthProbe` against a second snapshot with `rule_pack_version` `"v2"`. Assertion: the dispatched `IndexFreshness` for `"semgrep"` is `Stale(reason=DigestMismatch(expected="v1", actual="v2"))`; same shape for `"gitleaks"` and `"conventions"` (catalog-version drift).
- [ ] **AC-15.** **`mypy --strict`** passes on `test_coverage_mapping.py`, the three modules carrying registrations, and the test. No `Any` escapes `CoverageRecord` / `IndexFreshness`.
- [ ] **AC-16.** **`ruff check` + `ruff format --check`** pass on every touched file.
- [ ] **AC-17.** Sub-schemas are referenced from the merged-envelope schema (Phase 0); `tests/unit/schema/test_envelope_references_all_subschemas.py` (or extension thereof) finds the 15 Step-6 sub-schemas under the envelope's `$ref` graph.

## Implementation outline

1. **`test_coverage_mapping.py`** (~180 LOC):
   - Module docstring noting the SRP discipline (no shared base; mirror S6-06).
   - `CoverageRecord` Pydantic model with `model_config = ConfigDict(frozen=True, extra="forbid")`; fields `test_file: str | None, source_file: str, lines_covered: tuple[int, ...]`.
   - `TestCoverageSlice` with `outcome: ScannerOutcome, format: Literal["lcov", "istanbul"] | None, files_seen: int | None, rule_pack_version: None = None` (no rule-pack signal — coverage is per-repo).
   - `parse_lcov_bytes(raw)` — parses `SF:` / `DA:` / `end_of_record` lines into `CoverageRecord`s; 64 MB hard cap (raise `ParseError("oversized")` early).
   - `parse_istanbul_bytes(raw)` — `json.loads`; iterate keys; collect line-hit map. Smart constructor; ValidationError → ParseError.
   - `TestCoverageMappingProbe._run(ctx)`: stat `coverage/lcov.info` then `coverage/coverage-final.json`; if neither → `ScannerSkipped("no_coverage_artifact")`; read first found (≤ 64 MB); dispatch to parser; map result to `ScannerOutcome`; return `ProbeOutput`.
2. **Sub-schemas** under `src/codegenie/schema/probes/layer_{d,e,g}/` — one `.schema.json` per slice. Generate from the Pydantic models via `model_json_schema()` post-processed to add `"additionalProperties": false` at every object level (the post-processor lives at `scripts/regen_subschemas.py`; checked-in artifacts are the source of truth, regen script is reviewed-as-code). Match the canonicalization conventions of Phase 1 (sorted keys).
3. **Freshness registrations** — three module-level `@register_index_freshness_check(...)` decorators on three small functions:
   ```python
   # semgrep.py — top-level, after the probe class definition.
   @register_index_freshness_check("semgrep")
   def _semgrep_freshness(slice_: dict[str, JSONValue], _head: str) -> IndexFreshness:
       observed = slice_.get("rule_pack_version")
       expected = slice_.get("expected_rule_pack_version", observed)
       if observed is None or expected is None:
           return Fresh()  # nothing to compare — not Stale.
       if observed != expected:
           return Stale(reason=DigestMismatch(expected=str(expected), actual=str(observed)))
       return Fresh()
   ```
   Identical shape in `gitleaks.py` (reads `rule_pack_version` from its slice — gitleaks's rule pack version is documented in its stdout); identical shape in `conventions/loader.py` (reads `catalog_version`).

## TDD plan — red / green / refactor

### Red — write the failing tests first

```python
# tests/unit/probes/layer_g/test_test_coverage_mapping.py
"""Unit tests for TestCoverageMappingProbe (S6-08)."""
from __future__ import annotations

from pathlib import Path

import pytest

from codegenie.probes.base import ProbeContext, _PROBE_REGISTRY
from codegenie.probes.layer_g import test_coverage_mapping as tcm
from codegenie.probes._shared.scanner_outcome import ScannerRan, ScannerSkipped, ScannerFailed


def test_no_coverage_artifact_is_skipped_not_failed(tmp_path: Path) -> None:
    """AC-6. Mutation caught: any code path that raises past the probe
    boundary on this dominant case (most repos have no coverage file)."""
    ctx = ProbeContext.for_test(repo_root=tmp_path)
    output = tcm.TestCoverageMappingProbe()._run(ctx)
    slice_ = tcm.TestCoverageSlice.model_validate(output.schema_slice)
    assert isinstance(slice_.outcome, ScannerSkipped)
    assert slice_.outcome.reason == "no_coverage_artifact"
    assert output.confidence == "low"


def test_lcov_parses_into_coverage_records(tmp_path: Path) -> None:
    """AC-5. Mutation caught: dropping the SF: / DA: / end_of_record
    state machine would silently emit zero records."""
    cov = tmp_path / "coverage" / "lcov.info"
    cov.parent.mkdir(parents=True)
    cov.write_text(
        "TN:\nSF:src/payments/processor.ts\nDA:1,5\nDA:2,5\nDA:3,0\nend_of_record\n"
    )
    output = tcm.TestCoverageMappingProbe()._run(ProbeContext.for_test(repo_root=tmp_path))
    slice_ = tcm.TestCoverageSlice.model_validate(output.schema_slice)
    assert isinstance(slice_.outcome, ScannerRan)
    assert slice_.format == "lcov"
    assert slice_.files_seen == 1


def test_truncated_lcov_yields_scanner_failed(tmp_path: Path) -> None:
    """AC-7. Mutation caught: silent ValidationError swallow on a
    half-written file (CI artifact upload aborted)."""
    cov = tmp_path / "coverage" / "lcov.info"
    cov.parent.mkdir(parents=True)
    cov.write_text("TN:\nSF:src/payments/processor.ts\nDA:1,")  # truncated mid-record
    output = tcm.TestCoverageMappingProbe()._run(ProbeContext.for_test(repo_root=tmp_path))
    slice_ = tcm.TestCoverageSlice.model_validate(output.schema_slice)
    assert isinstance(slice_.outcome, ScannerFailed)


def test_oversized_coverage_yields_scanner_failed(tmp_path: Path) -> None:
    """AC-7. Mutation caught: reading a 1 GB lcov into memory before
    capping would OOM the gatherer."""
    cov = tmp_path / "coverage" / "lcov.info"
    cov.parent.mkdir(parents=True)
    cov.write_bytes(b"x" * (65 * 1024 * 1024))  # 65 MB > 64 MB cap
    output = tcm.TestCoverageMappingProbe()._run(ProbeContext.for_test(repo_root=tmp_path))
    slice_ = tcm.TestCoverageSlice.model_validate(output.schema_slice)
    assert isinstance(slice_.outcome, ScannerFailed)
    assert "oversized" in slice_.outcome.stderr_tail


def test_istanbul_parses_into_coverage_records(tmp_path: Path) -> None:
    """AC-5. Mutation caught: confusing lcov layout with Istanbul JSON
    layout — different smart constructor."""
    cov = tmp_path / "coverage" / "coverage-final.json"
    cov.parent.mkdir(parents=True)
    cov.write_text('{"src/payments/processor.ts": {"path": "src/payments/processor.ts",'
                   '"statementMap": {}, "s": {"0": 5, "1": 0}}}')
    output = tcm.TestCoverageMappingProbe()._run(ProbeContext.for_test(repo_root=tmp_path))
    slice_ = tcm.TestCoverageSlice.model_validate(output.schema_slice)
    assert isinstance(slice_.outcome, ScannerRan)
    assert slice_.format == "istanbul"


def test_registry_heaviness_is_medium() -> None:
    """AC-3. Mutation caught: bumping to "heavy" would cost the
    coordinator a runs_last slot."""
    assert _PROBE_REGISTRY["test_coverage_mapping"].heaviness == "medium"


def test_timeout_seconds_is_30() -> None:
    """AC-3."""
    assert tcm.TestCoverageMappingProbe.timeout_seconds == 30
```

```python
# tests/unit/indices/test_phase2_freshness_registrations.py
"""AC-12, AC-13 — registrations are at import time; B2 is unchanged."""
from __future__ import annotations

import codegenie.probes.layer_g.semgrep  # noqa: F401 — import triggers registration
import codegenie.probes.layer_g.gitleaks  # noqa: F401
import codegenie.conventions.loader  # noqa: F401
from codegenie.indices.registry import default_freshness_registry


def test_semgrep_registered_at_import_time() -> None:
    """AC-12. Mutation caught: any "register on first call" pattern."""
    assert "semgrep" in default_freshness_registry.registered_names()


def test_gitleaks_registered_at_import_time() -> None:
    """AC-12."""
    assert "gitleaks" in default_freshness_registry.registered_names()


def test_conventions_registered_at_import_time() -> None:
    """AC-12."""
    assert "conventions" in default_freshness_registry.registered_names()
```

```python
# tests/integration/probes/test_rule_pack_drift_marks_stale.py
"""AC-14 — load-bearing Open/Closed proof."""
from __future__ import annotations

import pytest

from codegenie.indices.freshness import DigestMismatch, Fresh, Stale
from codegenie.indices.registry import default_freshness_registry


@pytest.mark.parametrize("index_name,version_key", [
    ("semgrep", "rule_pack_version"),
    ("gitleaks", "rule_pack_version"),
    ("conventions", "catalog_version"),
])
def test_rule_pack_drift_marks_index_stale(index_name: str, version_key: str) -> None:
    # Arrange: simulate the just-written slice for this index after a re-gather
    # where the rule pack/catalog moved from v1 → v2 between gathers.
    slice_ = {
        version_key: "v2",
        f"expected_{version_key}": "v1",
    }
    # Act: dispatch only this index's freshness check (B2 itself isn't touched).
    result = default_freshness_registry.dispatch_all({index_name: slice_}, head="deadbeef")
    # Assert: typed Stale with the expected discriminator.
    freshness = result[index_name]
    assert isinstance(freshness, Stale)
    assert isinstance(freshness.reason, DigestMismatch)
    assert freshness.reason.expected == "v1"
    assert freshness.reason.actual == "v2"
```

```python
# tests/unit/schema/test_layer_d_e_g_subschemas_no_extra.py
"""AC-9 — every nested object in every Step-6 sub-schema declares
additionalProperties: false (Phase 1 ADR-0004 convention)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

SUBSCHEMA_ROOTS = [
    Path("src/codegenie/schema/probes/layer_d"),
    Path("src/codegenie/schema/probes/layer_e"),
    Path("src/codegenie/schema/probes/layer_g"),
]


def _walk_objects(node: object, path: str = "$"):
    if isinstance(node, dict):
        if node.get("type") == "object" or "properties" in node:
            yield path, node
        for k, v in node.items():
            yield from _walk_objects(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk_objects(v, f"{path}[{i}]")


@pytest.mark.parametrize("root", SUBSCHEMA_ROOTS)
def test_every_object_rejects_extra(root: Path) -> None:
    for schema_path in root.glob("*.schema.json"):
        schema = json.loads(schema_path.read_text())
        for jpath, obj in _walk_objects(schema):
            assert obj.get("additionalProperties") is False, (
                f"{schema_path}:{jpath} permits extra properties"
            )
```

### Green — make it pass

Skeleton for `test_coverage_mapping.py` (~180 LOC). Pattern mirrors `semgrep.py`:

```python
# src/codegenie/probes/layer_g/test_coverage_mapping.py
"""TestCoverageMappingProbe — Layer G, medium heaviness.

Reads coverage/lcov.info or coverage/coverage-final.json if present;
emits a typed test_coverage_map slice. The raw artifact Phase 3's
TestInventoryAdapter.tests_exercising projects against.

No new external CLI — file-only readers. Phase 2 deliberately ships
the raw evidence without per-line attribution (Phase 3 adapter concern).

Sources:
- ../phase-arch-design.md §"Component design" #5.
- ../../localv2.md §5.6 G3.
- ../../../production/adrs/0030-graph-aware-context-queries.md.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from codegenie.ids import ProbeId
from codegenie.probes._shared.scanner_outcome import (
    ScannerFailed,
    ScannerOutcome,
    ScannerRan,
    ScannerSkipped,
)
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, register_probe

_MAX_BYTES = 64 * 1024 * 1024
__all__ = ["TestCoverageMappingProbe", "TestCoverageSlice", "CoverageRecord"]


class CoverageRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    test_file: str | None
    source_file: str
    lines_covered: tuple[int, ...]


class TestCoverageSlice(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    outcome: ScannerOutcome
    format: Literal["lcov", "istanbul"] | None
    files_seen: int | None


def _parse_lcov(raw: bytes) -> tuple[tuple[CoverageRecord, ...], str | None]:
    # SF: ... DA: line,hit ... end_of_record state machine. ParseError on truncation.
    ...


def _parse_istanbul(raw: bytes) -> tuple[tuple[CoverageRecord, ...], str | None]:
    # json.loads + iterate. Smart constructor; ValidationError → str reason.
    ...


@register_probe(heaviness="medium")
class TestCoverageMappingProbe(Probe):
    probe_id = ProbeId("test_coverage_mapping")
    applies_to_tasks: tuple[str, ...] = ("*",)
    applies_to_languages: tuple[str, ...] = ("*",)
    timeout_seconds = 30

    def _run(self, ctx: ProbeContext) -> ProbeOutput:
        lcov = ctx.repo_root / "coverage" / "lcov.info"
        istanbul = ctx.repo_root / "coverage" / "coverage-final.json"
        target = lcov if lcov.exists() else (istanbul if istanbul.exists() else None)
        if target is None:
            return self._wrap(ScannerSkipped(reason="no_coverage_artifact"),
                              format=None, files_seen=None, confidence="low")
        if target.stat().st_size > _MAX_BYTES:
            return self._wrap(ScannerFailed(exit_code=0, stderr_tail="oversized"),
                              format=None, files_seen=None, confidence="low")
        raw = target.read_bytes()
        fmt: Literal["lcov", "istanbul"] = "lcov" if target.name == "lcov.info" else "istanbul"
        parsed, reason = (_parse_lcov if fmt == "lcov" else _parse_istanbul)(raw)
        if reason is not None:
            return self._wrap(ScannerFailed(exit_code=0, stderr_tail=reason),
                              format=fmt, files_seen=None, confidence="low")
        return self._wrap(ScannerRan(findings=list(parsed)),
                          format=fmt, files_seen=len({r.source_file for r in parsed}),
                          confidence="high")

    def _wrap(self, outcome: ScannerOutcome, *, format: Literal["lcov", "istanbul"] | None,
              files_seen: int | None, confidence: str) -> ProbeOutput:
        slice_ = TestCoverageSlice(outcome=outcome, format=format, files_seen=files_seen)
        return ProbeOutput(probe_id=self.probe_id, confidence=confidence,
                           schema_slice=slice_.model_dump(mode="json"), errors=[])
```

Then the three freshness registrations are added to `semgrep.py`, `gitleaks.py`, `conventions/loader.py` — each is a ~10-LOC module-level function decorated with `@register_index_freshness_check(name)`.

### Refactor — clean up

- **Do not extract a `_register_rule_pack_freshness(name, version_key)` helper.** Three call sites is one short of Rule-of-Three — and the three sites already share the registry decorator. The duplication is in the 5-line body, which is intentional: each scanner owns its freshness contract in its own file. A future `bun-test-coverage` scanner adds a fourth registration the same way — by writing the same ~10 LOC in its own module.
- The sub-schema regen script (`scripts/regen_subschemas.py`) is reviewed-as-code; the committed `.schema.json` files are the source of truth. Two consecutive runs must produce byte-identical output (Phase 1 Step-6 discipline).
- `CoverageRecord.lines_covered` is a `tuple[int, ...]` not a `list[int]` so the Pydantic model stays `frozen=True`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/layer_g/test_coverage_mapping.py` | New file ≤ 200 LOC — the fifth Layer G probe. |
| `src/codegenie/probes/layer_g/semgrep.py` | Add module-level `@register_index_freshness_check("semgrep")` block (~10 LOC). |
| `src/codegenie/probes/layer_g/gitleaks.py` | Add module-level `@register_index_freshness_check("gitleaks")` block (~10 LOC). |
| `src/codegenie/conventions/loader.py` | Add module-level `@register_index_freshness_check("conventions")` block (~10 LOC). |
| `src/codegenie/schema/probes/layer_d/*.schema.json` | New — 7 sub-schemas for Layer D (`skills_index`, `conventions`, `adrs`, `repo_notes`, `repo_config`, `policy`, `exceptions`, `external_docs`). |
| `src/codegenie/schema/probes/layer_e/*.schema.json` | New — 3 sub-schemas for Layer E (`ownership`, `service_topology_stub`, `slo_stub`). |
| `src/codegenie/schema/probes/layer_g/*.schema.json` | New — 5 sub-schemas for Layer G (`semgrep`, `ast_grep`, `ripgrep_curated`, `gitleaks`, `test_coverage_mapping`). |
| `scripts/regen_subschemas.py` | New — reviewed-as-code regen helper; `additionalProperties: false` post-processor; sorted keys. |
| `tests/unit/probes/layer_g/test_test_coverage_mapping.py` | New — 7 tests for the probe. |
| `tests/unit/probes/layer_g/test_scanner_loc_ceiling.py` | Extend `SCANNER_MODULES` with the fifth file. |
| `tests/unit/indices/test_phase2_freshness_registrations.py` | New — 3 import-time-registration tests. |
| `tests/unit/schema/test_layer_d_e_g_subschemas_no_extra.py` | New — every-object-rejects-extra walker. |
| `tests/integration/probes/test_rule_pack_drift_marks_stale.py` | New — parametrized over the three indices. |

## Out of scope

- **Per-line coverage attribution / call-graph projection.** That's Phase 3's `TestInventoryAdapter.tests_exercising(symbol)` adapter (`production/adrs/0030-graph-aware-context-queries.md`). Phase 2 ships the raw `test_coverage_map` slice; the adapter projects against it.
- **Coverage-tool selection (c8, jest, vitest, nyc).** A strategy registry like `@register_dep_graph_strategy` (S1-10) is the right shape if Phase 3 finds it needs ecosystem-specific coverage tooling — but Phase 2 reads on-disk lcov / Istanbul JSON only, with no tool selection. The strategy registry would be premature here.
- **Invoking a coverage CLI (`bun test --coverage`, `pytest --cov`).** Phase 2 reads existing coverage artifacts; running the test suite is a Phase-4+ Planner concern, not a gatherer concern. If a future story adds CLI invocation, the binary lands in `ALLOWED_BINARIES` first (02-ADR-0001 amendment), and the call routes through `run_external_cli` (S1-07).
- **`SecretRedactor` invocation inside the probe.** That's the writer chokepoint's job (02-ADR-0005, S3-03). Coverage slices return raw `CoverageRecord`s; the writer redacts before disk.
- **Phase-4+ rule-pack vendor advisories.** Each scanner's `rule_pack_version` is whatever string it emits today — semantic versioning of the rule pack content is the scanner vendor's contract, not codewizard-sherpa's. The freshness check is "is the string the same as last gather" — a `DigestMismatch` is a `DigestMismatch`.

## Notes for the implementer

1. **The Open/Closed promise is the story's whole point.** Three new indices, zero edits to `IndexHealthProbe`. AC-13's "B2 file is not in this PR's changed files" assertion is the load-bearing test of the S1-02 registry's design. If you find yourself reaching for `index_health.py` to teach B2 about `semgrep`, **stop** — the registration must happen in `semgrep.py` and B2 must learn via the registry's dispatch loop. If `dispatch_all()` doesn't already produce the right shape, the right fix is in `indices/registry.py` (S1-02), not in B2.
2. **Module-import time registration is non-negotiable.** A lazy "register on first dispatch" pattern would silently fail AC-12. The decorator must run when the module is imported — which means the import-side-effect must be triggered by *somebody* importing `codegenie.probes.layer_g.semgrep` (the probe registry's `_PROBE_REGISTRY` already pulls it in via `codegenie.probes.__init__` — verify this chain is intact). If a future contributor adds lazy loading to the probe registry, both the probe and the freshness registrations break together — which is the right coupling.
3. **`test_coverage_mapping.py` is structurally the fifth Layer G scanner, not a sibling pattern.** S6-06 + S6-07 establish "one file per Layer G scanner; no shared base class." This story is the test of that discipline at scale — five scanners, five files, zero shared `ScannerRunner`. The Pydantic-smart-constructor + `ScannerOutcome`-payload + `run_external_cli`-routing patterns are inline in each file. If you find yourself extracting a helper, count the call sites first (Rule of Three).
4. **`rule_pack_version` is the freshness key, not file mtime.** A semgrep rule-pack file may be unchanged on disk while a downloaded rule pack version moves; conversely the file may rewrite with the same logical version. The freshness check reads `slice["rule_pack_version"]` (the string semgrep emits in its own output) — *not* `os.path.getmtime`. The pre-commit `forbidden-patterns` hook (S1-11) bans mtime probes inside `index_health.py`; the same discipline applies to these registrations.
5. **Sub-schemas must reject extra fields at every level.** Phase 1 ADR-0004's `additionalProperties: false` convention — `tests/unit/schema/test_layer_d_e_g_subschemas_no_extra.py` walks the JSON tree to enforce it. The regen script's post-processor adds the property at every `type: "object"` / `properties:`-bearing node; don't hand-edit schemas to drop the property.
6. **The rule-pack-drift integration test is the proof, not the spec.** AC-14 is parametrized over three indices because that's the symmetry — if the test passes for `semgrep` and not `gitleaks`, the registration in `gitleaks.py` is broken. The parametrization is what makes a regression on the fourth scanner (`runtime_trace`, S5-05) immediately visible too: failing one row of the parametrize tells you exactly which freshness contract drifted.
