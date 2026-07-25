# Validation report — S1-01 Phase-9 Newtype identifiers

**Date:** 2026-07-24
**Story:** `docs/phases/09-temporal-durable-workflow/stories/S1-01-durable-newtypes.md`
**Verdict:** HARDENED
**Skill:** phase-story-validator

## Context Brief (Stage 1)

Story S1-01 lands the Phase-9 catalog additions to the kernel-tier
`codegenie.types.identifiers` module and ships the typed-credential-class
registry at `codegenie.types.credentials` that Step-3's sanitizer will
consume. Every downstream Phase-9 story (`EventPayload` union, activity
registry, workflow body, Postgres schema, projection kernel) threads these
Newtypes simultaneously — `mypy --strict` is the primary correctness gate.

**Load-bearing references:**

- `phase-arch-design.md §Newtype identifiers (Contract)` (line 780) — the
  arch-listed 11 names include four already-shipped ones (`WorkflowId`,
  `EventId`, `BlobDigest`, `AttemptId`) and one closed-set literal-like
  (`TaskClassId`); the *new* Phase-9 additions are six, not seven.
- `phase-arch-design.md §Design patterns applied #3` — Newtype-for-domain
  identifiers is enforced across the phase; primitive obsession is a review
  blocker (production ADR-0033).
- `ADRs/0008-typed-credential-blocklist-not-regex.md` — `SECRET_TYPES` is the
  trust root of the sanitizer's load-bearing layer (b). Load-bearing.
- `production ADR-0033` — newtype/smart-constructor/sum-type discipline.
- `production ADR-0043` — extension by addition; loud, compiler-policed edits
  are the enforcement mechanism, not violations.
- `src/codegenie/types/identifiers.py` — Phase-1/2/3/4/6/7 catalog already
  present. The module-level registry is named **`_NEWTYPE_REGISTRY`** (not
  `_DEFINITIONS`); `AttemptId` and `TaskClassId` already exist and must not
  be redefined.
- `tests/unit/types/test_identifiers_phase3.py` — carries three drift-fences
  that ANY addition to `__all__` must extend:
  - `test_all_is_exact_set` — exact-set equality; a Phase-9 name set must be
    added to the union or the assertion fails.
  - `test_newtype_registry_matches_all` — asserts the registry keys equal
    `__all__ − PHASE7_TYPE_ALIAS_NAMES`; every new name must land in
    `_NEWTYPE_REGISTRY` with a per-phase-specific ADR citation branch, or the
    generic else-branch (which requires `"ADR-0010"` in the docstring — a
    lineage citation, not the newtype ADR).
  - `test_pairwise_distinct` — every NewType a distinct object.

## Stage-2 findings — four critics

### Coverage critic

| # | Finding | Severity | Proposed fix |
|---|---|---|---|
| C1 | AC-2 references `_DEFINITIONS`, which does not exist. Actual registry is `_NEWTYPE_REGISTRY` (line 314 of `identifiers.py`). Executor would search for a symbol that isn't there. | block | Rename to `_NEWTYPE_REGISTRY` in AC-2, Implementation outline step 4, and Notes. |
| C2 | ACs don't cover the drift-fences in `test_identifiers_phase3.py` (`test_all_is_exact_set`, `test_newtype_registry_matches_all`) — those tests WILL FAIL when new names appear in `__all__` unless a `PHASE9_NEWTYPE_NAMES` set is added to the test file AND the registry-doc-citation branch is extended. Story lists only two new test files; missing the loud test-file edit. | block | Add AC: "`tests/unit/types/test_identifiers_phase3.py` gains a `PHASE9_NEWTYPE_NAMES` set added to the union in `test_all_is_exact_set` and a Phase-9 branch in `test_newtype_registry_matches_all` asserting the docstring cites production ADR-0033 + Phase-9 ADR-0008." Add the file to "Files to touch." |
| C3 | AC-7 tests only the ConfigDict introspection (`cfg.get("frozen") is True`). Missing runtime behavioural ACs: (a) instance mutation raises, (b) extra field at construction raises, (c) `SECRET_TYPES` is a runtime frozenset (Final is a type-checker hint only). | harden | Add three assertions inside `test_phase09_secret_types.py`. |
| C4 | AC missing that the new Phase-9 entries in `_NEWTYPE_REGISTRY` carry a phase-specific ADR citation (needed because `test_newtype_registry_matches_all`'s Phase-9 branch will assert it). | harden | Add AC: each Phase-9 `_NEWTYPE_REGISTRY` entry cites production ADR-0033 + Phase-9 ADR-0008 in its docstring. |
| C5 | AC missing that `__all__` remains strictly alphabetically sorted (`test_all_is_exact_set` asserts `ids.__all__ == sorted(ids.__all__)`). | nit | Add AC. |

### Test-Quality critic

| # | Finding | Severity | Proposed fix |
|---|---|---|---|
| T1 | `test_phase09_newtypes_present_and_typed` loops `("AttemptId", "CorrelationId", …)` — `AttemptId` is already in the module (Phase-4 catalog, line 168); test would pass whether or not the story wrote anything. Fails intent-verifying discipline (Rule 9). | block | Remove `AttemptId` from the test loop; assert only the six truly-new names. |
| T2 | `test_secret_types_are_frozen_pydantic` only inspects `model_config`; a wrong implementation with `model_config = {"frozen": True, "extra": "forbid"}` (raw dict, not ConfigDict) or with `frozen=True, extra="ignore"` (wrong value) would still pass the current assertions. Behavioural test would catch both. | harden | Instantiate one credential class, attempt `.value = "x"` → assert Pydantic raises `ValidationError`; attempt `Cls(value="v", extra="oops")` → assert `ValidationError`. |
| T3 | No test asserts `WorkflowSeq` is distinct from `AttemptNumber` at compile time (both are `int`-backed). Downstream stories rely on non-swap. | harden | Add a subprocess-mypy negative sibling test (or a runtime `is not` assertion) proving `WorkflowSeq is not AttemptNumber`. |
| T4 | No test asserts `SECRET_TYPES` cannot be mutated in place. Adding a `.add(…)` attempt makes the frozenset guarantee explicit and mutation-resistant. | harden | Add `with pytest.raises(AttributeError): SECRET_TYPES.add(str)`. |
| T5 | No `test_pairwise_distinct`-style property extended to Phase-9 names — the existing test only covers Phase-2 ∪ Phase-3. Two Phase-9 str-backed NewTypes accidentally aliased to the same object would slip through. | harden | Add a `test_phase09_pairwise_distinct` in the new test file. |

### Consistency critic

| # | Finding | Severity | Proposed fix |
|---|---|---|---|
| K1 | Story lists **seven** new Newtypes including `AttemptId`, but `AttemptId = NewType("AttemptId", str)` was landed in Phase-4 S1-01 (line 168 of `identifiers.py`, described as "S6-08 AttemptAnchor…FallbackTier._pending_anchors key"). Story explicitly excludes `WorkflowId`, `EventId`, `BlobDigest`, `TaskClassId` from redefinition but forgets `AttemptId`. Executor would either redefine (mypy error) or spot the duplication and manually reconcile — either wastes an attempt. | block | Reduce to **six** new Newtypes; add `AttemptId` to the "do not redefine" list. |
| K2 | Story references `_DEFINITIONS` (line 27, line 47); actual module symbol is `_NEWTYPE_REGISTRY` (see C1 above). | block | Fix references. |
| K3 | Story does not surface that the arch's contract block (`phase-arch-design.md §Newtype identifiers` line 780-795) lists `TaskClassId` and `AttemptId` as "additions" — that is misleading in the arch (both pre-exist). The story correctly excludes `TaskClassId`; the same treatment must apply to `AttemptId`. Not a story edit (arch is arch scope), but the validator notes it in Notes for the implementer. | nit | Add a note. |
| K4 | ADR-0043 §"loud compiler-policed edits are the enforcement mechanism, not violations" — appending to `__all__`, extending `_NEWTYPE_REGISTRY`, and adding names to the existing `test_identifiers_phase3.py` fence sets are all sanctioned loud edits. Not a violation of ADR-0043; explicitly permitted by commitment 1. | nit | Note in the Implementation outline (avoids future contributor doubt). |

### Design-Patterns critic

| # | Finding | Severity | Proposed fix |
|---|---|---|---|
| D1 | NewType-per-identifier ✓ (primitive-obsession is a production-ADR-0033 blocker). No pattern-improvement opportunity — this story *is* the pattern. | strong | none |
| D2 | Pydantic frozen + `extra="forbid"` on each credential class ✓ (illegal-states-unrepresentable + smart-constructor discipline). | strong | none |
| D3 | `SECRET_TYPES: Final[frozenset[type]]` — type-registry pattern; extension by one-line addition to the frozenset. Rule of three met (five members day-1). Adding a sixth secret type is a "loud compiler-policed edit" per ADR-0043 — Open/Closed as understood by ADR-0043. Not registry-decorator machinery (would be ceremony over five members). | strong | Add to Notes: "Adding a new secret type = one line in the `SECRET_TYPES` frozenset + one new Pydantic class file. Not `@register_credential_type(…)` — the frozenset IS the registry; ADR-0043 sanctions this as a loud additive edit." |
| D4 | Story defers smart-constructor parsers for the new IDs (Notes line 116 explicitly out of scope). Arch §Design patterns applied #4 says "Did NOT apply to WorkflowId — bare Newtype is fine; the constructor would be ceremonial." Consistency > Design-Patterns: YAGNI wins. Note the rule-of-three trigger for later stories. | nit | Add to Notes: "When a downstream consumer needs to construct a Phase-9 NewType from external input (CLI arg, Postgres load, HTTP body), that is the third callsite triggering parser addition per ADR-0033. Not this story's scope." |
| D5 | Credential classes carry a single `value: str` field. Reasonable minimal shape. The security guarantee is the *type* of the field downstream declares, not the field name (Notes line 122). Design pattern is correct. No `SecretStr` — explicitly deferred to sanitizer. | strong | none |
| D6 | Newtypes for domain identifiers with different backing types (`str` vs `int`) — story implicitly enables `mypy --strict` catching `AttemptNumber` ↔ `WorkflowSeq` swaps. T3 above adds an explicit test for this — good design-pattern reinforcement. | harden (via T3) | see T3 |

## Stage 3 — Research

Not fired. No finding tagged `NEEDS RESEARCH` — the failure modes are all
codebase-precedented (Phase-3 and Phase-7 already followed this shape).

## Stage 4 — Synthesizer + Edits

Conflict resolution: none needed. Coverage and Consistency findings agree
that `AttemptId` must be removed from the "new" list, that the registry
name is `_NEWTYPE_REGISTRY`, and that the drift-fences in
`test_identifiers_phase3.py` must be extended. Test-Quality's mutation-
resistance additions are additive to the current TDD plan. Design-Patterns
findings are notes-only (rule-of-three thresholds surface in
`Notes for the implementer`).

### Edits applied to story

1. **Header — Status:** `Ready` → `HARDENED`.
2. **Validation notes block** appended after the header documenting every
   change with rationale.
3. **Context (§Context):** Corrected "seven → six" and added `AttemptId` to
   the "already ships" list.
4. **References:** Replaced dangling `_DEFINITIONS` reference with
   `_NEWTYPE_REGISTRY`; added pointer to `test_identifiers_phase3.py`
   drift-fences.
5. **Goal:** Six → new phrasing that names the six additions explicitly.
6. **Acceptance criteria:** Reduced to six new Newtypes; added ACs for
   (a) `_NEWTYPE_REGISTRY` name + citation, (b) `test_identifiers_phase3.py`
   drift-fence extension, (c) runtime frozenset check, (d) instance-mutation
   rejection, (e) extra-field rejection, (f) `__all__` remains sorted,
   (g) `WorkflowSeq is not AttemptNumber` pairwise-distinct, and
   (h) Phase-9 pairwise-distinctness.
7. **Implementation outline:** Renumbered; step 4 fixed to
   `_NEWTYPE_REGISTRY`; added a step 6 for the existing-test extension.
8. **TDD plan — Red:** Removed `AttemptId` from the loop; added tests for
   pairwise-distinct, `SECRET_TYPES` frozenset runtime, instance mutation,
   extra field rejection, `WorkflowSeq is not AttemptNumber`, alphabetized
   `__all__` sentinel, and the `test_identifiers_phase3.py` PHASE9-set +
   registry-branch edits.
9. **Files to touch:** Added `tests/unit/types/test_identifiers_phase3.py`
   (extend drift-fences).
10. **Out of scope:** No changes.
11. **Notes for the implementer:** Added K3, D3, D4 notes; strengthened the
    "already exists — do not redefine" list to include `AttemptId`.

### Verdict

**HARDENED.** The story had three blocking bugs (`AttemptId`
duplication, `_DEFINITIONS` name mismatch, existing test-file drift not
covered) and four hardening improvements (mutation-resistant credential
tests, runtime frozenset check, pairwise distinctness, alphabetization).
All are now embedded in ACs and the TDD plan. Executor should complete in
one attempt.
