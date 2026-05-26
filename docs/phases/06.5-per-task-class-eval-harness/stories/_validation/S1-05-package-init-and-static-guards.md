# Validation report: S1-05 — Package `__init__` + static smuggling/SDK guards

**Validated:** 2026-05-26
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S1-05 closes Step 1 of Phase 6.5 — it wires `src/codegenie/eval/__init__.py` re-exporting nine names from S1-02 / S1-03 / S1-04, lands the **recursive Pydantic field-graph substring ban** (`test_bench_score_static.py`) porting Phase 5 ADR-0014's mechanic to Phase 6.5 wire types, and lands the **AST-walking LLM-SDK import ban** (`test_eval_package_imports_no_llm_sdk.py`) as the structural complement to Phase 0's import-linter contract. The story is well-referenced — every claim traces to `phase-arch-design.md §Goal #1`, §Component design — `__init__.py`, §Testing strategy — Unit (which marks both static tests as "load-bearing"), §CI gates, §Edge cases #12, and to ADR-0008 + Phase 5 ADR-0014 + production ADR-0008. The goal is small, singular, and structurally meaningful.

But four critics converged on a **load-bearing structural flaw**: the original AC-4 promised "Both static tests fail loudly when a synthetic violation is injected: the red test §TDD plan demonstrates the failure injection" — and then the TDD plan delivered a *comment block* ("this is documentation, not executed code"). Mutation thinking: shrink `BANNED = ()`, narrow `BANNED_ROOTS = frozenset()`, flip `f.lower()` → `f`, drop `node.module.split(".", 1)[0]` to `node.module` — every mutation survives because no real model has a banned-substring field and no real `eval/*.py` imports an SDK. The tests as originally written verify "the system is currently uncontaminated"; they do NOT verify "the contamination-detection mechanism works." This is the most load-bearing story-level issue and it rests on a non-executed comment.

Layered on top: substring list duplicated across 4+ future consumers without a single source-of-truth (rule-of-three crossed by the story's own enumeration), AST walker re-implemented `ast.walk` inline despite Phase 4's deliberate "exactly one AST kernel" lesson (`tests/fence/_phase4_scanner.py`), tests placed in `tests/unit/` while the codebase convention puts structural-defense / AST-walking guards under `tests/fence/`, recursion-shape coverage matrix unspecified beyond a single one-level sanity test (the cited Phase 5 ADR-0014 *explicitly* requires dict-value-type recursion — the story did not pin it), forward-ref correctness under `from __future__ import annotations` not addressed, and AST import-shape coverage matrix unspecified across aliased / multi-name / dotted / relative shapes.

**Four critics, no `NEEDS RESEARCH`.** Every pattern is precedented in this repo: `src/codegenie/_fence.py:50` (`FORBIDDEN_LLM_SDKS` as `Final[frozenset[str]]` source-of-truth); `tests/fence/_phase4_scanner.py:walk_imports` (the single AST kernel); `tests/fence/_fixtures_phase4/violator_*.py.txt` (planted-positive-control fixture pattern); `tests/fence/test_pyproject_fence_phase4_negatives.py` (parametrised-fixture mutation-resistance pattern); `src/codegenie/vuln_index/__init__.py` and `src/codegenie/probes/__init__.py` (module-docstring ADR-citation discipline); `tests/static/test_universal_fallback_id_single_source.py` (single-source-of-truth precedent).

### Findings condensed

- **1 block:** F-COV-4 / F-TQ-1 / F-DP-8 converged — load-bearing AC-4 documentation problem; no executed mutation-resistance test.
- **15 hardens:** the source-of-truth extraction (F-TQ-6 + F-DP-1 + F-CON-F2), `walk_imports` reuse (F-DP-5 + F-DP-7), test-directory convention (F-DP-6), case-insensitive + container-shape ACs (F-COV-1, F-COV-2, F-TQ-4), forward-ref handling (F-COV-8), AST import-shape matrix (F-COV-3, F-TQ-7), duplicate-in-`__all__` (F-TQ-2), identity check (F-TQ-3), Hypothesis-or-equivalent for substring ban (F-TQ-5), `Final` discipline (F-DP-2), import-linter-contract clarification (F-CON-F7), substring-list source-of-truth phrasing (F-CON-F2), module-docstring AST-citation (F-DP-16), namespace-vs-`__all__` clarification (F-COV-6), structural-perf-observable (F-COV-7), negative-space AC #1 (F-COV-11), Mypy AC split (F-COV-5).
- **6 nits:** relative-imports pinned (F-COV-9), `test_walker_scanned_at_least_four_files` named-set (F-COV-10), per-submodule cold-start (F-TQ-11 — deferred to S2-01), `__init__.py` order (F-DP-9), `_walk` rule-of-three deferred (F-DP-4), dynamic-import bypass framing (F-DP-11), infinite-recursion safety (F-TQ-10), `test_failure_mode_is_not_public` strengthening (F-TQ-9), bypass-residual specification (F-DP-11).

### Conflict resolution

- **F-DP-3** (Design-Patterns) proposed auto-deriving `BANNED_ROOTS = FORBIDDEN_LLM_SDKS | {"anthropic"}` so the eval-package ban is structurally ≥ the closure ban. **F-CON-F7** (Consistency) clarified that the two sets are *intentionally different mechanisms* (path-scoped vs. closure-scoped) over *different artifacts* (files inside `src/codegenie/eval/` vs. `[project].dependencies`); the arch §CI gates pins `BANNED_ROOTS` to the verbatim five-name list, not to any derivation from `FORBIDDEN_LLM_SDKS`. **Consistency wins** per the validator's priority order (Consistency > Coverage > Test-Quality > Design-Patterns). The relationship is documented as a Notes-for-implementer paragraph; no auto-derivation. The five-name set stays the arch-authorised verbatim list.
- **F-COV-7** (drop wall-clock) vs the original AC #5 (≤ 200 ms) — Coverage's structural-observable replacement (AC-18) wins because wall-clock claims on CI variance are unreliable and the structural property is what made the perf claim achievable. The "≤ 200 ms" target survives in `Out of scope`.
- **F-TQ-8** (named-set sanity floor) vs **F-DP-10** (drop to `>= 1`) — F-TQ-8 wins; the named-set is a stronger structural defense and matches the F-COV-10 nit. Adopted as AC-16.

### Hardens covered

The hardened test suite resists the following mutation set (non-exhaustive):

- Shrink `SMUGGLING_SUBSTRINGS` to `frozenset()` → planted-positive-control tests fail.
- Narrow `BANNED_ROOTS` → `tests/fence/test_eval_static_negatives.py::test_walker_flags_planted_violator_fixtures` fails.
- Flip `f.lower()` → `f` in the substring check → parametrised `LlmConfidence` / `MODEL_SAYS_score` positive controls fail.
- Drop `node.level == 0` → the relative-import benign fixture trips (false-positive).
- Drop `.split(".", 1)[0]` → dotted-import violator fixtures escape detection.
- Rename `__all__` → `_all_` → `set(pkg.__all__) == EXPECTED_PUBLIC` raises `AttributeError`.
- Duplicate an entry in `__all__` → `len(set(pkg.__all__)) == 9` fails.
- Re-export the wrong symbol with the right name (e.g., `pkg.BenchScore = "string"`) → identity-equality test fails (mypy `--strict` alone cannot catch this).
- Drop the module docstring or remove an ADR citation → `ast.get_docstring`-introspected AC-5 test fails.
- Forward-ref skip: define a model under `from __future__ import annotations` with nested banned field, then break `model_rebuild()` → AC-10 synthetic test fails.
- Container-shape skip: walker silently bails on `dict[str, X]` value-type recursion → parametrised AC-9 test fails on the `_InDictValue` case.
- Self-referential model triggers infinite loop: drop the `seen: set[type]` cycle guard → `_Recursive` test hangs (failure surface).
- Re-implement `ast.walk` inline instead of reusing `walk_imports` → AC-12's `grep` mutation guard at refactor time catches it.
- Inline the four substrings in the test file → AC-7's `grep -E '"confidence"|"llm"|"self_reported"|"model_says"' tests/fence/test_bench_score_static.py` catches it.

### Consistency review

- All four cited ADR paths exist on disk (`phase-arch-design.md`, `ADRs/0008-…`, Phase 5 ADR-0014, production ADR-0008, Phase 0 S1-05).
- The nine-name enumeration matches arch §Executive summary (line 12) and §Goal #1 (line 20) byte-for-byte.
- `FailureMode` exclusion is arch-authorised — §Component design — models.py (line 532) lists six wire types, §Goal #1 lists nine total exports, the implicit decision (`FailureMode` stays module-private) is the natural reading.
- The five-name `BANNED_ROOTS` matches arch §CI gates (line 1026) verbatim.
- Cold-start budget (≤ 600 ms) is pinned at arch line 695 (the CLI surface); the story's Notes correctly recognises `__init__.py`'s import cost feeds the CLI cold-start.
- Dependency declaration (`S1-02, S1-03, S1-04`) correctly omits S1-01 — `errors.py` is consumed only by submodules (registry / loader / future runner), not by the public surface.
- The "extends Phase 0's import-linter contract" wording in the original story conflated two different mechanisms. F-CON-F7 clarified: the eval-package guard is a **parallel** structural defense over a different artifact (files in `src/codegenie/eval/**`) using a different mechanism (in-test AST walk via `_phase4_scanner.py:walk_imports`), NOT a `pyproject.toml [tool.importlinter]` edit. Phase 0's import-linter contract polices heavy modules at cold-start (`yaml`, `jsonschema`, `pydantic`, `blake3`, `structlog`) at `codegenie.cli` and `codegenie` — fundamentally different scope.
- Forward-looking phrasing: the original Notes claimed "the substring list lives in 2 test files, 1 ADR, and 1 fence-CI assertion" — but at S1-05 merge time only the two ADRs hold the list. F-CON-F2 surfaced the present-tense-vs-future-state confusion; the synthesizer's chosen fix (extract `_smuggling.py` as the structural source-of-truth NOW) collapses the issue: from the moment this story ships, the constant module IS the source-of-truth.

### Design-pattern review

Surfaced as Notes-for-implementer (NOT as ACs, per the skill's observability rule):

- **(a) Source-of-truth extraction (Final[frozenset[str]] discipline).** The codebase already has the canonical precedent at `src/codegenie/_fence.py:50` (`FORBIDDEN_LLM_SDKS`). The story's own enumeration of 4-5 future consumers of `SMUGGLING_SUBSTRINGS` puts it firmly past the rule-of-three threshold. Extract NOW (`src/codegenie/eval/_smuggling.py`), leading-underscore-private so it does NOT widen the 9-name public surface. Observable AC: AC-6 (constant defined with `Final[frozenset[str]]`) + AC-7 (consumed via import; literal-set MUST NOT appear inline — grep guard).
- **(b) Single AST-walking kernel reuse.** Phase-4's `_phase4_scanner.py:walk_imports` is **the** AST-import-walker. Re-implementing it inline (as the original story did) was about to silently violate the deliberate Phase-4 lesson. Reuse brings the `node.level == 0` relative-import filter and the `SyntaxError` skip for free. Observable AC: AC-12 (reuse `walk_imports`; grep mutation guard at refactor time).
- **(c) Planted-fixture mutation-resistance.** `tests/fence/_fixtures_phase4/` + `tests/fence/test_pyproject_fence_phase4_negatives.py` is the established pattern. Mirror it for the eval-package scanner: 6 violator fixtures (one per import shape) + 2 benign fixtures (string-mention + relative-import) + parametrised tests. The original story's AC-4 promised this; the fix delivers it as code.
- **(d) Functional core / imperative shell — clean.** `_walk` and `_candidate_models` are pure (annotation introspection only); `walk_imports` is the imperative shell (reads `.py` files). `__init__.py` is pure re-exports + assignment. No tangle.
- **(e) Sibling module-docstring convention.** `src/codegenie/vuln_index/__init__.py:1-29` and `src/codegenie/probes/__init__.py:1-14` cite ADRs in the module docstring; the S1-04 validator established AST-introspection of this convention as a structural test. AC-5 ports the same pattern to `codegenie.eval.__init__`.
- **(f) Rule of three not crossed for the Pydantic-field-walker.** `_walk` is the FIRST concrete instance in this repo. Phase 5 ADR-0014's sibling walker will be the second. Keep both copies until the third — at which point `tests/_helpers/pydantic_field_walk.py` becomes the extract target (deferred-extract framing same as S1-04's `port_base.py` discussion). Notes-for-implementer only; no AC.
- **(g) Open/Closed at the public surface.** Adding a tenth name to `__all__` IS extension-by-edit — by design (the public surface is a deliberately-closed contract, not a registry). Per-task-class extension lives in `bench/{task-class}/`, NOT in `src/codegenie/eval/`. Seam well-placed; no change.
- **(h) Path-scoped vs closure-scoped ban-set asymmetry.** `BANNED_ROOTS` (path-scoped, in-test AST walk) and `FORBIDDEN_LLM_SDKS` (closure-scoped, `[project].dependencies` scan) are *intentionally different mechanisms over different artifacts*. They do not derive from each other. Documented as a Notes-for-implementer paragraph (resolves F-DP-3 vs F-CON-F7 conflict per the validator's priority).
- **(i) Dynamic-import bypass.** `__import__("anthropic")` and `importlib.import_module("anthropic")` are acknowledged residuals — CODEOWNERS on `src/codegenie/eval/` is the compensating control. Same posture as ADR-0008 §Tradeoffs row 3 for dynamic StrEnum-value computation. Phase 16 may add a `_DynamicImportCall` AST walker; do NOT add it here (Rule 3).

## Edits applied

Story file edited in place. New `Validation notes (2026-05-26)` block appended under the story header documenting every change. Acceptance criteria expanded from 9 unnumbered checkboxes to **20 explicit `AC-N` entries** (AC-1..AC-20), organised into six labelled sections (Public-surface contract / Smuggling source-of-truth / Recursive field-graph guard / AST-walking LLM-SDK guard / Vacuous-scan defenses / Structural perf / Process gates). Implementation outline rewritten — original 5 steps grew to 9 (added: `_smuggling.py` extraction step #1, fixture-creation step #7, structural-perf-observable step #8). TDD plan completely rewritten — original 3 test files grew to 4 plus 8 planted fixtures; original ~12 tests grew to ~25 including the recursion-shape parametrised matrix, the substring-positive-control parametrised matrix, the planted-import parametrised matrix, the benign-mention parametrised matrix, the forward-ref synthetic test, the self-referential cycle-guard test, and the docstring-citation AST-introspected test. Files-to-touch grew from 4 to 14 (1 new private module + 4 new test files + 8 new planted fixtures + 1 modified `__init__.py`). Out-of-scope grew from 5 bullets to 9 with corrected import-linter-contract framing, perf-claim deferral, dynamic-bypass acknowledgment, and explicit anti-derivation clause for the two ban sets. Notes-for-implementer grew from 7 bullets to 7 labelled subsections (Discipline / Smuggling source-of-truth / `walk_imports` reuse / Banned-set relationships / Sibling Protocol-port lineage / Forward-ref correctness / Subtle gotchas / Dynamic-import bypass).

Pre/post diff summary:

| Field | Pre | Post |
|---|---|---|
| Status | `Ready` | `HARDENED` |
| ACs | 9 unnumbered | 20 numbered (AC-1..AC-20) |
| Files-to-touch | 4 | 14 |
| Test modules in TDD plan | 3 | 4 |
| Planted fixtures | 0 | 8 |
| Parametrised positive-control tests | 0 | 4 matrices (substring-naming / recursion-shape / planted-violator / benign-mention) |
| Out-of-scope bullets | 5 | 9 |
| Notes-for-implementer | 7 bullets | 7 labelled subsections |

## Findings by critic

(Inlined critic reports below for archival completeness. The terse list above is the executable summary.)

### Coverage critic — 12 findings

- **F-COV-1** (harden): case-insensitive substring match not pinned by an AC; only implicit in test code. Fix: tighten AC #3 + add parametrised negative tests.
- **F-COV-2** (harden): recursive-walker descent asserted only by a single one-level sanity check. Fix: add recursion-shape matrix AC.
- **F-COV-3** (harden): AST import-shape coverage incomplete (aliased / multi-name / dotted). Fix: parametrised planted-import fixtures.
- **F-COV-4** (BLOCK): AC #4's "synthetic violation injection" rests on a non-executed comment. Fix: executed planted-fixture tests.
- **F-COV-5** (harden): AC #6 (mypy resolves all nine names) bundles two distinct claims. Fix: split into runtime + static-import-check.
- **F-COV-6** (harden): "nine names and nothing else" — the "nothing else" half is under-pinned for module namespace. Fix: clarify `__all__` is the contract boundary.
- **F-COV-7** (harden): wall-clock perf AC (≤ 200ms) is unreliable on CI. Fix: replace with structural observable (tests don't live-import subject modules).
- **F-COV-8** (harden): forward-ref annotations under `from __future__ import annotations` not addressed. Fix: add AC + synthetic test.
- **F-COV-9** (nit): relative imports not explicitly pinned. Fix: comment in Notes (resolved by `walk_imports` reuse).
- **F-COV-10** (nit): `>= 4 files` threshold is arbitrary. Fix: named-set superset.
- **F-COV-11** (harden): negative-space "adding a tenth name fails CI" not explicit in AC. Fix: rephrase AC #1.
- **F-COV-12** (nit): empty-package failure mode not named in AC. Fix: AC includes `is_dir` + non-empty.

Verdict: **HARDEN.**

### Test-Quality critic — 12 findings

- **F-TQ-1** (BLOCK): no positive-control fixtures for either static guard. Fix: planted fixtures (mirrors Phase-4 pattern).
- **F-TQ-2** (harden): duplicate-in-`__all__` not caught without `len()` guard. Fix: add `len(set(...))` assertion.
- **F-TQ-3** (harden): `is not None` is a tautology hole on identity. Fix: identity equality per name.
- **F-TQ-4** (harden): recursion sanity test shallow. Fix: parametrised synthetic-model matrix.
- **F-TQ-5** (harden): substring ban is a natural property-test target (hypothesis available). Fix: parametrised matrix is the practical equivalent.
- **F-TQ-6** (harden): `BANNED` / `BANNED_ROOTS` duplicated. Fix: extract `_smuggling.py`.
- **F-TQ-7** (harden): aliased / multi-name / dotted shapes not pinned. Fix: planted-fixture matrix.
- **F-TQ-8** (harden): `>= 4` threshold not intent-bound. Fix: named-set superset.
- **F-TQ-9** (nit): `test_failure_mode_is_not_public` too narrow. Fix: strengthen to include reachability.
- **F-TQ-10** (nit): no infinite-recursion safety test. Fix: synthetic recursive model in matrix.
- **F-TQ-11** (nit): cold-start fence not enforced; deferred to S2-01. Fix: explicit Out-of-scope.
- **F-TQ-12** (nit): dynamic-import bypass framing. Fix: Notes-for-implementer.

Verdict: **HARDEN.**

### Consistency critic — 12 findings (10 confirming, 2 actionable)

- **F-CON-F1**: `_load_breakdown_keys` / `_load_failure_mode_taxonomy` are private (leading-underscore). No conflict.
- **F-CON-F2** (harden): the "list lives in 4 places" claim is forward-looking; at merge time only the 2 ADRs hold the list. Fix: extract `_smuggling.py` NOW (resolved by F-DP-1 + F-TQ-6).
- **F-CON-F3** (nit): self-referential import from `codegenie.eval` (not `codegenie.eval.models`). Acceptable.
- **F-CON-F4** (confirming): nine-name enumeration matches arch byte-for-byte. ✓
- **F-CON-F5** (confirming): `FailureMode` exclusion is arch-authorised. ✓
- **F-CON-F6** (confirming): banned-import set matches arch §CI gates verbatim. ✓
- **F-CON-F7** (harden): "extends Phase 0's import-linter contract" wording conflates two mechanisms. Fix: clarify in Out-of-scope.
- **F-CON-F8** (confirming): cold-start budget cited correctly. ✓
- **F-CON-F9** (confirming): all referenced doc paths exist on disk. ✓
- **F-CON-F10** (confirming): dependency declaration correct. ✓
- **F-CON-F11** (confirming): `@register_task_class` precedent claim against `@register_probe` accurate. ✓
- **F-CON-F12** (confirming): "Extension by addition" honored. ✓

Verdict: **HARDEN.**

### Design-Patterns critic — 16 findings

- **F-DP-1** (harden): substring source-of-truth duplicated across 4 future consumers. Fix: extract `_smuggling.py`.
- **F-DP-2** (harden): `Final[frozenset[str]]` discipline. Fix: annotate both.
- **F-DP-3** (harden, resolved via Consistency): `BANNED_ROOTS` vs `FORBIDDEN_LLM_SDKS` relationship. Conflict resolved: don't auto-derive (Consistency wins); document relationship as Notes.
- **F-DP-4** (nit): `_walk` rule-of-three not yet crossed. Notes only.
- **F-DP-5** (harden): AST-walker should reuse `_phase4_scanner.py:walk_imports`. Fix: AC-12 reuse mandate.
- **F-DP-6** (harden): wrong test directory. Fix: move all tests to `tests/fence/`.
- **F-DP-7** (harden): `_banned_imports_in` missing `node.level == 0` filter. Fix: resolved by reusing `walk_imports`.
- **F-DP-8** (harden): planted-positive-control fixtures absent. Fix: ship them (mirrors Phase-4 pattern).
- **F-DP-9** (nit): `__init__.py` order convention. Fix: Notes for implementer.
- **F-DP-10** (nit, superseded by F-TQ-8): `>= 4` threshold. F-TQ-8 stronger fix adopted.
- **F-DP-11** (nit): dynamic-import bypass — specification-by-example. Fix: light Notes update.
- **F-DP-12** (info): Functional core / imperative shell — clean. ✓
- **F-DP-13** (info): Newtype / primitive obsession — N/A. ✓
- **F-DP-14** (info): Composition / hidden state — clean. ✓
- **F-DP-15** (info): Open/Closed at public surface — preserved. ✓
- **F-DP-16** (harden): module-docstring ADR-citation discipline missing AC. Fix: AC-5 (AST-introspected).

Verdict: **HARDEN.**

## Verdict rationale

**HARDENED.** One block-grade finding (F-COV-4 / F-TQ-1 / F-DP-8 converged on the load-bearing AC-4 documentation problem — the static guards as originally written would pass forever even if the contamination-detection mechanism was completely broken). Fifteen hardens converged across the four critics. Six nits absorbed. Zero `NEEDS RESEARCH` — every pattern is precedented in this repo (`_fence.py`, `_phase4_scanner.py`, `_fixtures_phase4/`, `vuln_index/__init__.py`, `probes/__init__.py`, `test_universal_fallback_id_single_source.py`, `test_pyproject_fence_phase4_negatives.py`). All fixes are precedented in-place edits.

The hardened suite makes the load-bearing structural defenses *actively verified*, not passively trusted. The mutation set the story now resists (per the Validation notes block) is comprehensive enough that a future contributor cannot silently break the smuggling ban, the SDK-import ban, the 9-name public surface contract, the forward-ref handling, the recursion-shape coverage, or the source-of-truth discipline — every one of those mutations now fails a parametrised positive-control test that did not exist before.

## Recommended next step

Pass to `phase-story-executor`. The story is ready for autonomous implementation.
