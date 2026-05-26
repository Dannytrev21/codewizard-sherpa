# Story S1-03 — Add the `DetectionResult` sum type

**Step:** Step 1 — Establish the `LanguagePack` contract, the `DetectionResult` sum type, and the `markers.py` catalog
**Status:** HARDENED
**Effort:** S
**Depends on:** —
**ADRs honored:** ADR-0005

## Validation notes (phase-story-validator v1 · 2026-05-26)

- Story is **structurally sound** — Goal, ADR-0005 honor, scope, and reference to arch §Data model all hold up. No `RESCUE`-level findings; verdict: **HARDENED**.
- **Coverage hardened (6)**: split the original conflated AC-1 (both variants in one criterion) into per-variant ACs; pinned `Confidence`'s syntactic form (`: TypeAlias = Literal[...]`), definition site (`pack.py`), and `Literal` argument order (`"high", "medium", "low"`) — order is contract per ADR-0005 ("`confidence="high"` only on a real manifest"); split the frozen test into three field categories (scalar, tuple, no-field-attribute-creation) so a partial-freeze regression cannot pass; added an AC for sum-type structural integrity (`isinstance` discrimination + `get_args(DetectionResult)`); added an AC honoring S1-02's six-name `__all__` reservation (`Detected` / `NotDetected` / `DetectionResult` / `Confidence` are **module-level only** in `pack.py`, NOT re-exported from `codegenie.languages`); added an AC pinning module-level stdlib-only purity for this story's contribution.
- **Test-quality hardened (5)**: TDD snippets were pseudocode `#` comments — rewritten as near-executable test functions; the original frozen test exercised one field category — widened to three; the original "match covering both variants" test was tautological — pinned `typing.assert_never` in the `case _:` arm as the load-bearing runtime exhaustiveness witness (the static-time fence is **deferred to S1-06**'s mypy-must-fail harness); added equality + hash semantics ACs (`match` dispatch relies on dataclass-generated `__eq__`); added a hypothesis property test (`tests/property/test_detection_result.py`) drawing over `confidence` and `marker_files`' full input spaces, killing "frozen at construction only" mutations.
- **Consistency clarified (2)**: References block pointed to `src/codegenie/result.py` as the "frozen-dataclass + union-alias idiom" precedent — but `result.py` is Pydantic `BaseModel`, **not** `@dataclass`. The arch §Data model code block is the **technology precedent** (`@dataclass(frozen=True)`); `result.py` is reframed in Notes as the *naming / co-location* precedent only. Clarified S1-03 is the **creator** of `__init__.py` and `pack.py` (S1-02 hardening confirmed S1-02 / S1-04 append to existing files).
- **Design-patterns surfaced (4)**: `Confidence` defined here does **NOT** replace inline `Literal["high","medium","low"]` usages in `semgrep.py` / `ripgrep_curated.py` / `test_coverage_mapping.py` (ADR-0043 — extension by addition; silent edits forbidden); explicit prohibition on a `_NOTDETECTED_INSTANCE` singleton sentinel (anti-pattern — `match case NotDetected():` works on type, not identity; the arch's "singleton-shaped" language is descriptive, not prescriptive); explicit prohibition on abstract base classes / `Variant` enums / `ResultBuilder` helpers (Rule 2 — the sum type IS the abstraction; Open/Closed seams live at the registry level); pinned module-level-only placement (the four S1-03 symbols are NOT in `codegenie.languages.__all__`).
- Full audit log: [`_validation/S1-03-add-detectionresult-sum-type.md`](_validation/S1-03-add-detectionresult-sum-type.md).

## Context
Every `LanguagePack` must answer "is this repo a $LANGUAGE project?" The answer is a *state with per-variant fields*: `Detected` carries a confidence and the marker files that matched; `NotDetected` carries nothing. Modeling this as `Detected | NotDetected` — a closed tagged union — makes "detected with no markers" unrepresentable and turns a missing `match` case into an `assert_never`/`mypy` compile error. This is foundational: `S1-04`'s `ProjectDetector` Protocol returns this type, and `S3-03`/`S4-03`'s detector implementations produce it.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component design — ProjectDetector + DetectionResult + the markers.py catalog` — the `Detected`/`NotDetected`/`DetectionResult` public interface block.
- **Architecture:** `../phase-arch-design.md §Data model` — the `DetectionResult — contract (in-memory sum type)` code block: explicitly `@dataclass(frozen=True)` for both variants. `Detected` has `confidence: Confidence` + `marker_files: tuple[Path, ...]`; `NotDetected` is "singleton-shaped, no fields". **This is the technology precedent — `@dataclass`, NOT Pydantic.**
- **Phase ADRs (rules to honor):** `../ADRs/0005-projectdetector-protocol-shared-marker-catalog.md` — ADR-0005 — Option D: a `Detected(confidence, marker_files) | NotDetected` sum type, *not* `detected: bool` + loose siblings; `match` + `assert_never` makes a missing case a compile error. Note: `confidence="high"` is reserved for a real manifest; `confidence="low"` for a bare `*.py` tree — `Literal` argument order is contract.
- **Production ADRs (if applicable):** `../../../production/adrs/0033-domain-modeling-discipline.md` — sum-type discipline; closed-set `Literal` for `Confidence`.
- **Sibling validation (rules to honor):** [`_validation/S1-02-add-languagepack-frozen-value.md`](_validation/S1-02-add-languagepack-frozen-value.md) — S1-02's hardening reserved `codegenie.languages.__all__` to **exactly six names**: `LanguagePack`, `LanguageRegistry`, `register_language`, `default_language_registry`, `LanguageRegistryError`, `language_packs`. S1-03's symbols (`Detected`/`NotDetected`/`DetectionResult`/`Confidence`) are **NOT** in this set and **MUST NOT** be added — consumers import via `from codegenie.languages.pack import ...`.
- **Sibling story (deferred fence):** `./S1-06-build-mypy-must-fail-harness.md` — the mypy-must-fail harness owns the **static-time** non-exhaustiveness proof (a planted `match` missing `NotDetected` is a mypy error). This story commits the **runtime** witness (`assert_never` in `case _:`).
- **Existing code (style precedent — naming/co-location only, NOT technology):** `src/codegenie/result.py` — `Ok` / `Err` / `Result` sum-type co-location and `TypeAlias` form precedent. **Caution:** `result.py` uses Pydantic `BaseModel`, NOT `@dataclass` — the arch §Data model block is the source-of-truth on technology choice for `DetectionResult`. Do **not** copy `result.py`'s `BaseModel` declaration.
- **Existing code (canonical `TypeAlias` style):** `src/codegenie/types/identifiers.py:29` — `from typing import ... TypeAlias` + `Foo: TypeAlias = ...` form. Mirror this for `Confidence` and `DetectionResult`.
- **Existing code (do NOT edit):** `src/codegenie/probes/layer_g/semgrep.py:190`, `ripgrep_curated.py:172`, `test_coverage_mapping.py:140` — three inline `Literal["high", "medium", "low"]` usages pre-dating this canonical alias. Per production ADR-0043 (extension by addition; silent edits forbidden), this story does **not** touch them; migration is a separate sanctioned sweep.

## Goal
Define `Confidence`, `Detected`, `NotDetected`, and `DetectionResult = Detected | NotDetected` as a frozen-dataclass tagged union in `src/codegenie/languages/pack.py` such that (a) "detected with no markers" is unrepresentable, (b) a runtime `match` with a missing case raises via `assert_never`, and (c) the four symbols stay module-level (NOT in `codegenie.languages.__all__`, per S1-02's six-name reservation).

## Acceptance criteria

- [ ] **AC-1 — `Confidence` alias definition site, form, and `Literal` argument order pinned.** `Confidence: TypeAlias = Literal["high", "medium", "low"]` is defined in `src/codegenie/languages/pack.py` (NOT `types/identifiers.py`; NOT `result.py`). The `TypeAlias` syntactic form is mandatory (mirrors `src/codegenie/types/identifiers.py:29` style). Test asserts:
  ```python
  from typing import get_args
  from codegenie.languages.pack import Confidence
  assert get_args(Confidence) == ("high", "medium", "low")
  ```
  Argument order is **contract**, not aesthetic — ADR-0005 §Decision uses `confidence="high"` (real manifest) and `confidence="low"` (bare `*.py`) as semantic markers; reordering breaks downstream conformance pins.

- [ ] **AC-2 — `Detected` shape pinned.** `Detected` is `@dataclass(frozen=True)` with exactly two fields in this canonical order: `confidence: Confidence`, `marker_files: tuple[Path, ...]` (where `Path = pathlib.Path`). Test asserts:
  ```python
  import dataclasses
  fields = dataclasses.fields(Detected)
  assert tuple(f.name for f in fields) == ("confidence", "marker_files")
  assert dataclasses.is_dataclass(Detected) and Detected.__dataclass_params__.frozen is True
  ```

- [ ] **AC-3 — `NotDetected` shape pinned independently.** `NotDetected` is `@dataclass(frozen=True)` with **zero** fields. Test asserts:
  ```python
  import dataclasses
  assert dataclasses.fields(NotDetected) == ()
  assert dataclasses.is_dataclass(NotDetected) and NotDetected.__dataclass_params__.frozen is True
  assert NotDetected() == NotDetected()                  # interchangeable, dataclass-generated __eq__
  ```

- [ ] **AC-4 — `DetectionResult` alias pinned via `get_args`.** `DetectionResult: TypeAlias = Detected | NotDetected`. Test asserts:
  ```python
  from typing import get_args
  from codegenie.languages.pack import Detected, NotDetected, DetectionResult
  assert get_args(DetectionResult) == (Detected, NotDetected)   # order matters for snapshot/conformance pins
  ```

- [ ] **AC-5 — Frozen across all three field categories.** Three separate `pytest.raises(dataclasses.FrozenInstanceError)` cases:
  ```python
  d = Detected(confidence="high", marker_files=(Path("pyproject.toml"),))
  with pytest.raises(dataclasses.FrozenInstanceError): d.confidence = "low"        # scalar Literal
  with pytest.raises(dataclasses.FrozenInstanceError): d.marker_files = ()         # tuple field
  with pytest.raises(dataclasses.FrozenInstanceError): NotDetected().foo = 1       # attribute creation on zero-field variant
  ```
  Without three cases, a partial-freeze regression (`@dataclass(frozen=True, eq=False)`, or only-scalar protection) passes the original single-case test.

- [ ] **AC-6 — Equality + hash semantics pinned.** `match` dispatch and downstream set/dict use rely on the dataclass-generated `__eq__` / `__hash__`:
  ```python
  d1 = Detected(confidence="high", marker_files=(Path("p"),))
  d2 = Detected(confidence="high", marker_files=(Path("p"),))
  assert d1 == d2 and hash(d1) == hash(d2)              # value-equal, hash-stable
  assert NotDetected() == NotDetected() and hash(NotDetected()) == hash(NotDetected())
  assert d1 != NotDetected()                            # variant inequality
  ```
  An executor doing `@dataclass(frozen=True, eq=False)` passes the original AC-1 but breaks `match` semantics; this AC catches it.

- [ ] **AC-7 — `marker_files` is structurally a `tuple` at runtime.** `isinstance(Detected(...).marker_files, tuple)` is `True`; `Detected(...).marker_files.append(Path("x"))` raises `AttributeError` (tuples have no `.append`). Note: dataclasses do NOT validate field *types* at runtime — passing a `list` to `marker_files` does not raise at construction; that's a `mypy --strict` error and is **deferred to S1-06**'s mypy-must-fail harness. This AC pins the **runtime-observable** invariant only.

- [ ] **AC-8 — Match exhaustiveness with `assert_never` runtime witness.** The TDD plan ships a `classify(r: DetectionResult) -> str` function that uses `typing.assert_never` in the `case _:` catch-all arm; the test invokes it on both variants and asserts the variant-specific return value:
  ```python
  from typing import assert_never
  def classify(r: DetectionResult) -> str:
      match r:
          case Detected():     return "detected"
          case NotDetected():  return "not_detected"
          case _:              assert_never(r)         # runtime witness; mypy --strict also enforces statically
  assert classify(Detected(confidence="high", marker_files=())) == "detected"
  assert classify(NotDetected()) == "not_detected"
  ```
  The `assert_never` line is the load-bearing exhaustiveness signal — a tautological "match returns something" test would pass even against a stub. The **static-time** non-exhaustiveness proof (planted `match` missing `NotDetected` is mypy-rejected) is **deferred to S1-06**'s mypy-must-fail harness; this story commits the **runtime** witness.

- [ ] **AC-9 — Module purity: `pack.py` is stdlib-only for this story's contribution.** An AST-scan (or text-scan) test asserts that `src/codegenie/languages/pack.py`'s S1-03-introduced symbols (`Confidence`, `Detected`, `NotDetected`, `DetectionResult`) are supported by **stdlib imports only** — `dataclasses`, `pathlib`, `typing` (or `collections.abc` if `Mapping` is co-located). No `codegenie.*` sibling imports, no `tree_sitter*`, no `logging`, no I/O. S1-02 / S1-04 add codegenie sibling imports later — out of scope here. Test:
  ```python
  import ast, pathlib
  src = pathlib.Path("src/codegenie/languages/pack.py").read_text(encoding="utf-8")
  tree = ast.parse(src)
  ALLOWED = {"dataclasses", "pathlib", "typing", "collections.abc", "__future__"}
  for node in ast.walk(tree):
      if isinstance(node, (ast.Import, ast.ImportFrom)):
          # S1-03's contribution must only pull from the allowed stdlib set.
          # (After S1-02 / S1-04 land, additional codegenie sibling imports appear — adjust ALLOWED then.)
          ...
  ```
  Note: as S1-02 and S1-04 land, this allowlist widens — this AC is **scoped to S1-03's contribution at the time it lands**, not a permanent invariant. (S1-02's AC-10 — `import codegenie.languages` is grammar-wheel-free — is the permanent package-level guarantee.)

- [ ] **AC-10 — `codegenie.languages.__all__` non-inclusion; consumer import path pinned.** Per S1-02 hardening, `codegenie.languages.__all__` is reserved to **exactly** `{"LanguagePack", "LanguageRegistry", "register_language", "default_language_registry", "LanguageRegistryError", "language_packs"}`. `Detected` / `NotDetected` / `DetectionResult` / `Confidence` are **NOT** in this set. Test asserts:
  ```python
  import codegenie.languages as _lang_pkg
  assert set(_lang_pkg.__all__).isdisjoint({"Detected", "NotDetected", "DetectionResult", "Confidence"})
  # And consumers must import via the module path:
  from codegenie.languages.pack import Detected, NotDetected, DetectionResult, Confidence  # MUST succeed
  ```

- [ ] **AC-11 — Sum-type structural integrity (strict `isinstance` discrimination).** `NotDetected` does NOT extend `Detected` and vice versa; neither shares a common non-`object` ancestor introduced by this story. Test asserts:
  ```python
  d = Detected(confidence="high", marker_files=())
  n = NotDetected()
  assert isinstance(d, Detected) and not isinstance(d, NotDetected)
  assert isinstance(n, NotDetected) and not isinstance(n, Detected)
  assert Detected.__mro__[-1] is object                # no introduced common base
  assert NotDetected.__mro__[-1] is object
  ```
  Defends against the failure mode where an executor accidentally makes `NotDetected` extend `Detected` (or both inherit from a shared `_DetectionResultBase`) and every other AC silently passes.

- [ ] **AC-12 — Full local gate.** The TDD red tests exist, are committed, and are green. `ruff check`, `ruff format --check`, `mypy --strict src/`, `pytest -q`, `make fence`, `make lint-imports` all pass. The pre-existing Phase 0–7 regression suite stays green (G3 hard gate).

- [ ] **AC-13 — Status.** Story `**Status:**` set to `Done` on completion.

## Implementation outline
1. **Create** `src/codegenie/languages/__init__.py` — net-new package skeleton (S1-03 is the first story to land in `codegenie.languages`; S1-02 hardening confirmed it appends to S1-03's `pack.py`). Keep `__init__.py` minimal — do NOT pre-populate `__all__` with the six reserved names; S1-02 owns that pinning when `LanguagePack` lands.
2. **Create** `src/codegenie/languages/pack.py` with `from __future__ import annotations`. Imports for this story's contribution are **stdlib only**: `from dataclasses import dataclass, FrozenInstanceError` (the latter referenced from tests, not pack.py); `from pathlib import Path`; `from typing import Literal, TypeAlias`. Do **NOT** import any `codegenie.*` sibling module; do **NOT** import any `tree_sitter*` wheel; do **NOT** import `logging` or any I/O module. (S1-02 / S1-04 widen the import set later when they append `LanguagePack` / `ProjectDetector`.)
3. Define `Confidence: TypeAlias = Literal["high", "medium", "low"]` — argument order is contract (ADR-0005); mirror `types/identifiers.py:251` form (`Foo: TypeAlias = ...`).
4. Define `Detected` as `@dataclass(frozen=True)` with two fields in canonical order: `confidence: Confidence`, then `marker_files: tuple[Path, ...]`. One docstring line citing ADR-0005 is acceptable; no behavior, no methods.
5. Define `NotDetected` as `@dataclass(frozen=True)` with no fields. One docstring line citing ADR-0005's "singleton-shaped" descriptive language is acceptable; do **NOT** introduce a `_NOTDETECTED_INSTANCE` module-level singleton.
6. Define `DetectionResult: TypeAlias = Detected | NotDetected`. Argument order in the union matters — `get_args(DetectionResult) == (Detected, NotDetected)` is asserted by AC-4.
7. **Do NOT** add `Detected` / `NotDetected` / `DetectionResult` / `Confidence` to `codegenie.languages.__all__` (S1-02's six-name reservation; AC-10). Consumers will import via `from codegenie.languages.pack import ...`.
8. **Write the TDD red tests first**, then `pack.py`, then run `make check` + `make fence` + `make lint-imports` as the sealing gate. The red tests must be **committed** (AC-12).

## TDD plan — red / green / refactor
### Red — write the failing tests first

Test file: `tests/unit/languages/test_detection_result.py` (new). Near-executable templates:

```python
# tests/unit/languages/test_detection_result.py
from __future__ import annotations

import ast
import dataclasses
import pathlib
import subprocess
import sys
from pathlib import Path
from typing import assert_never, get_args

import pytest

from codegenie.languages.pack import (
    Confidence,
    Detected,
    DetectionResult,
    NotDetected,
)


# AC-1 — Confidence alias form + argument order
def test_confidence_argument_order_is_high_medium_low() -> None:
    assert get_args(Confidence) == ("high", "medium", "low"), (
        "ADR-0005 uses confidence='high' for real manifest, 'low' for bare *.py; "
        "argument order is contract — downstream conformance pins assume this order."
    )


# AC-2 — Detected shape
def test_detected_fields_and_frozen() -> None:
    fields = dataclasses.fields(Detected)
    assert tuple(f.name for f in fields) == ("confidence", "marker_files")
    assert dataclasses.is_dataclass(Detected)
    assert Detected.__dataclass_params__.frozen is True


# AC-3 — NotDetected shape
def test_notdetected_zero_fields_and_frozen() -> None:
    assert dataclasses.fields(NotDetected) == ()
    assert dataclasses.is_dataclass(NotDetected)
    assert NotDetected.__dataclass_params__.frozen is True


# AC-4 — DetectionResult alias union args
def test_detection_result_union_args() -> None:
    assert get_args(DetectionResult) == (Detected, NotDetected)


# AC-5 — Frozen across three field categories
@pytest.mark.parametrize(
    ("variant_builder", "attribute", "new_value"),
    [
        # scalar Literal field
        (lambda: Detected(confidence="high", marker_files=(Path("pyproject.toml"),)), "confidence", "low"),
        # tuple field
        (lambda: Detected(confidence="high", marker_files=(Path("pyproject.toml"),)), "marker_files", ()),
        # no-field-attribute-creation on NotDetected
        (lambda: NotDetected(), "foo", 1),
    ],
)
def test_frozen_blocks_assignment_across_categories(variant_builder, attribute, new_value) -> None:
    instance = variant_builder()
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(instance, attribute, new_value)


# AC-6 — Equality + hash semantics (dataclass-generated __eq__ / __hash__)
def test_detected_value_equality_and_hash_stable() -> None:
    d1 = Detected(confidence="high", marker_files=(Path("p"),))
    d2 = Detected(confidence="high", marker_files=(Path("p"),))
    assert d1 == d2
    assert hash(d1) == hash(d2)


def test_notdetected_instances_interchangeable() -> None:
    assert NotDetected() == NotDetected()
    assert hash(NotDetected()) == hash(NotDetected())


def test_variants_unequal() -> None:
    assert Detected(confidence="high", marker_files=()) != NotDetected()


# AC-7 — marker_files is structurally a tuple
def test_marker_files_is_a_tuple_instance() -> None:
    d = Detected(confidence="high", marker_files=(Path("pyproject.toml"),))
    assert isinstance(d.marker_files, tuple)
    with pytest.raises(AttributeError):
        d.marker_files.append(Path("setup.py"))  # type: ignore[attr-defined]


# AC-8 — Match exhaustiveness with assert_never runtime witness
def _classify(r: DetectionResult) -> str:
    match r:
        case Detected():
            return "detected"
        case NotDetected():
            return "not_detected"
        case _:
            assert_never(r)  # runtime witness; mypy --strict also enforces statically (S1-06 owns the static fence)


def test_match_dispatch_detected_arm() -> None:
    assert _classify(Detected(confidence="high", marker_files=())) == "detected"


def test_match_dispatch_notdetected_arm() -> None:
    assert _classify(NotDetected()) == "not_detected"


# AC-9 — Module purity (stdlib-only for S1-03's contribution at time of landing)
def test_pack_module_is_stdlib_only_for_s1_03_contribution() -> None:
    src = pathlib.Path("src/codegenie/languages/pack.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    allowed_top_level = {"__future__", "dataclasses", "pathlib", "typing", "collections", "collections.abc"}
    forbidden = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                root = n.name.split(".", 1)[0]
                if root not in allowed_top_level and not n.name.startswith("collections."):
                    forbidden.add(n.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            root = mod.split(".", 1)[0]
            if root not in allowed_top_level and not mod.startswith("collections."):
                forbidden.add(mod)
    # NOTE: when S1-02 / S1-04 land, this allowlist widens (LanguagePack pulls codegenie.types.identifiers,
    # ProjectDetector pulls codegenie.probes.base, etc.). Update this test alongside.
    assert not forbidden, (
        f"pack.py introduced non-stdlib imports for S1-03's contribution: {forbidden!r}. "
        f"This story's contribution must be stdlib-only; S1-02 / S1-04 widen the allowlist later."
    )


# AC-10 — codegenie.languages.__all__ non-inclusion
def test_s1_03_symbols_not_in_package_all() -> None:
    import codegenie.languages as _lang_pkg

    reserved = {"Detected", "NotDetected", "DetectionResult", "Confidence"}
    all_set = set(getattr(_lang_pkg, "__all__", ()))
    assert all_set.isdisjoint(reserved), (
        f"S1-02 reserved __all__ to six names; S1-03 symbols MUST stay module-level in pack.py. "
        f"Found in __all__: {all_set & reserved!r}"
    )


def test_consumer_import_path_via_pack_module_succeeds() -> None:
    # If this import fails, the executor likely re-exported through __init__.py — undoing S1-02's reservation.
    from codegenie.languages.pack import Confidence, Detected, DetectionResult, NotDetected  # noqa: F401


# AC-11 — Sum-type structural integrity (strict isinstance discrimination)
def test_isinstance_strict_discrimination() -> None:
    d = Detected(confidence="high", marker_files=())
    n = NotDetected()
    assert isinstance(d, Detected) and not isinstance(d, NotDetected)
    assert isinstance(n, NotDetected) and not isinstance(n, Detected)


def test_no_shared_introduced_base() -> None:
    # Both variants must inherit directly from object — no introduced _DetectionResultBase.
    assert Detected.__mro__[-1] is object
    assert NotDetected.__mro__[-1] is object
    # And they share no non-object ancestor.
    assert set(Detected.__mro__) & set(NotDetected.__mro__) == {object}
```

Property test file: `tests/property/test_detection_result.py` (new). Hypothesis property drawing over `Confidence` and `marker_files`' full input spaces:

```python
# tests/property/test_detection_result.py
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import get_args

import pytest
from hypothesis import given, strategies as st

from codegenie.languages.pack import Confidence, Detected


_paths = st.lists(st.text(min_size=1, max_size=8).map(Path), max_size=4).map(tuple)


@given(confidence=st.sampled_from(get_args(Confidence)), marker_files=_paths)
def test_detected_property_constructible_frozen_hashable(confidence: str, marker_files: tuple[Path, ...]) -> None:
    d = Detected(confidence=confidence, marker_files=marker_files)
    # Constructible
    assert d.confidence == confidence
    assert d.marker_files == marker_files
    # Frozen (kills "frozen at construction only" mutations)
    with pytest.raises(dataclasses.FrozenInstanceError):
        d.confidence = "low" if confidence != "low" else "high"
    # Hash + equality value-stable
    d2 = Detected(confidence=confidence, marker_files=marker_files)
    assert d == d2 and hash(d) == hash(d2)
```

Before `pack.py` exists, every import is an `ImportError` — the red.

### Green — make it pass

`src/codegenie/languages/pack.py`:

```python
# src/codegenie/languages/pack.py
"""Language-pack types — `DetectionResult` sum type and supporting aliases.

This module is **stdlib-only** for S1-03's contribution. S1-02 appends
`LanguagePack` (which pulls codegenie sibling imports for field types);
S1-04 appends the `ProjectDetector` Protocol. Until those land,
`pack.py` carries only the type definitions below.

References:
- Phase ADR-0005 — `ProjectDetector` Protocol returns `Detected | NotDetected`.
- Phase arch §Data model — canonical `@dataclass(frozen=True)` form for both variants.
- Production ADR-0033 — sum-type discipline; closed-set `Literal` for state primitives.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias


Confidence: TypeAlias = Literal["high", "medium", "low"]
"""Closed-set confidence marker. Argument order is contract (ADR-0005)."""


@dataclass(frozen=True)
class Detected:
    """Positive detection — carries the confidence and matched marker files."""

    confidence: Confidence
    marker_files: tuple[Path, ...]


@dataclass(frozen=True)
class NotDetected:
    """Negative detection — singleton-shaped (zero fields, instances interchangeable)."""


DetectionResult: TypeAlias = Detected | NotDetected
"""Tagged union over `Detected | NotDetected`. Exhaustiveness: use `typing.assert_never`
in the catch-all arm of any `match` to make a missing variant a runtime + static error."""
```

Nothing else. No methods, no `Variant` enum, no `_NOTDETECTED_INSTANCE` singleton, no abstract base class.

### Refactor — clean up
- Confirm docstrings on `Detected` / `NotDetected` are one line each, citing ADR-0005.
- Confirm `marker_files` annotation is `tuple[Path, ...]` (not `list`, not `Sequence`, not `Iterable`) — tuple is the frozen-by-construction container.
- Confirm `Confidence`'s argument order is `("high", "medium", "low")` exactly.
- Confirm no `_NOTDETECTED_INSTANCE` sentinel, no `_DetectionResultBase` shared parent, no `Variant` enum.
- Confirm `pack.py` imports are exactly `from __future__ import annotations`, `from dataclasses import dataclass`, `from pathlib import Path`, `from typing import Literal, TypeAlias`.
- Run `make check` + `make fence` + `make lint-imports` as the sealing gate.

## Files to touch
| Path | Verb | Why |
|---|---|---|
| `src/codegenie/languages/__init__.py` | `new` | net-new package skeleton; S1-03 is the first story to land here; S1-02 will populate `__all__` when `LanguagePack` lands |
| `src/codegenie/languages/pack.py` | `new` | net-new — holds `Confidence`, `Detected`, `NotDetected`, `DetectionResult`; S1-02 / S1-04 append `LanguagePack` / `ProjectDetector` later |
| `tests/unit/languages/__init__.py` | `new` | test package skeleton (if not already present) |
| `tests/unit/languages/test_detection_result.py` | `new` | shape + frozen + equality + hash + match + isinstance + module-purity + `__all__`-non-inclusion tests (AC-1..AC-11) |
| `tests/property/test_detection_result.py` | `new` | hypothesis property test over `Confidence × marker_files` input space (AC-5, AC-6 reinforced) |

## Out of scope
- The `ProjectDetector` Protocol that returns `DetectionResult` — S1-04.
- The `LanguagePack` value — S1-02.
- The `LANGUAGE_MARKERS` shared marker catalog — S1-05.
- Any concrete detector implementation — S3-03 (TypeScript), S4-03 (Python).
- Monotonicity / additivity properties of detection (a polyglot repo detected as both languages) — that's a `ProjectDetector` *implementation* concern (S3-03 / S4-03).
- The **static-time** mypy-must-fail proof (a planted `match` missing `NotDetected` is rejected by mypy) — S1-06 owns the mypy-must-fail harness; this story commits only the **runtime** `assert_never` witness.
- Migrating the inline `Literal["high", "medium", "low"]` usages in `src/codegenie/probes/layer_g/semgrep.py`, `ripgrep_curated.py`, and `test_coverage_mapping.py` to consume the new canonical `Confidence` alias — that's a separate sanctioned migration (ADR-0043 — extension by addition; silent edits forbidden).

## Notes for the implementer

- **Technology precedent: `@dataclass`, NOT Pydantic.** The story's References block names `src/codegenie/result.py` as a **naming / co-location** precedent (sum-type variants + `TypeAlias` co-located in one module). `result.py` is **Pydantic `BaseModel`**, NOT `@dataclass` — the arch §Data model code block is the **technology** precedent (`@dataclass(frozen=True)`). Do **not** copy `result.py`'s `BaseModel` form. The arch chose `@dataclass` for `DetectionResult` because this is an *internal* sum type produced/consumed within `codegenie.languages` (no user-facing validation surface to justify Pydantic's overhead); `LanguagePack` / `Result` are Pydantic because they validate *user-facing* shapes.

- **`Confidence` is intentionally a NEW alias — do NOT migrate existing inline literals.** `src/codegenie/probes/layer_g/semgrep.py:190`, `ripgrep_curated.py:172`, and `test_coverage_mapping.py:140` each declare `confidence: Literal["high", "medium", "low"]` inline. Per production ADR-0043 (extension by addition; silent edits forbidden), this story does **NOT** touch those files. The dual existence is intentional; a future migration may unify them under `Confidence`, but that's a separate sanctioned sweep.

- **`__all__` reservation discipline.** S1-02's hardening (see [`_validation/S1-02-add-languagepack-frozen-value.md`](_validation/S1-02-add-languagepack-frozen-value.md)) reserved `codegenie.languages.__all__` to **exactly six names**: `LanguagePack`, `LanguageRegistry`, `register_language`, `default_language_registry`, `LanguageRegistryError`, `language_packs`. `Detected` / `NotDetected` / `DetectionResult` / `Confidence` are **NOT** in this set and **MUST NOT** be added. Consumers import via `from codegenie.languages.pack import ...` (module path), not `from codegenie.languages import ...` (package surface). AC-10 enforces this.

- **No `_NOTDETECTED_INSTANCE` singleton.** The arch's "singleton-shaped" language is **descriptive**, not prescriptive — a zero-field frozen dataclass is NOT a singleton; every `NotDetected()` call creates a new instance, but they all compare equal via the dataclass-generated `__eq__`. Do NOT introduce `_NOTDETECTED_INSTANCE: Final = NotDetected()` — it's an anti-pattern that couples consumers to identity rather than to type (and `match case NotDetected():` works on the *type* via the dataclass-generated `__match_args__`, not on identity).

- **No abstract base class, no `Variant` enum, no `ResultBuilder` helper.** The sum type **IS** the abstraction. Open/Closed seams live at the **registry** level (S2-01 `LanguageRegistry`, S5-02..S5-04 dep-graph strategy registries) and at the **Protocol** level (S1-04 `ProjectDetector`), NOT at the value-type level. Adding a `_DetectionResultBase` parent or a `DetectionResultVariant` enum would (a) violate the sum-type-not-bool discipline ADR-0005 chose Option D over Option C to enforce, and (b) cross the "three similar lines is better than premature abstraction" line (Rule 2). The sum type has exactly **two** variants, both with their own contract — abstraction earns its keep only when a third variant appears with a shared concern (and even then, addition-via-the-union is preferred over inheritance).

- **`assert_never` is the runtime exhaustiveness witness; S1-06 owns the static fence.** `typing.assert_never(r)` in the `case _:` arm raises `AssertionError` at runtime if a variant escapes the explicit arms, AND `mypy --strict` rejects the function if the narrowed type at that point is not `Never` (the static-time signal). This story's AC-8 commits the *runtime* witness in the test fixture. The *static-time* non-exhaustiveness proof (a planted `match` missing `NotDetected` is rejected by mypy) lives in S1-06's mypy-must-fail harness. Two complementary mechanisms; don't conflate them here.

- **Stdlib-only invariant during S1-03.** `pack.py` imports for this story's contribution are exactly `from __future__ import annotations`, `from dataclasses import dataclass`, `from pathlib import Path`, `from typing import Literal, TypeAlias`. No `codegenie.*` sibling imports, no `tree_sitter*`, no `logging`. S1-02 / S1-04 widen the import set when they append `LanguagePack` / `ProjectDetector`. The hard rule: **no I/O, no logger, no grammar wheels EVER** in this module — type definitions only. (S1-02 AC-10 is the permanent package-level grammar-wheel-free guarantee; this story's AC-9 is the S1-03-scoped module-level stdlib-only invariant.)

- **Match dispatch + `__match_args__`.** Dataclasses auto-generate `__match_args__` from the field declarations. `match Detected(confidence=c, marker_files=m): ...` works without further ceremony. The shape tests (AC-2, AC-3) pinning field name order also lock the match-pattern order — a future reorder would break downstream consumers that pattern-match positionally. Document the link in a one-line code comment if it helps an executor; do NOT add a separate AC for `__match_args__` (it's a derived property of the field declarations).
