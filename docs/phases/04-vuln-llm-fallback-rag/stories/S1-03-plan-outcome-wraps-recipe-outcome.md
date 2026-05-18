# Story S1-03 — `PlanOutcome` wraps `RecipeOutcome`

**Step:** Step 1 — Establish Phase-4 type substrate + path-scoped fence amendment
**Status:** Ready
**Effort:** S
**Depends on:** S1-01
**ADRs honored:** ADR-0004 (`PlanOutcome` is Phase-4-LOCAL; Phase-3 `RecipeOutcome` is NOT widened), ADR-0001 (`AppliedFromLlm` references `LeafResponseId` + `SolvedExampleId` from the newtype catalog)

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
  - Phase 3's `RecipeOutcome` definition. Find it (likely under `src/codegenie/plugins/protocols.py`, `src/codegenie/transforms/`, or `src/codegenie/orchestrator/`). Capture its **exact** variant list and field shapes. This story's AST walk depends on the canonical declaration.
  - `RecipeApplication` is Phase-3-owned; this story does NOT introduce a Phase-4 variant of it. Re-use the import.

## Goal

Ship the Phase-4-LOCAL `PlanOutcome` Pydantic v2 discriminated union (`AppliedFromRecipe | AppliedFromLlm | RagOnlyApplicable | Refused`) at `src/codegenie/fallback/plan_outcome.py`, and land `tests/property/test_plan_outcome_no_recipe_outcome_widening.py` — the AST-walk fence asserting Phase-3 `RecipeOutcome` variant list is byte-identical to its snapshot.

## Acceptance criteria

- [ ] AC-1 — `src/codegenie/fallback/plan_outcome.py` ships four `BaseModel` subclasses (`AppliedFromRecipe`, `AppliedFromLlm`, `RagOnlyApplicable`, `Refused`), all `model_config = ConfigDict(frozen=True, extra="forbid")`. Each carries a `kind: Literal[<tag>]` discriminator.
- [ ] AC-2 — Variant fields per arch §Data model:
  - `AppliedFromRecipe`: `kind: Literal["recipe"]`, `recipe_outcome_digest: BlobDigest`. (Phase-3 `RecipeOutcome.Applied` is referenced by BLAKE3 digest; the wrap does not embed the foreign instance.)
  - `AppliedFromLlm`: `kind: Literal["llm"]`, `recipe_outcome_digest: BlobDigest`, `few_shot_ref: SolvedExampleId | None`, `response_id: LeafResponseId`.
  - `RagOnlyApplicable`: `kind: Literal["rag_only"]`, `few_shot_ref: SolvedExampleId`.
  - `Refused`: `kind: Literal["refused"]`, `reason: Literal["PROVENANCE_NOT_APP_LAYER", "BUDGET_EXCEEDED", "LEAF_REFUSED", "LEAF_SCHEMA_VIOLATION"]`.
- [ ] AC-3 — `PlanOutcome = Annotated[AppliedFromRecipe | AppliedFromLlm | RagOnlyApplicable | Refused, Discriminator("kind")]` is exported. The v2 idiom must match S1-02's `PlanProposal` shape (consistent across `fallback/`).
- [ ] AC-4 — `tests/unit/fallback/test_plan_outcome.py` covers happy + sad paths:
  - Happy: each variant constructs from valid input; `TypeAdapter(PlanOutcome).validate_python(...)` routes by discriminator.
  - Sad — unknown `kind` value rejected.
  - Sad — `extra="forbid"` rejects unknown keys.
  - Sad — `frozen=True` rejects assignment.
  - Sad — `Refused.reason` outside the four-literal set rejected.
  - Sad — `AppliedFromLlm.response_id` typed as `LeafResponseId`; passing a raw `str` is allowed at runtime (NewType is identity) but the mypy negative test below proves the static rejection.
- [ ] AC-5 — **`response_id: LeafResponseId` mypy discipline** — extend `tests/unit/types/test_phase4_identifiers_mypy_negative.py` (or sibling) with a subprocess `mypy --strict` case asserting `AppliedFromLlm(response_id=BudgetTokenId("..."))` is a type error.
- [ ] AC-6 — **Load-bearing fence: `tests/property/test_plan_outcome_no_recipe_outcome_widening.py`** asserts Phase-3 `RecipeOutcome`'s variant list (canonical module + class name) is **exactly** the byte-identical snapshot stored as `tests/property/_recipe_outcome_phase3_snapshot.txt` (one variant tag per line). Test:
  - AST-walks the Phase-3 `RecipeOutcome` source file (path resolved from the import — `inspect.getfile(RecipeOutcome)`).
  - Extracts the discriminated-union variant list (the `case` shapes inside the `Annotated[..., Discriminator(...)]` declaration OR the `RecipeOutcome = X | Y | Z` union members).
  - Loads `tests/property/_recipe_outcome_phase3_snapshot.txt` (committed snapshot of Phase-3 variant names sorted).
  - Asserts the two sets are equal.
  - On mismatch the failure message is `"RecipeOutcome variants drifted from Phase-3 snapshot — Phase 7's exit criterion is at risk; see ADR-0004"`.
- [ ] AC-7 — The snapshot file `tests/property/_recipe_outcome_phase3_snapshot.txt` is committed with the canonical Phase-3 variant names (one per line, sorted) — discovered by reading the current Phase-3 source per Rule 8.
- [ ] AC-8 — `PlanOutcome` is exported from `src/codegenie/fallback/__init__.py`.
- [ ] AC-9 — **`assert_never` exhaustiveness via subprocess mypy** (`tests/property/test_plan_outcome_match_exhaustive.py`): mirror S1-02's pattern over the four `PlanOutcome` variants. Parametrized incomplete-match files fail `mypy --strict`; complete-match file passes.
- [ ] AC-10 — `mypy --strict src/codegenie/fallback/` clean. `ruff check`, `ruff format --check` clean. The TDD plan's red tests exist, are committed, and are green.

## Implementation outline

1. Read Phase-3 `RecipeOutcome` source (per Rule 8); capture canonical variant names.
2. Create `tests/property/_recipe_outcome_phase3_snapshot.txt` — one variant tag per line, sorted. (Likely: `Applied\nFailed\nSkipped\n` — verify against the source.)
3. Create `src/codegenie/fallback/plan_outcome.py` with four `BaseModel` subclasses + `PlanOutcome = Annotated[..., Discriminator("kind")]`.
4. Export `PlanOutcome` + the four variants from `src/codegenie/fallback/__init__.py`.
5. Write `tests/unit/fallback/test_plan_outcome.py`: happy + sad paths.
6. Write `tests/property/test_plan_outcome_no_recipe_outcome_widening.py`: AST-walk the Phase-3 `RecipeOutcome` declaration, compare against the snapshot.
7. Write `tests/property/test_plan_outcome_match_exhaustive.py`: subprocess mypy meta-test mirroring S1-02.
8. Extend `tests/unit/types/test_phase4_identifiers_mypy_negative.py` with the `AppliedFromLlm.response_id ← BudgetTokenId` swap pair (or add a sibling file `test_plan_outcome_field_types_mypy_negative.py`).
9. Run `mypy --strict src/codegenie/fallback/` + `make check`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/fallback/test_plan_outcome.py`

```python
from __future__ import annotations

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
def test_discriminator_routes(payload, cls):
    adapter = TypeAdapter(PlanOutcome)
    out = adapter.validate_python(payload)
    assert isinstance(out, cls)


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
import inspect
import pathlib

# Adjust import to the Phase-3 canonical home discovered per Rule 8.
# Replace with the actual import once the path is confirmed.
from codegenie.plugins.protocols import RecipeOutcome  # adjust if wrong


SNAPSHOT = pathlib.Path(__file__).parent / "_recipe_outcome_phase3_snapshot.txt"


def _extract_variant_names_from_module(mod_path: pathlib.Path) -> set[str]:
    """Return the set of variant class names that compose RecipeOutcome.

    Looks for either a `RecipeOutcome = A | B | C` alias or an
    `Annotated[A | B | C, Discriminator(...)]` shape.
    """
    tree = ast.parse(mod_path.read_text())
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "RecipeOutcome" for t in node.targets)
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


def test_recipe_outcome_variants_match_phase3_snapshot():
    snapshot = {line.strip() for line in SNAPSHOT.read_text().splitlines() if line.strip()}
    mod_path = pathlib.Path(inspect.getfile(RecipeOutcome))
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

OMITTED = ["AppliedFromRecipe", "AppliedFromLlm", "RagOnlyApplicable", "Refused"]


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
def test_mypy_strict_rejects_incomplete_plan_outcome_match(tmp_path: Path, omit: str) -> None:
    tmp = tmp_path / "m.py"
    tmp.write_text(_src(omit))
    res = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(tmp)],
        capture_output=True, text=True,
    )
    assert res.returncode != 0, f"mypy --strict accepted incomplete PlanOutcome match: {res.stdout}"
```

State why it fails: `ImportError` — `codegenie.fallback.plan_outcome` doesn't exist. AC-6 fails because the snapshot file doesn't exist yet.

### Green — make it pass

1. Read Phase-3 `RecipeOutcome` source; populate `tests/property/_recipe_outcome_phase3_snapshot.txt` with the canonical variant names (e.g., `Applied`, `Failed`, `Skipped`).
2. Create `src/codegenie/fallback/plan_outcome.py` per AC-1/2/3.
3. Wire exports.

### Refactor — clean up

- Module docstring naming ADR-0004 and the load-bearing fence test.
- Per-variant docstrings naming the originating event (`"""Emitted when FallbackTier dispatched the recipe-tier path; ADR-0004."""`).
- Edge cases enumerated in arch that touch this code: none directly; ADR-0004's "harvester reads `AppliedFromLlm.few_shot_ref`" coupling is consumed by S6-03.
- Confirm `tests/property/_recipe_outcome_phase3_snapshot.txt` ends with a newline and contains exactly the Phase-3 variants (no extras, no missing).

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/fallback/plan_outcome.py` | NEW — four Phase-4-local variants + `PlanOutcome` discriminated union. |
| `src/codegenie/fallback/__init__.py` | Add `PlanOutcome` + four variants to exports. |
| `tests/unit/fallback/test_plan_outcome.py` | NEW — happy/sad paths per variant. |
| `tests/property/_recipe_outcome_phase3_snapshot.txt` | NEW — canonical Phase-3 variant names (sorted, one per line). |
| `tests/property/test_plan_outcome_no_recipe_outcome_widening.py` | NEW — load-bearing fence; AST-walk + snapshot compare. |
| `tests/property/test_plan_outcome_match_exhaustive.py` | NEW — subprocess `mypy --strict` exhaustiveness meta-test. |
| `tests/unit/types/test_plan_outcome_field_types_mypy_negative.py` | NEW — `response_id ← BudgetTokenId` and `few_shot_ref ← LeafResponseId` swap rejection. |

## Out of scope

- **`FallbackTier.run` projection from `PlanProposal` + recipe state → `PlanOutcome`** — S6-01 (`FallbackTier` builds the projection).
- **Inline harvester reading `AppliedFromLlm.few_shot_ref`** — S6-03 (`on_validated` hook).
- **Event-emission shapes (`PlanOutcomeEmitted`)** — S6-01 (audit-event vocabulary).
- **Phase-3 `RecipeOutcome` itself** — Phase-3-owned; this story only references it.
- **`PlanProposal` union** — S1-02 (independent).

## Notes for the implementer

- **Find the Phase-3 `RecipeOutcome` source FIRST (Rule 8).** Likely `src/codegenie/plugins/protocols.py` or `src/codegenie/transforms/`. The exact module path determines what the AST-walk in AC-6 reads. If the actual import is `from codegenie.transforms.recipe_outcome import RecipeOutcome`, update the test accordingly.
- **The snapshot is canonical sorted variant names, one per line.** If Phase 3 uses `RecipeOutcome = Applied | Failed | Skipped` then the snapshot is exactly those three lines (sorted). Discover, do not guess.
- **`recipe_outcome_digest: BlobDigest` is a digest, not the foreign instance.** ADR-0004 §Tradeoffs row 1: "PlanOutcome and RecipeOutcome are two sum types covering overlapping ground; reading the event log requires understanding both." Embedding the foreign instance would couple Phase 4 to Phase 3's serialization shape; the digest is the loose coupling that survives Phase 3 internal changes.
- **`AppliedFromLlm.few_shot_ref` is `SolvedExampleId | None`** because the LLM may answer cold (no RAG hit), in which case `few_shot_ref` is `None` and the harvester gates on the `confidence == "high"` test (S6-03).
- **`Refused.reason` literal set is closed** by ADR-0004. Adding a fifth reason is an ADR amendment per ADR-0001 §Reversibility — surface per Rule 7 if a Phase-4 implementation discovers a fifth failure mode.
- **The fence inherits to every future phase.** If Phase 5 / 6 / 7 / 11 ever proposes widening `RecipeOutcome`, AC-6 fires loudly. The fence's failure message names ADR-0004 explicitly so the next reader knows where to look.
- **Match S1-02's Pydantic v2 idiom.** Use `Annotated[..., Discriminator("kind")]` — same shape; the consistency check that runs across `src/codegenie/fallback/` should pass without exception.
- **Do not import Phase 3's `RecipeOutcome` into `plan_outcome.py`** at the type level — `PlanOutcome` references it only via `recipe_outcome_digest: BlobDigest`. The looseness is the whole point of ADR-0004's composition pattern.
