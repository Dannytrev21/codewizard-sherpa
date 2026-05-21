# Validation report: S1-01 — Newtype + smart-constructor substrate

**Validated:** 2026-05-21
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S1-01 lands the Phase-4 type substrate — eleven new `NewType` identifiers in
`codegenie.types.identifiers` plus eight smart-constructor parsers in
`codegenie.types.parsers` — so every later Phase-4 story imports typed
primitives from one canonical home. The story was already detailed and
well-structured (rich TDD plan, family-symmetric closures, property tests),
but the four-lens audit found **three blockers** that would make
`make check` fail as written and the executor burn attempts, plus six
hardens and three nits. All twelve findings were fixable in place — verdict
**HARDENED**, not RESCUE: the goal, scope, and the bulk of the ACs are sound.

The three blockers all stem from the story under-modelling the *existing*
state of `identifiers.py` / `parsers.py` / `test_identifiers_phase3.py`,
which already carry a Phase-2 + Phase-3 + Phase-7 catalog with established
conventions:

1. **Forked registry (F1).** The story prescribed a new
   `_PHASE4_NEWTYPE_REGISTRY` constant. The file has exactly one shared
   `_NEWTYPE_REGISTRY`; Phase 7 already appended to it; the existing
   `test_newtype_registry_matches_all` asserts that dict is exact against
   `__all__`. A forked registry breaks that test and forks a convention.
2. **Unacknowledged cross-file coupling (F2).** Adding eleven names to
   `identifiers.__all__` breaks the existing `test_all_is_exact_set` and
   `test_newtype_registry_matches_all` in `test_identifiers_phase3.py`.
   The story's Files-to-touch omitted that file, so AC-18 ("pytest passes")
   was literally unsatisfiable.
3. **`NewType` over a parametrized generic (F3).** AC-2 prescribed
   `NewType("EmbeddingVector", "tuple[float, ...]")` — `mypy --strict`
   rejects `NewType` over a parametrized type. The *same file* already
   proves this: `ProvenanceAdapterId` is a `TypeAlias` for exactly this
   reason. AC-2 as written failed its own AC-18.

## Methodology note

The four critic lenses (Coverage, Test-Quality, Consistency,
Design-Patterns) were applied inline by the validator after a full read of:
the story; `phase-arch-design.md §Data model / §Goals G6 / §Design patterns`;
the current `identifiers.py`, `parsers.py`, `errors.py`, `types/__init__.py`;
and the Phase-3 test precedents `test_identifiers_phase3.py`,
`test_identifiers_phase3_mypy_negative.py`, `test_module_purity.py`. Parallel
critic subagents were not spawned — every finding is grounded in a concrete
file read, and re-reading the 43k-token arch file under four subagents would
have burned token budget for no additional coverage (Rule 6).

## Findings by critic

### Consistency critic

- **F1 (block)** — AC-15 prescribed `_PHASE4_NEWTYPE_REGISTRY`. `identifiers.py`
  has one shared `_NEWTYPE_REGISTRY` (Phase 2/3/7 all appended to it);
  `test_identifiers_phase3.py::test_newtype_registry_matches_all` asserts
  `_NEWTYPE_REGISTRY.keys() == __all__ - PHASE7_TYPE_ALIAS_NAMES`. A forked
  registry breaks that test + forks a convention (Rule 7 / Rule 11).
- **F2 (block)** — Files-to-touch omitted `test_identifiers_phase3.py`.
  Adding to `identifiers.__all__` breaks `test_all_is_exact_set` +
  `test_newtype_registry_matches_all` there. AC-18 unsatisfiable as written.
- **F3 (block)** — AC-2 `NewType("EmbeddingVector", "tuple[float, ...]")`
  fails `mypy --strict` (NewType over a parametrized generic). The file's
  own `ProvenanceAdapterId` is a `TypeAlias` precisely because of this.
- **F7 (harden)** — AC-13 prose roster (14 keywords incl. `package`)
  disagreed with the skeleton code roster (13, omitting `package`).
- **F8 (harden)** — AC-16 re-specified the `parsers.py` import allowlist and
  omitted `collections.abc` (already imported for `Callable`). The existing
  `test_module_purity.py` already guards this correctly; Phase 4 adds no new
  imports to `parsers.py`.
- **F9 (harden)** — "twelve new names" miscount: AC-1 listed twelve incl.
  `BlobDigest`, then said do-not-redefine `BlobDigest`. The real count is
  eleven; every roster constant (`PHASE4_NAMES`) already had eleven.

### Coverage critic

- **F9 (harden)** — see above; "twelve" vs eleven would confuse the executor.
- **F10 (harden)** — `parse_token_count` / `parse_similarity` did not reject
  `bool`. `True`/`False` are `int` instances; `parse_token_count(True)` would
  return `Ok(TokenCount(True))`. The precedent `parse_attempt_number`
  *explicitly* rejects bool. AC-7 listed `"1"` (str) but not `True`.
- **F12 (nit)** — AC-11 prose demanded exact-set equality "stowaway exports
  fail" but the only test the story provided (`test_all_is_exact_superset_…`)
  does `issubset`. The real exact-set guard lives in `test_identifiers_phase3.py`.

### Test-Quality critic

- **F4 (harden)** — `parse_budget_token_id` (a uuid4 *regex*) was labelled a
  "direct function". A hand-written `.fullmatch` breaks the existing
  `test_only_one_fullmatch_outside_helper` (AST-asserts `.fullmatch` only
  inside `_regex_parser`). Same for the regex inside `parse_model_id`.
- **F5 (harden)** — AC-8's mypy-negative test promised swap coverage for
  `Similarity`/`TokenCount`/`EmbeddingVector` but `SWAP_PAIRS` had only ten
  `str`-backed pairs and the template hardcoded `B("dummy")` — which would
  fail with the *wrong* mypy diagnostic for non-`str` newtypes. The
  precedent `test_identifiers_phase3_mypy_negative.py` solves this with a
  per-name `_ctor_arg` helper; the story did not mirror it.
- **F6 (harden)** — AC-13's fence skeleton walked only `ast.AnnAssign`. The
  AC prose explicitly promises "function signature" coverage; a
  `def foo(cve_id: str)` would slip through every later Phase-4 story.
- **F11 (nit)** — AC-12 excluded `Similarity`/`TokenCount`/`EmbeddingVector`
  from the `isinstance`-TypeError parametrized test for no functional
  reason (all `NewType`s raise `TypeError` regardless of backing).

### Design-Patterns critic

- **F1 (block)** — see Consistency. The single-registry pattern is the
  Open/Closed seam: a new phase contributes *additive rows*, never a new
  structure. A forked registry is the textbook violation.
- **F3 (block)** — `EmbeddingVector` as `NewType` over the bare `tuple`
  (not a `TypeAlias`, not a parametrized `NewType`) keeps it
  family-symmetric with the other ten newtypes, so the test suite's uniform
  parametrization (`__name__` pinning, distinctness, `isinstance`) holds. A
  `TypeAlias` would silently fail `__name__` pinning.
- **F4 (harden)** — `_regex_parser` as the single regex chokepoint is a
  deliberate design (Phase-3 AC-18: "add a new regex parser = one closure
  row"). The story's "direct function" framing for `parse_budget_token_id`
  would erode it.
- Reuse note (folded into the Refactor section): the four hex-shaped parsers
  should reuse the existing `_HEX64_RX` (identical to `parse_blob_digest`'s
  shape) rather than introduce a duplicate `_BLAKE3_HEX_RX`.

## Research briefs

None required — no finding was tagged `NEEDS RESEARCH`. Every fix had a
direct in-repo precedent (`parse_attempt_number`, `parse_branch_name`,
`_image_digest_match`/`_layer_digest_match`, `test_identifiers_phase3_*`).

## Conflict resolutions

No critic conflicts. F3 (Consistency + Design-Patterns) and F1 (Consistency +
Design-Patterns) were raised by two lenses each with the same fix — merged.

## Edits applied

| # | Target | Change | Finding |
|---|---|---|---|
| 1 | Header | `Status: Ready → HARDENED`; added `Validation notes` block | — |
| 2 | AC-1 | "twelve" → "eleven"; `BlobDigest`/`WorkflowId` reused | F9 |
| 3 | AC-2 | `EmbeddingVector = NewType("EmbeddingVector", tuple)` (bare) | F3 |
| 4 | AC-3 | `parse_budget_token_id`/`parse_model_id` via `_regex_parser`; `parse_token_count`/`parse_similarity` reject `bool` | F4, F10 |
| 5 | AC-7 | added `True` rejection rows for token_count + similarity | F10 |
| 6 | AC-8 | ≥12 pairs incl. non-`str` newtypes; `_ctor_arg` helper mandated | F5 |
| 7 | AC-11 | exact-set guard clarified to live in updated `test_identifiers_phase3.py` | F2, F12 |
| 8 | AC-12 | parametrize over all eleven newtypes | F11 |
| 9 | AC-13 | scan function-arg + return annotations; roster reconciled (`package`) | F6, F7 |
| 10 | AC-15 | append to existing `_NEWTYPE_REGISTRY`; no `_PHASE4_NEWTYPE_REGISTRY` | F1 |
| 11 | AC-16 | reference existing `test_module_purity.py`; no stale import set | F8 |
| 12 | AC-18 + AC-19 | AC-19 added — cross-file fence reconciliation in `test_identifiers_phase3.py` | F2 |
| 13 | Impl outline | steps 1–11 rewritten to match the hardened ACs | F1–F10 |
| 14 | TDD Red | `test_phase4_rows_in_shared_registry` (was `_PHASE4_…`); mypy-negative rewritten with `_ctor_arg` + raw-literal swaps; fence skeleton walks function args/returns; `isinstance` test over all eleven | F1, F5, F6, F11 |
| 15 | TDD Green/Refactor | reuse `_HEX64_RX`; `_regex_parser` chokepoint; `test_identifiers_phase3.py` update step | F1, F2, F4 |
| 16 | Files to touch | added `test_identifiers_phase3.py` (MODIFY); noted `tests/fence/` already exists; `test_module_purity.py` untouched | F2, F8 |
| 17 | Notes for implementer | single-registry / fenced-`__all__` / `_regex_parser`-chokepoint paragraphs; corrected `tests/fence/` exists | F1, F2, F4 |

## Verdict rationale

HARDENED. The story's goal (one canonical typed-primitive home for Phase 4)
is correct and traces cleanly to arch §Data model + G6 + production ADR-0033.
Every blocker was an in-place fixable mismatch with the *current* state of
the kernel `types` package — not a goal-level defect — so RESCUE was not
warranted. After the edits, every AC is individually verifiable, the TDD
plan's tests would fail against a wrong implementation, and the cross-file
fence coupling that would have silently failed `make check` is now an
explicit AC (AC-19) with a Files-to-touch row.

## Recommended next step

`phase-story-executor` to implement S1-01. The executor MUST run the full
`make check` (not a touched-file subset) — AC-19 exists because this story
edits the fenced `identifiers.__all__` surface.
