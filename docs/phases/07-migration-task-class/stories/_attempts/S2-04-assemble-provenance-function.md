# Attempt log: S2-04 — `assemble_provenance(...)` free function

## Attempt 1 — 2026-05-19 23:30 — SUCCESS

**Approach:** Red-green-refactor TDD. Wrote the headline `Both`-composition
red test first (`test_both_app_and_base_compose_into_both_variant` — failed
with `ImportError`), implemented `assemble_provenance` in `assembly.py`,
then back-filled one+ test per remaining AC. The function walks
`_ADAPTER_DISPATCH_ORDER` (S2-03), dispatches each registered adapter class
through the `AdapterFactory` (S2-02), keeps the first non-`Unknown` result
per layer, and composes `(app_result, base_result)` with a
`match`/`assert_never` block.

**ReAct cycles:** ~14.

**What worked:**
- Designing the function before writing it: read every dependency module
  (`registry.py`, `factory.py`, `protocols.py`, `types.py`, `errors.py`,
  `syft_reader.py`, `identifiers.py`, `parsers.py`) so the imports and the
  variant field shapes were right on the first implementation pass.
- The global `adapter_error_seen` flag (story Notes' recommended reading of
  arch §6) — a single `ProvenanceError` anywhere in the dispatch poisons the
  `(None, None)` arm's reason to `adapter_error`; AC-7 passes on the
  single-adapter case either way, but the global flag is the honest answer
  to partial failure.

**What didn't (resolved in-attempt):**
- **Stale `SyftSbom` placeholder in `protocols.py`.** S1-04 left a
  `TYPE_CHECKING` placeholder `class SyftSbom: ...`; S1-05 shipped the real
  model but (per its own `_lessons.md` entry) deferred the swap "until an
  adapter actually imports it". `assemble_provenance` is the first code to
  call `adapter.attribute(..., sbom)`, so `mypy --strict` flagged the real
  `SyftSbom` vs the placeholder. Completed the deferred swap — replaced the
  placeholder with the real `TYPE_CHECKING`-guarded import. See deviations.
- **mypy cannot prove tuple-pattern `match` exhaustiveness with class
  patterns.** A first cut used `case (AppDirect()|... as app, None)` for all
  four arms; `assert_never` then failed (`Argument 1 ... expected "Never"`)
  because mypy does not eliminate matched tuple shapes from the subject
  type. Fix: the fourth arm is a pure-capture `case (app, base)` — an
  irrefutable 2-tuple pattern mypy *does* recognise as making `case _`
  unreachable. The two app/base captures in that arm need `cast(...)` (mypy
  cannot cross-narrow them to non-`None`); the casts are honest — that arm
  is reached only when the class-pattern arms above did not.

**Root cause of the two snags:** both pre-existing — an S1-05-deferred
follow-up and a known mypy limitation, not story-spec defects.

**Lesson for next attempt:** none — story shipped clean.

**Validator report (Stage 3):**

### Per-AC results — all PASS (runtime-verified)
- AC-1 signature exact → `test_function_signature_is_exact`.
- AC-2 `(None,None)` → `Unknown("no_adapter_resolved")` →
  `test_empty_registry_returns_unknown_no_adapter_resolved`.
- AC-3 `(app,None)` → app unchanged (identity) →
  `test_app_only_returns_app_result_unchanged`.
- AC-4 `(None,base)` → base unchanged →
  `test_base_only_returns_base_result_unchanged`.
- AC-5 `(app,base)` → `Both` (identity; nested guard not tripped) →
  `test_both_app_and_base_compose_into_both_variant`.
- AC-6 first non-`Unknown` per layer, `Ecosystem`-sorted →
  `test_first_non_unknown_adapter_in_layer_wins` +
  `test_ecosystem_sort_order_decides_winner_not_registration_order`.
- AC-7 `ProvenanceError` → `Unknown("adapter_error")` →
  `test_provenance_error_folds_into_unknown_adapter_error`.
- AC-8 `RuntimeError` propagates →
  `test_runtime_error_propagates_and_is_not_swallowed`.
- AC-9 four-arm `match` + `assert_never` guard → AST-walk in
  `test_assemble_match_exhaustive.py` (2 tests).
- AC-10 `registry=None` → `_REGISTRY` →
  `test_registry_kwarg_defaults_to_module_registry`.
- AC-11 `adapter_factory=None` → `default_adapter_factory`, constructs once
  → `test_default_factory_constructs_each_adapter_exactly_once`.
- AC-12 body ≤ 80 LOC → `test_function_body_is_at_most_80_loc` (≈45 LOC).
- AC-13 `provenance` alias → `test_provenance_alias_is_assemble_provenance`.
- AC-14 red test exists, green → the AC-5 test was the `ImportError` red.
- AC-15 lint/type clean → see gates.

### Gates
- `pytest` full suite: 5585 passed, 69 skipped, 6 xfailed. 3 reported
  failures (`test_goldens_match_live_output`, 2× `test_lint_imports_canary`)
  are the documented `.venv/bin`-not-on-`PATH` local-env issue (S2-03
  lesson) — all 3 pass with `PATH="$PWD/.venv/bin:$PATH"`; CI runs the venv
  on `PATH`. Not caused by this story (`vuln_provenance` is outside the
  gather closure + golden path).
- `mypy --strict src/`: clean (194 files).
- `ruff check` / `ruff format --check`: clean.
- `lint-imports`: 5 contracts kept, 0 broken (incl. "phase-7 primitive does
  not import LLM SDKs").
- `tests/unit/primitives/vuln_provenance/` + `tests/fence/`: 206 + fences
  green.
- Design quality: no anti-pattern smells — no `Any`, newtypes for IDs,
  `match`/`assert_never` (no string-`kind` ladder), narrow `except
  ProvenanceError`, no new module state, no inheritance. Two `cast(...)` at
  a genuine type-gap, commented.

### Recommendation
PROCEED — all 15 ACs verified, all gates green.

**Final files touched:**
- `src/codegenie/primitives/vuln_provenance/assembly.py` — modified — added
  `assemble_provenance(...)` + module-docstring paragraph; `__all__` grows
  to `["assemble_provenance", "iter_adapters_for_layer_set"]`.
- `src/codegenie/primitives/vuln_provenance/__init__.py` — modified —
  re-exports `assemble_provenance` and the `provenance` alias; `__all__` +
  docstring grown additively.
- `src/codegenie/primitives/vuln_provenance/protocols.py` — modified —
  replaced the stale S1-05 placeholder `SyftSbom` with the real
  `TYPE_CHECKING`-guarded import (S1-05's deferred follow-up; see
  deviations).
- `tests/unit/primitives/vuln_provenance/test_assembly.py` — new — AC-1..8,
  AC-10..14 (14 tests).
- `tests/unit/primitives/vuln_provenance/test_assemble_match_exhaustive.py`
  — new — AC-9 AST-walk (2 tests).
- `tests/unit/primitives/vuln_provenance/test_types_dunder_all.py` —
  modified — `_EXPECTED_PUBLIC_ALL` grows by `assemble_provenance` +
  `provenance` (required consequence of the `__init__.py` change; S2-03
  lesson).
- `tests/unit/primitives/vuln_provenance/test_protocols_module_purity.py` —
  modified — `_ALLOWED_PROTOCOLS_IMPORTS` admits `...syft_reader` (required
  consequence of the protocols.py placeholder swap).

**Tests added:** 16 (`test_assembly.py` ×14, `test_assemble_match_exhaustive.py` ×2).

**Refactor decisions:**
- Composition is a `match`/`assert_never` block (ADR-0006 §Decision) — no
  `if r.kind in {...}` string-set ladder.
- Locals typed `Provenance | None` (not `AppKind|None`/`BaseKind|None`) so
  the loop assigns without a cast; the match's class patterns narrow on the
  way out. The two `cast(...)` are confined to the irrefutable 4th arm.
- Routed to the app/base slot by registration `Layer`, not by result type
  — the story's framing; a misbehaving adapter that smuggles a wrong-layer
  variant is rejected by `Both(...)`'s discriminated-union validation
  (fail-loud, Rule 12).
- No helper extracted — the function is ≈45 LOC, well under the 80 budget.

**Deviations from the story spec (surfaced for human review):**
- **`protocols.py` touched (not in the story's Files-to-touch).** S2-04 is
  the first `.attribute()` caller; `mypy --strict` requires the real
  `SyftSbom`. The protocols.py docstring + S1-05's `_lessons.md` entry both
  prescribe exactly this swap "when an adapter actually imports it". The
  import stays `TYPE_CHECKING`-guarded so the AC-6 forward-reference test
  (`raw["sbom"] == "SyftSbom"`) is unchanged.
- **`test_protocols_module_purity.py` touched** — one allowlist entry, the
  required consequence of the protocols.py change.
- **`test_types_dunder_all.py` touched** (not in Files-to-touch) — required
  consequence of growing `__init__.py.__all__`; S2-01/02/03 all did the
  same (recorded in `_lessons.md`).
- **`provenance` is a pure alias, not a separate wrapper.** Arch §1 sketches
  `provenance` as a thin wrapper with a `*, sbom` keyword-only signature.
  The story (AC-13 + Implementation outline + Notes "don't add another
  exported name") mandates a pure re-export alias — `provenance is
  assemble_provenance`. Followed the story (more recent, the executor
  contract; AC-13's `provenance is assemble_provenance` is unsatisfiable by
  a separate function). Arch §1's code block is now stale.
- **Test assertions use the real S1-03 variant fields, not the story's TDD
  stub fields.** The story's TDD-plan stubs reference `AppDirect(cve_id=...,
  package_id=..., chain_length=...)` — fields that do not exist on the real
  S1-03 types (`AppDirect` has `manifest_path`, `package`, `confidence`).
  AC-3's literal `result.cve_id == cve_id` is unsatisfiable; used `result
  is expected` (identity), which AC-3's own first sentence permits and is
  the stronger assertion. The story TDD-plan code blocks predate the S1-03
  type shapes.

**Follow-ups surfaced this attempt:**
- `phase-arch-design.md §Component design §1` still shows the `provenance`
  thin-wrapper with a `*, sbom` keyword-only signature. The shipped
  `provenance` is a pure alias. The arch §1 code block should be reconciled
  (cosmetic doc drift; not touched — Rule 3).
- `test_adapter_protocol_shape.py` carries a `TODO(S1-05)` to flip the AC-6
  test from the raw-string check to `get_type_hints(...) is SyftSbom`. Now
  that the real import has landed in `protocols.py`, that tightening is
  unblocked — left as a deliberate follow-up (out of S2-04 scope).
