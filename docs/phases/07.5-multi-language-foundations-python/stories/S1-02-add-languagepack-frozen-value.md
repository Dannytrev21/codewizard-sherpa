# Story S1-02 — Add the `LanguagePack` frozen total value

**Step:** Step 1 — Establish the `LanguagePack` contract, the `DetectionResult` sum type, and the `markers.py` catalog
**Status:** HARDENED
**Effort:** M
**Depends on:** S1-01, S1-04 (transitively S1-03 via S1-04)
**ADRs honored:** ADR-0001, ADR-0003, ADR-0006

## Validation notes (phase-story-validator v1 · 2026-05-26)

- Story is **structurally sound** — Goal, ADRs, references, and arch trace are all internally consistent. No `RESCUE`-level findings; verdict: **HARDENED**.
- **Coverage hardened (5)**: added AC pinning `probes_self_registered` default to `False` (load-bearing ADR-0006 fact); added AC pinning the canonical `model_fields` order (snapshot fence S7-05 depends on it); promoted "no grammar-wheel import on `import codegenie.languages`" from a Notes hint to an AC with a concrete `sys.modules` test; widened the frozen-mutation AC to cover **multiple** field types (`Literal` newtype, tuple field, mapping field) so a partial `frozen=True` regression cannot pass; widened the `arbitrary_types_allowed` test to exercise **both** the `type[Probe]` field and the `DepGraphStrategy` callable inside `dep_graph_strategies`.
- **Test-quality hardened (4)**: TDD snippets were pseudocode `#` comments — rewritten as near-executable `assert` templates; a shared `_valid_pack(**overrides)` helper is now mandatory (lives in `tests/unit/languages/conftest.py` so S1-04 can reuse it); the derived-`@property` AC now asserts `inspect.getattr_static(LanguagePack, "package_managers")` is a `property` descriptor (catches an executor naively making it a Pydantic Field with `default_factory`); a hypothesis property test was added for `package_managers ≡ tuple(dep_graph_strategies.keys())` to kill the "second source of truth" risk (final-design §Departures item 5).
- **Consistency clarified (2)**: Files-to-touch verbs split into `append` (`pack.py`, `__init__.py` already exist post-S1-03/S1-04) vs. `new`/`update`; Implementation outline step 1 now reads "append `LanguagePack` to the existing `pack.py`" rather than "Ensure … exists".
- **Design-patterns surfaced (3)**: pinned `__all__` to the **exact** six-name reserved set (`LanguagePack`, `LanguageRegistry`, `register_language`, `default_language_registry`, `LanguageRegistryError`, `language_packs`) — Step-1 ships only `LanguagePack`, but the `__all__` is reserved to those names so later stories cannot squat reserved slots; added Notes — `search_adapter_module: str` is **intentionally** stringly-typed per production ADR-0032, format validation belongs in `validate_pack` (S2-02), NOT in `LanguagePack`; added Notes pointing at `src/codegenie/result.py` (`Ok`/`Err`) as the canonical Pydantic v2 `ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)` style precedent — mirror it for review-style consistency.
- Full audit log: [`_validation/S1-02-add-languagepack-frozen-value.md`](_validation/S1-02-add-languagepack-frozen-value.md).

## Context
`LanguagePack` is the load-bearing value of the phase: a frozen Pydantic model that *is* a language — six required capability fields plus one typed retrofit discriminator. A partial language is a real bug, and a total frozen value pushes that bug to the construction site where `mypy --strict` catches it for free (G2). This story lands the new `src/codegenie/languages/` package's `LanguagePack` definition; it is the seam every Phase 8+ target language registers through and the type `S2-01`'s registry and `S3-02`/`S7-01`'s packs construct.

## References — where to look
- **Architecture:** `../phase-arch-design.md §Component design — LanguagePack` — the full public-interface code block (`model_config`, six fields, `package_managers` `@property`).
- **Architecture:** `../phase-arch-design.md §Data model` — the `LanguagePack — contract (stable, in-memory; pinned by snapshot fence)` block — the canonical field list and order.
- **Phase ADRs (rules to honor):** `../ADRs/0001-languagepack-total-frozen-value-contract-and-freeze.md` — ADR-0001 — frozen Pydantic v2, `ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)`; `package_managers` is a derived `@property`, NOT a field.
- **Phase ADRs (rules to honor):** `../ADRs/0003-grammars-modeled-one-to-many-relation.md` — ADR-0003 — `language: Language` reuses the existing newtype; `grammars: tuple[SupportedLanguage, ...]` models the one-to-many relation.
- **Phase ADRs (rules to honor):** `../ADRs/0006-typescript-retrofit-by-reference-probes-self-registered.md` — ADR-0006 — `probes_self_registered: bool = False` is the typed retrofit discriminator.
- **Source design:** `../final-design.md §Departures` item 5 — `package_managers` derived `@property` over `dep_graph_strategies.keys()`, never a seventh field (drift-prone dual source of truth).
- **Existing code:** `src/codegenie/types/identifiers.py` — `Language`, `PackageManager` (the `+3` from S1-01).
- **Existing code:** `src/codegenie/grammars/lock.py` — `SupportedLanguage` (the `+1` from S1-01).
- **Existing code:** `src/codegenie/probes/base.py` — `Probe` ABC (`layer_a_probes: tuple[type[Probe], ...]`).
- **Existing code:** `src/codegenie/depgraph/registry.py` — `DepGraphStrategy` callable alias.

## Goal
Land the `src/codegenie/languages/` package carrying the frozen Pydantic `LanguagePack` with six required capability fields, the `probes_self_registered` discriminator, and the derived `package_managers` property — such that an incomplete construction is a `mypy --strict` error.

## Acceptance criteria
- [ ] **AC-1 — model shape.** `LanguagePack` is a `pydantic.BaseModel` with `model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)`. Test asserts `LanguagePack.model_config["frozen"] is True`, `LanguagePack.model_config["extra"] == "forbid"`, `LanguagePack.model_config["arbitrary_types_allowed"] is True`.
- [ ] **AC-2 — canonical field set + order.** `LanguagePack` carries exactly: `language: Language`, `grammars: tuple[SupportedLanguage, ...]`, `project_detector: ProjectDetector`, `layer_a_probes: tuple[type[Probe], ...]`, `dep_graph_strategies: Mapping[PackageManager, DepGraphStrategy]`, `search_adapter_module: str`, `probes_self_registered: bool = False`. Test asserts:
  ```python
  assert tuple(LanguagePack.model_fields.keys()) == (
      "language", "grammars", "project_detector", "layer_a_probes",
      "dep_graph_strategies", "search_adapter_module", "probes_self_registered",
  )
  ```
  Order matters — the snapshot fence (S7-05) pins this tuple. `package_managers` is **NOT** in `model_fields`.
- [ ] **AC-3 — `package_managers` is a class-level `property` descriptor, not a field.** `inspect.getattr_static(LanguagePack, "package_managers")` is an instance of `property`; `"package_managers" not in LanguagePack.model_fields`. (A naive executor making `package_managers` a `Field(default_factory=...)` would pass a "returns the keys" check; this AC kills that mutation.)
- [ ] **AC-4 — derived equivalence.** `pack.package_managers == tuple(pack.dep_graph_strategies.keys())` for every constructed pack. A **hypothesis property test** (`tests/property/test_language_pack_derived.py`) asserts this for `≥ 5` randomly drawn non-empty subsets of `get_args(PackageManager)`. (No second source of truth — final-design §Departures item 5.)
- [ ] **AC-5 — `probes_self_registered` default.** `LanguagePack.model_fields["probes_self_registered"].default is False`. The retrofit discriminator (ADR-0006) is `False` by default; a wrong default would silently make every Python pack a retrofit and skip its probe fan-out.
- [ ] **AC-6 — extra field rejected, missing field rejected.** Constructing with an extra/typo'd field raises `pydantic.ValidationError` (`extra="forbid"`). Constructing with any one required field omitted raises `pydantic.ValidationError` — a **parameterized** test omits each of the six required fields in turn (six `pytest.raises` cases). (Compile-time `mypy --strict` proof is S1-06; this AC pins the runtime guarantee.)
- [ ] **AC-7 — frozen across all field categories.** `pack.language = Language("typescript")` raises (`pydantic.ValidationError` under Pydantic v2's `frozen=True`); the same assignment failure holds when mutating a tuple-typed field (`pack.grammars = (...)`) and a mapping-typed field (`pack.dep_graph_strategies = {...}`). All three categories — `Literal` newtype, tuple, mapping — are covered by separate `pytest.raises` cases. Additionally: `pack.grammars` is a `tuple` (so `.append` raises `AttributeError`) — confirming the immutability is **structural**, not just Pydantic-level.
- [ ] **AC-8 — `arbitrary_types_allowed` does not weaken `frozen` or `extra="forbid"`.** Construct a pack carrying a real `type[Probe]` subclass in `layer_a_probes` AND a real `DepGraphStrategy` callable inside `dep_graph_strategies`. Assert that the frozen-mutation block AND the `extra="forbid"` check **both** still fire under that mode (arch §Step 1 risk; both arbitrary-typed fields exercised, not just one).
- [ ] **AC-9 — `__all__` reserves the exact six-name set.** `src/codegenie/languages/__init__.py` defines `__all__` containing **exactly** `{"LanguagePack", "LanguageRegistry", "register_language", "default_language_registry", "LanguageRegistryError", "language_packs"}` — pin the *set*, not just the count. Step 1 ships `LanguagePack` (and re-exports from S1-01 / S1-03 / S1-04 as they land); the other names raise `ImportError` until their owning story lands. A test asserts `set(codegenie.languages.__all__) == {<the six>}`.
- [ ] **AC-10 — `import codegenie.languages` is grammar-wheel-free.** A unit test (`tests/unit/languages/test_import_purity.py`) runs `import codegenie.languages` in an isolated subprocess and asserts none of `tree_sitter`, `tree_sitter_typescript`, `tree_sitter_python`, `tree_sitter_javascript` are in `sys.modules`. The pack holds grammar *keys* (`SupportedLanguage` `Literal` members), not loaded `Language` objects; the wheel must load lazily on first `language_for` (Notes).
- [ ] **AC-11 — import-linter contract for the new package.** `pyproject.toml` adds an `[[tool.importlinter.contracts]]` entry for `codegenie.languages` forbidding the `FORBIDDEN_LLM_SDKS` set (mirror the shape used by `codegenie.plugins` / `codegenie.transforms`). `make lint-imports` and `make fence` are green.
- [ ] **AC-12 — full local gate.** The TDD red test exists, is committed, and is green. `ruff check`, `ruff format --check`, `mypy --strict src/`, `pytest -q`, `make fence`, `make lint-imports` all pass. The pre-existing Phase 1–7 regression suite stays green (G3 hard gate).
- [ ] **AC-13 — status.** Story `**Status:**` set to `Done` on completion.

## Implementation outline
1. **Append** to the existing `src/codegenie/languages/pack.py` (created by S1-03 for `DetectionResult`; extended by S1-04 for `ProjectDetector`). Do **not** create a new module; this story adds `LanguagePack` next to the existing siblings so the language-axis surface stays in one file (mirrors `codegenie.result`'s `Ok` + `Err` + `Result` co-location).
2. Import the field types: `Language`/`PackageManager` from `codegenie.types.identifiers`, `SupportedLanguage` from `codegenie.grammars.lock`, `Probe` from `codegenie.probes.base`, `DepGraphStrategy` from `codegenie.depgraph.registry`. Import `Mapping` from `collections.abc`; import `BaseModel`, `ConfigDict` from `pydantic`. **Do not** import any `tree_sitter*` wheel here (AC-10).
3. Declare the model with `model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)`, the six required fields in the canonical order (AC-2), the typed discriminator `probes_self_registered: bool = False`, and `package_managers` as a `@property` returning `tuple(self.dep_graph_strategies.keys())`.
4. **Append** to `src/codegenie/languages/__init__.py`: re-export `LanguagePack`. Reserve the full six-name `__all__` set per AC-9 — names whose modules don't exist yet (`LanguageRegistry`, etc.) are listed but not yet importable; the executor MUST NOT add stub modules to satisfy import — the test for AC-9 only inspects `__all__` membership, not import resolvability.
5. Add `[[tool.importlinter.contracts]]` for `codegenie.languages` to `pyproject.toml` — `type = "forbidden"`, `source_modules = ["codegenie.languages"]`, `forbidden_modules = ["langgraph", "openai", "langchain", "transformers", "sentence-transformers", "torch"]`, `as_packages = true` (mirror the `codegenie.plugins` / `codegenie.transforms` shape).
6. Land the `_valid_pack(**overrides)` helper in `tests/unit/languages/conftest.py` (NOT in the test file) — S1-04 reuses it. Helper builds a complete pack from a stub `ProjectDetector` and a stub `Probe` subclass, accepting per-test overrides.
7. Write the red tests across `tests/unit/languages/test_language_pack.py`, `tests/unit/languages/test_import_purity.py`, and `tests/property/test_language_pack_derived.py`. Run red, then green.
8. Run `make check` + `make fence` + `make lint-imports` to seal AC-11/AC-12.

## TDD plan — red / green / refactor
### Shared helper — `tests/unit/languages/conftest.py` (NEW; reused by S1-04 too)
```python
from collections.abc import Mapping
from typing import Any

from codegenie.depgraph.registry import DepGraphStrategy
from codegenie.languages.pack import (
    Detected,
    DetectionResult,
    LanguagePack,
    NotDetected,
    ProjectDetector,
)
from codegenie.probes.base import Probe, ProbeContext, ProbeOutput, RepoSnapshot
from codegenie.types.identifiers import Language, PackageManager


class _StubDetector:  # structural ProjectDetector
    def detect(self, repo: RepoSnapshot) -> DetectionResult:
        return NotDetected()


class _StubProbe(Probe):
    name = "stub"
    layer = "A"
    tier = "base"
    applies_to_tasks = ["*"]
    applies_to_languages = ["*"]
    requires: list[str] = []
    declared_inputs: list[str] = []

    async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput:  # pragma: no cover
        raise NotImplementedError


def _stub_strategy(ctx: ProbeContext, manifests: list[Mapping[str, Any]]):  # pragma: no cover
    raise NotImplementedError


def _valid_pack(**overrides: Any) -> LanguagePack:
    defaults: dict[str, Any] = dict(
        language=Language("python"),
        grammars=(),                                # empty is fine here; AC-2/AC-7 don't depend on grammar membership
        project_detector=_StubDetector(),
        layer_a_probes=(_StubProbe,),
        dep_graph_strategies={PackageManager("pip"): _stub_strategy},
        search_adapter_module="codegenie.search.stub:StubAdapter",
        # probes_self_registered defaults to False — exercised by AC-5
    )
    defaults.update(overrides)
    return LanguagePack(**defaults)
```

### Red — write the failing tests first
**Test file 1: `tests/unit/languages/test_language_pack.py`** (NEW)

```python
import inspect
from collections.abc import Mapping

import pytest
from pydantic import ValidationError

from codegenie.depgraph.registry import DepGraphStrategy
from codegenie.languages.pack import LanguagePack, ProjectDetector
from codegenie.probes.base import Probe
from codegenie.types.identifiers import Language, PackageManager


# AC-1 — model_config flags
def test_model_config_is_frozen_extra_forbid_arbitrary_types() -> None:
    assert LanguagePack.model_config["frozen"] is True
    assert LanguagePack.model_config["extra"] == "forbid"
    assert LanguagePack.model_config["arbitrary_types_allowed"] is True


# AC-2 — canonical field order
def test_model_fields_are_exactly_the_canonical_seven_in_order() -> None:
    assert tuple(LanguagePack.model_fields.keys()) == (
        "language", "grammars", "project_detector", "layer_a_probes",
        "dep_graph_strategies", "search_adapter_module", "probes_self_registered",
    )
    assert "package_managers" not in LanguagePack.model_fields  # NOT a field


# AC-3 — package_managers is a class-level property descriptor
def test_package_managers_is_a_property_descriptor_not_a_field() -> None:
    descriptor = inspect.getattr_static(LanguagePack, "package_managers")
    assert isinstance(descriptor, property), (
        "package_managers must be a @property, not a Pydantic Field"
    )


# AC-5 — probes_self_registered default
def test_probes_self_registered_default_is_false() -> None:
    assert LanguagePack.model_fields["probes_self_registered"].default is False


# AC-6 — extra field rejected
def test_extra_field_is_validation_error(_valid_pack):
    with pytest.raises(ValidationError):
        _valid_pack(bogus_field=1)


# AC-6 — every required field omitted in turn raises ValidationError
@pytest.mark.parametrize(
    "missing",
    [
        "language", "grammars", "project_detector",
        "layer_a_probes", "dep_graph_strategies", "search_adapter_module",
    ],
)
def test_missing_required_field_raises_validation_error(_valid_pack, missing: str) -> None:
    with pytest.raises(ValidationError):
        _valid_pack(**{missing: ...})  # ellipsis triggers Pydantic missing-field path
        # (or: build kwargs explicitly and pop `missing` — both shapes acceptable)


# AC-7 — frozen across Literal, tuple, and mapping field categories
def test_pack_is_frozen_on_literal_field(_valid_pack):
    pack = _valid_pack()
    with pytest.raises(ValidationError):
        pack.language = Language("typescript")  # pydantic v2 frozen → ValidationError


def test_pack_is_frozen_on_tuple_field(_valid_pack):
    pack = _valid_pack()
    with pytest.raises(ValidationError):
        pack.grammars = ()


def test_pack_is_frozen_on_mapping_field(_valid_pack):
    pack = _valid_pack()
    with pytest.raises(ValidationError):
        pack.dep_graph_strategies = {}


def test_grammars_field_is_tuple_not_list(_valid_pack):
    pack = _valid_pack()
    assert isinstance(pack.grammars, tuple)
    with pytest.raises(AttributeError):
        pack.grammars.append("typescript")  # tuple is structurally immutable


# AC-8 — arbitrary_types_allowed does not weaken frozen / extra="forbid"
def test_arbitrary_types_allowed_still_enforces_frozen_and_extra_forbid(_valid_pack):
    # pack carries a real type[Probe] in layer_a_probes AND a real DepGraphStrategy in
    # dep_graph_strategies — both arbitrary types — yet both guarantees must hold.
    pack = _valid_pack()
    with pytest.raises(ValidationError):
        pack.layer_a_probes = ()
    with pytest.raises(ValidationError):
        _valid_pack(bogus=1)


# AC-4 (concrete) + AC-3 — derived property equivalence on a concrete construction
def test_package_managers_returns_keys_of_dep_graph_strategies(_valid_pack):
    pack = _valid_pack()
    assert pack.package_managers == tuple(pack.dep_graph_strategies.keys())
```

**Test file 2: `tests/unit/languages/test_import_purity.py`** (NEW — AC-10)

```python
import subprocess
import sys
import textwrap


def test_importing_codegenie_languages_does_not_load_grammar_wheels() -> None:
    """import codegenie.languages must NOT transitively import any tree-sitter wheel.
    The pack holds grammar *keys* (SupportedLanguage Literal members), not loaded
    Language objects; the wheel must stay lazy on first language_for() call."""
    script = textwrap.dedent(
        """
        import sys, json
        import codegenie.languages  # noqa: F401
        loaded = sorted(m for m in sys.modules if m.startswith("tree_sitter"))
        print(json.dumps(loaded))
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script], check=True, capture_output=True, text=True
    )
    import json
    assert json.loads(result.stdout) == [], (
        f"importing codegenie.languages transitively imported {result.stdout!r}"
    )
```

**Test file 3: `tests/property/test_language_pack_derived.py`** (NEW — AC-4)

```python
from hypothesis import given
from hypothesis import strategies as st

from codegenie.types.identifiers import PackageManager
from tests.unit.languages.conftest import _stub_strategy, _valid_pack


_PM_VALUES = tuple(PackageManager(s) for s in ("npm", "yarn", "pnpm", "pip", "poetry", "uv"))


@given(st.lists(st.sampled_from(_PM_VALUES), min_size=1, max_size=6, unique=True))
def test_package_managers_property_tracks_dep_graph_strategies_keys(pms: list[PackageManager]) -> None:
    strategies = {pm: _stub_strategy for pm in pms}
    pack = _valid_pack(dep_graph_strategies=strategies)
    # The @property has NO independent state — it must equal the mapping's keys, always.
    assert pack.package_managers == tuple(strategies.keys())
    # Metamorphic check: rebuilding with same keys yields identical package_managers.
    assert _valid_pack(dep_graph_strategies=strategies).package_managers == pack.package_managers
```

**Test file 4: `tests/unit/languages/test_package_surface.py`** (NEW — AC-9)

```python
import codegenie.languages


_RESERVED_NAMES = {
    "LanguagePack",
    "LanguageRegistry",
    "register_language",
    "default_language_registry",
    "LanguageRegistryError",
    "language_packs",
}


def test_languages_package_all_pins_the_six_reserved_names() -> None:
    assert set(codegenie.languages.__all__) == _RESERVED_NAMES
    # Step-1 ships LanguagePack only — other names exist in __all__ but importing them
    # raises ImportError until their owning story lands. This test does NOT attempt to
    # import them; it ONLY asserts the reservation set is intact.
```

Before `pack.py` carries `LanguagePack`, every test above is RED (`ImportError`, then `AttributeError`/`AssertionError`).

### Green — make it pass
Implement the Pydantic model exactly as the arch §Component design + §Data model blocks specify — six required fields in the canonical order, the typed discriminator, the `@property`. Mirror the style of `src/codegenie/result.py` (`Ok`/`Err`) for `model_config`. No validators beyond Pydantic's built-in totality. **No format validation for `search_adapter_module`** — that "module:ClassName" check belongs to `validate_pack` (S2-02). No registration logic (that is S2-01+).

### Refactor — clean up
Module + field docstrings naming ADR-0001 / ADR-0003 / ADR-0006; confirm `tuple` / `Mapping` (not `list` / `dict`) so the frozen value is genuinely immutable; confirm the `__all__` reservation; add the `import-linter` contract and run `make lint-imports` + `make fence`. Confirm the conftest helper lives at `tests/unit/languages/conftest.py` so S1-04 (and later step-1 stories) can reuse it without duplicating stub objects.

## Files to touch
| Path | Why |
|---|---|
| `src/codegenie/languages/__init__.py` | **append** — re-export `LanguagePack`; `__all__` pinned to the canonical six-name reserved set (AC-9). File already exists (S1-03). |
| `src/codegenie/languages/pack.py` | **append** — add `LanguagePack` next to existing `Detected` / `NotDetected` / `DetectionResult` (S1-03) and `ProjectDetector` (S1-04). Do NOT redefine the siblings. |
| `pyproject.toml` | **update** — add `[[tool.importlinter.contracts]]` for `codegenie.languages` mirroring the `codegenie.plugins` / `codegenie.transforms` shape (AC-11). |
| `tests/unit/languages/conftest.py` | **new** — shared `_valid_pack(**overrides)` helper + `_StubDetector` + `_StubProbe` + `_stub_strategy` (S1-04 reuses these). |
| `tests/unit/languages/test_language_pack.py` | **new** — AC-1..AC-3, AC-5..AC-8 (model-config, field-order, property-descriptor, default, extra-forbid, missing-field, frozen, arbitrary-types). |
| `tests/unit/languages/test_import_purity.py` | **new** — AC-10 grammar-wheel-free import. |
| `tests/unit/languages/test_package_surface.py` | **new** — AC-9 `__all__` reservation set. |
| `tests/property/test_language_pack_derived.py` | **new** — AC-4 hypothesis property test for `package_managers ≡ tuple(dep_graph_strategies.keys())`. |

## Out of scope
- The `mypy`-must-fail snippet harness (the *compile-time* incompleteness proof) — S1-06.
- `LanguageRegistry` / `register_language` / `validate_pack` — Step 2.
- The contract-snapshot fence (`test_language_pack_contract.py`) — S7-05.
- Constructing `TS_PACK` / `PYTHON_PACK` — S3-02 / S7-01.

## Notes for the implementer
- **Style precedent:** `src/codegenie/result.py` (`Ok` / `Err` / `Result`) is the canonical Pydantic-v2 frozen-value shape in this codebase — same `ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)` line, same `BaseModel` subclass shape, same module co-location of related types. Mirror its style (line spacing, docstring shape, import order) for review-style consistency. Do not introduce a new pattern.
- `arbitrary_types_allowed=True` is **required** — `type[Probe]` and the `DepGraphStrategy` callable are not Pydantic-native. The Step-1 risk (arch) is that this mode might weaken `frozen` / `extra="forbid"` — it does not, but AC-8 *asserts* it across **both** arbitrary-typed fields (the `type[Probe]` and the callable inside the mapping), not just one. Do not skip the second exercise.
- `package_managers` is a `@property` returning `tuple(self.dep_graph_strategies.keys())` — **never** a seventh field. A second field would drift (final-design §Departures item 5). AC-3's `inspect.getattr_static` check kills an executor naively making it a `Field(default_factory=...)`; AC-4's hypothesis test kills any implementation that caches the result independently of the mapping.
- **Do not validate `search_adapter_module` format here.** `search_adapter_module: str` is intentionally a plain `str` per production ADR-0032's `"module:ClassName"` adapter idiom. The "module path imports, the class exists" check is `validate_pack`'s responsibility (story S2-02), not the `LanguagePack` model's. Adding format validation here would (a) duplicate S2-02's checks, (b) couple `LanguagePack` construction to module-import time, and (c) break the "pack holds references / strings only — no behavior, no I/O" property the arch component spec calls out.
- Reuse `Language` — do **not** mint a `LanguageId` (ADR-0003). Reuse `Probe` (the frozen ABC at `src/codegenie/probes/base.py`) and `DepGraphStrategy` (the callable alias at `src/codegenie/depgraph/registry.py`) **unchanged** — they are referenced, not redefined.
- `__init__.py` `__all__` is pinned to the **exact** six-name reserved set (AC-9): `LanguagePack`, `LanguageRegistry`, `register_language`, `default_language_registry`, `LanguageRegistryError`, `language_packs`. Step 1 only ships `LanguagePack`; the other names appear in `__all__` so importing `from codegenie.languages import LanguageRegistry` raises a clear `ImportError` ("not yet implemented — see story S2-01") rather than silently succeeding against a stub. **Do not** create stub modules to make those imports resolve.
- `import codegenie.languages` must not transitively import any grammar wheel — `LanguagePack` holds grammar *keys* (the `SupportedLanguage` `Literal` tuple), not loaded `Language` objects; the wheel loads lazily on first `language_for`. AC-10's subprocess test is the binary gate. If you find yourself importing `tree_sitter` anywhere under `codegenie.languages`, you've taken a wrong turn.
- The model is `Provisional Accepted` and frozen (ADR-0001) — S7-05's snapshot fence pins it. Do not over-build it. Six fields + one discriminator, no speculative seventh, no extra Pydantic validators, no methods beyond the one `@property`. The Java/Maven review trigger (third pack) is the **only** sanctioned future widening path.
- **Conftest hygiene:** `_valid_pack(**overrides)` lives in `tests/unit/languages/conftest.py` (a pytest fixture pattern) so S1-04's `test_project_detector.py` and any later step-1 story can reuse the same stubs. Do NOT duplicate stub classes across test files — drift is the failure mode.
- This story is the canonical **Value Object + Make-Illegal-States-Unrepresentable** pattern (ADR-0001 §Pattern fit). The plugin-architecture / strategy-pattern opportunities live at the *registry* level (S2-01) and the *strategy-registry* level (S2-03 / S5-02..S5-04), not here. Resist any urge to add abstract base classes or extension hooks to `LanguagePack` itself — the value object's job is to *be a language*, not to know how to extend itself.
