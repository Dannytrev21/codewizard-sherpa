# Story S1-02 — `PlanProposal` closed discriminated union

**Step:** Step 1 — Establish Phase-4 type substrate + path-scoped fence amendment
**Status:** HARDENED
**Effort:** M
**Depends on:** S1-01
**ADRs honored:** ADR-0001 (`PlanProposal` is THE closed sum type the LLM may emit), ADR-0004 (`PlanProposal` is the LLM-output shape; `PlanOutcome` wraps `RecipeOutcome` separately — this story does NOT widen any Phase-3 sum type)

## Validation notes

Validated: 2026-05-21
Verdict: HARDENED
Findings addressed: 20 — 4 blocks, 10 hardens, 6 nits. One critic conflict resolved (see F-conflict).

Changes applied:
- **F1 (block)** — `SandboxedRelativePath` **does not exist** anywhere in `src/codegenie/` (grep-confirmed 2026-05-21). The story, S1-01's out-of-scope, and `phase-arch-design.md §Data model` all wrongly assume it is a Phase-3-owned newtype. The only real path type is `codegenie.plugins.sandbox_path.SandboxedPath` — a *jailed capability* minted by the sandbox at construction, **not** a value an LLM can emit as a JSON string at the SDK boundary. S1-01 (still `HARDENED`, unexecuted) closed without it. Resolution: **S1-02 defines `SandboxedRelativePath` itself**, locally in `plan_proposal.py` as `Annotated[str, AfterValidator(...)]` — a sibling of `UnifiedDiff`, for the identical reason (`UnifiedDiff` is deliberately *not* a `NewType` because a validator must fire on every Pydantic construction; `manifest_path` smart-construction has the same requirement). New AC-12 added. This avoids touching the fenced `identifiers.__all__` surface. Arch §Data model + S1-01 out-of-scope should be corrected for accuracy — flagged for follow-up, not edited by this validator.
- **F2 (block)** — AC-2's "`Field(discriminator=...)` is v1, `Discriminator(...)` is v2" premise is **factually wrong**. In Pydantic v2 both forms are valid; `Field(discriminator="kind")` is the codebase's settled convention — 7+ shipped, tested discriminated unions use it (`indices/freshness.py`, `probes/_shared/scanner_outcome.py`, `probes/layer_c/_sbom_models.py`, `scenario_result.py` ×3, `probes/layer_c/_cve_models.py`, `plugins/bundle.py`). `Discriminator(...)` is a v2 construct for *callable* discriminators, not needed here. Per Rule 11 (match conventions) the story now prescribes `Field(discriminator="kind")`. The phantom "Rule-7 conflict" Out-of-scope bullet is removed. `assert_never` exhaustiveness over a `Field(discriminator=...)` union is already proven in-repo by `tests/unit/indices/test_freshness_assert_never.py`.
- **F3 (block)** — AC-6 `test_schema_lists_exactly_four_tags` had an escape hatch (`... or len(tags) == 4`): a schema with four *wrong* tags, or with the four canonical tags **plus a spurious fifth**, passed. Rewritten to strict set-equality against `{dep_bump, override, callsite_rewrite, refuse}`.
- **F4 (block)** — AC-7 `test_mypy_strict_rejects_incomplete_match` asserted only `returncode != 0`; mypy failing for an unrelated reason (import-resolution error, missing stubs) green-washed the test while proving nothing about exhaustiveness. Now asserts an exhaustiveness diagnostic substring in stdout (mirrors sibling S1-01's `test_phase4_identifiers_mypy_negative.py` discipline).
- **F5 (harden)** — `SemverString` does not exist; the real Phase-3 type is `SemverVersion` (`NewType("SemverVersion", str)` at `identifiers.py:129`, smart constructor `parse_semver`). Renamed throughout AC-3, References, Out-of-scope, TDD plan.
- **F6 (harden)** — `manifest_path` had no standalone path-escape validation. AC-12's `SandboxedRelativePath` smart constructor supplies it; AC-5 gains `manifest_path` sad-path tests (`../../etc/passwd`, absolute path, empty).
- **F7 (harden)** — AC-4: `--- /dev/null` new-file-creation diffs are now explicitly rejected (`callsite_rewrite` modifies existing files only) instead of failing with a confusing `/dev/null`-not-in-`files` path-escape error.
- **F8 (harden)** — AC-4: CRLF (`\r`) in a diff is now explicitly rejected; a trailing `\r` on a `+++ b/<path>` line would otherwise smuggle past the path-extraction parser.
- **F9 (harden)** — AC-5 sad-path tests asserted only `pytest.raises(ValidationError)` — a diff rejected for the *wrong* reason passed. Each rejection test now asserts a distinctive keyword in the error; validators must raise stable, distinct messages.
- **F10 (harden)** — added 64 KB boundary tests: exactly 65 536 bytes accepted, 65 537 rejected (catches `>=` vs `>`).
- **F11 (harden)** — `test_discriminator_routes` asserted only `isinstance`; an implementation that routes correctly but drops/defaults fields passed. Now asserts non-`kind` field values.
- **F12 (harden)** — added a data round-trip property: every valid variant survives `model_validate(json.loads(json.dumps(model_dump(mode="json"))))`.
- **F13 (harden)** — Goal / AC-2 / AC-6 prose said `PlanProposal.model_json_schema()`, but `PlanProposal` is an `Annotated[...]` alias with no such method — it would `AttributeError`. Corrected to `TypeAdapter(PlanProposal).json_schema()` (the TDD plan's test code was already correct).
- **F14 (harden)** — AC-6 gains a lightweight SDK-shape structural check (schema is a JSON-serializable `dict` carrying a `discriminator` block; no Pydantic-internal keys). Full SDK wiring stays S3-02.
- **F15 (nit)** — Notes: lift `ConfigDict(frozen=True, extra="forbid")` to a module-level `Final` constant referenced by all four variants (single-source; not an AC — not externally observable).
- **F16 (nit)** — Notes: `PlanProposalRefuse.reason` inline `Literal` is intentional per Rule 2; promote to `StrEnum` only if multi-site branching emerges.
- **F17 (nit)** — embedded test signatures annotated to match the repo convention (`tests/unit/probes/layer_c/test_scenario_result.py` is fully annotated).
- **F18 (nit)** — Notes: the mypy meta-test should `pytest.importorskip`/skip when mypy is absent, so a missing install surfaces as a skip rather than a false pass/fail.
- **F19 (nit)** — Notes: the `test_no_rationale_in_prompts.py` skeleton catches only f-strings (`JoinedStr`); S2-04 must extend it to `str.format` and `%`-formatting before declaring the guard production-ready.
- **F20 (nit)** — arch edge-case citations corrected: the real arch table rows are **#8** (>64 KB cap) and **#15** (path escape); binary-content and no-op rejections are story-level smart-constructor hardening beyond the arch edge table (no #20/#21/#22 exist).
- **F-conflict** — the Coverage critic proposed a *bidirectional* path check (every `files` entry must also appear in the diff). Rejected: `phase-arch-design.md §Data model` line 734 explicitly specifies `paths ⊆ files` (subset, not equality) — Consistency outranks Coverage. AC-4 keeps the one-directional subset check; the arch's `⊆` is honored verbatim.

Full audit log: docs/phases/04-vuln-llm-fallback-rag/stories/_validation/S1-02-plan-proposal-closed-union.md

## Context

Phase 4's load-bearing structural choice is that **the LLM emits exactly one of four named shapes** — `dep_bump`, `override`, `callsite_rewrite`, `refuse` — validated at the Anthropic SDK boundary via `response_format=TypeAdapter(PlanProposal).json_schema()` before bytes ever reach Python (ADR-0001). The closed Pydantic v2 discriminated union is the type-level firewall: an injected LLM cannot structurally emit a shell command, an `rm -rf`, or unfenced markdown. The 64 KB `UnifiedDiff` cap and path-escape rejection inside the `callsite_rewrite` variant are the smart-constructor controls the critic surfaced as load-bearing — the synthesis ledger upgraded the cap from 32 KB after evidence the headline major-bump fixture (`express-cve-2026-1234`) regularly produces ≥ 40 KB diffs.

## References — where to look

- **Architecture:**
  - `../phase-arch-design.md §Component design — PlanProposal (Component 2)` — variant declarations. (The arch shows `Discriminator("kind")`; this story uses the codebase idiom `Field(discriminator="kind")` instead — see F2. The arch doc should be corrected for accuracy.)
  - `../phase-arch-design.md §Data model` — full `PlanProposal*` model bodies; the `frozen=True, extra="forbid"` config. (Arch shows `Annotated[..., Discriminator("kind")]`; superseded by `Field(discriminator="kind")` per F2.)
  - `../phase-arch-design.md §Edge cases` #8 (`> 64 KB` diff cap) and #15 (path-escape — file outside `files`). Binary-content rejection and no-op-diff rejection are **story-level smart-constructor hardening** beyond the arch edge table (no rows #20/#21/#22 exist — the story's original citation was wrong; F20).
  - `../phase-arch-design.md §Testing strategy → Property tests` — `test_plan_proposal_schema_totality.py`.
- **Phase ADRs (rules this story must honor):**
  - `../ADRs/0001-plan-proposal-closed-sum-type.md` — `Tagged union + Smart constructor + Make illegal states unrepresentable`; `model_construct()` forbidden; rationale audit-log-only.
  - `../ADRs/0004-plan-outcome-wraps-recipe-outcome.md` — `PlanProposal` is independent from `PlanOutcome`; this story must not introduce coupling.
- **Production ADRs:**
  - `../../../production/adrs/0033-domain-modeling-discipline.md` — newtype + smart constructor + sum type + illegal-states-unrepresentable.
- **Source design:**
  - `../final-design.md §Component 2 — PlanProposal` — variant rationale.
- **Existing code (READ BEFORE WRITING — Rule 8):**
  - **Discriminated-union idiom — settled (F2).** The codebase convention is `Annotated[A | B | ..., Field(discriminator="kind")]` — used by **7+ shipped, tested** discriminated unions: `src/codegenie/indices/freshness.py:110`, `src/codegenie/probes/_shared/scanner_outcome.py:136`, `src/codegenie/probes/layer_c/_sbom_models.py:70`, `src/codegenie/probes/layer_c/scenario_result.py` (×3), `src/codegenie/probes/layer_c/_cve_models.py:70`, `src/codegenie/plugins/bundle.py:268`. This story uses `Field(discriminator="kind")` to match (Rule 11). The story's original "`Field(discriminator=...)` is v1, surface a Rule-7 conflict, pick `Discriminator(...)`" framing was factually wrong — in Pydantic v2 *both* forms are valid; `Discriminator(...)` exists for *callable* discriminators (not needed here). There is no v1/v2 conflict to surface. `assert_never` exhaustiveness over a `Field(discriminator=...)` union is already proven in-repo by `tests/unit/indices/test_freshness_assert_never.py`.
  - `src/codegenie/types/identifiers.py` — only `PackageId` (`NewType("PackageId", str)`) and `SemverVersion` (`NewType("SemverVersion", str)`, line ~129, with smart constructor `parse_semver` in `parsers.py`) exist and are Phase-3-owned — **re-use** these. `SandboxedRelativePath` **does not exist** (the closest type, `codegenie.plugins.sandbox_path.SandboxedPath`, is a jailed *capability*, not an LLM-emittable string) — **this story defines it** locally in `plan_proposal.py` (AC-12). The story's original `SemverString` name was wrong; the real name is `SemverVersion` (F5).

## Goal

Ship the `PlanProposal` closed Pydantic v2 discriminated union (`dep_bump | override | callsite_rewrite | refuse`) at `src/codegenie/fallback/plan_proposal.py` with `UnifiedDiff` smart-constructor enforcing 64 KB cap + path-escape rejection + binary rejection, so every later Phase-4 module consumes the typed shape and the Anthropic SDK can be passed `TypeAdapter(PlanProposal).json_schema()` as `response_format`. (`PlanProposal` is an `Annotated[...]` union alias, **not** a `BaseModel` — it has no `.model_json_schema()` method; the schema is produced via `TypeAdapter`. S3-02 wires the schema into the actual SDK call.)

## Acceptance criteria

- [ ] AC-1 — `src/codegenie/fallback/plan_proposal.py` ships four `BaseModel` subclasses (`PlanProposalDepBump`, `PlanProposalOverride`, `PlanProposalCallsiteRewrite`, `PlanProposalRefuse`), all with `model_config = ConfigDict(frozen=True, extra="forbid")`. Each carries a `kind: Literal[<tag>]` discriminator field with a default matching the tag.
- [ ] AC-2 — `PlanProposal = Annotated[PlanProposalDepBump | PlanProposalOverride | PlanProposalCallsiteRewrite | PlanProposalRefuse, Field(discriminator="kind")]` is exported. The `Field(discriminator="kind")` idiom is used — it is the codebase-wide convention for discriminated unions (7+ shipped instances; see References) and Rule 11 mandates conformance. The `Discriminator("kind")` callable form is **not** used (it exists for callable discriminators, which this story does not need). There is no v1/v2 conflict to surface — both forms are valid Pydantic v2; the story's original premise was wrong (F2). (validator: rewritten — F2.)
- [ ] AC-3 — Variant fields match arch §Data model. `SandboxedRelativePath` is defined by this story (AC-12); `PackageId` and `SemverVersion` are consumed from `codegenie.types.identifiers` (Phase-3-owned — F5: the story's original `SemverString` name was wrong, the real newtype is `SemverVersion`):
  - `PlanProposalDepBump`: `kind`, `manifest_path: SandboxedRelativePath`, `package: PackageId`, `target_version: SemverVersion`, `rationale: Annotated[str, Field(max_length=2048)]`.
  - `PlanProposalOverride`: `kind`, `manifest_path: SandboxedRelativePath`, `package: PackageId`, `forced_version: SemverVersion`, `rationale: Annotated[str, Field(max_length=2048)]`.
  - `PlanProposalCallsiteRewrite`: `kind`, `manifest_path: SandboxedRelativePath`, `files: list[SandboxedRelativePath]` (non-empty, `Field(min_length=1)`), `diff: UnifiedDiff`, `rationale: Annotated[str, Field(max_length=2048)]`.
  - `PlanProposalRefuse`: `kind`, `reason: Literal["out_of_scope", "insufficient_context", "policy_block"]`, `rationale: Annotated[str, Field(max_length=2048)]`.
- [ ] AC-4 — `UnifiedDiff` is a Pydantic-validated newtype (not a `NewType`-as-`str`) implemented as `Annotated[str, AfterValidator(...)]`. Each rejection below MUST raise with a **distinct, stable error message** (a keyword the sad-path tests in AC-5 assert on — F9): a diff rejected for the wrong reason must not silently pass a test targeting a different reason. Smart-constructor rejects:
  - **Length > 64 KB** — `len(diff.encode("utf-8")) > 65_536` → `ValidationError`. The boundary is strict `>`: exactly `65_536` bytes is **accepted**, `65_537` is **rejected** (AC-5 pins both — F10). Message keyword: `64 KB` / `exceeds`.
  - **Binary content** (any non-UTF-8 byte → `ValidationError`). Message keyword: `binary`.
  - **Path escape** — every `+++ b/<path>` / `--- a/<path>` line's path **must appear in the parent `files` list** (`diff paths ⊆ files`, per arch §Data model line 734 — subset, *not* equality; `files` MAY legitimately list more than the diff touches). Validator runs at the `PlanProposalCallsiteRewrite` model level so it sees `files` + `diff` together — Pydantic v2 `@model_validator(mode="after")`. Message keyword: `path` / `escape`.
  - **No-op diff** (zero `+`/`-` data lines after the header) → `ValidationError`. (Arch §Edge cases — no-op treated as `Refuse`.) Message keyword: `no-op`.
  - **Empty diff string** → `ValidationError`. Message keyword: `empty`.
  - **New-file creation** — a diff carrying a `--- /dev/null` marker is rejected (`callsite_rewrite` modifies *existing* files only; F7). This is checked explicitly so the implementer does not hit a confusing `/dev/null`-not-in-`files` path-escape error. Message keyword: `new file` / `/dev/null`.
  - **CRLF line endings** — a diff containing any `\r` byte is rejected (F8); a trailing `\r` on a `+++ b/<path>` line would otherwise smuggle a path past the extraction parser. Message keyword: `CRLF` / `carriage return`.
- [ ] AC-5 — `tests/unit/fallback/test_plan_proposal.py` covers happy + sad paths for every variant. Every sad-path `UnifiedDiff`/`SandboxedRelativePath` test asserts a **distinctive keyword in the `ValidationError`** (F9) — not bare `pytest.raises(ValidationError)` — so a rejection for the wrong reason fails the test:
  - Happy: each variant constructs from a valid dict via `Model.model_validate(payload)`; the discriminator routes to the correct class **and** the routed object's non-`kind` fields equal the input (F11 — not just `isinstance`).
  - Happy — boundary: a `callsite_rewrite` whose `diff` is exactly `65_536` UTF-8 bytes constructs successfully (F10).
  - Sad — discriminator: unknown `kind` value (`"shell_command"`) raises `ValidationError`.
  - Sad — `extra="forbid"`: extra keys (`{"kind": "dep_bump", ..., "shell": "rm"}`) raise.
  - Sad — `frozen=True`: `model.manifest_path = "x"` raises `ValidationError`.
  - Sad — `rationale > 2048 chars` raises.
  - Sad — `PlanProposalCallsiteRewrite` with `files=[]` raises (`min_length=1`).
  - Sad — `manifest_path` validation (F6): `manifest_path="../../etc/passwd"`, `manifest_path="/etc/passwd"` (absolute), and `manifest_path=""` (empty) each raise `ValidationError` (these exercise the `SandboxedRelativePath` smart constructor from AC-12).
  - Sad — `UnifiedDiff` `65_537` bytes raises (one byte over the cap — F10); error keyword `exceeds`/`64 KB`.
  - Sad — `UnifiedDiff` with a `+++ b/../../etc/passwd` line where `files` does not include `../../etc/passwd` raises (path escape); error keyword `path`/`escape`.
  - Sad — `UnifiedDiff` carrying non-UTF-8 bytes (binary header) raises; error keyword `binary`.
  - Sad — `UnifiedDiff` empty raises (keyword `empty`); no-op raises (keyword `no-op`).
  - Sad — `UnifiedDiff` with a `--- /dev/null` new-file marker raises (F7); error keyword `new file`/`/dev/null`.
  - Sad — `UnifiedDiff` containing `\r\n` line endings raises (F8); error keyword `CRLF`/`carriage return`.
- [ ] AC-6 — **Schema-totality property** (`tests/property/test_plan_proposal_schema_totality.py`). The schema is produced via `TypeAdapter(PlanProposal).json_schema()` — `PlanProposal` is an `Annotated[...]` alias with no `.model_json_schema()` method (F13):
  - `json.loads(json.dumps(TypeAdapter(PlanProposal).json_schema()))` is a no-op (round-trippable).
  - The schema names **exactly** the four tags `{dep_bump, override, callsite_rewrite, refuse}` via strict set-equality on `schema["discriminator"]["mapping"]` keys — `set(mapping) == {…}`, **not** a `len(...) == 4` count (F3 — a four-wrong-tags or four-canonical-plus-a-fifth schema must fail).
  - `TypeAdapter(PlanProposal).json_schema()` is **idempotent across calls** (two calls deep-equal).
  - **SDK-shape structural check** (F14): the schema is a plain JSON-serializable `dict` carrying a `discriminator` block (with a `mapping`) and a `$defs`/`oneOf` member set; it contains **no** Pydantic-internal keys (no key starting with `__pydantic` or named `__pydantic_core_schema__`). This is a lightweight smoke test that the output is structurally the kind of thing the Anthropic `response_format` parameter accepts; full SDK wiring stays S3-02.
  - **Data round-trip property** (F12): for every variant, a valid constructed instance survives `model_validate(json.loads(json.dumps(instance.model_dump(mode="json"))))` and re-equals the original — catches asymmetric serializer/deserializer bugs.
- [ ] AC-7 — **`assert_never` exhaustiveness via subprocess mypy** (`tests/property/test_plan_proposal_match_exhaustive.py`):
  - Writes a temp file with `match plan: case PlanProposalDepBump(): ...` covering three of four arms + `case _ as never: assert_never(never)` (parametrized over each omitted variant) and asserts (a) `mypy --strict` exits non-zero **and** (b) `result.stdout` contains an exhaustiveness diagnostic — at least one of `argument 1 to "assert_never"`, `unreachable`, `Missing` (F4). Asserting only `returncode != 0` is insufficient: mypy failing for an unrelated reason (import-resolution error, missing stubs) would green-wash the test. This mirrors sibling S1-01's `test_phase4_identifiers_mypy_negative.py`, which already asserts on stdout substrings.
  - Writes a complete `match` (all four arms) and asserts `mypy --strict` exits 0 with no error on stdout.
  - The test `pytest.importorskip("mypy")` (or equivalent skip when `python -m mypy --version` is unavailable) so a missing mypy install surfaces as a skip, not a confusing pass/fail (F18).
  - This is the load-bearing test that catches a future `Refuse`-arm regression at planner-fold-in time (arch §Risks specific to this step §2 — mypy --strict is the only place exhaustiveness is enforced).
- [ ] AC-8 — `model_construct` is forbidden in production code under `src/codegenie/fallback/` and `src/codegenie/rag/`. Test `tests/fence/test_phase4_no_model_construct.py` AST-walks both directories (handling `not yet existent`) and asserts no `*.model_construct(` callsite. Skeleton lands here; coverage grows as later stories add code.
- [ ] AC-9 — **Rationale-discipline AST guard** (`tests/fence/test_no_rationale_in_prompts.py`): walks `src/codegenie/fallback/` and asserts `PlanProposal*.rationale` is **never** read into a string that flows into `prompt_builder.build(...)` (no `f"... {plan.rationale} ..."` patterns under `fallback/`). Skeleton lands here (S2-04 will exercise it).
- [ ] AC-10 — `PlanProposal` is exported from `src/codegenie/fallback/__init__.py`; the four variant classes are also exported individually.
- [ ] AC-11 — `mypy --strict src/codegenie/fallback/` clean. `ruff check`, `ruff format --check` clean. The TDD plan's red test exists, was committed, and is green.
- [ ] AC-12 — **`SandboxedRelativePath` is defined by this story** (F1 — it does not exist in the codebase; `phase-arch-design.md §Data model` and S1-01's out-of-scope wrongly call it "Phase-3-owned"). It is `Annotated[str, AfterValidator(_validate_sandboxed_relative_path)]` in `src/codegenie/fallback/plan_proposal.py` — a sibling of `UnifiedDiff`, for the identical reason (`UnifiedDiff` is deliberately not a `NewType` because a validator must fire on every Pydantic construction; `manifest_path` smart-construction has the same requirement, and the LLM emits it as a raw JSON string at the SDK boundary). It is **not** added to `codegenie.types.identifiers` (that would touch the fenced `__all__` surface and require the S1-01-style cross-file reconciliation; a Pydantic-validated `Annotated` type cannot be a bare `NewType` anyway). The pure helper `_validate_sandboxed_relative_path(value: str) -> str` rejects, each with a distinct message:
  - **empty string**, **absolute path** (leading `/`), any **`..` path segment** (traversal), any **NUL byte** (`\x00`), and any **backslash** (`\\` — Windows separators are not accepted; reject rather than normalize).
  - A valid relative path (e.g. `package.json`, `src/app.ts`) passes through unchanged.
  `SandboxedRelativePath` is exported from `src/codegenie/fallback/__init__.py` alongside `UnifiedDiff`. Note: `SandboxedRelativePath` is distinct from the Phase-3 `SandboxedPath` capability (`codegenie.plugins.sandbox_path.SandboxedPath`) — that is an absolute, jail-minted capability, unsuitable as an LLM-emitted JSON value. `tests/unit/fallback/test_plan_proposal.py` covers happy + sad paths for `_validate_sandboxed_relative_path` directly (the helper is pure and testable in isolation). (validator: added — F1.)

## Implementation outline

1. Create `src/codegenie/fallback/__init__.py` and `src/codegenie/fallback/plan_proposal.py`.
2. Import `PackageId` and `SemverVersion` from `codegenie.types.identifiers` (Phase-3-owned — verified present 2026-05-21). **Do not** import `SandboxedRelativePath` — it does not exist; this story defines it (step 3a).
3. Define `UnifiedDiff` as `Annotated[str, AfterValidator(_validate_unified_diff)]`. The helper enforces, with a distinct message per failure: empty, CRLF (`\r`), binary (non-UTF-8), `> 64 KB`, no-op, and `--- /dev/null` new-file marker (AC-4). The path-escape check needs `files`, so it is a separate Pydantic `@model_validator(mode="after")` on `PlanProposalCallsiteRewrite` running `_validate_diff_paths_in_files(diff, files)` (`diff paths ⊆ files`). All validators are pure module-level helpers, testable independently (functional core).
3a. Define `SandboxedRelativePath = Annotated[str, AfterValidator(_validate_sandboxed_relative_path)]` (AC-12) — sibling of `UnifiedDiff`, in the same module. The helper rejects empty, absolute (`/`-leading), `..` segments, NUL bytes, and backslashes.
4. Define the four `PlanProposal*` `BaseModel` subclasses per arch §Data model. Lift `ConfigDict(frozen=True, extra="forbid")` to a module-level `_FROZEN_FORBID: Final` constant referenced by all four (F15). Order matters for readability; `Refuse` last.
5. Export `PlanProposal = Annotated[..., Field(discriminator="kind")]` — the codebase-wide idiom (F2; **not** `Discriminator("kind")`).
6. Add the variants, `PlanProposal`, `UnifiedDiff`, and `SandboxedRelativePath` to `src/codegenie/fallback/__init__.py`.
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
from pydantic import TypeAdapter, ValidationError

from codegenie.fallback.plan_proposal import (
    PlanProposal,
    PlanProposalCallsiteRewrite,
    PlanProposalDepBump,
    PlanProposalOverride,
    PlanProposalRefuse,
    SandboxedRelativePath,
    UnifiedDiff,
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
def test_discriminator_routes(
    payload: dict[str, object], expected_cls: type[object]
) -> None:
    # F11 — assert routed class AND that every input field survived. An
    # implementation that routes correctly but drops/defaults a field
    # (manifest_path -> "", rationale -> "") must fail here.
    obj = TypeAdapter(PlanProposal).validate_python(payload)
    assert isinstance(obj, expected_cls)
    for key, value in payload.items():
        assert getattr(obj, key) == value, f"field {key} not preserved"


# --- Discriminator rejects unknown tag (AC-5 sad) ---

def test_unknown_kind_rejected() -> None:
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


# --- UnifiedDiff rejections (AC-4 / AC-5) ---
#
# Each sad-path test asserts a DISTINCTIVE keyword in the error (F9): a diff
# rejected for the wrong reason must not green-wash a test targeting another.

def _err_text(exc: ValidationError) -> str:
    return " ".join(e["msg"].lower() for e in exc.errors())


def _bytes_header() -> str:
    return "--- a/src/app.ts\n+++ b/src/app.ts\n@@ -1 +1 @@\n-x\n+"


def test_diff_at_64kb_boundary_accepted() -> None:
    # F10 — exactly 65_536 UTF-8 bytes is ACCEPTED (boundary is strict `>`).
    header = _bytes_header()
    diff = header + "y" * (65_536 - len(header.encode()) - 1) + "\n"
    assert len(diff.encode()) == 65_536
    obj = PlanProposalCallsiteRewrite.model_validate({**VALID_CALLSITE, "diff": diff})
    assert isinstance(obj, PlanProposalCallsiteRewrite)


def test_diff_one_byte_over_boundary_rejected() -> None:
    # F10 — 65_537 bytes is REJECTED (catches a `>=` vs `>` mutation).
    header = _bytes_header()
    diff = header + "y" * (65_537 - len(header.encode()) - 1) + "\n"
    assert len(diff.encode()) == 65_537
    with pytest.raises(ValidationError) as exc:
        PlanProposalCallsiteRewrite.model_validate({**VALID_CALLSITE, "diff": diff})
    assert "64 kb" in _err_text(exc.value) or "exceeds" in _err_text(exc.value)


def test_diff_path_escape_rejected() -> None:
    bad = "--- a/../../etc/passwd\n+++ b/../../etc/passwd\n@@ -1 +1 @@\n-x\n+y\n"
    payload = {**VALID_CALLSITE, "files": ["src/app.ts"], "diff": bad}
    with pytest.raises(ValidationError) as exc:
        PlanProposalCallsiteRewrite.model_validate(payload)
    assert "path" in _err_text(exc.value) or "escape" in _err_text(exc.value)


def test_no_op_diff_rejected() -> None:
    no_op = "--- a/src/app.ts\n+++ b/src/app.ts\n@@ -1 +1 @@\n unchanged\n"
    with pytest.raises(ValidationError) as exc:
        PlanProposalCallsiteRewrite.model_validate({**VALID_CALLSITE, "diff": no_op})
    assert "no-op" in _err_text(exc.value)


def test_empty_diff_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        PlanProposalCallsiteRewrite.model_validate({**VALID_CALLSITE, "diff": ""})
    assert "empty" in _err_text(exc.value)


def test_new_file_diff_rejected() -> None:
    # F7 — `--- /dev/null` new-file creation is not allowed for callsite_rewrite.
    new_file = "--- /dev/null\n+++ b/src/app.ts\n@@ -0,0 +1 @@\n+x\n"
    with pytest.raises(ValidationError) as exc:
        PlanProposalCallsiteRewrite.model_validate({**VALID_CALLSITE, "diff": new_file})
    assert "new file" in _err_text(exc.value) or "/dev/null" in _err_text(exc.value)


def test_crlf_diff_rejected() -> None:
    # F8 — CRLF line endings are rejected (a trailing \r could smuggle a path).
    crlf = GOOD_DIFF.replace("\n", "\r\n")
    with pytest.raises(ValidationError) as exc:
        PlanProposalCallsiteRewrite.model_validate({**VALID_CALLSITE, "diff": crlf})
    assert "crlf" in _err_text(exc.value) or "carriage return" in _err_text(exc.value)


# --- manifest_path / SandboxedRelativePath rejections (AC-5 / AC-12, F6) ---

@pytest.mark.parametrize("bad_path", ["../../etc/passwd", "/etc/passwd", ""])
def test_manifest_path_rejected(bad_path: str) -> None:
    with pytest.raises(ValidationError):
        PlanProposalDepBump.model_validate({**VALID_DEP_BUMP, "manifest_path": bad_path})


@pytest.mark.parametrize(
    "bad_path", ["../escape", "/abs", "", "with\x00nul", "back\\slash"]
)
def test_sandboxed_relative_path_rejects(bad_path: str) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(SandboxedRelativePath).validate_python(bad_path)


@pytest.mark.parametrize("ok_path", ["package.json", "src/app.ts", "a/b/c.txt"])
def test_sandboxed_relative_path_accepts(ok_path: str) -> None:
    assert TypeAdapter(SandboxedRelativePath).validate_python(ok_path) == ok_path


# --- Data round-trip property (AC-6 / F12) ---

@pytest.mark.parametrize(
    "payload", [VALID_DEP_BUMP, VALID_OVERRIDE, VALID_CALLSITE, VALID_REFUSE]
)
def test_json_round_trip_identity(payload: dict[str, object]) -> None:
    adapter = TypeAdapter(PlanProposal)
    obj = adapter.validate_python(payload)
    again = adapter.validate_python(json.loads(json.dumps(obj.model_dump(mode="json"))))
    assert again == obj
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


def test_schema_lists_exactly_four_tags() -> None:
    # AC-6 / F3 — STRICT set equality. Pydantic v2 emits discriminator.mapping
    # for a Field(discriminator="kind") closed union. No `len(...) == 4` escape
    # hatch: four wrong tags, or four canonical + a spurious fifth, must FAIL.
    schema = TypeAdapter(PlanProposal).json_schema()
    mapping = schema.get("discriminator", {}).get("mapping", {})
    assert set(mapping) == {"dep_bump", "override", "callsite_rewrite", "refuse"}, (
        f"discriminator mapping must be exactly the four tags; got {set(mapping)}"
    )


def test_schema_is_sdk_shaped() -> None:
    # AC-6 / F14 — lightweight structural smoke test for SDK response_format.
    schema = TypeAdapter(PlanProposal).json_schema()
    assert isinstance(schema, dict)
    assert "discriminator" in schema and "mapping" in schema["discriminator"]
    assert "$defs" in schema or "oneOf" in schema
    # No Pydantic-internal keys may leak into an SDK-bound schema.
    assert "__pydantic" not in json.dumps(schema), (
        "Pydantic-internal key leaked into the JSON schema"
    )


def test_schema_is_idempotent() -> None:
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


pytest.importorskip("mypy")  # F18 — missing mypy => skip, not a false pass/fail.

# F4 — substrings proving the failure is the EXHAUSTIVENESS diagnostic, not an
# unrelated mypy error (import resolution, missing stubs). assert_never's arg is
# typed `Never`; an unhandled variant makes mypy flag the assert_never call.
_EXHAUSTIVENESS_MARKERS = ("assert_never", "unreachable", "missing")


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
    out = result.stdout.lower()
    assert any(m in out for m in _EXHAUSTIVENESS_MARKERS), (
        f"mypy failed but not for an exhaustiveness reason (missing {omit}); "
        f"stdout:\n{result.stdout}"
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
    assert "error:" not in result.stdout.lower(), result.stdout
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
- Create `src/codegenie/fallback/plan_proposal.py` with the four `BaseModel` subclasses + `UnifiedDiff` + `SandboxedRelativePath` validators + `PlanProposal = Annotated[..., Field(discriminator="kind")]` (the codebase idiom — F2).
- Implement `_validate_unified_diff(value: str) -> str` (empty, CRLF, UTF-8/binary, length, no-op, `--- /dev/null`), `_validate_sandboxed_relative_path(value: str) -> str` (empty, absolute, `..`, NUL, backslash), and `_validate_diff_paths_in_files(self) -> Self` (`@model_validator(mode="after")`). Each rejection raises with a distinct, stable message keyword (AC-4).
- Wire variants, `UnifiedDiff`, and `SandboxedRelativePath` into `src/codegenie/fallback/__init__.py`.

### Refactor — clean up

- Lift the 64 KB cap to a module-level `Final` constant `_MAX_DIFF_BYTES: Final[int] = 65_536` with a comment naming ADR-0001 + the synthesis-ledger 32 KB → 64 KB upgrade.
- Lift the `rationale` length cap (`2048`) to `_MAX_RATIONALE_CHARS: Final[int]`.
- Lift `ConfigDict(frozen=True, extra="forbid")` to a module-level `_FROZEN_FORBID: Final` constant referenced by all four variants (F15 — single-source the config).
- Docstring each variant naming the LLM emission semantics (`"""LLM emits this when the patch is a manifest-only version bump; ADR-0001."""`).
- Edge cases enumerated in arch §Edge cases that touch this code: #8 (>64 KB cap), #15 (path escape). Binary-content and no-op rejections are story-level hardening beyond the arch edge table (F20).
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
- **Wiring the schema into the Anthropic SDK `response_format` parameter** — S3-02 wires `TypeAdapter(PlanProposal).json_schema()` into the SDK call. This story only produces and shape-tests the schema.
- **`assert_never`-exhaustive consumer code** — S6-01 (`FallbackTier`) is the first consumer; this story's exhaustiveness test is meta-test infrastructure.
- **The fence amendment admitting `anthropic`/`chromadb`/`fastembed`/`onnxruntime`** — S1-05.
- **`PackageId` / `SemverVersion` definitions** — Phase-3-owned (`codegenie.types.identifiers`); this story consumes them. **`SandboxedRelativePath` is NOT out of scope** — it does not exist and this story defines it (AC-12); the original "Phase-3-owned" assumption was wrong (F1).

## Notes for the implementer

- **Discriminated-union idiom is settled — use `Field(discriminator="kind")` (F2).** It is the codebase-wide convention (7+ shipped unions; see References) and Rule 11 mandates conformance. Do **not** use `Discriminator("kind")` — that v2 construct exists for *callable* discriminators, which this story does not need. The story's original belief that `Field(discriminator=...)` is "Pydantic v1" is wrong: in v2 both forms are valid, and `Field(discriminator=...)` is the recommended form for a plain string discriminator. There is no Rule-7 conflict to surface. `assert_never` exhaustiveness over such a union is already proven in-repo by `tests/unit/indices/test_freshness_assert_never.py`.
- **`UnifiedDiff` and `SandboxedRelativePath` are NOT `NewType`s.** A `NewType("X", str)` would have no validator; the smart-constructor controls must fire on every Pydantic construction (the LLM emits both as raw JSON strings at the SDK boundary). Use `Annotated[str, AfterValidator(...)]` for both — pure-`str` carrier; Pydantic enforces the validator on every model field of that type. This is also why `SandboxedRelativePath` lives in `plan_proposal.py` and not `codegenie.types.identifiers` (an `Annotated`-validated type cannot be a bare `NewType`, and adding to `identifiers.__all__` would force the S1-01-style fenced-surface reconciliation).
- **`SandboxedRelativePath` is defined by this story, not consumed (F1).** It does not exist anywhere in `src/codegenie/`. The arch §Data model and S1-01's out-of-scope wrongly call it "Phase-3-owned" — that is a documentation error (recommend both be corrected). The only real path type, `codegenie.plugins.sandbox_path.SandboxedPath`, is a jail-minted *absolute capability* — unusable as an LLM-emitted relative-path string. Define `SandboxedRelativePath` per AC-12.
- **`SemverString` does not exist — the Phase-3 newtype is `SemverVersion` (F5).** `NewType("SemverVersion", str)` at `codegenie/types/identifiers.py` (~line 129), smart constructor `parse_semver` in `parsers.py`. Import `SemverVersion`; do not invent `SemverString`.
- **Lift `ConfigDict(frozen=True, extra="forbid")` to a module-level `_FROZEN_FORBID: Final` constant (F15)** referenced by all four variant classes — single-source the config (same reasoning as lifting the numeric caps). Not an AC (not externally observable), but do it in the Refactor step.
- **`PlanProposalRefuse.reason` stays an inline `Literal` (F16).** Three members, one field site — inline `Literal` is correct per Rule 2 ("three similar lines beat premature abstraction"). Promote to a `StrEnum` only if Phase-4 consumers begin `match`-branching on it across multiple modules (extension by addition, at that point).
- **The exhaustiveness meta-test must `pytest.importorskip("mypy")` (F18)** so a missing mypy install surfaces as a skip, not a confusing pass (incomplete-match test) or fail (complete-match test).
- **Annotate every test function (`-> None`, typed params) (F17)** — the repo convention (`tests/unit/probes/layer_c/test_scenario_result.py` is fully annotated). The TDD-plan snippets above model this.
- **Path-escape check needs `files` context.** `UnifiedDiff` alone cannot validate paths because the allowed list lives on the parent model. Run the path-escape validator as `@model_validator(mode="after")` on `PlanProposalCallsiteRewrite` so `self.files` and `self.diff` are both available. The parser splits the diff on lines starting with `+++ b/` and `--- a/`; each extracted path must be in `set(self.files)` (raw string equality after stripping `a/`/`b/`).
- **No-op detection** is a count of lines starting with `+` or `-` (excluding the `+++`/`---` header lines); zero data-lines → no-op → reject. (Story-level hardening — no arch edge-table row; F20.)
- **Binary detection** is `value.encode("utf-8")` raising → `ValidationError`. Pydantic's default `str` validator already enforces UTF-8 on input, but the byte-length cap (`len(value.encode("utf-8")) > 65_536`) is the operative check.
- **`assert_never` exhaustiveness is mypy-strict-only.** The meta-test (`test_plan_proposal_match_exhaustive.py`) MUST subprocess `mypy --strict` to be load-bearing. README §Open implementation questions §5 calls this out explicitly. CI runs `make typecheck` (`mypy --strict src/`); this story's meta-test verifies `mypy --strict` is wired up correctly.
- **`PlanProposalRefuse.rationale` is audit-log-only.** Per ADR-0001 §Consequences, the `rationale` field is never re-prompted. The `test_no_rationale_in_prompts.py` skeleton lands here so S2-04's `PromptBuilder` is guarded the moment it lands. **F19 caveat:** the skeleton's AST heuristic catches only f-strings (`ast.JoinedStr`); `"...".format(plan.rationale)` and `"..." % plan.rationale` slip through. The skeleton is acceptable *as a skeleton* (no `fallback/` code reads `rationale` yet), but S2-04 MUST extend it to `str.format` call patterns and `%`-formatting before the guard is load-bearing.
- **Do not import `anthropic` here.** The path-scoped fence (S1-05) admits `anthropic` only under `src/codegenie/fallback/leaf/anthropic_adapter.py`. `plan_proposal.py` is pure Pydantic.
- **Newtypes-everywhere cross-cutting rule.** Every field naming a domain primitive is typed, never raw `str`: `manifest_path` / `files` → `SandboxedRelativePath` (defined by this story, AC-12), `package` → `PackageId` (Phase-3), `target_version` / `forced_version` → `SemverVersion` (Phase-3). The AST source-scan from S1-01 (`test_phase4_no_raw_str_for_domain_ids.py`) is the load-bearing guard once `fallback/` exists — its `_DOMAIN_KEYWORDS` roster includes `manifest_path` and `package`, so a raw-`str` annotation on either fails the fence. `SandboxedRelativePath` being `Annotated[str, ...]` (alias name `SandboxedRelativePath`, not bare `str`) passes the scan.
