# Story S1-01 — Typed errors module

**Step:** Step 1 — Establish contracts: package scaffold, wire models, registry, Protocol
**Status:** HARDENED
**Effort:** S
**Depends on:** —
**ADRs honored:** ADR-0001 (subprocess-isolation failure typing), ADR-0004 (failure-mode taxonomy), ADR-0010 (isolation-class), Phase 5 ADR-0016 (eval-harness-as-trust-evidence)

## Validation notes

Validated: 2026-05-25
Verdict: HARDENED
Findings addressed: 11 total — 3 blocks, 6 hardens, 2 nits

Changes applied:
- AC-4 (was AC-4 "docstring exists"): tightened so the docstring must name one of the four documented raise-site module slugs (`loader`, `registry`, `audit`, `promotion`) and have ≥ 10 chars (Test-Quality F-TQ-2, Coverage F-COV-1) — mirrors Phase 0 S2-01 AC-1 precedent. A `"""TODO"""` docstring now fails CI.
- AC-3 (direct subclass): tightened from `issubclass` to `cls.__mro__[1] is e.CodegenieEvalError`, plus `e.CodegenieEvalError.__mro__[1] is Exception` (Test-Quality F-TQ-5, Coverage F-COV-4). Guards an intermediate-class-insertion mutation.
- AC-2 (`__all__` closure): equality now includes the root (`set(e.__all__) == EXPECTED_SUBCLASSES | {"CodegenieEvalError"}`), so dropping the root from `__all__` fails CI (Test-Quality F-TQ-1).
- AC-7 (added): `CodegenieEvalError` is a **sibling** of `codegenie.errors.CodegenieError`, not a child — pinned by a test asserting neither is a subclass of the other and they are distinct classes (Consistency F-CON-2, Coverage F-COV-3, Test-Quality F-TQ-7). This is the load-bearing decision in the story's implementer notes; without an AC, a future "tidy-up" PR could rebase under `CodegenieError` and silently invalidate the import-linter contract S1-05 wires.
- AC-8 (added): markers-only invariant — every subclass inherits `__init__` from the root and `cls.__dict__` is constrained to `{"__module__", "__qualname__", "__doc__", "__firstlineno__", "__static_attributes__"}` (the last two are Python 3.13 compiler-injected per Phase 0 S2-01 `_lessons.md`). Guards a "smuggle a constructor signature" mutation (Test-Quality F-TQ-6, Coverage F-COV-2).
- AC-9 (added): the root `CodegenieEvalError` itself has a non-empty docstring (Test-Quality F-TQ-3) — the marker-discipline test excluded the root.
- TDD plan: red-phase test file rewritten end-to-end to encode every AC above; raise-site slug catalog promoted to a module-level `Final[frozenset[str]]` so adding a new error in a future story requires editing the catalog (extension-by-addition discipline; Design-Patterns F-DP-3).
- Out of scope: clarified that `src/codegenie/eval/__init__.py` MUST NOT re-export from `errors.py` (deferred to S1-05) — was prose only, now explicit (Coverage F-COV-5).
- Implementer notes: named the **bounded-context** discipline explicitly — the sibling hierarchy is the package boundary that lets `eval/` be a self-contained module with its own import-linter contract; this aligns with hexagonal / DIP (the `eval` package depends on nothing in `codegenie.errors`). Surfaced for the executor's design-pattern awareness (Design-Patterns F-DP-2).
- Surfaced inconsistency (no edit): `final-design.md` line 63 calls this an "EvalError hierarchy **under** `CodegenieError`," but `phase-arch-design.md` + this story + the executor target make it a **sibling** hierarchy. The story's reasoning is sound (preserves import-linter contract) and supersedes the brief final-design.md mention. Flagged for a doc-sweep PR; do not auto-fix here (Consistency F-CON-1).

Full audit log: `_validation/S1-01-typed-errors-module.md`

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

- [ ] AC-1: `src/codegenie/eval/errors.py` exists and exports `CodegenieEvalError` as the root, plus exactly these nine subclasses: `TaskClassNotFound`, `TaskClassAlreadyRegistered`, `BenchCaseLoadError`, `BenchCaseDigestMismatch`, `BenchCaseIDCollision`, `ChainTamperDetected`, `IncompleteReportForPromotion`, `PromotionMustBeHumanAuthorized`, `TierConfigInvalid`.
- [ ] AC-2: `__all__` is a `list[str]` and the public-name closure is exact: `set(e.__all__) == EXPECTED_SUBCLASSES | {"CodegenieEvalError"}`. A typo'd `TaskClassNotFoun` or a forgotten root-in-`__all__` entry fails CI in both directions. (validator: hardened — original AC excluded the root from the closure equality.)
- [ ] AC-3: Every subclass is a **direct** subclass of `CodegenieEvalError` (`cls.__mro__[1] is e.CodegenieEvalError`, not transitive `issubclass`), and `e.CodegenieEvalError.__mro__[1] is Exception` (also direct). Guards an "insert intermediate class" mutation that `issubclass` would silently pass. (validator: hardened.)
- [ ] AC-4: Every subclass has a non-empty docstring (≥ 10 characters after `.strip()`) whose lowercased text contains at least one of the documented raise-site module slugs: `loader`, `registry`, `audit`, `promotion`. (E.g., `"""Raised by loader.load_cases when two case directories share case_id."""`.) A `"""TODO"""` or `"""x"""` docstring must fail CI. (validator: hardened — original AC said "naming the module that raises it" with no enforceable scope; mirrors Phase 0 [S2-01 AC-1](../../00-bullet-tracer-foundations/stories/S2-01-errors-logging.md) precedent.)
- [ ] AC-5: The red tests from §TDD plan exist, were committed at the red marker, and are now green; the commit message names the red→green transition.
- [ ] AC-6: `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/eval/errors.py`, and `pytest tests/unit/test_eval_errors.py` all pass on touched files.
- [ ] AC-7: `CodegenieEvalError` is a **sibling** of `codegenie.errors.CodegenieError` (Phase 0), **not** a subclass. Pinned by: `e.CodegenieEvalError is not codegenie.errors.CodegenieError`, `not issubclass(e.CodegenieEvalError, codegenie.errors.CodegenieError)`, and `not issubclass(codegenie.errors.CodegenieError, e.CodegenieEvalError)`. This load-bearing decision (see Notes for implementer + Validation notes) preserves the import-linter contract S1-05 will extend; a future "tidy-up" rebase under `CodegenieError` must fail CI here, not slip silently. (validator: added.)
- [ ] AC-8: Every subclass is a marker only. For each subclass `cls`: `cls.__init__ is e.CodegenieEvalError.__init__` (no custom constructor) AND `set(cls.__dict__.keys()) <= {"__module__", "__qualname__", "__doc__", "__firstlineno__", "__static_attributes__"}` (the last two are Python 3.13 compiler-injected per Phase 0 S2-01 `_lessons.md` — widened to match). Guards a "smuggle a constructor signature or class attribute" mutation; behavior-free discipline is enforced, not merely advised. (validator: added.)
- [ ] AC-9: `CodegenieEvalError` itself has a non-empty docstring (≥ 10 characters); the AC-4 loop intentionally excludes the root, so this AC closes the gap. (validator: added.)

## Implementation outline

1. Create `src/codegenie/eval/__init__.py` as a stub (`""""""`); the real export wiring is S1-05. This story does **not** re-export from the package — only `codegenie.eval.errors` is importable here. The stub must not `from .errors import *` or any equivalent (per AC-7 boundary discipline; S1-05 will not re-export `CodegenieEvalError` either — consumers import as `from codegenie.eval.errors import ...`).
2. Create `src/codegenie/eval/errors.py` with:
   - A module docstring naming `../phase-arch-design.md §Component design` as the source-of-truth for what raises which subclass, and explicitly documenting the **sibling** (not child) relationship with `codegenie.errors.CodegenieError` (Phase 0) and the rationale (package boundary / bounded context — see Notes for implementer).
   - `class CodegenieEvalError(Exception):` root with a non-empty docstring (AC-9).
   - Nine subclass declarations, each `class X(CodegenieEvalError):` with a one-line docstring that names one of `loader` / `registry` / `audit` / `promotion`; no `__init__`, no `__str__`, no behavior, no class attributes (AC-8).
   - `__all__: list[str] = ["CodegenieEvalError", "TaskClassNotFound", ...]` listing all ten names. (Annotation aids mypy `--strict`; sort is by raise-site module then alphabetical so a future reader sees the structure.)
3. Write `tests/unit/test_eval_errors.py` first (TDD red) — see §TDD plan. The catalog of raise-site slugs lives at module scope in the test file as `RAISE_SITE_SLUGS: Final[frozenset[str]] = frozenset({"loader", "registry", "audit", "promotion"})` so adding a new error in a future story (e.g., `cache.*`) is one edit to the catalog + one new docstring — extension by addition, not editing the test body.
4. Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/eval/errors.py`, `pytest tests/unit/test_eval_errors.py`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/test_eval_errors.py`

The red tests pin **both directions** of every contract: closure (no extras, no omissions), direct inheritance (no transitive smuggling), sibling-not-child (the load-bearing decision in Notes for implementer), and marker-only discipline (no smuggled constructors or class attributes). Three concrete mutations are guarded explicitly: (a) rebasing under `codegenie.errors.CodegenieError`, (b) inserting an intermediate class between a subclass and the root, (c) adding a `__init__(self, *args)` to one of the subclasses.

```python
# tests/unit/test_eval_errors.py
from typing import Final

import codegenie.errors as phase0_errors
import codegenie.eval.errors as e

EXPECTED_SUBCLASSES: Final[frozenset[str]] = frozenset({
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

# Documented raise-site module slugs (../phase-arch-design.md §Component design).
# Adding a new error in a future story = one entry here + one matching docstring.
# Catalog-driven so new errors are extension-by-addition, not test-body edits.
RAISE_SITE_SLUGS: Final[frozenset[str]] = frozenset({
    "loader",
    "registry",
    "audit",
    "promotion",
})

# Python 3.13 auto-injects __firstlineno__ and __static_attributes__ into every
# class __dict__ (see Phase 0 S2-01 _lessons.md). Widen the allowed set to
# include them; the load-bearing intent ("subclasses are markers only") is
# preserved.
MARKER_ALLOWED_DICT_KEYS: Final[frozenset[str]] = frozenset({
    "__module__",
    "__qualname__",
    "__doc__",
    "__firstlineno__",
    "__static_attributes__",
})


def test_all_closure_is_exact_in_both_directions():
    # AC-2: dropping the root from __all__, adding an undocumented subclass,
    # or typo'ing a name (TaskClassNotFoun) must fail. Equality, not subset.
    assert set(e.__all__) == EXPECTED_SUBCLASSES | {"CodegenieEvalError"}


def test_codegenie_eval_error_root_is_direct_subclass_of_exception():
    # AC-3 (root half): __mro__[1] is Exception — direct, not transitive.
    # Guards both `class CodegenieEvalError: pass` (no Exception base) and
    # an intermediate-class insertion above the root.
    assert e.CodegenieEvalError.__mro__[1] is Exception
    assert issubclass(e.CodegenieEvalError, Exception)
    assert e.CodegenieEvalError is not Exception  # aliasing-collapse guard


def test_every_subclass_inherits_directly_from_codegenie_eval_error():
    # AC-3 (subclass half): __mro__[1] is the root — direct, not transitive.
    # `issubclass` alone would silently pass an inserted intermediate.
    for name in EXPECTED_SUBCLASSES:
        cls = getattr(e, name)
        assert cls.__mro__[1] is e.CodegenieEvalError, (
            f"{name} must inherit directly from CodegenieEvalError, "
            f"not via an intermediate class (got __mro__={cls.__mro__})"
        )
        assert cls is not e.CodegenieEvalError  # the root is not itself an entry


def test_codegenie_eval_error_is_sibling_of_codegenie_error_not_child():
    # AC-7: load-bearing decision — the eval package is bounded-context;
    # CodegenieEvalError must NOT be a subclass of the Phase 0 root.
    # A future tidy-up rebase under CodegenieError would silently invalidate
    # the import-linter contract S1-05 will extend. Fail loud here instead.
    assert e.CodegenieEvalError is not phase0_errors.CodegenieError
    assert not issubclass(e.CodegenieEvalError, phase0_errors.CodegenieError), (
        "CodegenieEvalError must be a SIBLING of CodegenieError, not a child; "
        "see Notes for implementer + Validation notes"
    )
    assert not issubclass(phase0_errors.CodegenieError, e.CodegenieEvalError), (
        "Inverse must also hold — neither root is a parent of the other"
    )


def test_root_has_non_empty_docstring():
    # AC-9: the per-subclass loop excludes the root; close the gap here.
    doc = e.CodegenieEvalError.__doc__
    assert doc is not None and len(doc.strip()) >= 10, (
        "CodegenieEvalError must declare a >=10-char root docstring"
    )


def test_every_subclass_docstring_names_a_documented_raise_site():
    # AC-4: docstring must (a) exist, (b) be >=10 chars, (c) name one of
    # the four documented raise-site slugs (loader/registry/audit/promotion).
    # A `"""TODO"""` or `"""x"""` docstring fails CI.
    for name in EXPECTED_SUBCLASSES:
        cls = getattr(e, name)
        doc = cls.__doc__
        assert doc is not None and len(doc.strip()) >= 10, (
            f"{name} must declare a >=10-char raise-site docstring"
        )
        lowered = doc.lower()
        assert any(slug in lowered for slug in RAISE_SITE_SLUGS), (
            f"{name} docstring must name one of the documented raise-site "
            f"slugs {sorted(RAISE_SITE_SLUGS)}; got {doc!r}"
        )


def test_every_subclass_is_marker_only():
    # AC-8: no custom __init__, no class attributes. Guards a "smuggle a
    # constructor signature" mutation. Adding behavior is a separate decision
    # and must not slip into the marker hierarchy under the cover of S1-01.
    for name in EXPECTED_SUBCLASSES:
        cls = getattr(e, name)
        assert cls.__init__ is e.CodegenieEvalError.__init__, (
            f"{name} must inherit __init__ from CodegenieEvalError "
            f"(no custom constructor)"
        )
        extra = set(cls.__dict__.keys()) - MARKER_ALLOWED_DICT_KEYS
        assert not extra, (
            f"{name} declares extra class attributes {extra}; "
            f"subclasses must remain markers (allowed: {sorted(MARKER_ALLOWED_DICT_KEYS)})"
        )
```

Run it; confirm every test fails with `ModuleNotFoundError: No module named 'codegenie.eval.errors'` (or `AttributeError` if the stub already exists). Commit as the red marker.

### Green — make it pass

Declare `CodegenieEvalError(Exception)` with a non-empty (≥ 10 chars) root docstring. Then nine `class X(CodegenieEvalError): """<raise-site docstring naming loader|registry|audit|promotion>"""` declarations matching `EXPECTED_SUBCLASSES`. Set `__all__: list[str]` listing all ten names. No `__init__`, no `__str__`, no class attributes — markers only. Do **not** add `from codegenie.errors import CodegenieError`; the sibling decision (AC-7) forbids any inheritance edge.

### Refactor — clean up

- Confirm `mypy --strict src/codegenie/eval/errors.py` passes. The only annotation needed is `__all__: list[str] = [...]`; the classes themselves carry no callables.
- Confirm `ruff check` passes; `ruff format --check` produces no diff.
- Module docstring (a) cites `../phase-arch-design.md §Component design` as the canonical map from error → raise site, (b) documents the **sibling** relationship with `codegenie.errors.CodegenieError` and the rationale (bounded-context / package boundary; see Notes for implementer), (c) lists the four raise-site slugs (`loader`, `registry`, `audit`, `promotion`) so a future reader can extend by addition without spelunking the tests.
- Per `../../00-bullet-tracer-foundations/stories/S2-01-errors-logging.md` notes: do not add `__str__` overrides; constructors carry positional args by Python's default `Exception.__init__`, and consumers format messages at the call site. Removing behavior post-Phase-6.5 is expensive; adding it is cheap.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/eval/__init__.py` | New file — stub package marker; real re-exports land in S1-05 |
| `src/codegenie/eval/errors.py` | New file — `CodegenieEvalError` root + nine documented subclasses |
| `tests/unit/test_eval_errors.py` | New file — pins subclass closure + docstring discipline |

## Out of scope

- **Re-exporting `CodegenieEvalError` from `codegenie.eval.__init__`** — handled by S1-05 (it wires the full ≤ 9 public-name surface, but `CodegenieEvalError` is internal; it is imported as `from codegenie.eval.errors import ...`). This story's `__init__.py` MUST NOT contain `from .errors import ...` or any equivalent — the public-name closure is S1-05's contract and this story must not preempt it.
- **Wiring CLI exit-code mapping** — handled by S4-01 (exit codes 1–6 for the six startup/runtime error categories). This story does not import `click`, `typer`, or any CLI dependency; the error → exit-code table lives in `cli.py`, not `errors.py`.
- **`FailureMode` per-case error typing** — that is `models.py` (S1-02), not this module; per ADR-0004 the rubric subprocess failure surface is `FailureMode`, not `Exception`. This story does not import `pydantic`.
- **`BenchScoreInvalid` runtime wrapper** — runner-internal (S3-04); does not live in `errors.py`.
- **Inheritance under `codegenie.errors.CodegenieError`** — per AC-7, the eval error hierarchy is a deliberate **sibling**, not a child. Surfaced because `final-design.md` line 63 ("EvalError hierarchy under CodegenieError") reads as if it were a child; the `phase-arch-design.md` + this story + the executor target win on more elaborated reasoning (import-linter contract preservation). Flagged for a doc-sweep PR; this story will not auto-fix `final-design.md`.

## Notes for the implementer

- Keep the file behavior-free. No `__init__(*args)`, no `__str__`, no custom message formatting. Phase 0 ADR-0008 / ADR-0012 precedent and the cited Phase 0 story (`S2-01-errors-logging.md` line 144) explicitly call this out: behavior-free markers are cheap to extend later; pre-emptive constructor signatures lock callers in and are expensive to change after Step 2 consumers exist. AC-8 makes this load-bearing, not advisory.
- The error *names* are the contract — phase-arch-design and ADRs name `TaskClassAlreadyRegistered(name, existing_qualname, incoming_qualname)`. The argument *shape* is documented in the *raiser's* code (S1-03 will pass three positional args to `__init__`), not enforced here.
- **Bounded-context discipline (the load-bearing design decision in this story):** `CodegenieEvalError` is a **sibling** of `codegenie.errors.CodegenieError`, not a child. This is not a naming convenience — it is a **package boundary** the import-linter contract in S1-05 will enforce, aligning with hexagonal / DIP: the `eval` package depends on **nothing** in the Phase 0 error hierarchy. A caller catching both must write `except (CodegenieError, CodegenieEvalError):` deliberately; a future "tidy-up" rebase under `CodegenieError` would silently collapse the boundary and let any Phase-0 `except CodegenieError:` swallow eval-harness errors it has no business catching. AC-7 pins this; the test names the mutation it guards against. The deeper architectural payoff is that `src/codegenie/eval/` can be lifted into its own distribution package later without rewiring callers — the sibling-not-child relationship makes that a mechanical move, not a hierarchy refactor.
- The story does **not** introduce an `ErrorRegistry`, exception factory, or marker-decorator. Rule of three is not met (one consumer family). If a third sibling error hierarchy appears in a later phase and the three duplicate the same closure-test boilerplate, that is the point at which an extraction kernel becomes warranted — not this story.
- The raise-site slug catalog (`RAISE_SITE_SLUGS`) in the test lives at module scope as a `Final[frozenset[str]]`. Adding a new error in a later story (e.g., `cache.*`) is one entry there + one matching docstring — extension by addition, not editing the test body. The catalog mirrors the data-driven-registry pattern used elsewhere in the codebase (e.g., `_GENERATOR_HEADER_MARKERS`, `_LOCKFILE_PRECEDENCE`).
- Do not import this module from `codegenie.eval/__init__.py` at this step. S1-05 wires the public surface, and the test there pins exactly nine public names — the errors are *not* on that public-name list. Consumers do `from codegenie.eval.errors import X`.
- The `BenchCaseIDCollision` subclass closes Gap #3 from `phase-arch-design.md §Gap analysis`. It is one of the seven fence-CI assertions S7-01 will wire; this story makes the type available so S2-02 (loader) can raise it.
- mypy `--strict` does not require any annotations on these classes (no methods, no fields). If mypy complains about `__all__`, declare it as `__all__: list[str] = [...]` (already in the green-phase guidance).
- `final-design.md` line 63 ("EvalError hierarchy under CodegenieError") **contradicts** AC-7. The story's reasoning wins (the import-linter contract preservation is concrete; the final-design line is a one-liner). Note this for a doc-sweep PR but do **not** edit `final-design.md` from this story.
