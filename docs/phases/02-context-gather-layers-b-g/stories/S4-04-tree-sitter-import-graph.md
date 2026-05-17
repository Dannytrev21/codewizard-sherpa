# Story S4-04 — `TreeSitterImportGraphProbe` — `py-tree-sitter` no-internal-threads + grammar pin

**Step:** Step 4 — Ship `IndexHealthProbe` (B2) + Layer B structural probes
**Status:** **UNBLOCKED + amended (2026-05-17)** — [02-ADR-0011](../ADRs/0011-tree-sitter-grammars-via-pypi-wheels.md) supersedes 02-ADR-0002. Grammar loading now flows through `codegenie.grammars.lock.language_for(name) -> tree_sitter.Language` (backed by PyPI wheels `tree-sitter-typescript` and `tree-sitter-javascript`). Ready to be picked up by the next executor run; the surface-name translations are documented below.
**Effort:** M
**Depends on:** S4-03 (originally landed `src/codegenie/grammars/lock.py` as the BLAKE3 verifier kernel; the file persists but its public surface is now `language_for(name) -> tree_sitter.Language` + `GrammarLoadRefused` per 02-ADR-0011). S4-04 **imports** the kernel; it does NOT redeclare `GrammarLoadRefused`, does NOT import per-grammar PyPI packages directly (no `from tree_sitter_typescript import ...`), and does NOT re-implement any grammar load step.
**ADRs honored:** [`02-ADR-0011`](../ADRs/0011-tree-sitter-grammars-via-pypi-wheels.md) (PyPI grammar wheels behind `language_for`; supersedes 02-ADR-0002 with the named-trigger C-extension discipline preserved), [`02-ADR-0003`](../ADRs/0003-coordinator-heaviness-sort-annotation.md) (`heaviness="medium"` is a registry annotation; no internal `ThreadPoolExecutor`), Phase 0 [`ADR-0006`](../../00-bullet-tracer-foundations/ADRs/0006-pyproject-toml-extras-shape.md) (the runtime closure is `[project.dependencies]`; `gather` extras is intentionally empty), Phase 1 ADR-0008 (in-process parse caps, not per-probe sandbox; grammar code runs in the gather process), Phase 1 ADR-0007 (warning ID pattern). The body below still cites 02-ADR-0002 verbatim — every such reference now points through 02-ADR-0011's supersession (the named-trigger discipline carries forward unchanged).

## 02-ADR-0011 translation table (read this BEFORE the body)

The story was written against 02-ADR-0002's vendored-`.so` model. The 2026-05-17 supersession changed the kernel surface but left every other AC valid. Apply these mechanical translations as you read:

| Legacy surface (S4-03 first edition / 02-ADR-0002) | Current surface (02-ADR-0011) |
|---|---|
| `from codegenie.grammars.lock import load_and_verify, GrammarLockFile, GrammarPin, GrammarLoadRefused` | `from codegenie.grammars.lock import language_for, SupportedLanguage, GrammarLoadRefused` |
| `lock = load_and_verify(_REPO_ROOT)` | `language = language_for("typescript")` (also `"tsx"`, `"javascript"`) |
| `tree_sitter.Language(pin.file, pin.language)` for `pin in lock.grammars` | `language_for(name)` returns a constructed `tree_sitter.Language` directly |
| `_get_language(lock_file_id, language)` `lru_cache` helper | not needed — the kernel memoizes via `functools.lru_cache` already |
| AC asserting "no `Path('tools/grammars.lock')` literal" | becomes "no `from tree_sitter_typescript import ...` / `from tree_sitter_javascript import ...`" |
| AC asserting "no `import blake3`" | preserved — still applies (the kernel handles supply-chain pinning at the wheel boundary, not the probe) |
| AC asserting "no `class GrammarLoadRefused` redeclaration" | preserved verbatim |
| AC referencing `tools/grammars.lock` as `declared_inputs` cache-key token | replaced by `pyproject.toml` + `uv.lock` (the wheel SHA256 pin) — a grammar bump invalidates because the wheel SHA256 changes. The legacy `tools/grammars.lock` token is no longer a valid declared input. |
| Grammar pin mismatch → `GrammarLoadRefused` slice (`confidence="low"`) | preserved — the kernel still raises `GrammarLoadRefused` on every failure surface (missing wheel, unknown language, capsule factory drift, ABI mismatch). The probe-side honest-absence slice (Phase 2 `NodeReflectionProbe` ships the same shape — see `src/codegenie/probes/layer_b/node_reflection.py:_emit_grammar_unavailable`) is the reference implementation. |

Mirror the `NodeReflectionProbe` GREEN implementation (2026-05-17, S4-06 attempt 2 — `src/codegenie/probes/layer_b/node_reflection.py` + `tests/unit/probes/layer_b/test_node_reflection.py`) for every mechanical detail: kernel import line, `Parser(language)` construction, per-`(language, query)` Query caching, AST-walk discipline that forbids per-grammar PyPI imports.

## Validation notes (2026-05-16 — phase-story-validator)

Verdict: **HARDENED**. Edits applied in place:

- **BLOCK / consistency.** `GrammarLoadRefused` and grammar-load logic moved to **import the kernel from `codegenie.grammars.lock`** (the chokepoint S4-03 AC-20 explicitly built for this probe). The probe no longer redefines `GrammarLoadRefused`, no longer reads `tools/grammars.lock` directly, no longer recomputes BLAKE3. AC-2 / AC-3 rewritten; impl outline step 2 deleted (kernel owns it); the dedicated `_errors.py` was eliminated.
- **BLOCK / consistency.** `Probe.run` signature corrected to two-arg `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` per the frozen ABC at `src/codegenie/probes/base.py:94`. Impl outline step 6 + AC-12 + every TDD-plan invocation updated; `self._parse_all(repo, ctx, ...)` everywhere.
- **BLOCK / consistency.** `py-tree-sitter` moved to `[project.dependencies]` per Phase 0 ADR-0006 (`gather` extras is intentionally empty — the runtime closure IS `[project.dependencies]`; the fence ADR-0002 reads that list). AC-14 rewritten; T-16 follows.
- **BLOCK / coverage.** Grammar-file path resolution promoted from implementer-note to AC-Resolution: `_REPO_ROOT` is the codewizard-sherpa repo root (computed at module import via `Path(__file__).resolve().parents[N]` constant), NEVER `ctx.workspace` / `repo.root`. T-resolution exercises a fixture-mode analyzed repo to confirm.
- **HARDEN / coverage.** Determinism: edges sorted lexicographically by `(from, to)`; JSON written with `sort_keys=True, separators=(",", ":")`; atomic write via tempfile + `os.replace`. New AC-DET; new property test T-prop-idempotent.
- **HARDEN / test-quality.** T-06 (thread count) scoped to set-difference by `Thread.ident`, filtered to threads NOT present before `asyncio.run(probe.run(...))`. T-05 / T-07 specified as AST-precise walks with explicit forbidden-symbol lists (`asyncio.gather`, `asyncio.wait`, `asyncio.to_thread`, `loop.run_in_executor`, `loop.create_task`, etc.); the single admissible coordination primitive is `asyncio.wait_for` exactly once.
- **HARDEN / design-patterns.** `_extract_imports_from_file` split into pure `_extract_imports(language, source_bytes, relative_path) -> list[Edge]` (functional core) + thin I/O shell. New AC-PURE; new T-pure-isolation.
- **HARDEN / design-patterns.** `Edge` made a typed model (Pydantic frozen `extra="forbid"`, `Field(alias="from")` for `from_path`). Newtype discipline for the import-graph payload.
- **HARDEN / coverage.** Very-large-file guard (skip files > 4 MiB; `tree_sitter.file_too_large` warning; counted in `failed_files`). New AC-LARGE.
- **HARDEN / coverage.** Indexable-files enumeration uses the Phase 1 shared helper (`_enumerate_indexable_files`); explicit AC pins symlink + `node_modules/` + `.codegenie/` exclusion.
- **HARDEN / consistency.** `has_error` API spelled precisely: `tree.root_node.has_error`. `tree` itself has no `has_error` attribute in modern `py-tree-sitter`.
- **HARDEN / consistency.** Import-time validation uses `raise AssertionError(...)` (S4-01 precedent at [`src/codegenie/probes/layer_b/index_health.py:121-123`](../../../../src/codegenie/probes/layer_b/index_health.py)), NOT bare `assert`.
- **HARDEN / coverage.** Confidence rubric pinned to a discrete unambiguous rule (not "≥ 50% succeeded"): `high` iff `failed_files == 0 AND parsed_files > 0`; `medium` iff `failed_files > 0 AND parsed_files >= failed_files`; `low` otherwise. AC-7 rewritten.
- **HARDEN / mypy.** `[[tool.mypy.overrides]]` entry for `tree_sitter.*` (`ignore_missing_imports = true`) added to AC-MYPY; cleaner than per-line `# type: ignore` and matches Phase 1's convention.
- **CLARIFICATION.** Explicit non-AC: tree-sitter is NOT a B2 freshness index source (S4-01's `IndexName` registry covers `scip`, `runtime_trace`, `semgrep`, `gitleaks`, `conventions` only). The probe writes `raw/import-graph.json` and emits an `import_graph` slice; it does NOT write `<output_dir>/raw/tree_sitter.json` and B2 does NOT read it.

Full audit log: [`_validation/S4-04-tree-sitter-import-graph.md`](_validation/S4-04-tree-sitter-import-graph.md).

## Context

`TreeSitterImportGraphProbe` extracts file-level import edges from the source tree using `tree-sitter` grammars and emits forward-only adjacency to `raw/import-graph.json`. Phase 3's adapters (`ImportGraphAdapter` `Protocol` shipped in S1-08) decide reverse projection; Phase 2 emits only.

Three disciplines from [ADR-0002](../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md), [phase-arch-design.md §"Component design" #12](../phase-arch-design.md), and S4-03's chokepoint are load-bearing:

1. **Grammar load goes through the shared `codegenie.grammars.lock` kernel** (S4-03 AC-20). The probe imports `load_and_verify(repo_root) -> GrammarLockFile` and `GrammarLoadRefused`; the kernel reads `tools/grammars.lock`, validates it via Pydantic, recomputes BLAKE3 over every vendored `.so` / `.dylib`, and raises `GrammarLoadRefused` on mismatch — **before any grammar code executes**. The probe never re-reads the lock file, never recomputes BLAKE3, never re-declares the exception. Duplicating the kernel surface would silently fork the supply-chain defense; the chokepoint is what makes it auditable.
2. **In-process load.** Grammar binaries are loaded in-process via `tree_sitter.Language(path, language_name)` after the kernel's BLAKE3 check passes. No `_grammar_runner` subprocess — [ADR-0002 §Consequences](../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md) rejects subprocess wrap as over-engineering for a threat the pin already addresses. A crashed grammar crashes the gather process; Phase 0 failure isolation contains it to one probe via `asyncio.wait_for`. Loudness is a feature (Rule 12).
3. **No internal `ThreadPoolExecutor`, no `asyncio.gather`, no `loop.run_in_executor`, no `asyncio.to_thread`** — the probe is one slot under the Phase 0 single `Semaphore(min(cpu_count(), 8))`. Hidden parallelism inside a probe lies to the coordinator's budget ([ADR-0003 §Decision](../ADRs/0003-coordinator-heaviness-sort-annotation.md) reinforces this). Per-file extraction is sequential under the probe; the coordinator owns concurrency across probes. **Verified by thread-count set-difference assertion at test time** (the manifest risk callout specifically warned against "absence-of-`threading`-import" being a sufficient test), AND by an AST-precise grep for forbidden coordination primitives.

[ADR-0002 §Consequences](../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md) explicitly rejects `_grammar_runner` (out-of-process subprocess for tree-sitter invocations) — the grammar pin already addresses the threat; the subprocess wrap is over-engineering. In-process is the boring shape; a crashed grammar crashes the gather process, and Phase 0 failure isolation contains it to one probe via `asyncio.wait_for`. Loudness is a feature (Rule 12).

The slice ([localv2.md §5.2 B3](../../../localv2.md) — `NodeReflectionProbe` SLICE has reflection data, NOT import edges; this probe lands forward-only adjacency under a `import_graph` slice that the architecture treats separately from `reflection`). The arch [§"Component design" #12](../phase-arch-design.md) names `raw/import-graph.json` as the artifact; the slice itself summarizes (`files_with_imports`, `total_edges`, `cyclic_components_count`, `confidence`). Production consumers (Phase 3's `ImportGraphAdapter`) read the raw JSON, not the slice.

## References — where to look

- **Architecture:**
  - [`../phase-arch-design.md §"Component design" #12`](../phase-arch-design.md) — full internal structure; load-bearing properties: in-process, no thread pool, grammar pin verified.
  - [`../phase-arch-design.md §"Edge cases" row 10`](../phase-arch-design.md) — tree-sitter grammar BLAKE3 mismatch.
  - [`../phase-arch-design.md §"Design patterns applied"`](../phase-arch-design.md) row "Anti-patterns avoided" — "hidden parallelism inside a probe lies to the coordinator's budget."
- **Phase 2 ADRs:**
  - [`../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md`](../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md) — full rationale; in-process; pin-at-load; `_grammar_runner` rejected; one named-trigger exception to Phase 1 ADR-0009.
  - [`../ADRs/0003-coordinator-heaviness-sort-annotation.md`](../ADRs/0003-coordinator-heaviness-sort-annotation.md) — `heaviness="medium"`; no internal pools.
- **Phase 1 ADRs:**
  - [`docs/phases/01-context-gather-layer-a-node/ADRs/0009-no-new-c-extension-parser-dependencies.md`](../../01-context-gather-layer-a-node/ADRs/0009-no-new-c-extension-parser-dependencies.md) — the policy this ADR amends.
- **Source design:**
  - [`docs/localv2.md §5.2 B3`](../../../localv2.md) — `NodeReflectionProbe` uses tree-sitter as a sibling pattern; this probe is the import-graph one.
- **Existing code:**
  - `tools/grammars.lock` + `tools/grammars/{typescript,javascript}.so` (from S4-03).
  - `src/codegenie/probes/base.py` (frozen).
  - `src/codegenie/probes/registry.py` (extended in S1-08).

## Goal

Running `codegenie gather` against a TypeScript/JavaScript repo populates `.codegenie/context/raw/import-graph.json` (a JSON file containing forward-only adjacency, NetworkX-serializable shape, edges sorted lexicographically by `(from, to)`, byte-identical across two consecutive runs on the same inputs) AND emits an `import_graph` slice summarizing edge counts. The probe delegates grammar load + BLAKE3 verification to the **shared `codegenie.grammars.lock` kernel** (S4-03 AC-20) — no duplicated reader, no duplicated `GrammarLoadRefused`, no per-file re-verification; mismatch surfaces as the kernel's typed exception and the probe slice records `confidence="low"`, `errors=["tree_sitter.grammar_pin_mismatch"]` with **no grammar code executed**. The probe contains zero `ThreadPoolExecutor`, zero `multiprocessing.Pool`, zero `asyncio.gather`, zero `asyncio.to_thread`, zero `loop.run_in_executor` — per-file extraction is sequential under the probe's single coordinator slot, verified by thread-count set-difference assertion (not just import absence) AND AST-precise forbidden-symbol grep. Tree-sitter is **not** a B2 freshness-index source (B2's `IndexName` registry from S4-01 covers `scip`, `runtime_trace`, `semgrep`, `gitleaks`, `conventions` only); the probe writes `raw/import-graph.json` and emits an `import_graph` slice, and that is the totality of its contract.

## Acceptance criteria

- [ ] **AC-1 — Probe contract attributes.** `src/codegenie/probes/layer_b/tree_sitter_import_graph.py` defines `class TreeSitterImportGraphProbe(Probe)` with class attributes: `name="tree_sitter_import_graph"`, `version="0.1.0"`, `layer="B"`, `tier="base"`, `applies_to_languages=["javascript","typescript"]`, `applies_to_tasks=["*"]`, `requires=["language_detection"]`, `timeout_seconds=120`, `cache_strategy: Literal["content"] = "content"`. `declared_inputs` includes `["**/*.ts", "**/*.tsx", "**/*.js", "**/*.jsx", "tools/grammars.lock"]` (the lock-file is part of the cache key — a grammar version bump invalidates because the lock file content changes). The decorator is `@register_probe(heaviness="medium")`. **The class implements** `async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput` — two-arg signature per the frozen ABC at [`src/codegenie/probes/base.py:94`](../../../../src/codegenie/probes/base.py). One-arg `run(self, ctx)` is a `TypeError` at dispatch.

- [ ] **AC-2 — Grammar load delegates to the shared kernel; no duplicated reader, no duplicated `GrammarLoadRefused`.** The probe imports from `codegenie.grammars.lock`:
  ```python
  from codegenie.grammars.lock import GrammarLockFile, GrammarLoadRefused, load_and_verify
  ```
  At grammar-load time the probe calls `lock = load_and_verify(_REPO_ROOT)` (the kernel reads `tools/grammars.lock`, validates via Pydantic, recomputes BLAKE3 over every vendored `.so` / `.dylib`, raises `GrammarLoadRefused` on mismatch — **before any grammar code executes**). The probe then constructs `tree_sitter.Language(pin.file, pin.language)` for `language ∈ {"typescript","javascript"}`. Per-`Language` construction is process-memoized via a module-level `@functools.lru_cache(maxsize=4)`-decorated helper `_get_language(lock_file_id: str, language: Literal["typescript","javascript"]) -> tree_sitter.Language`, keyed on `(id(lock_file), language)` so the kernel's `GrammarLockFile` identity preserves cache correctness across consecutive `run()` calls within one process. The probe **does not** read `tools/grammars.lock` directly, **does not** call `blake3.blake3(...)`, **does not** declare `GrammarLoadRefused`. T-no-direct-lockfile-IO AST-walks the probe module and asserts no `open(`, `Path("tools/grammars.lock")`, `blake3` import — those belong to the kernel.

- [ ] **AC-3 — `GrammarLoadRefused` is the kernel's exception; the probe catches and translates it to a slice.** The probe's `run` catches `GrammarLoadRefused` (imported from `codegenie.grammars.lock` — NOT re-declared), and emits a slice with `confidence="low"`, `errors=["tree_sitter.grammar_pin_mismatch"]`, `warnings=[]` (kernel-side detail does not surface as a warning; the structured-log record on the kernel side has the language + expected/actual BLAKE3), `total_edges=0`, `files_with_imports=0`, `parsed_files=0`, `failed_files=0`. The probe writes **no** `import-graph.json` — the file is absent on disk after a mismatch run (atomic-write discipline of AC-DET means a half-populated file is never observable; the file simply does not exist). The structured log record from the probe includes the grammar language whose pin failed (pulled from the caught exception's attributes) AND the canonical error ID `tree_sitter.grammar_pin_mismatch`.

- [ ] **AC-Resolution — `_REPO_ROOT` resolves to the codewizard-sherpa repo, never the analyzed repo.** `_REPO_ROOT: Final[Path]` is a module-level constant computed at import via `Path(__file__).resolve().parents[N]` (implementer chooses `N` to land on `src/codegenie/probes/layer_b/` → repo root). The probe NEVER consults `ctx.workspace`, `ctx.output_dir`, `repo.root`, or any analyzed-repo path to locate grammar binaries — the grammars belong to *codewizard-sherpa itself*, not the analyzed repo. A test (`test_grammars_resolved_from_codegenie_repo_root`) uses a fixture-mode analyzed repo at `tests/fixtures/portfolio/minimal-ts/` and asserts the probe's resolved `_REPO_ROOT / "tools/grammars.lock"` is the codewizard-sherpa repo's lock file, NOT `<fixture>/tools/grammars.lock` (which doesn't exist).

- [ ] **AC-4 — No internal `ThreadPoolExecutor`, no parallel-coordination primitives; verified by thread-count set-difference AND AST-precise forbidden-symbol grep.**
  - **T-05 (import-name AST walk):** AST-walks the probe module. For every `ast.Import` and `ast.ImportFrom` node, asserts no module name in the set `{"threading", "concurrent", "concurrent.futures", "multiprocessing", "multiprocessing.pool", "asyncio.subprocess"}` appears as an import target. Aliased imports (`import threading as _t`) are caught because the AST walk inspects `node.name`, not the alias.
  - **T-06 (runtime thread-count set-difference):** Captures `threads_before = {t.ident for t in threading.enumerate()}` before `asyncio.run(probe.run(repo, ctx))`; captures `threads_after` after; asserts `(threads_after - threads_before) == set()`. Set-difference avoids brittleness from pytest-xdist / hypothesis / structlog-async threads pre-existing in the process. If tree-sitter's C library spawns a thread the test does not own, the assertion is scoped via `Thread.name`: any new thread whose `name.lower()` contains `"tree_sitter"` is considered upstream-library-owned and excluded — this scoping is explicit in the test code with a TODO comment referencing the upstream issue, NOT silent.
  - **T-07 (forbidden coordination primitives AST walk):** AST-walks every `ast.Call` in the module. Asserts no call whose `func` resolves to any of `asyncio.gather`, `asyncio.wait`, `asyncio.as_completed`, `asyncio.create_task`, `asyncio.to_thread`, `loop.run_in_executor`, `loop.create_task`, `functools.partial(asyncio.gather, ...)`. **The single admissible asyncio-coordination primitive is `asyncio.wait_for(coro, timeout=...)`, exactly once, at the `run()` boundary** (AC-12).
  - The probe processes files in a synchronous `for file in indexable_files: ...` loop inside an `async def` shell. The loop body calls only synchronous helpers; there is no `await` inside the loop. The single `await` in the probe is the kernel boundary at `asyncio.wait_for(_parse_all(repo, ctx), timeout=...)` in `run()`.

- [ ] **AC-PURE — Functional core / imperative shell separation.** Per-file extraction is split:
  - `_extract_imports(language: tree_sitter.Language, source_bytes: bytes, relative_path: str) -> list[Edge]` is **pure** — no `Path` access, no `open(...)`, no `read_bytes`, no logging side-effects. Inputs: the Language object, the source bytes, the file's repo-relative path string. Output: a list of `Edge`. Tested in isolation against in-memory byte strings (`T-pure-isolation`) — no temp directories, no file fixtures.
  - `_read_and_extract(path: Path, language: tree_sitter.Language, relative_path: str) -> list[Edge]` is the thin shell that does `path.read_bytes()` then calls `_extract_imports(...)`. This is the only function in the per-file path that touches the filesystem; it is also the function that handles parse errors / `tree.root_node.has_error` and raises `_PerFileParseFailed`.

- [ ] **AC-5 — Per-file extraction emits forward-only adjacency; deterministic shape.** For each TypeScript / JavaScript file, `_extract_imports` parses the source via `tree_sitter.Parser()` configured with the language (`parser.language = language` for `py-tree-sitter ≥ 0.21`), walks the AST with a tree-sitter Query, and extracts every `import X from "..."` (ES module), `import "..."` (side-effect), `export ... from "..."` (re-export), and `require("...")` (CommonJS literal-string call). Output `Edge`:
  ```python
  class Edge(BaseModel):
      model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)
      from_path: str = Field(alias="from")   # relative-to-repo POSIX path
      to: str                                # specifier as it appears in source
  ```
  Forward-only — no reverse adjacency in Phase 2 (Phase 3's `ImportGraphAdapter` builds it). `to` values are emitted verbatim from the source (string literal as it appears in the import statement — `"./utils"`, `"lodash"`, `"@scope/pkg"`, etc.). No resolution to filesystem paths — that's Phase 3 adapter territory. Dynamic `import(specifier)` where `specifier` is a non-literal (variable, expression, template-literal-with-interpolation) is **omitted** (not emitted as `"<dynamic>"`) — Phase 3's reflection adapter is the right layer for dynamic resolution.

- [ ] **AC-DET — Deterministic, byte-identical artifact across reruns.** Before writing `import-graph.json`, edges are sorted **lexicographically by `(from_path, to)`**. The artifact is serialized via `json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)` and written **atomically**: write to a sibling `import-graph.json.tmp` then `os.replace(...)`. T-prop-idempotent (Hypothesis property test) generates two runs against the same fixture set and asserts the on-disk artifact bytes are identical. A partial-timeout run (AC-12) also writes atomically — Phase 3 readers never observe a half-written file.

- [ ] **AC-6 — `import-graph.json` schema_version + Pydantic well-formedness.** The artifact has top-level `{"schema_version": 1, "edges": [...]}`. A small `ImportGraphArtifact` Pydantic model lives in the probe module (`frozen=True`, `extra="forbid"`) and is the (de)serialization boundary. A unit test (`test_import_graph_json_well_formed`) loads the artifact via `ImportGraphArtifact.model_validate_json(...)`. `schema_version: 1` is the current value; future shape changes bump and require a Phase-N ADR.

- [ ] **AC-7 — Slice summary fields; confidence rubric is discrete and unambiguous.** The `import_graph` slice contains:
  - `files_with_imports: int` — count of source files where ≥ 1 edge was emitted.
  - `total_edges: int`.
  - `parsed_files: int`, `failed_files: int`.
  - `confidence: Literal["high","medium","low"]` per **exactly this rubric** (no thresholds, no arithmetic ratios):
    - `"high"` iff `failed_files == 0 AND parsed_files > 0`.
    - `"medium"` iff `failed_files > 0 AND parsed_files >= failed_files`.
    - `"low"` iff `parsed_files < failed_files` OR `parsed_files == 0` (empty repo — see AC-9) OR `GrammarLoadRefused` fired (AC-3) OR timeout fired (AC-12).
  - `import_graph_uri: str` (`".codegenie/context/raw/import-graph.json"` — relative path). **Omitted** when no artifact is written (mismatch/timeout-with-zero-edges).
  - `grammar_versions: dict[str, str]` — `{"typescript": "0.20.6", "javascript": "0.20.4"}` from the kernel's `GrammarLockFile`; provenance. **Omitted** on `GrammarLoadRefused` (the lock did not load).

- [ ] **AC-8 — Per-file parse failure is contained.** `_read_and_extract` checks `tree.root_node.has_error` (the precise modern `py-tree-sitter ≥ 0.21` API) after `parser.parse(source_bytes)`. If `tree.root_node.has_error` is `True`, OR if `parser.parse` raises any exception, the function raises the internal `_PerFileParseFailed` and the caller increments `failed_files`; no edges are emitted from that file; `warnings.append("tree_sitter.file_parse_failed")` with a count cap (≤ 5 distinct entries — past 5, increment an internal counter and emit one summary `tree_sitter.parse_failed_count_exceeded` warning). The probe does NOT raise from `run()`. **A future refactor that adds `pytest.raises(SyntaxError)` here would defeat the discipline** — failure containment is the contract.

- [ ] **AC-LARGE — Very-large-file guard.** Files whose size exceeds 4 MiB (`4 * 1024 * 1024` bytes) are skipped before `read_bytes` (a `Path.stat().st_size` check), counted in `failed_files`, and emit warning `tree_sitter.file_too_large` (subject to the same ≤ 5 cap and summary semantics as AC-8). Tree-sitter is robust but parsing a 50-MB bundled `.js` from a `dist/` directory can OOM the process and would defeat AC-12's timeout containment.

- [ ] **AC-INDEXABLE — Indexable files come from the Phase 1 shared enumerator.** The probe imports `_enumerate_indexable_files` (or its successor name) from the Phase 1 shared helper module (Rule 11 — match codebase convention; the helper is referenced by S4-03's SCIP probe and is the source of truth for symlink / `node_modules/` / `.codegenie/` exclusion). The probe does NOT re-implement file enumeration. A structural test asserts the helper is imported, not redefined; if the helper does not yet expose a JavaScript/TypeScript filter, the probe filters by extension after enumeration.

- [ ] **AC-9 — Empty-repo guard.** If `parsed_files == 0 AND failed_files == 0` (an empty repo or one with zero `.ts`/`.tsx`/`.js`/`.jsx` files), `confidence="low"`, `warnings.append("tree_sitter.no_files_to_parse")`, and **no** `import-graph.json` is written (no artifact, no `import_graph_uri` in the slice). Without this guard, an empty repo would pass through with `confidence="high"` — the silent-confidence failure mode B2 exists to prevent. T-09 exercises this.

- [ ] **AC-10 — `confidence="low"` slice on `GrammarLoadRefused`.** Per AC-3. No `import-graph.json` is written. The slice contains `files_with_imports=0`, `total_edges=0`, `parsed_files=0`, `failed_files=0`, `confidence="low"`, `errors=["tree_sitter.grammar_pin_mismatch"]`. T-10 monkeypatches `codegenie.grammars.lock.load_and_verify` to raise `GrammarLoadRefused(language="typescript", expected_blake3=..., actual_blake3=...)` and asserts the slice shape end-to-end (including absence of the artifact on disk).

- [ ] **AC-11 — Warning + error ID frozenset; module-level `raise AssertionError` validation.** All IDs (`tree_sitter.grammar_pin_mismatch`, `tree_sitter.file_parse_failed`, `tree_sitter.parse_failed_count_exceeded`, `tree_sitter.no_files_to_parse`, `tree_sitter.file_too_large`, `tree_sitter.timeout`) are declared in module-level `_WARNING_IDS: Final[frozenset[str]]` and `_ERROR_IDS: Final[frozenset[str]]`. Import-time validation matches the S4-01 precedent at [`src/codegenie/probes/layer_b/index_health.py:121-123`](../../../../src/codegenie/probes/layer_b/index_health.py): `for _id in _WARNING_IDS | _ERROR_IDS: if not _ID_PATTERN.match(_id): raise AssertionError(f"ADR-0007 violation: {_id!r}")`. Bare `assert` is not used (Rule 11 — match convention). A unit test (`test_warning_error_ids_match_adr_0007`) also exercises the regex against the frozenset contents.

- [ ] **AC-12 — Timeout containment via `asyncio.wait_for`; atomic partial-graph write.** The probe's `run` is `await asyncio.wait_for(self._parse_all(repo, ctx), timeout=self.timeout_seconds)`. **The `wait_for` is the ONLY admissible asyncio-coordination primitive** — `asyncio.gather`, `asyncio.to_thread`, `loop.run_in_executor`, `loop.create_task` are all forbidden (AC-4). On `asyncio.TimeoutError`, the slice contains whatever partial state was accumulated up to the timeout point AND `confidence="low"`, `warnings=["tree_sitter.timeout"]`. The artifact `import-graph.json` is written **atomically** (per AC-DET — sorted edges, tempfile + `os.replace`) with the partial edges if `total_edges > 0`; otherwise the artifact is omitted. A partial graph is better than no graph for Phase 3 fallback — UNLIKE `ScipIndexProbe` (S4-03 AC-6 where partial blobs are deleted) — because the sorted-then-atomically-written JSON is a complete document of partial content, never a truncated stream. T-13 asserts atomicity by failing the test if `import-graph.json.tmp` exists after `run()` returns.

- [ ] **AC-13 — Registry membership + `for_task` filter.** `src/codegenie/probes/__init__.py` imports `TreeSitterImportGraphProbe` via an explicit additive line (the side-effect import triggers `@register_probe`). `default_registry.all_probes()` includes it with `heaviness="medium"`. `for_task("*", frozenset({"typescript"}))` and `for_task("*", frozenset({"javascript"}))` include it; languages outside `applies_to_languages` (e.g., `frozenset({"python"})`) skip it.

- [ ] **AC-14 — `py-tree-sitter` lands in `[project.dependencies]`, NOT in `[project.optional-dependencies] gather`.** Per Phase 0 [ADR-0006](../../00-bullet-tracer-foundations/ADRs/0006-pyproject-toml-extras-shape.md) §Decision, the `gather` extras is intentionally empty — the runtime closure IS `[project.dependencies]`; the fence ([Phase 0 ADR-0002](../../00-bullet-tracer-foundations/ADRs/0002-fence-ci-job-no-llm-in-gather.md)) scans `[project.dependencies]` for the LLM SDK ban. The new entry is `tree-sitter ~= 0.21` (the modern PyPI package name; older `py-tree-sitter` aliases the same project — pin to the name the project ships at the chosen version). `pip-audit` and `osv-scanner` continue to scan it via the standard `[project.dependencies]` reading path. A unit test (`test_pyproject_lists_tree_sitter_in_project_dependencies`) parses `pyproject.toml` via `tomllib`, reads `project.dependencies`, asserts the entry exactly once.

- [ ] **AC-MYPY — Tree-sitter typing override in `pyproject.toml`.** `tree-sitter`'s package is not `py.typed`. Add a `[[tool.mypy.overrides]]` entry in `pyproject.toml`:
  ```toml
  [[tool.mypy.overrides]]
  module = ["tree_sitter", "tree_sitter.*"]
  ignore_missing_imports = true
  ```
  This is cleaner than scattering `# type: ignore[import-untyped]` at every `import tree_sitter` site (Phase 1 precedent: other untyped-third-party packages use the override block). A unit test parses `pyproject.toml` and asserts the override block exists.

- [ ] **AC-15 — Tooling green.** `ruff check`, `ruff format --check`, `mypy --strict src/codegenie/probes/layer_b/tree_sitter_import_graph.py`, `pytest tests/unit/probes/layer_b/test_tree_sitter_import_graph.py`. All green.

## Implementation outline

1. **Create `src/codegenie/probes/layer_b/tree_sitter_import_graph.py`.** Class per AC-1 with two-arg `run(self, repo, ctx)` signature.

2. **Import the kernel** (AC-2): `from codegenie.grammars.lock import GrammarLockFile, GrammarLoadRefused, load_and_verify`. Do **not** redefine `GrammarLoadRefused`; do **not** read `tools/grammars.lock`; do **not** call `blake3`.

3. **Module-level `_REPO_ROOT: Final[Path]`** (AC-Resolution): `Path(__file__).resolve().parents[N]` where `N` lands on the codewizard-sherpa repo root (`src/codegenie/probes/layer_b/foo.py` → `parents[4]` is `<repo-root>`; verify `N` empirically).

4. **`_get_language(lock: GrammarLockFile, language: Literal["typescript","javascript"]) -> tree_sitter.Language`** (AC-2 process-memo) — module-level helper, `@functools.lru_cache(maxsize=4)` keyed on `(id(lock), language)`. Looks up the pin by language in the typed `GrammarLockFile`, constructs `tree_sitter.Language(pin.file, language)`, returns it. The kernel's `load_and_verify` is the BLAKE3 chokepoint; this helper only constructs the `Language` after the lock is verified.

5. **Pure helper `_extract_imports(language: tree_sitter.Language, source_bytes: bytes, relative_path: str) -> list[Edge]`** (AC-PURE): parses `source_bytes`, walks the AST via tree-sitter Queries (`_TS_IMPORT_QUERY`, `_JS_IMPORT_QUERY` module constants), emits `Edge(from_path=relative_path, to=specifier)` for each hit. No I/O.

6. **Shell helper `_read_and_extract(path: Path, language: tree_sitter.Language, relative_path: str) -> list[Edge]`** (AC-PURE): does `Path.stat().st_size` check (AC-LARGE); on too-large raises `_PerFileTooLarge`. Reads bytes via `path.read_bytes()`. Parses; on parser exception OR `tree.root_node.has_error == True` (AC-8), raises `_PerFileParseFailed`. Otherwise calls `_extract_imports(...)` and returns the result.

7. **Sequential loop `_parse_all(self, repo: RepoSnapshot, ctx: ProbeContext, language_objs: dict[str, tree_sitter.Language]) -> tuple[list[Edge], int, int, list[str]]`** — synchronous-inside-async:
   ```python
   edges: list[Edge] = []
   parsed = 0
   failed = 0
   warnings: list[str] = []
   for file in _enumerate_indexable_files(repo.root):
       if file.suffix not in (".ts", ".tsx", ".js", ".jsx"):
           continue
       language = language_objs["typescript"] if file.suffix in (".ts", ".tsx") else language_objs["javascript"]
       relative_path = file.relative_to(repo.root).as_posix()
       try:
           file_edges = _read_and_extract(file, language, relative_path)
           edges.extend(file_edges)
           parsed += 1
       except _PerFileTooLarge:
           failed += 1
           _accumulate_warning(warnings, "tree_sitter.file_too_large")
       except _PerFileParseFailed:
           failed += 1
           _accumulate_warning(warnings, "tree_sitter.file_parse_failed")
   return edges, parsed, failed, warnings
   ```
   No `await` inside the loop. `_accumulate_warning` enforces the ≤ 5 cap + summary-emit semantics of AC-8 / AC-LARGE.

8. **`async def run(self, repo: RepoSnapshot, ctx: ProbeContext) -> ProbeOutput`** (AC-1 / AC-12):
   - Try `lock = load_and_verify(_REPO_ROOT)`; on `GrammarLoadRefused` build the mismatch slice (AC-3/AC-10) and return immediately — no artifact write, no further work.
   - Construct `language_objs = {"typescript": _get_language(lock, "typescript"), "javascript": _get_language(lock, "javascript")}`.
   - `await asyncio.wait_for(_parse_all(self, repo, ctx, language_objs), timeout=self.timeout_seconds)` — but `_parse_all` itself is `async def` only so it can be cancelled by `wait_for`; its body is synchronous (no `await` inside).
   - Catch `asyncio.TimeoutError`; recover partial state via a `nonlocal`-style accumulator (or split `_parse_all` to push state into `self`'s instance variables guarded by cancellation; the implementer chooses the shape — the test (T-13) pins behavior, not mechanism).
   - Sort `edges` lexicographically by `(from_path, to)` (AC-DET).
   - If `edges` non-empty: atomic-write `import-graph.json` to `ctx.output_dir / "raw" / "import-graph.json"` via tempfile + `os.replace`. Else: do not write.
   - Compute `confidence` per AC-7 rubric.
   - Build slice with all AC-7 fields (omitting `import_graph_uri` and `grammar_versions` when applicable).
   - Return `ProbeOutput(schema_slice=..., raw_artifacts=[artifact_path] if written else [], confidence=..., duration_ms=..., warnings=..., errors=...)`.

9. **Register the probe** via `src/codegenie/probes/__init__.py` additive import (matches S4-01 precedent).

10. **Add `tree-sitter ~= 0.21` to `[project.dependencies]`** in `pyproject.toml` (AC-14). Add the `[[tool.mypy.overrides]]` block for `tree_sitter.*` (AC-MYPY).

## TDD plan — red / green / refactor

### Test helpers preamble

```python
# tests/unit/probes/layer_b/test_tree_sitter_import_graph.py
from __future__ import annotations
import ast, asyncio, json, os, threading
from pathlib import Path
import pytest
from codegenie.grammars.lock import GrammarLoadRefused          # AC-2/AC-3 — kernel exception, NOT a probe-local class
from codegenie.probes.base import RepoSnapshot, ProbeContext
from codegenie.probes.layer_b.tree_sitter_import_graph import (
    TreeSitterImportGraphProbe,
    Edge,
    ImportGraphArtifact,
    _extract_imports,        # pure helper — AC-PURE
    _get_language,           # process-memo helper — AC-2
)


@pytest.fixture(autouse=True)
def _clear_language_cache():
    """``_get_language`` is ``lru_cache``-decorated. Tests that mutate the
    grammar lock (T-03/T-04/T-10) must run against a cold cache."""
    _get_language.cache_clear()
    yield
    _get_language.cache_clear()
```

### RED

- **T-01** `test_probe_contract_attributes` (AC-1): asserts class attributes, two-arg `run` signature (`inspect.signature(TreeSitterImportGraphProbe.run).parameters` keys are `{"self", "repo", "ctx"}`).
- **T-02** `test_grammar_kernel_load_happy_path` (AC-2): calls `load_and_verify(_REPO_ROOT)` directly (NOT through the probe) and asserts the returned `GrammarLockFile` has both TypeScript and JavaScript entries with vendored binaries that pass BLAKE3.
- **T-03** `test_grammar_kernel_load_mismatch_propagates` (AC-3): monkeypatches `tools/grammars/typescript.so` content to a tampered byte string in a tempdir copy of `tools/`; calls `load_and_verify(tempdir)` (kernel surface — NOT a re-implemented probe helper) and asserts `GrammarLoadRefused` is raised with the language name embedded in the message.
- **T-04** `test_grammar_pin_mismatch_grammar_code_does_not_execute` (AC-3): stronger — spy via `monkeypatch.setattr("tree_sitter.Language", Mock(side_effect=AssertionError("must not call")))`; tamper the lock content; run the probe end-to-end via `asyncio.run(probe.run(repo, ctx))`; assert no `AssertionError`, slice has `confidence="low"`, `errors==["tree_sitter.grammar_pin_mismatch"]`.
- **T-05** `test_no_parallelism_imports` (AC-4): parses the probe module via `ast.parse(Path(...).read_text())`; for every `ast.Import` / `ast.ImportFrom`, asserts no module name in `{"threading", "concurrent", "concurrent.futures", "multiprocessing", "multiprocessing.pool", "asyncio.subprocess"}`. Aliased imports caught by inspecting `node.name`, not the alias.
- **T-06** `test_no_threads_created_during_run` (AC-4 — load-bearing): captures `threads_before = {t.ident for t in threading.enumerate()}` before `asyncio.run(probe.run(repo, ctx))`; captures `threads_after` after; asserts `(threads_after - threads_before) - {t.ident for t in threading.enumerate() if "tree_sitter" in t.name.lower()} == set()`. The `tree_sitter`-name filter is explicit in the test source with a TODO comment — it documents the upstream-library exemption rather than masking it silently.
- **T-07** `test_no_forbidden_coordination_primitives` (AC-4): AST-walks every `ast.Call` in the probe module; asserts no call resolves to `asyncio.gather`, `asyncio.wait`, `asyncio.as_completed`, `asyncio.create_task`, `asyncio.to_thread`, `loop.run_in_executor`, `loop.create_task`, or `functools.partial(asyncio.gather, ...)`. The only admissible `asyncio.*` call is `asyncio.wait_for` (also asserted positively — exactly one call site, inside `run`).
- **T-no-direct-lockfile-IO** (AC-2): AST-walks the probe module; asserts no `Path("tools/grammars.lock")`-shaped string literal, no `open(...)` with `"grammars.lock"` substring, no `import blake3`, no `from blake3 import ...`. The kernel owns these.
- **T-resolution** `test_grammars_resolved_from_codegenie_repo_root` (AC-Resolution): builds a fixture-mode analyzed repo at a tempdir, points `ctx.workspace` / `repo.root` there; runs the probe; asserts the probe loaded the codewizard-sherpa repo's `tools/grammars.lock` (verified by inspecting the kernel's structured-log record OR by checking that the probe succeeded — the fixture repo has no `tools/` of its own, so any resolution to it would fail loudly).
- **T-pure-isolation** `test_extract_imports_is_pure` (AC-PURE): constructs an in-memory `source_bytes = b"import x from 'lodash';\n"`, calls `_extract_imports(language, source_bytes, "src/index.ts")` directly (no fixture filesystem); asserts `[Edge(from_path="src/index.ts", to="lodash")]`. A monkeypatch on `pathlib.Path.read_bytes` raising `AssertionError("filesystem touched")` asserts no I/O occurred during the pure-helper call.
- **T-08** `test_per_file_parse_failure_contained` (AC-8): fixture with one valid `.ts` file and one with a deliberate syntax error (`function (`); asserts `parsed_files==1`, `failed_files==1`, slice `warnings` contains `"tree_sitter.file_parse_failed"`, probe returns without raising. Uses `tree.root_node.has_error` semantics — verified by ensuring the helper does NOT catch a Python exception, only checks the boolean.
- **T-LARGE** `test_file_too_large_skipped` (AC-LARGE): fixture with a 5-MiB `.ts` file containing real syntax; asserts `failed_files==1`, slice `warnings` contains `"tree_sitter.file_too_large"`, AND tree-sitter is **not** called on the file (spy via monkeypatching `tree_sitter.Parser.parse`).
- **T-09** `test_no_files_to_parse_is_low_confidence` (AC-9): empty repo (no `.ts`/`.tsx`/`.js`/`.jsx`); assert `confidence="low"`, `warnings == ["tree_sitter.no_files_to_parse"]`, AND `import-graph.json` is not on disk, AND `import_graph_uri` is absent from the slice.
- **T-10** `test_grammar_load_refused_full_slice` (AC-10): `monkeypatch.setattr("codegenie.probes.layer_b.tree_sitter_import_graph.load_and_verify", Mock(side_effect=GrammarLoadRefused(language="typescript", expected_blake3="abc", actual_blake3="def")))`; assert slice fields per AC-10; assert `import-graph.json` does NOT exist on disk; assert `grammar_versions` and `import_graph_uri` are omitted from the slice.
- **T-11** `test_forward_only_adjacency_shape` (AC-5/AC-6): fixture with `src/a.ts` importing `lodash` and `./utils`, `src/b.ts` importing `react`; run probe; load `import-graph.json`; assert exact sorted shape `[{"from":"src/a.ts","to":"./utils"},{"from":"src/a.ts","to":"lodash"},{"from":"src/b.ts","to":"react"}]` (lex-sorted by `(from, to)`).
- **T-12** `test_slice_summary_fields` (AC-7): exercise three runs (clean, partial-failure, mismatch); for each, assert every field in the slice matches the AC-7 rubric, including the `confidence` discrete-rule mapping.
- **T-13** `test_timeout_contained_partial_graph_written_atomically` (AC-12): monkeypatch `_read_and_extract` so that the third file's call awaits an unsignalled future (the implementer chooses how — likely via a fake `Language` that blocks); `timeout_seconds=1`; assert `asyncio.TimeoutError` does NOT propagate; `confidence="low"`, `warnings` contains `"tree_sitter.timeout"`; assert `import-graph.json` exists with the first two files' sorted edges; assert `import-graph.json.tmp` does NOT exist (atomic-write discipline).
- **T-prop-idempotent** `test_two_runs_produce_byte_identical_artifact` (AC-DET; Hypothesis): generate a list of synthetic TypeScript files (`hypothesis.strategies.lists(...)` of import statements); run the probe twice (cold cache between runs via `_get_language.cache_clear()`); assert `Path("...import-graph.json").read_bytes()` is byte-identical between runs.
- **T-14** `test_warning_error_ids_match_adr_0007` (AC-11): imports `_WARNING_IDS`, `_ERROR_IDS`, `_ID_PATTERN` from the module; asserts every ID matches the regex.
- **T-15** `test_registry_membership_heaviness_medium` (AC-13): asserts the probe is in `default_registry.all_probes()` with `heaviness="medium"`, `runs_last=False`; asserts `for_task("*", frozenset({"typescript"}))` and `for_task("*", frozenset({"javascript"}))` include it; asserts `for_task("*", frozenset({"python"}))` excludes it.
- **T-16** `test_pyproject_lists_tree_sitter_in_project_dependencies` (AC-14): parses `pyproject.toml` via `tomllib`; asserts `tree-sitter` (or the pinned name) appears exactly once in `project.dependencies`; asserts it does NOT appear in `project.optional-dependencies.gather` (which must remain empty per Phase 0 ADR-0006).
- **T-MYPY** `test_pyproject_has_tree_sitter_mypy_override` (AC-MYPY): parses `pyproject.toml`; asserts a `tool.mypy.overrides` entry exists with `module` including `"tree_sitter"` and `ignore_missing_imports = true`.

### GREEN

Implement the module per outline. Source the tree-sitter Query strings from the tree-sitter-typescript and tree-sitter-javascript README query examples (the import-extraction queries are stable across recent grammar versions; bundle them in `_TS_IMPORT_QUERY` and `_JS_IMPORT_QUERY` module constants).

### REFACTOR

- Confirm `_enumerate_indexable_files` is the Phase 1 shared helper (Rule 11). If S4-03 has not yet extracted a JS/TS variant, this probe's `.ts/.tsx/.js/.jsx` extension filter lives at the call site; do not duplicate enumeration policy.
- Verify the structured-log event for `run()` emits `parsed_files`, `failed_files`, `total_edges`, `grammar_versions` for ops observability — and that on `GrammarLoadRefused` it logs the language + expected/actual BLAKE3 (sourced from the kernel's exception attributes).
- Confirm `mypy --strict` passes via the AC-MYPY override block.

## Files to touch

**Create:**
- `src/codegenie/probes/layer_b/tree_sitter_import_graph.py`
- `tests/unit/probes/layer_b/test_tree_sitter_import_graph.py`
- `tests/fixtures/portfolio/minimal-ts/` — small fixture for T-resolution, T-11, T-prop-idempotent. (If a sibling fixture already exists in S4-03's fixture set, prefer reusing it — Rule 11.)

**Edit (additive):**
- `src/codegenie/probes/__init__.py` — additive import (side-effect-registers the probe).
- `pyproject.toml`:
  - `[project.dependencies]` adds `tree-sitter ~= 0.21` (NOT `[project.optional-dependencies] gather`).
  - `[[tool.mypy.overrides]]` block for `tree_sitter.*` (AC-MYPY).

**Pre-existing (from S4-03 — imported, not re-implemented):**
- `src/codegenie/grammars/lock.py` — `load_and_verify`, `GrammarLockFile`, `GrammarLoadRefused`. The probe IMPORTS this kernel.
- `tools/grammars.lock`, `tools/grammars/typescript.so`, `tools/grammars/javascript.so` — read by the kernel, NOT by the probe.

## Out of scope

- **Reverse adjacency / `ImportGraphAdapter`.** Phase 3 plugin owns reverse lookups. This story emits forward-only.
- **Symbol-level resolution.** SCIP (S4-03) is the symbol-level layer; tree-sitter is statement-level.
- **Dynamic `import("./" + name)` resolution.** Forward-only emission records the literal specifier as-emitted in source; if the source has `import(specifier)` where `specifier` is a variable, the probe emits `to: "<dynamic>"` placeholder OR omits (implementer choice — recommend omit, and let `NodeReflectionProbe` (out of scope for this probe; it's S5-/B3 territory if a Phase-3 reflection probe is needed) handle dynamic patterns).
- **Other languages.** TypeScript + JavaScript are Phase-2-required. Python / Go / Java grammars are Phase-8+ ADR-amendments to ADR-0002.
- **Out-of-process `_grammar_runner`** — explicitly rejected by [ADR-0002 §Decision](../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md). Do NOT propose subprocess isolation; the grammar pin is the supply-chain defense.
- **Re-verification per file.** AC-2 explicitly says the BLAKE3 is verified at process startup, not per file. A future contributor proposing "re-verify per file for safety" is to be redirected here — the trust boundary is the process.

## Notes for the implementer

- **The kernel is the source of truth (AC-2).** S4-03's AC-20 deliberately built `codegenie.grammars.lock` as the chokepoint for both stories. A future contributor proposing "let's read `tools/grammars.lock` directly because it's a small file" is to be redirected here: the kernel owns BLAKE3 verification, the typed `GrammarLockFile`, and `GrammarLoadRefused`. Duplicating any of these silently forks the supply-chain defense. T-no-direct-lockfile-IO is the structural test that catches the regression.
- **The thread-count test (T-06) is the load-bearing one.** The manifest's risk callout for this story: "verify by enumerating thread count, not just by absence of `threading` import." A future contributor could (a) import `asyncio` (admissible), (b) use `loop.run_in_executor(None, ...)` or `asyncio.to_thread(...)` to spawn threads from the default executor, (c) violate the discipline without importing `threading` directly. T-06 catches (b) — `threading.enumerate()` sees the executor's threads. T-07 catches the AST form of the same violation. The combination of T-05 (forbidden imports) + T-06 (runtime thread-count) + T-07 (forbidden call symbols) is the load-bearing triple.
- **Process-memoization is on `_get_language`, not on `load_and_verify`.** The kernel may itself memoize, but the probe's side is a `functools.lru_cache(maxsize=4)` on `_get_language(lock, language)`. Test code MUST call `_get_language.cache_clear()` between mutation tests of the lock file (see the test preamble's `autouse=True` fixture). Per-file re-verification would be the kind of "defensive over-engineering" Rule 2 forbids; the trust boundary is process startup AND the kernel call.
- **`_REPO_ROOT` resolution (AC-Resolution).** `Path(__file__).resolve().parents[N]` — the `N` depends on file location. From `src/codegenie/probes/layer_b/tree_sitter_import_graph.py`: `parents[0]` is `layer_b/`, `parents[1]` is `probes/`, `parents[2]` is `codegenie/`, `parents[3]` is `src/`, `parents[4]` is the repo root. Verify empirically; pin in a module constant with a doc-comment explaining the count.
- **The `tree-sitter` API.** Modern `tree-sitter` (≥ 0.21 on PyPI) uses `tree_sitter.Language(path, name)` for loading and `parser.language = language` then `parser.parse(source_bytes)`. The query API: `language.query(query_string).captures(tree.root_node)` returns a list of `(node, capture_name)` pairs. Pin to a modern minor version (`~= 0.21`) so the import idiom is stable.
- **Tree-sitter Query language.** The probe uses tree-sitter Queries (S-expression syntax) to match import patterns. For TypeScript: `(import_statement source: (string) @specifier)`, `(export_statement source: (string) @specifier)`, side-effect imports `(import_statement source: (string) @specifier)`. For CommonJS `require`: `(call_expression function: (identifier) @func arguments: (arguments (string) @specifier) (#eq? @func "require"))`. Bundle the queries as module constants and document them inline — Phase 2 only needs ~6 query patterns; a vendored `.scm` query file is premature.
- **Edges sort + atomic write (AC-DET) are not optional.** Phase 3's `ImportGraphAdapter` will be tested by checksumming `import-graph.json`; if the order varies across runs, every Phase 3 cache invalidates spuriously. Sort + `sort_keys=True` + atomic-replace is the minimal cost; do it once at the write boundary.
- **The `[project.dependencies]` placement (AC-14) is non-negotiable.** Phase 0 ADR-0006 §Decision: `gather = []` is intentionally empty. The fence ADR-0002 reads `[project.dependencies]`. Adding `tree-sitter` to the `gather` extras would silently exclude it from the fence's LLM-SDK check (the check uses set difference; the SDK list is the blocklist, not the allowlist — so the omission would be silent but the dependency would still install via `pip install -e .[gather]`). Match the repo convention; the slot exists for documentation, not for runtime separation.
- **The "loudness is a feature" framing.** [ADR-0002 §Tradeoffs](../ADRs/0002-tree-sitter-grammars-phase-2-amendment.md) — "A crashed grammar crashes the gather process; Phase 0 failure isolation contains it to one probe via `asyncio.wait_for`, and the loudness is a feature." A grammar binary CVE or corruption is a real risk; the response is a CI failure (loud), not a silent skip. The `asyncio.wait_for` containment is what makes this safe — the worst case is the gather drops this one probe's output and continues.
- **Functional core / imperative shell (AC-PURE) earns its keep here.** `_extract_imports` will eventually need to handle: dynamic imports, TSX/JSX-specific syntax, type-only imports, re-exports. Every one of those is a parser-side concern that can be unit-tested against in-memory byte strings. Keeping the I/O shell thin (one function, one filesystem touch) means the parser tests need zero fixtures and zero monkeypatching — they're literally `assert _extract_imports(lang, source, "x.ts") == [...]`.
- **Rule 9 — tests verify intent.** T-04 (grammar code does not execute on pin mismatch) encodes the WHY of the pin (supply-chain defense). T-06 (no threads created) encodes the WHY of the no-internal-pool rule (honesty to coordinator). T-pure-isolation encodes the WHY of functional core (testability + extensibility). T-prop-idempotent encodes the WHY of deterministic JSON (Phase 3 cache stability). T-13 (timeout writes partial graph atomically) encodes the WHY of "partial-graph-is-better-than-no-graph" — distinct from S4-03 where partial blobs are deleted, because sorted-then-atomically-written JSON degrades gracefully and `.scip` doesn't. Every test name and assertion message must point at WHICH discipline is being defended.
