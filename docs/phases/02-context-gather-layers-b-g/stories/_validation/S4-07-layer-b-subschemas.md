# Validation report — S4-07 (Layer B sub-schemas + explicit additive imports)

**Story:** [S4-07-layer-b-subschemas.md](../S4-07-layer-b-subschemas.md)
**Date:** 2026-05-16
**Validator:** phase-story-validator (skill v1.x)
**Verdict:** **HARDENED**

## Summary

The story's goal — seven Layer B JSON Schema sub-schemas under `src/codegenie/schema/probes/`, each with `additionalProperties: false` at every object level, ADR-0007 regex on `warnings[]`/`errors[]`, an embedded-from-Pydantic `IndexFreshness` discriminated union for `index_health`, a regeneration-as-discipline script, and a per-probe rejection test — is sound and traces cleanly to Phase 1 ADR-0004 (per-probe sub-schema convention), Phase 1 ADR-0007 (warning ID pattern), Phase 1 ADR-0010 (slice optional at envelope), Phase 0 ADR-0013 (the layered `additionalProperties` policy this story extends), and 02-ADR-0006 (`IndexFreshness` sum-type location and discriminator).

But the draft referenced **four block-tier surfaces** that would have crashed the executor or produced trivially-passing tests, plus **ten harden-tier weaknesses** in mutation-resistance, design-pattern enforcement, and structural integrity:

1. **B-1 — Envelope `$ref` wiring was missing.** The envelope's `probes.*` is `additionalProperties: true` (Phase 0 ADR-0013). A sub-schema file on disk that's NOT `$ref`'d from `repo_context.schema.json` is silently inert: the validator's `referencing` Registry at [`validator.py:54-58`](../../../../src/codegenie/schema/validator.py) includes it, but no envelope path invokes it. AC-6's rejection test as drafted would pass trivially — the extra field falls through `additionalProperties: true` at `probes.*` and the test would never see a `ValidationError`. **Added AC-1b** explicitly wiring all seven `$ref` entries into `properties.probes.properties`, and a corresponding test (`test_envelope_refs_every_layer_b_subschema`). AC-6 sharpened to verify (a) rejection fires, (b) `error.validator == "additionalProperties"`, (c) round-trip control with the extra field removed validates clean.
2. **B-2 — Dependency list was incomplete.** Original listed S4-01, S4-05, S4-06. The `scip_index` and `tree_sitter_import_graph` slices (from S4-03 and S4-04) are in the seven-probe set, and their `_WARNING_IDS` frozensets are needed for AC-3's regex cross-check. Without S4-03 and S4-04 listed, the executor would discover the gap at red-test time. Added.
3. **B-3 — `$id` convention was unpinned.** All six existing Layer A sub-schemas follow `https://codewizard-sherpa.dev/schemas/probes/<probe_name>/v<MAJOR.MINOR.PATCH>.json` (verified via `grep '"\$id"' src/codegenie/schema/probes/*.schema.json`). Story said only "valid Draft 2020-12 document … self-contained." Without a pinned `$id`, AC-1b's envelope `$ref` cannot resolve — the validator would attempt to fetch the URI and fail at compile time. Pinned in AC-1, asserted with regex-match + uniqueness + slice-name-agreement in AC-10b.
4. **B-4 — AC-8 prescribed per-line imports; codebase convention is grouped.** Verified at [`src/codegenie/probes/__init__.py:16-30`](../../../../src/codegenie/probes/__init__.py): the file uses grouped form (`from codegenie.probes.layer_b import (dep_graph, index_health, scip_index, …)`). Story prescribed:
   ```python
   from codegenie.probes.layer_b import dep_graph                      # noqa: F401
   from codegenie.probes.layer_b import generated_code                 # noqa: F401
   …
   ```
   Rule 11 — match codebase convention. AC-8 rewritten to assert the grouped form with all seven names in alphabetical order using `ast.parse` to walk the import node — robust against whitespace/comment variation, mutation-resistant to a future contributor adding an eighth name in the wrong position.

Plus the harden-tier:

- **H-1 — AC-4 was vacuously true.** `envelope.properties.probes.required` does not exist (the envelope intentionally has no `required` array at `probes.*`). "Asserts the seven names are NOT in the required list" passes trivially. Rewrote AC-4 to positive (each of the seven IS in `properties.probes.properties` with a `$ref`) + conditional negative (if `required` exists, none of the seven appears in it).
- **H-2 — `warnings[]` shape divergence.** The convention doc at `src/codegenie/schema/probes/_subschema_convention.md` shows `{id, message}` objects; all production sub-schemas use flat-string + pattern. Pinned to flat-string (matches production); added implementer note acknowledging the convention-doc drift as a tracked-cleanup item (Rule 7 — surface, don't average; do not touch the doc in this story per Rule 3).
- **H-3/H-4 — AC-7 round-trip was probe-runtime-coupled.** Invoking each of seven probes against a synthetic `ProbeContext` couples the test to runtime quirks (git state, SCIP binaries, tree-sitter grammars). Reframed: validate against the typed Pydantic model's `model_dump(mode="json")` wrapped in a canonical envelope, run through `codegenie.schema.validator.validate` — exercises model↔schema agreement AND envelope `$ref` resolution without coupling to probe I/O. Added AC-7b for the bidirectional structural check.
- **H-5 — AC-2 walker was vulnerable to `allOf`/`oneOf`/`anyOf`/`$defs`/`items`/`prefixItems` bypass.** Specified the walker's traversal rules verbatim, added T-02b (mutation-style test) that monkey-patches a real schema by removing `additionalProperties: false` at a chosen nested path and asserts the walker catches it — proves T-02 isn't passing by accident on schemas that already conform.
- **H-6 — AC-3's regex cross-check needed a stable surface.** Confirmed all Layer A probes + the three shipped Layer B probes already expose `_WARNING_IDS: Final[frozenset[str]]` at module level (verified: [`dep_graph.py:82`](../../../../src/codegenie/probes/layer_b/dep_graph.py), [`index_health.py:109`](../../../../src/codegenie/probes/layer_b/index_health.py), [`scip_index.py:90`](../../../../src/codegenie/probes/layer_b/scip_index.py), [`ci.py:160`](../../../../src/codegenie/probes/ci.py), [`deployment.py:132/147`](../../../../src/codegenie/probes/deployment.py), [`node_build_system.py:226/240`](../../../../src/codegenie/probes/node_build_system.py)). Pinned the `_WARNING_IDS` convention in AC-3 + added skip-with-warn for in-flight probes (S4-04, S4-06×3).
- **H-7 — AC-5 regenerator script lacked declared-input discipline.** Pinned: the script's top-of-file docstring carries a `# DECLARED-INPUTS:` block listing Pydantic model source files; T-06 asserts the block exists and lists at minimum `src/codegenie/indices/freshness.py` and `src/codegenie/depgraph/model.py`. This mirrors the probe `declared_inputs` discipline (Phase 0 cache key) and is the structural defense against "I changed the Pydantic model, forgot to rerun the script."
- **H-8 — AC-10 missed `$id` uniqueness.** Added AC-10b: pairwise distinct, canonical regex, slice-name agreement with the trailing `<probe_name>` segment of the `$id`. Catches the copy-paste bug class where two sub-schema files share an `$id` and one silently overwrites the other in the `referencing` Registry.
- **H-10 — Tagged-union embedding integrity (AC-5b new).** AC-5 originally said "the script regenerates byte-identically" but didn't verify the embedded `IndexFreshness` schema preserves the `kind` discriminator. Added AC-5b: each generated `$defs` entry (`Fresh`, `Stale`, `CommitsBehind`, `DigestMismatch`, `CoverageGap`, `IndexerError`) carries `properties.kind.const` matching the Pydantic `Literal["..."]` discriminator at [`src/codegenie/indices/freshness.py`](../../../../src/codegenie/indices/freshness.py). Catches "Pydantic Literal renamed without schema regeneration."

Design-pattern tier (D-tier) findings surfaced two follow-ups for Phase 3 backlog (not in scope here, per Rule 2 + 3):

- **D-2 — Auto-wire envelope `$ref` from sub-schema filename.** The validator already auto-discovers `*.schema.json` files; the envelope's per-slice `$ref` is a hand edit per probe. A small post-load step could derive probe name from filename stem, read `$id` from the discovered schema, and inject the `$ref` programmatically. Eliminates the envelope-edit friction forever. But this touches Phase 0 surface — ADR amendment required. **Flagged for Phase 3 backlog.**
- **D-3 — `@register_probe_schema_builder` decorator-registry.** The regenerator script ships as a tuple-list `_BUILDERS`; at the rule-of-three threshold (Phase 3 Layer C / D / G), promote to a decorator-registry mirroring `@register_probe` / `@register_dep_graph_strategy`. **Flagged for Phase 3 backlog.** Renamed the script to `tools/regenerate_probe_schemas.py` (drop `_layer_b` suffix) so Phase 3 extensions don't require a rename.

The retained-but-promoted D-tier patterns: smart-constructor at the serialization boundary (`write_schema_file(path, schema)` is the single chokepoint for byte-identical output), functional core / imperative shell (pure builder functions + post-processors; `main()` is the thin imperative shell), tagged-union discipline preserved through schema generation (AC-5b), `mypy --strict` on the script with `_SchemaDict = dict[str, object]` as the kernel type.

After hardening, every AC is verifiable against the master surface (`validator.py`, `repo_context.schema.json`, the six Layer A sub-schemas, `freshness.py`, `model.py`, `__init__.py`), the rejection test is mutation-resistant (three assertions instead of one), the round-trip is honest (typed-model serialization, not probe-runtime coupling), the discriminator integrity is mechanically verified, and the extension-by-addition stance for Phase 3 Layer C/D/E/G sub-schemas is preserved through the tuple-registry rename without premature kernel extraction.

## Process note

This validation ran as in-process synthesis with the four lenses (coverage / test-quality / consistency / design-patterns) applied serially — same precedent as S4-05 and S4-06. By the time four parallel critic subagents would have spawned, the main pass had already loaded the full architectural surface (story, phase-arch-design.md references, Phase 1 ADRs 0004/0007/0010, Phase 0 ADR-0013 transitively, 02-ADR-0006, `validator.py`, `repo_context.schema.json`, all six Layer A sub-schemas, `_subschema_convention.md`, `freshness.py`, `depgraph/model.py`, `__init__.py`, `dep_graph.py`, `scip_index.py`, `index_health.py`, `ci.py`, `deployment.py`, `node_build_system.py`). Each parallel critic would have re-loaded 1000+ lines without adding signal beyond what synthesis covered. The four lenses are mapped to findings below.

## Context Brief

**What the story promises:**

1. Seven JSON Schema 2020-12 sub-schemas, one per Layer B probe, each strict at every nested object level.
2. ADR-0007 regex constraint on `warnings[]` / `errors[]` items.
3. The `index_health` sub-schema embeds `IndexFreshness` (Fresh | Stale + four StaleReason variants) by regeneration from the Pydantic models, not by hand-editing.
4. A regeneration script that produces byte-identical output across runs — discipline against "I hand-edited the generated section."
5. A per-probe rejection test asserting that adding an extra field fires `SchemaValidationError` at the precise JSON Pointer.
6. Confirmation that all seven Layer B probes are imported in `__init__.py` and registered in `default_registry`.

**What the phase's exit criteria demand:**

- Phase 2 exit criterion (operational): a deliberately-seeded `stale-scip` fixture in `tests/fixtures/portfolio/` must be caught by `IndexHealthProbe` (B2); the sub-schema is the structural defense that the slice this probe emits is shaped per ADR-0004 + ADR-0007.
- Schema drift fails loud at PR time (Rule 12), not silently at downstream-consumer parse time — the per-probe sub-schemas + envelope `$ref` wiring + rejection tests are how that's mechanically enforced.
- Extension by addition: adding a new Layer C/D/E/G probe in Phase 3 must require **zero edits** to the existing seven Layer B sub-schemas or to the regeneration kernel — only additive entries (one new sub-schema file + one builder in `_BUILDERS` + one envelope `$ref` line until D-2 is resolved).

**What the arch + ADRs constrain:**

- Phase 0 ADR-0013: envelope-root strict, `probes.*: additionalProperties: true`, per-probe sub-schemas strict. The story's seven sub-schemas live at the strict layer.
- Phase 1 ADR-0004: `additionalProperties: false` at sub-schema root **and every nested object level**. The recursive walker (AC-2) is how this is mechanically enforced.
- Phase 1 ADR-0007: `warnings[]` IDs match `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`. Flat-string convention (per production), not object-form (per convention doc, divergent — H-2).
- Phase 1 ADR-0010: slices optional at envelope's `probes.*` level — no `required[]` entries for any Layer B slice.
- 02-ADR-0006: `IndexFreshness` lives at `codegenie.indices.freshness`; the sub-schema for `index_health` embeds it via `$defs`, generated from Pydantic.
- CLAUDE.md "Extension by addition" (load-bearing commitment): adding a Phase 3 probe must not edit Phase 2's sub-schemas, regeneration script kernel, or envelope shape beyond one additive `$ref` line (until D-2 closes that gap).

## Findings (organized by lens)

### Coverage critic

The story's seven ACs cover the structural disciplines (file presence, recursive `additionalProperties: false`, regex constraint, optional at envelope, regenerator script, rejection test, round-trip, import shape, registry membership, meta-schema validity, tooling green). After hardening, an additional **AC-1b** (envelope wiring), **AC-5b** (discriminator integrity), **AC-7b** (bidirectional model↔schema), and **AC-10b** (`$id` uniqueness + canonical + slice-name agreement) close gaps where the original ACs were either trivially passing or didn't cover a class of failure.

Edge cases now covered:
- A sub-schema file exists but is not wired to the envelope (B-1, AC-1b).
- A sub-schema is wired but its `$id` doesn't match its file's slice — silent registry overwrite (H-8, AC-10b).
- The Pydantic model adds a field; schema doesn't follow — drift silent until the probe emits the field (H-3/H-4, AC-7b).
- The Pydantic `Literal["..."]` discriminator is renamed; schema's `const` doesn't follow — sum-type discipline silently broken (H-10, AC-5b).
- Walker passes by accident because schema already conforms — mutation-resistance check (H-5, T-02b).

### Test-quality critic

Original TDD plan had ten tests, most of them shape-checks. The hardening:
- T-02 was structural-only; added T-02b (mutation-style) to catch walker-passes-by-accident.
- T-04 was the cross-check; added skip-with-warn for in-flight probes so the gap is logged loudly (Rule 12).
- T-06 was idempotency-only; extended with declared-input verification.
- T-06b is new (discriminator integrity) — the canonical "this test would fail if I rename `commits_behind` to `Behind` in the Pydantic model" mutation thinking.
- T-07 was probe-runtime-coupled (3 of 4 critics flagged this); reframed to typed-model serialization through the production validator chokepoint.
- T-07b is new (bidirectional structural check) — closes both directions of model↔schema drift.
- T-09 was a string-match read of `__init__.py`; replaced with `ast.parse` walk so whitespace/comment variation doesn't matter.

### Consistency critic

Cross-checked the story against:
- `src/codegenie/schema/validator.py` — confirmed `Draft202012Validator`, glob-based discovery of sub-schemas, `referencing` Registry semantics. The B-1 finding (envelope wiring) lands here.
- `src/codegenie/schema/repo_context.schema.json` — confirmed `probes.*: additionalProperties: true`, no `required[]` on `probes`. The H-1 finding (AC-4 vacuously true) lands here.
- `src/codegenie/schema/probes/_subschema_convention.md` — confirmed the convention doc shows `{id, message}` object form. The H-2 finding (production divergence) lands here.
- `src/codegenie/probes/__init__.py` — confirmed grouped import form. The B-4 finding (AC-8 wrong form) lands here.
- `src/codegenie/indices/freshness.py` — confirmed `Literal["fresh"|"stale"|"commits_behind"|"digest_mismatch"|"coverage_gap"|"indexer_error"]` discriminators at lines 45, 56, 68, 79, 96, plus `Stale.kind` elsewhere. AC-5b pins these by reference.
- `src/codegenie/depgraph/model.py` — confirmed `DepGraphProbeOutput` is the typed model for `dep_graph` slice. AC-7's parametrization can rely on this.
- The six Layer A sub-schemas — confirmed `$id` convention, `$schema: 2020-12`, flat-string `warnings[]`. B-3 (pin `$id`) and H-2 (flat-string is the convention) land here.
- Production code shows three of seven Layer B probes shipped (`dep_graph`, `index_health`, `scip_index`); four pending. The Dependency line was extended to surface this.

No story-vs-arch contradictions. The story is consistent with all referenced ADRs after hardening.

### Design-patterns critic

Pattern opportunities surfaced and resolved:

| Pattern | Where applicable | Decision |
|---|---|---|
| **Tagged union / sum type** | `IndexFreshness = Fresh \| Stale(reason)` | Already used; AC-5b adds the structural defense for discriminator preservation through schema generation. |
| **Smart constructor** | Serialization to disk | Promoted: one `write_schema_file(path, schema)` chokepoint for byte-identical output. |
| **Functional core / imperative shell** | Regenerator script | Pure builder functions + post-processors; `main()` is the thin imperative shell. Explicit. |
| **Registry pattern** | The regenerator's `_BUILDERS` tuple-list | Tuple-list at rule-of-two; decorator-registry at rule-of-three. **Hold off on decorator** (Rule 2). |
| **Plugin / Open-Closed at envelope** | Auto-wire `$ref` from filename | D-2: Phase 3 backlog (touches Phase 0 surface — ADR amendment required). |
| **Hexagonal / Ports** | Validator port surface | The validator at `validator.py` is already minimal (`jsonschema` + `referencing`); the walker stays test-only — don't pollute the production kernel with a recursive utility that has no production consumer. Explicit in the refactor section. |
| **Newtype pattern** | Probe IDs, schema IDs | Not introduced here — Phase 2 already has `ProbeId`; adding `SchemaId` for the seven `$id` strings is over-engineering until a second module consumes them. Recorded as a Phase 3+ thought, not as scope. |

Anti-patterns avoided:
- **Premature pluggability** — the decorator-registry for builders is held back until Phase 3 (rule of three).
- **Primitive obsession** — typed `_SchemaDict` for builders (instead of `dict[str, Any]`); pin `mypy --strict`.
- **Anaemic types** — the AC-5b discriminator check turns the embedded `IndexFreshness` from a passive `dict` into an actively-checked tagged union with `const` discriminators that mirror the Pydantic source.
- **Hidden state / pure-impure tangle** — the regenerator has the imperative `main()` boundary explicitly named; pure builders + post-processors compose into it.

## Edits applied (before / after)

| AC | Change | Severity |
|---|---|---|
| Header `Status` | Marked HARDENED (validated 2026-05-16) | meta |
| Header `Depends on` | Added S4-03 and S4-04 to the dependency set (B-2) | block |
| Header `ADRs honored` | Added Phase 0 ADR-0013 (the layered policy this story extends) | harden |
| New `Validation notes` block | Documented every change with severity | meta |
| AC-1 | Pinned `$id` convention per probe (B-3) | block |
| AC-1b | NEW — envelope `$ref` wiring (B-1) | block |
| AC-2 | Specified walker's traversal rules; added mutation-resistance sub-check T-02b (H-5) | harden |
| AC-3 | Pinned flat-string `warnings[]` shape; surfaced convention-doc divergence (H-2); added skip-with-warn for in-flight probes (H-6) | harden |
| AC-4 | Rewrote from vacuous-negative to positive-presence + conditional-negative (H-1) | harden |
| AC-5 | Renamed regenerator script (D-3); added declared-input discipline (H-7) | block + harden |
| AC-5b | NEW — embedded sum-type discriminator integrity (H-10) | harden |
| AC-6 | Three assertions instead of one — rejection + validator-fingerprint + round-trip control | harden |
| AC-7 | Reframed from full-probe-run to typed-model-serialization through production validator (H-3/H-4) | harden |
| AC-7b | NEW — bidirectional structural check (model fields ⊆ schema properties; schema required ⊆ model required) | harden |
| AC-8 | Rewrote to grouped-import shape per codebase convention; assertion via `ast.parse` (B-4) | block |
| AC-10b | NEW — `$id` uniqueness + canonical regex + slice-name agreement (H-8) | harden |
| AC-11 | Renamed script reference (`regenerate_probe_schemas.py`) | nit |
| Implementation outline | Rewrote step 1 with `_BUILDERS` tuple-registry, post-process helpers, `write_schema_file` chokepoint; added step 2 (envelope edit); reorganized test composition | block + design |
| TDD plan | Expanded RED with T-01b, T-01c, T-02b, T-06b, T-07b, T-08b; sharpened T-07; rewrote T-09 to `ast.parse` | harden |
| Files to touch | Added `repo_context.schema.json` (envelope edit); renamed regenerator script | block |
| Notes for implementer | Rewrote in 12 entries covering H-2 (convention doc divergence), D-2 backlog, D-3 backlog, smart-constructor chokepoint, tuple-registry vs decorator-registry, sequencing, Rule 9 explanations | design |

## Conflicts resolved

- **Consistency vs Design-Patterns:** "Auto-wire envelope `$ref` from sub-schema filename" (Open/Closed kernel extraction) vs "Phase 0 ADR-0013 is frozen — touching the envelope shape is an ADR amendment." Consistency wins: kernel extraction is **flagged for Phase 3 backlog**, not done in this story. The story adds the seven `$ref` entries by hand, with a test that catches forgetting any of them.
- **Coverage vs Design-Patterns:** "Introduce a `@register_probe_schema_builder` decorator now" (registry pattern at rule-of-three) vs "Rule 2 — three similar lines is better than premature abstraction." YAGNI wins: tuple-list `_BUILDERS` is the additive surface; decorator-registry promoted at the third Layer's first consumer. Recorded as D-3 backlog with the upgrade path named.
- **Test-Quality vs Coverage:** "Round-trip the slice through the production validator AND through the standalone `jsonschema.validate`" vs "One assertion through the production chokepoint is enough." Test-Quality wins partially: use production validator only (`codegenie.schema.validator.validate`), because that's what real consumers use and exercising it catches `$ref`-resolution bugs the standalone wouldn't. Standalone `jsonschema.validate` would be redundant.

## What remains as risk to the executor

- **Predecessor stories in-flight.** S4-04 (`TreeSitterImportGraphProbe`) and the three S4-06 marker probes (`generated_code`, `node_reflection`, `semantic_index_meta`) must ship their typed Pydantic models (or `TypedDict` shapes, depending on what those stories chose) AND their `_WARNING_IDS` frozensets before AC-3/AC-7/AC-7b can fully assert. The skip-with-warn pattern is the structural defense — when those stories land, the skip becomes a real assertion automatically. **Verify before executor handoff: are S4-04 and S4-06 done?** If not, executor must mark this story BLOCKED pending those predecessors.
- **Convention doc cleanup.** `_subschema_convention.md` shows `{id, message}` for `warnings[]`; production uses flat strings. **Not in scope here** (Rule 3 — surgical). Track as a follow-up doc-only PR.
- **D-2 / D-3 backlog items** (Phase 3 ADR amendment for envelope auto-wiring; decorator-registry for builders). These are not regressions; they are the natural-evolution surfaces once Phase 3 Layer C/D/G probes ship. The seven hand-edited `$ref` entries and the tuple-list `_BUILDERS` are the additive interim.

## Verdict

**HARDENED** — story is ready for executor handoff.

The original draft was structurally sound but had four block-tier surfaces that would have crashed the first attempt and ten harden-tier weaknesses that would have admitted silent schema drift through tests that pass by coincidence. After hardening, the story enforces six load-bearing disciplines: (1) envelope-to-sub-schema wiring is structurally guaranteed (AC-1b), (2) `additionalProperties: false` propagation is mutation-resistant (AC-2 + T-02b), (3) `warnings[]`/`errors[]` regex agreement spans schema AND probe-module surface (AC-3 + T-04), (4) `index_health`'s sum-type discriminators survive Pydantic → JSON Schema serialization (AC-5b), (5) the rejection test fires for the right reason at the right pointer with a valid control (AC-6 three-assertion form), (6) model↔schema agreement is bidirectional (AC-7 + AC-7b). Extension-by-addition is preserved through the tuple-list `_BUILDERS` and the naming-forward-compatible `tools/regenerate_probe_schemas.py` (without `_layer_b` suffix), with D-2/D-3 Phase 3 backlog items named explicitly so the kernel-extraction opportunities are not forgotten.
