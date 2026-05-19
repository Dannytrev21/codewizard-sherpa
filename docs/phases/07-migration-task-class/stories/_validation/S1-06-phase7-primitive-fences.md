# S1-06 — Phase 7 LLM-SDK + no-`Any` fences — Validation report

**Story:** [../S1-06-phase7-primitive-fences.md](../S1-06-phase7-primitive-fences.md)
**Validated:** 2026-05-19
**Validator pass:** `phase-story-validator` skill (first pass — no prior `_validation/` entry for S1-06)
**Verdict:** **HARDENED** — real, fixable weaknesses across Test-Quality, Design-Patterns, and Consistency lenses; edits applied in place; story is now ready for `phase-story-executor`.

## Context Brief (Stage 1)

### Story snapshot

- **Goal (verbatim):** Land three CI gates that protect `src/codegenie/primitives/vuln_provenance/`:
  1. An `import-linter` contract forbidding `FORBIDDEN_LLM_SDKS` under the primitive (cold-start defense).
  2. `tests/fence/test_phase7_no_llm.py` — runtime-closure scan asserting no LLM SDK imports through the primitive.
  3. `tests/fence/test_no_any_in_provenance_surface.py` — AST-walk asserting no `Any` / `dict[str, Any]` annotations on the primitive surface.
- **Effort:** S
- **Depends on:** S1-03, S1-04, S1-05
- **Status pre-edit:** `Ready`. Status post-edit: `HARDENED`.

### Files to touch (post-edit)

- `pyproject.toml` — add one `[[tool.importlinter.contracts]]` block (Phase 7 fence allowlist row #4 forward-claimed via S5-01 coordination note).
- `tests/fence/test_phase7_no_llm.py` — NEW (runtime-closure scan; AC-3 family).
- `tests/fence/test_no_any_in_provenance_surface.py` — NEW (AST-walk; AC-4 + AC-5 families).
- `tests/fence/test_phase7_importlinter_contracts_shape.py` — NEW (contract-shape pin; AC-1 family).
- `tests/fence/test_lint_imports_catches_phase7_planted_leak.py` — NEW (subprocess planted-positive; AC-2).
- `tests/fence/test_fence_target_wiring.py` — EXTEND (verify `make fence` recipe covers all four new fence files; AC-6).
- `_attempts/S1-06.md` — NEW (record three-out-of-three planted-violation evidence; AC-7).

### Phase / arch constraints

- **Phase 7 ADR-0004** — primitive home + Consequences clause enumerates exactly the two fences this story lands (`import_linter` contract extension + `tests/fence/test_phase7_no_llm.py`).
- **Phase 7 ADR-0009** — byte-edit allowlist. Row #3 (`src/codegenie/__init__.py`) and the implicit "additive new files under `tests/fence/`" path govern what this story touches.
- **Production ADR-0005** — no LLM in gather pipeline; the parent rule this story extends.
- **Production ADR-0039** — bounded additive core primitives; admits the fence extension without further architectural debate.
- **Phase 3 ADR-0010 / ADR-0011** — `Any` ban under contract-surface trees + audit-and-lint posture; this story extends both to `primitives/vuln_provenance/`.

### Existing kernel consumed (canonical home — Rule 7: do NOT fork)

- `codegenie._fence.FORBIDDEN_LLM_SDKS` (`frozenset[str]`) — the closed SDK set. Phase 7 imports; does not redefine.
- `codegenie._fence.scan_installed_distribution` — runtime-closure scanner (used by Phase 0 fence). Phase 7's runtime-closure fence works at a different scope (package-walk vs distribution-requires), so it does not import this function directly, but the *constant* is shared.
- `codegenie._phase3_fence.walk_any_annotations(src: str, path: Path) -> list[Violation]` — canonical AST walker. Phase 7 imports verbatim; does not extract, fork, or rename.
- `codegenie._phase3_fence.Violation` (frozen dataclass with `kind: ViolationKind` closed `Literal`) — reused for hit aggregation.
- `codegenie._phase3_fence.PHASE3_ROOTS` precedent — Phase 7 mirrors with a parallel module-level `PHASE7_ROOTS: Final[tuple[Path, ...]]` constant in the fence test file. Phase 3's `PHASE3_ROOTS` is **not** modified (anti-additive — Phase 7 ADR-0009 byte-edit allowlist would forbid it).

### Sibling-family lineage (Design-Patterns)

- This story is the **2nd concrete consumer** of the `walk_any_annotations` walker (Phase 3 S1-05 was the 1st).
- **Rule-of-three threshold:** NOT YET REACHED. Phase 8+ extending the fence to a third surface (e.g., a hypothetical `primitives/dep_chain/`) is the third consumer that would justify lifting per-phase root tuples into a shared registry (`codegenie._fence_roots`). Surfaced as a forward note; out of scope for this story.
- **Prior validation framings carried forward:** Phase 3 S1-05's discipline (per-shape mutation matrix, floor guard, planted-positive vs metamorphic complement parity, ADR-named docstrings, marker-grammar strictness) is the canonical shape Phase 7 mirrors.

### Goal-to-AC trace

| AC | Trace to goal | Verdict |
|---|---|---|
| AC-1 contract shape | Cold-start defense (gate 1) | ✓ strong |
| AC-2 lint-imports planted leak | Cold-start defense (gate 1) | ✓ strong |
| AC-3.a–e runtime-closure scan | Runtime fence (gate 2) | weak on test-isolation discipline + metamorphic concrete invariant (F4, F5) |
| AC-4 AST walk + planted matrix | AST fence (gate 3) | weak on walker-function naming + `PHASE7_ROOTS` extension pattern (F1, F2) |
| AC-5 `syft_reader.py` exempt-but-clean | Carve-out boundary | ✓ strong |
| AC-6 `make fence` wiring | All three gates run in CI | weak — under-specified (F7) |
| AC-7 three-planted evidence | Mutation evidence for all three gates | weak — three scenarios not enumerated (F8) |
| AC-8 gates green | Done-criterion | ✓ strong |

### Phase exit criteria the story must contribute to

- Phase 7 fence posture: `make fence` + `make lint-imports` must catch both LLM-SDK leakage and `Any`-annotation drift under the primitive surface (Phase 7 ADR-0004 Consequences + Phase 7 ADR-0009).

### Prior validation history

None. This is the first validator pass on S1-06.

### Open ambiguities (Stage 1 hard gate)

None blocking — proceeded to Stage 2.

## Findings (Stage 2 single-pass synthesis)

The four critic lenses were applied as a single-pass synthesis given the breadth of pre-fetched context (story, two existing fence implementations under `tests/fence/`, Phase 3 `_phase3_fence.py`, `pyproject.toml`'s import-linter section). Findings are tagged by lens.

### F1 — TDD-plan code blocks reference the wrong walker name (Test-Quality + Design-Patterns, **harden**)

**Pre-edit:**
> ```python
> from codegenie._phase3_fence import (  # or wherever the shared helper lives
>     has_any_annotation,
> )
> …
> hits = has_any_annotation(tree)
> ```

The canonical walker is `walk_any_annotations(src: str, path: Path) -> list[Violation]` — not `has_any_annotation(tree)`. The story's TDD plan-code-blocks would mislead an implementer into either (a) writing a new helper with the wrong signature, (b) attempting an "extraction" of code that was already extracted in Phase 3 S1-05, or (c) silently forking the walker. Each violates Rule 7 ("don't fork the canonical walker") and breaks the mutation-resistance property the validator depends on.

**Fix:** TDD-plan code-blocks rewritten to import `walk_any_annotations` (not `has_any_annotation`) and `Violation` from `codegenie._phase3_fence`. Implementation-outline §3 rewritten: "The walker `walk_any_annotations` already exists in `codegenie._phase3_fence` (extracted by Phase 3 S1-05). Import directly — do NOT extract, fork, or rename." References block tightened.

### F2 — `PHASE3_ROOTS` extension pattern not surfaced (Design-Patterns, **harden**)

Phase 3 established `PHASE3_ROOTS: Final[tuple[Path, ...]]` as the module-level scan roots, with `scan_phase3_surface()` consuming them. The Open/Closed seam is: a new phase mirrors the constant (`PHASE7_ROOTS`), it does NOT mutate Phase 3's tuple. The story did not surface this convention explicitly — the implementer could plausibly (a) hardcode paths inline, losing parametrize-friendly extension, (b) mutate `PHASE3_ROOTS` (anti-additive — Phase 7 ADR-0009 byte-edit fence forbids it), or (c) invent a new naming convention.

**Fix:** AC-4 amended to require `PHASE7_ROOTS: Final[tuple[Path, ...]]` at module scope, mirroring `PHASE3_ROOTS`. Floor guard parametrizes over `PHASE7_ROOTS` (not over a hardcoded path string). Notes-for-implementer adds: "Phase 3's `PHASE3_ROOTS` MUST NOT be mutated; Phase 7 ADR-0009 byte-edit allowlist forbids edits to `_phase3_fence.py`."

### F3 — Marker grammar Open/Closed concern (Design-Patterns, **surface in Notes**)

`codegenie._phase3_fence.ALLOWED_MARKER_RE` is regex-pinned to `P3-ADR-\d{4}`. If Phase 7 ever needs an inline exemption marker for an `Any` annotation, the regex must either (a) be widened to admit `P7-ADR-NNNN` — an edit to Phase 3's `_phase3_fence.py`, which Phase 7 ADR-0009 forbids — or (b) a phase-prefix-agnostic grammar (e.g., `P\d-ADR-\d{4}`) be adopted via Phase-3 ADR amendment.

This story's posture is "zero markers under Phase 7 surface at landing time" (mirroring Phase 3 S1-05's AC-5.d), so no marker is needed today. But a future Phase 7+ developer who *does* need one will hit this Open/Closed cliff. Recorded in Notes-for-implementer as forward guidance.

**Fix:** Notes-for-implementer entry added: "If a future Phase 7 file ever needs a `# fence: any-allowed` marker, do NOT widen `_phase3_fence.ALLOWED_MARKER_RE` from Phase 7 — that's a Phase-3 ADR amendment. The mechanically-additive path is a Phase 7 ADR that amends Phase 3's grammar to phase-prefix-agnostic." (Cross-reference to F2: Phase 3's module must not be edited from Phase 7.)

### F4 — AC-3.b's test-isolation discipline implicit (Test-Quality, **harden**)

The TDD-plan code-block for AC-3.b is a `pass` stub. The actual mutation-resistance property requires snapshotting + restoring `sys.modules[codegenie.primitives.vuln_provenance.*]` so subsequent tests see the same class identities they had at collection time. Without this, the planted-positive test leaks a re-imported primitive into the rest of the pytest run, breaking shared-state contracts (e.g., the future adapter registry from S2-01 would see a different `VulnProvenanceAdapter` class identity post-test).

**Fix:** AC-3.b amended with an explicit isolation requirement: "snapshot ALL `codegenie.primitives.vuln_provenance` and `codegenie.primitives.vuln_provenance.*` entries from `sys.modules` before injecting the planted submodule; pop them; let the scanner re-import fresh; in `finally`, restore the snapshot AND pop the post-scan re-imports." Implementation outline §2 mirrors. The body of `tests/fence/test_phase7_no_llm.py` already lands this discipline; the AC now matches the implementation contract instead of leaving it implicit.

### F5 — AC-3.c metamorphic complement scoping is hand-wavy (Test-Quality, **harden**)

Pre-edit AC-3.c said "the implementer wires this test to use a closure-scoped scanner (per Phase 0 precedent) rather than the raw `sys.modules` intersection." This is hand-wavy — an implementer could write a test that asserts a tautology and pass the AC.

**Fix:** AC-3.c amended to a concrete operational invariant:
> "Plant a fake `anthropic` module on `sys.path` (not under the primitive's path); `importlib.import_module('anthropic')` to populate `sys.modules['anthropic']`; walk the primitive packages (which must NOT re-import anthropic); pop all `FORBIDDEN_LLM_SDKS` from `sys.modules`; intersect the post-pop `sys.modules` with `FORBIDDEN_LLM_SDKS`; assert the result is empty. The invariant proven is: the primitive's import closure does not silently pull in a globally-present SDK."

The test body is now concrete enough for the executor's Validator pass to verify by inspection.

### F6 — AC-1's `as_packages = true` rationale was load-bearing but unstated (Coverage, **harden / nit**)

Pre-edit AC-1 mentioned `as_packages is True` but didn't surface the structural reason (submodules `types`, `protocols`, `errors`, `syft_reader`, `registry`, `assembly`, `events`, `sbom_verifier` silently leak otherwise). An implementer who treats the flag as cosmetic could later "clean up" the contract by dropping it.

**Fix:** AC-1.c body extended: "Without `as_packages = true`, only `vuln_provenance/__init__.py` is scanned; every submodule leaks. Pin the flag with a load-bearing error message."

### F7 — `make fence` discoverability under-specified (Consistency, **harden**)

Pre-edit AC-6 said "or that the glob covers them" and Notes mentioned "the existing `tests/fence/test_fence_target_wiring.py` from Phase 3, if present — extend it." `test_fence_target_wiring.py` does exist (Phase 3 landed it). The story should NOT condition the AC on "if present" — it is present, and the executor should extend it, not invent a new wiring test.

**Fix:** AC-6 amended: "extend `tests/fence/test_fence_target_wiring.py` with assertions that the four new Phase 7 fence files (`test_phase7_no_llm.py`, `test_no_any_in_provenance_surface.py`, `test_phase7_importlinter_contracts_shape.py`, `test_lint_imports_catches_phase7_planted_leak.py`) are covered by the `Makefile`'s `fence:` recipe." Implementation outline §6 mirrors.

### F8 — AC-7's three planted-violation scenarios were unspecified (Coverage, **harden**)

Pre-edit AC-7 said "for each of the three CI gates, evidence that a deliberately-planted violation (a) was inserted, (b) caused CI to fail, (c) was removed before merge" — but the *shape* of each violation was left to the executor. Three under-specified scenarios → the executor can be inconsistent and the validation precedent loses force.

**Fix:** AC-7 enumerates the three:
1. **Gate 1 (`import-linter` contract):** plant `import anthropic` in a temp `src/codegenie/primitives/vuln_provenance/_test_planted_phase7_leak.py`; run `make lint-imports`; capture stderr; assert non-zero exit AND failure message names both `anthropic` and `phase-7` (or `vuln_provenance`); remove planted file.
2. **Gate 2 (runtime-closure fence):** plant the same `import anthropic` file; run `pytest tests/fence/test_phase7_no_llm.py`; capture failure output; assert it names the planted file path; remove planted file.
3. **Gate 3 (no-`Any` AST fence):** plant `x: Any = 1` in a temp `src/codegenie/primitives/vuln_provenance/_test_planted_any.py`; run `pytest tests/fence/test_no_any_in_provenance_surface.py`; capture failure; assert it reports `file=…_test_planted_any.py, line=1, kind="any-name", snippet="Any"`; remove planted file.

Evidence (commands run, output, removal confirmation) recorded in `_attempts/S1-06.md`.

### F9 — `__init__.py` inclusion in AST scan is a deliberate divergence from Phase 3 (Consistency, **harden**)

Phase 3's `scan_phase3_surface()` excludes `__init__.py` from walking. Phase 7's existing implementation **includes** `__init__.py` (rationale: re-exports from `vuln_provenance/__init__.py` are part of the public surface — an `Any` annotation there is just as harmful as one in a submodule). The story does not surface this deliberate divergence. A future "consistency cleanup" PR could silently remove the inclusion.

**Fix:** AC-4 amended to require: "the AST walker scans ALL `*.py` files under `PHASE7_ROOTS` (including `__init__.py`), since re-exports in the package init are public surface. The floor guard counts non-`__init__.py` modules only (to avoid silently-greening an empty package whose init re-exports nothing)." Notes-for-implementer captures the rationale and the Phase-3 divergence.

### F10 — Forward-coupling to S5-01 byte-edit allowlist concrete (Consistency, **harden / nit**)

Pre-edit's tail note said "Coordinate file paths with the S5-01 implementer; if S5-01 has not yet been written, leave a `# TODO(S5-01)` marker." This is vague. The byte-edit allowlist mechanically tracks file paths; the executor should record the touched paths in a machine-readable form so S5-01 can consume them.

**Fix:** AC-7 (combined with implementer-notes) requires `_attempts/S1-06.md` to include a `## Forward-coupling to S5-01` section listing every byte-edit this story made to Phase 0–6.5-locked files (in practice: 1 row in `pyproject.toml`) and every new file under `tests/fence/` (4 new files). S5-01's executor mechanically picks these up from the attempt log when writing the allowlist.

### F11 — `lint-imports` invocation drift risk (Test-Quality, **nit**)

`test_lint_imports_catches_phase7_planted_leak.py` resolves `lint-imports` via `Path(sys.executable).parent / "lint-imports"` with a `shutil.which` fallback. The story does not pin this discipline. An "improvement" to use `make lint-imports` (which shells out) would re-introduce the `make` -> `subprocess` -> `make` recursion problem the Phase 3 precedent test avoids.

**Fix:** Implementer-notes entry added: "Invoke `lint-imports` directly (the console script), not `make lint-imports`. The `make` indirection (a) requires a working `make` on the test host, (b) re-invokes pytest in some configs, (c) loses pytest's `capture_output` discipline." Mirror Phase 3's precedent test.

## Edits applied to the story file

| AC / Section | Pre-edit | Post-edit summary |
|---|---|---|
| References block (`tests/fence/test_no_any_in_plugin_surface.py`) | "The `_has_any` visitor function" | Names the canonical helper exactly: `walk_any_annotations(src, path) -> list[Violation]` from `codegenie._phase3_fence` |
| References block (Phase 3 precedent) | "if the walker is already in a shared helper or extract it" | Removed — walker is extracted, story states this as fact |
| AC-1.c | `as_packages is True` | Adds rationale: "without it, submodules (`types`, `protocols`, …) silently leak; load-bearing error message in the shape-pin test" |
| AC-3.b | `pass  # implementer: fill in` | Concrete isolation discipline: snapshot+pop primitive sys.modules entries; let scanner re-import; restore in `finally` |
| AC-3.c | "implementer wires this test to use a closure-scoped scanner" | Concrete invariant: plant `anthropic` on sys.path outside primitive; walk; pop SDKs from sys.modules; assert post-pop intersection empty |
| AC-4 (AST walker) | `has_any_annotation(tree)` (wrong signature) | `walk_any_annotations(src, path) -> list[Violation]` (canonical) |
| AC-4 (`__init__.py` policy) | unstated | "Scan ALL `*.py` files including `__init__.py`; floor guard counts non-init modules only" (with Phase-3 divergence rationale) |
| AC-4 (`PHASE7_ROOTS`) | unstated | "Module-level `PHASE7_ROOTS: Final[tuple[Path, ...]]`; floor guard parametrizes over it" (Open/Closed mirror of `PHASE3_ROOTS`) |
| AC-6 | "the existing `test_fence_target_wiring.py` from Phase 3, if present" | "Extend `tests/fence/test_fence_target_wiring.py` with assertions for all four new Phase 7 fence files" |
| AC-7 | "evidence that a deliberately-planted violation (a) inserted, (b) caused failure, (c) removed" | Enumerates three concrete scenarios with shape of failure each must produce |
| Implementation outline §3 | "If `_phase3_fence` has an extractable `_has_any` … extract" | "`walk_any_annotations` already exists; import — do NOT extract, fork, or rename" |
| Notes-for-implementer | — | Added: marker-grammar Open/Closed forward note; `PHASE3_ROOTS` mutation prohibition; `lint-imports` invocation discipline; S5-01 forward-coupling section requirement |

## Verdict and next steps

**HARDENED.** The story now:

- Pins the canonical walker name (`walk_any_annotations`) and signature in the TDD plan — no silent fork risk
- Surfaces the `PHASE3_ROOTS` → `PHASE7_ROOTS` Open/Closed mirror as an explicit AC requirement
- Defines concrete invariants for each `sys.modules` discipline that was previously hand-wavy (AC-3.b isolation, AC-3.c metamorphic scoping)
- Enumerates the three planted-violation scenarios so AC-7's evidence is uniform and reproducible
- Surfaces (without escalating to AC) two forward design seams — marker-grammar grandfathering and rule-of-three threshold for a shared root-registry — so the next implementer doesn't accidentally edit Phase 3's module from Phase 7
- Concretises AC-6 to extend `test_fence_target_wiring.py` (which exists) rather than conditionally inventing a new wiring test

The story is ready for `phase-story-executor`. Note: substantial portions of the implementation already exist in the working tree (untracked) — the executor's first ReAct cycle should diff the working tree against the post-edit story spec and confirm shape match before re-running the TDD red→green→refactor loop. If shape matches, the work is effectively GREEN-pending-commit; if not, the deltas must be reconciled and recorded.

### Out-of-scope items recorded (not folded into the story)

- Lifting `PHASE3_ROOTS` / `PHASE7_ROOTS` / future `PHASE8_ROOTS` into a shared `codegenie._fence_roots` registry — defer until Phase 8+ creates the 3rd consumer (rule-of-three).
- Phase-prefix-agnostic `ALLOWED_MARKER_RE` (`P\d-ADR-\d{4}`) — defer until a real Phase 7+ marker is needed; requires Phase-3 ADR amendment, out of S1-06's surface.
- The `model_construct()` bypass fence under the primitive — already named in ADR-0004 Consequences; explicitly out of scope per the story's Out-of-scope section, deferred to S1-05 follow-up (validation note from S1-05 already records partial coverage in `test_syft_reader_has_no_model_construct_call_sites`).
