# Story S1-05 — Add the `markers.py` addition-only catalog

**Step:** Step 1 — Establish the `LanguagePack` contract, the `DetectionResult` sum type, and the `markers.py` catalog
**Status:** Ready
**Effort:** S
**Depends on:** S1-01
**ADRs honored:** ADR-0005

## Context
Every `ProjectDetector` answers "is this a $LANGUAGE repo?" by checking for marker files (`pyproject.toml`, `package.json`, …). ADR-0005 forbids duplicating those marker tuples into each detector — duplication-by-addition is the exact anti-pattern ADR-0043 names as a standing review criterion. This story lands `LANGUAGE_MARKERS`, a single addition-only `Final` catalog that every per-language detector consults. It is foundational data the `S3-03` (TypeScript) and `S4-03` (Python) detectors read.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component design — ProjectDetector + DetectionResult + the markers.py catalog` — the `markers.py` code block and "the addition-only Final catalog … both the per-language ProjectDetector and (read-only, by import) LanguageDetectionProbe-adjacent code can consult".
- **Architecture:** `../phase-arch-design.md §Data model` — the `LANGUAGE_MARKERS — contract (addition-only Final catalog)` block: Python markers (`pyproject.toml`, `setup.py`, `setup.cfg`, `requirements*.txt`, `Pipfile`, `Pipfile.lock`) and TypeScript markers (`package.json`, `tsconfig.json`).
- **Phase ADRs (rules to honor):** `../ADRs/0005-projectdetector-protocol-shared-marker-catalog.md` — ADR-0005 — Option F: a shared addition-only `Final` catalog (the `_MONOREPO_PRECEDENCE` idiom); the shipped `LanguageDetectionProbe` is **not** edited to read it.
- **Source design:** `../phase-arch-design.md §Tradeoffs` — "markers.py shared catalog; LanguageDetectionProbe not edited to read it" — the catalog is the source of truth for the *new* detectors only.
- **Existing code:** `src/codegenie/probes/layer_a/` — `LanguageDetectionProbe`'s own Phase-0/1 marker logic; look but do **not** edit (that would be a silent edit — ADR-0005).
- **Existing code:** grep `_MONOREPO_PRECEDENCE` / `_LOCKFILE_PRECEDENCE` in `src/codegenie/` — the `Final`-tuple data-driven catalog idiom to mirror (iterated data, never branched).
- **Existing code:** `src/codegenie/types/identifiers.py` — `Language` newtype, the catalog's key type.

## Goal
Land `LANGUAGE_MARKERS: Final[Mapping[Language, tuple[str, ...]]]` in `src/codegenie/languages/markers.py` as the single addition-only marker source of truth for Python and TypeScript.

## Acceptance criteria
- [ ] `src/codegenie/languages/markers.py` defines `LANGUAGE_MARKERS: Final[Mapping[Language, tuple[str, ...]]]` with a `Language("python")` row and a `Language("typescript")` row, each mapping to a non-empty `tuple[str, ...]` of marker filenames/globs.
- [ ] The Python row includes at least `pyproject.toml`, `setup.py`, `setup.cfg`, `requirements*.txt`, `Pipfile`; the TypeScript row includes at least `package.json`, `tsconfig.json` (matching arch §Data model).
- [ ] A test asserts `LANGUAGE_MARKERS` is the single marker source within `codegenie.languages` — no marker tuple is duplicated in `pack.py` or any other `codegenie.languages` module (a grep/AST check, or simply: detectors import from `markers.py`, asserted when S3-03/S4-03 land).
- [ ] The catalog is immutable at the value level — `tuple` values, `Mapping` (not `dict`) annotation, `Final`; a mutation attempt on a value tuple fails statically/at runtime.
- [ ] The TDD red test exists, is committed, and is green; `ruff check`, `ruff format --check`, `mypy --strict src/`, `pytest` pass on touched files.
- [ ] Story `**Status:**` set to `Done` on completion.

## Implementation outline
1. Create `src/codegenie/languages/markers.py` (the `codegenie.languages` package exists from S1-02/S1-03).
2. Define `LANGUAGE_MARKERS` as a module-level `Final[Mapping[Language, tuple[str, ...]]]` with the two language rows.
3. Decide whether `LANGUAGE_MARKERS` is re-exported from `codegenie.languages.__init__` — keep `__all__` ≤ 6; markers can stay imported directly from `markers.py` by detectors.
4. Write the catalog tests (presence, shape, immutability, single-source); run red, then green.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/languages/test_markers.py` (new).

```python
# test_language_markers_has_python_and_typescript_rows
#   assert Language("python") in LANGUAGE_MARKERS
#   assert Language("typescript") in LANGUAGE_MARKERS
#
# test_python_markers_cover_canonical_manifests
#   py = LANGUAGE_MARKERS[Language("python")]
#   for m in ("pyproject.toml", "setup.py", "setup.cfg", "Pipfile"):
#       assert m in py
#   assert any(m.startswith("requirements") for m in py)
#
# test_typescript_markers_cover_canonical_manifests
#   ts = LANGUAGE_MARKERS[Language("typescript")]
#   assert "package.json" in ts and "tsconfig.json" in ts
#
# test_marker_values_are_tuples  (immutability intent, Rule 9)
#   for markers in LANGUAGE_MARKERS.values():
#       assert isinstance(markers, tuple)   # not list — frozen catalog
```
Before `markers.py` exists, the import is an `ImportError`.

### Green — make it pass
A module-level `LANGUAGE_MARKERS` `Final` dict literal with the two rows. No functions, no logic — pure data.

### Refactor — clean up
Module docstring naming ADR-0005 (addition-only catalog, the `_MONOREPO_PRECEDENCE` idiom, why `LanguageDetectionProbe` is *not* edited); confirm `Final` + `Mapping` annotation; confirm marker tuples are deliberate and minimal — the detector's `confidence` split (real manifest → high, bare `*.py` → low, in S4-03) depends on these being *manifest* markers.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/languages/markers.py` | new — the `LANGUAGE_MARKERS` `Final` catalog |
| `tests/unit/languages/test_markers.py` | new — presence/shape/immutability tests |

## Out of scope
- Editing `LanguageDetectionProbe` to read the catalog — ADR-0005 forbids it (silent edit); the shipped probe keeps its own Phase-0/1 logic. A conformance assertion (S7-02/S7-04) proves probe and detectors agree.
- The `ProjectDetector` implementations that consume the catalog — S3-03 (TypeScript), S4-03 (Python).
- Adding a third language's markers — Phase 8+.

## Notes for the implementer
- This is an **addition-only** catalog — a new language is one new row, never an edit to an existing row or to a detector (ADR-0005). Build it that way: a flat `Final` dict, no per-language branching.
- Do **not** touch `LanguageDetectionProbe`. ADR-0005 is explicit: editing the shipped probe to read this catalog is a silent edit. The probe keeps its own markers; a conformance test bridges them. If you find yourself wanting to refactor the probe — stop, that is out of scope and ADR-forbidden.
- The Python markers must be the *manifest* markers (the files that signal `confidence="high"` in S4-03's detector). A bare `*.py` glob is **not** a marker here — the detector's low-confidence path handles "Python files but no manifest" separately.
- Mirror the `_MONOREPO_PRECEDENCE` / `_LOCKFILE_PRECEDENCE` `Final`-tuple idiom already in the codebase — iterated data, not branched code.
- Keep marker values as `tuple`, not `list` — the catalog is a frozen value; `Mapping` (not `dict`) in the annotation signals read-only intent.
