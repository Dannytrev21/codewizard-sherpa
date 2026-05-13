# Story S1-01 — Typed errors module

**Step:** Step 1 — Establish contracts: package scaffold, wire models, registry, Protocol
**Status:** Ready
**Effort:** S
**Depends on:** —
**ADRs honored:** ADR-0001 (subprocess-isolation failure typing), ADR-0004 (failure-mode taxonomy), ADR-0010 (isolation-class), Phase 5 ADR-0016 (eval-harness-as-trust-evidence)

## Context

Every later module in `src/codegenie/eval/` raises one of nine typed exceptions. Loader-side failures (`BenchCaseLoadError`, `BenchCaseDigestMismatch`, `BenchCaseIDCollision`), registry-side (`TaskClassNotFound`, `TaskClassAlreadyRegistered`), audit-chain-side (`ChainTamperDetected`), and promotion-side (`IncompleteReportForPromotion`, `PromotionMustBeHumanAuthorized`, `TierConfigInvalid`) are the partitioned-exit-code surface the CLI maps to codes 1/2/3/4/5/6. Until this module exists, nothing in Step 1–4 can compile against the documented `fail loud` discipline.

This is the smallest contract that unblocks every other Step 1 story; it is intentionally behavior-free.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design → src/codegenie/eval/registry.py` — names `TaskClassAlreadyRegistered(name, existing_qualname, incoming_qualname)` and `TaskClassNotFound(name, available_names)`.
  - `../phase-arch-design.md §Component design → src/codegenie/eval/loader.py` — names `BenchCaseLoadError(case_dir, field, reason)` and `BenchCaseDigestMismatch(case_id, expected, computed)`.
  - `../phase-arch-design.md §Component design → src/codegenie/eval/audit.py` — names `ChainTamperDetected(file_path, expected_prev, computed_prev)`.
  - `../phase-arch-design.md §Component design → src/codegenie/eval/promotion.py` — names `PromotionMustBeHumanAuthorized`, `IncompleteReportForPromotion`, `TierConfigInvalid(unknown_tier)`.
  - `../phase-arch-design.md §Edge cases #7` — `BenchCaseIDCollision(case_id, paths)` is a new fence-CI surface (Gap #3).
  - `../phase-arch-design.md §Component design → src/codegenie/eval/cli.py` — exit-code table maps these errors to codes 1–6.
- **Phase ADRs:**
  - `../ADRs/0001-rubric-execution-isolation-via-subprocess.md` — rubric subprocess failures *become* typed `FailureMode`s (not exceptions); the runner does not re-raise. The errors here are for *startup-time* failures (load, digest, chain) and *promotion-time* failures only.
  - `../ADRs/0004-per-task-class-failure-modes-taxonomy.md` — per-case rubric failures are typed `FailureMode`, not exceptions; this module owns the orthogonal startup-/promotion-time error surface.
- **Source design:** `../High-level-impl.md §Step 1` — lists the nine error types verbatim.
- **Existing precedent:** `../../00-bullet-tracer-foundations/stories/S2-01-errors-logging.md` — Phase 0 used the same "behavior-free marker subclasses + `__all__` closure" pattern; mirror it.

## Goal

Land `src/codegenie/eval/errors.py` exporting `CodegenieEvalError` (root) plus the nine documented subclasses, each behavior-free, each carrying a docstring naming its raise site.

## Acceptance criteria

- [ ] `src/codegenie/eval/errors.py` exists and exports `CodegenieEvalError` as the root, plus exactly these nine subclasses: `TaskClassNotFound`, `TaskClassAlreadyRegistered`, `BenchCaseLoadError`, `BenchCaseDigestMismatch`, `BenchCaseIDCollision`, `ChainTamperDetected`, `IncompleteReportForPromotion`, `PromotionMustBeHumanAuthorized`, `TierConfigInvalid`.
- [ ] `__all__` lists exactly ten names (root + nine); the red test asserts both directions (no extras, no omissions).
- [ ] Every subclass is a direct subclass of `CodegenieEvalError`; `CodegenieEvalError` is a direct subclass of `Exception`.
- [ ] Every subclass has a one-line docstring naming the module that raises it (e.g., `"""Raised by loader.load_cases when two case directories share case_id."""`).
- [ ] The red test from §TDD plan exists, was committed at the red marker, and is now green.
- [ ] `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/unit/test_eval_errors.py` all pass on touched files.

## Implementation outline

1. Create `src/codegenie/eval/__init__.py` as a stub (`""""""`); the real export wiring is S1-05. This story does **not** re-export from the package — only `codegenie.eval.errors` is importable here.
2. Create `src/codegenie/eval/errors.py` with:
   - `class CodegenieEvalError(Exception):` root with a module-level docstring naming `../phase-arch-design.md §Component design` as the source-of-truth for what raises which subclass.
   - Nine subclass declarations, each `class X(CodegenieEvalError):` with a one-line docstring; no `__init__`, no `__str__`, no behavior.
   - `__all__ = ["CodegenieEvalError", "TaskClassNotFound", ...]` listing all ten names alphabetically after the root.
3. Write `tests/unit/test_eval_errors.py` first (TDD red) — see §TDD plan.
4. Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/eval/errors.py`, `pytest tests/unit/test_eval_errors.py`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/test_eval_errors.py`

```python
# tests/unit/test_eval_errors.py
import codegenie.eval.errors as e

EXPECTED_SUBCLASSES = frozenset({
    "TaskClassNotFound",
    "TaskClassAlreadyRegistered",
    "BenchCaseLoadError",
    "BenchCaseDigestMismatch",
    "BenchCaseIDCollision",
    "ChainTamperDetected",
    "IncompleteReportForPromotion",
    "PromotionMustBeHumanAuthorized",
    "TierConfigInvalid",
})


def test_root_error_subclasses_exception():
    # The root must inherit Exception (not BaseException; Phase 0 precedent).
    assert issubclass(e.CodegenieEvalError, Exception)


def test_exactly_nine_documented_subclasses_present_no_more_no_less():
    # Pinning the closure: adding/removing without an ADR rationale fails CI.
    public_names = {n for n in e.__all__ if n != "CodegenieEvalError"}
    assert public_names == EXPECTED_SUBCLASSES
    for name in EXPECTED_SUBCLASSES:
        cls = getattr(e, name)
        assert issubclass(cls, e.CodegenieEvalError)
        assert cls is not e.CodegenieEvalError  # direct subclass, not the root itself


def test_every_subclass_has_a_raise_site_docstring():
    # Behavior-free markers must still document who raises them.
    for name in EXPECTED_SUBCLASSES:
        cls = getattr(e, name)
        assert cls.__doc__ is not None and cls.__doc__.strip() != ""
```

Run it; confirm `ModuleNotFoundError: No module named 'codegenie.eval.errors'`. Commit as the red marker.

### Green — make it pass

Declare `CodegenieEvalError(Exception)` with a module docstring. Then nine `class X(CodegenieEvalError): """<raise-site>"""` declarations matching `EXPECTED_SUBCLASSES`. Set `__all__` listing all ten names. No `__init__`, no behavior.

### Refactor — clean up

- Confirm `mypy --strict src/codegenie/eval/errors.py` passes (zero annotations needed — the file has no callables).
- Confirm `ruff check` passes; `ruff format --check` produces no diff.
- Module docstring cites `../phase-arch-design.md §Component design` as the canonical map from error → raise site.
- Per `../../00-bullet-tracer-foundations/stories/S2-01-errors-logging.md` notes: do not add `__str__` overrides; constructors carry positional args by Python's default `Exception.__init__`, and consumers format messages at the call site. Removing behavior post-Phase-6.5 is expensive; adding it is cheap.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/__init__.py` | New file — stub package marker; real re-exports land in S1-05 |
| `src/codegenie/eval/errors.py` | New file — `CodegenieEvalError` root + nine documented subclasses |
| `tests/unit/test_eval_errors.py` | New file — pins subclass closure + docstring discipline |

## Out of scope

- **Re-exporting `CodegenieEvalError` from `codegenie.eval.__init__`** — handled by S1-05 (it wires the full ≤ 9 public-name surface, but `CodegenieEvalError` is internal; it is imported as `from codegenie.eval.errors import ...`).
- **Wiring CLI exit-code mapping** — handled by S4-01 (exit codes 1–6 for the six startup/runtime error categories).
- **`FailureMode` per-case error typing** — that is `models.py` (S1-02), not this module; per ADR-0004 the rubric subprocess failure surface is `FailureMode`, not `Exception`.
- **`BenchScoreInvalid` runtime wrapper** — runner-internal (S3-04); does not live in `errors.py`.

## Notes for the implementer

- Keep the file behavior-free. No `__init__(*args)`, no `__str__`, no custom message formatting. Phase 0 ADR-0008 / ADR-0012 precedent and the cited Phase 0 story (`S2-01-errors-logging.md` line 144) explicitly call this out: behavior-free markers are cheap to extend later; pre-emptive constructor signatures lock callers in and are expensive to change after Step 2 consumers exist.
- The error *names* are the contract — phase-arch-design and ADRs name `TaskClassAlreadyRegistered(name, existing_qualname, incoming_qualname)`. The argument *shape* is documented in the *raiser's* code (S1-03 will pass three positional args to `__init__`), not enforced here.
- `CodegenieEvalError` is intentionally namespaced (`*Eval*`) to avoid collision with any future top-level `CodegenieError` hierarchy in `src/codegenie/errors.py` (Phase 0). The two hierarchies are siblings, not parent/child — the eval package is self-contained per the import-linter contract that S1-05 will extend.
- Do not import this module from `codegenie.eval/__init__.py` at this step. S1-05 wires the public surface, and the test there pins exactly nine public names — the errors are *not* on that public-name list. Consumers do `from codegenie.eval.errors import X`.
- The `BenchCaseIDCollision` subclass closes Gap #3 from `phase-arch-design.md §Gap analysis`. It is one of the seven fence-CI assertions S7-01 will wire; this story makes the type available so S2-02 (loader) can raise it.
- mypy `--strict` does not require any annotations on these classes (no methods, no fields). If mypy complains about `__all__`, declare it as `__all__: list[str] = [...]`.
