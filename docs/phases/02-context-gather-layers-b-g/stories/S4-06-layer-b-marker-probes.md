# Story S4-06 — `GeneratedCode` + `NodeReflection` + `SemanticIndexMeta` marker probes

**Step:** Step 4 — Ship `IndexHealthProbe` (B2) + Layer B structural probes
**Status:** Ready
**Effort:** M
**Depends on:** S4-03 (`tools/grammars.lock` + vendored grammars on disk — `NodeReflectionProbe` uses `tree-sitter` queries against the JS/TS AST; consumes the same in-process grammar-load path S4-04 established)
**ADRs honored:** [`02-ADR-0002`](../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md) (NodeReflection's tree-sitter use is governed by the same grammar pin; same `_load_grammar` from S4-04 is reused — NOT redeclared), [`02-ADR-0003`](../ADRs/0003-coordinator-heaviness-sort-annotation.md) (all three are `heaviness="light"` — marker detection is fast), Phase 1 ADR-0004 (sub-schema per probe, lands in S4-07), Phase 1 ADR-0007 (warning ID pattern), Rule 2 (simplicity first — each probe ≤ 100 LOC, marker-based, no parsing beyond what Phase 1 supplies; Rule 8 — read Phase 1's existing parsers and reuse, don't reinvent)

## Context

This story lands the three "marker probes" that complete Layer B's evidence set:

1. **`GeneratedCodeProbe`** (B4 per [localv2.md §5.2 B4](../../../localv2.md)) — detects code-generation output via header patterns and well-known directory conventions (`graphql-codegen`, `openapi-typescript`, `prisma generate`, Protocol Buffers `.pb.ts`, `dist/`/`build/`/`out/` build artifacts). Reports `generated_code` slice with `files` (each annotated with generator + source spec + regenerate_command) and `build_outputs` (glob list for distroless-image build-stage copy decisions in Phase 7+).

2. **`NodeReflectionProbe`** (B3 per [localv2.md §5.2 B3](../../../localv2.md)) — detects Node-specific dynamic patterns that erode SCIP confidence: `eval`, `Function`, dynamic `require(varName)`, dynamic `import(specifier)`, prototype manipulation, decorator usage (NestJS, TypeORM, class-validator), Express middleware chains, `process.env.*` code-path-affecting reads. Reports `reflection` slice.

3. **`SemanticIndexMetaProbe`** (per [phase-arch-design.md §"Development view"](../phase-arch-design.md) lines 250–253 `semantic_index_meta.py` listing) — reads the metadata about the SCIP indexer run itself (separate from B2's freshness check): which `tsconfig.json` was used, what compiler API version, what file exclusion patterns SCIP applied. Reports `semantic_index_meta` slice consumed by Phase 3 adapters that need to know "what did the indexer actually look at?" — and by Phase 5+ debugging tooling.

**Constraint from the manifest:** each probe ≤ 100 LOC, marker-based detection, **no parsing beyond what Phase 1 parsers already supply**. The discipline is Rule 2 (simplicity first) + Rule 3 (surgical changes) + Rule 8 (reuse Phase 1's parsers). `package.json` → Phase 1's `ParsedManifestMemo` via `ctx.parsed_manifest(...)`. `tsconfig.json` → Phase 1's `jsonc.load` (S1-04). Filesystem walks for header-pattern detection use `pathlib`'s built-in `read_bytes` with the Phase 0 size cap — no new parsers, no Python imports beyond stdlib + Phase 1 utilities + tree-sitter (NodeReflection only — and via the SAME `_load_grammar` from S4-04, not a redeclared loader).

The probes are intentionally separate (not one fused "marker probe") — different consumers, different cache-key sensitivities, different `applies_to_*` filters in a future phase. Rule 7 — surface the conflict rather than averaging: the alternative shape "one `MarkerProbe` with three sub-slices" was considered and rejected because (a) cache invalidation on a graphql-codegen change should not also invalidate reflection scan results, (b) the slices live in three different localv2-spec sections, (c) the LOC budget per file stays under 100 only by keeping them split.

## References — where to look

- **Source design (the localv2 slice shapes are the contract):**
  - [`docs/localv2.md §5.2 B3 NodeReflectionProbe`](../../../localv2.md) lines 629–664 — full slice shape (`dynamic_property_access_count`, `eval_usage`, `function_constructor_usage`, `dynamic_require_count`, `dynamic_import_count`, `prototype_manipulation_count`, `decorator_usage`, `middleware_chains`, `env_var_reads`, `confidence_impact`, `affected_files`).
  - [`docs/localv2.md §5.2 B4 GeneratedCodeProbe`](../../../localv2.md) lines 666–692 — full slice shape (`files`, `build_outputs`).
- **Architecture:**
  - [`../phase-arch-design.md §"Development view"`](../phase-arch-design.md) — the three filenames are listed in `layer_b/`; per-file ≤ 100 LOC budget.
  - [`../phase-arch-design.md §"Component design" #12`](../phase-arch-design.md) — `TreeSitterImportGraphProbe`'s grammar-pin discipline is the precedent NodeReflection follows.
  - [`../phase-arch-design.md §"Goals" G1`](../phase-arch-design.md) — every Layer B–G language-agnostic probe ships with golden coverage; these three are language-agnostic in the sense that their detection logic is data-driven (catalog of generators, catalog of patterns).
- **Phase 2 ADRs:**
  - [`../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md`](../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md) — NodeReflection reuses the same load path.
- **Existing code:**
  - `src/codegenie/probes/layer_b/tree_sitter_import_graph.py` (from S4-04) — `_load_grammar` is exported / imported here, NOT redeclared.
  - `src/codegenie/parsers/jsonc.py` (Phase 1 S1-04) — for `tsconfig.json` consumption in `SemanticIndexMetaProbe`.
  - `src/codegenie/coordinator/parsed_manifest_memo.py` (Phase 1 S1-07) — `ctx.parsed_manifest(...)` for `package.json` reads.

## Goal

Running `codegenie gather` against the `tests/fixtures/portfolio/minimal-ts/` fixture produces three new slices in `repo-context.yaml`: `generated_code` (with at least one detected generator + `build_outputs` list from `package.json#files`), `reflection` (with counts for every dynamic pattern category — most are zero in `minimal-ts`, that's fine), and `semantic_index_meta` (with the `tsconfig.json` path used and indexer-relevant compiler options). Each probe is independently testable (one test file per probe), marker-absent paths emit `confidence="medium"` with reason `"no_markers_detected"` (NOT `"low"` — the absence of markers is honest evidence, not a degraded signal), and tests **fail loudly** on schema drift.

## Acceptance criteria

### Cross-probe ACs (apply to all three)

- [ ] **AC-X1 — File size budget.** Each probe module is **≤ 100 LOC** of code (comments and module-level docstrings excluded by `radon` or equivalent — implementer choice of LOC counter; CI bench `cloc --include-ext=py --not-match-f='__init__'` or `radon raw --no-comments --no-blank` is acceptable). A unit test (`test_layer_b_marker_probe_loc_budget`) parametrizes over the three files and asserts the limit. **The 100-LOC budget is the structural discipline that keeps each probe marker-based and forbids creeping parser logic.**

- [ ] **AC-X2 — Marker catalogs are data, not branching code.** Each probe's detection logic uses **module-level tuples/dicts** (the data) and a single-pass scan/dispatch loop (the code). Example shape for `GeneratedCodeProbe`:
  ```python
  _GENERATOR_HEADER_MARKERS: Final[tuple[tuple[str, bytes], ...]] = (
      ("graphql-codegen", b"// This file was automatically generated by graphql-codegen"),
      ("openapi-typescript", b"/**\n * This file was auto-generated by openapi-typescript"),
      ("protoc-typescript", b"// Code generated by protoc-gen-ts"),
      ("prisma", b"// This file is auto-generated by Prisma"),
  )
  _BUILD_OUTPUT_DIRS: Final[frozenset[str]] = frozenset({"dist", "build", "out"})
  ```
  Adding a generator is a tuple-entry insertion + a fixture test + the sub-schema's `Literal` enum update. **Zero edits to detection logic** (Open/Closed at the file boundary — same pattern as S2-02's `_LOCKFILE_PRECEDENCE`).

- [ ] **AC-X3 — Marker-absent path is honest `confidence="medium"`.** Each probe's slice carries `confidence: "high" | "medium" | "low"`. `"high"` when ≥ 1 marker hit AND no parse errors. `"medium"` when zero markers hit (honest absence) — NOT `"low"`. `"low"` is reserved for parser failures, grammar-load refusals, or hard errors. The Rule 12 (fail loud) framing: a repo with no codegen output is *normal*, not degraded; the slice should not slot it into the same confidence bucket as a parser-broken slice.

- [ ] **AC-X4 — Per-probe warning ID frozenset + import-time assertion.** Each probe declares a `_WARNING_IDS` frozenset; the IDs match the Phase 1 ADR-0007 regex via import-time `assert`.

- [ ] **AC-X5 — Registry membership.** Each probe is imported in `src/codegenie/probes/__init__.py` via additive lines. `default_registry.all_probes()` includes all three.

- [ ] **AC-X6 — Tooling green.** `ruff check`, `ruff format --check`, `mypy --strict` on each module, `pytest tests/unit/probes/layer_b/test_{generated_code,node_reflection,semantic_index_meta}.py`. All green.

### Per-probe ACs

#### `GeneratedCodeProbe` — `src/codegenie/probes/layer_b/generated_code.py`

- [ ] **AC-G1 — Probe contract attributes.** `class GeneratedCodeProbe(Probe)`: `name="generated_code"`, `version="0.1.0"`, `layer="B"`, `tier="base"`, `applies_to_languages=["javascript","typescript"]`, `applies_to_tasks=["*"]`, `requires=["language_detection"]`, `timeout_seconds=30`, `declared_inputs=["**/*.ts", "**/*.tsx", "**/*.js", "package.json", "openapi.yaml", "openapi.yml", "schema.graphql", "prisma/schema.prisma"]`. Decorator `@register_probe` (defaults — light).

- [ ] **AC-G2 — Detection sources (data, not branches).**
  - **Header pattern match** via `_GENERATOR_HEADER_MARKERS` (AC-X2 example). Reads the first 4 KB of each `.ts`/`.tsx`/`.js` file (size cap — files shorter are fine; longer files match only against the first 4 KB) and tests every marker. First hit wins (generator-name dedup).
  - **Well-known generated directory match**: `src/generated/`, `__generated__/`, `gen/` are flagged as "likely-generated" with `confidence="medium"` on the slice entry (the directory convention is a strong signal; absence of a header is not disqualifying).
  - **`package.json#scripts` heuristic** — `scripts.codegen`, `scripts["build:gql"]`, `scripts.generate` etc. are recorded as `regenerate_command` for matched generators. Read via `ctx.parsed_manifest(repo_root / "package.json")` (Rule 8 — reuse Phase 1 memo).

- [ ] **AC-G3 — Slice shape per `localv2.md §5.2 B4`.**
  ```yaml
  generated_code:
    files:
      - path: "src/generated/graphql.ts"
        generator: "graphql-codegen"
        source_spec: "src/schema.graphql"        # optional; only when matchable
        regenerate_command: "pnpm run codegen"    # optional; only when matchable
    build_outputs:                                # `package.json#files` verbatim when list-of-strings; else []
      - "dist/index.js"
      - "dist/**/*.js"
    confidence: high
  ```
  `source_spec` and `regenerate_command` are present when matchable from `package.json#scripts` + standard generator-name heuristics; otherwise omitted from the entry (the sub-schema in S4-07 marks them optional).

- [ ] **AC-G4 — Marker-absent path (AC-X3).** Repo with zero generator headers and zero generated directories → `files: []`, `build_outputs: <package.json#files or []>`, `confidence: "medium"`, `warnings: ["generated_code.no_markers_detected"]`.

- [ ] **AC-G5 — Per-generator unit tests.** `tests/unit/probes/layer_b/test_generated_code.py` includes one test per marker in `_GENERATOR_HEADER_MARKERS` (parametrized): synthesize a fixture file with the header; run the probe; assert `files[0].generator == <expected>`. **A future contributor adding a marker but forgetting the test** fails CI via a `test_every_generator_marker_has_a_test` enumeration check.

#### `NodeReflectionProbe` — `src/codegenie/probes/layer_b/node_reflection.py`

- [ ] **AC-R1 — Probe contract attributes.** `class NodeReflectionProbe(Probe)`: `name="node_reflection"`, `version="0.1.0"`, `layer="B"`, `tier="base"`, `applies_to_languages=["javascript","typescript"]`, `applies_to_tasks=["*"]`, `requires=["language_detection"]`, `timeout_seconds=60`, `declared_inputs=["**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx", "package.json", "tools/grammars.lock"]` (tools/grammars.lock pins invalidation alongside grammar updates). Decorator `@register_probe(heaviness="light")`.

- [ ] **AC-R2 — Reuses `_load_grammar` from S4-04.** The probe imports `from codegenie.probes.layer_b.tree_sitter_import_graph import _load_grammar, GrammarLoadRefused` — does NOT redeclare. Rule 8 — read before you write. AST-walk test (`test_no_redeclared_grammar_loader`) asserts no function named `_load_grammar` defined in this module.

- [ ] **AC-R3 — Pattern catalog as data (AC-X2 shape).** Each Node-specific dynamic pattern from [localv2.md §5.2 B3](../../../localv2.md) maps to a tree-sitter Query string in a module-level dict:
  ```python
  _REFLECTION_QUERIES: Final[dict[str, str]] = {
      "eval_usage":                 "(call_expression function: (identifier) @id (#eq? @id \"eval\"))",
      "function_constructor_usage": "(new_expression constructor: (identifier) @id (#eq? @id \"Function\"))",
      "dynamic_require":            "(call_expression function: (identifier) @id arguments: (arguments . (identifier))  (#eq? @id \"require\"))",
      "dynamic_import":             "(call_expression function: (import) arguments: (arguments . (identifier)))",
      "dynamic_property_access":    "(subscript_expression)",
      "prototype_manipulation":     "(member_expression property: (property_identifier) @p (#match? @p \"^(prototype|__proto__)$\"))",
      ...
  }
  ```
  Adding a pattern is a dict-entry + a fixture file + the sub-schema's count-field declaration. **Zero edits to detection logic.**

- [ ] **AC-R4 — Slice shape per `localv2.md §5.2 B3`.** Every count field from the localv2 spec is emitted (`dynamic_property_access_count`, `eval_usage`, `function_constructor_usage`, `dynamic_require_count`, `dynamic_import_count`, `prototype_manipulation_count`, `decorator_usage.{nestjs,typeorm,class_validator,custom_decorators_detected}`, `middleware_chains`, `env_var_reads.{count,code_path_affecting}`, `confidence_impact`, `affected_files`). All `int` counts default to `0` when no match; `decorator_usage` flags default to `false`. `affected_files` is the sorted list of files where ≥ 1 reflection pattern hit.

- [ ] **AC-R5 — `decorator_usage.{nestjs,typeorm,class_validator}` detection via `package.json` deps.** Reads `dependencies` ∪ `devDependencies` from `ctx.parsed_manifest`; `nestjs` ← `@nestjs/core` present; `typeorm` ← `typeorm` present; `class_validator` ← `class-validator` present. `custom_decorators_detected` counts decorator nodes (tree-sitter Query) NOT attributable to these three frameworks. (Detection is structural — name-based via package presence; not call-pattern.)

- [ ] **AC-R6 — `env_var_reads.code_path_affecting` heuristic.** A `process.env.X` read is "code-path-affecting" if it appears within 2 AST levels of an `if_statement` or `switch_statement` condition. Tree-sitter Query captures the parent-context; the heuristic is data-driven (a single `_ENV_VAR_CODE_PATH_QUERY` string). The count is informational — `confidence_impact: medium` when `code_path_affecting > 0`.

- [ ] **AC-R7 — `confidence_impact` derivation.** Pattern-matched typed:
  - All counts == 0 AND `decorator_usage.{nestjs,typeorm,class_validator}` all False → `confidence_impact: "low"` (i.e., HIGH confidence that reflection isn't a concern — note the inverted semantics; the field is named "confidence_impact" not "confidence," per the localv2 spec). Rule 8 — match the spec; clarify in implementer notes.
  - Any `eval_usage > 0` OR `function_constructor_usage > 0` → `confidence_impact: "high"` (these are rare and high-signal).
  - Otherwise → `confidence_impact: "medium"`.

- [ ] **AC-R8 — Grammar pin mismatch path.** On `GrammarLoadRefused` propagated from `_load_grammar`, the slice is `confidence_impact: "high"` (treat as "we couldn't measure, assume the worst — the gather output must not falsely claim low impact"); `affected_files: []`; `errors: ["node_reflection.grammar_pin_mismatch"]`. T-R5 exercises this.

#### `SemanticIndexMetaProbe` — `src/codegenie/probes/layer_b/semantic_index_meta.py`

- [ ] **AC-M1 — Probe contract attributes.** `class SemanticIndexMetaProbe(Probe)`: `name="semantic_index_meta"`, `version="0.1.0"`, `layer="B"`, `tier="base"`, `applies_to_languages=["javascript","typescript"]`, `applies_to_tasks=["*"]`, `requires=["node_build_system"]`, `timeout_seconds=10`, `declared_inputs=["tsconfig.json", "tsconfig.*.json", "package.json"]`. Decorator `@register_probe` (defaults — light).

- [ ] **AC-M2 — Reads `tsconfig.json` via Phase 1 `jsonc` parser (no new parser).** Uses `parsers.jsonc.load(tsconfig_path, max_bytes=5*1024*1024, max_depth=64)` (Phase 1 S1-04 caps). The probe does NOT walk `extends` chains (that's `NodeBuildSystemProbe`'s job in S2-02) — it reads the resolved `compilerOptions` from `build_system.typescript` slice if available, OR falls back to a single-file `tsconfig.json` read.

- [ ] **AC-M3 — Slice shape.**
  ```yaml
  semantic_index_meta:
    tsconfig_path: "tsconfig.json"        # the path SCIP would use
    has_extends: false                    # whether tsconfig.json has an `extends` field
    target: "es2022"                      # compilerOptions.target
    module: "esnext"                      # compilerOptions.module
    module_resolution: "node"             # compilerOptions.moduleResolution
    strict: true                          # compilerOptions.strict (default false if absent)
    include_globs: ["src/**/*", ...]      # compilerOptions.include (verbatim)
    exclude_globs: ["node_modules", ...]  # compilerOptions.exclude (verbatim)
    files_count_estimate: 247             # count of indexable files matching include/exclude
    confidence: high
  ```
  Every field optional; missing `tsconfig.json` → `confidence: "medium"`, `warnings: ["semantic_index_meta.no_tsconfig"]`, empty slice except `tsconfig_path: null`.

- [ ] **AC-M4 — `files_count_estimate` consistency with `ScipIndexProbe.files_in_repo`.** The estimate uses the same exclude set as `ScipIndexProbe._count_indexable_files` (S4-03 AC-9) — extract the helper to a shared module (`src/codegenie/probes/layer_b/_indexable_files.py`) and import. **Divergence is a structural bug** — Phase 3 adapters reading both slices would see inconsistent counts. A cross-probe test (`test_semantic_index_meta_count_matches_scip_count`) on the `minimal-ts` fixture asserts equality.

- [ ] **AC-M5 — Parse failure path.** `jsonc.load` raises `SizeCapExceeded` or `MalformedJSONError` → `confidence: "low"`, `errors: ["semantic_index_meta.tsconfig_unparseable"]`, slice contains `tsconfig_path` only.

### Cross-probe golden test

- [ ] **AC-X7 — Golden snapshots against `minimal-ts` fixture (when S7-01 lands).** Each probe ships a golden test slot — `tests/golden/probes/layer_b/{generated_code,node_reflection,semantic_index_meta}/minimal-ts.golden.yaml`. The goldens are stubbed in this story (empty placeholder + a `pytest.skip("golden produced in S7-05")` decorator on the test until the fixture lands). **Wired this way so S7-01/S7-05 can drop in the real golden without editing this story's code.**

## Implementation outline

1. **Decide co-location of `_indexable_files`.** Either (a) extract from S4-03 to `src/codegenie/probes/layer_b/_indexable_files.py` and update S4-03 to import (small Rule 3 / Rule 11 refactor; do this if it stays under 50 LOC), OR (b) duplicate per probe — chosen path is (a) because AC-M4 requires structural equality, and duplication makes that an aspirational test rather than a structural one. The extraction is one of this story's `Edit` artifacts.

2. **`GeneratedCodeProbe` (~80 LOC):**
   - Module-level constants per AC-X2.
   - Pure helpers: `_detect_header_marker(content_head: bytes) -> str | None`, `_detect_directory_marker(path: Path) -> bool`, `_match_regenerate_command(generator: str, scripts: dict) -> str | None`.
   - `async def run(...)`: enumerate `.ts`/`.tsx`/`.js`/`.jsx` files; read first 4 KB; check each marker; compose slice.

3. **`NodeReflectionProbe` (~95 LOC):**
   - Module-level `_REFLECTION_QUERIES` dict.
   - Imports `_load_grammar`, `GrammarLoadRefused` from S4-04's module.
   - Pure helper: `_count_matches(language, query_str, file_bytes) -> int`.
   - `async def run(...)`: load grammar (catch `GrammarLoadRefused` → AC-R8); enumerate files; per file, run each query; aggregate counts; derive `confidence_impact`.

4. **`SemanticIndexMetaProbe` (~70 LOC):**
   - Reads `build_system` slice for `typescript.resolved_compiler_options` if present; else parses `tsconfig.json` via `jsonc.load`.
   - Uses extracted `_count_indexable_files`.

5. **Register all three** via `src/codegenie/probes/__init__.py` additive imports.

## TDD plan — red / green / refactor

### RED — per probe

#### GeneratedCode
- **T-G1** `test_probe_contract_attributes` (AC-G1).
- **T-G2** `test_loc_budget` (AC-X1).
- **T-G3** `test_per_generator_marker_detection` (AC-G2, AC-G5): parametrize over `_GENERATOR_HEADER_MARKERS`; assert each is detected.
- **T-G4** `test_every_generator_marker_has_a_test` (AC-G5): enumerate `_GENERATOR_HEADER_MARKERS`; for each, assert a test exists in the parametrize ID list.
- **T-G5** `test_build_outputs_from_package_json_files` (AC-G3): fixture with `package.json#files = ["dist/index.js", "dist/**/*.js"]`; assert `build_outputs` matches verbatim.
- **T-G6** `test_marker_absent_emits_medium_confidence` (AC-G4, AC-X3): empty fixture; `confidence="medium"`, NOT `"low"`.
- **T-G7** `test_marker_catalog_is_open_closed` (AC-X2): AST-walk `generated_code.py`; assert the run method body contains exactly one `for` over `_GENERATOR_HEADER_MARKERS`; no `if generator == "..."` branches.

#### NodeReflection
- **T-R1** `test_probe_contract_attributes` (AC-R1).
- **T-R2** `test_loc_budget` (AC-X1).
- **T-R3** `test_no_redeclared_grammar_loader` (AC-R2): AST-walk; assert no `def _load_grammar` in this module; assert `_load_grammar` IS imported from `tree_sitter_import_graph`.
- **T-R4** `test_per_reflection_pattern_detection` (AC-R3): parametrize over `_REFLECTION_QUERIES`; synthesize a fixture file matching the pattern; assert count > 0.
- **T-R5** `test_grammar_pin_mismatch_path` (AC-R8): monkeypatch `_load_grammar` to raise; assert `confidence_impact="high"` (the inverted semantics), `errors=["node_reflection.grammar_pin_mismatch"]`.
- **T-R6** `test_decorator_usage_via_package_json` (AC-R5): `package.json` with `@nestjs/core`, no `typeorm`, with `class-validator`; assert `decorator_usage = {nestjs: true, typeorm: false, class_validator: true, custom_decorators_detected: 0}`.
- **T-R7** `test_eval_usage_promotes_high_confidence_impact` (AC-R7): fixture with `eval("...")`; assert `confidence_impact="high"`.
- **T-R8** `test_all_counts_zero_low_confidence_impact` (AC-R7): clean fixture; `confidence_impact="low"` (the "no reflection concern" terminal).
- **T-R9** `test_env_var_reads_code_path_affecting_heuristic` (AC-R6): fixture with `if (process.env.X) { ... }`; assert `code_path_affecting >= 1`.

#### SemanticIndexMeta
- **T-M1** `test_probe_contract_attributes` (AC-M1).
- **T-M2** `test_loc_budget` (AC-X1).
- **T-M3** `test_reads_tsconfig_via_phase1_jsonc_parser` (AC-M2): AST-walk; assert `from codegenie.parsers.jsonc import load` (or equivalent); assert no `json.load`/`open(tsconfig).read()` raw paths.
- **T-M4** `test_slice_shape_minimal_ts` (AC-M3): fixture `tsconfig.json` with target=es2022, module=esnext, strict=true; assert slice fields match.
- **T-M5** `test_files_count_estimate_matches_scip_count` (AC-M4): on the `minimal-ts` fixture (or a synthetic equivalent), run both `ScipIndexProbe._count_indexable_files` and `SemanticIndexMetaProbe`'s file-count; assert exact equality.
- **T-M6** `test_no_tsconfig_emits_medium_confidence` (AC-M3): empty fixture; `confidence="medium"`, `warnings=["semantic_index_meta.no_tsconfig"]`.
- **T-M7** `test_tsconfig_parse_failure_path` (AC-M5): fixture with truncated `tsconfig.json` (`{`); assert `confidence="low"`, `errors=["semantic_index_meta.tsconfig_unparseable"]`.

### Shared
- **T-X1** `test_layer_b_marker_probes_registered` (AC-X5): all three in `default_registry`.
- **T-X2** `test_warning_ids_match_adr_0007` for each (AC-X4).

### GREEN

Implement each probe per outline. Keep each file ≤ 100 LOC by extracting helpers ruthlessly and using catalog-driven detection.

### REFACTOR

- Run `radon raw` or `cloc` on each file; confirm under 100 LOC.
- If `NodeReflectionProbe` exceeds the budget (likely tight given the tree-sitter query infrastructure), extract `_count_matches` to a shared util at `src/codegenie/probes/layer_b/_tree_sitter_helpers.py`. Do NOT inflate the budget — extraction is the discipline.
- Confirm `mypy --strict` passes for all three.

## Files to touch

**Create:**
- `src/codegenie/probes/layer_b/generated_code.py`
- `src/codegenie/probes/layer_b/node_reflection.py`
- `src/codegenie/probes/layer_b/semantic_index_meta.py`
- `src/codegenie/probes/layer_b/_indexable_files.py` (extracted from S4-03 if a shared helper)
- `tests/unit/probes/layer_b/test_generated_code.py`
- `tests/unit/probes/layer_b/test_node_reflection.py`
- `tests/unit/probes/layer_b/test_semantic_index_meta.py`
- Golden stubs (placeholders) at `tests/golden/probes/layer_b/{generated_code,node_reflection,semantic_index_meta}/minimal-ts.golden.yaml`.

**Edit (additive):**
- `src/codegenie/probes/__init__.py` — three additive imports.
- `src/codegenie/probes/layer_b/scip_index.py` (only if extracting `_count_indexable_files`) — update import to point at `_indexable_files.py`.

## Out of scope

- **Golden file content.** S7-01 lands the `minimal-ts` fixture; S7-05 produces real goldens. Stubs here; production goldens later.
- **Sub-schemas.** S4-07 lands per-probe sub-schemas.
- **`BuildGraphProbe`** (the localv2 §5.2 B5 cousin). The arch synthesizes this into `DepGraphProbe` (S4-05). Marker-style B5 detection is not a separate probe.
- **`ScipIndexProbe`-vs-`SemanticIndexMetaProbe` overlap.** SCIP probe is heavy (subprocess), SemanticIndexMeta is light (config-file read). Separate cache lifetimes. The overlap is intentional — they answer different questions.
- **Cross-language reflection patterns.** Phase 2 is Node-only. Python `eval`, Java reflection, Go reflection are Phase-8+.
- **Recursive directory walk depth.** Each probe walks `repo_root` with default depth — no cap — but excludes `node_modules`, `.git`, `dist`, `build`, `out` (canonical exclude set from S4-03). Adding a new exclude is a one-line addition to the shared `_indexable_files.py` exclude tuple.

## Notes for the implementer

- **Rule 8 — read before you write.** `_load_grammar` (S4-04), `_count_indexable_files` (S4-03), `ctx.parsed_manifest` (S1-07), `jsonc.load` (S1-04), `safe_yaml.load` (S1-03) all exist. Reusing them is mandatory; AC-R2, AC-M2, AC-M4, and AC-X2 enforce structurally. T-R3 / T-M3 / T-G7 are the AST-walk discipline that catches drift.
- **The "marker probes are small" discipline.** AC-X1's 100-LOC budget is structural — it forbids creeping parser logic. A future contributor proposing "let's add `package-lock.json` parsing to `GeneratedCodeProbe` to detect `prisma generate` from the resolved dep tree" must be redirected: that's a parsing task; Phase 1's parsers OR a new dedicated probe is the right home. **Marker probes detect markers, period.**
- **`confidence_impact` inverted semantics in NodeReflection (AC-R7).** The localv2 spec's `confidence_impact` field is "how much does this erode confidence" — `"high"` means "high erosion = bad," `"low"` means "low erosion = good." This is inverted from the normal `confidence` field semantics. Document inline in the module docstring; do NOT alias to `confidence: high/medium/low` for cosmetic consistency — that would break the localv2 contract (Rule 11 — match codebase / spec convention).
- **Marker-absent ≠ degraded.** AC-X3 / AC-G4. A repo with no codegen output is normal. A renderer that highlights `confidence: medium` slices must NOT pile-up these honest absences as "warnings to escalate." Phase 8 renderer (Phase 8+) will categorize; Phase 2 just emits the honest typed shape.
- **Why split into three files instead of one fused probe.** Rule 7 — surface the conflict. Cache invalidation on a graphql-codegen change ≠ cache invalidation on a reflection scan ≠ cache invalidation on tsconfig change. Co-located in one module → all three invalidate on any of the three input changes. Separate modules → each owns its `declared_inputs`. Rule 2 says simplicity — but the cost of fusion (cache over-invalidation) outweighs the saving (one file vs three).
- **Tree-sitter Queries cheat-sheet.** The Queries used in `NodeReflectionProbe` are short S-expressions. Tree-sitter's docs explain the syntax; bundle them as inline string constants (Rule 11 — match S4-04's precedent). Don't pull in a `.scm` query-file vendoring system for ~10 queries.
- **`process.env.X` heuristic.** AC-R6 is a heuristic — perfect detection of "code-path-affecting" reads would require dataflow analysis (way beyond Phase 2). The 2-AST-level heuristic catches the canonical `if (process.env.X)` pattern. Document inline that this is a heuristic with known false-positives (e.g., `process.env.X` inside a `return` expression of an `if`-block body would be missed). Phase 8+'s richer Planner can refine.
- **`tsconfig_path` resolution (AC-M2).** When `extends` chains exist (S2-02 already handled this in `NodeBuildSystemProbe`), `SemanticIndexMetaProbe` reads `build_system.typescript.resolved_compiler_options_path` if available, NOT the raw `tsconfig.json`. Fallback when `build_system` is missing → read literal `tsconfig.json`. Rule 7 / Rule 8 — surface and reuse.
- **Rule 9 — tests verify intent.** T-G7 (AST-walk for `if generator==` branches) encodes the WHY of catalog-driven detection. T-R3 (no redeclared grammar loader) encodes the WHY of S4-04 reuse. T-M5 (count equality with SCIP) encodes the WHY of the shared helper. None of these check "the function works" — they check WHICH discipline is upheld.
