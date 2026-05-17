# Story S4-06 — `GeneratedCode` + `NodeReflection` + `SemanticIndexMeta` marker probes

**Step:** Step 4 — Ship `IndexHealthProbe` (B2) + Layer B structural probes
**Status:** **GREEN (2026-05-17)** — all three probes shipped. `GeneratedCodeProbe` + `SemanticIndexMetaProbe` landed 2026-05-16 ([`_attempts/S4-06.md`](_attempts/S4-06.md) attempt 1). `NodeReflectionProbe` unblocked + shipped 2026-05-17 after [02-ADR-0011](../ADRs/0011-tree-sitter-grammars-via-pypi-wheels.md) superseded the vendored-`.so` grammar model with PyPI wheels; grammar loading now flows through `codegenie.grammars.lock.language_for` against `tree-sitter-typescript` / `tree-sitter-javascript`.
**Effort:** M
**Depends on:** S4-03 (lands `src/codegenie/grammars/lock.py` — the `load_and_verify(repo_root) -> GrammarLockFile` typed loader + `GrammarLoadRefused` exception; `tools/grammars.lock`; vendored TypeScript + JavaScript grammar binaries on disk). `NodeReflectionProbe` **imports the S4-03 kernel directly**; it does NOT import private helpers from S4-04's `tree_sitter_import_graph` module (those are module-private; the load chokepoint is the shared kernel in `codegenie.grammars.lock`). S4-06 therefore does not topologically depend on S4-04 — the two probes are siblings consuming the same kernel.
**ADRs honored:** [`02-ADR-0002`](../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md) (NodeReflection's tree-sitter use is governed by the same grammar pin; uses the shared `codegenie.grammars.lock` kernel from S4-03 — NOT redeclared, NOT re-implemented; identical discipline to S4-04 hardened story), [`02-ADR-0003`](../ADRs/0003-coordinator-heaviness-sort-annotation.md) (`GeneratedCodeProbe` and `SemanticIndexMetaProbe` are `heaviness="light"` — marker detection is fast; `NodeReflectionProbe` is `heaviness="medium"` to match S4-04 parity since both run per-file tree-sitter Queries on the same `.ts/.tsx/.js/.jsx` glob), Phase 1 ADR-0004 (sub-schema per probe, lands in S4-07), Phase 1 ADR-0007 (warning ID pattern), Phase 0 ADR-0007 (`ProbeContext` ABC is frozen — no `sibling_slices` field; sibling reads not available without ADR amendment), Rule 2 (simplicity first — each probe ≤ 100 LOC, marker-based, no parsing beyond what Phase 1 supplies; Rule 8 — read Phase 1's existing parsers and reuse, don't reinvent)

## Validation notes (2026-05-16, phase-story-validator)

Audited via four critic lenses (coverage, test-quality, consistency, design-patterns). Verdict: **HARDENED**. Goal and AC-to-goal trace unchanged. Edits were mechanical reconciliations against shipped code + frozen contracts; no design intent was rewritten.

Summary of changes (full audit in [`_validation/S4-06-layer-b-marker-probes.md`](_validation/S4-06-layer-b-marker-probes.md)):

1. **Phantom-import correction.** `NodeReflectionProbe`'s grammar imports were rewritten from the phantom `codegenie.probes.layer_b.tree_sitter_import_graph._load_grammar` to the shipped kernel surface `codegenie.grammars.lock.{load_and_verify, GrammarLoadRefused, GrammarLockFile}` (the exact same chokepoint S4-04 hardened to). `_load_grammar` does not exist anywhere in the codebase; AC-R2 / T-R3 / impl outline §3 / AC-R8 now reference the real surface.
2. **Sibling-slice path is unavailable.** Phase 0 ADR-0007 freezes `ProbeContext` — no `sibling_slices` field, and `NodeBuildSystemProbe` does not write a `build_system.json` sidecar. AC-M1 `requires=["node_build_system"]` → `requires=["language_detection"]`; AC-M2 / impl §4 / Notes drop the "reads `build_system.typescript.resolved_compiler_options` if available" branch. `SemanticIndexMetaProbe` always reads `tsconfig.json` directly via `jsonc.load`.
3. **`Probe.run` two-arg signature pinned.** All three probes implement `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` (the frozen ABC at `src/codegenie/probes/base.py:94`). Impl outline §2/§3/§4 now show the signature explicitly; mirrors S4-04 hardened pattern.
4. **`_indexable_files.py` extraction signatures pinned to S4-03's actual surface.** Exclude set is `{"node_modules", "dist", "build", ".git"}` (no `"out"` — only scip_index's set is canonical for indexable-file counting); suffix set is `{".ts", ".tsx"}` (no `.js`/`.jsx` for SCIP's program scope). `GeneratedCodeProbe`'s `_BUILD_OUTPUT_DIRS = {"dist", "build", "out"}` is a separate concept (generator-output detection, not SCIP-indexable counting) and is documented as such.
5. **`NodeReflectionProbe` reclassified `heaviness="medium"`.** Matches S4-04 parity — same workload shape (per-file tree-sitter Query scan across `.ts/.tsx/.js/.jsx`), same grammar-pin discipline. `GeneratedCodeProbe` + `SemanticIndexMetaProbe` remain `light`.
6. **LOC budget tool pinned to `radon raw --no-comments --no-blank`** (one tool, not "implementer choice"). Removes a variance source from CI.
7. **`_REPO_ROOT` resolution discipline.** `NodeReflectionProbe` resolves the codewizard-sherpa repo root (where `tools/grammars.lock` lives), NEVER the analyzed `repo.root`. Same `Path(__file__).resolve().parents[N]` pattern S4-04 hardened to. New AC-R0 ("Repo-root resolution").
8. **T-R3 rewritten** from the wrong-shaped "no `def _load_grammar`" check to the load-bearing assertion: no redefinition of `GrammarLoadRefused`, no direct `Path("tools/grammars.lock")` read, no `import blake3` — those belong to the kernel.
9. **T-G7 open/closed assertion strengthened.** Single AST-walk asserts (a) one `for` over `_GENERATOR_HEADER_MARKERS` AND (b) no string-literal `Compare` against any value present in `_GENERATOR_HEADER_MARKERS` outside the constant declaration itself.
10. **Byte-identical determinism test added (T-X3)** — runs each probe twice on the same fixture, asserts `model_dump_json(...)` byte equality. Catches dict-iteration-order leaks (e.g., unsorted `affected_files`).
11. **`confidence` Literal alias** — introduced module-level `_Confidence = Literal["high", "medium", "low"]` (matching `scip_index.py` precedent) and `_ConfidenceImpact = Literal["high", "medium", "low"]` so the inverted-semantics field in `NodeReflectionProbe` is machine-distinct from the standard `confidence` field. Make illegal mixing un-typeable.
12. **Notes: rule-of-three backlog.** Documented that `_get_language(lock, language) -> tree_sitter.Language` will be duplicated once between S4-04 and S4-06; rule-of-three not yet triggered, but flagged for extraction to `src/codegenie/grammars/loader.py` when the third consumer (Python grammar — Phase 8+) appears.

## Context

This story lands the three "marker probes" that complete Layer B's evidence set:

1. **`GeneratedCodeProbe`** (B4 per [localv2.md §5.2 B4](../../../localv2.md)) — detects code-generation output via header patterns and well-known directory conventions (`graphql-codegen`, `openapi-typescript`, `prisma generate`, Protocol Buffers `.pb.ts`, `dist/`/`build/`/`out/` build artifacts). Reports `generated_code` slice with `files` (each annotated with generator + source spec + regenerate_command) and `build_outputs` (glob list for distroless-image build-stage copy decisions in Phase 7+).

2. **`NodeReflectionProbe`** (B3 per [localv2.md §5.2 B3](../../../localv2.md)) — detects Node-specific dynamic patterns that erode SCIP confidence: `eval`, `Function`, dynamic `require(varName)`, dynamic `import(specifier)`, prototype manipulation, decorator usage (NestJS, TypeORM, class-validator), Express middleware chains, `process.env.*` code-path-affecting reads. Reports `reflection` slice. Grammar load + BLAKE3 verification go through the **S4-03 kernel** at `codegenie.grammars.lock.load_and_verify` (the same chokepoint S4-04 uses) — `NodeReflectionProbe` does NOT re-read `tools/grammars.lock`, does NOT recompute BLAKE3, does NOT re-declare `GrammarLoadRefused`. The probe constructs `tree_sitter.Language(pin.file, pin.language)` for `language ∈ {"typescript","javascript"}` **after** the kernel's verification passes.

3. **`SemanticIndexMetaProbe`** (per [phase-arch-design.md §"Development view"](../phase-arch-design.md) lines 250–253 `semantic_index_meta.py` listing) — reads the metadata about the SCIP indexer run itself (separate from B2's freshness check): which `tsconfig.json` was used, what compiler API version, what file exclusion patterns SCIP applied. Reports `semantic_index_meta` slice consumed by Phase 3 adapters that need to know "what did the indexer actually look at?" — and by Phase 5+ debugging tooling. The probe reads `tsconfig.json` **directly** via Phase 1's `jsonc.load` (Phase 0 ADR-0007 freezes `ProbeContext`; no `sibling_slices` field exists, and `NodeBuildSystemProbe` does not write a `build_system.json` sidecar — so cross-probe slice access is not available and the probe falls back to first-principles reads of the resolved `tsconfig.json`).

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
  - `src/codegenie/grammars/lock.py` (from S4-03) — **the kernel chokepoint**: `load_and_verify(repo_root) -> GrammarLockFile`, `GrammarLoadRefused`, `GrammarPin`. `NodeReflectionProbe` imports `load_and_verify` + `GrammarLoadRefused` + `GrammarLockFile` from here, then constructs `tree_sitter.Language(pin.file, pin.language)` itself. The probe does NOT import S4-04's module (its helpers are private; the kernel is the shared surface).
  - `src/codegenie/parsers/jsonc.py` (Phase 1 S1-04) — `load(path: Path, *, max_bytes: int, max_depth: int = 64) -> dict[str, JSONValue]`; raises `SizeCapExceeded`, `DepthCapExceeded`, `MalformedJSONError`, `SymlinkRefusedError`. Used by `SemanticIndexMetaProbe` for `tsconfig.json`.
  - `src/codegenie/coordinator/parsed_manifest_memo.py` (Phase 1 S1-07) — `ParsedManifestMemo`; exposed on `ProbeContext` as the optional callable `ctx.parsed_manifest(path) -> Mapping[str, Any] | None`. Allowlist defaults to `frozenset({"package.json"})` — sufficient for the `nestjs/typeorm/class-validator` dep detection in `NodeReflectionProbe`. Fallback to direct `safe_json.load(...)` when `ctx.parsed_manifest is None` (matches `language_detection.py:330` pattern).
  - `src/codegenie/probes/layer_b/scip_index.py` (from S4-03) — currently owns `_count_indexable_files(root)`, `_walk_indexable_files(root)`, `_read_exclude_file(root)`, `_INDEXABLE_SUFFIXES = frozenset({".ts", ".tsx"})`, `_EXCLUDE_DIRS = frozenset({"node_modules", "dist", "build", ".git"})`. Extracted to `_indexable_files.py` by AC-M4 step 1 below.
  - `src/codegenie/probes/base.py:74-96` — frozen `Probe` ABC: `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`. Two-arg signature; one-arg `run(self, ctx)` is `TypeError` at dispatch.
  - `src/codegenie/probes/registry.py` — `@register_probe` (no parens, defaults `heaviness="light"`, `runs_last=False`) AND `@register_probe(heaviness="medium")` are both valid; `default_registry.all_probes()` is the enumeration API.
  - `src/codegenie/probes/layer_b/index_health.py:118-123` — the **import-time validation pattern** `_WARNING_IDS` + `_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")` + `for _id in _WARNING_IDS: if not _ID_PATTERN.match(_id): raise AssertionError(...)`. Mirror verbatim (Rule 11 — match convention). Bare `assert` is forbidden (S4-04 AC-11 precedent).

## Goal

Running `codegenie gather` against the `tests/fixtures/portfolio/minimal-ts/` fixture produces three new slices in `repo-context.yaml`: `generated_code` (with at least one detected generator + `build_outputs` list from `package.json#files`), `reflection` (with counts for every dynamic pattern category — most are zero in `minimal-ts`, that's fine), and `semantic_index_meta` (with the `tsconfig.json` path used and indexer-relevant compiler options read directly from the file — no sibling-slice resolution, since Phase 0 ADR-0007 freezes `ProbeContext`). Each probe is independently testable (one test file per probe), implements the two-arg `async def run(self, repo, ctx) -> ProbeOutput` from the frozen ABC, marker-absent paths emit `confidence="medium"` with `warnings=[<probe>.no_markers_detected]` (NOT `"low"` — the absence of markers is honest evidence, not a degraded signal), and tests **fail loudly** on schema drift, on non-deterministic reruns (AC-X9 / T-X3), on phantom-surface imports (T-R3 catches kernel-chokepoint violations), and on functional-core leaks (T-X4 catches I/O in pure helpers).

## Acceptance criteria

### Cross-probe ACs (apply to all three)

- [ ] **AC-X1 — File size budget (pinned tool).** Each probe module is **≤ 100 LOC** of code as reported by `radon raw --no-comments --no-blank <path>` (`LOC = SLOC + multi_blank + ...` per radon's definition; we read radon's `sloc` column). The tool is pinned — "implementer choice" is removed to make CI deterministic. A unit test `test_layer_b_marker_probe_loc_budget` parametrizes over the three modules and asserts `radon`'s `sloc` value is `<= 100` for each. Tooling availability: `radon` ships in the dev extras (already used by S4-04's identical assertion); if absent, the test errors with a "missing dev dep" message — does NOT silently pass. **The 100-LOC budget is the structural discipline that keeps each probe marker-based and forbids creeping parser logic.**

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

- [ ] **AC-X3 — Marker-absent path is honest `confidence="medium"`.** Each probe declares a module-level type alias `_Confidence: TypeAlias = Literal["high", "medium", "low"]` (mirroring `index_health.py:134` precedent) and the slice's `confidence` field is typed as `_Confidence`. `"high"` when ≥ 1 marker hit AND no parse errors. `"medium"` when zero markers hit (honest absence) — **NOT `"low"`**. `"low"` is reserved for parser failures, grammar-load refusals, or hard errors. Test: a regression that flips the literal `"medium"` → `"low"` in the marker-absent path must fail (i.e., the assertion is `== "medium"`, not `in {"medium", "low"}`). The Rule 12 (fail loud) framing: a repo with no codegen output is *normal*, not degraded; the slice should not slot it into the same confidence bucket as a parser-broken slice.

- [ ] **AC-X8 — Two-arg `run` signature; functional core / imperative shell.** Each probe implements `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` — the two-arg signature from the frozen Phase 0 ABC at [`src/codegenie/probes/base.py:94`](../../../../src/codegenie/probes/base.py). All path inputs come from `repo.root` (NOT `ctx.workspace`, NOT `ctx.output_dir`). Detection work splits into **pure module-level helpers** (no I/O, no `await`, no `ctx`) consumed by the imperative `run` shell. A test (`test_pure_helpers_have_no_io`) AST-walks each module and asserts the helper functions named in the impl outline contain no `Call` to `open`, `Path.read_*`, `Path.write_*`, `asyncio.*`, `subprocess.*` — only the `run` shell may touch I/O. (S4-01 / `index_health.py` precedent for the functional-core split.)

- [ ] **AC-X9 — Byte-identical reruns (determinism).** Running each probe twice on the same fixture produces byte-identical `model_dump_json(...)` output (or, for the dict-shaped `ProbeOutput.schema_slice`, byte-identical `json.dumps(..., sort_keys=True)`). `affected_files` and any other list-shaped slice fields are sorted; dict iteration is locked via explicit key sorting. A property-style test `test_probe_is_deterministic_on_fixture` runs each probe twice on the `minimal-ts` fixture and asserts byte equality of the dumped slices. Catches unsorted-set and unsorted-dict leaks that golden files would only catch in S7-05.

- [ ] **AC-X4 — Per-probe warning ID frozenset + import-time assertion.** Each probe declares a `_WARNING_IDS` frozenset; the IDs match the Phase 1 ADR-0007 regex via import-time `assert`.

- [ ] **AC-X5 — Registry membership.** Each probe is imported in `src/codegenie/probes/__init__.py` via additive lines. `default_registry.all_probes()` includes all three.

- [ ] **AC-X6 — Tooling green.** `ruff check`, `ruff format --check`, `mypy --strict` on each module, `pytest tests/unit/probes/layer_b/test_{generated_code,node_reflection,semantic_index_meta}.py`. All green.

### Per-probe ACs

#### `GeneratedCodeProbe` — `src/codegenie/probes/layer_b/generated_code.py`

- [ ] **AC-G1 — Probe contract attributes.** `class GeneratedCodeProbe(Probe)`: `name="generated_code"`, `version="0.1.0"`, `layer="B"`, `tier="base"`, `applies_to_languages=["javascript","typescript"]`, `applies_to_tasks=["*"]`, `requires=["language_detection"]`, `timeout_seconds=30`, `declared_inputs=["**/*.ts", "**/*.tsx", "**/*.js", "package.json", "openapi.yaml", "openapi.yml", "schema.graphql", "prisma/schema.prisma"]`. Decorator `@register_probe` (defaults — light).

- [ ] **AC-G2 — Detection sources (data, not branches).**
  - **Header pattern match** via `_GENERATOR_HEADER_MARKERS` (AC-X2 example). For each candidate file, reads the **first 4096 bytes** via `Path.read_bytes()` with a `_MAX_HEAD_BYTES: Final[int] = 4096` constant (no `pathlib.Path.read_bytes()` size-limit kwarg exists — implementer slices `[:4096]`). Files shorter than 4 KB read fully. Iterates `_GENERATOR_HEADER_MARKERS` in declaration order — **first matching marker wins, dedup is by ordered iteration of the tuple** (deterministic; the tuple ordering IS the precedence policy and must be documented in a module-level comment naming the chosen precedence).
  - **Well-known generated directory match**: a separate `_GENERATED_DIRS: Final[frozenset[str]] = frozenset({"src/generated", "__generated__", "gen"})` (POSIX paths relative to `repo.root`). A file under one of these prefixes is flagged with `generator: "directory_convention"` and `confidence="medium"` even when no header marker is present (the directory convention is a strong signal but weaker than an explicit header).
  - **`package.json#scripts` heuristic** — `scripts.codegen`, `scripts["build:gql"]`, `scripts.generate` etc. are recorded as `regenerate_command` for matched generators. Read via `ctx.parsed_manifest(repo_root / "package.json")` when `ctx.parsed_manifest is not None`; **fallback to `safe_json.load(pkg_path, max_bytes=_PKG_JSON_MAX_BYTES)` when the memo is unavailable** (mirrors `language_detection.py:330` pattern — `if ctx.parsed_manifest is not None: return ctx.parsed_manifest(pkg_path); return safe_json.load(pkg_path, ...)`).
  - **`files` field** in the slice is the sorted union over all detection sources (header match ∪ directory match), keyed by `path` (POSIX-relative to `repo.root`). Sort key is `(path,)`. Sorting is part of AC-X9 (determinism).

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

- [ ] **AC-R0 — `_REPO_ROOT` resolves to the codewizard-sherpa repo, never the analyzed repo.** `_REPO_ROOT: Final[Path]` is a module-level constant computed at import via `Path(__file__).resolve().parents[N]` (implementer chooses `N` to land on the codewizard-sherpa repo root). The probe NEVER consults `ctx.workspace`, `ctx.output_dir`, or analyzed `repo.root` to locate grammar binaries — the grammars belong to codewizard-sherpa itself, not the analyzed repo. Test `test_grammars_resolved_from_codegenie_repo_root` builds a fixture-mode analyzed repo at a tempdir, runs the probe, and asserts the resolved `_REPO_ROOT / "tools/grammars.lock"` is codewizard-sherpa's lock file (NOT `<fixture>/tools/grammars.lock`, which doesn't exist). Mirrors S4-04 AC-Resolution.

- [ ] **AC-R1 — Probe contract attributes.** `class NodeReflectionProbe(Probe)`: `name="node_reflection"`, `version="0.1.0"`, `layer="B"`, `tier="base"`, `applies_to_languages=["javascript","typescript"]`, `applies_to_tasks=["*"]`, `requires=["language_detection"]`, `timeout_seconds=60`, `cache_strategy: Literal["content"] = "content"`, `declared_inputs=["**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx", "package.json", "tools/grammars.lock"]` (`tools/grammars.lock` is the codewizard-sherpa-resident cross-repo cache-key token — the coordinator's snapshot system already accepts it as a special token per S4-04 hardened story; a grammar version bump invalidates because the lock file content changes). Decorator `@register_probe(heaviness="medium")` — matches S4-04 parity (same per-file tree-sitter Query workload). The class implements `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`; one-arg `run(self, ctx)` is `TypeError` at dispatch.

- [ ] **AC-R2 — Grammar load delegates to the S4-03 kernel; no duplicated reader, no duplicated `GrammarLoadRefused`.** The probe imports from `codegenie.grammars.lock`:
  ```python
  from codegenie.grammars.lock import GrammarLockFile, GrammarLoadRefused, load_and_verify
  ```
  At grammar-load time the probe calls `lock = load_and_verify(_REPO_ROOT)` (the kernel reads `tools/grammars.lock`, validates via Pydantic, recomputes BLAKE3 over every vendored `.so` / `.dylib`, raises `GrammarLoadRefused` on mismatch — **before any grammar code executes**). The probe then constructs `tree_sitter.Language(pin.file, pin.language)` for `language ∈ {"typescript","javascript"}`. Per-`Language` construction is process-memoized via a module-level `@functools.lru_cache(maxsize=4)`-decorated helper `_get_language(lock_file_id: str, language: Literal["typescript","javascript"]) -> tree_sitter.Language` keyed on `(id(lock), language)`. The probe **does NOT** read `tools/grammars.lock` directly, **does NOT** call `blake3.blake3(...)`, **does NOT** declare a class named `GrammarLoadRefused`. Test `test_no_direct_lockfile_io` AST-walks the probe module and asserts: (a) no `Path("tools/grammars.lock")`-shaped string literal, (b) no `open(...)` with a `"grammars.lock"` substring argument, (c) no `import blake3` / `from blake3 import ...`, (d) no `class GrammarLoadRefused` definition. The kernel owns these.

  **Rule-of-three note (backlog only, do not extract in this story):** `_get_language` will be duplicated once between S4-04 and S4-06 — two consumers, not three. When the third consumer appears (Phase 8+ Python grammar), extract to `src/codegenie/grammars/loader.py`. **Do NOT pre-extract in S4-06**: rule-of-three is not yet triggered, and surfacing the duplication via a Note is the surgical Phase-2 choice.

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

- [ ] **AC-R4 — Slice shape per `localv2.md §5.2 B3`.** Every count field from the localv2 spec is emitted (`dynamic_property_access_count`, `eval_usage`, `function_constructor_usage`, `dynamic_require_count`, `dynamic_import_count`, `prototype_manipulation_count`, `decorator_usage.{nestjs,typeorm,class_validator,custom_decorators_detected}`, `middleware_chains`, `env_var_reads.{count,code_path_affecting}`, `confidence_impact`, `affected_files`). All `int` counts default to `0` when no match; `decorator_usage` flags default to `false`. `affected_files` is the **sorted** list of POSIX paths relative to `repo.root` where ≥ 1 reflection pattern hit (sort key is the path string; sorting is part of AC-X9 determinism).

- [ ] **AC-R5 — `decorator_usage.{nestjs,typeorm,class_validator}` detection via `package.json` deps.** Reads `dependencies` ∪ `devDependencies` from `ctx.parsed_manifest(repo.root / "package.json")` (returns `Mapping[str, Any] | None`); **fallback to `safe_json.load(pkg_path, max_bytes=5*1024*1024)` when `ctx.parsed_manifest is None`** (mirrors the `language_detection.py:330` pattern). Truth-tabled: `nestjs` ← `@nestjs/core` present; `typeorm` ← `typeorm` present; `class_validator` ← `class-validator` present. `custom_decorators_detected` counts decorator nodes (tree-sitter Query) NOT attributable to these three frameworks. (Detection is structural — name-based via package presence; not call-pattern.) Edge: when `package.json` is unparseable (`MalformedJSONError`), the three booleans default to `False`, `custom_decorators_detected` is still computed from AST, and `warnings: ["node_reflection.package_json_unparseable"]` is emitted.

- [ ] **AC-R6 — `env_var_reads.code_path_affecting` heuristic.** A `process.env.X` read is "code-path-affecting" if it appears within 2 AST levels of an `if_statement` or `switch_statement` condition. Tree-sitter Query captures the parent-context; the heuristic is data-driven (a single `_ENV_VAR_CODE_PATH_QUERY` string). The count is informational — `confidence_impact: medium` when `code_path_affecting > 0`.

- [ ] **AC-R7 — `confidence_impact` derivation (inverted-semantics, typed Literal).** Module-level type alias `_ConfidenceImpact: TypeAlias = Literal["high", "medium", "low"]` — **distinct from `_Confidence`** (AC-X3) so a typo `slice["confidence"] = "high"` when the inverted-semantics value was intended is caught by `mypy --strict` rather than at runtime. Derivation:
  - All counts == 0 AND `decorator_usage.{nestjs,typeorm,class_validator}` all False → `confidence_impact: "low"` (i.e., HIGH confidence that reflection isn't a concern — note the **inverted semantics**; the field is named `confidence_impact` not `confidence`, per the localv2 spec). Rule 8 — match the spec; clarify in implementer notes and the module docstring.
  - Any `eval_usage > 0` OR `function_constructor_usage > 0` → `confidence_impact: "high"` (these are rare and high-signal).
  - Otherwise → `confidence_impact: "medium"`.

  Test T-R7-mutation: a regression that swaps `"high"` ↔ `"low"` in either branch fails the per-branch assertion (T-R7, T-R8 below). The test does NOT use `in {"high", "low"}` — it asserts `== "high"` and `== "low"` respectively, so the inversion semantics are mutation-resistant.

- [ ] **AC-R8 — Grammar pin mismatch path.** On `GrammarLoadRefused` propagated from the kernel `load_and_verify` (imported from `codegenie.grammars.lock` — NOT a probe-local exception), the probe catches the exception and emits a slice with `confidence_impact: "high"` (the inverted-semantics "we couldn't measure, assume the worst — the gather output must not falsely claim low impact"); also sets `confidence: "low"` on the slice envelope; `affected_files: []`; `errors: ["node_reflection.grammar_pin_mismatch"]`; `warnings: []`. **No tree-sitter Query is executed**; no `Language` is constructed. T-R5 monkeypatches `codegenie.grammars.lock.load_and_verify` to raise `GrammarLoadRefused(...)`, runs the probe end-to-end, asserts the slice shape AND that `tree_sitter.Language` was never called (spy via `monkeypatch.setattr("tree_sitter.Language", Mock(side_effect=AssertionError("must not call")))`).

#### `SemanticIndexMetaProbe` — `src/codegenie/probes/layer_b/semantic_index_meta.py`

- [ ] **AC-M1 — Probe contract attributes.** `class SemanticIndexMetaProbe(Probe)`: `name="semantic_index_meta"`, `version="0.1.0"`, `layer="B"`, `tier="base"`, `applies_to_languages=["javascript","typescript"]`, `applies_to_tasks=["*"]`, `requires=["language_detection"]`, `timeout_seconds=10`, `declared_inputs=["tsconfig.json", "tsconfig.*.json", "package.json"]`. Decorator `@register_probe` (defaults — light). The class implements `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`.

  **Rationale for `requires=["language_detection"]` (NOT `["node_build_system"]`):** Phase 0 ADR-0007 freezes `ProbeContext` — no `sibling_slices` field — and `NodeBuildSystemProbe` does not write a `build_system.json` sidecar (its `raw_artifacts=[]`, see [`node_build_system.py:748`](../../../../src/codegenie/probes/node_build_system.py)). Cross-probe slice reads are therefore unavailable; `SemanticIndexMetaProbe` reads `tsconfig.json` directly. The topological dependency on `node_build_system` would only be load-bearing if its sibling slice were accessible, which it is not.

- [ ] **AC-M2 — Reads `tsconfig.json` via Phase 1 `jsonc` parser (no new parser, single-file read).** Uses `parsers.jsonc.load(tsconfig_path, max_bytes=5*1024*1024, max_depth=64)` (Phase 1 S1-04 caps). The probe reads `<repo.root>/tsconfig.json` only; **it does NOT walk `extends` chains** (that's `NodeBuildSystemProbe`'s job in S2-02 — duplicating it here would re-implement S2-02 and violate Rule 3). If a `tsconfig.json` extends another file, the slice's `has_extends: true` flag is set and the `target` / `module` / `module_resolution` / `strict` / `include_globs` / `exclude_globs` fields reflect the **literal `tsconfig.json` contents only** (post-jsonc-decode, no extends merge); a `warnings: ["semantic_index_meta.extends_chain_not_resolved"]` warning is emitted to make this honest. Phase 3 adapters that need the resolved view consult `build_system.typescript.resolved_compiler_options` (which Phase 1 already produces and writes to the `build_system` slice in the final `repo-context.yaml` — not to a sibling sidecar this probe can read).

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

- [ ] **AC-M4 — `files_count_estimate` consistency with `ScipIndexProbe.files_in_repo` via shared helper extraction.** Step 1 of the impl outline (mandatory, not optional): move the four S4-03 helpers from `src/codegenie/probes/layer_b/scip_index.py` (`_INDEXABLE_SUFFIXES`, `_EXCLUDE_DIRS`, `_read_exclude_file`, `_walk_indexable_files`, `_count_indexable_files`) into a new module `src/codegenie/probes/layer_b/_indexable_files.py`. Update `scip_index.py` to re-import. Update `semantic_index_meta.py` to import the same `_count_indexable_files`. **The exclude set is `frozenset({"node_modules", "dist", "build", ".git"})`** — verbatim from S4-03; no addition of `"out"`, no addition of `.js`/`.jsx` to the suffix set (SCIP's program scope is TS-only per `localv2.md §5.2 B1`). A structural test `test_semantic_index_meta_count_matches_scip_count` runs both `_count_indexable_files(root)` and the slice's `files_count_estimate` on the `minimal-ts` fixture and asserts exact equality. A second AST-walk test (`test_both_probes_import_indexable_files_kernel`) parses both `scip_index.py` and `semantic_index_meta.py` and asserts each contains an `import` resolving to the shared `_indexable_files` module — **divergence via copy-paste is mechanically forbidden, not just aspirationally tested.**

  *Scope note:* `_BUILD_OUTPUT_DIRS = frozenset({"dist", "build", "out"})` in `GeneratedCodeProbe` is a **separate concept** (build-output detection for distroless image build-stage decisions in Phase 7+) and is NOT shared with the SCIP indexable-file exclude set. The two sets overlap on `{"dist", "build"}` but the inclusion of `"out"` in build-output detection is a generator-convention signal (`out/` is a common bundler output dir), while the SCIP exclude set's purpose is "files SCIP would NOT index" and does not include `"out"` (S4-03 AC-9 precedent).

- [ ] **AC-M5 — Parse failure path.** `jsonc.load` raises `SizeCapExceeded` or `MalformedJSONError` → `confidence: "low"`, `errors: ["semantic_index_meta.tsconfig_unparseable"]`, slice contains `tsconfig_path` only.

### Cross-probe golden test

- [ ] **AC-X7 — Golden snapshots against `minimal-ts` fixture (when S7-01 lands).** Each probe ships a golden test slot — `tests/golden/probes/layer_b/{generated_code,node_reflection,semantic_index_meta}/minimal-ts.golden.yaml`. The goldens are stubbed in this story (empty placeholder + a `pytest.skip("golden produced in S7-05")` decorator on the test until the fixture lands). **Wired this way so S7-01/S7-05 can drop in the real golden without editing this story's code.**

## Implementation outline

1. **Extract `_indexable_files`** (mandatory per AC-M4). Move from `src/codegenie/probes/layer_b/scip_index.py` the five surfaces — `_INDEXABLE_SUFFIXES`, `_EXCLUDE_DIRS`, `_read_exclude_file`, `_walk_indexable_files`, `_count_indexable_files` — into a new module `src/codegenie/probes/layer_b/_indexable_files.py`. Update `scip_index.py` to `from codegenie.probes.layer_b._indexable_files import _count_indexable_files, _walk_indexable_files, _compute_indexable_merkle_input` (or equivalent — match what S4-03 actually uses). The extraction is a Rule-3 surgical refactor; the helpers are package-private (`_`-prefix) so the visibility is unchanged. Net delta to `scip_index.py`: import line + helper deletions (~70 LOC removed). Net add: ~70 LOC in `_indexable_files.py`. Confirm `pytest tests/unit/probes/layer_b/test_scip_index.py` stays green after the move (regression guard).

2. **`GeneratedCodeProbe` (target ≤ 90 SLOC by `radon raw --no-comments --no-blank`):**
   - Module-level constants per AC-X2: `_GENERATOR_HEADER_MARKERS: Final[tuple[tuple[str, bytes], ...]]`, `_BUILD_OUTPUT_DIRS: Final[frozenset[str]]`, `_GENERATED_DIRS: Final[frozenset[str]]`, `_MAX_HEAD_BYTES: Final[int] = 4096`, `_PKG_JSON_MAX_BYTES: Final[int] = 5 * 1024 * 1024`, `_WARNING_IDS: Final[frozenset[str]]` + import-time `_ID_PATTERN` validation (S4-04 / S4-01 precedent).
   - Pure helpers (NO I/O, NO `ctx`): `_detect_header_marker(content_head: bytes) -> str | None`, `_detect_directory_marker(rel_path: str) -> bool`, `_match_regenerate_command(generator: str, scripts: Mapping[str, Any]) -> str | None`, `_select_build_outputs(pkg: Mapping[str, Any] | None) -> list[str]`.
   - `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` (imperative shell): enumerate candidate files via shared walker; per file, read first `_MAX_HEAD_BYTES`; call `_detect_header_marker` then `_detect_directory_marker`; read `package.json` via `ctx.parsed_manifest` with `safe_json.load` fallback; compose slice; **sort `files` by path before emit**; build `ProbeOutput(schema_slice={"generated_code": ...}, raw_artifacts=[], confidence=..., duration_ms=..., warnings=..., errors=[])`.

3. **`NodeReflectionProbe` (target ≤ 100 SLOC by `radon raw --no-comments --no-blank`):**
   - Module-level constants: `_REFLECTION_QUERIES: Final[dict[str, str]]`, `_DECORATOR_DEP_TRUTH_TABLE: Final[tuple[tuple[str, str], ...]]` (e.g., `(("nestjs", "@nestjs/core"), ("typeorm", "typeorm"), ("class_validator", "class-validator"))` — extension by adding a tuple entry), `_WARNING_IDS` + `_ERROR_IDS` + import-time `_ID_PATTERN` validation. `_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[N]` (implementer chooses `N`).
   - Imports the kernel: `from codegenie.grammars.lock import GrammarLockFile, GrammarLoadRefused, load_and_verify`. Does NOT import from `codegenie.probes.layer_b.tree_sitter_import_graph` (its helpers are module-private; the kernel is the shared surface).
   - Process-memo: `@functools.lru_cache(maxsize=4) def _get_language(lock_id: int, language: Literal["typescript","javascript"]) -> tree_sitter.Language` — constructs `tree_sitter.Language(pin.file, pin.language)` for the matching pin after the kernel's BLAKE3 check passes.
   - Pure helpers (NO I/O, NO `ctx`): `_count_matches(language: tree_sitter.Language, query_str: str, file_bytes: bytes) -> int`, `_derive_confidence_impact(counts: Mapping[str, int], flags: Mapping[str, bool]) -> _ConfidenceImpact` (AC-R7 typed three-arm pattern match), `_decorator_flags(pkg: Mapping[str, Any] | None) -> dict[str, bool]`.
   - `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`: `try: lock = load_and_verify(_REPO_ROOT)` — `except GrammarLoadRefused: return <AC-R8 slice>`; enumerate files under `repo.root` via the shared `_walk_indexable_files`-style walker (the candidate set extends to `.js`/`.jsx`/`.ts`/`.tsx` — different from SCIP's TS-only walker, so do NOT reuse `_walk_indexable_files` directly; declare a local helper `_walk_node_source_files(root)` that excludes the same `_EXCLUDE_DIRS` but accepts the wider suffix set); per file, run each query; aggregate counts; **sort `affected_files`**; compose slice with both `confidence` (envelope) and `confidence_impact` (slice field, inverted-semantics).

4. **`SemanticIndexMetaProbe` (target ≤ 70 SLOC by `radon raw --no-comments --no-blank`):**
   - Imports the shared `_count_indexable_files` from `codegenie.probes.layer_b._indexable_files`.
   - Reads `<repo.root>/tsconfig.json` directly via `parsers.jsonc.load(tsconfig_path, max_bytes=5*1024*1024, max_depth=64)`. Does NOT walk `extends` chains (Rule 3 — that's S2-02's job; the slice carries `has_extends: bool` only).
   - Pure helpers: `_extract_compiler_option(payload: Mapping[str, Any], key: str, default: Any) -> Any`, `_normalize_string_list(value: Any) -> list[str]`.
   - `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`: try `jsonc.load`; on `SizeCapExceeded` / `MalformedJSONError` / `DepthCapExceeded` / `SymlinkRefusedError` → AC-M5 slice; on missing tsconfig → AC-M3 missing-tsconfig slice; otherwise compose the full slice with `files_count_estimate = _count_indexable_files(repo.root)`.

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
- **T-G7** `test_marker_catalog_is_open_closed` (AC-X2): AST-walk `generated_code.py`; assert (a) at least one `For` node iterates `_GENERATOR_HEADER_MARKERS`; (b) **no `Compare` node anywhere outside the `_GENERATOR_HEADER_MARKERS` assignment** compares to a string literal that is present as an entry-name (i.e., the first element of any tuple in `_GENERATOR_HEADER_MARKERS`) — this catches a regression that switches from data-driven dispatch to `if generator == "graphql-codegen"` branches even if the new code uses `in {"x", "y"}` rather than `==`. The walk reads `_GENERATOR_HEADER_MARKERS` from the module to derive the forbidden literal set at test time (no hardcoded literal list — adding a marker doesn't require editing the test).

#### NodeReflection
- **T-R1** `test_probe_contract_attributes` (AC-R1).
- **T-R2** `test_loc_budget` (AC-X1).
- **T-R3** `test_no_direct_lockfile_io_no_kernel_redeclaration` (AC-R2): AST-walk `node_reflection.py`; assert (a) no `Path(...)` string literal contains `"grammars.lock"`; (b) no `open(...)` call has an argument whose string literal contains `"grammars.lock"`; (c) no `import blake3` and no `from blake3 import ...`; (d) **no `class GrammarLoadRefused`** definition (the exception is imported from the kernel, NOT redeclared); (e) the import `from codegenie.grammars.lock import GrammarLockFile, GrammarLoadRefused, load_and_verify` IS present (a tampered import line would be caught here). Mirrors S4-04 `test_no_direct_lockfile_io`.
- **T-R4** `test_per_reflection_pattern_detection` (AC-R3): parametrize over `_REFLECTION_QUERIES`; synthesize a fixture file matching the pattern; assert count > 0.
- **T-R5** `test_grammar_pin_mismatch_path` (AC-R8): monkeypatch `codegenie.grammars.lock.load_and_verify` to raise `GrammarLoadRefused("test")`; spy `monkeypatch.setattr("tree_sitter.Language", Mock(side_effect=AssertionError("must not call")))`; run the probe end-to-end via `asyncio.run(probe.run(repo, ctx))`; assert no `AssertionError` (Language was never constructed), `confidence_impact == "high"` (inverted semantics), `confidence == "low"` (envelope), `errors == ["node_reflection.grammar_pin_mismatch"]`, `affected_files == []`.
- **T-R6** `test_decorator_usage_via_package_json` (AC-R5): `package.json` with `@nestjs/core`, no `typeorm`, with `class-validator`; assert `decorator_usage = {nestjs: true, typeorm: false, class_validator: true, custom_decorators_detected: 0}`.
- **T-R7** `test_eval_usage_promotes_high_confidence_impact` (AC-R7): fixture with `eval("...")`; assert `confidence_impact="high"`.
- **T-R8** `test_all_counts_zero_low_confidence_impact` (AC-R7): clean fixture; `confidence_impact="low"` (the "no reflection concern" terminal).
- **T-R9** `test_env_var_reads_code_path_affecting_heuristic` (AC-R6): fixture with `if (process.env.X) { ... }`; assert `code_path_affecting >= 1`.

#### SemanticIndexMeta
- **T-M1** `test_probe_contract_attributes` (AC-M1).
- **T-M2** `test_loc_budget` (AC-X1).
- **T-M3** `test_reads_tsconfig_via_phase1_jsonc_parser` (AC-M2): AST-walk; assert `from codegenie.parsers.jsonc import load` (or equivalent); assert no `json.load`/`open(tsconfig).read()` raw paths.
- **T-M4** `test_slice_shape_minimal_ts` (AC-M3): fixture `tsconfig.json` with target=es2022, module=esnext, strict=true; assert slice fields match.
- **T-M5** `test_files_count_estimate_matches_scip_count` (AC-M4): on a synthetic fixture tree, call `_count_indexable_files(root)` (imported from the extracted `codegenie.probes.layer_b._indexable_files`) and the `SemanticIndexMetaProbe`'s slice-level `files_count_estimate`; assert exact equality. Plus a second test `test_both_probes_import_indexable_files_kernel` AST-walks `scip_index.py` and `semantic_index_meta.py` and asserts each contains an `ImportFrom` node naming `codegenie.probes.layer_b._indexable_files` — copy-paste divergence is mechanically forbidden.
- **T-M6** `test_no_tsconfig_emits_medium_confidence` (AC-M3): empty fixture; `confidence="medium"`, `warnings=["semantic_index_meta.no_tsconfig"]`.
- **T-M7** `test_tsconfig_parse_failure_path` (AC-M5): fixture with truncated `tsconfig.json` (`{`); assert `confidence="low"`, `errors=["semantic_index_meta.tsconfig_unparseable"]`.

### Shared
- **T-X1** `test_layer_b_marker_probes_registered` (AC-X5): all three appear in `default_registry.all_probes()` after `from codegenie.probes import *`. Negative companion: a test that removes a probe import and asserts the registration is gone — verifies the registry isn't sticky across test runs.
- **T-X2** `test_warning_ids_match_adr_0007` for each (AC-X4): parametrize over the three modules' `_WARNING_IDS` (and `_ERROR_IDS` for `node_reflection`); assert every ID matches `_ID_PATTERN`. Companion: mutate one ID at module-import time (monkeypatch) to violate the pattern; assert `AssertionError` fires with the expected message — proves the load-bearing import-time guard isn't a bare `assert` that gets stripped under `python -O`.
- **T-X3** `test_probe_is_deterministic_on_fixture` (AC-X9): parametrize over the three probes; for each, run `asyncio.run(probe.run(repo, ctx))` twice against the same fixture (`tests/fixtures/portfolio/minimal-ts/` once it lands; until then a tempdir scaffolded by the test); assert `json.dumps(output1.schema_slice, sort_keys=True) == json.dumps(output2.schema_slice, sort_keys=True)` AND `output1.warnings == output2.warnings` AND `output1.errors == output2.errors`. Catches dict-iteration-order, unsorted-set, and frozenset-repr-stability leaks BEFORE S7-05's golden files land.
- **T-X4** `test_pure_helpers_have_no_io` (AC-X8): AST-walk each module; assert every function at module top level whose name does NOT start with `_run_` or equal `run` contains no `Call` to `open`, `Path.read_*`, `Path.write_*`, `subprocess.*`, `asyncio.create_subprocess_*`, `asyncio.to_thread`. Catches functional-core leaks.

### GREEN

Implement each probe per outline. Keep each file ≤ 100 LOC by extracting helpers ruthlessly and using catalog-driven detection.

### REFACTOR

- Run `radon raw --no-comments --no-blank <path>` on each file; confirm `sloc <= 100`.
- If `NodeReflectionProbe` exceeds the budget (likely tight given the tree-sitter query infrastructure), extract `_count_matches` to a shared util at `src/codegenie/probes/layer_b/_tree_sitter_helpers.py`. Do NOT inflate the budget — extraction is the discipline.
- Confirm `mypy --strict src/codegenie/probes/layer_b/{generated_code,node_reflection,semantic_index_meta,_indexable_files}.py` passes (the typed `_Confidence` / `_ConfidenceImpact` aliases are part of the discipline; a `dict[str, Any]` shortcut on the slice payload would un-type the inverted-semantics field).
- Verify the byte-identical determinism test (T-X3) is green before merge. A determinism leak that the golden files would otherwise catch in S7-05 is cheapest to fix now.

## Files to touch

**Create:**
- `src/codegenie/probes/layer_b/generated_code.py`
- `src/codegenie/probes/layer_b/node_reflection.py`
- `src/codegenie/probes/layer_b/semantic_index_meta.py`
- `src/codegenie/probes/layer_b/_indexable_files.py` (mandatory — AC-M4 step 1)
- `tests/unit/probes/layer_b/test_generated_code.py`
- `tests/unit/probes/layer_b/test_node_reflection.py`
- `tests/unit/probes/layer_b/test_semantic_index_meta.py`
- `tests/unit/probes/layer_b/test_indexable_files.py` (regression guard for the extracted helpers — at minimum, parametrizes over the existing scip_index tests that exercise the walker to confirm no behavioral change).
- Golden stubs (placeholders) at `tests/golden/probes/layer_b/{generated_code,node_reflection,semantic_index_meta}/minimal-ts.golden.yaml`.

**Edit (additive):**
- `src/codegenie/probes/__init__.py` — three additive imports.
- `src/codegenie/probes/layer_b/scip_index.py` — replace inline helper bodies with import from `codegenie.probes.layer_b._indexable_files`. Verify `pytest tests/unit/probes/layer_b/test_scip_index.py` stays green.

## Out of scope

- **Golden file content.** S7-01 lands the `minimal-ts` fixture; S7-05 produces real goldens. Stubs here; production goldens later.
- **Sub-schemas.** S4-07 lands per-probe sub-schemas.
- **`BuildGraphProbe`** (the localv2 §5.2 B5 cousin). The arch synthesizes this into `DepGraphProbe` (S4-05). Marker-style B5 detection is not a separate probe.
- **`ScipIndexProbe`-vs-`SemanticIndexMetaProbe` overlap.** SCIP probe is heavy (subprocess), SemanticIndexMeta is light (config-file read). Separate cache lifetimes. The overlap is intentional — they answer different questions.
- **Cross-language reflection patterns.** Phase 2 is Node-only. Python `eval`, Java reflection, Go reflection are Phase-8+.
- **Recursive directory walk depth.** Each probe walks `repo_root` with default depth — no cap — but excludes `node_modules`, `.git`, `dist`, `build`, `out` (canonical exclude set from S4-03). Adding a new exclude is a one-line addition to the shared `_indexable_files.py` exclude tuple.

## Notes for the implementer

- **Rule 8 — read before you write.** `codegenie.grammars.lock.load_and_verify` + `GrammarLoadRefused` (S4-03 kernel — **NOT a hypothetical `_load_grammar` in S4-04's module**; that helper is private), `_count_indexable_files` (S4-03, extracted by AC-M4 step 1), `ctx.parsed_manifest` (S1-07; allowlists `package.json` by default), `jsonc.load(path, *, max_bytes, max_depth=64)` (S1-04 — raises `SizeCapExceeded`, `DepthCapExceeded`, `MalformedJSONError`, `SymlinkRefusedError`), `safe_json.load` (S1-02; fallback when `ctx.parsed_manifest is None`) all exist. Reusing them is mandatory; AC-R2, AC-M2, AC-M4, AC-G2, and AC-X2 enforce structurally. T-R3 / T-M3 / T-G7 / T-M5 are the AST-walk discipline that catches drift.
- **The "marker probes are small" discipline.** AC-X1's 100-LOC budget is structural — it forbids creeping parser logic. A future contributor proposing "let's add `package-lock.json` parsing to `GeneratedCodeProbe` to detect `prisma generate` from the resolved dep tree" must be redirected: that's a parsing task; Phase 1's parsers OR a new dedicated probe is the right home. **Marker probes detect markers, period.**
- **`confidence_impact` inverted semantics in NodeReflection (AC-R7).** The localv2 spec's `confidence_impact` field is "how much does this erode confidence" — `"high"` means "high erosion = bad," `"low"` means "low erosion = good." This is inverted from the normal `confidence` field semantics. Document inline in the module docstring; do NOT alias to `confidence: high/medium/low` for cosmetic consistency — that would break the localv2 contract (Rule 11 — match codebase / spec convention).
- **Marker-absent ≠ degraded.** AC-X3 / AC-G4. A repo with no codegen output is normal. A renderer that highlights `confidence: medium` slices must NOT pile-up these honest absences as "warnings to escalate." Phase 8 renderer (Phase 8+) will categorize; Phase 2 just emits the honest typed shape.
- **Why split into three files instead of one fused probe.** Rule 7 — surface the conflict. Cache invalidation on a graphql-codegen change ≠ cache invalidation on a reflection scan ≠ cache invalidation on tsconfig change. Co-located in one module → all three invalidate on any of the three input changes. Separate modules → each owns its `declared_inputs`. Rule 2 says simplicity — but the cost of fusion (cache over-invalidation) outweighs the saving (one file vs three).
- **Tree-sitter Queries cheat-sheet.** The Queries used in `NodeReflectionProbe` are short S-expressions. Tree-sitter's docs explain the syntax; bundle them as inline string constants (Rule 11 — match S4-04's precedent). Don't pull in a `.scm` query-file vendoring system for ~10 queries.
- **`process.env.X` heuristic.** AC-R6 is a heuristic — perfect detection of "code-path-affecting" reads would require dataflow analysis (way beyond Phase 2). The 2-AST-level heuristic catches the canonical `if (process.env.X)` pattern. Document inline that this is a heuristic with known false-positives (e.g., `process.env.X` inside a `return` expression of an `if`-block body would be missed). Phase 8+'s richer Planner can refine.
- **`tsconfig_path` resolution (AC-M2).** Sibling-slice access is **not available** in Phase 2 — Phase 0 ADR-0007 freezes `ProbeContext` (no `sibling_slices` field) and `NodeBuildSystemProbe` does not write a `build_system.json` sidecar. `SemanticIndexMetaProbe` always reads the literal `<repo.root>/tsconfig.json` via `jsonc.load`. When the file `extends` another, the slice's `has_extends: true` is set and `warnings: ["semantic_index_meta.extends_chain_not_resolved"]` makes the limitation honest. Phase 3 adapters that need the merged compiler-options view consult the `build_system.typescript.resolved_compiler_options` payload that `NodeBuildSystemProbe` already places in the final `repo-context.yaml` — that is the sanctioned cross-probe pathway in Phase 2.
- **Rule 9 — tests verify intent.** T-G7 (AST-walk for branch-on-marker regressions) encodes the WHY of catalog-driven detection. T-R3 (no redeclared `GrammarLoadRefused`, no direct lock-file IO, kernel import present) encodes the WHY of the S4-03 kernel chokepoint. T-M5 (count equality + AST-asserted import of the shared helper) encodes the WHY of the extracted module. T-X3 (byte-identical reruns) encodes the WHY of determinism. T-X4 (no I/O in pure helpers) encodes the WHY of functional core / imperative shell. None of these check "the function works" — they check WHICH discipline is upheld.

- **Rule-of-three on `_get_language` (S4-04 + S4-06 = two consumers).** Do NOT pre-extract `_get_language` to a shared `codegenie.grammars.loader` module in this story. Two consumers is below the rule-of-three threshold (CLAUDE.md "extension by addition" + Rule 2 "three similar lines is better than premature abstraction"). When the third consumer appears (Phase 8+ Python tree-sitter grammar), elevate the helper to `src/codegenie/grammars/loader.py` as `language_for(lock, language) -> tree_sitter.Language`. **Backlog Note** — implementer should add a short comment near `_get_language` in `node_reflection.py` pointing at this elevation path.

- **Design-pattern shape (informational).** The two registries this story crosses (`@register_probe` for probe collection, and the implicit "marker catalog" tuples/dicts within each probe) embody the same Open/Closed pattern: a small stable kernel + a registry of capabilities, extension by addition. The marker catalogs are NOT a runtime registry (they are module-private `Final` tuples / dicts) — that's deliberate; per `02-ADR-0007` (no plugin loader in Phase 2), runtime registration via entry points or plugin loaders is forbidden. Each tuple/dict IS the registry, and the iteration loop IS the dispatch. The forthcoming Phase 8 (or beyond) `KernelRegistry[K, V]` could absorb these patterns once three precedents accumulate — but in Phase 2 the inline catalogs are surgical and grep-able.
