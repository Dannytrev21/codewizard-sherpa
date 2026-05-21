# Validation report: S1-05 — Path-scoped pyproject fence amendment

**Validated:** 2026-05-21 12:10
**Verdict:** HARDENED
**Validator version:** phase-story-validator v1

## Summary

S1-05 lands the Phase-4 fence amendment: it adds `anthropic`/`chromadb`/`fastembed`/`onnxruntime`/`keyring` to `[project.dependencies]`, narrows the Phase-0 closure-scoped `FORBIDDEN_LLM_SDKS`, and ships a new path-scoped fence (`tests/fence/test_pyproject_fence_phase4.py`) plus targeted per-rule fences and deliberate-violation fixtures. The story's goal is sound and traces cleanly to `phase-arch-design.md §Gap 5` and ADR-0003 — no RESCUE.

Four-lens review (Coverage, Test-Quality, Consistency, Design-Patterns) found **13 actionable findings — 1 block, 8 hardens, 4 nits**. The dominant pattern was the one this validator has now seen across S1-01..S1-04: *arch/ADR drift the story faithfully copied*. Three issues stood out: (1) ADR-0003 §Decision and final-design §2.1 both literally say "the Phase-0 `FORBIDDEN_LLM_SDKS` set is not edited" — a mechanically impossible claim once `anthropic` becomes a runtime dependency, already corrected by `phase-arch-design.md §Gap 5`; (2) the deny-set member `sentence_transformers` was the package's *import* name, but `FORBIDDEN_LLM_SDKS` is matched against PyPI *distribution* names (`sentence-transformers`), leaving a real fence hole; (3) the implementation prescribed four hand-rolled AST walkers in one directory while the story's own AC-11 states "use the SAME scanner" as the mutation-guard principle. Every finding had a clear in-place fix. The story was conformed to §Gap 5, the namespace bug fixed with a canonicalization AC, the three targeted tests collapsed onto the single `walk_imports` kernel, and negative-fixture coverage widened. Verdict: **HARDENED**.

**Process note:** the four critic lenses were applied inline by the synthesizer rather than via four spawned subagents — the full context (story + ADR-0003 + ADR-0006 + `_fence.py` + `test_pyproject_fence.py` + arch §Gap 5 + final-design §2.1 + `pyproject.toml` + `ci.yml` + `Makefile`) was already loaded into the main window during Stage 1, and re-spawning would have re-read the same files at a real token cost (global Rule 6) with no context-window protection benefit. All four lenses were exercised; findings are tagged by lens below.

## Findings by critic

### Coverage critic

- **F8 (harden)** — ADR-0003 §Testing strategy names `tests/fence/test_pyproject_fence_phase4.py` "a CI gate," but the CI `fence` job (`.github/workflows/ci.yml:252`) runs only `pytest ... tests/unit/test_pyproject_fence.py`. `make fence` (`Makefile:52`) already runs `tests/unit/test_pyproject_fence.py tests/fence/` — so local `make fence` and the dedicated CI `fence` job diverge. The new fence IS gated (by the CI `test` job), but a path-scope regression would fail `make fence` locally while the CI `fence` gate stays green — a confusing divergence. → new **AC-22**, `ci.yml` added to Files-to-touch.
- **F11 (nit)** — AC-12 noted it is vacuously green until S3-02; AC-13 and the AC-8(4) rag check are equally vacuous until `rag/`/`fallback/leaf/` exist but did not say so — an executor's Validator pass could wrongly flag "no runtime evidence." → AC-12/13 annotated "vacuously green until S3-02/S4-xx — expected."
- Strengths recorded: the AC set is otherwise complete and traces cleanly to the goal; the set-membership / pyproject-deps / path-scoped-fence / targeted / hygiene grouping is coherent; `Out of scope` is real and specific.

### Test-Quality critic

- **F4 (harden)** — `test_fence_ignores_llm_sdk_when_planted_in_optional_extras` plants `anthropic` in `[project.optional-dependencies]` and asserts `names & FORBIDDEN_LLM_SDKS == set()`. After the narrowing `anthropic ∉ FORBIDDEN_LLM_SDKS`, so the test passes *vacuously* — its stated mutation guard ("a regression that widens the fence to extras re-includes anthropic and dies") is dead. AC-2 ("all five tests still pass") is true but masks the toothlessness. → AC-3 now requires re-planting a still-forbidden SDK (`torch`); this is test-*data*, not scan-*logic*, so it is in scope.
- **F12 (harden)** — All four planted-violation fixtures are plain `import X` one-liners (story line: "similar one-line `import` lines"). The `ast.ImportFrom` branch of `_top_level_packages` therefore has **zero** negative coverage — it could be deleted and every fixture still pass. Separately, the "AST, not regex" guarantee asserted in Notes-for-implementer has no test — a regex regression would false-positive on `s = "import anthropic"` undetected. → AC-10 now mandates the torch fixture use `from torch import nn`; a 5th `benign_string_literal_mentions_anthropic` fixture + paired test added; new **AC-21**.
- **F9 (nit)** — the TDD-plan red test `test_pyproject_fence_phase4.py` opened with `import ast` that the file never uses (it delegates to `walk_imports`). `ruff` (AC-16) flags F401 → the red test as written fails lint. → removed from the TDD-plan code block.
- **F10 (harden, shared with Design-Patterns)** — see Design-Patterns F10.
- Mutation-resistance strengths recorded: the negative tests correctly invoke the *same* `walk_imports` the live fence uses (Phase-0 pattern mirrored); the parametrized planted-SDK approach gives one independent guard per SDK.

### Consistency critic

- **F1 (block)** — Story AC-1 narrows `FORBIDDEN_LLM_SDKS` (removes `anthropic`). **ADR-0003 §Decision** states verbatim "**The Phase-0 `FORBIDDEN_LLM_SDKS` set is not edited.**" and **final-design §2.1** states "**The original `FORBIDDEN_LLM_SDKS` set is not edited.**" Both contradict the story. Resolution: the story is *correct* and the two docs are *stale*. `test_pyproject_fence.py::test_fence_blocks_known_llm_sdks` runs a live `scan_installed_distribution()` = `requires_names_from_distribution() & FORBIDDEN_LLM_SDKS`; once `anthropic` is in `[project.dependencies]` (AC-4), keeping it in the set makes that fence fail. `anthropic` *must* leave the set. `phase-arch-design.md §Gap 5` is the considered correction and says exactly this ("the synthesis claim 'original set is unchanged' is mechanically incorrect"). Priority chain: a Gap-analysis correction that is *mechanically forced* outranks un-amended Decision prose. → story keeps the narrowing; a `⚠ STALE` annotation added to both References entries + a top-of-Notes block-finding callout; executor instructed to flag ADR-0003 §Decision/§Consequences + final-design §2.1 for amendment. A spawned-task chip was raised for that ADR amendment.
- **F3 (harden)** — AC-1 / arch §Gap 5 / final-design §2.1 all write the deny-set member as `sentence_transformers` (underscore). `FORBIDDEN_LLM_SDKS` is consumed by `_fence.py` exclusively against PyPI **distribution** names (`parse_runtime_dep_names_from_toml` reads `[project].dependencies`; `requires_names_from_distribution` reads `importlib.metadata`). The distribution is `sentence-transformers` (hyphen). Verified empirically: `packaging.requirements.Requirement('sentence-transformers>=2').name` → `'sentence-transformers'`, `Requirement('sentence_transformers>=2').name` → `'sentence_transformers'` — `Requirement` does **not** canonicalize; `_fence._name_of` only `.lower()`s. So a contributor adding the real `sentence-transformers` distribution would slip past the Phase-0 closure fence — a hole, directly undermining the story's "honest, stricter fence" rationale. (`PHASE4_STILL_FORBIDDEN` correctly keeps the underscore form — that set is matched against AST *import* names, a different namespace.) → AC-1 uses the canonical hyphen name; new **AC-19** makes `_name_of` apply `packaging.utils.canonicalize_name` (no-op for the five single-token members) + a metamorphic test planting the underscore spelling.
- **F2b (harden)** — AC-4 said only "add ... with strict version constraints." Every existing entry in `[project.dependencies]` (`networkx`, `alembic`, `orjson`, `zstandard`, `tree-sitter*`) carries an inline comment explaining its closure membership and fence relationship — a uniform, load-bearing convention (Rule 11). AC-4 omitted it. → AC-4 now requires the inline comments; `anthropic`/`chromadb`/`fastembed`/`onnxruntime` must note ADR-0003 path-scope.
- **AC-5 (nit)** — the `[project.optional-dependencies].agents` slot *does* exist (`pyproject.toml:125`) with a 3-line comment, so AC-5's premise holds. But AC-5's prescribed replacement ("Reserved for Phase 6 (langgraph)") over-claims: ADR-0003 §Consequences says Phase 6 will *path-scope* langgraph into the runtime closure too, so the slot may become vestigial. → AC-5 replacement text refined to record the supersedure without over-claiming.
- Consistency strengths recorded: the Rule-7 ADR-0006-vs-ADR-0003 conflict is correctly identified and handled by the story (References + Notes + AC-5); the three path-scope constants in AC-7 match ADR-0003 verbatim; `keyring` is correctly reasoned as not-LLM-shaped and closure-wide.

### Design-Patterns critic

- **F5 (harden)** — The three targeted fence tests (`test_only_leaf_imports_anthropic.py`, `test_rag_no_anthropic.py`, `test_no_langgraph_in_phase4.py`) each re-implemented `ast.walk` / `ast.Import` / `ast.ImportFrom` handling inline — four hand-rolled AST walkers in `tests/fence/` once `_phase4_scanner.walk_imports` is counted. This contradicts the story's *own* AC-11 principle ("uses the SAME scanner — mutating the production scanner kills both"): a contributor "simplifying" `walk_imports` would not be caught by the targeted tests, and vice versa. Rule-of-three is well past. → new **AC-20** mandates a single AST-walking kernel; the three targeted skeletons rewritten as thin `walk_imports` consumers.
- **F6 (harden)** — Internal contradiction: Implementation-outline step 6 prescribed `walk_imports(roots: Sequence[Path]) -> set[ImportViolation]` with `ImportViolation = NamedTuple(...)` and no `forbidden` parameter; the TDD-plan scanner code prescribed `walk_imports(files, *, forbidden: Iterable[str]) -> list[ImportViolation]` with a frozen dataclass. AC-11 named a third, non-existent `_walk_imports(paths, gathered_paths) -> set` signature. The omnibus tests call the keyword-`forbidden` form. → reconciled to the TDD-plan signature across step 6, AC-11, and the scanner code block.
- **F10 (harden, shared with Test-Quality)** — `ImportViolation` carried a `reason` string built generically inside `walk_imports` (`f"{pkg} imported by {f}; ADR-0003 path-scope violated"`), but AC-9 demands *rule-specific* diagnostics ("PHASE4_ADMITTED_PACKAGES are admitted only under src/codegenie/fallback/leaf/") — and the scanner cannot know which of the four rules a call site is enforcing. → `ImportViolation` reduced to a minimal `(file, package)` value object; AC-9 rewritten so rule-specific remedy text lives in each call-site assert message (the four omnibus + the targeted asserts already carry it).
- **F7 (nit)** — AC-14's `test_no_langgraph_in_phase4.py` fully duplicates the langgraph subset of AC-8(2)'s omnibus closure-wide scan; ADR-0003 §Consequences mentions only `test_only_leaf_imports_anthropic.py` and `test_rag_no_anthropic.py` as per-rule files, not a langgraph one. Rather than delete (the per-rule + omnibus split is a deliberate ADR-0003 pattern), → AC-14 annotated as an intentional per-rule echo and made a thin `walk_imports` wrapper so the redundancy costs ~3 lines, not a 4th walker.
- Design strengths recorded: putting `_phase4_scanner.py` in `tests/fence/` (not the runtime closure) is correct — it is a pure test/lint utility; the `tests/fence/__init__.py` package marker exists and `from tests.fence... import` is a proven pattern (`test_kernel_frozen.py`); the `.py.txt` fixture-extension trick correctly keeps fixtures out of pytest collection.

## Research briefs (if any)

None — no finding was tagged `NEEDS RESEARCH`. The one empirical question (does `packaging.Requirement` canonicalize names?) was resolved by a direct interpreter check, recorded under F3.

## Conflict resolutions

- **Consistency F1 vs the story's stated ADR-0003 compliance.** ADR-0003 §Decision (a source-of-truth doc) says the set is not edited; the story edits it. Normally Consistency wins and the story conforms to the ADR. Here the ADR's Decision text is *mechanically self-defeating* and `phase-arch-design.md §Gap 5` — a Gap-analysis section whose explicit purpose is to correct the synthesis — already overrides it. Resolution: §Gap 5 wins (Rule 7: pick the more-considered, surface the conflict; do not average). The story keeps the narrowing; the staleness is surfaced loudly rather than silently reconciled. This is a `block`-class contradiction with a clear in-place fix → HARDENED, not RESCUE.
- **Design-Patterns F5 (single kernel) vs Rule 2 (no premature abstraction).** No conflict: `walk_imports` already exists in the story as the shared scanner for the omnibus + negative tests; AC-20 does not *introduce* an abstraction, it *removes* three duplicate re-implementations. The simpler design and the pattern-correct design coincide.

## Edits applied

### Edit 1 — `Validation notes` block inserted under the story header
Records verdict, 13 findings, and the per-AC change list with the F1 block-finding called out.

### Edit 2 — References block annotated (Consistency F1)
`⚠ STALE DECISION TEXT` warnings added to the ADR-0003 and final-design §2.1 reference entries, pointing the executor to `phase-arch-design.md §Gap 5` as the authoritative correction.

### Edit 3 — AC-1 corrected (Consistency F3)
- Before: `frozenset({..., "sentence_transformers", "torch"})` (underscore).
- After: `frozenset({..., "sentence-transformers", "torch"})` (canonical PyPI distribution name) + rationale paragraph distinguishing distribution-name vs import-name namespaces.

### Edit 4 — AC-3 strengthened (Test-Quality F4)
- Before: "comment / docstring updated **only** ... no behavior change to the closure-scoped scan logic."
- After: still comment-only for scan *logic*, but explicitly requires re-planting `test_fence_ignores_llm_sdk_when_planted_in_optional_extras` with a still-forbidden SDK (`torch`) so the metamorphic edge-case test keeps teeth — flagged as a test-*data* change (in scope).

### Edit 5 — AC-4 strengthened (Consistency/Design F2b)
Added the requirement that each new dependency carry the inline `[project.dependencies]` comment the codebase uniformly uses, with the `anthropic`/`chromadb`/`fastembed`/`onnxruntime` comments stating the ADR-0003 path-scope.

### Edit 6 — AC-5 refined (nit)
Replacement comment text rewritten to record the ADR-0006→ADR-0003 supersedure without over-claiming a firm Phase-6 reservation; exact current 3-line comment quoted for the executor.

### Edit 7 — AC-9 reconciled (Test-Quality/Design F10)
Rewrote so `ImportViolation` is a minimal `(file, package)` value object and rule-specific remedy text lives in each call site's assert message.

### Edit 8 — AC-10 / AC-11 strengthened (Test-Quality F12, Design F6)
AC-10: the torch fixture must use `from torch import ...` (ImportFrom-branch coverage); a 5th benign string-literal fixture added. AC-11: reconciled to the canonical `walk_imports` signature (was a non-existent `_walk_imports(paths, gathered_paths)`); the benign fixture asserts zero violations.

### Edit 9 — AC-12 / AC-13 / AC-14 rewritten (Design F5, Coverage F11, F7)
All three now mandated to consume the shared `walk_imports`; AC-12/13 annotated as vacuously-green-until-later-stories; AC-14 documented as a deliberate per-rule echo of AC-8(2).

### Edit 10 — four new ACs appended (AC-19..AC-22)
- AC-19 — `_name_of` canonicalizes via `packaging.utils.canonicalize_name` + underscore-spelling metamorphic test (F3).
- AC-20 — exactly one AST-walking implementation in `tests/fence/`; all fence tests consume it (F5).
- AC-21 — negative fixtures cover the `from X import` form and the AST-not-regex guarantee (F12).
- AC-22 — the CI `fence` job runs `tests/fence/` so it matches `make fence` and ADR-0003's CI-gate claim (F8).

### Edit 11 — Implementation outline reconciled (Design F6, Coverage F8)
Step 6 rewritten with the canonical `walk_imports` signature and the no-`reason` `ImportViolation`; steps 8–11 updated for five fixtures + the CI-wiring step.

### Edit 12 — TDD plan hardened
Removed the unused `import ast` (F9); dropped `reason` from the `ImportViolation` dataclass; added the `test_scanner_ignores_string_and_comment_mentions` negative test + the `from torch import nn` and benign fixtures; rewrote the three targeted-test skeletons as `walk_imports` consumers; updated the Green checklist.

### Edit 13 — Files-to-touch + Notes-for-implementer + Goal
Added `.github/workflows/ci.yml` and the 5th fixture; updated the `_fence.py` and `test_pyproject_fence.py` rows. Added two Notes bullets (the F1 stale-ADR block-finding; the distribution-vs-import namespace explanation). Corrected `sentence_transformers`→`sentence-transformers` in the Goal and the existing "narrowing is honest" / "Phase-0 invariant preserved" notes; fixed a mis-attribution (the "synthesis claim is wrong" wording is in §Gap 5, not ADR-0003). Story `Status` set `Ready → HARDENED`.

## Verdict rationale

**HARDENED.** The story's goal — a path-scoped fence that admits the Phase-4 LLM/vector-store deps into the runtime closure while keeping the gather pipeline LLM-free — is correct and matches `phase-arch-design.md §Gap 5`. None of the 13 findings required rewriting the goal or scope; all were fixable in place. The single `block` finding (ADR-0003 / final-design §2.1 staleness) does not invalidate the story — it invalidates two un-amended sentences in older docs, which §Gap 5 had already corrected; the fix was to surface the contradiction loudly so the executor follows §Gap 5 with eyes open. The remaining findings tightened a real fence hole (`sentence-transformers` namespace), a toothless edge-case test, a 4-walker duplication, an internal signature contradiction, and a local/CI gating divergence. The story is now ready for the executor.

## Recommended next step

- `phase-story-executor` to implement S1-05.
- **Out-of-band:** ADR-0003 (§Decision + §Consequences) and `final-design.md §2.1` should be amended to drop the "the original `FORBIDDEN_LLM_SDKS` set is not edited" claim and adopt §Gap 5's honest-narrowing framing. A spawned-task chip was raised for this; it is not part of S1-05's executor scope.
