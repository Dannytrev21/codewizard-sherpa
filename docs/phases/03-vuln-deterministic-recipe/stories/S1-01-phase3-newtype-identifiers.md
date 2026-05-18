# Story S1-01 — Phase 3 newtype identifiers + smart constructors

**Step:** Step 1 — Scaffold packages, domain primitives, sum types, and structural CI fences
**Status:** Ready
**Effort:** M
**Depends on:** —
**ADRs honored:** ADR-0010 (domain-modeling discipline — newtype every domain identifier), ADR-0001 (Phase-5 contract surface needs `AttemptNumber`, `WorkflowId`, `TransformId` already typed)

## Context

Production ADR-0033 commits the system to newtypes on every domain identifier; Phase 3 is the first phase where this discipline lands across a *plugin contract*, so the catalog of typed primitives must exist before any orchestrator, plugin, registry, recipe engine, event log, or scorer code references one. The critic flagged this in `critique.md §Design-pattern critiques §Missed patterns`: a `WorkflowId ↔ BundleId` swap at any call site is a runtime bug `mypy --strict` cannot catch when both are raw `str`. This story lands the 14 Phase-3-new newtypes and pairs each with a smart constructor returning `Result[T, ParseError]` so external-boundary parsers (YAML manifests, CVE feeds, branch-name validators) have one typed entry point per ID.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design C3` — `Concrete` carries a raw `str`; call sites wrap with the Phase-3 newtypes this story ships.
  - `../phase-arch-design.md §Component design C5` — `AttemptSummary.attempt: AttemptNumber`, `ApplyContext.workflow_id: WorkflowId`; S1-04 lands the models, this story lands the types they import.
  - `../phase-arch-design.md §Component design C4` — `TransformId = blake3(diff_bytes)` newtype.
  - `../phase-arch-design.md §Data model` and §Design patterns applied row 4 (Newtype pattern) — the catalog is exhaustive.
- **Phase ADRs:**
  - `../ADRs/0010-domain-modeling-discipline-scope-sum-type-and-newtypes.md` — names every newtype this story must land; smart-constructor convention; `BranchName.parse` regex `^[a-z0-9/_.-]+$`.
  - `../ADRs/0001-ship-phase5-contract-surface-by-name.md` — `_validate_stage6` consumers expect `WorkflowId`/`TransformId`/`AttemptNumber` already typed; Phase 5 amends behavior, not shape.
- **Production ADRs:**
  - `../../../production/adrs/0033-domain-modeling-discipline.md` — the parent rule this story instantiates for Phase 3.
- **Existing code:**
  - `src/codegenie/types/identifiers.py` — Phase 2's pattern (`NewType` + module-level `__all__` + docstring naming the owning ADR). Extend, don't rewrite.
  - `tests/unit/types/test_identifiers.py` and `test_identifiers_typecheck.py` — the established test shape for newtype round-trip + `mypy --strict` evidence. Mirror it for the Phase 3 additions.
  - `src/codegenie/probes/node_build_system.py` — precedent for an upstream-owned enum that `identifiers.py` re-exports rather than redefines (`PackageManager`); a related concern when adding `PackageId`/`PrimitiveName`.

## Goal

Extend `codegenie.types.identifiers` with the 14 Phase-3 newtypes and pair each one with a smart-constructor wrapper returning `Result[T, ParseError]`, so every later Step 1 story (and every downstream Phase 3 module) imports its typed primitives from one canonical home.

## Acceptance criteria

- [ ] `src/codegenie/types/identifiers.py` exports `PluginId`, `RecipeId`, `TransformId`, `WorkflowId`, `EventId`, `CveId`, `PackageId`, `BranchName`, `BlobDigest`, `RegistryUrl`, `SignalKind`, `PrimitiveName`, `TransformKind`, `AttemptNumber` — each `NewType(<Name>, str)` or `NewType(<Name>, int)` (only `AttemptNumber` is `int`).
- [ ] A `Result[T, ParseError]`-shaped helper module (`src/codegenie/types/result.py`) exists with `Ok[T]`, `Err[E]`, `Result: TypeAlias = Ok[T] | Err[E]`, `ParseError(message: str, value: str)` Pydantic model. (No 3rd-party `returns`/`result` dep; in-tree, ~30 LoC.)
- [ ] Smart constructors live in `src/codegenie/types/parsers.py`: `parse_workflow_id`, `parse_cve_id` (regex `^CVE-\d{4}-\d{4,}$`), `parse_branch_name` (regex `^[a-z0-9/_.-]+$`, length ≤ 200), `parse_blob_digest` (hex 64 chars), `parse_registry_url` (`https://` + host validation), `parse_attempt_number` (`> 0`), `parse_signal_kind` (`^[a-z][a-z0-9_]*$`), `parse_primitive_name`, `parse_transform_kind`, `parse_package_id` (`<name>@<semver>` with `name` per npm rules), `parse_plugin_id`/`parse_recipe_id`/`parse_transform_id`/`parse_event_id` (BLAKE3 hex or stable string per type). Each returns `Result[T, ParseError]`.
- [ ] `tests/unit/types/test_identifiers_phase3.py` covers: round-trip (input → `Ok` → `.value` → equality); rejection (each parser has ≥ 1 deliberate bad-input case → `Err` with `ParseError.value == the_bad_input`); cross-newtype substitution is a mypy error (use the `tests/unit/types/test_identifiers_typecheck.py` pattern — collect a `mypy` exit-code assertion).
- [ ] `mypy --strict src/codegenie/types/` clean; the new module is included in the existing strict surface.
- [ ] `ruff check`, `ruff format --check` clean on touched files.
- [ ] Module-level `__all__` is sorted; docstring on each newtype names ADR-0010 and the immediate Phase 3 consumer (e.g., `"# WorkflowId — landed for S1-04 ApplyContext + S6-04 RemediationOrchestrator."`).
- [ ] TDD plan's red test exists, committed, green.

## Implementation outline

1. Add `src/codegenie/types/result.py` with `Ok`/`Err`/`Result`/`ParseError`. Frozen Pydantic `ParseError`. `Ok`/`Err` as frozen `@dataclass(slots=True)` generics. (Keep it tiny — single file, no dependencies.)
2. Extend `src/codegenie/types/identifiers.py` with the 14 newtypes. Match the existing docstring convention (one comment block per type naming owning ADR + consumer).
3. Add `src/codegenie/types/parsers.py` with the 14 smart constructors. Each is a pure function: `def parse_<x>(s: str) -> Result[<X>, ParseError]: ...`.
4. Update `__all__` in `src/codegenie/types/identifiers.py` (sorted, includes the 14 new types).
5. Land `tests/unit/types/test_identifiers_phase3.py` mirroring `test_identifiers.py`: parametrized happy + sad paths for every parser; a static-typing test in the spirit of `test_identifiers_typecheck.py`.
6. Run `mypy --strict src/codegenie/types/` + `make check` locally.

## TDD plan — red / green / refactor

### Red — write the failing test first
Test file path: `tests/unit/types/test_identifiers_phase3.py`

```python
import pytest
from codegenie.types.identifiers import (
    PluginId, RecipeId, TransformId, WorkflowId, EventId, CveId,
    PackageId, BranchName, BlobDigest, RegistryUrl, SignalKind,
    PrimitiveName, TransformKind, AttemptNumber,
)
from codegenie.types.parsers import (
    parse_workflow_id, parse_cve_id, parse_branch_name,
    parse_blob_digest, parse_registry_url, parse_attempt_number,
    parse_signal_kind, parse_package_id,
)
from codegenie.types.result import Ok, Err, ParseError


def test_cve_id_happy_path():
    r = parse_cve_id("CVE-2024-21501")
    assert isinstance(r, Ok)
    assert r.value == CveId("CVE-2024-21501")


def test_cve_id_rejects_malformed():
    r = parse_cve_id("cve-2024-21501")  # lowercase
    assert isinstance(r, Err)
    assert r.error.value == "cve-2024-21501"


@pytest.mark.parametrize("bad", ["", "feature branch", "../escape", "A" * 201])
def test_branch_name_rejects(bad: str):
    assert isinstance(parse_branch_name(bad), Err)


def test_attempt_number_rejects_zero():
    assert isinstance(parse_attempt_number(0), Err)
```

State why it fails: `ImportError` — `codegenie.types.parsers` and `codegenie.types.result` don't exist; `ImportError` — the 14 new names are not in `identifiers.py`.

### Green — minimal pass
- Add `src/codegenie/types/result.py` with `Ok`, `Err`, `ParseError`, `Result` alias.
- Append the 14 `NewType` lines to `src/codegenie/types/identifiers.py`.
- Add `src/codegenie/types/parsers.py` with 14 `parse_<x>` functions returning `Result`. Each is the minimum regex + length check needed to make the test pass.

### Refactor
- Lift shared regex patterns to module-level `Final` constants with comment naming the spec (e.g., `_CVE_RX: Final = re.compile(r"^CVE-\d{4}-\d{4,}$")  # MITRE CVE ID format`).
- Docstring each parser with a one-liner naming its boundary (`"""External boundary: YAML plugin.yaml; ADR-0010."""`).
- Add type-checker negative case to `test_identifiers_typecheck.py` (or new `test_identifiers_phase3_typecheck.py`): `pid: PluginId = ...; rid: RecipeId = pid  # type: ignore[assignment]` and assert mypy reports the error.
- Edge cases from §Edge cases that touch this code: E20 — adversarial repo content (NUL bytes, zero-width) in identifiers. Add NFKC normalization + ASCII-only check inside `parse_package_id` and `parse_branch_name`; cover with adversarial input cases.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/types/identifiers.py` | Append 14 newtypes; update `__all__`. |
| `src/codegenie/types/result.py` | NEW — `Ok`/`Err`/`Result`/`ParseError`. |
| `src/codegenie/types/parsers.py` | NEW — 14 smart constructors. |
| `tests/unit/types/test_identifiers_phase3.py` | NEW — round-trip + rejection + adversarial. |
| `tests/unit/types/test_identifiers_typecheck.py` | Extend with cross-newtype substitution negative cases for Phase 3 types. |

## Out of scope

- **`PluginScope` parsing** — handled by S1-02 (uses `parse_plugin_id`, `parse_*` for dim values, but the scope sum type itself ships there).
- **`AttemptSummary` / `ApplyContext` Pydantic models** — handled by S1-04.
- **Tagged-union outcome types** — handled by S1-03.
- **Fence tests asserting no raw `str` for domain IDs** — handled by S1-05 (`test_no_any_in_plugin_surface.py` covers part; a dedicated `test_no_raw_str_for_domain_ids.py` is left as a follow-up per ADR-0010 §Consequences).
- **Pickling / serialization helpers** — Pydantic on consuming models handles this; no JSON encoders here.

## Notes for the implementer

- **Don't pull in `result`/`returns` third-party libs.** A 30-LoC in-tree `Result` is the right size; the runtime-closure fence will reject anything heavier (and Phase 0/1/2 code already follows this convention — check `src/codegenie/probes/` for existing internal `Result`-shaped returns).
- **`AttemptNumber` is `int`, not `str`.** Everything else in the 14 is `str`-backed.
- **`PackageId` is `<name>@<semver>` per npm**, not just `<name>`. The smart constructor must accept `lodash@4.17.21` and reject `lodash` (no version) or `LODASH@4.17.21` (name regex).
- **Match the existing docstring convention** in `identifiers.py` — each newtype block names the owning ADR and the immediate Phase-3 consumer story so future readers can trace why it exists.
- **`mypy --strict` is the bar, not pyright.** The repo has no pyright config; use mypy's `reveal_type` for diagnostic spot-checks during development.
- **`Result[T, ParseError]` matches the Phase 5 ADR-0006 convention referenced from ADR-0010.** If Phase 5 has already shipped a different `Result` shape, surface it and ask before duplicating — do not silently fork.
- **Existing `IndexName` / `SkillId` / `ConventionId` newtypes** (already in `identifiers.py`) are the convention to mirror — same `NewType("X", str)` shape, same docstring style, same `__all__` discipline.
