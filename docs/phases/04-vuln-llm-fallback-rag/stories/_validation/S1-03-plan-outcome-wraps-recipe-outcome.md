# Validation report — S1-03 `PlanOutcome` wraps `RecipeOutcome`

**Validated:** 2026-05-21
**Validator:** phase-story-validator (scheduled story-validation-corrector run)
**Verdict:** HARDENED
**Story:** `docs/phases/04-vuln-llm-fallback-rag/stories/S1-03-plan-outcome-wraps-recipe-outcome.md`

## Summary

The story is structurally sound — its goal (a Phase-4-local `PlanOutcome`
discriminated union + an AST-walk fence pinning Phase-3 `RecipeOutcome`'s
variant set) traces cleanly to ADR-0004, the phase arch, and Phase 7's exit
criterion. But it was written against **guessed** facts about the codebase that
turned out wrong, and three of its load-bearing tests would not have worked or
would have green-washed. Six block-severity findings, all fixable in place →
**HARDENED**, not RESCUE.

The dominant theme mirrors the HARDENED sibling S1-02: the upstream design docs
(`phase-arch-design.md`, ADR-0004) carry transcription errors the story
inherited — the `Discriminator("kind")` idiom and the `RecipeOutcome` variant
list are both wrong in the source docs. Ground truth was established by reading
`src/codegenie/transforms/outcomes.py`, `pyproject.toml`, and the S1-02
validation report.

## Context loaded

- Story file (full).
- `ADRs/0004-plan-outcome-wraps-recipe-outcome.md` — Decision + Tradeoffs + Consequences.
- Sibling story `S1-02-plan-proposal-closed-union.md` (HARDENED) + its `Validation notes` block — the established `fallback/` family framing (`Field(discriminator="kind")`, `_FROZEN_FORBID` lift, stdout-substring exhaustiveness assertions, `pytest.importorskip("mypy")`).
- `phase-arch-design.md` §Component 13 (`PlanOutcome`), §Data model (lines 748–782).
- `S1-01-newtype-smart-constructor-substrate.md` — confirms `LeafResponseId`, `SolvedExampleId`, `BudgetTokenId` are S1-01 newtypes (`BlobDigest` is Phase-3-owned, already present).
- **Source of truth:** `src/codegenie/transforms/outcomes.py` (the real `RecipeOutcome` declaration), `src/codegenie/transforms/__init__.py` (re-export + "single repo convention" docstring), `pyproject.toml` `[tool.mypy]` (no pydantic plugin), `src/codegenie/types/identifiers.py` (`BlobDigest` present).

## Findings

Severity legend: **block** = the story as written produces wrong or
non-functional code; **harden** = real weakness, test could pass a wrong impl;
**nit** = polish.

### F1 — block — wrong `RecipeOutcome` source location

The story said the definition is "likely under `src/codegenie/plugins/protocols.py`"
and the fence test imported `from codegenie.plugins.protocols import RecipeOutcome`.

Grep-verified: `RecipeOutcome` is declared in **`src/codegenie/transforms/outcomes.py`**
(re-exported from `codegenie.transforms.__init__`). `codegenie/plugins/protocols.py`
exists but does **not** export `RecipeOutcome`. The story's `# adjust if wrong`
placeholder import would `ImportError`.

**Fix:** References, AC-6, Notes, the implementation outline, the Green steps,
and the fence-test code now name `codegenie.transforms.outcomes`.

### F2 — block — wrong `RecipeOutcome` variant list (3 guessed vs 4 real)

The story (impl outline: "Likely: `Applied\nFailed\nSkipped\n`"; Green: "e.g.,
`Applied`, `Failed`, `Skipped`") — and ADR-0004 itself ("`RecipeOutcome =
Applied | Skipped | Failed`"), and `phase-arch-design.md` — all describe a
**three**-variant union with a variant named `Failed`.

The real declaration (`outcomes.py:284`):

```python
RecipeOutcome = Annotated[
    Applied | Skipped | RecipeNotApplicable | RecipeFailed,
    Field(discriminator="kind"),
]
```

**Four** variants; the failure variant is `RecipeFailed`, not `Failed`; there is
an extra `RecipeNotApplicable`. The AST-walk fence (AC-6) compares the extracted
class-name set against a committed snapshot — a wrong snapshot makes the fence
fail on its first run, or (worse) pass against a wrong baseline and never catch
real drift.

**Fix:** AC-7 now carries the four verified class names (sorted: `Applied`,
`RecipeFailed`, `RecipeNotApplicable`, `Skipped`); impl outline + Green updated.
ADR-0004 and the arch doc are stale — **flagged for follow-up**, not edited
(validator edits stories only).

### F3 — block — `inspect.getfile(RecipeOutcome)` raises `TypeError`

AC-6 and the fence-test code resolved the source path via
`pathlib.Path(inspect.getfile(RecipeOutcome))`. `RecipeOutcome` is an
`Annotated[...]` alias — a `typing` special form, not a module / class /
method / function / traceback / frame / code object. `inspect.getfile` raises
`TypeError` on exactly that input. The test would error on collection, never
running the assertion.

**Fix:** the test now imports the **module** (`import codegenie.transforms.outcomes
as _recipe_outcome_mod`) and resolves the path via `_recipe_outcome_mod.__file__`.
AC-6's mechanism description updated.

### F4 — block — wrong discriminated-union idiom

AC-3, the implementation outline (step 3), and Notes prescribed
`Annotated[..., Discriminator("kind")]`. AC-3 simultaneously said "must match
S1-02's `PlanProposal` shape (consistent across `fallback/`)" — and S1-02
(HARDENED, same package) settled on `Field(discriminator="kind")`. The AC was
internally contradictory.

Ground truth: every umbrella in `outcomes.py` (`RecipeOutcome`,
`RemediationOutcome`, `NodeTransition`, `AdapterConfidence`, `Applicability`)
uses `Field(discriminator="kind")`; the `transforms` package docstring calls it
"the single repo convention". `Discriminator(...)` is a v2 construct for
*callable* discriminators — not needed here.

The arch doc + ADR-0004 show `Discriminator("kind")` — the identical
transcription error S1-02's F2 already flagged.

**Conflict resolution:** Consistency normally outranks all other critics, but
here the "source of truth" is itself split (arch says `Discriminator`, the
shipped codebase + the HARDENED sibling say `Field`). The codebase's actual
convention + the validated sibling in the *same package* win — this is the same
resolution S1-02 made for the same family (Rule 11; Rule 7 — pick the
more-tested, don't average). **Fix:** `Field(discriminator="kind")` throughout
AC-3, outline, Notes.

### F5 — block — exhaustiveness meta-test green-washes

`test_plan_outcome_match_exhaustive.py` asserted only `res.returncode != 0`.
A mypy run that fails for an unrelated reason (import resolution failure,
missing stubs, a syntax slip in the generated file) satisfies that assertion
while proving nothing about `assert_never` exhaustiveness. This is verbatim the
F4 weakness S1-02 fixed — and AC-9 even said "mirror S1-02's pattern", but the
embedded code mirrored the *pre-hardening* S1-02.

**Fix:** the meta-test now (a) asserts a `{assert_never, unreachable, missing}`
substring on stdout, (b) adds `pytest.importorskip("mypy")` so a missing mypy
install skips rather than false-passes, and (c) adds the complete-match
positive case (`test_mypy_strict_accepts_complete_plan_outcome_match`). AC-9
rewritten to spell out all three.

### F6 — block — AC-5 mypy-negative test cannot work as specified

AC-5 prescribed a subprocess `mypy --strict` case asserting
`AppliedFromLlm(response_id=BudgetTokenId("..."))` is a type error — i.e. a
**constructor-kwarg** type swap.

`pyproject.toml [tool.mypy]` enables `strict = true` + `warn_unreachable` but
carries **no `plugins =`** entry. Without the `pydantic.mypy` plugin, mypy sees
`BaseModel.__init__(self, **data: Any)` — every constructor kwarg is `Any`-typed
and a wrong newtype is silently accepted. The test would **false-pass** (mypy
exits 0, the negative test sees no error and... actually asserts an error is
present → it would fail to find one → but the deeper point: it cannot prove the
field is typed). Either way the prescribed mechanism is unsound.

Additionally the snippet `AppliedFromLlm(response_id=BudgetTokenId("..."))`
omits the required `recipe_outcome_digest` and `kind` — even *with* the plugin,
mypy would flag missing-args, not the type swap, muddying the diagnostic.

**Fix:** AC-5 rewritten to the plugin-independent **attribute-read** idiom:
`def _read(m: AppliedFromLlm) -> None: wrong: SolvedExampleId = m.response_id`.
mypy reads `response_id: LeafResponseId` straight from the class body and flags
the assignment — no plugin required. Two swaps covered (`response_id`,
`few_shot_ref`); stdout asserted for `incompatible type`/`assignment`. Full
test code added to the TDD plan.

### F7 — harden — `test_discriminator_routes` only checks `isinstance`

The routing test asserted only `isinstance(out, cls)`. An implementation that
routes by discriminator correctly but drops or defaults a non-`kind` field
(`recipe_outcome_digest -> ""`, `few_shot_ref -> None`) passes. Same as S1-02 F11.

**Fix:** the test now iterates `payload.items()` and asserts each field survived
onto the routed object. Test params + signature annotated per repo convention.

### F8 — harden — no serialization round-trip property

`PlanOutcome` flows to the event log (ADR-0004 §Consequences). An asymmetric
serializer/deserializer bug (a field that dumps under one key and validates
under another) would not be caught by any existing test.

**Fix:** added `test_json_round_trip_identity` — every variant survives
`model_validate(json.loads(json.dumps(obj.model_dump(mode="json"))))` and
re-equals the original. Mirrors S1-02 F12.

### F9 — harden — no totality guard on `PlanOutcome`'s own variant set

The AC-6 fence pins *`RecipeOutcome`*'s variants; nothing pinned *`PlanOutcome`*'s.
A smuggled fifth `PlanOutcome` variant, or a typo in a `kind` tag, was caught
only by AC-9's slow subprocess-mypy meta-test (skippable if mypy is absent).

**Fix:** new **AC-11** + `test_discriminator_mapping_is_exactly_four_tags` —
strict set equality on `TypeAdapter(PlanOutcome).json_schema()["discriminator"]["mapping"]`
keys against `{recipe, llm, rag_only, refused}`. Fast, always-runs. Mirrors
S1-02's `test_schema_lists_exactly_four_tags` (and its F3 "no `len(...) == 4`
escape hatch" discipline).

### F10 — harden — `kind` discriminator needs a default

AC-1 required `kind: Literal[<tag>]` but not a default. The arch §Data model
shows `kind: Literal["llm"] = "llm"` (with default). Without the default, every
direct construction (the meta-tests, any future consumer) must pass `kind=`
explicitly, and an implementer omitting it produces a model that only validates
from dicts. Consistency with S1-02 (which settled on defaults).

**Fix:** AC-1 now requires each `kind` to carry a default matching its tag.

### F11 — harden — AST walk handles only `ast.Assign`

`_extract_variant_names_from_module` matched only `ast.Assign`
(`RecipeOutcome = ...`). The current source is an `ast.Assign`, so this is not
a live break — but a future Phase-3 refactor adding an explicit alias
annotation (`RecipeOutcome: TypeAlias = ...`) would turn the node into an
`ast.AnnAssign`, the walk would fall through to its `AssertionError`
("declaration not found"), and the failure message would misdirect the next
reader (it would read as "RecipeOutcome was deleted", not "the fence can't
parse the new shape").

**Fix:** the walk now also matches `ast.AnnAssign` with a `Name` target. AC-6
updated.

### F12 — nit — single-source the model config

S1-02 lifted `ConfigDict(frozen=True, extra="forbid")` to a module-level
`_FROZEN_FORBID: Final` in `fallback/`. S1-03 repeated the literal four times.

**Fix:** a Notes paragraph + a Refactor-step bullet prescribe the `_FROZEN_FORBID`
lift. Not an AC (not externally observable). Also: Files-to-touch gains
`tests/unit/fallback/__init__.py` (NEW if absent) so the story is self-contained
even if executed before S1-02.

## Conflicts surfaced

- **F4 (idiom):** arch/ADR (`Discriminator`) vs codebase + HARDENED sibling
  (`Field`). Resolved in favour of the codebase convention — see F4. The arch
  doc + ADR-0004 transcription errors are **flagged for follow-up**; this
  validator does not edit ADRs or arch docs (out of scope — it edits stories).

## Items flagged for follow-up (not edited by this validator)

1. `ADRs/0004-plan-outcome-wraps-recipe-outcome.md` §Context line 10 + §Consequences
   line 45 say `RecipeOutcome = Applied | Skipped | Failed` — stale (real:
   `Applied | Skipped | RecipeNotApplicable | RecipeFailed`).
2. `phase-arch-design.md` §Component 13 + §Data model show `Discriminator("kind")`
   and the 3-variant `RecipeOutcome` — both inaccurate. (S1-02's F2 already
   flagged the `Discriminator` error.)

## Verdict

**HARDENED.** Six blocks, five hardens, one nit — all patched in place. The
story's goal, scope, and ADR tracing were never in question; the failures were
all guessed-codebase-fact and thin-test issues. The story is now ready for
`phase-story-executor`.
