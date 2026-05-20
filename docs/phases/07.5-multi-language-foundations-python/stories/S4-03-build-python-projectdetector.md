# Story S4-03 — Build the Python `ProjectDetector`

**Step:** Step 4 — Build the Python Layer A/B probes and the `tree-sitter-python` grammar row
**Status:** Ready
**Effort:** S
**Depends on:** S1-04, S1-05
**ADRs honored:** ADR-0004, ADR-0005

## Context
Every `LanguagePack` carries a `project_detector` capability — a `ProjectDetector` object that answers "is this repo a $LANGUAGE project?" and returns a `DetectionResult` sum type. ADR-0005 makes it a `typing.Protocol` (structural, no inheritance) reading the shared `LANGUAGE_MARKERS` catalog; ADR-0004 fixes the confidence semantics — `Detected(confidence="high")` only on a real manifest, `Detected(confidence="low")` for a bare `*.py` tree, `NotDetected` otherwise. This story builds the concrete Python detector that `PYTHON_PACK` will reference in S7-01.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component design — ProjectDetector + DetectionResult + the markers.py catalog` — the `Protocol`, the sum type, the monotone/additive detection rule.
- **Architecture:** `../phase-arch-design.md §Edge cases` rows 2 and 3 — bare `*.py` tree → `Detected(confidence="low")`; planted `pyproject.toml` in a Node repo → `Detected(confidence="high")` (a real manifest is genuinely present).
- **Architecture:** `../phase-arch-design.md §Control flow` decision point 4 — real manifest → high; bare `*.py` → low; no marker → `NotDetected`.
- **Phase ADRs:** `../ADRs/0005-projectdetector-protocol-shared-marker-catalog.md` — ADR-0005 — `Protocol`, `Detected | NotDetected`, marker knowledge in `LANGUAGE_MARKERS`, never raises.
- **Phase ADRs:** `../ADRs/0004-python-detection-as-base-tier-probe-not-prepass.md` — ADR-0004 — `Detected(confidence="high")` only on a real Python manifest.
- **Source design:** `../final-design.md §Synthesis ledger CR-5` — `confidence="high"` only on a real manifest narrows the "force Python parsers on a Node repo" attack surface.
- **Existing code:** `src/codegenie/languages/markers.py` (lands S1-05) — `LANGUAGE_MARKERS[Language("python")]`, the marker source of truth.
- **Existing code:** `src/codegenie/languages/` `ProjectDetector` Protocol + `DetectionResult` (`Detected | NotDetected`) — landed by S1-03 / S1-04.
- **Existing code:** `src/codegenie/probes/base.py` — `RepoSnapshot` (the detector input).

## Goal
Land a concrete Python `ProjectDetector` returning `Detected(high)` on a real manifest, `Detected(low)` on a bare `*.py` tree, and `NotDetected` otherwise.

## Acceptance criteria
- [ ] A red test asserts the Python detector returns `Detected(confidence="high")` for a `pyproject.toml` fixture, `Detected(confidence="low")` for a manifest-free `*.py` tree, and `NotDetected` for a Node-only fixture; it fails before the detector exists.
- [ ] The detector structurally satisfies the `ProjectDetector` `Protocol` (verified by `mypy --strict` — assign an instance to a `ProjectDetector`-typed variable in the test).
- [ ] The detector reads marker knowledge **only** from `LANGUAGE_MARKERS[Language("python")]` — no marker tuple is duplicated in the detector module.
- [ ] The detector never raises — a no-marker repo returns `NotDetected`; detection is monotone (it inspects only Python markers and never demotes another language).
- [ ] `Detected.marker_files` carries the actual matched marker paths; the result is a frozen sum-type value.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/`, `pytest` pass on touched files; Status set to `Done`.

## Implementation outline
1. Create `src/codegenie/languages/detectors/__init__.py` (or the location S3-03's TypeScript detector establishes — match it) and `python.py`.
2. Implement a `PythonProjectDetector` class with `detect(self, repo: RepoSnapshot) -> DetectionResult`.
3. Glob the snapshot path index against `LANGUAGE_MARKERS[Language("python")]`; partition matches into "real manifest" markers (`pyproject.toml`/`setup.py`/`setup.cfg`/`requirements*.txt`/`Pipfile`) vs. the bare-`*.py` signal.
4. Real manifest present → `Detected(confidence="high", marker_files=...)`; only `*.py` files, no manifest → `Detected(confidence="low", marker_files=...)`; neither → `NotDetected()`.
5. Keep `detect` pure — a function over a `RepoSnapshot`, no I/O beyond the snapshot's already-materialized path index.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/languages/test_python_detector.py`.
Test name: `test_python_detector_confidence_by_manifest_presence`.
```python
def test_python_detector_confidence_by_manifest_presence() -> None:
    detector: ProjectDetector = PythonProjectDetector()  # mypy: structural conformance
    # arrange: three RepoSnapshots — (a) has pyproject.toml, (b) bare foo.py only, (c) Node-only.
    # act: detector.detect(repo) for each.
    # assert: (a) Detected, confidence == "high"; (b) Detected, confidence == "low";
    #         (c) isinstance(result, NotDetected).
```
Fails today: `PythonProjectDetector` does not exist.

### Green — make it pass
Smallest detector: a class with one `detect` method doing a marker glob and a two-branch confidence decision. No tree-sitter, no parsing — a marker-presence check only.

### Refactor — clean up
Add type hints, a docstring tracing to ADR-0004/ADR-0005, and confirm `match`-based handling of the `DetectionResult` at any call site stays exhaustive. Verify no marker tuple is inlined — the catalog is the single source.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/languages/detectors/python.py` | `PythonProjectDetector` implementation (path matches the S3-03 precedent). |
| `tests/unit/languages/test_python_detector.py` | The red test + the three confidence cases. |

## Out of scope
- The TypeScript detector — S3-03.
- `PythonProjectProbe` (the `tier="base"` probe) — S4-02. The detector and the probe are distinct objects per ADR-0004 / ADR-0005.
- Constructing `PYTHON_PACK` and wiring `project_detector=PythonProjectDetector()` — S7-01.
- The conformance assertion that `LanguageDetectionProbe` and the detectors agree — S7-02.

## Notes for the implementer
- The detector is a `typing.Protocol` implementer — do **not** subclass an ABC; `mypy --strict` proves structural conformance. Assign an instance to a `ProjectDetector`-typed variable in the test so the conformance is checked.
- `confidence="high"` requires a *real manifest* — a bare `*.py` tree is `confidence="low"`, never `"high"`. This is the security-relevant narrowing (CR-5): it limits an attacker forcing Python parsers onto a Node repo.
- A planted `pyproject.toml` in a Node repo is genuinely `Detected(confidence="high")` — the manifest is really there. Detection is monotone; it never demotes the Node verdict (edge case #3). The cheap-but-real over-detection is accepted as the lesser evil vs. a silent skip.
- Match the file/path layout S3-03 chose for the TypeScript detector — if S3-03 placed it under `languages/detectors/`, mirror it; surface a conflict rather than forking a second layout.
- The detector never raises — `NotDetected` is the no-marker answer, not an exception.
