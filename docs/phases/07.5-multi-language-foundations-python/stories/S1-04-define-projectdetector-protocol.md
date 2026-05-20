# Story S1-04 — Define the `ProjectDetector` Protocol

**Step:** Step 1 — Establish the `LanguagePack` contract, the `DetectionResult` sum type, and the `markers.py` catalog
**Status:** Ready
**Effort:** S
**Depends on:** S1-03
**ADRs honored:** ADR-0005

## Context
The `project_detector` capability of a `LanguagePack` needs a *type*. ADR-0005 settles it as a `typing.Protocol` — structural, no inheritance — so a new language implements detection with zero base-class ceremony, exactly the adapter idiom production ADR-0032 uses. This story defines the `ProjectDetector` Port; it is the contract `S1-02`'s `LanguagePack.project_detector` field is typed against and that `S3-03`/`S4-03` implement structurally. Foundational, downstream-blocking type work.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component design — ProjectDetector + DetectionResult + the markers.py catalog` — the `ProjectDetector(Protocol)` interface block with `detect(self, repo: RepoSnapshot) -> DetectionResult`.
- **Architecture:** `../phase-arch-design.md §Logical view` — the `classDiagram` shows `ProjectDetector <<Protocol>>` returning `DetectionResult`, consulting `MarkerCatalog`.
- **Phase ADRs (rules to honor):** `../ADRs/0005-projectdetector-protocol-shared-marker-catalog.md` — ADR-0005 — Option B: a `typing.Protocol`, not an ABC; structural typing, no inheritance coupling.
- **Production ADRs (if applicable):** `../../../production/adrs/0032-language-search-adapters.md` — the `Protocol` adapter idiom this mirrors.
- **Existing code:** `src/codegenie/probes/base.py` — `RepoSnapshot` is the dataclass `ProjectDetector.detect` takes (`root`, `git_commit`, `detected_languages`, `config`). Import it from there.
- **Existing code (same phase):** `src/codegenie/languages/pack.py` — `DetectionResult` (S1-03) lives here; `ProjectDetector` goes in the same module.

## Goal
Add a `ProjectDetector` `typing.Protocol` with a single `detect(self, repo: RepoSnapshot) -> DetectionResult` method, so any class with that method shape satisfies the language-pack detector capability structurally.

## Acceptance criteria
- [ ] `ProjectDetector` is a `typing.Protocol` (decorated `@runtime_checkable` only if a test or `validate_pack` needs `isinstance` — otherwise plain `Protocol`); its sole method is `detect(self, repo: RepoSnapshot) -> DetectionResult`.
- [ ] A structural-conformance test: a minimal stub class with a correctly-typed `detect` method is accepted where a `ProjectDetector` is expected (assignment type-checks under `mypy --strict`); a stub missing `detect` or with a wrong return type is rejected (negative `mypy` assertion or a documented intent test).
- [ ] The TDD red test exists, is committed, and is green.
- [ ] `ProjectDetector` is importable from `codegenie.languages.pack` (and re-exported from `codegenie.languages` only if needed — keep `__all__` ≤ 6).
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/`, `pytest` pass on the touched files.
- [ ] Story `**Status:**` set to `Done` on completion.

## Implementation outline
1. In `src/codegenie/languages/pack.py`, add `from typing import Protocol` and define `class ProjectDetector(Protocol)` with the `detect` method signature.
2. Import `RepoSnapshot` from `codegenie.probes.base`; `DetectionResult` is already in the same module (S1-03).
3. Write the structural-conformance test with a stub detector; run red, then green.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/languages/test_project_detector.py` (new).

```python
# test_structural_stub_satisfies_protocol
#   class _StubDetector:
#       def detect(self, repo: RepoSnapshot) -> DetectionResult:
#           return NotDetected()
#   def _accepts(d: ProjectDetector) -> None: ...
#   _accepts(_StubDetector())   # must type-check under mypy --strict (no inheritance)
#   -- assert at runtime: _StubDetector().detect(<snapshot>) returns a DetectionResult
#
# test_protocol_has_single_detect_method  (intent test, Rule 9)
#   -- inspect ProjectDetector.__protocol_attrs__ (or members) == {"detect"};
#      documents that the Port surface is exactly one method — a second method
#      added without an ADR amendment is caught here.
```
Before `ProjectDetector` exists, the import is an `ImportError`.

### Green — make it pass
A one-method `Protocol`. No implementation, no body — `detect` is `...`.

### Refactor — clean up
Docstring naming ADR-0005 (structural Port, no inheritance); confirm the import of `RepoSnapshot` does not form a cycle (`codegenie.probes.base` is leaf-ish — verify `mypy`/`import-linter` stay clean); decide `@runtime_checkable` deliberately — add it only if `validate_pack` or a conformance test will `isinstance`-check, otherwise omit (it costs nothing but is unused machinery).

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/languages/pack.py` | new/append — `ProjectDetector` Protocol next to `DetectionResult` |
| `tests/unit/languages/test_project_detector.py` | new — structural-conformance + single-method intent test |

## Out of scope
- Concrete `ProjectDetector` implementations — S3-03 (TypeScript), S4-03 (Python).
- The `markers.py` catalog detectors read — S1-05.
- The `LanguagePack.project_detector` field — S1-02.

## Notes for the implementer
- ADR-0005 chose `Protocol` over ABC deliberately — do **not** make `ProjectDetector` an `abc.ABC`. A new language's detector satisfies it by *shape*, not by `class PythonDetector(ProjectDetector)`.
- The `detect` parameter is `RepoSnapshot` (Phase 0/1 dataclass), not a raw `Path` — the detector reads the snapshot's path index, no I/O of its own.
- Keep `pack.py` cohesive: `Confidence`, `Detected`, `NotDetected`, `DetectionResult` (S1-03), `ProjectDetector` (this story), `LanguagePack` (S1-02) all live there. One module — do not scatter.
- If you add `@runtime_checkable`, note that it only checks method *presence*, not signature — the `mypy` assignment test is what verifies the signature shape.
