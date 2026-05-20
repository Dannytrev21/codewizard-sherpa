# Story S1-03 — Add the `DetectionResult` sum type

**Step:** Step 1 — Establish the `LanguagePack` contract, the `DetectionResult` sum type, and the `markers.py` catalog
**Status:** Ready
**Effort:** S
**Depends on:** —
**ADRs honored:** ADR-0005

## Context
Every `LanguagePack` must answer "is this repo a $LANGUAGE project?" The answer is a *state with per-variant fields*: `Detected` carries a confidence and the marker files that matched; `NotDetected` carries nothing. Modeling this as `Detected | NotDetected` — a closed tagged union — makes "detected with no markers" unrepresentable and turns a missing `match` case into an `assert_never`/`mypy` compile error. This is foundational: `S1-04`'s `ProjectDetector` Protocol returns this type, and `S3-03`/`S4-03`'s detector implementations produce it.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component design — ProjectDetector + DetectionResult + the markers.py catalog` — the `Detected`/`NotDetected`/`DetectionResult` public interface block.
- **Architecture:** `../phase-arch-design.md §Data model` — the `DetectionResult — contract (in-memory sum type)` code block: `Detected` has `confidence: Confidence` + `marker_files: tuple[Path, ...]`; `NotDetected` is "singleton-shaped, no fields".
- **Phase ADRs (rules to honor):** `../ADRs/0005-projectdetector-protocol-shared-marker-catalog.md` — ADR-0005 — Option D: a `Detected(confidence, marker_files) | NotDetected` sum type, *not* `detected: bool` + loose siblings; `match` + `assert_never` makes a missing case a compile error.
- **Production ADRs (if applicable):** `../../../production/adrs/0033-domain-modeling-discipline.md` — sum-type discipline; closed-set `Literal` for `Confidence`.
- **Existing code:** `src/codegenie/probes/layer_g/semgrep.py` line ~165 — `confidence: Literal["high", "medium", "low"]` is the de-facto `Confidence` shape; the codebase has no shared `Confidence` alias yet — this story defines one.
- **Existing code:** `src/codegenie/result.py` — the project's canonical `Result` sum type; mirror its frozen-dataclass + union-alias idiom (do **not** fork `Result`; `DetectionResult` is a distinct domain type).

## Goal
Define `Detected`, `NotDetected`, and the `DetectionResult = Detected | NotDetected` alias as a frozen-dataclass tagged union so a `match` with a missing case is a `mypy --strict` / `assert_never` error.

## Acceptance criteria
- [ ] `Detected` is a `@dataclass(frozen=True)` with `confidence: Confidence` and `marker_files: tuple[Path, ...]`; `NotDetected` is a `@dataclass(frozen=True)` with no fields.
- [ ] `Confidence` is defined (or imported if a canonical one exists) as `Literal["high", "medium", "low"]`; `DetectionResult: TypeAlias = Detected | NotDetected`.
- [ ] An exhaustiveness test: a `match` over a `DetectionResult` covering both variants type-checks; a planted `match` missing `NotDetected` is rejected — proven by an `assert_never` in the test's else branch (the red test exists and is committed).
- [ ] `Detected` and `NotDetected` are genuinely frozen — a mutation attempt raises `FrozenInstanceError`.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict src/`, `pytest` pass on the touched files.
- [ ] Story `**Status:**` set to `Done` on completion.

## Implementation outline
1. Create `src/codegenie/languages/` package (if not already created by a sibling) with `__init__.py`.
2. In `src/codegenie/languages/pack.py` (the module that will also hold `LanguagePack` from S1-02 and `ProjectDetector` from S1-04), define `Confidence`, `Detected`, `NotDetected`, `DetectionResult`.
3. Re-export `Detected`, `NotDetected`, `DetectionResult` from `languages/__init__.py` only if a downstream consumer needs them at the package surface — keep `__all__` ≤ 6 names (arch §Development view); `DetectionResult` types may stay module-level in `pack.py`.
4. Write the exhaustiveness + frozen tests; run red, then green.

## TDD plan — red / green / refactor
### Red — write the failing test first
Test file: `tests/unit/languages/test_detection_result.py` (new).

```python
# test_detected_carries_confidence_and_marker_files
#   d = Detected(confidence="high", marker_files=(Path("pyproject.toml"),))
#   assert d.confidence == "high" and d.marker_files == (Path("pyproject.toml"),)
#
# test_detection_result_is_frozen
#   with pytest.raises(FrozenInstanceError): d.confidence = "low"  # type: ignore[misc]
#
# test_match_over_detection_result_is_exhaustive
#   def describe(r: DetectionResult) -> str:
#       match r:
#           case Detected(): return "detected"
#           case NotDetected(): return "not detected"
#   -- both arms reachable; assert describe(Detected(...)) and describe(NotDetected())
#
# test_missing_case_is_assert_never  (intent test, Rule 9)
#   def classify(r: DetectionResult) -> str:
#       match r:
#           case Detected(): return "d"
#           case _ as other: assert_never(other)  # mypy: only NotDetected reaches here
#   -- comment: deleting the Detected arm makes mypy report a non-exhaustive match;
#      this test documents the exhaustiveness contract.
```
Before `pack.py` exists, every import is an `ImportError`.

### Green — make it pass
Two frozen dataclasses + a `Confidence` `Literal` + a `DetectionResult` `TypeAlias`. `NotDetected` has no fields. Nothing else.

### Refactor — clean up
Docstrings on `Detected`/`NotDetected` naming the ADR-0005 sum-type contract; confirm `marker_files` is `tuple` (not `list`) so the frozen value is genuinely immutable; confirm `Confidence` is reused consistently (do not redefine it in `LanguagePack` work).

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/languages/__init__.py` | new — net-new package skeleton (created here or by a sibling Step-1 story; coordinate) |
| `src/codegenie/languages/pack.py` | new — holds `Confidence`, `Detected`, `NotDetected`, `DetectionResult` |
| `tests/unit/languages/test_detection_result.py` | new — exhaustiveness + frozen tests |

## Out of scope
- The `ProjectDetector` Protocol that returns `DetectionResult` — S1-04.
- The `LanguagePack` value — S1-02.
- Any concrete detector implementation — S3-03 (TypeScript), S4-03 (Python).

## Notes for the implementer
- `NotDetected` is "singleton-shaped" per the arch data model — a fieldless frozen dataclass. Do **not** make it a sentinel `object()` or `None`; it must be a real type so `isinstance`/`match` and `assert_never` work.
- Do **not** use `detected: bool` + loose `markers` siblings — ADR-0005 explicitly rejects that as tag-and-dispatch-without-a-tagged-union; `detected=False` with populated markers would slip through.
- `pack.py` is shared with S1-02 (`LanguagePack`) and S1-04 (`ProjectDetector`) — if you create it first, leave it minimal; if a sibling created it, append. Coordinate on one `pack.py`, not three modules.
- The `assert_never` test is the intent test (Rule 9): a thin `match` test that only checks both arms return *something* would pass even against a `bool` — the `assert_never` branch is what proves exhaustiveness has teeth.
- `import codegenie.languages` must not pull in `tree_sitter_python` or any grammar wheel — `pack.py` holds only type definitions.
