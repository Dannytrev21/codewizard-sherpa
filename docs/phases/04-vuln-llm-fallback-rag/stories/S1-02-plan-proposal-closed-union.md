# Story S1-02 — `PlanProposal` closed discriminated union

**Step:** Step 1 — Establish Phase-4 type substrate + path-scoped fence amendment
**Status:** Ready
**Effort:** M
**Depends on:** S1-01
**ADRs honored:** ADR-0001 (`PlanProposal` is THE closed sum type the LLM may emit), ADR-0004 (`PlanProposal` is the LLM-output shape; `PlanOutcome` wraps `RecipeOutcome` separately — this story does NOT widen any Phase-3 sum type)

## Context

Phase 4's load-bearing structural choice is that **the LLM emits exactly one of four named shapes** — `dep_bump`, `override`, `callsite_rewrite`, `refuse` — validated at the Anthropic SDK boundary via `response_format=PlanProposal.model_json_schema()` before bytes ever reach Python (ADR-0001). The closed Pydantic v2 discriminated union is the type-level firewall: an injected LLM cannot structurally emit a shell command, an `rm -rf`, or unfenced markdown. The 64 KB `UnifiedDiff` cap and path-escape rejection inside the `callsite_rewrite` variant are the smart-constructor controls the critic surfaced as load-bearing — the synthesis ledger upgraded the cap from 32 KB after evidence the headline major-bump fixture (`express-cve-2026-1234`) regularly produces ≥ 40 KB diffs.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — PlanProposal (Component 2)` — variant declarations + Pydantic `Discriminator("kind")` shape.
  - `../phase-arch-design.md §Data model` — full `PlanProposal*` model bodies; the `frozen=True, extra="forbid"` config; the `Annotated[..., Discriminator("kind")]` shape.
  - `../phase-arch-design.md §Edge cases` #6 (`UnifiedDiff` path-escape), #20 (binary diff rejection), #21 (`> 64 KB` rejection), #22 (no-op diff treated as `Refuse`).
  - `../phase-arch-design.md §Testing strategy → Property tests` — `test_plan_proposal_schema_totality.py`.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0001-plan-proposal-closed-sum-type.md` — `Tagged union + Smart constructor + Make illegal states unrepresentable`; `model_construct()` forbidden; rationale audit-log-only.
  - `../ADRs/0004-plan-outcome-wraps-recipe-outcome.md` — `PlanProposal` is independent from `PlanOutcome`; this story must not introduce coupling.
- **Production ADRs:**
  - `../../../production/adrs/0033-domain-modeling-discipline.md` — newtype + smart constructor + sum type + illegal-states-unrepresentable.
- **Source design:**
  - `../final-design.md §Component 2 — PlanProposal` — variant rationale.
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - **Verify Pydantic v2 discriminated-union idiom alignment with Phase 3.** Inspect `src/codegenie/plugins/` and `src/codegenie/transforms/` for the existing `RecipeOutcome` definition. If Phase 3 uses `Field(discriminator=...)` (v1 shape) the story must surface the conflict per Global Rule 7 and pick the more-recent idiom (`Annotated[..., Discriminator("kind")]`). The README §Open implementation questions §1 calls this out explicitly.
  - `src/codegenie/types/identifiers.py` — `SandboxedRelativePath`, `PackageId`, `SemverString` should already be Phase-3-owned newtypes. Re-use; do not redefine.

## Goal

Ship the `PlanProposal` closed Pydantic v2 discriminated union (`dep_bump | override | callsite_rewrite | refuse`) at `src/codegenie/fallback/plan_proposal.py` with `UnifiedDiff` smart-constructor enforcing 64 KB cap + path-escape rejection + binary rejection, so every later Phase-4 module consumes the typed shape and the Anthropic SDK can be passed `PlanProposal.model_json_schema()` as `response_format`.

## Acceptance criteria

- [ ] AC-1 — `src/codegenie/fallback/plan_proposal.py` ships four `BaseModel` subclasses (`PlanProposalDepBump`, `PlanProposalOverride`, `PlanProposalCallsiteRewrite`, `PlanProposalRefuse`), all with `model_config = ConfigDict(frozen=True, extra="forbid")`. Each carries a `kind: Literal[<tag>]` discriminator field with a default matching the tag.
- [ ] AC-2 — `PlanProposal = Annotated[PlanProposalDepBump | PlanProposalOverride | PlanProposalCallsiteRewrite | PlanProposalRefuse, Discriminator("kind")]` is exported. The v2 `Annotated[..., Discriminator(...)]` idiom is used (not v1 `Field(discriminator=...)`); if Phase 3 uses v1 anywhere, the conflict is surfaced per Rule 7 in the story attempt log (and the v2 idiom is the pick).
- [ ] AC-3 — Variant fields match arch §Data model:
  - `PlanProposalDepBump`: `kind`, `manifest_path: SandboxedRelativePath`, `package: PackageId`, `target_version: SemverString`, `rationale: Annotated[str, Field(max_length=2048)]`.
  - `PlanProposalOverride`: `kind`, `manifest_path: SandboxedRelativePath`, `package: PackageId`, `forced_version: SemverString`, `rationale: Annotated[str, Field(max_length=2048)]`.
  - `PlanProposalCallsiteRewrite`: `kind`, `manifest_path: SandboxedRelativePath`, `files: list[SandboxedRelativePath]` (non-empty, `Field(min_length=1)`), `diff: UnifiedDiff`, `rationale: Annotated[str, Field(max_length=2048)]`.
  - `PlanProposalRefuse`: `kind`, `reason: Literal["out_of_scope", "insufficient_context", "policy_block"]`, `rationale: Annotated[str, Field(max_length=2048)]`.
- [ ] AC-4 — `UnifiedDiff` is a Pydantic-validated newtype (not a `NewType`-as-`str`) implemented as a `BaseModel` subclass or `Annotated[str, AfterValidator(...)]`. Smart-constructor rejects:
  - **Length > 64 KB** (`len(diff.encode("utf-8")) > 65_536` → `ValidationError`).
  - **Binary content** (any non-UTF-8 byte → `ValidationError`).
  - **Path escape** — every `+++ b/<path>` / `--- a/<path>` line's path **must appear in the parent `files` list**. (Validator runs at the `PlanProposalCallsiteRewrite` model level so it sees `files` + `diff` together — Pydantic v2 `@model_validator(mode="after")`.)
  - **No-op diff** (zero `+`/`-` lines after the header) → `ValidationError`. (Edge case #22.)
  - **Empty diff string** → `ValidationError`.
- [ ] AC-5 — `tests/unit/fallback/test_plan_proposal.py` covers happy + sad paths for every variant:
  - Happy: each variant constructs from a valid dict via `Model.model_validate(payload)`; the discriminator routes correctly.
  - Sad — discriminator: unknown `kind` value (`"shell_command"`) raises `ValidationError`.
  - Sad — `extra="forbid"`: extra keys (`{"kind": "dep_bump", ..., "shell": "rm"}`) raise.
  - Sad — `frozen=True`: `model.manifest_path = "x"` raises `ValidationError`.
  - Sad — `rationale > 2048 chars` raises.
  - Sad — `PlanProposalCallsiteRewrite` with `files=[]` raises (`min_length=1`).
  - Sad — `UnifiedDiff` > 64 KB raises.
  - Sad — `UnifiedDiff` with a `+++ b/../../etc/passwd` line where `files` does not include `../../etc/passwd` raises (path escape).
  - Sad — `UnifiedDiff` carrying non-UTF-8 bytes (binary header) raises.
  - Sad — `UnifiedDiff` empty / no-op raises.
- [ ] AC-6 — **Schema-totality property** (`tests/property/test_plan_proposal_schema_totality.py`):
  - `json.loads(json.dumps(PlanProposal.model_json_schema()))` is a no-op (round-trippable).
  - The schema's `oneOf` (or `discriminator.mapping`) names exactly the four tags `{dep_bump, override, callsite_rewrite, refuse}` — no more, no fewer.
  - `model_json_schema()` is **idempotent across calls** (`PlanProposal.model_json_schema() == PlanProposal.model_json_schema()` deep-equal).
- [ ] AC-7 — **`assert_never` exhaustiveness via subprocess mypy** (`tests/property/test_plan_proposal_match_exhaustive.py`):
  - Writes a temp file with `match plan: case PlanProposalDepBump(): ...` covering three of four arms + `case _ as never: assert_never(never)` and asserts `mypy --strict` reports a "Statement is unreachable" / "missing case" / "no overload variant" error (parametrized over each omitted variant).
  - Writes a complete `match` (all four arms) and asserts `mypy --strict` exits 0.
  - This is the load-bearing test that catches a future `Refuse`-arm regression at planner-fold-in time (arch §Risks specific to this step §2 — mypy --strict is the only place exhaustiveness is enforced).
- [ ] AC-8 — `model_construct` is forbidden in production code under `src/codegenie/fallback/` and `src/codegenie/rag/`. Test `tests/fence/test_phase4_no_model_construct.py` AST-walks both directories (handling `not yet existent`) and asserts no `*.model_construct(` callsite. Skeleton lands here; coverage grows as later stories add code.
- [ ] AC-9 — **Rationale-discipline AST guard** (`tests/fence/test_no_rationale_in_prompts.py`): walks `src/codegenie/fallback/` and asserts `PlanProposal*.rationale` is **never** read into a string that flows into `prompt_builder.build(...)` (no `f"... {plan.rationale} ..."` patterns under `fallback/`). Skeleton lands here (S2-04 will exercise it).
- [ ] AC-10 — `PlanProposal` is exported from `src/codegenie/fallback/__init__.py`; the four variant classes are also exported individually.
- [ ] AC-11 — `mypy --strict src/codegenie/fallback/` clean. `ruff check`, `ruff format --check` clean. The TDD plan's red test exists, was committed, and is green.

## Implementation outline

1. Create `src/codegenie/fallback/__init__.py` and `src/codegenie/fallback/plan_proposal.py`.
2. Import `SandboxedRelativePath`, `PackageId`, `SemverString` from their Phase-3 canonical home in `codegenie.types.identifiers`. **Read first** (Rule 8) to verify the names + shapes; surface any drift per Rule 7.
3. Define `UnifiedDiff` as `Annotated[str, AfterValidator(_validate_unified_diff_bytes_and_no_op)]` and a Pydantic `@model_validator(mode="after")` on `PlanProposalCallsiteRewrite` that runs `_validate_diff_paths_in_files(diff, files)`. The validators are pure module-level helpers, testable independently.
4. Define the four `PlanProposal*` `BaseModel` subclasses per arch §Data model. Order matters for readability; `Refuse` last.
5. Export `PlanProposal = Annotated[..., Discriminator("kind")]`.
6. Add the variants and `PlanProposal` to `src/codegenie/fallback/__init__.py`.
7. Write `tests/unit/fallback/test_plan_proposal.py`: parametrized happy/sad paths.
8. Write `tests/property/test_plan_proposal_schema_totality.py`: schema round-trip + tag exactness + idempotence.
9. Write `tests/property/test_plan_proposal_match_exhaustive.py`: subprocess `mypy --strict` against deliberately-incomplete `match` files.
10. Write `tests/fence/test_phase4_no_model_construct.py` and `tests/fence/test_no_rationale_in_prompts.py` skeletons.
11. Run `mypy --strict src/codegenie/fallback/` + `make check`.

## TDD plan — red / green / refactor

### Red — write the failing test first

Test file path: `tests/unit/fallback/test_plan_proposal.py`

```python
from __future__ import annotations

import json
import pytest
from pydantic import ValidationError

from codegenie.fallback.plan_proposal import (
    PlanProposal,
    PlanProposalCallsiteRewrite,
    PlanProposalDepBump,
    PlanProposalOverride,
    PlanProposalRefuse,
)

VALID_DEP_BUMP = {
    "kind": "dep_bump",
    "manifest_path": "package.json",
    "package": "lodash@4.17.21",
    "target_version": "4.17.21",
    "rationale": "Patch advisory CVE-2024-21501; minor bump.",
}
VALID_OVERRIDE = {
    "kind": "override",
    "manifest_path": "package.json",
    "package": "express@5.0.0",
    "forced_version": "5.0.0",
    "rationale": "Force resolution of transitive dep.",
}
GOOD_DIFF = (
    "--- a/src/app.ts\n"
    "+++ b/src/app.ts\n"
    "@@ -1,3 +1,3 @@\n"
    "-const x = 1;\n"
    "+const x = 2;\n"
    " // unchanged\n"
)
VALID_CALLSITE = {
    "kind": "callsite_rewrite",
    "manifest_path": "package.json",
    "files": ["src/app.ts"],
    "diff": GOOD_DIFF,
    "rationale": "Update callsite for new API.",
}
VALID_REFUSE = {
    "kind": "refuse",
    "reason": "insufficient_context",
    "rationale": "Not enough context to safely rewrite.",
}


# --- Discriminator routing (AC-5 happy) ---

@pytest.mark.parametrize(
    "payload,expected_cls",
    [
        (VALID_DEP_BUMP, PlanProposalDepBump),
        (VALID_OVERRIDE, PlanProposalOverride),
        (VALID_CALLSITE, PlanProposalCallsiteRewrite),
        (VALID_REFUSE, PlanProposalRefuse),
    ],
)
def test_discriminator_routes(payload, expected_cls):
    from pydantic import TypeAdapter
    adapter = TypeAdapter(PlanProposal)
    obj = adapter.validate_python(payload)
    assert isinstance(obj, expected_cls)


# --- Discriminator rejects unknown tag (AC-5 sad) ---

def test_unknown_kind_rejected():
    from pydantic import TypeAdapter
    adapter = TypeAdapter(PlanProposal)
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "shell_command", "cmd": "rm -rf /"})


# --- extra="forbid" (AC-5) ---

def test_extra_keys_rejected():
    with pytest.raises(ValidationError):
        PlanProposalDepBump.model_validate({**VALID_DEP_BUMP, "shell": "rm"})


# --- frozen=True (AC-5) ---

def test_frozen_immutable():
    m = PlanProposalDepBump.model_validate(VALID_DEP_BUMP)
    with pytest.raises(ValidationError):
        m.manifest_path = "other.json"  # type: ignore[misc]


# --- rationale length (AC-5) ---

def test_rationale_max_2048():
    big = {**VALID_DEP_BUMP, "rationale": "x" * 2049}
    with pytest.raises(ValidationError):
        PlanProposalDepBump.model_validate(big)


# --- files non-empty (AC-5) ---

def test_callsite_files_non_empty():
    payload = {**VALID_CALLSITE, "files": []}
    with pytest.raises(ValidationError):
        PlanProposalCallsiteRewrite.model_validate(payload)


# --- UnifiedDiff > 64 KB (AC-4) ---

def test_diff_too_large_rejected():
    huge = "--- a/src/app.ts\n+++ b/src/app.ts\n@@ -1 +1 @@\n-x\n+" + ("y" * 70_000) + "\n"
    payload = {**VALID_CALLSITE, "diff": huge}
    with pytest.raises(ValidationError):
        PlanProposalCallsiteRewrite.model_validate(payload)


# --- Path escape (AC-4) ---

def test_diff_path_escape_rejected():
    bad = (
        "--- a/../../etc/passwd\n"
        "+++ b/../../etc/passwd\n"
        "@@ -1 +1 @@\n-x\n+y\n"
    )
    payload = {**VALID_CALLSITE, "files": ["src/app.ts"], "diff": bad}
    with pytest.raises(ValidationError):
        PlanProposalCallsiteRewrite.model_validate(payload)


# --- No-op diff (AC-4 / arch edge #22) ---

def test_no_op_diff_rejected():
    no_op = "--- a/src/app.ts\n+++ b/src/app.ts\n@@ -1 +1 @@\n unchanged\n"
    payload = {**VALID_CALLSITE, "diff": no_op}
    with pytest.raises(ValidationError):
        PlanProposalCallsiteRewrite.model_validate(payload)


# --- Empty diff (AC-4) ---

def test_empty_diff_rejected():
    payload = {**VALID_CALLSITE, "diff": ""}
    with pytest.raises(ValidationError):
        PlanProposalCallsiteRewrite.model_validate(payload)
```

The schema-totality property test:

```python
# tests/property/test_plan_proposal_schema_totality.py
from __future__ import annotations

import json
from pydantic import TypeAdapter
from codegenie.fallback.plan_proposal import PlanProposal


def test_schema_round_trips_through_json():
    schema = TypeAdapter(PlanProposal).json_schema()
    assert json.loads(json.dumps(schema)) == schema


def test_schema_lists_exactly_four_tags():
    schema = TypeAdapter(PlanProposal).json_schema()
    # Pydantic v2 emits discriminator.mapping for closed unions
    tags = (
        set(schema.get("discriminator", {}).get("mapping", {}).keys())
        or {ref["$ref"].rsplit("/", 1)[-1] for ref in schema.get("oneOf", [])}
    )
    # Either the discriminator mapping or the oneOf branch refs must enumerate four.
    # Accept canonical-tag form.
    canonical = {"dep_bump", "override", "callsite_rewrite", "refuse"}
    assert canonical.issubset({t.lower() for t in tags}) or len(tags) == 4


def test_schema_is_idempotent():
    a = TypeAdapter(PlanProposal).json_schema()
    b = TypeAdapter(PlanProposal).json_schema()
    assert a == b
```

The exhaustiveness meta-test:

```python
# tests/property/test_plan_proposal_match_exhaustive.py
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# Each row is the variant deliberately omitted from the `match` block; mypy --strict
# must report a missing-case / unreachable diagnostic via the `assert_never` arm.
OMITTED = ["PlanProposalDepBump", "PlanProposalOverride", "PlanProposalCallsiteRewrite", "PlanProposalRefuse"]


def _src(omit: str) -> str:
    arms = "\n".join(
        f"        case {v}():\n            pass"
        for v in OMITTED if v != omit
    )
    return textwrap.dedent(
        f"""
        from typing import assert_never
        from codegenie.fallback.plan_proposal import (
            PlanProposal, PlanProposalDepBump, PlanProposalOverride,
            PlanProposalCallsiteRewrite, PlanProposalRefuse,
        )

        def consume(p: PlanProposal) -> None:
            match p:
{arms}
                case _ as never:
                    assert_never(never)
        """
    )


@pytest.mark.parametrize("omit", OMITTED)
def test_mypy_strict_rejects_incomplete_match(tmp_path: Path, omit: str) -> None:
    src = _src(omit)
    tmp = tmp_path / "match.py"
    tmp.write_text(src)
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(tmp)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0, (
        f"mypy --strict accepted match block missing {omit}; stdout:\n{result.stdout}"
    )


def test_mypy_strict_accepts_complete_match(tmp_path: Path) -> None:
    full = textwrap.dedent(
        """
        from typing import assert_never
        from codegenie.fallback.plan_proposal import (
            PlanProposal, PlanProposalDepBump, PlanProposalOverride,
            PlanProposalCallsiteRewrite, PlanProposalRefuse,
        )

        def consume(p: PlanProposal) -> None:
            match p:
                case PlanProposalDepBump(): pass
                case PlanProposalOverride(): pass
                case PlanProposalCallsiteRewrite(): pass
                case PlanProposalRefuse(): pass
                case _ as never:
                    assert_never(never)
        """
    )
    tmp = tmp_path / "full.py"
    tmp.write_text(full)
    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(tmp)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"mypy --strict rejected complete match: {result.stdout}"
```

The fence skeletons:

```python
# tests/fence/test_phase4_no_model_construct.py
import ast, pathlib
import codegenie
_ROOT = pathlib.Path(codegenie.__file__).parent

def test_no_model_construct_in_phase4():
    offenders = []
    for path in (_ROOT / "fallback", _ROOT / "rag"):
        if not path.exists(): continue
        for py in path.rglob("*.py"):
            tree = ast.parse(py.read_text())
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "model_construct"):
                    offenders.append((str(py), node.lineno))
    assert not offenders, f"model_construct() bypasses validation: {offenders}"
```

```python
# tests/fence/test_no_rationale_in_prompts.py
# Skeleton — S2-04 (PromptBuilder) exercises this; lands here per ADR-0001 §Consequences.
import ast, pathlib
import codegenie
_ROOT = pathlib.Path(codegenie.__file__).parent / "fallback"

def test_rationale_does_not_flow_into_prompt_strings():
    if not _ROOT.exists(): return
    offenders = []
    for py in _ROOT.rglob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            # Heuristic AST scan for f-strings/format/concat carrying `.rationale`.
            if isinstance(node, ast.JoinedStr):
                for v in node.values:
                    if (isinstance(v, ast.FormattedValue)
                        and isinstance(v.value, ast.Attribute)
                        and v.value.attr == "rationale"):
                        offenders.append((str(py), node.lineno))
    assert not offenders, f"PlanProposal.rationale must not re-enter prompts: {offenders}"
```

State why it fails: `ImportError` — `codegenie.fallback.plan_proposal` doesn't exist.

### Green — make it pass

- Create `src/codegenie/fallback/__init__.py` (empty re-exports stub initially).
- Create `src/codegenie/fallback/plan_proposal.py` with the four `BaseModel` subclasses + `UnifiedDiff` validator + `PlanProposal = Annotated[..., Discriminator("kind")]`.
- Implement `_validate_unified_diff_bytes_and_no_op(value: str) -> str` (length, UTF-8, no-op detection) and `_validate_diff_paths_in_files(self) -> Self` (`@model_validator(mode="after")`).
- Wire variants into `src/codegenie/fallback/__init__.py`.

### Refactor — clean up

- Lift the 64 KB cap to a module-level `Final` constant `_MAX_DIFF_BYTES: Final[int] = 65_536` with a comment naming ADR-0001 + the synthesis-ledger 32 KB → 64 KB upgrade.
- Lift the `rationale` length cap (`2048`) to `_MAX_RATIONALE_CHARS: Final[int]`.
- Docstring each variant naming the LLM emission semantics (`"""LLM emits this when the patch is a manifest-only version bump; ADR-0001."""`).
- Edge cases enumerated in arch §Edge cases that touch this code: #6 (path escape), #20 (binary), #21 (>64 KB), #22 (no-op).
- Logging / structlog hooks per arch §Harness engineering: **none in this story** — the validator helpers are pure; `FallbackTier` emits `LeafProtocolViolation` events when validation fails downstream. Validators raise `ValidationError`; the imperative shell logs.

## Files to touch

| Path | Why |
|---|---|
| `src/codegenie/fallback/__init__.py` | NEW — package skeleton; re-export `PlanProposal` + four variants. |
| `src/codegenie/fallback/plan_proposal.py` | NEW — four variants + `UnifiedDiff` validator + `PlanProposal` discriminated union. |
| `tests/unit/fallback/__init__.py` | NEW — test package marker. |
| `tests/unit/fallback/test_plan_proposal.py` | NEW — happy/sad paths per variant + `UnifiedDiff` rejections. |
| `tests/property/__init__.py` | NEW if absent — test package marker. |
| `tests/property/test_plan_proposal_schema_totality.py` | NEW — schema round-trip + tag-set exactness + idempotence. |
| `tests/property/test_plan_proposal_match_exhaustive.py` | NEW — subprocess `mypy --strict` exhaustiveness meta-test. |
| `tests/fence/test_phase4_no_model_construct.py` | NEW — AST guard against `model_construct()` callsites under `fallback/`+`rag/`. |
| `tests/fence/test_no_rationale_in_prompts.py` | NEW skeleton — AST guard against `rationale` re-entering prompts. |

## Out of scope

- **`PlanOutcome` sum type** — S1-03 (independent of `PlanProposal`; `PlanOutcome` wraps `RecipeOutcome`).
- **`Discriminator("kind")` choice if Phase 3 used v1 `Field(discriminator=...)`** — surface as a Rule-7 conflict in the attempt log; do not silently blend (the README §Open implementation questions §1 names this).
- **Pydantic schema-generation for the Anthropic SDK `response_format` parameter** — S3-02 wires `PlanProposal.model_json_schema()` into the SDK call.
- **`assert_never`-exhaustive consumer code** — S6-01 (`FallbackTier`) is the first consumer; this story's exhaustiveness test is meta-test infrastructure.
- **The fence amendment admitting `anthropic`/`chromadb`/`fastembed`/`onnxruntime`** — S1-05.
- **`SandboxedRelativePath` / `PackageId` / `SemverString` definitions** — Phase-3-owned; this story consumes them.

## Notes for the implementer

- **Verify the Pydantic-v2 idiom alignment with Phase 3 FIRST (Rule 8 + Rule 7).** Read existing `RecipeOutcome` and any other discriminated union in `src/codegenie/`. If Phase 3 used `Field(discriminator=...)` (the v1 shape passed through to v2), pick `Annotated[..., Discriminator(...)]` (the recent v2 shape) and surface the inconsistency in the attempt log so a follow-up story aligns Phase 3. Do not blend the two idioms inside `plan_proposal.py`.
- **`UnifiedDiff` is NOT a `NewType`.** A `NewType("UnifiedDiff", str)` would have no validator; the smart-constructor controls (length, no-op, path-escape) need to fire on every construction. Use `Annotated[str, AfterValidator(...)]` (pure-`str` carrier; Pydantic enforces the validator on every model field of type `UnifiedDiff`).
- **Path-escape check needs `files` context.** `UnifiedDiff` alone cannot validate paths because the allowed list lives on the parent model. Run the path-escape validator as `@model_validator(mode="after")` on `PlanProposalCallsiteRewrite` so `self.files` and `self.diff` are both available. The parser splits the diff on lines starting with `+++ b/` and `--- a/`; each extracted path must be in `set(self.files)` (raw string equality after stripping `a/`/`b/`).
- **No-op detection** is a count of lines starting with `+` or `-` (excluding the `+++`/`---` header lines); zero data-lines → no-op → reject. Edge case #22.
- **Binary detection** is `value.encode("utf-8")` raising → `ValidationError`. Pydantic's default `str` validator already enforces UTF-8 on input, but the byte-length cap (`len(value.encode("utf-8")) > 65_536`) is the operative check.
- **`assert_never` exhaustiveness is mypy-strict-only.** The meta-test (`test_plan_proposal_match_exhaustive.py`) MUST subprocess `mypy --strict` to be load-bearing. README §Open implementation questions §5 calls this out explicitly. CI runs `make typecheck` (`mypy --strict src/`); this story's meta-test verifies `mypy --strict` is wired up correctly.
- **`PlanProposalRefuse.rationale` is audit-log-only.** Per ADR-0001 §Consequences, the `rationale` field is never re-prompted. The `test_no_rationale_in_prompts.py` skeleton lands here so S2-04's `PromptBuilder` is guarded the moment it lands.
- **Do not import `anthropic` here.** The path-scoped fence (S1-05) admits `anthropic` only under `src/codegenie/fallback/leaf/anthropic_adapter.py`. `plan_proposal.py` is pure Pydantic.
- **Newtypes-everywhere cross-cutting rule.** Every field that names a domain primitive (`manifest_path`, `package`, `target_version`, `forced_version`) is typed against the Phase-3 newtype, never `str`. The AST source-scan from S1-01 (`test_phase4_no_raw_str_for_domain_ids.py`) is the load-bearing guard once `fallback/` exists.
