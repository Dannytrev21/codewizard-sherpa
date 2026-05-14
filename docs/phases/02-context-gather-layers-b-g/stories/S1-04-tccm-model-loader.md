# Story S1-04 — `TCCM` Pydantic model + `DerivedQuery` five variants + `TCCMLoader`

**Step:** Step 1 — Plant new domain primitives, kernel contracts, and the nine new ADRs
**Status:** Ready
**Effort:** M
**Depends on:** S1-01, S1-05
**ADRs honored:** 02-ADR-0007

## Context

Task-Class Context Manifests (TCCMs, production ADR-0029) declare what evidence a task class needs: required probes, required skills, derived queries (the five ADR-0030 primitives), and a confidence floor. Phase 2 ships the schema and a loader; Phase 8 ships the Bundle Builder that consumes them. The Phase-2 consumer is `docs/_reference-tccm/tccm.yaml` (S2-03), which exercises every field and is the proof the schema is shaped right before any plugin ships in Phase 3.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §"Component design" #8 — TCCMLoader` — public interface, internal structure, `safe_yaml` chokepoint route.
  - `../phase-arch-design.md §"Data model"` (lines `# ---------- [contract] codegenie/tccm/model.py ----------` and `# ---------- [contract] codegenie/tccm/queries.py ----------`) — exact field set and the five `DerivedQuery` primitives.
  - `../phase-arch-design.md §"Design patterns applied"` row 7 — TCCM under `docs/_reference-tccm/`, not `plugins/`.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0007-no-plugin-loader-in-phase-2.md` — 02-ADR-0007 — Phase 2 ships the TCCM schema; Phase 3 ships the loader's first real consumer (a plugin's `plugin.yaml` → TCCM).
- **Production ADRs (if applicable):**
  - `../../../production/adrs/0029-task-class-context-manifests.md` — production ADR-0029 — the manifest's purpose.
  - `../../../production/adrs/0030-derived-queries-five-primitives.md` — production ADR-0030 — the five `DerivedQuery` variants (`ConsumersOf`, `ProducersOf`, `ReverseLookup`, `RefsTo`, `TestsExercising`); **no `Unknown` variant**; ADR-amend on a sixth.
- **Source design:**
  - `../final-design.md §"Synthesis ledger" — TCCMLoader schema only, no Bundle Builder` — the deliberate Phase-2 scope.
- **Existing code:**
  - `src/codegenie/parsers/safe_yaml.py` — Phase 1 chokepoint; the loader routes through `safe_yaml.load`. Size + depth caps already enforced.
  - `src/codegenie/errors.py` — Phase 0/1 marker convention; `TCCMLoadError` is a new marker subclass.
  - `src/codegenie/adapters/confidence.py` (S1-03) — `AdapterConfidence` is the type of `TCCM.confidence_floor`.
  - `src/codegenie/types/identifiers.py` (S1-05) — `TaskClassId`, `SkillId`, `IndexName` newtypes used by `TCCM` fields.
- **External docs (only if directly relevant):**
  - https://docs.pydantic.dev/latest/concepts/unions/#discriminated-unions — discriminated-union shape for `DerivedQuery`.

## Goal

Implement `src/codegenie/tccm/{__init__.py,model.py,queries.py,loader.py}` — `TCCM` Pydantic `frozen=True, extra="forbid"` model, `DerivedQuery` as a five-variant Pydantic discriminated union (no `Unknown`), and `TCCMLoader.load(path) -> Result[TCCM, TCCMLoadError]` routing every YAML read through Phase 1's `codegenie.parsers.safe_yaml.load` chokepoint.

## Acceptance criteria

- [ ] **AC-1.** `src/codegenie/tccm/__init__.py` exports `TCCM`, `TCCMLoader`, `TCCMLoadError`, `DerivedQuery`, `ConsumersOf`, `ProducersOf`, `ReverseLookup`, `RefsTo`, `TestsExercising` via `__all__`.
- [ ] **AC-2.** `TCCM` model fields (Pydantic, `frozen=True, extra="forbid"`):
  - `schema_version: Literal["1"]`
  - `task_class: TaskClassId`
  - `required_probes: list[ProbeId]` (imports `ProbeId` from `codegenie.probes.base` per existing Phase 0/1 convention; if `ProbeId` is a `NewType` already, reuse — do not redefine)
  - `required_skills: list[SkillId]`
  - `derived_queries: list[DerivedQuery]`
  - `confidence_floor: AdapterConfidence`
- [ ] **AC-3.** `DerivedQuery` is `Annotated[Union[ConsumersOf, ProducersOf, ReverseLookup, RefsTo, TestsExercising], Field(discriminator="compute")]`. Each variant is Pydantic `frozen=True, extra="forbid"` with `compute: Literal["consumers_of" | "producers_of" | "reverse_lookup" | "refs_to" | "tests_exercising"]` discriminator and a single payload field appropriate to the primitive (e.g., `ConsumersOf.pkg: str`, `ReverseLookup.module: str`, `RefsTo.symbol: str`, `TestsExercising.symbol: str`). Field set comes from production ADR-0030.
- [ ] **AC-4.** `TCCMLoader.load(path: Path) -> Result[TCCM, TCCMLoadError]` returns:
  - `Result.Ok(tccm)` for a well-formed YAML.
  - `Result.Err(TCCMLoadError(reason="schema", ...))` for a Pydantic `ValidationError`.
  - `Result.Err(TCCMLoadError(reason="unknown_query_primitive", ...))` for an unrecognized `compute:` value on any `DerivedQuery`. The check happens via Pydantic's discriminator failure path; the loader translates the validation-error code into the `unknown_query_primitive` reason string for callers.
  - `Result.Err(TCCMLoadError(reason="parse", ...))` if `safe_yaml.load` raises `MalformedYAMLError` / `SizeCapExceeded` / `DepthCapExceeded` (Phase 1 markers).
- [ ] **AC-5.** Every file read goes through `codegenie.parsers.safe_yaml.load(path)` (Phase 1 chokepoint). The loader does **not** call `yaml.safe_load`, `yaml.load`, `Path.read_text`, or `open(path)` directly.
- [ ] **AC-6.** Round-trip identity: for every `DerivedQuery` variant, `model_dump_json` → `model_validate_json` returns an equal instance with the right concrete type (parametrized over all five).
- [ ] **AC-7.** A well-formed in-memory TCCM passes `model_dump` → `model_validate` round-trip; `confidence_floor` accepts each of the three `AdapterConfidence` variants.
- [ ] **AC-8.** Unknown `compute:` value (e.g., `compute: "implementations_of"`) produces `Result.Err(TCCMLoadError(reason="unknown_query_primitive"))` — verified via a small inline YAML string in the test.
- [ ] **AC-9.** `Result` is the Phase 0 `Result[T, E]` type if one exists; otherwise the loader returns `tuple[Optional[TCCM], Optional[TCCMLoadError]]` with mutually-exclusive nullability (one is always None). Pick whichever Phase 0/1 already established (check `codegenie/__init__.py`); document the choice in the loader's module docstring.
- [ ] **AC-10.** The TDD plan's red test exists, was committed, and is green.
- [ ] **AC-11.** `ruff check`, `ruff format --check`, `mypy --strict`, and `pytest tests/unit/tccm/` all pass on the touched files.

## Implementation outline

1. `src/codegenie/tccm/queries.py` — five `DerivedQuery` variant classes + the `Annotated[Union, Field(discriminator="compute")]` alias. Field names from production ADR-0030.
2. `src/codegenie/tccm/model.py` — `TCCM` model importing `AdapterConfidence` (S1-03), `TaskClassId`/`SkillId` (S1-05), `ProbeId` (Phase 0).
3. `src/codegenie/tccm/loader.py` — `TCCMLoader.load(path)` reads through `safe_yaml.load`; wraps `ValidationError` and the four `Malformed*` markers into `TCCMLoadError(reason=...)`.
4. `src/codegenie/tccm/__init__.py` — re-export.
5. `src/codegenie/errors.py` — append `TCCMLoadError` as a bare marker subclass of `CodegenieError`.
6. Red tests → impl → refactor.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/tccm/test_loader.py`

```python
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from codegenie.adapters import Trusted, Degraded
from codegenie.errors import TCCMLoadError
from codegenie.tccm import (
    ConsumersOf,
    DerivedQuery,
    ProducersOf,
    RefsTo,
    ReverseLookup,
    TCCM,
    TCCMLoader,
    TestsExercising,
)
from codegenie.types.identifiers import SkillId, TaskClassId


VALID_TCCM_YAML = textwrap.dedent(
    """
    schema_version: "1"
    task_class: "index-health-self-check"
    required_probes: ["index_health", "scip_index"]
    required_skills: ["scip.maintenance"]
    derived_queries:
      - compute: "consumers_of"
        pkg: "@org/payments"
      - compute: "producers_of"
        pkg: "@org/payments"
      - compute: "reverse_lookup"
        module: "src/payments/processor.ts"
      - compute: "refs_to"
        symbol: "PaymentProcessor.charge"
      - compute: "tests_exercising"
        symbol: "PaymentProcessor.charge"
    confidence_floor:
      kind: "trusted"
    """
)


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "tccm.yaml"
    p.write_text(body)
    return p


# AC-4, AC-5 — happy path through safe_yaml chokepoint
def test_load_happy_path(tmp_path: Path) -> None:
    path = _write(tmp_path, VALID_TCCM_YAML)
    loader = TCCMLoader()
    result = loader.load(path)
    # Pattern: Phase 0 Result[T, E] is_ok/unwrap or tuple[ok, err]; adapt to whichever shipped.
    assert result.is_ok(), repr(result)
    tccm = result.unwrap()
    assert tccm.schema_version == "1"
    assert tccm.task_class == TaskClassId("index-health-self-check")
    assert SkillId("scip.maintenance") in tccm.required_skills
    assert len(tccm.derived_queries) == 5
    # Every variant decoded to its concrete class.
    variant_types = {type(q) for q in tccm.derived_queries}
    assert variant_types == {ConsumersOf, ProducersOf, ReverseLookup, RefsTo, TestsExercising}


# AC-8 — unknown compute: → unknown_query_primitive
def test_load_unknown_compute(tmp_path: Path) -> None:
    bad = VALID_TCCM_YAML.replace("compute: \"consumers_of\"", "compute: \"implementations_of\"")
    path = _write(tmp_path, bad)
    result = TCCMLoader().load(path)
    assert result.is_err(), repr(result)
    err = result.unwrap_err()
    assert isinstance(err, TCCMLoadError)
    # Reason is encoded in the message string (markers-only convention per Phase 0/1).
    assert "unknown_query_primitive" in err.args[0]


# AC-4 — schema violation (missing required field)
def test_load_schema_violation(tmp_path: Path) -> None:
    bad = "schema_version: \"1\"\n"  # missing every required field
    path = _write(tmp_path, bad)
    result = TCCMLoader().load(path)
    assert result.is_err()
    err = result.unwrap_err()
    assert "schema" in err.args[0]


# AC-4 — malformed YAML routes through safe_yaml markers
def test_load_malformed_yaml(tmp_path: Path) -> None:
    path = _write(tmp_path, "schema_version: [unterminated")
    result = TCCMLoader().load(path)
    assert result.is_err()
    err = result.unwrap_err()
    assert "parse" in err.args[0]


# AC-5 — chokepoint usage: monkeypatch safe_yaml.load to assert it was called
def test_load_routes_through_safe_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from codegenie.parsers import safe_yaml as sy

    called: list[Path] = []
    original = sy.load
    def spy(path: Path, *args: object, **kwargs: object) -> object:
        called.append(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(sy, "load", spy)
    path = _write(tmp_path, VALID_TCCM_YAML)
    TCCMLoader().load(path)
    assert called == [path]


# AC-6 — round-trip identity per DerivedQuery variant
@pytest.mark.parametrize("q", [
    ConsumersOf(pkg="@org/p"),
    ProducersOf(pkg="@org/p"),
    ReverseLookup(module="src/x.ts"),
    RefsTo(symbol="Foo.bar"),
    TestsExercising(symbol="Foo.bar"),
])
def test_derived_query_roundtrip(q: "DerivedQuery") -> None:
    adapter = TypeAdapter(DerivedQuery)
    encoded = adapter.dump_json(q)
    decoded = adapter.validate_json(encoded)
    assert decoded == q
    assert type(decoded) is type(q)


# AC-7 — confidence_floor accepts each AdapterConfidence variant
def test_confidence_floor_variants(tmp_path: Path) -> None:
    body = VALID_TCCM_YAML.replace(
        "confidence_floor:\n      kind: \"trusted\"",
        "confidence_floor:\n      kind: \"degraded\"\n      reason: \"index_unavailable\"",
    )
    result = TCCMLoader().load(_write(tmp_path, body))
    assert result.is_ok()
    assert isinstance(result.unwrap().confidence_floor, Degraded)
```

Run — confirm `ImportError`. Commit.

### Green — make it pass

`queries.py` skeleton:

```python
from __future__ import annotations
from typing import Annotated, Literal, Union
from pydantic import BaseModel, ConfigDict, Field

class ConsumersOf(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    compute: Literal["consumers_of"] = "consumers_of"
    pkg: str

class ProducersOf(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    compute: Literal["producers_of"] = "producers_of"
    pkg: str

class ReverseLookup(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    compute: Literal["reverse_lookup"] = "reverse_lookup"
    module: str

class RefsTo(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    compute: Literal["refs_to"] = "refs_to"
    symbol: str

class TestsExercising(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    compute: Literal["tests_exercising"] = "tests_exercising"
    symbol: str

DerivedQuery = Annotated[
    Union[ConsumersOf, ProducersOf, ReverseLookup, RefsTo, TestsExercising],
    Field(discriminator="compute"),
]
```

`model.py` skeleton:

```python
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, ConfigDict
from codegenie.adapters import AdapterConfidence
from codegenie.tccm.queries import DerivedQuery
from codegenie.types.identifiers import SkillId, TaskClassId
# ProbeId comes from Phase 0/1; if it's a NewType("ProbeId", str), import as-is.
from codegenie.probes.base import Probe as _Probe  # ProbeId might live elsewhere — adapt at impl time

ProbeId = str  # adapt at impl time; align with Phase 0/1's existing identifier story

class TCCM(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal["1"]
    task_class: TaskClassId
    required_probes: list[ProbeId]
    required_skills: list[SkillId]
    derived_queries: list[DerivedQuery]
    confidence_floor: AdapterConfidence
```

`loader.py` skeleton: read via `safe_yaml.load`; route `MalformedYAMLError`/`SizeCapExceeded`/`DepthCapExceeded` → `reason="parse"`; on `ValidationError`, examine `e.errors()[0]["type"]` — if any error has `type == "union_tag_invalid"` or `"literal_error"` and the loc ends in `("compute",)`, set `reason="unknown_query_primitive"`; otherwise `reason="schema"`. The translation table is part of the loader docstring.

```python
# src/codegenie/tccm/loader.py — sketch
from __future__ import annotations
from pathlib import Path

from pydantic import ValidationError

from codegenie.errors import (
    DepthCapExceeded, MalformedYAMLError, SizeCapExceeded, TCCMLoadError,
)
from codegenie.parsers import safe_yaml
from codegenie.tccm.model import TCCM
# Result type: import the Phase 0/1 idiom — adapt to whatever shipped.
from codegenie._result import Result, Ok, Err  # adapt module path

class TCCMLoader:
    def load(self, path: Path) -> Result[TCCM, TCCMLoadError]:
        try:
            data = safe_yaml.load(path)
        except (MalformedYAMLError, SizeCapExceeded, DepthCapExceeded) as exc:
            return Err(TCCMLoadError(f"parse: {exc.args[0] if exc.args else type(exc).__name__}"))
        try:
            return Ok(TCCM.model_validate(data))
        except ValidationError as ve:
            reason = "schema"
            for e in ve.errors():
                if e.get("type") in {"union_tag_invalid", "literal_error"} and e.get("loc", (None,))[-1] == "compute":
                    reason = "unknown_query_primitive"
                    break
            return Err(TCCMLoadError(f"{reason}: {ve.errors()[0]}"))
```

Add `TCCMLoadError` to `errors.py` as a marker (no `__init__`, docstring names the loader and the four reasons: `parse`, `schema`, `unknown_query_primitive`).

### Refactor — clean up

- Module docstrings: `loader.py` names the four `reason` strings as the public contract; future contributors must extend by amending the table, not by adding ad-hoc reasons.
- Confirm `model_construct` is not used anywhere (S1-11's `forbidden-patterns` on `codegenie/tccm/**` will enforce; do not regress).
- The loader does **not** log secrets; per Phase 0 audit anchor, every TCCM load emits `tccm.load.ok` or `tccm.load.err` with the reason (one log-emission assertion test).
- Run `ruff format`, `ruff check`, `mypy --strict src/codegenie/tccm/ tests/unit/tccm/`, `pytest tests/unit/tccm/ -v`.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/tccm/__init__.py` | New package; re-export the surface. |
| `src/codegenie/tccm/model.py` | `TCCM` Pydantic model. |
| `src/codegenie/tccm/queries.py` | Five `DerivedQuery` variants + the Annotated union. |
| `src/codegenie/tccm/loader.py` | `TCCMLoader` over `safe_yaml.load`. |
| `src/codegenie/errors.py` | Append `TCCMLoadError` marker; extend `__all__`. |
| `tests/unit/tccm/test_loader.py` | Coverage: happy, unknown compute, schema violation, parse error, chokepoint usage. |
| `tests/unit/tccm/test_queries.py` | Round-trip identity per `DerivedQuery` variant. |

## Out of scope

- **Reference TCCM at `docs/_reference-tccm/tccm.yaml` + integration roundtrip** — handled by S2-03.
- **Bundle Builder / Hierarchical Planner** — Phase 8.
- **Plugin Loader / `plugin.yaml` parser** — Phase 3; this story ships the TCCM schema only.
- **Sixth `DerivedQuery` variant** — explicitly out per production ADR-0030; ADR-amend required if Phase 3 discovers a sixth primitive.
- **`TCCM.required_probes` runtime-checked against the actual probe registry** — Phase 3+ concern.
- **Hashed body / progressive-disclosure for the manifest itself** — manifests are small (< 10 KB); `safe_yaml` caps already enforce.

## Notes for the implementer

- **`Result[T, E]` shape — match the Phase 0/1 idiom.** Phase 1 stories use a `Result` type for parser failures. Inspect `src/codegenie/` to find the exact module (likely `codegenie._result` or `codegenie.parsers.result`); the test uses `.is_ok()`, `.is_err()`, `.unwrap()`, `.unwrap_err()` — adapt the test if the existing API differs.
- **`ProbeId` source.** If Phase 0 already declares `ProbeId = NewType("ProbeId", str)`, import it (likely from `codegenie.probes.base` or `codegenie.probes.registry`). If it doesn't yet exist, declare it locally in `tccm/model.py` as `ProbeId = str` and file a follow-up — but do NOT redefine if it already exists (Rule 11).
- **`unknown_query_primitive` translation is brittle.** Pydantic v2 error codes (`union_tag_invalid`, `literal_error`) may shift across minor versions. The test pins behavior; the loader docstring documents the translation table. If pydantic upgrades break the test, this is the regression site — fix the translation, not the test (Rule 12 — fail loud).
- **`safe_yaml.load` is the *only* file-read path.** Do not import `yaml`, do not call `Path.read_text`. The chokepoint is the Phase 1 commitment; tests verify (`test_load_routes_through_safe_yaml`).
- **Markers-only invariant.** `TCCMLoadError` is a bare marker (no `__init__`, no class attributes), exactly like `MalformedYAMLError` / `CatalogLoadError` from Phase 1. Reason strings live in `args[0]`; the loader emits stable identifiers (`parse`, `schema`, `unknown_query_primitive`). Consumers parse the prefix; do not invent a structured `.reason` attribute.
- **`schema_version: Literal["1"]` is the upgrade door.** A future TCCM v2 would add `schema_version: Literal["1", "2"]` and the loader would dispatch internally. Do not invent `TCCMSchemaV1` / `TCCMSchemaV2` classes preemptively (Rule 2 — Simplicity First).
- **Five variants, no `Unknown`.** Resist `class UnknownQuery(BaseModel): compute: str` as a "graceful degradation" fallback. The whole point of the discriminator is that unknown `compute` values are loader errors, not data-model variants (production ADR-0030 §Consequences).
