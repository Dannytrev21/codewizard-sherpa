# Story S4-07 — Layer B sub-schemas + explicit additive imports

**Status:** Done
**Completed:** 2026-05-17
**Attempts:** 2 (1 implementation, 1 validation run — see `_attempts/S4-07.md`)
**Evidence:**
- Files: `tools/regenerate_probe_schemas.py`, `src/codegenie/schema/probes/{index_health,scip_index,tree_sitter_import_graph,dep_graph,generated_code,node_reflection,semantic_index_meta}.schema.json`, `src/codegenie/schema/repo_context.schema.json` (seven additive `$ref` entries), `src/codegenie/probes/__init__.py` (Layer B grouped-import block), `tests/unit/probes/layer_b/test_subschemas.py`, `tests/unit/probes/layer_b/_schema_walkers.py`
- Tests: 48 test functions / 58 parametrized rows in `tests/unit/probes/layer_b/test_subschemas.py` — all green (10 expected skip-with-warn rows for AC-7/AC-7b on dict-shaped slices, preserving Rule 12 fail-loud discipline)
- Gates: `pytest` 2347 passed / 15 skipped / 2 xfailed (pre-existing); `ruff check` clean; `ruff format --check` clean (295 files); `mypy --strict src/` clean (94 source files); `lint-imports` 2 contracts kept / 0 broken; coverage 93.22% (above 85% floor)
- Commit: (pending human merge)

**Step:** Step 4 — Ship `IndexHealthProbe` (B2) + Layer B structural probes
**Original status (pre-execution):** Ready — HARDENED (validated 2026-05-16)
**Effort:** S
**Depends on:** S4-01 (`IndexHealthProbe` shipping the `index_health` slice shape + `_WARNING_IDS` frozenset), S4-03 (`SCIPIndexProbe` shipping the `scip_index` slice shape + `_WARNING_IDS` frozenset), S4-04 (`TreeSitterImportGraphProbe` shipping the `tree_sitter_import_graph` slice shape + `_WARNING_IDS` frozenset), S4-05 (`DepGraphProbe` shipping the `dep_graph` slice and `DepGraphProbeOutput` Pydantic model + `_WARNING_IDS` frozenset), S4-06 (the three marker probes shipping `generated_code`/`node_reflection`/`semantic_index_meta` slices + `_WARNING_IDS` frozensets — `node_reflection` is the slice key per S4-06 final shape, not `reflection`)
**ADRs honored:** Phase 1 ADR-0004 (`additionalProperties: false` at sub-schema root + every nested block — the per-probe sub-schema convention), Phase 1 ADR-0007 (warning/error ID pattern `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$` enforced on `warnings[]` and `errors[]`), Phase 1 ADR-0010 (slice optional at envelope), Phase 0 ADR-0013 (envelope `probes.*: additionalProperties: true`, per-probe sub-schemas strict — the layering this story extends), [`02-ADR-0006`](../ADRs/0006-index-freshness-sum-type-location.md) (the `index_health` sub-schema embeds the `IndexFreshness` Pydantic JSON Schema generated from `codegenie.indices.freshness`)

## Validation notes (2026-05-16)

Hardened by `phase-story-validator` (v1.x) before executor handoff. The original draft's goal and overall shape are sound — seven Layer B sub-schemas, recursive `additionalProperties: false` enforcement, ADR-0007 pattern on `warnings[]`/`errors[]`, embedded `IndexFreshness` for `index_health`, regeneration-as-discipline. The hardening pass fixed:

- **B-1 (block) — Envelope `$ref` wiring was missing.** The envelope's `probes.*` is `additionalProperties: true` (Phase 0 ADR-0013), so a sub-schema file on disk that's NOT `$ref`'d from `repo_context.schema.json` is silently inert; the validator's `referencing` Registry includes it but never invokes it. AC-6's rejection test would have passed trivially (the extra field falls through `additionalProperties: true` at `probes.*`). **Added AC-1b** (envelope wiring) and **AC-6 was sharpened** (asserts the rejection fires AND that `error.validator == "additionalProperties"`, plus a round-trip control showing the same envelope-without-the-extra-field validates clean).
- **B-2 (block) — Dependency list was incomplete.** Original listed S4-01, S4-05, S4-06. AC-7 (round-trip) and AC-3 cross-checks need `_WARNING_IDS` frozensets and slice shapes from S4-03 (`SCIPIndexProbe`) and S4-04 (`TreeSitterImportGraphProbe`) too. Added.
- **B-3 (block) — `$id` convention was unpinned.** All Layer A sub-schemas use `https://codewizard-sherpa.dev/schemas/probes/<probe_name>/v<MAJOR.MINOR.PATCH>.json`. Story said only "valid Draft 2020-12." Without a pinned `$id`, the envelope's `$ref` can't resolve. Pinned in AC-1, asserted in AC-10b.
- **B-4 (block) — AC-8 prescribed per-line imports; actual codebase uses grouped `from … import (a, b, c)`.** Rule 11 — match codebase convention. The current `src/codegenie/probes/__init__.py:26-30` is `from codegenie.probes.layer_b import (dep_graph, index_health, scip_index, …)`. AC-8 rewritten to assert the grouped form contains all seven names in alphabetical order inside a single `import (…)` block, with the per-name `# noqa: F401 — S4-XX registration` trailer convention preserved.
- **H-1 (harden) — AC-4 was vacuously true.** `envelope.properties.probes.required` does not exist; the assertion "names are NOT in `required`" passes trivially. Rewrote AC-4 to a positive check: each of the seven probe names IS present in `properties.probes.properties` with a `$ref` whose target equals the sub-schema's `$id` — proving the wiring AND the optional-ness (because no `required` array is introduced).
- **H-2 (harden) — `warnings[]` shape divergence.** The convention doc shows `{id, message}` objects; production sub-schemas use flat-string + pattern. Pinned to flat-string (matches production); added implementer note acknowledging the convention-doc drift (Rule 7 — surface, don't average; the convention doc is a tracked-cleanup item separate from this story).
- **H-3/H-4 (harden) — AC-7 round-trip was probe-runtime-coupled.** Invoking each of seven probes against a synthetic context creates per-probe fixture sprawl AND ties the test to runtime quirks. Reframed AC-7 to validate against the typed Pydantic model's `model_dump(mode="json")` — exercises model↔schema agreement without coupling to probe I/O. Added AC-7b: bidirectional structural check that `model.__fields_set__` ⊆ schema's declared properties AND schema's `required[]` ⊆ model's required fields, so "schema-allows-more-than-model" and "model-requires-more-than-schema" both fail loud.
- **H-5 (harden) — AC-2 walker was vulnerable to `allOf`/`oneOf`/`anyOf`/`$defs`/`items`/`prefixItems` bypass.** Specified the walker's traversal rules verbatim; added T-02b (mutation-style test) that monkey-patches a real schema by removing `additionalProperties: false` at a chosen depth and asserts the walker catches it — this is the load-bearing mutation-resistance check.
- **H-6 (harden) — AC-3's regex cross-check needed a stable surface.** Confirmed all Layer A probes + the three shipped Layer B probes already expose `_WARNING_IDS: Final[frozenset[str]]` at module level (verified: `dep_graph.py:82`, `index_health.py:109`, `scip_index.py:90`, `ci.py:160`, `deployment.py:132/147`, `node_build_system.py:226/240`). Pinned the convention in AC-3 and added a precondition note for the four probes whose `_WARNING_IDS` shipping is in-flight (S4-04, S4-06×3).
- **H-7 (harden) — AC-5 regenerator script lacked declared-input discipline.** Pinned: the script's top-of-file docstring lists its declared inputs (Pydantic model files), mirroring the probe `declared_inputs` discipline. T-06 extended to assert a `# DECLARED-INPUTS:` block exists and lists `src/codegenie/indices/freshness.py` and `src/codegenie/depgraph/model.py`.
- **H-8 (harden) — AC-10 missed `$id` uniqueness.** Added AC-10b: the seven `$id` values are pairwise distinct, match the canonical regex, and the slice's identifier under `properties.probes` equals the trailing `<probe_name>` segment of its `$id`.
- **H-10 (harden) — Tagged-union embedding integrity.** AC-5 originally said "the script regenerates byte-identically" but didn't verify the embedded `IndexFreshness` schema preserves the `kind` discriminator. Added AC-5b: the generated `index_health.schema.json`'s `$defs` includes `Fresh`, `Stale`, `CommitsBehind`, `DigestMismatch`, `CoverageGap`, `IndexerError`, each carrying `properties.kind.const` matching the Pydantic `Literal["..."]` discriminator. Catches "Pydantic discriminator changed, schema didn't follow."
- **D-2 (design pattern) — Open/Closed at the schema directory.** The validator at `src/codegenie/schema/validator.py:51-52` already auto-discovers all `*.schema.json` files via `glob`, so the **registry side** is closed (kernel doesn't know about specific probes). But the envelope's `properties.probes.<name>: {$ref: …}` is a hand edit per probe. The story's seven-line envelope edit IS the friction the kernel would close. **Decision: hold off on a kernel extraction** (Rule 2 — the rule-of-three threshold has not been re-crossed; the existing six Layer A entries + seven Layer B entries = 13 hand edits, which IS past the rule of three, BUT extracting the kernel touches `repo_context.schema.json`'s shape and the validator, both Phase 0 surfaces — that's a Phase-0-amendment, not in Phase 2 scope). Recorded as a **Notes-for-implementer follow-up** naming the future kernel path: `validator.py` post-load step that auto-adds `properties.probes.<filename_stem>: {$ref: <sub_schema.$id>}` for every discovered sub-schema, dropping the per-probe envelope edit forever. **Flag for Phase 3 backlog.**
- **D-3 (design pattern) — Regenerator script naming.** Renamed prescribed file to `tools/regenerate_probe_schemas.py` (drop the `_layer_b` suffix) and structure as a `_BUILDERS: list[tuple[str, Callable[[], dict]]]` tuple-registry so Phase 3 Layer C probes extend by tuple insertion, not script edit (additive surface; preserves the rule-of-three discipline for the eventual `@register_probe_schema_builder` decorator).
- **D-5 (design pattern) — Smart-constructor at the serializer boundary.** Pinned a single `write_schema_file(path, schema_dict)` chokepoint inside the regenerator, so the byte-identical-output discipline lives in one function (not seven copies of `json.dumps(..., indent=2, sort_keys=True) + "\n"`).

**Full audit log:** [`_validation/S4-07-layer-b-subschemas.md`](_validation/S4-07-layer-b-subschemas.md).

## Context

Phase 1 ADR-0004 established the per-probe sub-schema convention: every probe ships a JSON Schema at `src/codegenie/schema/probes/<probe_name>.schema.json` with `additionalProperties: false` at **the root and every nested object level**. The envelope validator (Phase 0) loads the sub-schemas and validates each slice against its named schema before persisting `repo-context.yaml`. A slice with an unknown field fails validation at the precise JSON Pointer (`/probes/<name>/<bad_field>`), making schema drift loud at PR time.

This story lands the seven Layer B sub-schemas — one per probe shipped in S4-01, S4-03, S4-04, S4-05, S4-06 (three) — and updates `src/codegenie/probes/__init__.py` with the explicit additive imports for each. The sub-schemas were intentionally deferred from the per-probe stories to consolidate the schema-drift discipline in one place. The probes emit the slices; this story validates them.

**`additionalProperties: false` discipline.** Every sub-schema sets it at the root AND at every nested object. The `index_health` sub-schema is the deepest: `{<index_name>: {freshness: {kind: "fresh"|"stale", reason: {kind: "commits_behind"|"digest_mismatch"|...}}, ...}}` — three nested object levels, each `additionalProperties: false`. Without this, a future contributor adding `freshness.metadata: <unstructured>` would slip past validation. The `IndexFreshness` sub-schema content is **generated from the Pydantic model** via `Fresh.model_json_schema()` / `Stale.model_json_schema()` — not hand-written, so a Pydantic-model change ripples to the JSON Schema automatically.

**Per-probe sub-schema rejection test.** Each schema is exercised by a unit test that constructs a synthetic envelope with **one extra field** at a specified JSON Pointer and asserts `SchemaValidationError` fires at exactly that pointer. This is the structural defense against "the schema exists but doesn't actually validate anything." Phase 1 ADR-0004 line — "the schema is paired with a rejection test." S4-07 lands seven such tests.

**Explicit additive imports** in `src/codegenie/probes/__init__.py`. Each Layer B probe story added one line; this story confirms all seven are present, in stable alphabetical order, with `# noqa: F401` to silence linter "unused import" (the import side-effect is the `@register_probe` decorator's registration). A unit test (`test_layer_b_probes_explicit_additive_imports`) reads the `__init__.py` source and asserts the seven import statements appear.

## References — where to look

- **Phase 1 ADRs:**
  - [`docs/phases/01-context-gather-layer-a-node/ADRs/0004-per-probe-subschema-additional-properties-false.md`](../../01-context-gather-layer-a-node/ADRs/0004-per-probe-subschema-additional-properties-false.md) — the convention.
  - [`docs/phases/01-context-gather-layer-a-node/ADRs/0007-warnings-id-pattern.md`](../../01-context-gather-layer-a-node/ADRs/0007-warnings-id-pattern.md) — `warnings[]` and `errors[]` `pattern` constraint.
  - [`docs/phases/01-context-gather-layer-a-node/ADRs/0010-slice-optional-at-envelope.md`](../../01-context-gather-layer-a-node/ADRs/0010-slice-optional-at-envelope.md) — slices are optional at envelope level.
- **Phase 2 architecture:**
  - [`../phase-arch-design.md §"Data model"`](../phase-arch-design.md) lines 660–691 — the `IndexFreshness` Pydantic shape that drives the `index_health` sub-schema.
  - [`../phase-arch-design.md §"Component design"`](../phase-arch-design.md) — every probe's slice shape (the contract this story validates).
- **Phase 1 precedent:**
  - `src/codegenie/schema/probes/node_build_system.schema.json` (from S2-02) — the canonical example to mirror in style.
  - `tests/unit/probes/test_node_build_system_subschema.py` — the rejection-test precedent.
- **Source design:**
  - [`docs/localv2.md §5.2`](../../../localv2.md) — slice field documentation for Layer B.

## Goal

Seven JSON Schema files exist at `src/codegenie/schema/probes/`, one per Layer B probe. Each schema sets `additionalProperties: false` at every object level, declares `warnings[]` and `errors[]` with the ADR-0007 `pattern` constraint, and is exercised by a rejection test that asserts an extra-field envelope fails validation at the precise JSON Pointer. `src/codegenie/probes/__init__.py` lists the seven Layer B probe imports as additive lines in stable order. The envelope validator round-trip-tests each Layer B probe's actual slice output against its sub-schema and accepts it.

## Acceptance criteria

- [x] **AC-1 — Seven sub-schema files exist with the canonical `$id` shape.** Under `src/codegenie/schema/probes/`:
  - `index_health.schema.json` — `$id: "https://codewizard-sherpa.dev/schemas/probes/index_health/v0.1.0.json"`
  - `scip_index.schema.json` — `$id: "https://codewizard-sherpa.dev/schemas/probes/scip_index/v0.1.0.json"`
  - `tree_sitter_import_graph.schema.json` — `$id: ".../tree_sitter_import_graph/v0.1.0.json"`
  - `dep_graph.schema.json` — `$id: ".../dep_graph/v0.1.0.json"`
  - `generated_code.schema.json` — `$id: ".../generated_code/v0.1.0.json"`
  - `node_reflection.schema.json` — `$id: ".../node_reflection/v0.1.0.json"`
  - `semantic_index_meta.schema.json` — `$id: ".../semantic_index_meta/v0.1.0.json"`
  Each is a valid JSON Schema 2020-12 document (`$schema: "https://json-schema.org/draft/2020-12/schema"`), self-contained (no cross-file `$ref` — the `IndexFreshness` sub-schema is **embedded** in `index_health.schema.json`'s `$defs` rather than `$ref`'d, to defer the cross-schema-ref convention to Phase 3+), and Phase-1-ADR-0004 compliant. The `$id` URL stem matches the canonical pattern set by the six Layer A sub-schemas (`grep '"\$id"' src/codegenie/schema/probes/*.schema.json` is the spec).

- [x] **AC-1b — Envelope `$ref` wiring for all seven Layer B sub-schemas.** `src/codegenie/schema/repo_context.schema.json`'s `properties.probes.properties` is **edited additively** to add the seven `$ref` entries:
  ```json
  "index_health":            {"$ref": "https://codewizard-sherpa.dev/schemas/probes/index_health/v0.1.0.json"},
  "scip_index":              {"$ref": "https://codewizard-sherpa.dev/schemas/probes/scip_index/v0.1.0.json"},
  "tree_sitter_import_graph":{"$ref": "https://codewizard-sherpa.dev/schemas/probes/tree_sitter_import_graph/v0.1.0.json"},
  "dep_graph":               {"$ref": "https://codewizard-sherpa.dev/schemas/probes/dep_graph/v0.1.0.json"},
  "generated_code":          {"$ref": "https://codewizard-sherpa.dev/schemas/probes/generated_code/v0.1.0.json"},
  "node_reflection":         {"$ref": "https://codewizard-sherpa.dev/schemas/probes/node_reflection/v0.1.0.json"},
  "semantic_index_meta":     {"$ref": "https://codewizard-sherpa.dev/schemas/probes/semantic_index_meta/v0.1.0.json"}
  ```
  **This wiring is what activates per-slice validation.** Without it, Phase 0 ADR-0013's `probes.*: additionalProperties: true` swallows any rogue field silently — the sub-schemas on disk become inert. A test (`test_envelope_refs_every_layer_b_subschema`) asserts each of the seven slice names maps to a `$ref` whose target equals the corresponding sub-schema's `$id`.

- [x] **AC-2 — `additionalProperties: false` at root AND every nested object (including `$defs`, `oneOf`/`anyOf`/`allOf` branches, `items`, `prefixItems`).** Each sub-schema sets `additionalProperties: false`:
  - At the document root (the slice object).
  - At every nested `type: "object"` block (e.g., `index_health.<index_name>.freshness`, `index_health.<index_name>.freshness.reason`, `generated_code.files[*]`, `node_reflection.decorator_usage`, `semantic_index_meta` is single-level so root is sufficient).
  - At every object node reachable through `$defs.*`, `oneOf[*]`, `anyOf[*]`, `allOf[*]`, `if`/`then`/`else`, `items`, `prefixItems[*]`, and `additionalProperties` (when itself a schema). The `index_health` schema is the load-bearing case — its embedded `IndexFreshness` lives under `$defs.Fresh` / `$defs.Stale` / `$defs.CommitsBehind` / … each of which is a nested object node.

  A unit test (`test_additional_properties_false_at_every_object_level`) parametrized over the seven schemas uses a recursive `_walk_object_nodes(schema)` helper (extracted to `tests/unit/probes/layer_b/_schema_walkers.py`) that visits every node above by recursive descent; for each visited `{"type": "object", ...}` (or `{"properties": ..., ...}` without an explicit `type`, treated as object), asserts `additionalProperties: false` is set explicitly. The walker's traversal rules are documented inline; **the helper is intentionally test-only** (not promoted to production) so the schema-validation kernel stays minimal.

  **Mutation-resistance check (T-02b):** an additional test takes the committed `index_health.schema.json`, deep-copies it, deletes `additionalProperties: false` at a randomly chosen nested object path (e.g., `$defs.Stale`), and asserts `_walk_object_nodes` flags that exact path. This proves the walker isn't passing by accident on schemas that already conform.

- [x] **AC-3 — `warnings[]` and `errors[]` are ADR-0007-pattern-constrained as flat strings.** Each sub-schema declares:
  ```json
  "warnings": {"type": "array", "items": {"type": "string", "pattern": "^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$"}},
  "errors":   {"type": "array", "items": {"type": "string", "pattern": "^[a-z][a-z0-9_]*\\.[a-z][a-z0-9_]*$"}}
  ```
  The **flat-string** shape (NOT `{id, message}` objects) is the production convention — verified against `src/codegenie/schema/probes/language_detection.schema.json`, `node_build_system.schema.json`, etc. Implementer note: the convention doc at `_subschema_convention.md` shows an `{id, message}` example fragment that diverges from production code; **follow the production code** (Rule 7 — surface the divergence; updating the convention doc to match is a tracked cleanup item, not in scope here).

  **Cross-check (T-04):** for each of the seven Layer B probe modules, load `_WARNING_IDS: Final[frozenset[str]]` (and `_ERROR_IDS` if present) at import time; assert every member matches the regex pinned in its sub-schema. The convention is established: `src/codegenie/probes/layer_b/dep_graph.py:82`, `index_health.py:109`, `scip_index.py:90`, `src/codegenie/probes/ci.py:160`, `deployment.py:132/147`, `node_build_system.py:226/240`. **Precondition for AC-3:** the four probes whose `_WARNING_IDS` shipping is in-flight (S4-04 tree_sitter_import_graph, S4-06 generated_code, S4-06 node_reflection, S4-06 semantic_index_meta) must expose this frozenset at module level. If any probe lands without `_WARNING_IDS`, T-04 is allowed to skip *that* probe with `pytest.skip` AND a `warnings.warn(stacklevel=2)` so the gap is logged loudly (Rule 12 — fail loud, never silent).

- [x] **AC-4 — Slice optional at envelope level (positive + negative check).** Each Layer B sub-schema is wired by `$ref` under `properties.probes.properties.<name>` (AC-1b) but is NOT declared `required` at envelope level (Phase 1 ADR-0010). Two assertions, both load-bearing:
  - **Positive:** `envelope.properties.probes.properties` contains each of the seven Layer B probe names (proves wiring exists).
  - **Negative:** either `envelope.properties.probes.required` does NOT exist (current state — Phase 0 ADR-0013 keeps `probes.*: additionalProperties: true` and no `required` list) OR, if a `required` array IS present, none of the seven Layer B probe names appear in it.

  The negative check is structured this way because asserting "names not in `required`" when `required` doesn't exist is **vacuously true**; the original AC was vulnerable to a future contributor adding a `required: ["index_health"]` after the test was written and the test still passing. The positive check (presence under `properties`) plus the conditional negative (absence from `required` when it exists) together close the gap. A unit test (`test_layer_b_slices_wired_and_optional_at_envelope`) parses `repo_context.schema.json` and asserts both.

- [x] **AC-5 — `index_health` sub-schema embeds the `IndexFreshness` JSON Schema, regenerated from Pydantic.** The `index_health.schema.json` contains a `$defs` block with `Fresh`, `Stale`, `CommitsBehind`, `DigestMismatch`, `CoverageGap`, `IndexerError` definitions — **generated** at sub-schema build time from the Pydantic models (`Fresh.model_json_schema()`, etc.) via `tools/regenerate_probe_schemas.py` (note the **drop of `_layer_b`** in the name — see Notes for the implementer D-3: a Phase 3 Layer C probe extends this script by tuple-registry insertion, not by edit-and-rename).

  The script is reviewed-as-code; running it on a clean tree must produce byte-identical sub-schemas to those committed. A unit test (`test_index_health_subschema_regenerates_identically`) shells out to the script (`python -m tools.regenerate_probe_schemas`) in a tempdir copy of the repo and diffs against the committed `index_health.schema.json` — must be byte-identical (`assert produced == committed`).

  **Declared-input discipline:** the script's top-of-file docstring declares its inputs in a machine-readable `# DECLARED-INPUTS:` block:
  ```python
  # DECLARED-INPUTS:
  #   src/codegenie/indices/freshness.py
  #   src/codegenie/depgraph/model.py
  ```
  T-06 asserts this block exists and lists at minimum these two paths. This mirrors the probe `declared_inputs` discipline (Phase 0 cache key) and is the structural defense against "I changed the Pydantic model, forgot to rerun the script."

- [x] **AC-5b — Embedded sum-type discriminator integrity.** The generated `index_health.schema.json`'s `$defs` block includes exactly six entries — `Fresh`, `Stale`, `CommitsBehind`, `DigestMismatch`, `CoverageGap`, `IndexerError` — each carrying:
  - `$defs.Fresh.properties.kind` with `const: "fresh"`,
  - `$defs.Stale.properties.kind` with `const: "stale"`,
  - `$defs.CommitsBehind.properties.kind` with `const: "commits_behind"`,
  - `$defs.DigestMismatch.properties.kind` with `const: "digest_mismatch"`,
  - `$defs.CoverageGap.properties.kind` with `const: "coverage_gap"`,
  - `$defs.IndexerError.properties.kind` with `const: "indexer_error"`,

  matching the Pydantic `Literal["..."]` discriminators at `src/codegenie/indices/freshness.py` (`commits_behind` @45, `digest_mismatch` @56, `coverage_gap` @68, `indexer_error` @79, `fresh` @96, and `Stale.kind` in the rest of the file). A unit test (`test_index_freshness_discriminators_preserved_in_schema`) loads the generated schema and asserts each `const` value equals the Pydantic model class's `kind` field default. **Catches "Pydantic Literal renamed without schema regeneration."**

- [x] **AC-6 — Per-probe sub-schema rejection test (with validator-fingerprint + round-trip control).** Each of the seven schemas has a parametrized test entry in `tests/unit/probes/layer_b/test_subschemas.py`:
  ```python
  @pytest.mark.parametrize("probe_name, extra_field_pointer", [
      ("index_health",             "/probes/index_health/rogue_field"),
      ("scip_index",               "/probes/scip_index/rogue_field"),
      ("tree_sitter_import_graph", "/probes/tree_sitter_import_graph/rogue_field"),
      ("dep_graph",                "/probes/dep_graph/rogue_field"),
      ("generated_code",           "/probes/generated_code/files/0/rogue_field"),       # nested via files[*]
      ("node_reflection",          "/probes/node_reflection/decorator_usage/rogue_field"),  # nested
      ("semantic_index_meta",      "/probes/semantic_index_meta/rogue_field"),
  ])
  def test_subschema_rejects_extra_field(probe_name, extra_field_pointer): ...
  ```

  The test must assert **three** things, not one — this is what makes it mutation-resistant:
  1. **Rejection fires:** `schema.validate(envelope_with_extra_field)` raises `SchemaValidationError` (the wrapper from `codegenie.errors`) whose underlying `jsonschema.ValidationError.absolute_path` formats to the exact JSON Pointer above.
  2. **The triggering validator is `additionalProperties`:** `original_error.validator == "additionalProperties"`. Catches the failure mode where rejection fires for an unrelated reason (e.g., a required field elsewhere is missing) and the test passes by coincidence.
  3. **Round-trip control:** the same envelope with the extra field removed validates clean (`schema.validate(envelope_without_extra_field)` does NOT raise). Proves the test fixture is a minimal-valid envelope, not a malformed one that would fail validation regardless.

  Each row exercises **one** extra-field rejection; nested cases (`generated_code`, `node_reflection`) prove `additionalProperties: false` propagates beyond the root. AC-2's recursive test is the **structural** check (the flag is set at every depth); AC-6 is the **behavioral** check (the validator actually fires AND fires for the right reason); AC-1b's wiring is the **integration** check (the envelope's `$ref` routes the slice to the sub-schema). All three are needed — drop any one and a class of regression slips through silently.

- [x] **AC-7 — Round-trip validation of typed Pydantic model output (not full probe runs).** A unit test (`test_layer_b_typed_model_round_trips_against_subschema`) parametrized over the seven slices:
  1. Constructs a hand-built, minimal-valid instance of the slice's Pydantic model (e.g., `DepGraphProbeOutput(graph_path=None, confidence="low", reason="no_strategy_for_ecosystem")` for `dep_graph`).
  2. Serializes via `model.model_dump(mode="json")` wrapped in the canonical envelope: `{"schema_version": "0.1.0", "generated_at": "2026-05-16T00:00:00Z", "repo": {"root": "/tmp/x", "git_commit": None}, "probes": {"<slice_name>": <slice>}}`.
  3. Validates the full envelope through `codegenie.schema.validator.validate` (the **production chokepoint** — exercises the `$ref` resolution from AC-1b AND the sub-schema's interior, in one assertion).
  4. Asserts validation succeeds.

  **Why typed-model serialization, not full probe runs:** invoking each probe against a synthetic `ProbeContext` with synthetic fixtures couples this test to probe runtime quirks (git state, SCIP binaries, tree-sitter grammars, network access). The honest contract this AC enforces is "the schema accepts what the model emits"; the model is the contract surface. Full probe-run round-trip tests live per-probe (S4-01, S4-03, S4-04, S4-05, S4-06) and are out of scope here. **A slice without a Pydantic model** (e.g., `scip_index` ships as a `TypedDict`, not a Pydantic model — verify per probe) **skips its row with `pytest.skip(...)` AND a `warnings.warn(...)` (stacklevel=2)** so the gap is logged loudly, never silently passed (Rule 12).

- [x] **AC-7b — Structural bidirectional check (model ↔ schema).** A unit test (`test_typed_model_matches_subschema_structure`) for each Pydantic-modelled slice asserts both directions of the contract:
  - **Model fields ⊆ schema declared properties:** every field name on the Pydantic model (`Model.model_fields.keys()`) appears in `schema["properties"]` (recursively resolved through `$ref` for the `index_health` case). Catches "the model added a field the schema doesn't declare → `additionalProperties: false` would reject it the moment a probe emits a non-default value."
  - **Schema `required[]` ⊆ model required fields:** every name in `schema["required"]` is a field on the Pydantic model that is non-`Optional[T]` without a default. Catches "schema requires X, model marks X optional → schema-allows-LESS-than-model."

  Both directions are needed: dropping either side admits a silent contract drift. **Skip-with-warn** for slices without a Pydantic model, same as AC-7.

- [x] **AC-8 — `src/codegenie/probes/__init__.py` lists seven Layer B additive imports in stable alphabetical order, matching the grouped-import codebase convention.** The current file (verified at `src/codegenie/probes/__init__.py:26-30`) uses the **grouped** form:
  ```python
  from codegenie.probes.layer_b import (
      dep_graph,               # noqa: F401 — S4-05 registration
      generated_code,          # noqa: F401 — S4-06 registration
      index_health,            # noqa: F401 — S4-01 registration
      node_reflection,         # noqa: F401 — S4-06 registration
      scip_index,              # noqa: F401 — S4-03 registration
      semantic_index_meta,     # noqa: F401 — S4-06 registration
      tree_sitter_import_graph,# noqa: F401 — S4-04 registration
  )
  ```
  This story consolidates: confirms all seven names appear inside a single `from codegenie.probes.layer_b import (...)` statement in **alphabetical order** (the seven names sorted: `dep_graph`, `generated_code`, `index_health`, `node_reflection`, `scip_index`, `semantic_index_meta`, `tree_sitter_import_graph`), each with the `# noqa: F401 — S4-XX registration` trailer. A unit test (`test_layer_b_probes_grouped_additive_imports`) parses `__init__.py` with `ast.parse`, finds the `ImportFrom` node whose `module == "codegenie.probes.layer_b"`, and asserts:
  - `len(node.names) == 7`,
  - `[alias.name for alias in node.names] == sorted(["dep_graph", "generated_code", "index_health", "node_reflection", "scip_index", "semantic_index_meta", "tree_sitter_import_graph"])`.

  Rule 11 — match codebase convention; the per-line form (one `from … import x` per line) is NOT used here because Phase 0/1 chose grouped. Stable alphabetical order means a future PR adding an eighth Layer B probe inserts ONE name at its alphabetical position — diff is minimal, `git blame` is informative.

- [x] **AC-9 — All seven probes registered in `default_registry`.** A unit test (`test_layer_b_probes_in_default_registry`) imports `default_registry` (forcing module-level decorator runs), enumerates `default_registry.all_probes()`, and asserts the seven probe names are present. **This is a cross-cutting consolidation test** — each probe's individual story has its own membership test; this one asserts collective presence.

- [x] **AC-10 — Sub-schemas pass JSON Schema meta-schema validation.** A unit test (`test_subschemas_are_valid_json_schema_documents`) loads each of the seven sub-schemas, validates against the JSON Schema 2020-12 meta-schema (`jsonschema.Draft202012Validator.check_schema(...)`), and asserts no exception. **Catches the "malformed schema typo" failure mode.**

- [x] **AC-10b — `$id` uniqueness, canonical pattern, and slice-name agreement.** A unit test (`test_subschema_ids_are_unique_and_canonical`) asserts three properties of the seven sub-schemas' `$id` values:
  1. **Pairwise distinct.** Two sub-schemas sharing an `$id` would silently overwrite each other in the `referencing` Registry (`src/codegenie/schema/validator.py:54-58`) — a `set()` of the seven `$id`s must have length 7.
  2. **Canonical pattern.** Each `$id` matches the regex `^https://codewizard-sherpa\.dev/schemas/probes/[a-z][a-z0-9_]*/v\d+\.\d+\.\d+\.json$` — same shape as the six Layer A sub-schemas.
  3. **Slice-name agreement.** For each sub-schema, the trailing `<probe_name>` segment of its `$id` equals the slice key the envelope's `$ref` points to (AC-1b). Catches "the file is named `index_health.schema.json` but its `$id` says `.../scip_index/v0.1.0.json` and the envelope wires it to `index_health`" — a class of copy-paste bug that produces silent validation no-ops.

- [x] **AC-11 — Tooling green.** `ruff check`, `ruff format --check`, `mypy --strict tools/regenerate_probe_schemas.py`, `pytest tests/unit/probes/layer_b/test_subschemas.py`, `pytest tests/unit/probes/test_init.py` (if the init-shape tests live there) — all pass. Pre-commit hook `jsonlint` (if Phase 0 has one — verify) reports no issues on the seven JSON files.

## Implementation outline

1. **Land `tools/regenerate_probe_schemas.py`** — a Python script (≤ 120 LOC) structured as a **tuple-registry of builders** (Open/Closed at the script body — Phase 3 Layer C probes extend by tuple insertion, never by edit-and-rename):
   ```python
   # DECLARED-INPUTS:
   #   src/codegenie/indices/freshness.py
   #   src/codegenie/depgraph/model.py
   from typing import Callable
   _SchemaDict = dict[str, object]
   _BUILDERS: list[tuple[str, Callable[[], _SchemaDict]]] = [
       ("index_health",             _build_index_health),
       ("scip_index",               _build_scip_index),
       ("tree_sitter_import_graph", _build_tree_sitter_import_graph),
       ("dep_graph",                _build_dep_graph),
       ("generated_code",           _build_generated_code),
       ("node_reflection",          _build_node_reflection),
       ("semantic_index_meta",      _build_semantic_index_meta),
   ]
   ```
   Each `_build_<name>()` returns a `_SchemaDict` shaped per the per-probe AC; the per-builder logic:
   - `index_health.schema.json` — composes a top-level schema with `additionalProperties: false` at root, declares each known index source as an optional property whose value is `{$ref: "#/$defs/IndexFreshness"}`. The `$defs` block is **generated** from the Pydantic models via `Fresh.model_json_schema()` / `Stale.model_json_schema()` / each `StaleReason` variant's `.model_json_schema()`. The discriminator structure (AC-5b) is preserved by Pydantic's native schema export.
   - `scip_index.schema.json` — hand-coded per `localv2.md §5.2 B1` slice shape.
   - `tree_sitter_import_graph.schema.json` — hand-coded per S4-04 AC-7.
   - `dep_graph.schema.json` — generated from `DepGraphProbeOutput.model_json_schema()`.
   - `generated_code.schema.json` — hand-coded per `localv2.md §5.2 B4`.
   - `node_reflection.schema.json` — hand-coded per `localv2.md §5.2 B3`.
   - `semantic_index_meta.schema.json` — hand-coded per S4-06 AC-M3.

   Post-process steps applied uniformly via small pure helpers (functional core):
   - `_set_additional_props_false_recursively(schema)` — walks the JSON Schema and sets `additionalProperties: false` on every `{"type": "object"}` or `{"properties": ...}` node missing it. The walker's traversal rules cover `$defs`, `oneOf`/`anyOf`/`allOf`, `if`/`then`/`else`, `items`, `prefixItems`, and `additionalProperties` (when itself a schema), so future contributors don't have to remember every branch shape.
   - `_constrain_warnings_and_errors(schema)` — adds the ADR-0007 regex constraint on `properties.warnings.items` and `properties.errors.items`.
   - `_set_id_and_schema(schema, probe_name)` — writes `$schema` (Draft 2020-12) and `$id` (`https://codewizard-sherpa.dev/schemas/probes/<probe_name>/v0.1.0.json`).
   - **`write_schema_file(path, schema)` — the single smart-constructor chokepoint** for serialization (`json.dumps(schema, indent=2, sort_keys=True) + "\n"`). All seven sub-schemas pass through this one function — byte-identical reruns are enforced by serialization at one site, not seven copies.

   The `main()` is an **imperative shell** that maps over `_BUILDERS` and calls `write_schema_file`. Each builder is a pure function. `mypy --strict` is enforced; no `Any`, no untyped dict-shuffling — `_SchemaDict` is the kernel type.

2. **Edit `src/codegenie/schema/repo_context.schema.json` additively** — add the seven `$ref` entries under `properties.probes.properties` (AC-1b). The envelope's `additionalProperties: true` at `probes.*` is preserved (Phase 0 ADR-0013); no `required[]` is added (ADR-0010).

3. **Run the script once and commit** the seven sub-schemas + the updated envelope.

4. **Compose `tests/unit/probes/layer_b/test_subschemas.py`** with:
   - `test_subschemas_exist_and_are_valid_json` (AC-1, AC-10).
   - `test_subschema_ids_are_unique_and_canonical` (AC-10b).
   - `test_envelope_refs_every_layer_b_subschema` (AC-1b).
   - `test_additional_properties_false_at_every_object_level` (AC-2) + `test_walker_catches_removed_additional_properties_false` (AC-2 mutation-resistance, T-02b).
   - `test_warnings_and_errors_pattern_constraints` (AC-3 schema side).
   - `test_each_probe_emitted_ids_match_pattern_constraint` (AC-3 probe-module side, T-04).
   - `test_layer_b_slices_wired_and_optional_at_envelope` (AC-4).
   - `test_index_health_subschema_regenerates_identically` (AC-5).
   - `test_index_freshness_discriminators_preserved_in_schema` (AC-5b).
   - `test_subschema_rejects_extra_field` (AC-6) — parametrized over seven probes, three assertions per row (rejection + validator-fingerprint + round-trip control).
   - `test_layer_b_typed_model_round_trips_against_subschema` (AC-7) — parametrized over seven probes, skip-with-warn for non-Pydantic slices.
   - `test_typed_model_matches_subschema_structure` (AC-7b) — same parametrization.

5. **Compose `tests/unit/probes/test_init.py`** (or extend existing) with:
   - `test_layer_b_probes_grouped_additive_imports` (AC-8).
   - `test_layer_b_probes_in_default_registry` (AC-9).

6. **Confirm `src/codegenie/probes/__init__.py`** has the seven Layer B names in the grouped `from … import (…)` block in alphabetical order. The current file (verified) carries three of seven (`dep_graph`, `index_health`, `scip_index`); the remaining four land as S4-04/S4-06 implementation completes. This story's `__init__.py` edit is **additive consolidation** — never delete an existing import.

## TDD plan — red / green / refactor

### RED

- **T-01** `test_subschemas_exist_and_are_valid_json` (AC-1, AC-10): for each of seven, file exists; loads as JSON; passes `Draft202012Validator.check_schema`.
- **T-01b** `test_subschema_ids_are_unique_and_canonical` (AC-10b): collect each schema's `$id`; assert pairwise distinct, regex-match `^https://codewizard-sherpa\.dev/schemas/probes/[a-z][a-z0-9_]*/v\d+\.\d+\.\d+\.json$`, trailing slug equals slice key wired in envelope.
- **T-01c** `test_envelope_refs_every_layer_b_subschema` (AC-1b): load `repo_context.schema.json`; for each of the seven Layer B slice keys, assert `properties.probes.properties[<key>]` exists and its `$ref` equals the corresponding sub-schema's `$id`.
- **T-02** `test_additional_properties_false_at_every_object_level` (AC-2): for each schema, run `_walk_object_nodes(schema)` from `tests/unit/probes/layer_b/_schema_walkers.py`; collect any object node that lacks `additionalProperties: false`; assert the list is empty. Walker MUST traverse `$defs`, `oneOf`/`anyOf`/`allOf`, `if`/`then`/`else`, `items`, `prefixItems`, `additionalProperties` (when itself a schema), `properties.*`, `patternProperties.*`.
- **T-02b** `test_walker_catches_removed_additional_properties_false` (AC-2 mutation-resistance): deep-copy `index_health.schema.json`; delete `additionalProperties: false` at path `$defs.Stale` (or another nested object); assert the walker flags exactly that path. Proves T-02 isn't passing by accident on already-conformant schemas.
- **T-03** `test_warnings_and_errors_pattern_constraints` (AC-3): each schema's `properties.warnings.items.pattern` equals `^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`; same for `properties.errors.items.pattern` (string items, not objects).
- **T-04** `test_each_probe_emitted_ids_match_pattern_constraint` (AC-3 probe-module side): for each probe module, load `_WARNING_IDS` and (if present) `_ERROR_IDS`; assert every member matches the regex pinned in its sub-schema. Skip-with-warn for probe modules that haven't yet shipped `_WARNING_IDS`.
- **T-05** `test_layer_b_slices_wired_and_optional_at_envelope` (AC-4): positive — each of the seven slice keys is in `properties.probes.properties`. Negative — `properties.probes.required` either doesn't exist OR doesn't include any of the seven names.
- **T-06** `test_index_health_subschema_regenerates_identically` (AC-5): in a tempdir, run `python -m tools.regenerate_probe_schemas`; diff `src/codegenie/schema/probes/index_health.schema.json` against the committed version; assert byte-identical. Also assert the script's top contains a `# DECLARED-INPUTS:` block listing at minimum `src/codegenie/indices/freshness.py` and `src/codegenie/depgraph/model.py`.
- **T-06b** `test_index_freshness_discriminators_preserved_in_schema` (AC-5b): load `index_health.schema.json`; for each variant class (`Fresh`, `Stale`, `CommitsBehind`, `DigestMismatch`, `CoverageGap`, `IndexerError`), assert `$defs.<ClassName>.properties.kind.const` equals the Pydantic model class's `kind` field default (read via `Model.model_fields["kind"].default`).
- **T-07** `test_subschema_rejects_extra_field` (AC-6): parametrized; build a minimal-valid envelope for each probe; add an extra field at the specified JSON Pointer; call `codegenie.schema.validator.validate(envelope)`; assert (a) `SchemaValidationError` raised, (b) underlying `jsonschema.ValidationError.absolute_path` formats to the expected pointer, (c) underlying `error.validator == "additionalProperties"`, (d) the same envelope WITHOUT the extra field validates clean (round-trip control).
- **T-08** `test_layer_b_typed_model_round_trips_against_subschema` (AC-7): parametrized; for each Pydantic-modelled slice, construct a minimal-valid model instance; serialize via `model.model_dump(mode="json")`; wrap in canonical envelope; call `codegenie.schema.validator.validate(envelope)`; assert no exception. Skip-with-warn for non-Pydantic slices.
- **T-08b** `test_typed_model_matches_subschema_structure` (AC-7b): parametrized; model fields ⊆ schema properties AND schema `required[]` ⊆ model required fields.
- **T-09** `test_layer_b_probes_grouped_additive_imports` (AC-8): use `ast.parse` on `src/codegenie/probes/__init__.py`; find the `ImportFrom` node with `module == "codegenie.probes.layer_b"`; assert it has exactly 7 names in alphabetical order.
- **T-10** `test_layer_b_probes_in_default_registry` (AC-9): `default_registry.all_probes()` (or `default_registry.iter_probes()` per actual registry API — verify) contains all seven `Probe` subclasses by name.

### GREEN

- Land the empty `tools/regenerate_probe_schemas.py` with `_BUILDERS` skeleton and a stubbed `main()`.
- Implement each `_build_<name>()` per outline; iterate on sub-schema content until T-06b (discriminator integrity) and T-07/T-08 (model↔schema round-trip) pass.
- Edit `src/codegenie/schema/repo_context.schema.json` additively to add the seven `$ref` entries.
- Run the script; commit the seven sub-schemas + the envelope edit.
- Write the test file(s); iterate. T-06's byte-identical check is the load-bearing gate: a passing T-06 means the script is reproducible.
- Add the four missing Layer B imports to `__init__.py` as their predecessor stories land (S4-04, S4-06); confirm T-09 passes.

### REFACTOR

- Confirm `tools/regenerate_probe_schemas.py` is idempotent (second run produces byte-identical files; CI gate via T-06).
- Confirm `mypy --strict` on the script (no `Any`, no untyped dict-shuffling — `_SchemaDict = dict[str, object]` is the kernel type; consider `TypedDict` for the JSON Schema shape if the script grows past 150 LOC).
- If the schemas grow unwieldy in size, consider extracting common sub-objects (e.g., `Confidence`) to a shared `$defs` block within a single sub-schema only — DO NOT introduce cross-schema `$ref` in Phase 2 (Rule 7 — surface the pattern decision; cross-schema refs are a Phase 3+ scope choice).
- DO NOT promote `_walk_object_nodes` to production. It is a test-only helper; the production schema-validation kernel stays minimal (the validator lives at `src/codegenie/schema/validator.py` and uses `jsonschema` + `referencing` — that's the whole kernel).

## Files to touch

**Create:**
- `tools/regenerate_probe_schemas.py` (note: NOT `regenerate_layer_b_schemas.py` — see D-3, name is forward-compatible with Phase 3 Layer C extensions)
- `src/codegenie/schema/probes/index_health.schema.json`
- `src/codegenie/schema/probes/scip_index.schema.json`
- `src/codegenie/schema/probes/tree_sitter_import_graph.schema.json`
- `src/codegenie/schema/probes/dep_graph.schema.json`
- `src/codegenie/schema/probes/generated_code.schema.json`
- `src/codegenie/schema/probes/node_reflection.schema.json`
- `src/codegenie/schema/probes/semantic_index_meta.schema.json`
- `tests/unit/probes/layer_b/test_subschemas.py`
- `tests/unit/probes/layer_b/_schema_walkers.py` (test-only utility helpers; not promoted to production)

**Edit (additive — consolidation):**
- `src/codegenie/schema/repo_context.schema.json` — add seven `$ref` entries under `properties.probes.properties` (AC-1b). **No other change to the envelope shape** (Phase 0 ADR-0013 layering is preserved).
- `src/codegenie/probes/__init__.py` — confirm seven Layer B names appear inside the grouped `from codegenie.probes.layer_b import (...)` block in alphabetical order; add the four currently-missing names (`generated_code`, `node_reflection`, `semantic_index_meta`, `tree_sitter_import_graph`) once their predecessor stories land. Order is alphabetical by module name.
- `tests/unit/probes/test_init.py` (or new file) — add `test_layer_b_probes_grouped_additive_imports`, `test_layer_b_probes_in_default_registry`.

## Out of scope

- **Cross-schema `$ref`.** Phase 2 keeps schemas self-contained (`IndexFreshness` is embedded via `$defs` within `index_health.schema.json`, not `$ref`'d from a separate file). Cross-schema refs introduce a "schema discovery" concern Phase 3+ owns.
- **Schema versioning.** Phase 2 ships `schema_version: 1` implicitly via the sub-schema `$id` (e.g., `https://codewizard.local/schema/probes/index_health.v1.json`); a Phase 3 schema change bumps `v2` and the envelope validator picks based on emitted `schema_version` in the slice. The convention is documented but the version-2 path is unbuilt here.
- **OpenAPI / Swagger emission.** The JSON Schemas are the canonical contract; an OpenAPI rendering is Phase 8+.
- **Sub-schemas for Layer C/D/E/G probes.** Steps 5 and 6 land those probes; their sub-schemas land alongside (S5-07-ish, S6-09-ish — TBD by those stories' authors).
- **Generated `IndexFreshness` shape for Phase 3.** AC-5 generates the **current Phase 2 variant set** — `CommitsBehind | DigestMismatch | CoverageGap | IndexerError`. A Phase 3 ADR amending to a fifth variant requires a re-run of `regenerate_layer_b_schemas.py` and a sub-schema bump. Documented in `tools/regenerate_layer_b_schemas.py`'s docstring.
- **Hand-editing sub-schemas after generation.** Generated portions (the `IndexFreshness` `$defs`, the `DepGraphProbeOutput` shape) are reviewed by re-running the script. Hand edits are admissible **only** for the parts of sub-schemas that are hand-coded (e.g., `scip_index.schema.json`'s `coverage_pct` field is hand-declared because there's no Pydantic source). Document this split inline in the script's docstring.

## Notes for the implementer

- **Why this story is `S` not `M`.** The per-probe sub-schemas are largely hand-coded JSON guided by the probe stories' AC fields; the discipline is structural (recursive walker, ADR-0007 regex, rejection tests, envelope wiring). The novel work is `tools/regenerate_probe_schemas.py` and AC-5's regeneration discipline — both are small. Effort `S` reflects "no architectural decisions, just careful schema authoring + one tuple-registry script."
- **The draft pin is Draft 2020-12.** Verified at `src/codegenie/schema/validator.py:48` — the validator is `jsonschema.Draft202012Validator`, and the existing six Layer A sub-schemas all set `$schema: "https://json-schema.org/draft/2020-12/schema"`. Phase 2 Layer B sub-schemas conform.
- **`additionalProperties: false` is the structural defense (Phase 1 ADR-0004).** A future contributor who hand-edits a sub-schema to add `additionalProperties: true` ANYWHERE (root or nested, including inside `$defs`/`oneOf`/`anyOf`/`allOf`) breaks AC-2. The recursive walker (`_walk_object_nodes`) is the structural test. Resist the urge to "relax the walker for nested `allOf` cases" — those cases are real schema choices and need to be addressed in the schema authoring (lift the `additionalProperties: false` to every branch), not in the test.
- **The smart-constructor at the serialization boundary.** All seven schemas pass through `write_schema_file(path, schema)` in the regenerator script. Byte-identical output is enforced by **one** function, not seven copies of `json.dumps(...)`. Adding an eighth Layer C probe in Phase 3 reuses the same chokepoint — no risk of accidentally drifting whitespace, sort order, trailing newline.
- **`tools/regenerate_probe_schemas.py` is a tuple-registry, not a registry decorator (yet).** Rule 2 — three similar lines is better than premature abstraction. The seven Layer B builders are the FIRST consumers; Phase 3 Layer C is the second. At the third (Layer D? Layer G?), the `@register_probe_schema_builder("name")` decorator earns its keep — the tuple list crosses the rule-of-three threshold. **Until then**, the tuple-list `_BUILDERS` is the additive surface — a new Phase 3 builder is a one-tuple insertion, the kernel doesn't change.
- **D-2 follow-up (flag for Phase 3 backlog) — auto-wire envelope `$ref` from sub-schema filename.** The validator at `validator.py:51-52` already auto-discovers all `*.schema.json` files via `glob`, but the envelope's `properties.probes.<name>: {$ref: …}` is a hand edit per probe (this story adds seven). A small post-load step in `validator.py` could derive probe name from filename stem, read `$id` from the discovered schema, and inject `properties.probes.<stem>: {$ref: <$id>}` programmatically — eliminating the envelope edit forever. This touches Phase 0 surface (envelope schema shape + validator) so it's an ADR amendment, not Phase 2 scope. **Backlog item:** open a Phase 3 ADR proposing this auto-wiring; the seven entries this story adds are the rule-of-three threshold being re-crossed. **Until then**, every new sub-schema requires the envelope edit, and AC-1b's test (`test_envelope_refs_every_layer_b_subschema`) is the structural defense against forgetting it.
- **D-3 follow-up — `@register_probe_schema_builder` decorator.** As above, the tuple-registry pays off until the third Layer's consumers ship; then promote to a decorator-registry mirroring `@register_probe` / `@register_dep_graph_strategy`. The naming convention is set; the upgrade is mechanical.
- **The rejection-test parametrization (AC-6) is the load-bearing behavioral check.** AC-2 catches "the schema has `additionalProperties: false` at every nested level." AC-6 catches "the validator actually fires when an extra field is added AND fires for the right reason AND the test fixture is genuinely valid in the control case." AC-1b catches "the envelope's `$ref` actually routes the slice." All three can fail independently. Dropping any one admits a class of regression.
- **Don't $ref across files in Phase 2.** Tempting to factor `Confidence` (`Literal["high", "medium", "low"]`) into a shared schema — DON'T. Cross-schema discovery is a Phase 3+ concern. Embed `Literal` shapes in each sub-schema; duplication is the simplicity tradeoff Phase 2 explicitly takes ([phase-arch-design.md §"Design patterns applied"](../phase-arch-design.md) — Rule 2 over Rule 11 when the cost of one-step indirection is high).
- **The seven probes' membership test (AC-9) is structural.** It catches the "I forgot to register `dep_graph` in `__init__.py`" mistake — each individual story's per-probe registry test would still pass (it imports the module directly), but the consolidated test fails because `default_registry` doesn't see it without the package-level import side-effect. Rule 12 — fail loud.
- **The `_subschema_convention.md` divergence (H-2).** The doc shows `warnings: [{id, message}]` (object items); all six existing production sub-schemas use `warnings: [string]` (flat-string items with pattern). The production convention wins here — this story matches production. Updating the convention doc to match is a tracked-cleanup item; **flag for a follow-up doc PR** (do not touch in this story — Rule 3, surgical changes).
- **Rule 9 — tests verify intent, not just behavior.** AC-2 (recursive walker + mutation test) encodes the WHY of `additionalProperties: false` — preventing silent slice drift, even after a contributor adds a new `oneOf` branch. AC-5 (regeneration is idempotent) encodes the WHY of the generation script — hand-editing the generated section is the failure mode. AC-5b (discriminator integrity) encodes the WHY of the sum-type embedding — the tagged-union shape must survive serialization to JSON Schema. AC-7+AC-7b (typed-model round-trip, bidirectional) encode the WHY of model↔schema agreement — they must agree, in both directions, or `RepoContext` becomes a lie. Each test asserts a load-bearing discipline, not just behavior.
- **Sequencing reminder.** AC-7's round-trip test depends on S4-04 (`tree_sitter_import_graph`) and S4-06 (three marker probes) shipping their Pydantic models. If those stories aren't done yet, AC-7's rows for those probes skip-with-warn. The `warnings.warn` is the structural defense against silently passing the test — when those predecessor stories complete, the skip-with-warn becomes a real assertion automatically (no test code change needed). This is the **chain of responsibility** for the test fixture: each predecessor probe is responsible for its slice's typed model; this story is responsible only for the schema and the wiring.
