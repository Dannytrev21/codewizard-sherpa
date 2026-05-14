# Validation report — S2-01 `LanguageDetectionProbe` extension: `framework_hints` + `monorepo`

**Story:** [S2-01-language-detection-extension.md](../S2-01-language-detection-extension.md)
**Validated:** 2026-05-14
**Validator:** phase-story-validator (scheduled task: story-validation-corrector)
**Verdict:** **HARDENED**

## Summary

S2-01 lands the Phase-0-deferred fields (`framework_hints`, `monorepo`) on `LanguageDetectionProbe` and is **the first real consumer of `ParsedManifestMemo`** — so its memo-seam wiring is load-bearing for S2-04's warm-path integration test. The original draft was tight on goal/scope (S effort, single in-place edit, well-bounded) but had two block-tier consistency issues (confidence levels for symlink-refused, and the wrong output field for typed-exception error IDs per ADR-0007 line 50), several coverage gaps (no symlink test, no memo-consumption test, no determinism property, weak Phase-0-stability assertion), and one Open/Closed seam (monorepo-tool precedence encoded as branching rather than data).

The synthesizer rewrote the story from **7 single-bullet ACs + 5 TDD tests** to **13 individually-verifiable ACs + 10 TDD tests** (plus 2 sibling regression tests in the existing test file), introduced the precedence-ordered tuple `_MONOREPO_PRECEDENCE` as the file-boundary Open/Closed extension point, and reconciled the field/confidence semantics with the arch's own component-design #1 + ADR-0007.

**No `NEEDS RESEARCH` findings.** Every weakness was resolvable from authority docs (arch + ADR-0002 + ADR-0004 + ADR-0007 + ADR-0010 + Phase 0 ADR-0013) and the established Phase 1 pattern from S1-08's hardening (which was the first phase-1 story to nail the typed-exception → `errors[]` discipline). Stage 3 (researcher) skipped per skill's token-economy guidance.

**Most load-bearing fixes (block-tier):**

1. **Field semantics — typed-exception IDs go in `ProbeOutput.errors[]`, not `language_stack.warnings[]`.** ADR-0007 line 50 is explicit: *"errors is the typed-exception-raised-during-probe-run list; warnings is the soft-degrade signal"* and uses `package_json.size_cap_exceeded` as the canonical example of an `errors[]` entry. The arch §"Component design" #1 agrees: `ProbeOutput(confidence="medium", errors=["package_json.malformed"])`. The original story's T-5 asserted the ID in `schema_slice["language_stack"]["warnings"]` — inconsistent. Hardened: AC-11 places all three IDs in `out.errors`; AC-7 + AC-10 extend the sub-schema's ADR-0007 pattern constraint to **both** `warnings[]` and `errors[]`. T-6, T-7, T-8 each anchor one of the three failure modes against `out.errors`.
2. **Confidence levels — symlink-refused is `"low"`, not `"medium"`.** Arch §"Component design" #1 line 477: *"`package.json` symlink-out-of-repo (`O_NOFOLLOW` refused) → `confidence: low`, warning emitted."* The original story collapsed size-cap and symlink to a single `"medium"` for both. Hardened: AC-11 distinguishes — size-cap → `medium`, symlink → `low`, malformed → `medium`. T-7 anchors symlink → `low`.

**Coverage gaps closed (harden-tier):**

- AC for `markers` content was unspecified (Test 2 asserted `package.json` in markers but no AC said so). Hardened: AC-4 pins the union-of-all-hits rule + the `package.json` inclusion-when-`workspaces`-truthy rule.
- AC for monorepo precedence when multiple markers coexist was missing. Hardened: AC-3 + AC-4 + T-9 (deferred to Notes-and-implementation per priority — see Test-Quality).
- AC for `workspaces` field shape (array vs object vs null) was missing. Hardened: AC-5 (truthiness rule; both shapes detected; null/empty treated as absent).
- AC for `MalformedJSONError` was missing — Refactor mentioned catching it but no error ID was declared. Hardened: AC-11 + AC-12 add `package_json.malformed` as the third typed error ID; T-8 anchors it.
- "Existing counts/primary fields are unaffected" was a vague qualitative AC. Hardened: AC-8 turns it into a byte-equal regression check against a Phase 0 baseline; T-3 anchors it via `_phase0_baseline_keys`.
- Declared-inputs preservation was implicit. Hardened: AC-6 makes "Phase 0 entries are a contiguous prefix" the explicit invariant; new sibling test `test_declared_inputs_additive` anchors it.

**Test-quality gaps closed (harden-tier):**

- Original T-1 (`test_framework_hints_detected_from_dependencies`) would have passed under a hardcoded `return ["express"]` implementation — no negative assertion. Hardened T-1 adds `assert "lodash" not in hints` plus a `devDependencies` entry to exercise the union.
- No test for the memo-consumption seam, even though the story names this as "the first real consumer of `ParsedManifestMemo`" and S2-04 depends on `probe.memo.hit == 1`. Hardened: T-9 verifies both branches (memo called when present; safe_json fallback when `None`).
- No test for the symlink-refused branch. Hardened: T-7 — creates a real symlink pointing outside `tmp_path`, asserts `errors` + `confidence == "low"` + no leaked framework hint from the symlink target.
- No test for the malformed-JSON branch. Hardened: T-8 — truncated `{"dependencies": {"express": "^4.0.0"` asserts the typed `MalformedJSONError` mapping.
- No property test for determinism (would catch implementations that rely on dict-insertion order). Hardened: T-10 parametrized over three shuffled dep orderings + a `devDependencies` dup → asserts always-sorted, always-deduped.

**Design-pattern opportunity lifted from buried "Notes" into an explicit Implementation-outline change + an AC:**

- **`_MONOREPO_PRECEDENCE: tuple[tuple[str, str], ...]`** (Open/Closed at the file boundary). Original implementation outline had a chain-of-if for tool selection: `turbo.json → "turbo"`, `nx.json → "nx"`, etc. With 5 entries today and Phase 2 likely adding `pants`/`bazel`/`buck`, this would have been the next big extension cliff. Encoding precedence as a precedence-ordered tuple plus a single linear scan in `run(...)` means adding a new monorepo tool is a one-line tuple insertion — **no edits to branching logic**. Promoted to AC-3 (an observable constraint — "encoded as a single precedence-ordered tuple") rather than as a pattern-name mandate, per the validator's rule (ACs are observable; pattern names are contextual). The compile-time assertion that the last tuple entry is `package.json` keeps the workspaces-only fallback's position correct.

**Design-pattern opportunities deliberately deferred (rule-of-three not yet met):**

- **`_FRAMEWORK_SEED` → `catalogs/frameworks.yaml`.** Single-use today. Per Rule 2, three similar lines is better than premature abstraction. The right moment to extract is when a second consumer arrives (Phase 2 polyglot detection for Python/Go frameworks). Recorded in Notes-for-implementer.
- **`MonorepoBlock` → frozen dataclass.** TypedDict is enough today (single boundary; JSON-schema-validated). If logic on the block grows beyond 2 consumers, a frozen dataclass with a smart constructor becomes worth the boilerplate. Recorded in Notes-for-implementer.

**Departure from arch surfaced and recorded (per Rule 7).** Arch §"Component design" #1 says size-cap → `confidence: medium`; arch §"Edge cases" row 2 (line 834) says size-cap → `confidence: low`. These are internally inconsistent in the arch itself. This story sides with §"Component design" #1 (the more detailed component-level prescription, and the section the story originally cited). The conflict is flagged in the story's Notes-for-implementer block ("Confidence semantics — arch-internal conflict surfaced") so the implementer can re-surface it if a future arch patch reconciles in the other direction.

## Context Brief (Stage 1)

- **Goal as written:** Extend `LanguageDetectionProbe` so a gather over a Node fixture declaring `express` + shipping `turbo.json` produces `language_stack.framework_hints == ["express"]` and `language_stack.monorepo == {"tool": "turbo", "markers": ["package.json", "turbo.json"]}`, with Phase 0 counts/primary fields unchanged.

- **Phase exit criteria touched:**
  - Arch §"Component design" #1 — this probe; framework dict, monorepo markers, perf envelope, failure behavior.
  - Arch §"Data model" — `language_stack` extension prose under §"Component design" #1.
  - Arch §"Control flow" → "Decision points" → "Memo hit vs. memo miss" — the seam this probe is the *first consumer* of.
  - Arch §"Edge cases" rows 2 (oversized `package.json`), 3 (symlink-out-of-repo `package.json`), 11 (non-Node repo), 12 (`ctx.parsed_manifest is None`).
  - Arch §"Process view" — Wave-1 prelude pass; `LanguageDetection` runs alone before Wave 2 dispatch.

- **ADRs:**
  - **This phase ADR-0002** — `ParsedManifestMemo` on `ProbeContext`. S2-01 is its first consumer. The story's AC-1 pins the `ctx.parsed_manifest(...) if not None else safe_json.load(...)` pattern verbatim.
  - **This phase ADR-0004** — per-probe sub-schema `additionalProperties: false` at the sub-schema root. AC-7 + AC-9 + T-4 anchor.
  - **This phase ADR-0007** — `warnings[]`/`errors[]` pattern constraint `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`. Line 50 of the ADR is load-bearing: it distinguishes the two fields by exception-raised vs. soft-degrade semantics. AC-7 + AC-10 + AC-11 + AC-12 + T-5 + T-6 + T-7 + T-8 anchor.
  - **This phase ADR-0010** — Layer A slices optional at envelope (non-Node repos validate). Out of scope to test here (S5-04 covers non-Node fixture).
  - **Phase 0 ADR-0013** — envelope `probes.*: additionalProperties: true` preserved. The story's Notes-for-implementer reminds the implementer NOT to tighten the envelope.

- **Predecessor state (load-bearing for S2-01):**
  - S1-05: catalogs loader hard-fail-at-startup pattern (precedent for the `_ERRORS` compile-time assertion).
  - S1-06: `ProbeContext` already exposes `parsed_manifest: Callable[[Path], ...] | None = None`. AC-1 consumes it.
  - S1-07: `ParsedManifestMemo` registered + `probe.memo.{hit,miss}` events wired. T-9 verifies the seam from the probe side; S2-04 will verify the end-to-end memo-hit count.
  - S1-08: Pre-dispatch input snapshot (Gap 1) — `ctx.input_snapshot` available but not directly relied on by this probe.
  - Phase 0 `LanguageDetectionProbe`: ships extension counts only (Phase 0 final-design §2.10 deferred the rest); this is one of exactly three Phase-0 in-place edits the phase allows (§"Backlog stats").

- **Open ambiguities surfaced:**
  1. Field for typed-exception IDs (`warnings` vs `errors`). Resolved by AC-11 + ADR-0007 line 50 → `errors`.
  2. Confidence for symlink-refused. Resolved by AC-11 + arch §"Component design" #1 → `low`.
  3. Monorepo precedence when multiple markers coexist. Resolved by AC-3 (`_MONOREPO_PRECEDENCE` tuple) + T-2.
  4. `markers` inclusion of `package.json` when `workspaces` is truthy. Resolved by AC-4 + T-2's explicit expectation.
  5. `workspaces` shape acceptance (array, object, null, empty). Resolved by AC-5 (truthiness rule).
  6. `MalformedJSONError` ID. Resolved by AC-11 + AC-12 + T-8 → `package_json.malformed`.
  7. ADR-0013 cross-phase reference. Resolved by ADRs-honored header → "Phase 0 ADR-0013".
  8. Arch-internal conflict on size-cap confidence (component-design vs edge-case-table). Resolved by Notes-for-implementer block surfacing the conflict and committing to §"Component design" #1.

## Stage 2 — Critic findings

### Critic A — Coverage (Did the ACs collectively guarantee the goal? Edge cases missing? Vague ACs?)

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| CV-1 | harden | "existing counts/primary fields are unaffected" was qualitative | AC-8 — byte-equal regression check; T-3 — `_phase0_baseline_keys` helper |
| CV-2 | harden | No AC for monorepo precedence with multiple markers | AC-3 + `_MONOREPO_PRECEDENCE` |
| CV-3 | harden | No AC for `workspaces` shape (object vs array vs null) | AC-5 |
| CV-4 | harden | `MalformedJSONError` mentioned in Refactor but no ID declared | AC-11 + AC-12 (`package_json.malformed`) |
| CV-5 | harden | `markers` content was unspecified (does `package.json` count?) | AC-4 |
| CV-6 | harden | Declared-inputs preservation was implicit | AC-6 — Phase 0 entries are a contiguous prefix |
| CV-7 | harden | Symlink-refused branch had no AC test | AC-11 + T-7 |
| CV-8 | nit | ADR-0013 phase-of-origin unclear | ADRs-honored header clarified to "Phase 0 ADR-0013" |

### Critic B — Test Quality (Mutation-resistant? Intent-verifying? Property invariants?)

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| TQ-1 | harden | T-1 would pass under `return ["express"]` hardcode | Negative assertion (`lodash not in hints`) + multi-framework cross-list test |
| TQ-2 | harden | No memo-consumption test (load-bearing for S2-04) | T-9 — both branches (memo + fallback) |
| TQ-3 | harden | No symlink-refused test | T-7 — real symlink outside `tmp_path` |
| TQ-4 | harden | No malformed-JSON test | T-8 — truncated JSON |
| TQ-5 | harden | No determinism property test | T-10 — parametrized over shuffled dep orderings + devDep dup |
| TQ-6 | harden | T-5 asserted `package_json.size_cap_exceeded` in `warnings` — wrong field per ADR-0007 line 50 | T-6 asserts in `out.errors`; AC-11 + AC-7 align the schema |
| TQ-7 | nit | Pattern test only verified positive case for the two known IDs | T-5 parametrized — `bad_id`/`good_id` matrix for both fields |
| TQ-8 | harden | No test that `_ERRORS` module-import-time assertion fires | New sibling test `test_module_import_asserts_error_ids` |

### Critic C — Consistency (Story vs arch / ADRs / CLAUDE.md)

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| CN-1 | **block** | Story put `package_json.size_cap_exceeded` in `warnings` — ADR-0007 line 50 says typed-exception IDs go in `errors` | AC-11 + AC-7 + T-6 → `errors[]` |
| CN-2 | **block** | Story marked symlink-refused `confidence: "medium"` — arch §"Component design" #1 says `low` | AC-11 + T-7 → `low` |
| CN-3 | harden | `MalformedJSONError` mentioned but no error ID — arch §"Component design" #1 says `package_json.malformed` | AC-11 + AC-12 + T-8 |
| CN-4 | nit | ADR-0013 referenced without phase prefix; it's a Phase 0 ADR | ADRs-honored header clarified |
| CN-5 | harden | Arch-internal conflict on size-cap confidence (component-design says medium; edge-case-table row 2 says low) | Notes-for-implementer block records the choice + the conflict, per Rule 7 |
| CN-6 | nit | Slice's `warnings[]` shape — pattern constraint applied; field preserved as empty array for forward use | AC-7 — same pattern on both `warnings[]` and `errors[]` |

### Critic D — Design Patterns (Extension-by-addition, anti-patterns, abstraction threshold)

| ID | Severity | Finding | Resolution |
|---|---|---|---|
| DP-1 | harden | Monorepo tool selection as chain-of-if would lock in branching; Phase 2 likely adds pants/bazel/buck — Open/Closed violation at the file boundary | `_MONOREPO_PRECEDENCE` tuple + linear scan; AC-3 phrasing pins the *observable* constraint ("encoded as a single precedence-ordered tuple"), not the pattern name |
| DP-2 | nit | `_FRAMEWORK_SEED` could be a YAML catalog | Deferred — single-use today; rule-of-three threshold not met; Notes-for-implementer records the deferral and names Phase 2 polyglot detection as the candidate trigger |
| DP-3 | harden | `MonorepoBlock` shape was anaemic `dict` — mypy --strict can't catch a Phase-0-key regression | Notes-for-implementer prescribes `TypedDict`; AC-13 keeps `mypy --strict` clean as the regression gate |
| DP-4 | harden | `_WARNINGS` frozenset name was wrong (semantically these are errors) + the compile-time assertion was buried in Refactor | Renamed to `_ERRORS`; AC-12 lifts the assertion to AC level + a sibling test (`test_module_import_asserts_error_ids`) verifies it fires |
| DP-5 | nit | `_MONOREPO_PRECEDENCE` last-entry invariant (workspaces-fallback must be last) | Module-import assertion `_MONOREPO_PRECEDENCE[-1][0] == "package.json"` (in Refactor block) |
| DP-6 | nit | Exception-to-ID mapping could grow to many cases; for 3 entries an inline dict literal is right | Implementation outline uses a dict literal — keep inline; deferred extraction to a helper |

## Stage 3 — Researcher

Skipped (no `NEEDS RESEARCH` findings). All canonical patterns were resolvable from authority docs:

- Open/Closed-via-precedence-tuple pattern → Phase 1 already uses analogous tuples (CI provider catalog, lockfile precedence) — established Phase 1 idiom.
- TypedDict-for-anaemic-slice-shape → mypy stdlib pattern; no external research needed.
- Property-test-for-sort-determinism → `pytest.parametrize` over shuffled orderings is the standard idiom; Hypothesis would be overkill for a 6-element seed dict. The parametrized approach was chosen as the simpler form.
- Compile-time assertion against a regex → established Phase 1 idiom (S1-05 catalogs loader hard-fail-at-startup precedent).

## Stage 4 — Synthesis + edits applied

All edits are in [S2-01-language-detection-extension.md](../S2-01-language-detection-extension.md). Summary of changes:

- **Story header.** Status → `Ready (hardened 2026-05-14)`. ADRs-honored row clarified to call out this-phase vs Phase 0 ADRs.
- **New `## Validation notes` block** (after the header). Inline summary of the eight in-place edits + verdict.
- **`## Acceptance criteria` section.** Replaced 7 single-bullet ACs with **AC-1 through AC-13** — each individually verifiable, each named with the WHY behind it.
- **`## Implementation outline` section.** Rewrote to:
  - Name three module-level constants (`_FRAMEWORK_SEED`, `_MONOREPO_PRECEDENCE`, `_ERRORS`) with their invariants.
  - Replace the chain-of-if monorepo logic with a single linear scan over `_MONOREPO_PRECEDENCE`.
  - Specify the exception-type → error-ID mapping inline (3-entry dict literal) and the confidence-per-exception-type rule.
  - Specify the sub-schema extension fully (both `warnings[]` and `errors[]` pattern; `monorepo` shape with `required` + `additionalProperties: false`).
- **`## TDD plan` section.** Expanded from 5 named tests to **10 named tests** (T-1..T-10) + 2 sibling regression tests. Each test names its mutation-failure mode (Rule 9). T-10 is a parametrized property test for sort/dedup determinism.
- **`## Files to touch` table.** Updated row text (`_MONOREPO_PRECEDENCE` not `_MONOREPO_MARKERS`; `_ERRORS` not `_WARNINGS`; ten tests not five; sibling-test file row added).
- **`## Notes for the implementer` section.** Added/strengthened:
  - Error-IDs-go-in-`errors[]` discipline + ADR-0007 line 50 citation.
  - `_MONOREPO_PRECEDENCE` Open/Closed-at-file-boundary discipline.
  - Rule-of-three deferral for `_FRAMEWORK_SEED` + `_MONOREPO_PRECEDENCE` extractions.
  - TypedDict-for-slice-shape discipline (mypy --strict is the regression gate).
  - Arch-internal-conflict surfacing for size-cap confidence (per Rule 7).

## Verdict

**HARDENED.** The story now has 13 individually-verifiable ACs, 10 mutation-resistant TDD tests, deterministic precedence semantics encoded as data (not branching), and explicit reconciliation with ADR-0007 line 50's field-semantics rule. The memo-consumption seam is anchored by T-9 (load-bearing for S2-04). The Open/Closed extension point (`_MONOREPO_PRECEDENCE`) makes Phase 2's likely monorepo-tool additions one-line tuple insertions instead of branching-logic edits. Ready for `phase-story-executor`.
