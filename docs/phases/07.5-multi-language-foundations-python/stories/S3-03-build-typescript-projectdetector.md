# Story S3-03 — Build the TypeScript `ProjectDetector`

**Step:** Step 3 — Retrofit TypeScript as `LanguagePack` #1 (by reference)
**Status:** Ready
**Effort:** S
**Depends on:** S1-04, S1-05
**ADRs honored:** ADR-0005, ADR-0006, ADR-0003

## Context
The TypeScript retrofit is "by reference" for *probes* (they self-registered in Phase 1), but the `project_detector` capability is a genuinely new object — Phase 1 had no `ProjectDetector`, detection was a probe. `TS_PACK` (S3-02) needs a real `ProjectDetector` implementation to fill its `project_detector` field, so this story builds one that reads `LANGUAGE_MARKERS[Language("typescript")]` from the shared marker catalog rather than duplicating marker knowledge.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component design — ProjectDetector + DetectionResult + the markers.py catalog` — the `Protocol`, the `Detected | NotDetected` sum type, monotone/additive detection.
- **Phase ADRs:** `../ADRs/0005-projectdetector-protocol-shared-marker-catalog.md` — ADR-0005 — `ProjectDetector` is a structural `Protocol`, returns the sum type, reads the shared `markers.py` catalog; never edits `LanguageDetectionProbe`.
- **Phase ADRs:** `../ADRs/0006-typescript-retrofit-by-reference-probes-self-registered.md` — ADR-0006 — the detector for `TS_PACK` is a *genuine new object*, not a reference.
- **Phase ADRs:** `../ADRs/0003-grammars-modeled-one-to-many-relation.md` — ADR-0003 — `Language("typescript")` is the ecosystem axis; grammar keys are an internal pack detail, not the detector's concern.
- **Existing code:** `src/codegenie/languages/markers.py` (S1-05) — `LANGUAGE_MARKERS` catalog the detector consults.
- **Existing code:** `src/codegenie/languages/__init__.py` / `pack.py` area (S1-03/S1-04) — `Detected`, `NotDetected`, `DetectionResult`, the `ProjectDetector` Protocol.
- **Existing code:** `src/codegenie/probes/base.py` — `RepoSnapshot` (the detector's input); `src/codegenie/probes/language_detection.py` — Phase 1 marker logic, kept untouched (ADR-0005).

## Goal
Add a concrete `TypeScriptProjectDetector` satisfying the `ProjectDetector` Protocol that returns `Detected`/`NotDetected` for a `RepoSnapshot` by matching `LANGUAGE_MARKERS[Language("typescript")]`.

## Acceptance criteria
- [ ] The TDD red test exists, is committed, and is green: `tests/unit/languages/test_typescript_detector.py` asserts `Detected(confidence="high")` on a `package.json`/`tsconfig.json` fixture and `NotDetected` on a no-marker fixture.
- [ ] `TypeScriptProjectDetector` structurally satisfies the `ProjectDetector` Protocol (`mypy --strict` accepts it where a `ProjectDetector` is expected — no inheritance).
- [ ] The detector reads `LANGUAGE_MARKERS[Language("typescript")]` — no marker tuple is hard-coded in the detector module (grep-asserted or AST-asserted in the test; ADR-0005 anti-duplication).
- [ ] Detection never raises — a snapshot with no markers returns `NotDetected`; `Detected.marker_files` lists the actual matched paths.
- [ ] `LanguageDetectionProbe` is **not edited** by this story (ADR-0005 — no silent edit to shipped code); `git diff` touches no Phase 1 probe file.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/`, and `pytest` pass on touched files.
- [ ] Status set to `Done` on completion.

## Implementation outline
1. Add `src/codegenie/languages/typescript_detector.py` (or the module path the `languages` package convention dictates) with a `TypeScriptProjectDetector` class exposing `detect(self, repo: RepoSnapshot) -> DetectionResult`.
2. `detect` globs the `RepoSnapshot` path index against `LANGUAGE_MARKERS[Language("typescript")]`; on ≥ 1 match return `Detected(confidence="high", marker_files=tuple(matched_paths))`; on no match return `NotDetected()`.
3. Keep `detect` a pure function over the snapshot — no I/O, no parsing (functional core / imperative shell).
4. Decide confidence policy: TypeScript markers (`package.json`, `tsconfig.json`) are all real-manifest markers, so a match is `confidence="high"`. (Unlike Python, there is no bare-`*.ts`-tree low-confidence tier in scope here — note that decision in the module docstring.)
5. Run `mypy --strict src/`, `ruff`, `pytest`.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/languages/test_typescript_detector.py`.
Test name: `test_detects_typescript_repo_with_tsconfig` — a `RepoSnapshot` whose path index contains `package.json` + `tsconfig.json` yields `Detected(confidence="high")` with both files in `marker_files`.
```python
# arrange: build a RepoSnapshot (in-memory / tmp_path) with package.json + tsconfig.json
# act: result = TypeScriptProjectDetector().detect(snapshot)
# assert: isinstance(result, Detected) and result.confidence == "high"
#         and set of result.marker_files == {package.json path, tsconfig.json path}
#   intent: a real TS repo is detected high-confidence and reports its evidence
```
Add `test_returns_notdetected_on_no_markers` — a snapshot of plain `.txt` files yields `NotDetected`. Add `test_detector_reads_shared_catalog` — assert no literal `"package.json"` string in the detector module source (it must come from `LANGUAGE_MARKERS`). All fail before the module exists.

### Green — make it pass
Implement `TypeScriptProjectDetector.detect` looping `LANGUAGE_MARKERS[Language("typescript")]` against the snapshot's path index, returning the sum-type variants.

### Refactor — clean up
Extract a pure `_match_markers(repo, markers) -> tuple[Path, ...]` helper (reusable by the Python detector in S4-03 — but do not extract it to a shared module here; rule-of-three, leave the second use to S4-03 to decide). Add type hints, a docstring noting the no-low-confidence-tier decision and the ADR-0005 monotone-detection property. Confirm the Protocol is satisfied with a `mypy`-level `_: ProjectDetector = TypeScriptProjectDetector()` assignment in a test.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/languages/typescript_detector.py` | New `TypeScriptProjectDetector` reading the shared marker catalog. |
| `tests/unit/languages/test_typescript_detector.py` | Red tests: detect-high, not-detected, reads-shared-catalog. |
| `src/codegenie/languages/__init__.py` | Possibly export `TypeScriptProjectDetector` if the package convention requires (keep `__all__ ≤ 6` per Step 1). |

## Out of scope
- Constructing or registering `TS_PACK` — that is S3-02 (this story only supplies the detector object S3-02 puts in `project_detector`).
- The Python `ProjectDetector` — that is S4-03.
- Editing `LanguageDetectionProbe` to read the shared catalog — ADR-0005 forbids it; the conformance assertion (S7-02) is the agreed bridge.

## Notes for the implementer
- The detector must satisfy the Protocol *structurally* — do not subclass anything; `mypy --strict` is the conformance check (ADR-0005).
- Marker matching is glob-style (`requirements*.txt`-style entries exist for Python; TypeScript markers are exact filenames today — still use the catalog, do not special-case).
- Do not demote or look at other languages — detection is monotone/additive (ADR-0005); a TS detector answers only "is this a TS repo?".
- `confidence` is the `Confidence` `Literal["high","medium","low"]` reused from the codebase — do not mint a new enum.
- Keep `detect` pure — no `Path.exists()` / filesystem calls; operate over the `RepoSnapshot` path index the coordinator already built.
- `TS_PACK` (S3-02) instantiates this detector; ensure the constructor takes no required arguments so `TypeScriptProjectDetector()` is a valid field value.
