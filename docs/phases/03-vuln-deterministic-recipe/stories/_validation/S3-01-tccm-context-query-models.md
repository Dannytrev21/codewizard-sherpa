# Validation report — S3-01 `TCCM` + `ContextQuery` Pydantic models

**Story:** [`docs/phases/03-vuln-deterministic-recipe/stories/S3-01-tccm-context-query-models.md`](../S3-01-tccm-context-query-models.md)
**Date:** 2026-05-18
**Verdict:** **HARDENED**
**Validator:** `/phase-story-validator` skill (Sonnet)

## Context brief

S3-01 ships the Phase 3 plugin-private TCCM shape: `ContextQuery` (a typed graph-aware query primitive — ADR-0030 — with declared-fallback per ADR-0008) plus `TCCM` (priority-banded queries — ADR-0029 — and the `provides`/`requires` capability namespace map per ADR-0004). The story is a types-only contribution under `src/codegenie/plugins/tccm.py`; no I/O, no logger, no sibling Phase-3 modules. S3-04 (BundleBuilder) and S2-02 (manifest loader) are the downstream consumers.

Phase 02 already ships a different `TCCM` at `src/codegenie/tccm/model.py` for the probe-set declaration. The phase arch (`phase-arch-design.md §Data model` ~lines 759–773) explicitly carries the Phase-3 TCCM with `must_read` / `should_read` / `may_read` / `provides` / `requires` as a distinct shape.

## Stage 2 — four critics (parallel)

Critics ran in parallel as `general-purpose` subagents. Findings tagged `block` / `harden` / `nit`.

### Coverage critic — 4 block, 4 harden, 1 nit

| # | Tag | Issue |
|---|---|---|
| F1 | block | `args` value-type rejection untested — Notes say "reject `Any`" but no AC verifies it |
| F2 | block | `_KNOWN_PRIMITIVES` cardinality + exact-set not pinned — a 6th primitive could land silently |
| F3 | harden | `requires` empty-list permission stated in prose but no positive test |
| F4 | block | Fence assertion `_NAMESPACE_RE.match(p.split(".")[0])` accepts `scip` (no dot) and `scip.refs.deep` (two dots) — grammar too permissive |
| F5 | harden | Multi-namespace `provides` validation untested — early-return after first key would survive |
| F6 | harden | `ContextQuery` round-trip with `fallback` untested |
| F7 | block | Hashability claim in Notes (`hash(ContextQuery)` works) contradicts `args: dict` field (Pydantic v2 frozen + unhashable field = `TypeError`) |
| F8 | harden | AST source-scan AC has no test code in TDD plan; `re` was also missing from the allowlist |
| F9 | nit | `args = {}` empty-dict edge unpinned |

### Test-Quality critic — 1 block, 7 harden, 2 nit

| Item | Tag | Issue |
|---|---|---|
| TQ1 | block | Property test missing imports (`re`, `pytest`, `ValidationError`) — will `NameError` instead of asserting |
| TQ2 | harden | Negative tests are mutation-thin — single bad input per axis lets permissive-regex mutants survive |
| TQ3 | harden | No property test over invalid import paths — grammar drift in `_IMPORT_PATH_RE` invisible |
| TQ4 | harden | `_KNOWN_PRIMITIVES` set not pinned exactly (echoes Coverage F2) |
| TQ5 | harden | Hashability claim untested or wrong (echoes Coverage F7) |
| TQ6 | harden | `args` value-type rejection untested (echoes F1) |
| TQ7 | harden | Fallback recursion only 1-level deep — depth ≥ 2 untested |
| TQ8 | harden | Two-namespace `provides` round-trip absent (echoes F5) |
| TQ9 | harden | AST source-scan AC has no test code (echoes F8) |
| TQ10 | nit | `test_must_read_required` doesn't pin `loc` |
| TQ11 | nit | `TCCMParseError` markers-only discipline untested |

### Consistency critic — 1 block, 2 harden, 1 nit

| Item | Tag | Issue |
|---|---|---|
| C1 | **BLOCK** | **`PrimitiveName` smart-constructor grammar conflict with S1-01.** S1-01 HARDENED defines `parse_primitive_name` as `^[a-z][a-z0-9_]*$` (no dots); ADR-0030 primitives (`scip.refs`, `import_graph.reverse_lookup`, ...) all contain dots. The smart constructor cannot mint these values. Three resolutions: (1) amend S1-01's regex; (2) define a separate `PrimitiveName` newtype; (3) drop the smart-constructor for primitives and use `_KNOWN_PRIMITIVES` membership as the boundary. |
| C2 | harden | `TCCMParseError.reason: str` contradicts ADR-0010's "tagged-union sum types on every state machine" |
| C3 | harden | `TCCMParseError(CodegenieError)` markers-only discipline contradicts the TDD plan's typed `.reason` field reads (markers carry no class state) |
| C4 | nit | Notes' hashability claim contradicts ADR-0008 (echo of F7 / TQ5) |

### Design-Patterns critic — 2 harden tier 1, 2 harden tier 2, 4 nit

| Item | Tag | Issue |
|---|---|---|
| DP1 | harden | Primitive obsession on `TCCMParseError.reason: str` (echoes C2) — `Literal["unknown_primitive", "negative_max_files"]` |
| DP2 | harden | Helper extraction at rule-of-three already crossed for `provides` + `requires` namespace-key walking — should be Day 1 AC, not refactor advisory (S1-01 AC-18 precedent) |
| DP3 | harden | `hash(ContextQuery)` claim is incoherent with `args: dict` (echoes F7) |
| DP4 | harden | Forward-ref approach not pinned; pin to `from __future__ import annotations` (Phase-2 convention) |
| DP5 | nit | `_KNOWN_PRIMITIVES` cardinality pin missing (echoes F2 / TQ4) |
| DP6 | nit | Capability-namespace newtype deferred — flag for S2-02 (not blocking; rule-of-three not crossed) |
| DP7 | nit | `args` value union anaemic — flag for S3-04 BundleBuilder (per-primitive sum type) |
| DP8 | nit | `TCCMParseError` not in `errors.py` `__all__` — resolved by C3 (moves to plugins/tccm.py as Pydantic BaseModel, not exception) |

## Stage 3 — researcher

**Not invoked.** No findings tagged `NEEDS RESEARCH`. Canonical patterns (smart constructor, tagged union, S1-01 AC-18 helper-at-rule-of-three precedent) are already in-repo and were cited directly.

## Stage 4 — synthesis + edits

### Conflict resolution (precedence: Consistency > Coverage > Test-Quality > Design-Patterns)

- **C1 (Consistency BLOCK)** `PrimitiveName` grammar conflict — three options weighed:
  1. Amend S1-01's `parse_primitive_name` regex to allow dots. **Rejected here:** S1-01 is HARDENED and shipped; opening it for amendment exceeds this story's scope.
  2. Define a separate `PrimitiveName` newtype. **Rejected:** creates a second identifier with the same name, breaks Phase-2 + Phase-3 alignment.
  3. **Adopted:** bypass `parse_primitive_name` from `ContextQuery.create`; `_KNOWN_PRIMITIVES` membership IS the boundary; `PrimitiveName(s)` wraps directly after the check. AC-7 pins this discipline. Notes for the implementer documents the gap and points at a future S1-01 amendment as a follow-up.
- **C3 + DP1 (TCCMParseError shape)** — `TCCMParseError` redesigned as a **frozen Pydantic `BaseModel`** with `reason: Literal["unknown_primitive", "negative_max_files"]` and `details: dict[str, str | int] = {}`. Mirrors S1-01's `ParseError` precedent. Eliminates the typed-`.reason`-vs-markers-only contradiction (C3) AND closes the primitive-obsession finding (C2/DP1) in one swap. AC-4 codifies.
- **F7 + DP3 + C4 (hashability)** — Notes claim corrected. AC-16 explicitly tests `hash(ContextQuery)` raises `TypeError` AND that `model_dump_json()` is byte-deterministic across two identically-built instances. Cache-key strategy documented in Notes for downstream BundleBuilder (S3-04).
- **F4 (fence)** — replaced `_NAMESPACE_RE.match(p.split(".")[0])` with `_PRIMITIVE_RE = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")` and `fullmatch`. Three new mutation tests pin `scip` (no dot) and `scip.refs.deep` (two dots) as rejected.
- **F2 / F8** elevated to ACs (AC-5 exact set + cardinality; AC-21 AST source-scan with `re` and `__future__` in allowlist, `codegenie.errors` removed because `TCCMParseError` is no longer a marker).
- **DP2** — rule-of-three helper elevated from refactor advisory to AC-17, including an AST observable (substring-count assertion in `test_tccm_module_purity.py`).
- **TQ1, TQ2, TQ3** — property test imports fixed; negative-test corpora parametrized (8 bad namespaces, 8 bad import paths, 4 happy import paths); second property test added for import-path grammar drift.
- **F6 / TQ7** — fallback round-trip test added at depth 3.
- **F5 / TQ8** — two-namespace `provides` round-trip AC-13 added; multi-namespace iteration coverage AC-12 added; second-position invalid namespace surfaces in `loc`.
- **F1 / TQ6** — `args` non-primitive rejection parametrized over 5 payloads (AC-9).
- **F3 / F9** — positive ACs (empty `args = {}` AC-10; `requires: {valid_ns: []}` AC-14).
- **TQ10** — `test_must_read_required` now pins `loc == ("must_read",)`.
- **DP4** — forward-ref approach pinned to `from __future__ import annotations` + explicit `model_rebuild()` in Implementation outline.
- **DP6 / DP7** — deferred design opportunities recorded in Notes-for-implementer only (rule-of-three not yet crossed today).
- **DP8** — superseded by C3 resolution (`TCCMParseError` is a Pydantic BaseModel, not an exception, so the `errors.py` `__all__` question is moot).

### AC count

| Before | After |
|---|---|
| 10 unnumbered ACs (plus 1 "TDD red test exists") | 23 numbered ACs in 11 sections |

### Test count

| Before | After |
|---|---|
| 7 unit tests + 1 property test | 22 unit tests (many parametrized; effective ≈ 50 cases) + 2 property tests + 2 module-purity tests |

### Edits applied

| Section | Edit |
|---|---|
| Header | Status `Ready → HARDENED`; ADRs honored expanded (added ADR-0010, ADR-0033) |
| New `Validation notes` block | 10-bullet summary of changes for the implementer |
| Acceptance criteria | Rewritten — 23 numbered ACs grouped into 11 sections (Module surface, Error model, Primitive set + grammar, Smart constructor, args value-type rejection, provides validation, requires validation, Round-trip, Cache-key + hashability, Helper extraction, Property tests, max_files boundary, Module purity, Gates) |
| Implementation outline | Rewritten — 11 ordered steps; pins `from __future__ import annotations`, `_PRIMITIVE_RE` fence, `TCCMParseError` as Pydantic BaseModel, `_validate_namespace_keys` helper, `model_rebuild()` |
| TDD plan | Rewritten — 3 test files, all imports explicit, parametrized negatives, exact-set primitive pin, fence mutation tests, multi-namespace round-trip, fallback depth-3, hash + `model_dump_json` honesty tests, AST source-scan |
| Files to touch | Added `tests/unit/plugins/test_tccm_module_purity.py` |
| Notes for implementer | Rewritten — drops false hashability claim; documents PrimitiveName/S1-01 gap; pins forward-ref convention; documents deferred design opportunities (S2-02 newtypes, S3-04 per-primitive args sum type) |

## Verdict

**HARDENED.** Story now:

- Has 23 individually verifiable ACs, each with at least one mutation-resistant test in the TDD plan.
- Pins the closed `_KNOWN_PRIMITIVES` set, the closed `Literal` reason set on `TCCMParseError`, and the fence grammar — all three protected by tests that fail if the closed set drifts.
- Documents the `PrimitiveName` smart-constructor gap with S1-01 explicitly rather than silently diverging; future amendment path is identified in Notes.
- Corrects the hashability claim that conflicted with `args: dict[...]`; replaces with `model_dump_json()`-based cache-key strategy.
- Elevates rule-of-three helper extraction to a Day-1 AC (matching S1-01 AC-18 precedent), with an AST observable.
- Captures deferred design opportunities (capability-namespace newtypes, per-primitive args sum type) as Notes for implementer rather than premature abstractions today.
