# Validation report — S1-05 — Phase 3 import-linter contracts + AST fences

**Validated:** 2026-05-18
**Validator:** phase-story-validator skill (autonomous run via story-validation-corrector scheduled task)
**Verdict:** **HARDENED**
**Story file:** `docs/phases/03-vuln-deterministic-recipe/stories/S1-05-phase3-fence-tests.md`

---

## Context brief

S1-05 is the structural CI fence story for Phase 3. It lands three fence tests + two `import-linter` contracts so any later PR that imports an LLM SDK under `src/codegenie/{plugins,transforms}/`, introduces `Any` / `dict[str,Any]` annotations on the Phase 3 contract surface, or edits Phase 0/1/2 files outside the ADR-permitted allowlist fails CI before merge.

**Load-bearing context:**
- Goal G5 (`phase-arch-design.md:22`): no LLM SDK in Phase 3 runtime closure.
- Goal G6 (`phase-arch-design.md:22`): zero edits to Phase 0/1/2 outside ADR allowlist.
- ADR-0010 §Consequences: `dict[str, Any]` banned under `src/codegenie/{plugins,transforms}/` AND top-level `plugins/`.
- ADR-0011 §Framing: fences are audit + lint, NOT runtime — must not overclaim.
- Phase 0 precedent: `src/codegenie/_fence.py` + `tests/unit/test_pyproject_fence.py` — the live test and the planted-violation tests share the SAME production function (mutation-resistance).

**Original story strengths:**
- Honored Rule 7 by surfacing `tools/lint/importlinter.cfg` vs `pyproject.toml [tool.importlinter]` drift.
- Correctly invoked Rule 12 (fail loud) on planted-violation evidence.
- Cleanly out-of-scoped four sibling fences (capability, raw-str-id, event-taxonomy, contract-snapshot).
- Mirrored Phase 0's parametrized planted-SDK pattern for the LLM-runtime fence (in §Implementation outline, even if not as AC).

**Original story weaknesses (resolved here):**
- Helper `_walk_any_annotations` was test-local string-matching, not a production module → breaks the `_fence.py` mutation-resistance pattern.
- AST walker used shotgun `ast.walk(tree)` + string-match on `ast.unparse` — would miss `list[Any]`, `tuple[Any, ...]`, `Callable[..., Any]`, string forward-refs; would false-positive on `isinstance(x, Any)` runtime checks.
- Single planted-violation AC (AC-6 in original) didn't cover all three fences.
- Inline allowlist marker was substring-matched — bare `# fence: any-allowed` was silently honored.
- Empty Phase 3 surface would trivially green the AST fence.
- `make fence` target not amended — `phase-arch-design.md:1042` says all three fence files must run under that target.
- Floating edge-cases (type-comments, `TYPE_CHECKING`, aliased imports) lived in prose, not in tests.
- Baseline SHA mechanism had no integrity checks (could accept `HEAD`, malformed string, unreachable SHA).
- `as_packages = true` invariant was prose-only, not config-shape-asserted.

---

## Stage 2 — Four critic reports

### Coverage critic — 8 findings

| ID | Severity | Title | Resolution |
|---|---|---|---|
| F1 | block | Empty Phase 3 surface trivially greens `test_no_any_in_plugin_surface.py` | Applied — AC-5.a floor guard |
| F2 | block | Three-of-three planted-violation proofs not separately required | Applied — AC-7 split into AC-7.a (in-suite parametrized) + AC-7.b (out-of-suite evidence per fence) |
| F3 | harden | Type-comment / string-forward-ref / non-`typing` `Any` bypass paths not ACs | Applied — AC-5.b matrix includes forward-refs; AC-5.e `_known_bypasses` fixture + `KNOWN_BYPASSES` constant |
| F4 | harden | `# fence: any-allowed` marker has no governance AC | Applied — AC-5.c regex grammar + AC-5.d zero-markers assertion |
| F5 | block | `make fence` wiring not asserted | Applied — AC-3 + new `tests/fence/test_fence_target_wiring.py` |
| F6 | nit | AC 8 vague success criterion | Applied — AC-9 tightened with explicit "no skip/xfail" check |
| F7 | harden | Baseline SHA staleness has no detection AC | Partial — AC-6.b (shape + ancestor) applied; baseline-recency drift surfaced in Notes ("baseline rotates at Phase-3 phase boundaries") rather than as a fragile mechanical check |
| F8 | nit | ADR-0011 honest-framing posture not asserted in test docstrings | Applied — AC-4.e + AC-6.e docstring requirements |

### Test-quality critic — 11 findings

| ID | Severity | Title | Resolution |
|---|---|---|---|
| F1 | block | Empty-directory silent green | Applied — AC-5.a (merged with Coverage F1) |
| F2 | block | `_walk_any_annotations` heuristic misses violation classes AC-5 names | Applied — Implementation outline §1 specifies `ast.NodeVisitor` restricted to annotation contexts; AC-5.b shape matrix has 15 mutation cases |
| F3 | harden | Planted-violation test is helper-smoke, not end-to-end scanner test | Applied — Implementation outline §1 mandates `walk_any_annotations(src, path)` is called by both live + planted tests via `src/codegenie/_phase3_fence.py` (parity with `_fence.py`) |
| F4 | harden | No metamorphic complement for `test_no_llm_in_transforms.py` | Applied — AC-4.c |
| F5 | harden | `_phase2_baseline.txt` is unilaterally editable; no fence on the fence | Applied — AC-6.b shape + ancestor; AC-6.c helpful-error guard; Notes section recommends CODEOWNERS follow-up |
| F6 | block | Bare `# fence: any-allowed` without ADR ref silently honored | Applied — AC-5.c regex grammar |
| F7 | harden | Floating edge cases in §Refactor never become tests | Applied — TDD plan §Refactor lifts each to AC-5.b matrix or AC-5.e fixture catalog |
| F8 | nit | `(line, snippet)` tuple is not verified | Applied — AC-5.f + Implementation outline §1 uses `Violation` dataclass |
| F9 | harden | No verification `as_packages = true` actually covers submodules | Applied — AC-1 + AC-2 (subprocess test plants a real `import anthropic` and verifies lint-imports catches it) |
| F10 | harden | Red test is not actually red; "Red first" discipline broken | Applied — TDD plan rewritten so Red phase imports `codegenie._phase3_fence` (doesn't exist yet → ImportError → genuinely red), and the parametrized shape matrix is red-by-construction every CI run |
| F11 | nit | Property-based test for walker is a natural fit | Documented as optional Refactor stretch — Hypothesis already in dev deps; deferred (Rule 2 — parametrized matrix is the minimum bar) |

### Consistency critic — 7 findings

| ID | Severity | Title | Resolution |
|---|---|---|---|
| F1 | block | `make fence` target doesn't include new fence tests (`phase-arch-design.md:1042`) | Applied — AC-3 + Files-to-touch `Makefile` entry |
| F2 | harden | Top-level `plugins/` coverage gap (G5 + ADR-0010 line 71) | Applied — explicit Out-of-scope entry + Notes-for-implementer §forward-dependency-to-S7-01 |
| F3 | harden | Manifest drift `tools/lint/importlinter.cfg` vs `pyproject.toml` | Applied — AC-12 amends `High-level-impl.md` §Step 1 line 30 |
| F4 | nit | Test-file rename ADR-0010 inconsistency | Applied — AC-12 amends ADR-0010 §Consequences |
| F5 | nit | `ADRs honored: ADR-0001` claim is partially aspirational | Applied — header rewritten to "ADR-0001 — partial" with explicit S6-06 reference |
| F6 | harden | `_phase2_baseline.txt` + CI shallow-clone | Applied — AC-6.f CI fetch-depth note; Notes-for-implementer baseline-rotation rule |
| F7 | nit | Allowlist omits `Makefile` (Phase 0/1/2 surface) | Applied — Notes-for-implementer documents intentional `src/codegenie/`-only scope; CODEOWNERS / arch G6 boundary stated explicitly |

### Design-patterns critic — 6 findings

| ID | Severity | Title | Resolution |
|---|---|---|---|
| F1 | harden | AST walker belongs in production module (Phase 0 `_fence.py` parity) | Applied — `src/codegenie/_phase3_fence.py` is now the production walker; Files-to-touch + Implementation outline §1 + Notes-for-implementer all reinforce |
| F2 | harden | Inline marker must be parsed, not substring-matched | Applied — AC-5.c regex grammar (merged with Test-quality F6 / Coverage F4) |
| F3 | harden | AST walk should restrict to annotation contexts | Applied — Implementation outline §1 specifies `_AnyAnnotationVisitor` with explicit visitors; AC-5.b row for `isinstance(obj, Any) → expected_hit=False` is the metamorphic pin |
| F4 | nit | `Violation` as dataclass, not `tuple[int, str]` | Applied — Implementation outline §1 mandates `@dataclass(frozen=True): file/line/kind/snippet`; Notes-for-implementer surfaces newtype-style rationale tied to ADR-0010 |
| F5 | nit | Per-phase baseline file should support forward stacking | Applied — Implementation outline §10 + Notes-for-implementer mandate `_BASELINES: Final[tuple[tuple[str, Path], ...]]` so Phase-N baselines append as one row |
| F6 | positive | `Final[frozenset[str]]` constants + one-fence-per-file is the right Open/Closed shape; resist `FenceRule` ABC | Applied — Notes-for-implementer has explicit "**No `FenceRule` ABC or registry**" paragraph citing Rule 2 and the heterogeneous input/output shapes of the 5+ planned fences |

---

## Stage 3 — Research

**Not invoked.** The only `NEEDS RESEARCH` finding (Test-quality F11 — Hypothesis grammar fuzzing) was resolved by inspecting `pyproject.toml` (line 72 confirms `hypothesis` is a dev-dep) and `tests/unit/probes/test_registry_heaviness.py` (confirms prior art). Marked as deferred Refactor stretch — not load-bearing for Step 1's mutation-resistance bar, which the AC-5.b shape matrix already establishes.

---

## Stage 4 — Synthesis decisions

**Conflicts resolved via the documented priority (Consistency > Coverage > Test-Quality > Design-Patterns):**

1. **Coverage F3 (type-comment bypass) vs Test-Quality F7 (lift refactor edge cases to tests)** — same finding, different angles. Resolved by AC-5.e + `KNOWN_BYPASSES` constant: documented limitations are captured structurally, not in floating prose. The constant is exercised by `tests/fence/_fixtures/_known_bypasses.py` so a future regression that "fixes" the bypass shows up as a test edit.

2. **Test-Quality F6 (marker grammar) vs Design-Patterns F2 (marker parsed not substring-matched) vs Coverage F4 (governance)** — same finding × 3 critics. Resolved by AC-5.c regex grammar with parametrized cases.

3. **Coverage F1 (empty-surface floor) vs Test-Quality F1 (empty-dir silent green)** — same finding. Single AC-5.a covers both.

4. **Test-Quality F2 (heuristic misses) vs Design-Patterns F3 (shotgun walker)** — both address the same root cause: ad-hoc string matching instead of structural visitor. Resolved by Implementation outline §1 + AC-5.b matrix.

**No conflicts required the priority tiebreaker** — Consistency findings (mostly missing wiring + filename drift) don't overlap with Coverage/Test-Quality content findings.

**Scope discipline:**
- Did NOT add a `FenceRule` ABC or registry — Rule 2, explicit Design-Patterns F6 positive surface, deliberate Notes paragraph.
- Did NOT widen scope to top-level `plugins/` (G5 / ADR-0010 line 71) — Out-of-scope entry + forward dependency to S7-01.
- Did NOT add Hypothesis property-based fuzzing as an AC — deferred to Refactor §optional stretch.
- Did NOT add baseline-recency mechanical check (Coverage F7) — chose Notes-based "rotates at phase boundaries" rule instead of a fragile mechanical assertion that would page on every Phase 2 hotfix.

---

## Edits applied to the story

1. **Header `**Status:**`** changed `Ready` → `HARDENED`.
2. **Header `**ADRs honored:**`** rewrote ADR-0001 entry as "partial" with explicit deferred-to-S6-06 reference; ADR-0011 entry expanded with audit-not-runtime framing + CODEOWNERS mitigation.
3. **Added `Validation notes` block** under header summarizing headline changes.
4. **Acceptance criteria** completely restructured from 10 flat ACs → 12 ACs grouped (Configuration, Runtime-closure, Annotation, Kernel-frozen, Planted-violation, Scaffolding, Follow-up amendments). Sub-guards (AC-4.a–e, AC-5.a–f, AC-6.a–f, AC-7.a/b) added for granular mutation-resistance.
5. **Implementation outline** rewrote from 6 steps → 12 steps. Production-walker module now §1 (was implicit / test-local). Added meta-tests for contract shape (§5), planted leak (§6), Makefile wiring (§7). Restructured AST walker to `ast.NodeVisitor` (annotation-context-only).
6. **TDD plan §Red** rewrote so Red is genuinely red (imports a module that doesn't yet exist) and the parametrized shape matrix is red-by-construction every CI run, not just at story-landing.
7. **TDD plan §Green / §Refactor** updated to enumerate the production-walker pattern, framing docstrings, and edge-case lift-from-prose-into-tests.
8. **Files to touch** expanded from 6 rows → 15 rows. Added: `src/codegenie/_phase3_fence.py`, `Makefile`, three new test files (importlinter shape, lint-imports leak, Makefile wiring), known-bypass fixture, ADR-0010 + High-level-impl.md edits, optional `.github/workflows/*.yml` fetch-depth check.
9. **Out of scope** expanded: top-level `plugins/` directory (G5 follow-up to S7-01), Hypothesis stretch, `plugins/` lint-imports coverage.
10. **Notes for the implementer** rewrote from 6 paragraphs → 13 paragraphs covering: `_fence.py` parity, AC-7 evidence triple, `as_packages` rationale, baseline rotation rule, CI fetch-depth, `pkgutil` import side-effects, marker grammar, runtime-vs-annotation distinction, string forward-ref handling, `Violation` typed primitive, ADR-0011 framing, **explicit no-`FenceRule`-ABC rationale**, `_BASELINES` forward-compat shape, `make lint-imports` double-route, forward dependency to S7-01.

---

## Verdict

**HARDENED.** Story is ready for `phase-story-executor`. Mutation resistance is now structural (production-module walker called by every test), edge cases live in code (shape matrix + known-bypass fixture) rather than prose, the load-bearing `make fence` wiring is explicit, baseline integrity is checked, and the marker grammar is enforceable. The story explicitly resists premature `FenceRule` abstraction (Rule 2) while surfacing the right documentation seam (`tests/fence/__init__.py` docstring catalogue).

**Forward dependencies surfaced for the executor:**
- AC-12 amends ADR-0010 and High-level-impl.md (single-line edits each).
- AC-7.b requires three independent evidence blocks in `_attempts/S1-05.md` — Validator pass MUST verify all three.
- Out-of-scope §top-level `plugins/` directory: surface in `_attempts/S1-05.md` as a forward dependency for S7-01.
- CI fetch-depth: surface as a `_validation/` follow-up if `.github/workflows/*.yml` already runs `make fence` on a shallow clone.
