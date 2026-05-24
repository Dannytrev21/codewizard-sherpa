# Story S1-03 — `PlanOutcome` wraps `RecipeOutcome`

**Step:** Step 1 — Establish Phase-4 type substrate + path-scoped fence amendment
**Status:** Done — 2026-05-24 (phase-story-executor; see [`_attempts/S1-03.md`](_attempts/S1-03.md) for the per-AC evidence table + gate log — Phase-4 `PlanOutcome` closed Pydantic-v2 discriminated union landed with four variants (`AppliedFromRecipe`, `AppliedFromLlm`, `RagOnlyApplicable`, `Refused`), the load-bearing widening fence (`test_plan_outcome_no_recipe_outcome_widening.py`) asserting the Phase-3 `RecipeOutcome` variant set is byte-identical to the four-line snapshot, the F6 attribute-read mypy-negative test, and the F5 exhaustiveness meta-test. Story-scoped gates green: 25 story tests + 67 sibling fences + `mypy --strict src/codegenie/fallback/` + `make typecheck` (209 files) + `make fence` (379 tests) + `make lint-imports` (6 kept).)
**Effort:** S
**Depends on:** S1-01
**ADRs honored:** ADR-0004 (`PlanOutcome` is Phase-4-LOCAL; Phase-3 `RecipeOutcome` is NOT widened), ADR-0001 (`AppliedFromLlm` references `LeafResponseId` + `SolvedExampleId` from the newtype catalog)

## Validation notes

Validated: 2026-05-21
Verdict: HARDENED
Findings addressed: 12 — 6 blocks, 5 hardens, 1 nit.

Changes applied:
- **F1 (block)** — Wrong source location. The story said the Phase-3 `RecipeOutcome` definition is "likely under `src/codegenie/plugins/protocols.py`" and the fence test imported `from codegenie.plugins.protocols import RecipeOutcome`. Grep-verified 2026-05-21: `RecipeOutcome` is declared in **`src/codegenie/transforms/outcomes.py`** (re-exported from `codegenie.transforms`). `codegenie.plugins.protocols` exists but does not export it. References, AC-6, the TDD code, the implementation outline, and Notes corrected to the real path.
- **F2 (block)** — Wrong variant names. The story (and ADR-0004, and `phase-arch-design.md`) say `RecipeOutcome = Applied | Skipped | Failed` — **three** variants. The real declaration is `Annotated[Applied | Skipped | RecipeNotApplicable | RecipeFailed, Field(discriminator="kind")]` — **four**: `Applied`, `Skipped`, `RecipeNotApplicable`, `RecipeFailed`. AC-7's snapshot content, the implementation outline, and the Green steps now carry the four verified class names (sorted: `Applied`, `RecipeFailed`, `RecipeNotApplicable`, `Skipped`). ADR-0004 and the arch doc are stale on this point — recommend correction (not edited by this validator — out of scope).
- **F3 (block)** — `inspect.getfile(RecipeOutcome)` raises `TypeError`. `RecipeOutcome` is an `Annotated[...]` alias — a typing special form, not a module / class / function / code object — so `inspect.getfile` cannot resolve it. AC-6 + the TDD code now resolve the source path via `pathlib.Path(codegenie.transforms.outcomes.__file__)`.
- **F4 (block)** — Discriminator idiom. AC-3, the implementation outline, and Notes prescribed `Annotated[..., Discriminator("kind")]`, while AC-3 simultaneously said "must match S1-02's `PlanProposal` shape" — and S1-02 (HARDENED, same family) settled on `Field(discriminator="kind")`. Every umbrella in `codegenie/transforms/outcomes.py` uses `Field(discriminator="kind")`; the `transforms` package docstring calls it "the single repo convention". Rewritten to `Field(discriminator="kind")` throughout (Rule 11). The arch doc + ADR-0004 show `Discriminator("kind")` — the same transcription error S1-02's F2 flagged.
- **F5 (block)** — `tests/property/test_plan_outcome_match_exhaustive.py` asserted only `res.returncode != 0`. A mypy run that fails for an unrelated reason (import resolution, missing stubs) green-washes the test while proving nothing about exhaustiveness. Rewritten to mirror the **HARDENED** S1-02 pattern: assert a `{assert_never, unreachable, missing}` substring on stdout, add `pytest.importorskip("mypy")`, and add the complete-match positive case.
- **F6 (block)** — AC-5's mypy-negative test routed through the Pydantic **constructor** (`AppliedFromLlm(response_id=BudgetTokenId(...))`). This repo does **not** enable the `pydantic.mypy` plugin (`[tool.mypy]` carries no `plugins=`), so `BaseModel.__init__(**data: Any)` is unchecked and mypy would accept the wrong newtype — a false pass. Rewritten to the plugin-independent **attribute-read** idiom (`wrong: SolvedExampleId = m.response_id`), which mypy checks directly from the class-body annotation.
- **F7 (harden)** — `test_discriminator_routes` asserted only `isinstance`; an implementation that routes correctly but drops or defaults a field passed. Now asserts every non-`kind` input field survives onto the routed object.
- **F8 (harden)** — added a JSON round-trip identity property over all four variants — catches asymmetric serializer/deserializer bugs.
- **F9 (harden)** — added AC-11 + a test asserting `TypeAdapter(PlanOutcome).json_schema()` discriminator mapping is **exactly** `{recipe, llm, rag_only, refused}` (strict set equality). A fast runtime guard against a smuggled fifth variant, complementary to AC-9's slower subprocess-mypy meta-test. Mirrors S1-02's `test_schema_lists_exactly_four_tags`.
- **F10 (harden)** — AC-1 now requires each `kind` discriminator to carry a default matching its tag (arch §Data model shows `kind: Literal["llm"] = "llm"`). Without the default, direct construction in the meta-tests must pass `kind=` everywhere.
- **F11 (harden)** — the widening-fence AST walk handled only `ast.Assign`. It now also handles `ast.AnnAssign` (`RecipeOutcome: TypeAlias = ...`), so a future Phase-3 refactor adding an explicit alias annotation cannot silently make the fence unable to locate the declaration.
- **F12 (nit)** — Notes: lift `ConfigDict(frozen=True, extra="forbid")` to a module-level `_FROZEN_FORBID: Final` constant referenced by all four variants — matches S1-02's `fallback/` convention (single-source the config). Files-to-touch gains `tests/unit/fallback/__init__.py` (NEW if absent) so the story is self-contained.

Full audit log: docs/phases/04-vuln-llm-fallback-rag/stories/_validation/S1-03-plan-outcome-wraps-recipe-outcome.md

## Context

Phase 7's load-bearing exit criterion (`docs/roadmap.md §Phase 7`) is that "the diff touches only the new plugin directory" — Phase 7 must not edit `case` arms in Phase 3 / 4 / 5 / 6 files. ADR-0004's response to the best-practices-lens design (which proposed widening Phase 3's `RecipeOutcome` with `MatchedFromRag | ReplannedByLlm`) is to introduce a Phase-4-LOCAL `PlanOutcome` sum type that *wraps* `RecipeOutcome` instead of widening it. `FallbackTier.run` continues returning the Phase-3 `RecipeApplication`; `PlanOutcome` is consumed only by event emission and the inline harvester. The load-bearing assurance is `tests/property/test_plan_outcome_no_recipe_outcome_widening.py` — an AST walk that asserts `RecipeOutcome`'s variant list is **byte-identical** to the Phase-3 snapshot, inherited by every future phase.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — PlanOutcome (Component 13)` — variant declarations + the "consumed only by event emission and inline harvester" framing.
  - `../phase-arch-design.md §Data model` — `AppliedFromRecipe | AppliedFromLlm | RagOnlyApplicable | Refused` Pydantic shapes.
  - `../phase-arch-design.md §Goals — G3` — "Zero edits to Phase 0/1/2/3 kernel files."
  - `../phase-arch-design.md §Testing strategy → Property tests` — `test_plan_outcome_no_recipe_outcome_widening.py`.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0004-plan-outcome-wraps-recipe-outcome.md` — composition-over-union-widening; AST-walk-asserts variant list stays frozen.
  - `../ADRs/0001-plan-proposal-closed-sum-type.md` — `AppliedFromLlm.response_id: LeafResponseId` reuses the closed-sum identity from S1-01.
- **Production ADRs:**
  - `../../../production/adrs/0031-plugin-architecture.md` — Phase 7's distroless plugin convention; the "extension by addition" rule is what ADR-0004 protects.
  - `../../../production/adrs/0033-domain-modeling-discipline.md` — sum types as a discipline.
- **Source design:**
  - `../final-design.md §Component 14 — PlanOutcome` — wrapping pattern; `tests/property/test_plan_outcome_no_recipe_outcome_widening.py` is the load-bearing fence.
  - `../final-design.md §Departures from all three inputs` item 1 — why this departs from the best-practices-lens proposal.
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - Phase 3's `RecipeOutcome` definition lives at **`src/codegenie/transforms/outcomes.py`** (verified 2026-05-21 — re-exported from `codegenie.transforms.__init__`; **not** `codegenie.plugins.protocols`, F1). The canonical declaration is `RecipeOutcome = Annotated[Applied | Skipped | RecipeNotApplicable | RecipeFailed, Field(discriminator="kind")]` — **four** variant classes (F2). This story's AST walk + snapshot depend on this declaration; re-read the file per Rule 8 to confirm it has not drifted.
  - `RecipeApplication` is Phase-3-owned; this story does NOT introduce a Phase-4 variant of it. Re-use the import.
  - **Discriminated-union idiom is settled — `Field(discriminator="kind")`** (F4). Every umbrella in `codegenie/transforms/outcomes.py` (`RecipeOutcome`, `RemediationOutcome`, `NodeTransition`, `AdapterConfidence`, `Applicability`) and the HARDENED sibling `plan_proposal.py` use `Annotated[A | B | C, Field(discriminator="kind")]`. The `transforms` package docstring names it "the single repo convention". Do **not** use `Discriminator("kind")` — the arch doc + ADR-0004 show it, but that is a known transcription error (S1-02 F2).

## Goal

Ship the Phase-4-LOCAL `PlanOutcome` Pydantic v2 discriminated union (`AppliedFromRecipe | AppliedFromLlm | RagOnlyApplicable | Refused`) at `src/codegenie/fallback/plan_outcome.py`, and land `tests/property/test_plan_outcome_no_recipe_outcome_widening.py` — the AST-walk fence asserting Phase-3 `RecipeOutcome` variant list is byte-identical to its snapshot.

## Acceptance criteria

- [ ] AC-1 — `src/codegenie/fallback/plan_outcome.py` ships four `BaseModel` subclasses (`AppliedFromRecipe`, `AppliedFromLlm`, `RagOnlyApplicable`, `Refused`), all `model_config = ConfigDict(frozen=True, extra="forbid")`. Each carries a `kind: Literal[<tag>]` discriminator field **with a default matching the tag** (e.g. `kind: Literal["llm"] = "llm"` — arch §Data model shows the default; without it, direct construction in the meta-tests below would have to pass `kind=` at every call site). (validator: added the default requirement — F10.)
- [ ] AC-2 — Variant fields per arch §Data model:
  - `AppliedFromRecipe`: `kind: Literal["recipe"]`, `recipe_outcome_digest: BlobDigest`. (Phase-3 `RecipeOutcome.Applied` is referenced by BLAKE3 digest; the wrap does not embed the foreign instance.)
  - `AppliedFromLlm`: `kind: Literal["llm"]`, `recipe_outcome_digest: BlobDigest`, `few_shot_ref: SolvedExampleId | None`, `response_id: LeafResponseId`.
  - `RagOnlyApplicable`: `kind: Literal["rag_only"]`, `few_shot_ref: SolvedExampleId`.
  - `Refused`: `kind: Literal["refused"]`, `reason: Literal["PROVENANCE_NOT_APP_LAYER", "BUDGET_EXCEEDED", "LEAF_REFUSED", "LEAF_SCHEMA_VIOLATION"]`.
- [ ] AC-3 — `PlanOutcome = Annotated[AppliedFromRecipe | AppliedFromLlm | RagOnlyApplicable | Refused, Field(discriminator="kind")]` is exported. The `Field(discriminator="kind")` idiom is used — it is the codebase-wide convention for discriminated unions (every umbrella in `codegenie/transforms/outcomes.py`, plus `indices/freshness.py`, `probes/_shared/scanner_outcome.py`, and the HARDENED sibling `plan_proposal.py`) and Rule 11 mandates conformance. The `Discriminator("kind")` callable form is **not** used (it exists for callable discriminators, which this story does not need). This matches S1-02's `PlanProposal` shape exactly — consistent across `fallback/`. (validator: rewritten — F4; the arch doc + ADR-0004 show `Discriminator("kind")`, a known transcription error first flagged by S1-02's F2.)
- [ ] AC-4 — `tests/unit/fallback/test_plan_outcome.py` covers happy + sad paths:
  - Happy: each variant constructs from valid input; `TypeAdapter(PlanOutcome).validate_python(...)` routes by discriminator.
  - Sad — unknown `kind` value rejected.
  - Sad — `extra="forbid"` rejects unknown keys.
  - Sad — `frozen=True` rejects assignment.
  - Sad — `Refused.reason` outside the four-literal set rejected.
  - Sad — `AppliedFromLlm.response_id` typed as `LeafResponseId`; passing a raw `str` is allowed at runtime (NewType is identity) but the mypy negative test below proves the static rejection.
- [ ] AC-5 — **Field-type mypy discipline (`tests/unit/types/test_plan_outcome_field_types_mypy_negative.py`).** This repo does **not** enable the `pydantic.mypy` plugin (`[tool.mypy]` carries no `plugins=`), so `BaseModel.__init__(**data: Any)` is unchecked — a negative test routed through the *constructor* (`AppliedFromLlm(response_id=BudgetTokenId(...))`) would false-pass. The test instead exercises the **field annotation via attribute read**, which `mypy --strict` checks plugin-independently from the class body:
  - `response_id` — `def _r(m: AppliedFromLlm) -> None: wrong: SolvedExampleId = m.response_id` is a type error (`m.response_id` is `LeafResponseId`).
  - `few_shot_ref` — `wrong: LeafResponseId = m.few_shot_ref` is a type error (`m.few_shot_ref` is `SolvedExampleId | None`).
  Each parametrized case subprocess-invokes `mypy --strict`, asserts non-zero exit **and** an `incompatible type` / `assignment` diagnostic on stdout (asserting only `returncode != 0` green-washes on unrelated mypy errors). `pytest.importorskip("mypy")`. (validator: rewritten — F6; the original constructor-based mechanism cannot work without the pydantic mypy plugin.)
- [ ] AC-6 — **Load-bearing fence: `tests/property/test_plan_outcome_no_recipe_outcome_widening.py`** asserts Phase-3 `RecipeOutcome`'s variant **class-name set** is **exactly** the snapshot stored as `tests/property/_recipe_outcome_phase3_snapshot.txt` (one class name per line). Test:
  - Resolves the Phase-3 source path via `pathlib.Path(codegenie.transforms.outcomes.__file__)` — **not** `inspect.getfile(RecipeOutcome)`: `RecipeOutcome` is an `Annotated[...]` alias (a typing special form), and `inspect.getfile` raises `TypeError` on it (F3). The canonical home is `codegenie.transforms.outcomes` (F1).
  - AST-walks that module for the `RecipeOutcome = Annotated[A | B | C | D, Field(discriminator="kind")]` declaration, handling both `ast.Assign` and `ast.AnnAssign` targets (F11).
  - Extracts the union member class names from inside the `Annotated[...]` (the union is the first `Annotated` arg).
  - Loads `tests/property/_recipe_outcome_phase3_snapshot.txt` and asserts the two sets are equal.
  - On mismatch the failure message contains `"RecipeOutcome variants drifted from Phase-3 snapshot — Phase 7's exit criterion is at risk; see ADR-0004"`.
- [ ] AC-7 — The snapshot file `tests/property/_recipe_outcome_phase3_snapshot.txt` is committed with the canonical Phase-3 `RecipeOutcome` variant **class names**, one per line, sorted. Verified against `src/codegenie/transforms/outcomes.py` on 2026-05-21, the four names are exactly:
  ```
  Applied
  RecipeFailed
  RecipeNotApplicable
  Skipped
  ```
  Re-verify against the current source per Rule 8 before committing — the executor must read `outcomes.py`, not trust this list blindly. (ADR-0004 and `phase-arch-design.md` say `Applied | Skipped | Failed`, which is **stale/wrong** — F2; recommend correcting those docs.)
- [ ] AC-8 — `PlanOutcome` is exported from `src/codegenie/fallback/__init__.py`.
- [ ] AC-9 — **`assert_never` exhaustiveness via subprocess mypy** (`tests/property/test_plan_outcome_match_exhaustive.py`): mirror the **HARDENED** S1-02 `test_plan_proposal_match_exhaustive.py` over the four `PlanOutcome` variants:
  - Each parametrized incomplete-match file fails `mypy --strict` with **both** a non-zero exit **and** an exhaustiveness diagnostic on stdout — at least one of `assert_never`, `unreachable`, `missing`. Asserting only `returncode != 0` green-washes when mypy fails for an unrelated reason (import resolution, missing stubs) — F5.
  - The complete-match file (all four arms + `case _ as never: assert_never(never)`) passes `mypy --strict` with no `error:` on stdout.
  - `pytest.importorskip("mypy")` — a missing mypy install surfaces as a skip, not a confusing pass/fail. (validator: hardened — F5.)
- [ ] AC-10 — `mypy --strict src/codegenie/fallback/` clean. `ruff check`, `ruff format --check` clean. The TDD plan's red tests exist, are committed, and are green.
- [ ] AC-11 — **`PlanOutcome` discriminator-mapping totality** — a test in `tests/unit/fallback/test_plan_outcome.py` asserts `TypeAdapter(PlanOutcome).json_schema()["discriminator"]["mapping"]` has key set **exactly** `{"recipe", "llm", "rag_only", "refused"}` (strict `set(...) ==`, no `len(...) == 4` escape hatch — four wrong tags, or four canonical plus a spurious fifth, must fail). A fast runtime guard complementary to AC-9's slower subprocess-mypy meta-test. (validator: added — F9; mirrors S1-02's `test_schema_lists_exactly_four_tags`.)

## Implementation outline

1. Read `src/codegenie/transforms/outcomes.py` (per Rule 8); confirm the `RecipeOutcome` variant class names.
2. Create `tests/property/_recipe_outcome_phase3_snapshot.txt` — one variant class name per line, sorted: `Applied`, `RecipeFailed`, `RecipeNotApplicable`, `Skipped` (verified 2026-05-21; confirm against the source).
3. Create `src/codegenie/fallback/plan_outcome.py` with four `BaseModel` subclasses + `PlanOutcome = Annotated[..., Field(discriminator="kind")]` (the codebase idiom — F4; **not** `Discriminator("kind")`).
4. Export `PlanOutcome` + the four variants from `src/codegenie/fallback/__init__.py`.
5. Write `tests/unit/fallback/test_plan_outcome.py`: happy + sad paths + round-trip + discriminator-mapping totality.
6. Write `tests/property/test_plan_outcome_no_recipe_outcome_widening.py`: AST-walk the `codegenie.transforms.outcomes` module (resolved via `.__file__`) for the `RecipeOutcome` declaration, compare against the snapshot.
7. Write `tests/property/test_plan_outcome_match_exhaustive.py`: subprocess mypy meta-test mirroring the HARDENED S1-02 (stdout markers + `importorskip` + complete-match).
8. Add `tests/unit/types/test_plan_outcome_field_types_mypy_negative.py` — subprocess `mypy --strict` field-annotation checks via attribute read (F6); do **not** route through the Pydantic constructor (no `pydantic.mypy` plugin in this repo).
9. Run `mypy --strict src/codegenie/fallback/` + `make check`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/fallback/test_plan_outcome.py`

```python
from __future__ import annotations

import json

import pytest
from pydantic import TypeAdapter, ValidationError

from codegenie.fallback.plan_outcome import (
    AppliedFromLlm,
    AppliedFromRecipe,
    PlanOutcome,
    RagOnlyApplicable,
    Refused,
)
from codegenie.types.identifiers import BlobDigest, LeafResponseId, SolvedExampleId


GOOD_DIGEST = "a" * 64
GOOD_SEX_ID = "b" * 64
GOOD_RESP_ID = "msg_01ABCDEFGHIJKLMNOPQRSTUV"

VALID_RECIPE = {"kind": "recipe", "recipe_outcome_digest": GOOD_DIGEST}
VALID_LLM = {
    "kind": "llm",
    "recipe_outcome_digest": GOOD_DIGEST,
    "few_shot_ref": GOOD_SEX_ID,
    "response_id": GOOD_RESP_ID,
}
VALID_RAG = {"kind": "rag_only", "few_shot_ref": GOOD_SEX_ID}
VALID_REFUSED = {"kind": "refused", "reason": "PROVENANCE_NOT_APP_LAYER"}


@pytest.mark.parametrize(
    "payload,cls",
    [
        (VALID_RECIPE, AppliedFromRecipe),
        (VALID_LLM, AppliedFromLlm),
        (VALID_RAG, RagOnlyApplicable),
        (VALID_REFUSED, Refused),
    ],
)
def test_discriminator_routes(payload: dict[str, object], cls: type[object]) -> None:
    # F7 — assert the routed class AND that every input field survived. An impl
    # that routes correctly but drops/defaults a field must fail here.
    out = TypeAdapter(PlanOutcome).validate_python(payload)
    assert isinstance(out, cls)
    for key, value in payload.items():
        assert getattr(out, key) == value, f"field {key} not preserved"


@pytest.mark.parametrize(
    "payload", [VALID_RECIPE, VALID_LLM, VALID_RAG, VALID_REFUSED]
)
def test_json_round_trip_identity(payload: dict[str, object]) -> None:
    # F8 — every variant survives a model_dump -> json -> model_validate cycle.
    adapter = TypeAdapter(PlanOutcome)
    obj = adapter.validate_python(payload)
    again = adapter.validate_python(json.loads(json.dumps(obj.model_dump(mode="json"))))
    assert again == obj


def test_discriminator_mapping_is_exactly_four_tags() -> None:
    # F9 / AC-11 — strict set equality; a fifth variant or a wrong tag fails.
    schema = TypeAdapter(PlanOutcome).json_schema()
    mapping = schema.get("discriminator", {}).get("mapping", {})
    assert set(mapping) == {"recipe", "llm", "rag_only", "refused"}, (
        f"discriminator mapping must be exactly the four tags; got {set(mapping)}"
    )


def test_unknown_kind_rejected():
    adapter = TypeAdapter(PlanOutcome)
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "applied_from_void"})


def test_extra_keys_rejected():
    with pytest.raises(ValidationError):
        AppliedFromRecipe.model_validate({**VALID_RECIPE, "shell": "rm"})


def test_frozen_immutable():
    m = AppliedFromLlm.model_validate(VALID_LLM)
    with pytest.raises(ValidationError):
        m.response_id = "other"  # type: ignore[misc]


def test_refused_reason_literal():
    with pytest.raises(ValidationError):
        Refused.model_validate({"kind": "refused", "reason": "NOT_IN_THE_LITERAL"})


def test_few_shot_ref_optional_on_llm():
    m = AppliedFromLlm.model_validate({**VALID_LLM, "few_shot_ref": None})
    assert m.few_shot_ref is None


def test_few_shot_ref_required_on_rag_only():
    with pytest.raises(ValidationError):
        RagOnlyApplicable.model_validate({"kind": "rag_only"})
```

The load-bearing fence:

```python
# tests/property/test_plan_outcome_no_recipe_outcome_widening.py
"""ADR-0004 + Phase-7 exit-criterion fence: Phase-3 RecipeOutcome must not widen.

Inherited by every future phase. If this test fails, the introducing PR has
silently broken the 'extension by addition' invariant — Phase 7's plugin diff
would need new `case` arms in Phase-3/4/5/6 code.
"""
from __future__ import annotations

import ast
import pathlib

# Canonical Phase-3 home of RecipeOutcome (verified 2026-05-21). The module is
# imported (not the RecipeOutcome value) so its file path is resolvable via
# .__file__ — RecipeOutcome is an Annotated[...] alias and inspect.getfile()
# raises TypeError on it (F3).
import codegenie.transforms.outcomes as _recipe_outcome_mod


SNAPSHOT = pathlib.Path(__file__).parent / "_recipe_outcome_phase3_snapshot.txt"


def _extract_variant_names_from_module(mod_path: pathlib.Path) -> set[str]:
    """Return the set of variant class names that compose RecipeOutcome.

    Handles both `RecipeOutcome = A | B | C` (ast.Assign) and an annotated
    `RecipeOutcome: TypeAlias = A | B | C` (ast.AnnAssign), with the RHS being
    either a bare union or `Annotated[A | B | C, Field(...)/Discriminator(...)]`.
    """
    tree = ast.parse(mod_path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "RecipeOutcome" for t in node.targets
        ):
            return _names_from_union_or_annotated(node.value)
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "RecipeOutcome"
            and node.value is not None
        ):
            return _names_from_union_or_annotated(node.value)
    raise AssertionError("RecipeOutcome declaration not found in expected module")


def _names_from_union_or_annotated(value: ast.AST) -> set[str]:
    # Unwrap Annotated[X | Y | Z, Discriminator(...)] → take the first arg
    if (
        isinstance(value, ast.Subscript)
        and isinstance(value.value, ast.Name)
        and value.value.id == "Annotated"
    ):
        inner = value.slice.elts[0] if isinstance(value.slice, ast.Tuple) else value.slice
        return _names_from_union_or_annotated(inner)
    # Recurse over `A | B`
    if isinstance(value, ast.BinOp) and isinstance(value.op, ast.BitOr):
        return _names_from_union_or_annotated(value.left) | _names_from_union_or_annotated(value.right)
    if isinstance(value, ast.Name):
        return {value.id}
    raise AssertionError(f"Unrecognized RecipeOutcome RHS shape: {ast.dump(value)}")


def test_recipe_outcome_variants_match_phase3_snapshot() -> None:
    snapshot = {line.strip() for line in SNAPSHOT.read_text().splitlines() if line.strip()}
    # F3 — resolve the source file via the module's __file__, NOT
    # inspect.getfile(RecipeOutcome): RecipeOutcome is an Annotated[...] alias
    # and inspect.getfile raises TypeError on a typing special form.
    mod_path = pathlib.Path(_recipe_outcome_mod.__file__)
    found = _extract_variant_names_from_module(mod_path)
    assert found == snapshot, (
        f"RecipeOutcome variants drifted from Phase-3 snapshot — "
        f"Phase 7's exit criterion is at risk; see ADR-0004. "
        f"Snapshot={sorted(snapshot)}, Found={sorted(found)}."
    )
```

The exhaustiveness meta-test:

```python
# tests/property/test_plan_outcome_match_exhaustive.py
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytest.importorskip("mypy")  # F5 — missing mypy => skip, not a false pass/fail.

OMITTED = ["AppliedFromRecipe", "AppliedFromLlm", "RagOnlyApplicable", "Refused"]

# F5 — substrings proving the failure is the EXHAUSTIVENESS diagnostic, not an
# unrelated mypy error (import resolution, missing stubs). assert_never's arg is
# typed `Never`; an unhandled variant makes mypy flag the assert_never call.
_EXHAUSTIVENESS_MARKERS = ("assert_never", "unreachable", "missing")


def _src(omit: str) -> str:
    arms = "\n".join(
        f"        case {v}():\n            pass"
        for v in OMITTED if v != omit
    )
    return textwrap.dedent(
        f"""
        from typing import assert_never
        from codegenie.fallback.plan_outcome import (
            PlanOutcome, AppliedFromRecipe, AppliedFromLlm,
            RagOnlyApplicable, Refused,
        )

        def consume(p: PlanOutcome) -> None:
            match p:
{arms}
                case _ as never:
                    assert_never(never)
        """
    )


@pytest.mark.parametrize("omit", OMITTED)
def test_mypy_strict_rejects_incomplete_plan_outcome_match(
    tmp_path: Path, omit: str
) -> None:
    tmp = tmp_path / "m.py"
    tmp.write_text(_src(omit))
    res = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(tmp)],
        capture_output=True, text=True,
    )
    assert res.returncode != 0, (
        f"mypy --strict accepted incomplete PlanOutcome match (missing {omit}); "
        f"stdout:\n{res.stdout}"
    )
    out = res.stdout.lower()
    assert any(m in out for m in _EXHAUSTIVENESS_MARKERS), (
        f"mypy failed but not for an exhaustiveness reason (missing {omit}); "
        f"stdout:\n{res.stdout}"
    )


def test_mypy_strict_accepts_complete_plan_outcome_match(tmp_path: Path) -> None:
    full = textwrap.dedent(
        """
        from typing import assert_never
        from codegenie.fallback.plan_outcome import (
            PlanOutcome, AppliedFromRecipe, AppliedFromLlm,
            RagOnlyApplicable, Refused,
        )

        def consume(p: PlanOutcome) -> None:
            match p:
                case AppliedFromRecipe(): pass
                case AppliedFromLlm(): pass
                case RagOnlyApplicable(): pass
                case Refused(): pass
                case _ as never:
                    assert_never(never)
        """
    )
    tmp = tmp_path / "full.py"
    tmp.write_text(full)
    res = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(tmp)],
        capture_output=True, text=True,
    )
    assert res.returncode == 0, f"mypy --strict rejected complete match: {res.stdout}"
    assert "error:" not in res.stdout.lower(), res.stdout
```

The field-type mypy-negative test (F6 — attribute-read idiom; the
`pydantic.mypy` plugin is NOT enabled in this repo, so a constructor-based
negative test would false-pass):

```python
# tests/unit/types/test_plan_outcome_field_types_mypy_negative.py
"""mypy --strict must reject a field-type swap on AppliedFromLlm — newtype
discipline (production ADR-0033). The check reads the field via attribute
access, which mypy verifies from the class-body annotation regardless of
whether the pydantic mypy plugin is installed.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytest.importorskip("mypy")

# (field, wrong_target_type) — assigning m.<field> to a var of wrong_target_type
# must be a mypy error. response_id is LeafResponseId; few_shot_ref is
# SolvedExampleId | None.
_SWAPS = [
    ("response_id", "SolvedExampleId"),
    ("few_shot_ref", "LeafResponseId"),
]


def _src(field: str, wrong_target: str) -> str:
    return textwrap.dedent(
        f"""
        from codegenie.fallback.plan_outcome import AppliedFromLlm
        from codegenie.types.identifiers import LeafResponseId, SolvedExampleId

        def _read(m: AppliedFromLlm) -> None:
            wrong: {wrong_target} = m.{field}
        """
    )


@pytest.mark.parametrize("field,wrong_target", _SWAPS)
def test_mypy_strict_rejects_wrong_field_type(
    tmp_path: Path, field: str, wrong_target: str
) -> None:
    tmp = tmp_path / "swap.py"
    tmp.write_text(_src(field, wrong_target))
    res = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(tmp)],
        capture_output=True, text=True,
    )
    assert res.returncode != 0, (
        f"mypy --strict accepted a wrong type for {field}; stdout:\n{res.stdout}"
    )
    out = res.stdout.lower()
    assert "incompatible type" in out or "assignment" in out, (
        f"mypy failed but not for the {field} type swap; stdout:\n{res.stdout}"
    )
```

State why it fails: `ImportError` — `codegenie.fallback.plan_outcome` doesn't exist. AC-6 fails because the snapshot file doesn't exist yet.

### Green — make it pass

1. Read `src/codegenie/transforms/outcomes.py`; populate `tests/property/_recipe_outcome_phase3_snapshot.txt` with the canonical `RecipeOutcome` variant class names, sorted: `Applied`, `RecipeFailed`, `RecipeNotApplicable`, `Skipped`.
2. Create `src/codegenie/fallback/plan_outcome.py` per AC-1/2/3 (`Field(discriminator="kind")` — F4).
3. Wire exports.

### Refactor — clean up

- Module docstring naming ADR-0004 and the load-bearing fence test.
- Per-variant docstrings naming the originating event (`"""Emitted when FallbackTier dispatched the recipe-tier path; ADR-0004."""`).
- Edge cases enumerated in arch that touch this code: none directly; ADR-0004's "harvester reads `AppliedFromLlm.few_shot_ref`" coupling is consumed by S6-03.
- Confirm `tests/property/_recipe_outcome_phase3_snapshot.txt` ends with a newline and contains exactly the four Phase-3 variant class names (no extras, no missing).
- Lift `ConfigDict(frozen=True, extra="forbid")` to a module-level `_FROZEN_FORBID: Final` constant referenced by all four variants (F12) — single-source the config; matches S1-02's `fallback/` convention.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/fallback/plan_outcome.py` | NEW — four Phase-4-local variants + `PlanOutcome` discriminated union. |
| `src/codegenie/fallback/__init__.py` | Add `PlanOutcome` + four variants to exports. |
| `tests/unit/fallback/__init__.py` | NEW if absent — test package marker (S1-02 may have created it). |
| `tests/unit/fallback/test_plan_outcome.py` | NEW — happy/sad paths per variant + round-trip + discriminator-mapping totality. |
| `tests/property/_recipe_outcome_phase3_snapshot.txt` | NEW — the four canonical `RecipeOutcome` variant class names (sorted, one per line). |
| `tests/property/test_plan_outcome_no_recipe_outcome_widening.py` | NEW — load-bearing fence; AST-walk of `codegenie.transforms.outcomes` + snapshot compare. |
| `tests/property/test_plan_outcome_match_exhaustive.py` | NEW — subprocess `mypy --strict` exhaustiveness meta-test (markers + complete-match). |
| `tests/unit/types/test_plan_outcome_field_types_mypy_negative.py` | NEW — `response_id` / `few_shot_ref` field-annotation checks via attribute read (F6). |

## Out of scope

- **`FallbackTier.run` projection from `PlanProposal` + recipe state → `PlanOutcome`** — S6-01 (`FallbackTier` builds the projection).
- **Inline harvester reading `AppliedFromLlm.few_shot_ref`** — S6-03 (`on_validated` hook).
- **Event-emission shapes (`PlanOutcomeEmitted`)** — S6-01 (audit-event vocabulary).
- **Phase-3 `RecipeOutcome` itself** — Phase-3-owned; this story only references it.
- **`PlanProposal` union** — S1-02 (independent).

## Notes for the implementer

- **Phase-3 `RecipeOutcome` source is `src/codegenie/transforms/outcomes.py` (verified 2026-05-21, F1).** Re-confirm per Rule 8, but the location is settled — `RecipeOutcome` is **not** in `codegenie.plugins.protocols`. The widening fence resolves the file via `codegenie.transforms.outcomes.__file__`, never `inspect.getfile(RecipeOutcome)` (the alias is a typing special form — `inspect.getfile` raises `TypeError`, F3).
- **`RecipeOutcome` has FOUR variants, not three (F2).** The real declaration is `Annotated[Applied | Skipped | RecipeNotApplicable | RecipeFailed, Field(discriminator="kind")]`. ADR-0004 and the arch doc say `Applied | Skipped | Failed` — both stale. The snapshot file must carry `Applied`, `RecipeFailed`, `RecipeNotApplicable`, `Skipped` (sorted).
- **The snapshot is canonical sorted variant class names, one per line.** Per F2 the verified content is the four lines `Applied`, `RecipeFailed`, `RecipeNotApplicable`, `Skipped` (sorted). Re-read `outcomes.py` to confirm before committing — discover, do not guess.
- **`recipe_outcome_digest: BlobDigest` is a digest, not the foreign instance.** ADR-0004 §Tradeoffs row 1: "PlanOutcome and RecipeOutcome are two sum types covering overlapping ground; reading the event log requires understanding both." Embedding the foreign instance would couple Phase 4 to Phase 3's serialization shape; the digest is the loose coupling that survives Phase 3 internal changes.
- **`AppliedFromLlm.few_shot_ref` is `SolvedExampleId | None`** because the LLM may answer cold (no RAG hit), in which case `few_shot_ref` is `None` and the harvester gates on the `confidence == "high"` test (S6-03).
- **`Refused.reason` literal set is closed** by ADR-0004. Adding a fifth reason is an ADR amendment per ADR-0001 §Reversibility — surface per Rule 7 if a Phase-4 implementation discovers a fifth failure mode.
- **The fence inherits to every future phase.** If Phase 5 / 6 / 7 / 11 ever proposes widening `RecipeOutcome`, AC-6 fires loudly. The fence's failure message names ADR-0004 explicitly so the next reader knows where to look.
- **Match S1-02's Pydantic v2 idiom — `Field(discriminator="kind")` (F4).** S1-02 (HARDENED) and every discriminated union in `codegenie/transforms/outcomes.py` use `Annotated[..., Field(discriminator="kind")]`; that is the single repo convention (Rule 11). Do **not** use `Discriminator("kind")` — `phase-arch-design.md §Component 13`/`§Data model` and ADR-0004 show it, but that is a known transcription error first flagged by S1-02's F2 (recommend the docs be corrected). `Discriminator(...)` exists for *callable* discriminators, which this story does not need.
- **Lift `ConfigDict(frozen=True, extra="forbid")` to a module-level `_FROZEN_FORBID: Final` constant (F12)** referenced by all four variants — single-source the config, matching S1-02's `fallback/` convention. Not an AC (not externally observable); do it in the Refactor step.
- **The AC-5 negative test must NOT route through the Pydantic constructor (F6).** This repo has no `pydantic.mypy` plugin (`[tool.mypy]` has no `plugins=`), so `BaseModel.__init__` is `(**data: Any)` to mypy — a constructor-kwarg type swap is silently accepted. Test the field annotation via attribute read (`wrong: SolvedExampleId = m.response_id`) instead — mypy checks that directly from the class body.
- **Do not import Phase 3's `RecipeOutcome` into `plan_outcome.py`** at the type level — `PlanOutcome` references it only via `recipe_outcome_digest: BlobDigest`. The looseness is the whole point of ADR-0004's composition pattern.
