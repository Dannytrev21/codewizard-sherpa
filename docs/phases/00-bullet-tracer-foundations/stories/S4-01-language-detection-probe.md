# Story S4-01 — `LanguageDetectionProbe` + registration

**Step:** Step 4 — Cut the vertical slice: CLI, `LanguageDetectionProbe`, fixtures, end-to-end smoke
**Status:** Done — 2026-05-13. All 11 ACs verified; 13/13 new unit tests green; full suite 500/500; coverage 92.68%; mypy `--strict` + ruff + pre-commit all clean. Attempt log: [`_attempts/S4-01.md`](_attempts/S4-01.md). Implementation: [`src/codegenie/probes/language_detection.py`](../../../../src/codegenie/probes/language_detection.py). Tests: [`tests/unit/test_language_detection_probe.py`](../../../../tests/unit/test_language_detection_probe.py). Sub-schema amendment: [`src/codegenie/schema/probes/language_detection.schema.json`](../../../../src/codegenie/schema/probes/language_detection.schema.json) (`$id` → `v0.1.1`).
**Effort:** S
**Depends on:** S3-05
**See also:** S2-05 (sub-schema this story amends in-PR), S4-02 (CLI wires schema_slice into envelope under `probes.<name>`), S4-04 (smoke + cache-hit test; reads `language_stack.counts` / `language_stack.primary`)
**ADRs honored:** ADR-0007, ADR-0010, ADR-0013, ADR-0008, ADR-0003 (sub-schema `$id` bump triggers surgical cache invalidation — Phase 0 has no shipped cache entries, so the bump is free)

## Validation notes

Hardened on 2026-05-13 by `phase-story-validator` v1. Three critics returned **22 findings** (7 Coverage + 7 Test-Quality + 7 Consistency + 1 NIT; 7 block, 13 harden, 2 nit; 0 `NEEDS RESEARCH`). Full report at [`_validation/S4-01-language-detection-probe.md`](_validation/S4-01-language-detection-probe.md). Material changes:

- **Pinned the `language_stack` wrapper as a coordinated in-PR amendment to S2-05's sub-schema.** Pre-hardening, AC-2 emitted `schema_slice = {"language_stack": {"counts": ..., "primary": ...}}` (per arch §Gap 4 line 970 and `localv2.md §5.1 A1` lines 394–406) but the on-disk sub-schema (`src/codegenie/schema/probes/language_detection.schema.json`, shipped by S2-05) defines `counts`/`primary` at the slice top with `additionalProperties: false`, and `tests/unit/test_schema_validation.py` (lines 52–101) enforces that flat shape. Result: S4-02 step 9 (envelope JSON Schema validation) would have failed on every gather. Per CLAUDE.md Rule 7 (surface, don't average — pick the more authoritative source), localv2 + arch win; this story ships the sub-schema rewrite **in the same PR**. Sub-schema `$id` bumps `v0.1.0 → v0.1.1`; probe `version` bumps in lockstep `0.1.0 → 0.1.1` (cache-key tuple coherence per ADR-0003). `tests/unit/test_schema_validation.py` payloads update to wrap.
- **Pinned `declared_inputs` to glob form only.** Pre-hardening, AC-1 listed bare extensions `[".js", ".mjs", ...]` with "or the equivalent `**/*.<ext>` glob form" as an escape hatch. `cache/keys.py:declared_inputs_for` (lines 91–105) uses `snapshot.root.rglob(pattern)` — `rglob(".js")` matches files literally *named* `.js` (none in normal repos), so bare extensions silently resolve to an empty input set. `content_hash_of_inputs([])` is constant → cache key collides across any probes that differ only in declared_inputs → false-positive warm-run cache hits that mask real source changes. AC-1 now mandates `["**/*.js", "**/*.mjs", "**/*.cjs", "**/*.ts", "**/*.tsx", "**/*.py", "**/*.go", "**/*.rs", "**/*.java", "**/*.rb", "**/*.php"]` exactly; the escape hatch is gone.
- **Pinned `layer="A"` and `requires=[]` as required class attributes.** Pre-hardening AC-1 omitted both. The `Probe` ABC (`src/codegenie/probes/base.py:54-63`) declares `layer: Literal["A".."G"]` and `requires: list[str]` as bare class attributes with **no defaults**. `tests/unit/test_probe_contract.py:221` includes both in the frozen field list. Without setting them, AC-7's contract-conformance check (`hasattr(LanguageDetectionProbe, "layer")` etc.) fails. Story Notes line 164 pre-hardening said "do not set `requires=[...]`" — contradicting the ABC. Reworded to `requires=[]` (empty list — prelude has no upstream deps).
- **Pinned empty-repo case to `primary=None`** (not `<lang-or-None>`) and updated the sub-schema's `primary` to `{"type": ["string", "null"]}` in the same in-PR amendment. S4-04's existing assertion `language_stack.primary in (None, "")` (line 53) is compatible. `None` is more honest than `""` — it encodes "no primary detected" rather than a magic empty string. Empty repo also returns `counts={}`, `confidence="high"` (a successful scan of zero files is evidence, not absence-of-evidence).
- **Added vendor-dir deny-list as load-bearing AC.** Pre-hardening, the probe walks every file under `snapshot.root` indiscriminately. Real repos have `.git/`, `node_modules/`, `vendor/`, `dist/`, `build/`, `__pycache__/`, `.venv/`, `target/`, `out/`, `.next/`, `.cache/` — `node_modules` alone dwarfs source by 100×, and `primary` becomes whatever the largest vendor tree contains. Phase 0 fixtures are clean so the smoke would pass for the wrong reason. AC-3 now pins a module-level `_SKIP_DIRS: frozenset[str]` that the walker skips; an adversarial unit test (1 root `.js` + 100 `node_modules/*/*.js`) drives it in red.
- **Pinned case-insensitive extension lookup.** A `FOO.JS` on Linux ext4 counts as nothing pre-hardening. Step 2 now lowercases the extension via `.casefold()` before dict lookup. Red test added.
- **Pinned broken-symlink behavior.** `Path.resolve()` on a dangling symlink raises `FileNotFoundError` (or `OSError` on some platforms). Pre-hardening try/except caught `OSError` generically with no test. AC-4 splits broken-symlink (skip + `probe.symlink.broken`) from escaped-symlink (skip + `probe.symlink.escaped`); both have dedicated red tests.
- **Pinned deterministic alpha tie-break with a test.** Pre-hardening, the Refactor phase mentioned alpha tie-break but no test enforced it. Mutation: `max(counts, key=counts.get)` (insertion-order tie-break) passes 2js+1py but breaks on 2js+2py. New red test `test_primary_alpha_tiebreak` (2 `.js` + 2 `.py` → `primary == "javascript"`).
- **Pinned structlog event emission as load-bearing.** ADR-0010 §Consequences and Phase 8's Trust-Aware gates subscribe to `probe.start` / `probe.success` / `probe.failure`. Pre-hardening, zero tests asserted them — a mutation that drops `probe.failure` on the error path would slip through. Two new red tests use `structlog.testing.capture_logs()` to pin happy + error paths.
- **Pinned `os.scandir` access pattern to `import os` (not `from os import scandir`).** S4-04 (line 197) flagged this as a gap requiring S4-01 to declare its choice. Promoted to AC-5: module uses `import os` and calls `os.scandir(...)`, declared in the module docstring; monkeypatch target is unambiguously `codegenie.probes.language_detection.os.scandir`.
- **Pinned `counts` as a plain `dict[str, int]`** (`dict(counter)`, not the raw `Counter`). Avoids ambiguity at the `_ProbeOutputValidator` JSON-shape walk (ADR-0010).
- **Pinned `raw_artifacts==[]`, `warnings==[]`, `duration_ms>=0` on happy path.** Pre-hardening, only `errors==[]` and `confidence` were checked — an implementer could emit `duration_ms=-1` or stale `warnings=["lorem"]` without test failure.
- **Strengthened contract-conformance test** to a subset check on `declared_inputs` (every supported-language extension has its glob) plus exact equality on `layer`, `tier`, `requires`. Pre-hardening `declared_inputs != ["**/*"]` survives the mutation `["**/*.py"]` (missing JS).
- **Inlined helper definitions** (`_snapshot_from`, `_context_for`) in the TDD plan so each red test is reproducible; pre-hardening they were named but undefined, opening the door to inconsistent implementer fabrications across attempts.
- **Pinned symlink-escape log payload to relative path only.** Pre-hardening Notes (line 163) said "the sanitizer would scrub it anyway" — but `OutputSanitizer.scrub` (ADR-0008) is a two-pass chokepoint on `RepoContext` emit, **not** a structlog processor. A symlink target leaking `/Users/<user>/...` lands in logs unscrubbed. Step 2 now emits `str(Path(entry.path).relative_to(snapshot.root))`; resolved targets are never logged. Adversarial test asserts the event payload does not contain the resolved target.

## Context

This is the first concrete probe in the system and the prelude-pass anchor — its `schema_slice` is what every other probe in Phase 1 will read off `enriched_snapshot.detected_languages` (Gap 4 in the architecture). It also pins the structural property that makes the bullet tracer's load-bearing cache-hit test work: `declared_inputs` is scoped to language-extension globs, not `["**/*"]`, so editing `README.md` between two gathers must not invalidate the cache.

This story is the first time the harness internals built in Step 3 receive a real subclass of `Probe`. It's the smallest possible end of the vertical slice; the CLI (S4-02) wires it into the runtime path. It also ships a **coordinated in-PR amendment** to S2-05's `language_detection.schema.json` sub-schema — see Validation notes bullet #1 for the rationale; per CLAUDE.md Rule 7 the schema lifts to match the design intent (`language_stack` wrapper), not the inverse.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — Probe + Registry` — `default_registry` and `@register_probe` shape.
  - `../phase-arch-design.md §Scenarios — Scenario 1: Cold gather over a JS fixture` — the runtime path this probe participates in.
  - `../phase-arch-design.md §Scenarios — Scenario 2: Warm gather (cache hit, the bullet tracer's load-bearing exit)` — why `declared_inputs` is extension-scoped, not `["**/*"]`.
  - `../phase-arch-design.md §Edge cases` — row 1 (PermissionError mid-walk → `confidence="low"`) and row 4 (symlink resolving outside repo root → skip + `probe.symlink.escaped`).
  - `../phase-arch-design.md §Gap analysis — Gap 4` — `tier="base"` engages the coordinator prelude pass; arch line 970 confirms the slice shape is `{"language_stack": {"counts": ..., "primary": ...}}`.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0007-probe-contract-frozen-snapshot.md` — ADR-0007 — must subclass the frozen `Probe` ABC from `probes/base.py` without altering it.
  - `../ADRs/0010-pydantic-probe-output-validator.md` — ADR-0010 — `schema_slice` values must be JSON-representable; the validator runs in the coordinator after this probe returns. Phase 8's Trust-Aware gates subscribe to `probe.{start,success,failure}` structlog events.
  - `../ADRs/0013-layered-additional-properties-schema.md` — ADR-0013 — emit only fields the per-probe sub-schema accepts; the in-PR sub-schema amendment wraps `counts`/`primary` under `language_stack` so the emitted slice validates.
  - `../ADRs/0008-output-sanitizer-two-pass-chokepoint.md` — ADR-0008 — paths emitted from this probe go through the sanitizer; emit short relative names where possible. **Note:** the sanitizer is NOT a structlog processor; log payloads from this probe must be sanitized at the call site (Notes §Symlink logging).
  - `../ADRs/0003-two-level-cache-key-schema-versioning.md` — ADR-0003 — per-probe schema-version bumps are surgical cache invalidations; bumping the sub-schema `$id` and probe `version` together keeps the cache-key tuple coherent.
- **Source design:**
  - `../../../localv2.md §4` — `Probe` ABC, `ProbeOutput` dataclass.
  - `../../../localv2.md §5.1 A1` — `LanguageDetection` probe inventory entry (Phase 0 ships extension-counting only; no tree-sitter). Output slice shape (`language_stack: {primary, ...}`).
- **Existing code:**
  - `src/codegenie/probes/base.py` — the frozen ABC this probe subclasses. Note `layer` and `requires` are class-attribute declarations with **no defaults**.
  - `src/codegenie/probes/__init__.py` — register the probe here.
  - `src/codegenie/probes/registry.py` — `@register_probe` decorator; treats `version` as convention (not part of the frozen ABC).
  - `src/codegenie/cache/keys.py` — `declared_inputs_for` uses `Path.rglob(pattern)`; bare extensions match nothing.
  - `src/codegenie/coordinator/validator.py` — `_ProbeOutputValidator` enforces JSON-leaf closure and secret-key regex.
  - `src/codegenie/schema/probes/language_detection.schema.json` — the sub-schema this probe's output validates against. This story **amends** it in-PR (see Validation notes #1).
  - `tests/unit/test_schema_validation.py` — assertions over the slice shape; payloads updated by the in-PR amendment.

## Goal

`from codegenie.probes import default_registry; default_registry.for_task("__bullet_tracer__", frozenset({"unknown"}))` returns a tuple containing `LanguageDetectionProbe`, and instantiating + running it against `tests/fixtures/js_only/` produces a `ProbeOutput` whose `schema_slice == {"language_stack": {"counts": {"javascript": 5}, "primary": "javascript"}}`, whose `confidence == "high"`, whose `raw_artifacts == []`, whose `warnings == []`, and whose envelope-mounted form (under `probes.language_detection`) validates against the in-PR-amended sub-schema.

## Acceptance criteria

### Class shape

- [ ] **AC-1.** `src/codegenie/probes/language_detection.py` defines `class LanguageDetectionProbe(Probe)` with the following class attributes (all required — `layer`, `requires`, `declared_inputs` are bare class attributes on the ABC with **no defaults**):
  - `name = "language_detection"`
  - `version = "0.1.1"` (lockstep with the sub-schema `$id` bump; see AC-2)
  - `layer = "A"`
  - `tier = "base"` (engages the coordinator prelude pass per Gap 4)
  - `applies_to_tasks = ["*"]`
  - `applies_to_languages = ["*"]`
  - `requires = []` (prelude has no upstream deps)
  - `declared_inputs = ["**/*.js", "**/*.mjs", "**/*.cjs", "**/*.ts", "**/*.tsx", "**/*.py", "**/*.go", "**/*.rs", "**/*.java", "**/*.rb", "**/*.php"]` exactly — bare extensions are forbidden because `cache/keys.py:declared_inputs_for` uses `Path.rglob()` and `rglob(".js")` matches nothing.

### Output shape

- [ ] **AC-2.** `LanguageDetectionProbe.run(snapshot, ctx)` returns a `ProbeOutput` whose:
  - `schema_slice == {"language_stack": {"counts": {<lang>: <int>, ...}, "primary": <lang-with-max-count-or-None>}}`
  - `counts` is a plain `dict[str, int]` (cast `Counter → dict` before emit so the Pydantic validator sees a vanilla dict)
  - `primary` is the alpha-sorted-first language within the max-count set, or `None` if `counts == {}`
  - `confidence == "high"` on any successful scan (including an empty repo — a successful scan of zero files is evidence)
  - `raw_artifacts == []` (Phase 0 does not write artifacts for this probe per localv2 §5.1 A1)
  - `warnings == []` on the happy path
  - `errors == []` on the happy path
  - `duration_ms >= 0` (measured via `time.perf_counter()` deltas)

  The envelope-mounted form (`envelope["probes"]["language_detection"] = output.schema_slice`) validates against the in-PR-amended sub-schema (`v0.1.1`).

### In-PR sub-schema amendment (S2-05 coordination, ADR-0013 + ADR-0003)

- [ ] **AC-3.** This PR amends `src/codegenie/schema/probes/language_detection.schema.json`:
  - `$id` bumps to `https://codewizard-sherpa.dev/schemas/probes/language_detection/v0.1.1.json`.
  - Schema wraps `counts`/`primary` under a required `language_stack` object:
    ```json
    {"type": "object", "additionalProperties": false, "required": ["language_stack"],
     "properties": {"language_stack": {
       "type": "object", "additionalProperties": false, "required": ["counts", "primary"],
       "properties": {
         "counts": {"type": "object", "additionalProperties": {"type": "integer", "minimum": 0}},
         "primary": {"type": ["string", "null"]}
       }}}}
    ```
  - `tests/unit/test_schema_validation.py` payloads at lines 57, 67, 78, 93 update to the `language_stack`-wrapped shape; all four existing tests stay green. Add a new test `test_language_detection_primary_null_is_valid_for_empty_repo` that proves `primary: null` validates.
  - The envelope at `src/codegenie/schema/repo_context.schema.json` updates its `$ref` to `v0.1.1.json` (one line).
  - **Cache invalidation scope (ADR-0003):** Phase 0 ships no committed cache entries; the `$id` bump invalidates only `language_detection` and only on disk caches created by developer-local runs, which is exactly the surgical scope ADR-0003 commits to.

### Walker behavior

- [ ] **AC-4.** The walker:
  - Uses `os.scandir` (not `pathlib.Path.glob`/`rglob`) so S4-04 can monkeypatch invocation count.
  - Skips directories whose `entry.name` is in a module-level `_SKIP_DIRS: frozenset[str]` containing at minimum `{".git", "node_modules", "vendor", "dist", "build", "__pycache__", ".venv", "target", "out", ".next", ".cache"}`. The deny-list is checked **before** any recursion into the directory; entries under skipped dirs are never `scandir`-ed.
  - Lowercases the file extension via `.casefold()` before dict-lookup (`FOO.JS` counts as javascript).
  - Maps `.js`/`.mjs`/`.cjs` → `"javascript"`; `.ts`/`.tsx` → `"typescript"`; `.py` → `"python"`; `.go` → `"go"`; `.rs` → `"rust"`; `.java` → `"java"`; `.rb` → `"ruby"`; `.php` → `"php"`. Unknown extensions are silently skipped.
  - Handles three symlink cases distinctly:
    1. **Symlink whose `Path.resolve()` lands outside `snapshot.root.resolve()`** → skip + emit `probe.symlink.escaped` structlog event. Event payload's `path` field is `str(Path(entry.path).relative_to(snapshot.root))` (relative to repo root; resolved target is **never** logged — sanitizer is not a structlog processor per ADR-0008).
    2. **Broken symlink** (target does not exist; `Path.resolve()` raises `FileNotFoundError`/`OSError`) → skip + emit `probe.symlink.broken` structlog event with the same relative-path payload rule. No exception propagates.
    3. **Symlink resolving inside `snapshot.root`** → follow as a normal file (count its extension).

### Error path

- [ ] **AC-5.** `PermissionError` raised mid-walk is caught; the probe returns `ProbeOutput(errors=["PermissionError: ..."], confidence="low", raw_artifacts=[], warnings=[], duration_ms=<measured>, schema_slice=<partial-or-empty-counts-but-no-language_stack-key-missing>)`. The probe never re-raises a non-`CodegenieError`. Implementation note: schema_slice still has the `language_stack` wrapper with whatever counts accumulated before the error; `primary` is recomputed from the partial counts.

### Module-level structural pins

- [ ] **AC-6.** The module:
  - Uses `import os` (NOT `from os import scandir`) and calls `os.scandir(...)`, declaring this choice in the module docstring so S4-04's monkeypatch target (`codegenie.probes.language_detection.os.scandir`) is unambiguous.
  - Exposes `_SKIP_DIRS` and the extension map at module level (not nested inside the class) so tests can introspect them.

### Structlog lifecycle events (ADR-0010, Phase 8 dependency)

- [ ] **AC-7.** The probe emits exactly:
  - One `probe.start` event with `probe="language_detection"` before scanning begins.
  - On success: one `probe.success` event with `probe="language_detection"`, `confidence=<value>`, `count_total=<sum-of-counts>`.
  - On error path (any caught exception that flips `confidence` to `"low"`): one `probe.failure` event with `probe="language_detection"` and the error class name.
  - `probe.symlink.escaped` and `probe.symlink.broken` are emitted at most once per offending entry (no per-recursion-level duplicates).

### Validation + registration

- [ ] **AC-8.** A Pydantic validation test (per ADR-0010) asserts that the probe's `schema_slice` passes `_ProbeOutputValidator` (no `bytes`, no `Callable`, no secret-shaped keys, `confidence` is one of the three literals) — both on a happy-path fixture and on the empty-repo case (`primary=None`).
- [ ] **AC-9.** A probe-contract-conformance test (per ADR-0007) asserts:
  - `issubclass(LanguageDetectionProbe, Probe)`.
  - Exact equality: `LanguageDetectionProbe.layer == "A"`, `tier == "base"`, `requires == []`, `name == "language_detection"`, `version == "0.1.1"`.
  - For every value in the extension-to-language map (`javascript`, `typescript`, `python`, `go`, `rust`, `java`, `ruby`, `php`), at least one glob in `declared_inputs` ends with an extension that maps to that language (subset check — kills the mutation `["**/*.py"]` that survives the pre-hardened inequality check).
  - Does **not** re-run the frozen-ABC fingerprint test (already covered in `tests/unit/test_probe_contract.py`).
- [ ] **AC-10.** `src/codegenie/probes/__init__.py` imports `LanguageDetectionProbe` so it is registered at package import time; `default_registry.all_probes()` includes it; `default_registry.for_task("__bullet_tracer__", frozenset({"unknown"}))` returns a tuple containing it.
- [ ] **AC-11.** `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/probes/language_detection.py`, and `pytest tests/unit/test_language_detection_probe.py tests/unit/test_schema_validation.py` all pass.

## Implementation outline

1. Subclass `Probe` from `probes/base.py`; declare class attributes per AC-1 (set ALL of `name`, `version`, `layer`, `tier`, `applies_to_tasks`, `applies_to_languages`, `requires`, `declared_inputs` — the ABC has no defaults for `layer`, `requires`, `declared_inputs`).
2. Define module-level constants:
   - `_SKIP_DIRS: frozenset[str] = frozenset({".git", "node_modules", "vendor", "dist", "build", "__pycache__", ".venv", "target", "out", ".next", ".cache"})`
   - `_EXT_TO_LANG: dict[str, str]` mapping lowercased suffixes (with leading dot) to canonical language names.
3. Implement the walker using `os.scandir` (synchronous; bounded by the coordinator's `wait_for`). For each entry:
   - If `entry.is_dir(follow_symlinks=False)` and `entry.name in _SKIP_DIRS`: skip without recursing.
   - If `entry.is_dir(follow_symlinks=False)`: recurse.
   - If `entry.is_symlink()`:
     - `try: resolved = Path(entry.path).resolve(strict=True)` → `FileNotFoundError`/`OSError` → emit `probe.symlink.broken`, skip.
     - If `not resolved.is_relative_to(snapshot.root.resolve())` → emit `probe.symlink.escaped`, skip.
     - Otherwise follow as a normal file (count its extension).
   - For regular files: extract `Path(entry.name).suffix.casefold()`, look up in `_EXT_TO_LANG`, increment a `Counter`.
   - **Log payload rule:** for both `probe.symlink.{broken,escaped}`, the event's `path` field is `str(Path(entry.path).relative_to(snapshot.root))`; the resolved target is never logged.
4. Build `counts = dict(counter)`; `primary = sorted(c for c, v in counts.items() if v == max(counts.values()))[0] if counts else None`. Emit `schema_slice = {"language_stack": {"counts": counts, "primary": primary}}`.
5. Wrap the walk in try/except for `PermissionError` and other `OSError` subclasses (excluding the broken-symlink and escape paths, which are already handled in the loop); collect into `errors=[...]`; set `confidence="low"` on any caught error; `confidence="high"` on a clean scan (including empty repo). Always emit `language_stack` even on error (with whatever partial `counts` accumulated).
6. Emit `probe.start` before scanning; `probe.success` (with `confidence`, `count_total=sum(counts.values())`) on a clean scan; `probe.failure` (with the error class name) on any caught error. Use the structlog logger constants from `src/codegenie/logging.py`.
7. Measure `duration_ms` via `time.perf_counter()` deltas around the walk.
8. Register the probe via the `@register_probe` decorator and the explicit import in `probes/__init__.py`.
9. **In-PR amendment (AC-3):**
   - Rewrite `src/codegenie/schema/probes/language_detection.schema.json` to the `language_stack`-wrapped shape; bump `$id` to `v0.1.1.json`.
   - Update `src/codegenie/schema/repo_context.schema.json`'s `$ref` line to `v0.1.1.json`.
   - Update `tests/unit/test_schema_validation.py` payloads at lines 57, 67, 78, 93 to use the wrapped shape; add `test_language_detection_primary_null_is_valid_for_empty_repo`.

## TDD plan — red / green / refactor

### Red — write the failing tests first

Test file path: `tests/unit/test_language_detection_probe.py`

```python
# tests/unit/test_language_detection_probe.py
"""Red tests for S4-01. Helpers defined inline; no conftest dependency."""
from __future__ import annotations
import asyncio
import os
from logging import getLogger
from pathlib import Path

import pytest
import structlog
from structlog.testing import capture_logs

from codegenie.probes.base import ProbeContext, ProbeOutput, RepoSnapshot, Task


def _snapshot(root: Path) -> RepoSnapshot:
    return RepoSnapshot(root=root, git_commit=None, detected_languages={}, config={})


def _ctx(root: Path) -> ProbeContext:
    return ProbeContext(
        cache_dir=root / ".cache",
        output_dir=root / ".out",
        workspace=root / ".ws",
        logger=getLogger("test"),
        config={},
    )


def _run(probe, root: Path) -> ProbeOutput:
    return asyncio.run(probe.run(_snapshot(root), _ctx(root)))


# 1. Happy path — counts JS fixture, primary, raw_artifacts, warnings, duration.
def test_counts_js_fixture(tmp_path: Path) -> None:
    (tmp_path / "a.js").write_text("//")
    (tmp_path / "b.js").write_text("//")
    (tmp_path / "c.ts").write_text("//")
    (tmp_path / "d.py").write_text("#")
    from codegenie.probes.language_detection import LanguageDetectionProbe
    output = _run(LanguageDetectionProbe(), tmp_path)
    assert output.schema_slice == {
        "language_stack": {
            "counts": {"javascript": 2, "typescript": 1, "python": 1},
            "primary": "javascript",
        }
    }
    assert output.confidence == "high"
    assert output.errors == []
    assert output.warnings == []
    assert output.raw_artifacts == []
    assert output.duration_ms >= 0


# 2. Pydantic validation — slice survives the trust-boundary walker.
def test_schema_slice_passes_pydantic_validator(tmp_path: Path) -> None:
    (tmp_path / "x.js").write_text("//")
    from codegenie.probes.language_detection import LanguageDetectionProbe
    from codegenie.coordinator.validator import _ProbeOutputValidator
    output = _run(LanguageDetectionProbe(), tmp_path)
    _ProbeOutputValidator(schema_slice=output.schema_slice, confidence=output.confidence)


# 3. Contract conformance — subset check on declared_inputs, exact equality on layer/tier/requires/name/version.
def test_contract_conformance() -> None:
    from codegenie.probes.base import Probe
    from codegenie.probes.language_detection import LanguageDetectionProbe, _EXT_TO_LANG
    assert issubclass(LanguageDetectionProbe, Probe)
    assert LanguageDetectionProbe.name == "language_detection"
    assert LanguageDetectionProbe.version == "0.1.1"
    assert LanguageDetectionProbe.layer == "A"
    assert LanguageDetectionProbe.tier == "base"
    assert LanguageDetectionProbe.requires == []
    # subset check — every language in the map has a corresponding glob; kills "**/*.py"-only mutation
    languages_in_inputs = {
        _EXT_TO_LANG[ext]
        for ext in (Path(g).suffix.casefold() for g in LanguageDetectionProbe.declared_inputs)
        if ext in _EXT_TO_LANG
    }
    assert set(_EXT_TO_LANG.values()).issubset(languages_in_inputs)
    assert LanguageDetectionProbe.declared_inputs != ["**/*"]


# 4. Empty repo — primary None, confidence high, language_stack still present.
def test_empty_repo(tmp_path: Path) -> None:
    from codegenie.probes.language_detection import LanguageDetectionProbe
    output = _run(LanguageDetectionProbe(), tmp_path)
    assert output.schema_slice == {"language_stack": {"counts": {}, "primary": None}}
    assert output.confidence == "high"
    assert output.errors == []


# 5. Vendor-dir deny-list — node_modules etc. are not walked.
def test_skips_well_known_vendor_dirs(tmp_path: Path) -> None:
    (tmp_path / "a.js").write_text("//")
    (tmp_path / "node_modules").mkdir()
    for i in range(100):
        d = tmp_path / "node_modules" / f"pkg-{i}"
        d.mkdir()
        (d / "index.js").write_text("//")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config.js").write_text("//")  # adversarial; should NOT count
    from codegenie.probes.language_detection import LanguageDetectionProbe
    output = _run(LanguageDetectionProbe(), tmp_path)
    assert output.schema_slice["language_stack"]["counts"] == {"javascript": 1}


# 6. Case-insensitive extension.
def test_case_insensitive_extension(tmp_path: Path) -> None:
    (tmp_path / "FOO.JS").write_text("//")
    (tmp_path / "BAR.Ts").write_text("//")
    from codegenie.probes.language_detection import LanguageDetectionProbe
    output = _run(LanguageDetectionProbe(), tmp_path)
    assert output.schema_slice["language_stack"]["counts"] == {"javascript": 1, "typescript": 1}


# 7. Alpha tie-break is deterministic — kills max(counts, key=counts.get) mutation.
def test_primary_alpha_tiebreak(tmp_path: Path) -> None:
    for ext in (".js", ".js", ".py", ".py"):
        (tmp_path / f"x{ext}_{id(ext)}").rename if False else None
    (tmp_path / "a.js").write_text("//")
    (tmp_path / "b.js").write_text("//")
    (tmp_path / "c.py").write_text("#")
    (tmp_path / "d.py").write_text("#")
    from codegenie.probes.language_detection import LanguageDetectionProbe
    output = _run(LanguageDetectionProbe(), tmp_path)
    counts = output.schema_slice["language_stack"]["counts"]
    assert counts == {"javascript": 2, "python": 2}
    assert output.schema_slice["language_stack"]["primary"] == "javascript"  # alpha < "python"


# 8. Escaped symlink → skip + probe.symlink.escaped event; payload is relative path, no resolved target.
def test_symlink_escape_skipped_and_logged(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside_target.js"
    outside.write_text("//")
    link = tmp_path / "escape.js"
    os.symlink(outside, link)
    from codegenie.probes.language_detection import LanguageDetectionProbe
    with capture_logs() as logs:
        output = _run(LanguageDetectionProbe(), tmp_path)
    events = [e for e in logs if e.get("event") == "probe.symlink.escaped"]
    assert len(events) == 1
    assert events[0]["path"] == "escape.js"
    assert str(outside) not in str(events[0])  # resolved target never logged
    assert output.schema_slice["language_stack"]["counts"] == {}


# 9. Broken symlink → skip + probe.symlink.broken; no exception leaks.
def test_broken_symlink_skipped_and_logged(tmp_path: Path) -> None:
    os.symlink(tmp_path / "no_such_target.js", tmp_path / "dangling.js")
    from codegenie.probes.language_detection import LanguageDetectionProbe
    with capture_logs() as logs:
        output = _run(LanguageDetectionProbe(), tmp_path)
    events = [e for e in logs if e.get("event") == "probe.symlink.broken"]
    assert len(events) == 1
    assert events[0]["path"] == "dangling.js"


# 10. PermissionError mid-walk → confidence=low, probe.failure event, no exception leak.
def test_permission_error_demotes_confidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "a.js").write_text("//")
    import codegenie.probes.language_detection as ld
    real_scandir = os.scandir
    def boom(path: object) -> object:
        if str(path) == str(tmp_path):
            raise PermissionError("simulated")
        return real_scandir(path)
    monkeypatch.setattr(ld.os, "scandir", boom)
    from codegenie.probes.language_detection import LanguageDetectionProbe
    with capture_logs() as logs:
        output = _run(LanguageDetectionProbe(), tmp_path)
    assert output.confidence == "low"
    assert output.errors and output.errors[0].startswith("PermissionError")
    assert "language_stack" in output.schema_slice  # wrapper still present
    failure_events = [e for e in logs if e.get("event") == "probe.failure"]
    assert len(failure_events) == 1
    assert failure_events[0]["probe"] == "language_detection"


# 11. Happy-path lifecycle — exactly one probe.start + one probe.success; no probe.failure.
def test_lifecycle_events_happy_path(tmp_path: Path) -> None:
    (tmp_path / "a.js").write_text("//")
    from codegenie.probes.language_detection import LanguageDetectionProbe
    with capture_logs() as logs:
        _run(LanguageDetectionProbe(), tmp_path)
    starts = [e for e in logs if e.get("event") == "probe.start"]
    successes = [e for e in logs if e.get("event") == "probe.success"]
    failures = [e for e in logs if e.get("event") == "probe.failure"]
    assert len(starts) == 1 and starts[0]["probe"] == "language_detection"
    assert len(successes) == 1 and successes[0]["probe"] == "language_detection"
    assert successes[0]["confidence"] == "high"
    assert successes[0]["count_total"] == 1
    assert failures == []


# 12. Registration — probe appears in default_registry.
def test_probe_registered() -> None:
    from codegenie.probes import default_registry
    from codegenie.probes.language_detection import LanguageDetectionProbe
    all_names = {p.name for p in default_registry.all_probes()}
    assert "language_detection" in all_names
    selected = default_registry.for_task("__bullet_tracer__", frozenset({"unknown"}))
    assert any(isinstance(p, LanguageDetectionProbe) for p in selected) or any(
        p is LanguageDetectionProbe or p == LanguageDetectionProbe for p in selected
    )
```

All twelve tests must fail at first with `ModuleNotFoundError: No module named 'codegenie.probes.language_detection'`. Run them; confirm red; commit RED; then implement.

### Green — make it pass

Add `src/codegenie/probes/language_detection.py` with:

- Module docstring declaring the `import os` / `os.scandir(...)` access pattern (so S4-04 monkeypatches the right name).
- `_SKIP_DIRS: frozenset[str]` and `_EXT_TO_LANG: dict[str, str]` at module scope (private, but introspectable by tests).
- `LanguageDetectionProbe(Probe)` subclass with the class attributes from AC-1.
- An `async def run(self, snapshot, ctx) -> ProbeOutput` doing the `os.scandir` walk per outline step 3.
- Structlog event emissions per AC-7.
- `time.perf_counter()` deltas for `duration_ms`.
- Try/except for `PermissionError`/`OSError` around the walk per AC-5.

Add the explicit import to `src/codegenie/probes/__init__.py`.

Ship the in-PR sub-schema amendment (AC-3) in the same commit so `test_schema_validation.py` stays green.

### Refactor — clean up

After green:

- Type hints throughout (`mypy --strict` clean).
- Docstring on `LanguageDetectionProbe` explaining: (a) the prelude-pass role, (b) the extension-scoping rationale for `declared_inputs`, (c) the `os.scandir` access pattern, (d) the `language_stack` wrapper rationale (matches localv2 §5.1 A1 and the v0.1.1 sub-schema).
- Confirm `ruff format` / `ruff check` / `mypy --strict` clean on the module and the amended schema test file.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/probes/language_detection.py` | New file — implements `LanguageDetectionProbe` per ADR-0007 / ADR-0010 |
| `src/codegenie/probes/__init__.py` | Add explicit `from .language_detection import LanguageDetectionProbe` so registration fires |
| `tests/unit/test_language_detection_probe.py` | New test — twelve red tests (counts, validator, contract, empty, skip-dirs, case-insensitive, alpha-tiebreak, symlink-escape, broken-symlink, permission-error, lifecycle-events, registration) |
| `src/codegenie/schema/probes/language_detection.schema.json` | **In-PR amendment (AC-3)** — wrap `counts`/`primary` under `language_stack`; `$id` bumps to `v0.1.1` |
| `src/codegenie/schema/repo_context.schema.json` | **In-PR amendment (AC-3)** — `$ref` line updates to `v0.1.1.json` |
| `tests/unit/test_schema_validation.py` | **In-PR amendment (AC-3)** — payloads at lines 57/67/78/93 update to the wrapped shape; add `test_language_detection_primary_null_is_valid_for_empty_repo` |

## Out of scope

- **CLI wiring (`codegenie gather` invocation)** — handled by story S4-02.
- **End-to-end smoke / cache-hit-on-second-run test** — handled by story S4-04.
- **Golden-output assertions against `tests/fixtures/js_only/`, `polyglot/`, `empty_repo/`** — handled by S4-04 (which also creates the fixtures).
- **`tree-sitter` invocation for ambiguous extensions** — Phase 1's richer A1 probe per `../phase-arch-design.md §Non-goals` item 2.
- **`Dockerfile` detection** — Phase 7; explicitly out of scope per `../phase-arch-design.md §Non-goals` item 3.
- **`declared_resource_budget` field** — added in S3-05 on the base class with a default; this probe inherits the default and does not override.
- **Reading user-defined ignore globs from `.codegenie/config.yaml`** — Phase 1 enhancement; Phase 0's deny-list is a frozen module-level constant.

## Notes for the implementer

- **`declared_inputs` being extension-scoped (glob form, not bare extensions, not `["**/*"]`) is load-bearing** for both the cache-hit-on-second-run test in S4-04 and for the cache-key correctness invariant. `cache/keys.py:declared_inputs_for` calls `snapshot.root.rglob(pattern)`. `rglob(".js")` matches nothing; `rglob("**/*.js")` matches `*.js` files at any depth. If you accidentally set `["**/*"]` the second-run cache invalidates on every `README.md` edit S4-04 performs.
- **The probe's walker must call `os.scandir` (not `pathlib.Path.glob`)** — S4-04 monkeypatches `os.scandir` at the `codegenie.probes.language_detection` module level to assert zero invocations on the cache-hit path. AC-6 pins `import os` (so the monkeypatch target is `codegenie.probes.language_detection.os.scandir`); the module docstring must state this choice.
- **Symlink-escape check** uses `entry.is_symlink()` + `Path(entry.path).resolve(strict=True).is_relative_to(snapshot.root.resolve())`. `resolve(strict=True)` raises on broken symlinks — handle that branch with a `try/except FileNotFoundError, OSError` → `probe.symlink.broken` event + skip. Don't conflate it with the escape branch.
- **Log payload sanitization is your responsibility** — `OutputSanitizer.scrub` is a two-pass chokepoint on `RepoContext` emission (ADR-0008), **NOT** a structlog processor. Anything you log via structlog goes through the structlog processor chain only. Emit only paths relative to `snapshot.root` in any event payload; never log resolved symlink targets.
- **`tier="base"` engages the coordinator prelude pass** (Gap 4). Do not set `requires=[<other-probe>]`; this probe is the prelude. `requires=[]` is required by the ABC (no default).
- **The `_ProbeOutputValidator` (ADR-0010)** enforces "no `bytes` / `Callable` / `Any`" in `schema_slice`. Your `schema_slice` is `dict[str, dict[str, dict[str, int] | str | None]]` — all JSON-representable. Don't smuggle a `Counter` (cast `dict(counter)` first) or a `Path` (convert to `str`).
- **The contract-conformance test (ADR-0007)** checks structural attributes only — it does **not** re-run the snapshot fingerprint test (`tests/unit/test_probe_contract.py` already does that). Don't duplicate it.
- **`version` is convention, not part of the ABC.** `cache/keys.py:_ProbeLike` Protocol bridges the convention to `--strict` typing. Keep `probe.version` in lockstep with the sub-schema `$id` minor version — the cache key tuple is `(probe.name, probe.version, per_probe_schema_version(probe), content_hash_of_inputs(...))`, so bumping one without the other creates a redundant cache-key signal.
- **Empty repo returns `primary=None`** (not `""`). The in-PR amended sub-schema declares `primary: {"type": ["string", "null"]}` to accept this. S4-04's existing tolerance `primary in (None, "")` is compatible.
- **The in-PR amendment to S2-05's sub-schema is part of this story's scope per CLAUDE.md Rule 7 (surface, don't average).** Localv2 §5.1 A1 + arch §Gap 4 (the design intent) win over the S2-05 schema file (the implementation artifact). The amendment fixes the artifact to match the design; do not file it as a follow-up.
